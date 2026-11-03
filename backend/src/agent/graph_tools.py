"""Tools the agent uses to search the ontology and edit the query graph.

Besides subjects and links, the optional constraint tools (group
``CONSTRAINT_TOOLS``, switched off with ``constraint_tools=False``) add
subqueries to subjects: a filter on a datatype property (Number/Date/String/
BooleanSubQuery, picked by the property's literal range) or the restriction to
one instance (SubjectSubQuery), as progressive discovery builds them
(assistant/progressive.py, constraint_modifications).
"""

import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from agent.protocol import GraphDetails
from agent.tools import ToolCollection, ToolError, tool
from assistant.assistant_model import (
    AnyAssistantSubQuery,
    AssistantLink,
    AssistantNumberConstraintType,
    AssistantStringConstraintType,
    AssistantSubject,
    BooleanSubQuery,
    DateSubQuery,
    NumberSubQuery,
    QueryGraph,
    StringSubQuery,
    SubjectSubQuery,
)
from assistant.progressive import literal_value_kind, slug
from explorative.exp_model import (
    RELATION_TYPE,
    RETURN_TYPE,
    FuzzyQuery,
    FuzzyQueryResult,
)
from model import InstanceQuery, Subject, SubjectLink
from utils import wrap_iri

if TYPE_CHECKING:
    from explorative.explorative_support import GuidanceManager
    from ontology import OntologyManager


class ClassCandidate(BaseModel):
    uri: str
    label: str
    parents: list[str] | None = None  # URIs of the parent classes, if known


class LinkCandidate(BaseModel):
    uri: str
    label: str
    # domain and range of the property
    from_uri: str | None = None
    from_label: str | None = None
    to_uri: str | None = None
    to_label: str | None = None


ValueType = Literal["number", "date", "string", "boolean"]


class PropertyCandidate(BaseModel):
    """A datatype property a subject can be constrained on."""

    uri: str
    label: str
    # how values are compared, from the literal range
    value_type: ValueType
    range: str | None = None


class InstanceCandidate(BaseModel):
    uri: str
    label: str


