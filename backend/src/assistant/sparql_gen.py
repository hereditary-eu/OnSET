"""SPARQL generation from the backend QueryGraph (assistant_model.QueryGraph).

Mirrors the editor's generator (NodeLinkRepository.generateQuery/querySet in
frontend/src/utils/sparql/store.ts, representation/{graph,subqueries}.ts):

- every subject is ``?<id> a <uri>``, its label an OPTIONAL rdfs:label/foaf:name
  ``?lbl_<id>`` (restricted to ``language`` and untagged literals)
- a structural link is ``?from <uri>[quantifier] ?to``, an arbitrary one (or one
  without uri) ``?from ?p_<id> ?to`` with ``?p_<id>`` an output variable
- query/image/instance props are ``?subject <prop> ?sq_<id>`` output variables,
  string/number/boolean/date subqueries add a FILTER on such a variable,
  a subject subquery fixes the subject to its instance (VALUES)
- vector sorts BIND a dtf: distance to their vector and ORDER BY it, similarity
  links join the nearest neighbour through QLever's tensorIndex SERVICE

Deliberate differences to the editor (known bugs there):
- quantifiers follow the enum (ZERO_OR_MORE is ``*``, ONE_OR_MORE ``+``), the
  editor's LinkQuantifier.toString swaps them
- similarity links use the link's embedding property on both sides and bind the
  neighbour to the to subject (the editor's template has ``??node_2_emb`` and a
  hardcoded payload), vector sorts without a vector are left out (the editor
  emits an invalid BIND)
- literals are escaped, string filters compare STR() (so language-tagged
  labels match; the editor only for (in)equality), labels are filtered by
  language, numbers without a property type are plain numeric literals (the
  editor emits ``^^null``)
- several vector sorts form one ORDER BY (the editor emits one clause each)
- dates of xsd:date properties (property_type) compare with xsd:date literals,
  the editor compares every date with an xsd:dateTime

Beyond the editor: count mode counts the solutions (or a subject's bindings), and
with ``group_by`` the counts per value of a subject or query prop (the value
distributions of progressive discovery, assistant/progressive/sampler.py); ``projection``
and ``order_by`` select/sort by graph ids.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from eval_config import MultimodalConfig

from assistant.assistant_model import (
    AssistantLink,
    AssistantNumberConstraintType,
    AssistantStringConstraintType,
    AssistantSubject,
    AssistantSubQueryType,
    BooleanSubQuery,
    DateSubQuery,
    LinkQuantifier,
    LinkQuantifierType,
    LinkSemanticType,
    NumberSubQuery,
    QueryGraph,
    StringSubQuery,
    SubjectSubQuery,
    VectorSortDirection,
    VectorSortDistance,
    VectorSortSubQuery,
)

if TYPE_CHECKING:
    from ontology import OntologyManager


TENSOR_INDEX_NS = "https://qlever.cs.uni-freiburg.de/tensorIndex/"
TENSOR_FUNCTIONS_NS = "https://w3id.org/rdf-tensor/functions#"
TENSOR_DATATYPE = "<https://w3id.org/rdf-tensor/datatypes#NumericDataTensor>"

# prefixes the generator itself uses (labels, literal types, tensor functions)
DEFAULT_NAMESPACES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dtf": TENSOR_FUNCTIONS_NS,
    "tensorIndex": TENSOR_INDEX_NS,
}
LABEL_PROPERTIES = ["rdfs:label", "foaf:name"]
INTEGER_TYPES = {
    "integer", "int", "long", "short", "byte", "nonNegativeInteger", "positiveInteger",
    "nonPositiveInteger", "negativeInteger", "unsignedInt", "unsignedLong", "unsignedShort",
    "unsignedByte", "gYear",
}
DISTANCE_FUNCTIONS = {
    VectorSortDistance.COSINE: "dtf:cosineSimilarity",
    VectorSortDistance.EUCLIDEAN: "dtf:euclideanDistance",
    VectorSortDistance.MANHATTAN: "dtf:manhattanDistance",
}
# query props (output variables)
PROP_TYPES = {
    AssistantSubQueryType.QUERY_PROP,
    AssistantSubQueryType.IMAGE_PROP,
    AssistantSubQueryType.INSTANCE_PROP,
}

PREFIXED_NAME = re.compile(r"^([A-Za-z][A-Za-z0-9_\-.]*)?:(.*)$")
# simplified PN_LOCAL (no escapes or percent encoding)
LOCAL_NAME = re.compile(r"^([A-Za-z0-9_:]([A-Za-z0-9_\-.:]*[A-Za-z0-9_\-:])?)?$")


class SparqlGenerationError(ValueError):
    pass


class SparqlOptions(BaseModel):
    # "select" returns the bindings, "count" a single ?count of the (distinct) solutions
    mode: Literal["select", "count"] = "select"
    # select: LIMIT/OFFSET of the result; count: of the counted inner query, so a
    # limit caps the count (counting stops at `limit` solutions)
    limit: int | None = None
    offset: int | None = None
    distinct: bool = True
    # labels (?lbl_<id>) of the subjects, None: in select mode only (they are
    # OPTIONAL, so they do not restrict the solutions but are costly to join)
    labels: bool | None = None
    # language of the labels (untagged labels are kept as well), None for any
    language: str | None = "en"
    # select mode: ORDER BY the vector sorts, else the labels/output variables
    # (like the editor), which makes paging stable but costs a sort
    order: bool = True
    # count mode: count the distinct bindings of this subject instead of the
    # distinct solutions of all output variables
    count_subject: str | None = None
    count_var: str = "count"
    # graph ids (subject ids, query prop subquery ids) of the projected (select) or
    # counted (count, without count_subject) variables, None for all outputs
    projection: list[str] | None = None
    # select mode: ORDER BY these graph ids (ascending) instead of the default order
    order_by: list[str] | None = None
    # count mode: one count per value of this graph id (a subject or query prop),
    # ``SELECT ?value (COUNT(...) AS ?count) ... GROUP BY ?value``; limit/offset then
    # apply to the groups, which are ordered by value (ascending) or count (descending)
    group_by: str | None = None
    group_order: Literal["value", "count"] = "value"
    # group_by a query prop: keep only values in this language (and untagged ones)
    group_language: str | None = None
    # BETWEEN/EXACTLY quantifiers: "native" emits {n,m} (QLever, not SPARQL 1.1),
    # "expand" spells them out as sequences/alternatives of the property
    path_ranges: Literal["native", "expand"] = "native"
    # prefix -> namespace of the prefixed names in the graph (e.g. the
    # OntologyManager's namespaces()), merged into DEFAULT_NAMESPACES
    namespaces: dict[str, str] = Field(default_factory=dict)
    # emit PREFIX declarations of the used prefixes (off if the runner adds them)
    prefixes: bool = True
    # image types/properties and embedding properties of the configuration
    multimodal: MultimodalConfig | None = None

    @staticmethod
    def from_ontology(ontology_manager: "OntologyManager", **options) -> "SparqlOptions":
        """Options with the namespaces, language and multimodal config of a configuration."""
        config = ontology_manager.config
        defaults = dict(
            namespaces={str(k): str(v) for k, v in ontology_manager.namespaces().items()},
            language=config.language,
            multimodal=config.multimodal_config,
        )
        return SparqlOptions(**{**defaults, **options})


OutputKind = Literal["subject", "label", "property", "image", "similarity", "link", "distance", "count"]
# rank of the kinds in the projection (query props of either kind in their order)
OUTPUT_RANK = {"subject": 0, "label": 1, "property": 2, "image": 2, "similarity": 3, "link": 4, "distance": 5, "count": 6}


@dataclass
class SparqlOutput:
    """A projected variable (without ``?``) and the graph element it belongs to."""

    var: str
    kind: OutputKind
    subject_id: str | None = None
    # subquery id (or "<subject id>_<index>") / link id
    element_id: str | None = None
    property_id: str | None = None


@dataclass
class GeneratedSparql:
    query: str
    outputs: list[SparqlOutput] = field(default_factory=list)
    # parts of the graph that could not be expressed and were left out
    warnings: list[str] = field(default_factory=list)
    # prefixes used in the query without a known namespace
    undeclared_prefixes: list[str] = field(default_factory=list)

    @property
    def variables(self) -> list[str]:
        return [o.var for o in self.outputs]

    def var_of(self, kind: OutputKind, element_id: str) -> str | None:
        """Variable of a subject (kind subject/label: its id) or subquery/link."""
        for output in self.outputs:
            key = output.subject_id if kind in ("subject", "label") else output.element_id
            if output.kind == kind and key == element_id:
                return output.var
        return None

    def __str__(self) -> str:
        return self.query


def escape_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def format_date(value: str) -> str:
    """ISO 8601 date(time) as the editor's Date.toISOString() (UTC, milliseconds)."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise SparqlGenerationError(f"invalid date {value!r}") from e
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"