def same_uri(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and wrap_iri(a) == wrap_iri(b)


# tool group of the constraint (subquery) tools
CONSTRAINT_TOOLS = "constraints"
RDFS_LABEL = "rdfs:label"
OWL_THING = "http://www.w3.org/2002/07/owl#Thing"

ConstraintOperator = Literal[
    "equals", "!=", "less", "greater", "contains", "startswith", "endswith", "regex"
]
OPERATOR_ALIASES = {
    "=": "equals",
    "==": "equals",
    "eq": "equals",
    "equal": "equals",
    "is": "equals",
    "<": "less",
    "lt": "less",
    "less_than": "less",
    "before": "less",
    ">": "greater",
    "gt": "greater",
    "greater_than": "greater",
    "after": "greater",
    "<>": "!=",
    "ne": "!=",
    "neq": "!=",
    "not_equals": "!=",
    "starts_with": "startswith",
    "ends_with": "endswith",
}
OPERATORS_OF: dict[str, list[str]] = {
    "number": [o.value for o in AssistantNumberConstraintType],
    "date": [o.value for o in AssistantNumberConstraintType],
    "string": [o.value for o in AssistantStringConstraintType],
    "boolean": ["equals", "!="],
}
TRUE_VALUES = {"true", "yes", "1"}
FALSE_VALUES = {"false", "no", "0"}


class GraphEditorTools(ToolCollection):
    """Ontology search and query graph editing on ``graph``.

    ``details`` keeps the ontology data of the subjects/links the agent added,
    which the frontend needs to render them (see protocol.GraphDetails).
    """

    def __init__(
        self,
        ontology_manager: "OntologyManager",
        guidance: "GuidanceManager",
        graph: QueryGraph | None = None,
        retrieve_k: int = 5,
        constraint_tools: bool = True,
    ):
        self.ontology_manager = ontology_manager
        self.guidance = guidance
        self.graph = graph if graph is not None else QueryGraph()
        self.retrieve_k = retrieve_k
        # the constraint tools are only exposed to the model if enabled
        self.constraint_tools = constraint_tools
        self.disabled_groups = (
            frozenset() if constraint_tools else frozenset({CONSTRAINT_TOOLS})
        )
        self.details = GraphDetails()
        # links seen in search results, by URI; they carry domain/range and counts
        self._known_links: dict[str, SubjectLink] = {}
        # datatype properties found by search_properties, by (class, property) IRI
        self._known_properties: dict[tuple[str, str], PropertyCandidate] = {}
        # instances listed by restrict_to_instance, by (class, instance) IRI
        self._known_instances: dict[tuple[str, str], InstanceCandidate] = {}
        self._prefixes: dict[str, str] | None = None

    def prune_details(self):
        """Forget details of elements that are no longer in the graph."""
        subject_ids = {s.id for s in self.graph.subjects}
        link_ids = {l.id for l in self.graph.links}
        self.details.subjects = {
            k: v for k, v in self.details.subjects.items() if k in subject_ids
        }
        self.details.links = {
            k: v for k, v in self.details.links.items() if k in link_ids
        }

    def details_for(self, graph: QueryGraph) -> GraphDetails:
        return GraphDetails(
            subjects={
                s.id: self.details.subjects[s.id]
                for s in graph.subjects
                if s.id in self.details.subjects
            },
            links={
                l.id: self.details.links[l.id]
                for l in graph.links
                if l.id in self.details.links
            },
        )

    def _subject(self, subject_id: str) -> AssistantSubject:
        subject = self.graph.get_subject_by_id(subject_id)
        if subject is None:
            raise ToolError(
                f"Subject {subject_id} is not in the query graph, existing subjects: "
                f"{[s.id for s in self.graph.subjects]}"
            )
        return subject

    @tool()
    def search_classes(self, query: str) -> list[ClassCandidate]:
        """Search the ontology for classes matching a description of a subject.

        Args:
            query: what the user is looking for, e.g. "ship" or "military person".

        Returns:
            The best matching classes as [{"uri": "<http://dbpedia.org/ontology/Ship>", "label": "ship"}, ...].
            Use their uri with add_subject.
        """
        results = self.guidance.search_fuzzy(
            FuzzyQuery(q=query, type=RETURN_TYPE.SUBJECT, limit=self.retrieve_k)
        )
        candidates: dict[str, ClassCandidate] = {}
        for result in results.results:
            if (
                result.subject is not None
                and result.subject.subject_id not in candidates
            ):
                candidates[result.subject.subject_id] = ClassCandidate(
                    uri=result.subject.subject_id,
                    label=result.subject.label or result.subject.subject_id,
                    parents=[
                        p
                        for p in self.ontology_manager.get_parents(
                            result.subject.subject_id
                        )
                    ],
                )
        return list(candidates.values())

    @tool(strict=False)
    def search_links(
        self,
        query: str,
        class_uri: str | None = None,
        subject_id: str | None = None,
        side: Literal["source", "target"] | None = None,
        include_thing: bool = False,
    ) -> list[LinkCandidate]:
        """Search the ontology for properties (links) connecting a class to other classes. The side determines whether the class is the domain (source) or range (target) of the property.

        Args:
            query: how the user wants to connect the subjects, e.g. "homeport" or "commander".
            class_uri: URI of the class the link attaches to, e.g. "<http://dbpedia.org/ontology/Ship>".
            subject_id: ID of the subject to filter links by, if specified.
            include_thing: whether to include links to/from owl:Thing, which is the superclass of all classes. Useful for finding links to classes that are not shown as direct subclasses.
            side: "source" for links going out of the class, "target" for links pointing to it. If None, both sides are searched and the results are merged.

        Returns:
            Matching links with their domain (from_*) and range (to_*), e.g.
            [{"uri": "<http://dbpedia.org/ontology/homeport>", "label": "homeport",
              "from_uri": "<http://dbpedia.org/ontology/Ship>", "to_uri": "<http://dbpedia.org/ontology/Port>"}, ...].
            Use their uri with add_link.
        """
        if subject_id is not None:
            subject = self.graph.get_subject_by_id(subject_id)
            if subject is None:
                raise ToolError(
                    f"Subject {subject_id} is not in the query graph, existing subjects: "
                    f"{[s.id for s in self.graph.subjects]}"
                )
            class_uri = subject.uri
        if class_uri is None:
            raise ToolError(
                "search_links needs either a class_uri (as returned by search_classes) or a subject_id to filter links by."
            )
        results: list[FuzzyQueryResult] = []
        if side is None:
            result_sides = [
                self.guidance.search_fuzzy(
                    FuzzyQuery(
                        q=query,
                        type=RETURN_TYPE.LINK,
                        from_id=class_uri if side == "source" else None,
                        to_id=class_uri if side == "target" else None,
                        limit=self.retrieve_k,
                        include_thing=include_thing,
                    )
                ).results
                for side in ["source", "target"]
            ]
            results = [r for side_results in result_sides for r in side_results]
        else:
            results = self.guidance.search_fuzzy(
                FuzzyQuery(
                    q=query,
                    type=RETURN_TYPE.LINK,
                    from_id=class_uri if side == "source" else None,
                    to_id=class_uri if side == "target" else None,
                    limit=self.retrieve_k,
                    include_thing=include_thing,
                )
            ).results
        candidates: dict[str, LinkCandidate] = {}
        for result in results:
            link = result.link
            if (
                link is None
                or link.property_id is None
                or link.property_id in candidates
            ):
                continue
            self._known_links[wrap_iri(link.property_id)] = link
            candidates[link.property_id] = LinkCandidate(
                uri=link.property_id,
                label=link.label or link.property_id,
                from_uri=link.from_id,
                from_label=link.from_subject.label if link.from_subject else None,
                to_uri=link.to_id,
                to_label=link.to_subject.label if link.to_subject else None,
            )
        return list(candidates.values())

    @tool(strict=False)
    def search_links_generic(
        self,
        query: str,
        side: Literal["source", "target"] | None = None,
    ) -> list[LinkCandidate]:
        """Search the ontology for properties (links) connecting any class (owl:Thing) to other classes. The side determines whether the class is the domain (source) or range (target) of the property.

        Args:
            query (str): what the user wants to connect the subjects, e.g. "homeport" or "commander".
            side (Literal["source", "target"] | None): The side of the property to search for. If None, both sides are searched. Defaults to None.

        Returns:
            list[LinkCandidate]: Matching links with their domain (from_*) and range (to_*) matching to general classes (owl:Thing)
        """
        return self.search_links_generic(
            query=query,
            class_uri="owl:Thing",
            side=side,
            include_thing=True,
        )

    @tool()
    def add_subject(self, uri: str) -> AssistantSubject:
        """Add a class as a new subject (node) to the query graph.

        Args:
            uri: URI of the class, as returned by search_classes.

        Returns:
            The added subject; reference it by its "id" in add_link and remove_subject.
        """
        # same data as GET /classes/subjects, which the editor loads for new nodes
        subject: Subject | None = self.ontology_manager.enrich_subject(uri)
        # unknown URIs enrich to a subject without any statements
        if subject is None or not subject.spos:
            raise ToolError(
                f"Class {uri} does not exist, search it with search_classes."
            )
        added = AssistantSubject.from_subject(subject, id="")
        self.graph.add_subject(added)
        self.details.subjects[added.id] = subject
        return added

    @tool()
    def add_link(self, from_id: str, to_id: str, uri: str) -> AssistantLink:
        """Connect two subjects of the query graph with a link (property).

        Args:
            from_id: id of the source subject in the query graph (not its URI).
            to_id: id of the target subject in the query graph (not its URI).
            uri: URI of the property, as returned by search_links.

        Returns:
            The added link; reference it by its "id" in remove_link.
        """
        self._subject(from_id)
        self._subject(to_id)
        link = self._known_links.get(wrap_iri(uri))
        if link is None:
            prop = self.ontology_manager.enrich_subject(uri)
            if prop is None or "rdfs:domain" not in prop.spos:
                raise ToolError(
                    f"Property {uri} does not exist, search it with search_links."
                )
            link = prop.to_link()
            # to_link counts the instances of the property as a class (0)
            link.instance_count = self._link_count(uri)
        added = AssistantLink.from_link(
            graph=self.graph,
            link=link,
            from_subject_id=from_id,
            to_subject_id=to_id,
            id="",
        )
        self.graph.add_link(added)
        self.details.links[added.id] = link
        return added

    def _link_count(self, uri: str) -> int:
        """Usage count of a property (its triples), from the stored schema if it has
        the property, else counted on the endpoint; 0 if neither works."""
        try:
            stored = self.guidance.schema_index().link(uri)
            if stored is not None:
                return stored.instance_count
        except Exception:
            pass
        try:
            return int(self.ontology_manager.property_count(uri))
        except Exception:
            return 0

    @tool()
    def remove_subject(self, subject_id: str) -> dict:
        """Remove a subject and all links attached to it from the query graph.

        Args:
            subject_id: id of the subject in the query graph.
        """
        self._subject(subject_id)
        self.graph.remove_subject(subject_id)
        self.prune_details()
        return {"success": f"Subject {subject_id} removed from the query graph."}

    @tool()
    def remove_link(self, link_id: str) -> dict:
        """Remove a link from the query graph.

        Args:
            link_id: id of the link in the query graph.
        """
        if not self.graph.has_link(link_id):
            raise ToolError(
                f"Link {link_id} is not in the query graph, existing links: "
                f"{[l.id for l in self.graph.links]}"
            )
        self.graph.remove_link(link_id)
        self.prune_details()
        return {"success": f"Link {link_id} removed from the query graph."}

    @tool()
    def get_query_graph(self) -> QueryGraph:
        """Get the current query graph: its subjects (nodes) and the links between them."""
        return self.graph

    # --- constraints (subqueries), optional ---

    def _key(self, uri: str) -> str:
        """Full IRI (without <>) of an IRI, wrapped IRI or prefixed name."""
        uri = uri.strip()
        if uri.startswith("<") and uri.endswith(">"):
            return uri[1:-1]
        prefix, _, local = uri.partition(":")
        namespaces = self._namespaces()
        if prefix in namespaces and "://" not in uri:
            return namespaces[prefix] + local
        return uri

    def _namespaces(self) -> dict[str, str]:
        """Prefixes of the ontology and of the stored schema (looked up once)."""
        if self._prefixes is None:
            prefixes = dict(self.ontology_manager.namespaces())
            try:
                prefixes = {**self.guidance.schema_index().namespaces, **prefixes}
            except Exception:
                pass
            self._prefixes = prefixes
        return self._prefixes

    def _typed_subject(self, subject_id: str) -> AssistantSubject:
        subject = self._subject(subject_id)
        if not subject.uri:
            raise ToolError(
                f"Subject {subject_id} has no class, so it has no known properties or instances."
            )
        return subject

    @staticmethod
    def _label_property() -> PropertyCandidate:
        return PropertyCandidate(
            uri=RDFS_LABEL, label="label (name)", value_type="string", range="xsd:string"
        )

    def _candidate(self, uri: str, label: str | None, range_uri: str | None) -> PropertyCandidate | None:
        """The property as a candidate, None if its range has no comparable values."""
        if not range_uri:
            return None
        kind = literal_value_kind(self._key(range_uri))
        if kind is None:
            return None
        return PropertyCandidate(
            uri=wrap_iri(self._key(uri)),
            label=label or uri,
            value_type=kind,
            range=range_uri,
        )

    def _schema_properties(self, cls: str) -> list[PropertyCandidate]:
        """Datatype properties of ``cls`` (and its parents, owl:Thing last) in the
        stored schema; raises if there is no stored schema."""
        schema = self.guidance.schema_index()
        candidates: dict[str, PropertyCandidate] = {}
        # properties without a domain (stored for owl:Thing) apply to every class
        for link in schema.links_of(cls) + schema.links_of(OWL_THING):
            if link.to_id is not None:
                continue
            candidate = self._candidate(schema.key(link.property_id), link.label, link.range)
            if candidate is not None:
                candidates.setdefault(candidate.uri, candidate)
        return list(candidates.values())

    def _ontology_property(self, cls: str, uri: str) -> PropertyCandidate | None:
        """The datatype property from the ontology, if its domain fits ``cls``."""
        prop = self.ontology_manager.enrich_subject(uri)
        if prop is None or "rdfs:range" not in prop.spos:
            return None
        ranges = [str(v.value) for v in prop.spos["rdfs:range"].values]
        domains = [
            self._key(str(v.value))
            for v in (prop.spos["rdfs:domain"].values if "rdfs:domain" in prop.spos else [])
        ]
        classes = {self._key(c) for c in self.ontology_manager.get_parents(cls) + [cls]}
        if domains and not any(d in classes or d == OWL_THING for d in domains):
            return None
        label = prop.label if prop.label and prop.label != prop.subject_id else None
        for range_uri in ranges:
            candidate = self._candidate(uri, label, range_uri)
            if candidate is not None:
                return candidate
        return None

    def _property_for(self, subject: AssistantSubject, uri: str) -> PropertyCandidate | None:
        """The datatype property ``uri`` if the subject's class has it: from the stored
        schema, the search results, or the ontology."""
        key = self._key(uri)
        if key == self._key(RDFS_LABEL):
            return self._label_property()
        try:
            for candidate in self._schema_properties(subject.uri):
                if self._key(candidate.uri) == key:
                    return candidate
        except Exception:
            pass
        known = self._known_properties.get((self._key(subject.uri), key))
        if known is not None:
            return known
        try:
            return self._ontology_property(subject.uri, uri)
        except Exception:
            return None

    def _new_subquery_id(self, label: str) -> str:
        taken = {s.id for s in self.graph.subjects} | {l.id for l in self.graph.links}
        taken |= {
            str(sq.id) for s in self.graph.subjects for sq in s.subqueries if sq.id is not None
        }
        base, i = slug(label), 1
        while f"{base}_{i}" in taken:
            i += 1
        return f"{base}_{i}"

    @tool(strict=False, group=CONSTRAINT_TOOLS)
    def search_properties(self, subject_id: str, query: str | None = None) -> list[PropertyCandidate]:
        """Search the datatype properties (literal values like numbers, dates, texts, booleans) of a subject that it can be constrained on with add_constraint.

        Args:
            subject_id: id of the subject in the query graph.
            query: what the user wants to constrain, e.g. "length" or "launch date". Without a query, the subject's most specific properties are listed.

        Returns:
            Matching properties with how their values are compared, e.g.
            [{"uri": "<http://dbpedia.org/ontology/length>", "label": "length", "value_type": "number", "range": "xsd:double"}, ...].
            The label (name) of the subject's instances is always available as {"uri": "rdfs:label", "value_type": "string"}.
        """
        subject = self._typed_subject(subject_id)
        cls = self._key(subject.uri)
        if query:
            results = self.guidance.search_fuzzy(
                FuzzyQuery(
                    q=query,
                    type=RETURN_TYPE.LINK,
                    relation_type=RELATION_TYPE.PROPERTY,
                    from_id=subject.uri,
                    include_thing=True,
                    limit=self.retrieve_k,
                )
            ).results
            candidates: dict[str, PropertyCandidate] = {}
            for result in results:
                link = result.link
                if link is None or link.property_id is None or link.to_id is not None:
                    continue
                candidate = self._candidate(link.property_id, link.label, link.to_proptype)
                if candidate is not None:
                    candidates.setdefault(candidate.uri, candidate)
            found = list(candidates.values())
        else:
            try:
                found = [self._label_property()] + self._schema_properties(subject.uri)[
                    : self.retrieve_k * 4
                ]
            except Exception:
                raise ToolError(
                    "The properties of the subject cannot be listed, search them with a query."
                )
        for candidate in found:
            self._known_properties[(cls, self._key(candidate.uri))] = candidate
        return found

    def _parse_value(self, prop: PropertyCandidate, operator: str, value: str) -> AnyAssistantSubQuery:
        base = dict(
            property_id=prop.uri, property_label=prop.label, property_type=prop.range
        )
        text = str(value).strip()
        if prop.value_type == "number":
            try:
                number = float(text.replace(" ", "").replace("_", ""))
            except ValueError:
                number = float("nan")
            if number != number or number in (float("inf"), float("-inf")):
                raise ToolError(
                    f"Value {value!r} is not a number, but {prop.label} ({prop.range}) has numeric values; pass e.g. \"120\" or \"27.5\"."
                )
            return NumberSubQuery(value=number, operator=AssistantNumberConstraintType(operator), **base)
        if prop.value_type == "date":
            date = text
            if re.fullmatch(r"\d{4}", date):
                date = f"{date}-01-01"
            elif re.fullmatch(r"\d{4}-\d{2}", date):
                date = f"{date}-01"
            try:
                datetime.fromisoformat(date.replace("Z", "+00:00"))
            except ValueError:
                raise ToolError(
                    f"Value {value!r} is not a date, but {prop.label} ({prop.range}) has date values; pass an ISO 8601 date like \"1805-10-21\" (or a year like \"1805\")."
                )
            return DateSubQuery(value=date, operator=AssistantNumberConstraintType(operator), **base)
        if prop.value_type == "boolean":
            lowered = text.lower()
            if lowered not in TRUE_VALUES | FALSE_VALUES:
                raise ToolError(
                    f"Value {value!r} is not a boolean, but {prop.label} has boolean values; pass \"true\" or \"false\"."
                )
            flag = lowered in TRUE_VALUES
            return BooleanSubQuery(value=flag if operator == "equals" else not flag, **base)
        if not text:
            raise ToolError(f"Pass a non-empty text value to constrain {prop.label}.")
        if operator == "regex":
            try:
                re.compile(text)
            except re.error as e:
                raise ToolError(f"Value {value!r} is no valid regular expression: {e}.")
        return StringSubQuery(value=text, operator=AssistantStringConstraintType(operator), **base)

    @tool(group=CONSTRAINT_TOOLS)
    def add_constraint(
        self, subject_id: str, property_uri: str, operator: ConstraintOperator, value: str
    ) -> AnyAssistantSubQuery:
        """Constrain a subject by the value of one of its datatype properties, e.g. ships with a length greater than 100.

        Args:
            subject_id: id of the subject in the query graph.
            property_uri: URI of the property, as returned by search_properties (or "rdfs:label" for the name).
            operator: comparison; numbers and dates: "equals", "less", "greater"; texts: "equals", "!=", "contains", "startswith", "endswith", "regex"; booleans: "equals", "!=".
            value: the value to compare with, as text: a number ("100"), an ISO date ("1805-10-21" or a year "1805"), a text, or "true"/"false".

        Returns:
            The added constraint; reference it by its "id" in remove_constraint.
        """
        subject = self._typed_subject(subject_id)
        prop = self._property_for(subject, property_uri)
        if prop is None:
            raise ToolError(
                f"{property_uri} is no datatype property of {subject.label} ({subject.uri}); "
                f"find one with search_properties(subject_id={subject_id!r}). "
                "Use add_link to connect the subject to another subject, or restrict_to_instance for a specific instance."
            )
        normalized = OPERATOR_ALIASES.get(str(operator).strip().lower(), str(operator).strip().lower())
        allowed = OPERATORS_OF[prop.value_type]
        if normalized not in allowed:
            raise ToolError(
                f"Operator {operator!r} does not apply to {prop.label}, which has {prop.value_type} values; use one of {allowed}."
            )
        subquery = self._parse_value(prop, normalized, value)
        for existing in subject.subqueries:
            if existing.model_dump(exclude={"id"}) == subquery.model_dump(exclude={"id"}):
                raise ToolError(
                    f"Subject {subject_id} already has this constraint (id {existing.id})."
                )
        subquery.id = self._new_subquery_id(prop.label)
        subject.subqueries.append(subquery)
        return subquery

    @tool(group=CONSTRAINT_TOOLS)
    def restrict_to_instance(self, subject_id: str, instance: str) -> SubjectSubQuery:
        """Restrict a subject to one specific instance (entity) of its class, e.g. the ship "HMS Victory".

        Args:
            subject_id: id of the subject in the query graph.
            instance: the name of the instance (its label or a part of it), or the uri of a candidate listed by an earlier call.

        Returns:
            The added restriction; reference it by its "id" in remove_constraint.
            If several instances match, nothing is added and the candidates are listed in the error.
        """
        subject = self._typed_subject(subject_id)
        for existing in subject.subqueries:
            if isinstance(existing, SubjectSubQuery) and existing.instance_id:
                raise ToolError(
                    f"Subject {subject_id} is already restricted to {existing.instance_label or existing.instance_id} "
                    f"(constraint id {existing.id}); remove that constraint first."
                )
        cls = self._key(subject.uri)
        chosen = self._known_instances.get((cls, self._key(instance)))
        if chosen is None:
            # the name is a string literal in the instance query
            name = re.sub(r'["\\]', "", instance).strip()
            if not name:
                raise ToolError("Pass the name of the instance to look for.")
            found = [
                InstanceCandidate(uri=i.id, label=i.label)
                for i in self.ontology_manager.get_instances(
                    InstanceQuery(cls=subject.uri, q=name, limit=self.retrieve_k + 1)
                )
            ]
            for candidate in found:
                self._known_instances[(cls, self._key(candidate.uri))] = candidate
            exact = [c for c in found if c.label.lower() == name.lower()]
            if len(exact) == 1:
                chosen = exact[0]
            elif len(found) == 1:
                chosen = found[0]
            elif not found:
                raise ToolError(
                    f"No instance of {subject.label} ({subject.uri}) has a label containing {name!r}; try another or a shorter name."
                )
            else:
                listed = [c.model_dump() for c in found[: self.retrieve_k]]
                raise ToolError(
                    f"Several instances of {subject.label} match {name!r}: {listed}; "
                    "call restrict_to_instance again with the uri of the intended one."
                )
        subquery = SubjectSubQuery(
            id=self._new_subquery_id(chosen.label),
            instance_id=chosen.uri,
            instance_label=chosen.label,
            property_type="owl:Thing",
        )
        subject.subqueries.append(subquery)
        return subquery

    @tool(group=CONSTRAINT_TOOLS)
    def remove_constraint(self, subject_id: str, constraint_id: str) -> dict:
        """Remove a constraint (or instance restriction) from a subject.

        Args:
            subject_id: id of the subject in the query graph.
            constraint_id: id of the constraint, as returned by add_constraint or listed in the subject's "subqueries".
        """
        subject = self._subject(subject_id)
        ids = [str(sq.id) for sq in subject.subqueries]
        if str(constraint_id) not in ids:
            raise ToolError(
                f"Subject {subject_id} has no constraint {constraint_id}, its constraints: {ids}"
            )
        subject.subqueries = [sq for sq in subject.subqueries if str(sq.id) != str(constraint_id)]
        return {"success": f"Constraint {constraint_id} removed from subject {subject_id}."}