class _VarNames:
    """Valid, unique SPARQL variable names for graph ids."""

    def __init__(self):
        self.used: set[str] = set()
        self.names: dict[tuple[str, str], str] = {}

    def get(self, prefix: str, key: str) -> str:
        if (prefix, key) in self.names:
            return self.names[(prefix, key)]
        base = prefix + re.sub(r"[^A-Za-z0-9_]", "_", key)
        name, i = base, 2
        while name in self.used:
            name, i = f"{base}_{i}", i + 1
        self.used.add(name)
        self.names[(prefix, key)] = name
        return name


class SparqlGenerator:
    def __init__(self, graph: QueryGraph, options: SparqlOptions | None = None):
        self.graph = graph
        self.options = options or SparqlOptions()
        self.namespaces = {**DEFAULT_NAMESPACES, **self.options.namespaces}
        self.vars = _VarNames()
        self.used_prefixes: list[str] = []
        self.undeclared: list[str] = []
        self.warnings: list[str] = []
        multimodal = self.options.multimodal
        self.image_types = {self.expand(t) for t in (multimodal.image_types if multimodal else [])}
        self.image_properties = {self.expand(p) for p in (multimodal.image_properties if multimodal else [])}

    # --- terms ---

    def expand(self, term: str) -> str:
        """Full IRI (without <>) of a term, for comparisons."""
        term = term.strip()
        if term.startswith("<") and term.endswith(">"):
            return term[1:-1]
        match = PREFIXED_NAME.match(term)
        if match and "://" not in term and (match.group(1) or "") in self.namespaces:
            return self.namespaces[match.group(1) or ""] + match.group(2)
        return term

    def use_prefix(self, prefix: str):
        if prefix not in self.used_prefixes:
            self.used_prefixes.append(prefix)
            if prefix not in self.namespaces and prefix not in self.undeclared:
                self.undeclared.append(prefix)

    def iri(self, term: str | None, what: str = "term") -> str:
        """A graph term (n3 IRI, prefixed name or plain IRI) as SPARQL IRI."""
        if term is None or term.strip() == "":
            raise SparqlGenerationError(f"missing IRI of {what}")
        term = term.strip()
        if term.startswith("<") and term.endswith(">"):
            return term
        match = PREFIXED_NAME.match(term)
        if match is None or "://" in term:
            return f"<{term}>"
        prefix = match.group(1) or ""
        if not LOCAL_NAME.match(match.group(2)):
            # e.g. dbr:Foo_(bar), not a valid prefixed name
            if prefix in self.namespaces:
                return f"<{self.namespaces[prefix]}{match.group(2)}>"
        self.use_prefix(prefix)
        return term

    def is_image(self, subquery) -> bool:
        if subquery.type == AssistantSubQueryType.IMAGE_PROP:
            return True
        if subquery.property_type and self.expand(subquery.property_type) in self.image_types:
            return True
        return bool(subquery.property_id) and self.expand(subquery.property_id) in self.image_properties

    def path(self, link: AssistantLink) -> str:
        prop = self.iri(link.uri, f"link {link.id}")
        quantifier = link.quantifier
        if quantifier is None:
            return prop
        if quantifier.type in (
            LinkQuantifierType.ONE_OR_MORE,
            LinkQuantifierType.ZERO_OR_MORE,
            LinkQuantifierType.ZERO_OR_ONE,
        ):
            return prop + quantifier.type.value
        low, high = self.bounds(link, quantifier)
        if self.options.path_ranges == "native":
            if low == high:
                return f"{prop}{{{low}}}"
            return f"{prop}{{{low},{'' if high is None else high}}}"
        return self.expanded_path(prop, low, high)

    def bounds(self, link: AssistantLink, quantifier: LinkQuantifier) -> tuple[int, int | None]:
        if quantifier.type == LinkQuantifierType.EXACTLY:
            if quantifier.min is None:
                raise SparqlGenerationError(f"EXACTLY quantifier of link {link.id} without min")
            low, high = quantifier.min, quantifier.min
        else:
            low = quantifier.min or 0
            high = quantifier.max
        if low < 0 or (high is not None and high < low) or high == 0:
            raise SparqlGenerationError(f"invalid quantifier bounds {low}..{high} of link {link.id}")
        return low, high

    @staticmethod
    def expanded_path(prop: str, low: int, high: int | None) -> str:
        """prop{low,high} with SPARQL 1.1 paths only."""

        def seq(n: int) -> str:
            return "/".join([prop] * n)

        if high is None:
            # at least `low` steps
            return f"{seq(low)}/{prop}*" if low > 0 else f"{prop}*"
        alternatives = [seq(n) for n in range(max(low, 1), high + 1)]
        expanded = alternatives[0] if len(alternatives) == 1 else "(" + "|".join(alternatives) + ")"
        if low == 0:
            expanded = f"({expanded})?" if len(alternatives) == 1 else f"{expanded}?"
        return expanded

    # --- graph ---

    def subject_var(self, subject: AssistantSubject, index: int) -> str:
        return self.vars.get("", subject.id if subject.id else f"s{index}")

    def generate(self) -> GeneratedSparql:
        options = self.options
        count = options.mode == "count"
        labels = options.labels if options.labels is not None else not count
        if not self.graph.subjects:
            raise SparqlGenerationError("the query graph has no subjects")

        # variables first, so they do not depend on the pattern order
        subject_vars = {}
        for i, subject in enumerate(self.graph.subjects):
            subject_vars[subject.id] = self.subject_var(subject, i)

        patterns: list[str] = []
        values: list[str] = []
        outputs: list[SparqlOutput] = [
            SparqlOutput(var=var, kind="subject", subject_id=sid) for sid, var in subject_vars.items()
        ]
        order: list[str] = []

        for link in self.graph.links:
            if link.from_subject_id not in subject_vars or link.to_subject_id not in subject_vars:
                raise SparqlGenerationError(f"link {link.id} references a subject that is not in the graph")
            source = subject_vars[link.from_subject_id]
            target = subject_vars[link.to_subject_id]
            if link.semantic_link_type == LinkSemanticType.SIMILARITY:
                patterns.extend(self.similarity_link(link, source, target, outputs))
            elif link.allow_arbitrary or not link.uri:
                var = self.vars.get("p_", link.id or f"{source}_{target}")
                if link.quantifier is not None:
                    self.warnings.append(f"quantifier of arbitrary link {link.id} dropped (variables have no paths)")
                patterns.append(f"?{source} ?{var} ?{target} .")
                outputs.append(SparqlOutput(var=var, kind="link", element_id=link.id))
            else:
                patterns.append(f"?{source} {self.path(link)} ?{target} .")

        for i, subject in enumerate(self.graph.subjects):
            var = subject_vars[subject.id]
            if subject.uri:
                patterns.append(f"?{var} a {self.iri(subject.uri, f'subject {subject.id}')} .")
            if labels:
                label_var = self.vars.get("lbl_", var)
                outputs.append(SparqlOutput(var=label_var, kind="label", subject_id=subject.id))
                patterns.extend(self.label_patterns(var, label_var))
            for j, subquery in enumerate(subject.subqueries):
                key = subquery.id if subquery.id not in (None, "") else f"{var}_{j}"
                patterns.extend(self.subquery(subject, var, key, subquery, outputs, values, order, count))

        # projection like the editor's: subjects, labels, subquery variables, links
        outputs.sort(key=lambda o: OUTPUT_RANK[o.kind])
        return self.assemble(patterns, values, outputs, order, labels)

    def label_patterns(self, var: str, label_var: str) -> list[str]:
        language = self.options.language
        lang_filter = ""
        if language:
            lang_filter = f' FILTER(LANG(?{label_var}) = {escape_literal(language)} || LANG(?{label_var}) = "")'
        # the second OPTIONAL only binds the label if the first did not
        return [
            f"OPTIONAL {{ ?{var} {self.iri(prop)} ?{label_var} .{lang_filter} }}" for prop in LABEL_PROPERTIES
        ]

    def subquery(self, subject, var, key, subquery, outputs, values, order, count) -> list[str]:
        if isinstance(subquery, SubjectSubQuery):
            if subquery.instance_id:
                values.append(f"VALUES ?{var} {{ {self.iri(subquery.instance_id, f'instance of {key}')} }}")
            return []
        if isinstance(subquery, VectorSortSubQuery):
            return self.vector_sort(subject, var, key, subquery, outputs, order, count)

        prop_var = self.vars.get("sq_", key)
        prop = self.iri(subquery.property_id, f"subquery {key}")
        triple = f"?{var} {prop} ?{prop_var} ."
        if subquery.type in PROP_TYPES:
            kind = "image" if self.is_image(subquery) else "property"
            outputs.append(
                SparqlOutput(var=prop_var, kind=kind, subject_id=subject.id, element_id=key, property_id=subquery.property_id)
            )
            return [triple]
        return [triple, f"FILTER({self.filter_expression(subquery, f'?{prop_var}')})"]

    def filter_expression(self, subquery, var: str) -> str:
        if isinstance(subquery, StringSubQuery):
            value = escape_literal(subquery.value)
            match subquery.operator:
                case AssistantStringConstraintType.EQUALS:
                    return f"STR({var}) = {value}"
                case AssistantStringConstraintType.NEQUALS:
                    return f"STR({var}) != {value}"
                case AssistantStringConstraintType.CONTAINS:
                    return f"CONTAINS(STR({var}), {value})"
                case AssistantStringConstraintType.STARTSWITH:
                    return f"STRSTARTS(STR({var}), {value})"
                case AssistantStringConstraintType.ENDSWITH:
                    return f"STRENDS(STR({var}), {value})"
                case AssistantStringConstraintType.REGEX:
                    return f"REGEX(STR({var}), {value})"
        if isinstance(subquery, NumberSubQuery):
            return f"{var} {self.comparison(subquery.operator)} {self.number_literal(subquery)}"
        if isinstance(subquery, BooleanSubQuery):
            return f"{var} = {'true' if subquery.value else 'false'}"
        if isinstance(subquery, DateSubQuery):
            literal = f"{escape_literal(format_date(subquery.value))}^^{self.iri('xsd:dateTime')}"
            if subquery.property_type and self.expand(subquery.property_type) == DEFAULT_NAMESPACES["xsd"] + "date":
                # xsd:date values compare with dates only (SPARQL 1.1, rdflib)
                literal = f"{escape_literal(format_date(subquery.value)[:10])}^^{self.iri('xsd:date')}"
            return f"{var} {self.comparison(subquery.operator)} {literal}"
        raise SparqlGenerationError(f"unsupported subquery type {subquery.type}")

    @staticmethod
    def comparison(operator: AssistantNumberConstraintType) -> str:
        return {
            AssistantNumberConstraintType.EQUALS: "=",
            AssistantNumberConstraintType.LESS: "<",
            AssistantNumberConstraintType.GREATER: ">",
        }[operator]

    def number_literal(self, subquery: NumberSubQuery) -> str:
        value = format_number(subquery.value)
        if not subquery.property_type:
            return value
        type_iri = self.expand(subquery.property_type)
        xsd = DEFAULT_NAMESPACES["xsd"]
        if type_iri.startswith(xsd) and type_iri[len(xsd):] in INTEGER_TYPES and "." in value:
            # a fraction is no valid integer literal, compare numerically instead
            return value
        return f"{escape_literal(value)}^^{self.iri(subquery.property_type)}"

    def vector_property(self, property_id: str | None) -> str | None:
        if property_id:
            return property_id
        multimodal = self.options.multimodal
        if multimodal and multimodal.image_vector_properties:
            return multimodal.image_vector_properties[0]
        return None

    def vector_sort(self, subject, var, key, subquery: VectorSortSubQuery, outputs, order, count) -> list[str]:
        prop = self.vector_property(subquery.property_id)
        if not subquery.vector or prop is None:
            self.warnings.append(f"vector sort {key} left out (no vector or embedding property)")
            return []
        emb_var = self.vars.get("sq_", key)
        triple = f"?{var} {self.iri(prop)} ?{emb_var} ."
        if count:
            # the sort does not change the solutions, but only subjects with an embedding have a distance
            return [triple]
        sim_var = self.vars.get("sim_", key)
        tensor = json.dumps(
            {"type": "float32", "shape": [len(subquery.vector)], "data": subquery.vector}, separators=(",", ":")
        )
        literal = f"{escape_literal(tensor)}^^{TENSOR_DATATYPE}"
        function = DISTANCE_FUNCTIONS[subquery.distance]
        self.use_prefix("dtf")
        outputs.append(SparqlOutput(var=sim_var, kind="similarity", subject_id=subject.id, element_id=key, property_id=prop))
        direction = "ASC" if subquery.direction == VectorSortDirection.ASCENDING else "DESC"
        order.append(f"{direction}(?{sim_var})")
        return [triple, f"BIND({function}(?{emb_var}, {literal}) AS ?{sim_var})"]

    def similarity_link(self, link: AssistantLink, source: str, target: str, outputs) -> list[str]:
        """Nearest neighbour (QLever tensorIndex) of the source's embedding among the target's."""
        prop_term = self.vector_property(link.uri or None)
        if prop_term is None:
            raise SparqlGenerationError(f"similarity link {link.id} without embedding property")
        prop = self.iri(prop_term, f"link {link.id}")
        key = link.id or f"{source}_{target}"
        left = self.vars.get("emb_", f"{key}_from")
        right = self.vars.get("emb_", f"{key}_to")
        dist = self.vars.get("dist_", key)
        outputs.append(SparqlOutput(var=dist, kind="distance", element_id=link.id, property_id=link.uri))
        target_subject = self.graph.get_subject_by_id(link.to_subject_id)
        right_patterns = f"?{target} {prop} ?{right} ."
        if target_subject is not None and target_subject.uri:
            # restrict the candidates, else the nearest neighbour may be of another class
            right_patterns = f"?{target} a {self.iri(target_subject.uri)} . " + right_patterns
        self.use_prefix("tensorIndex")
        cache_name = escape_literal(f"{target_subject.uri if target_subject else ''}-{prop_term}")
        config = f"_:config_{re.sub(r'[^A-Za-z0-9_]', '_', key)}"
        return [
            f"?{source} {prop} ?{left} .",
            "SERVICE tensorIndex: {",
            f"    {config} tensorIndex:left ?{left} ;",
            f"        tensorIndex:right ?{right} ;",
            f"        tensorIndex:payload ?{target} ;",
            "        tensorIndex:numNN 1 ;",
            "        tensorIndex:searchK 1 ;",
            "        tensorIndex:kIVF 512 ;",
            "        tensorIndex:algorithm tensorIndex:ivf ;",
            "        tensorIndex:distance tensorIndex:dot ;",
            f"        tensorIndex:bindDistance ?{dist} ;",
            f"        tensorIndex:experimentalRightCacheName {cache_name} .",
            f"    {{ {right_patterns} }}",
            "}",
        ]

    # --- query ---

    def prologue(self) -> str:
        if not self.options.prefixes:
            return ""
        lines = [
            f"PREFIX {prefix}: <{self.namespaces[prefix]}>" for prefix in self.used_prefixes if prefix in self.namespaces
        ]
        return "\n".join(lines) + "\n" if lines else ""

    @staticmethod
    def element_var(outputs: list[SparqlOutput], element_id: str) -> str:
        """Variable of a subject id or a query prop's subquery id."""
        for output in outputs:
            if output.kind == "subject" and output.subject_id == element_id:
                return output.var
        for output in outputs:
            if output.kind in ("property", "image") and output.element_id == element_id:
                return output.var
        raise SparqlGenerationError(f"{element_id} is neither a subject nor a query prop of the graph")

    def assemble(self, patterns, values, outputs: list[SparqlOutput], order, labels) -> GeneratedSparql:
        options = self.options
        if options.group_by is not None and options.group_language:
            group_var = self.element_var(outputs, options.group_by)
            language = escape_literal(options.group_language)
            patterns = patterns + [f'FILTER(LANG(?{group_var}) = {language} || LANG(?{group_var}) = "")']
        body = "\n".join("    " + line for line in values + patterns)
        where = f"WHERE {{\n{body}\n}}"
        distinct = "DISTINCT " if options.distinct else ""
        modifiers = []
        if options.limit is not None:
            modifiers.append(f"LIMIT {options.limit}")
        if options.offset:
            modifiers.append(f"OFFSET {options.offset}")

        if options.mode == "count":
            count_var = options.count_var
            if options.count_subject is not None:
                counted = [o.var for o in outputs if o.kind == "subject" and o.subject_id == options.count_subject]
                if not counted:
                    raise SparqlGenerationError(f"count_subject {options.count_subject} not in the graph")
            elif options.projection is not None:
                counted = [self.element_var(outputs, e) for e in options.projection]
            else:
                counted = [o.var for o in outputs if o.kind not in ("similarity", "distance")]
            if options.group_by is not None:
                return self.grouped(where, counted, outputs, modifiers)
            if not modifiers and len(counted) == 1:
                query = f"SELECT (COUNT({distinct}?{counted[0]}) AS ?{count_var}) {where}"
            elif not modifiers and not options.distinct:
                query = f"SELECT (COUNT(*) AS ?{count_var}) {where}"
            else:
                inner = f"SELECT {distinct}{' '.join('?' + v for v in counted)} {where}"
                if modifiers:
                    inner += "\n" + "\n".join(modifiers)
                inner = "\n".join("    " + line for line in inner.split("\n"))
                query = f"SELECT (COUNT(*) AS ?{count_var}) WHERE {{\n  {{\n{inner}\n  }}\n}}"
            return self.result(query, [SparqlOutput(var=count_var, kind="count")])

        projected = (
            [self.element_var(outputs, e) for e in options.projection]
            if options.projection is not None
            else [o.var for o in outputs]
        )
        query = f"SELECT {distinct}{' '.join('?' + v for v in projected)} {where}"
        if options.order_by is not None:
            query += "\nORDER BY " + " ".join("?" + self.element_var(outputs, e) for e in options.order_by)
        elif options.order:
            if order:
                query += "\nORDER BY " + " ".join(order)
            else:
                order_vars = [o.var for o in outputs if o.kind in ("label", "property", "image", "link")]
                order_vars = order_vars or [o.var for o in outputs if o.kind == "subject"]
                query += "\nORDER BY " + " ".join("?" + v for v in order_vars)
        if modifiers:
            query += "\n" + "\n".join(modifiers)
        return self.result(query, outputs)

    def grouped(self, where: str, counted: list[str], outputs: list[SparqlOutput], modifiers: list[str]) -> GeneratedSparql:
        """Count mode with group_by: the count of every value of the group variable."""
        options = self.options
        group = self.element_var(outputs, options.group_by)
        count_var = options.count_var
        if options.count_subject is not None:
            # distinct bindings of the counted subject per value
            query = f"SELECT ?{group} (COUNT(DISTINCT ?{counted[0]}) AS ?{count_var}) {where}"
        else:
            # distinct solutions of the counted variables (and the group) per value
            inner_vars = list(dict.fromkeys([group, *counted]))
            inner = f"SELECT {'DISTINCT ' if options.distinct else ''}{' '.join('?' + v for v in inner_vars)} {where}"
            inner = "\n".join("    " + line for line in inner.split("\n"))
            query = f"SELECT ?{group} (COUNT(*) AS ?{count_var}) WHERE {{\n  {{\n{inner}\n  }}\n}}"
        query += f"\nGROUP BY ?{group}"
        if options.group_order == "count":
            query += f"\nORDER BY DESC(?{count_var}) ?{group}"
        else:
            query += f"\nORDER BY ?{group}"
        if modifiers:
            query += "\n" + "\n".join(modifiers)
        return self.result(
            query, [SparqlOutput(var=group, kind="property", element_id=options.group_by), SparqlOutput(var=count_var, kind="count")]
        )

    def result(self, query: str, outputs: list[SparqlOutput]) -> GeneratedSparql:
        return GeneratedSparql(
            query=self.prologue() + query,
            outputs=outputs,
            warnings=list(self.warnings),
            undeclared_prefixes=list(self.undeclared),
        )


def generate_sparql(graph: QueryGraph, options: SparqlOptions | None = None, **kwargs) -> GeneratedSparql:
    """SPARQL of a query graph; kwargs override fields of options (see SparqlOptions)."""
    if kwargs:
        base = options.model_dump() if options is not None else {}
        options = SparqlOptions.model_validate({**base, **kwargs})
    return SparqlGenerator(graph, options).generate()
