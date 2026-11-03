"""The sampler of progressive discovery (the overview is the package's docstring).

Candidates
- non-empty graph: every outgoing link of a (typed) subject, i.e. each
  (property, range) of the stored object properties whose domain is the
  subject's class or a parent (SchemaIndex.links_of). A candidate adds the link and a new
  target subject of the range class; a property without (blank-node, union,
  owl:Thing) range gets an untyped target (empty uri, no type triple).
  Datatype properties are no candidates: they would be query_prop subqueries,
  which Operations cannot attach to a subject. Properties the subject already
  links with are left out, as are untyped subjects (no domain to look up).
- empty graph: the root classes as starting points (add one subject).

Constraint candidates (``sample_constraints``, non-empty graphs): subqueries
on the (typed) subjects, each an Operation with the subject's ``subject_id``.
A sampled candidate (subject, property) yields several modifications, from the
property's value distribution in the context of the request graph (the graph's
query with ``?subject <property> ?value`` added, weighted by the distinct
bindings of the counted subject per value, i.e. the share of the counted result
a value stands for; see value_distribution):
- numeric (xsd decimal/float/double/integer types) and date (xsd:date,
  xsd:dateTime) datatype properties: a threshold at each of the configured
  percentiles (weighted nearest rank), ``< p`` below the median (the lowest p
  percent) and ``> p`` from it on (the highest), as Number/DateSubQuery. The
  distribution is one GROUP BY of the values (ordered by value, capped at
  max_numeric_values); if there are more distinct values, the percentiles are
  read off the distinct (counted subject, value) pairs ordered by value with
  one OFFSET/LIMIT 1 subquery per percentile in a UNION, after a count of the
  pairs (QLever sorts the pairs once, its cache shares the sorted subtree).
  xsd:gYear and other partial dates are left out (no date/number comparison).
- categorical properties, values that recur among the counted results: string
  datatype properties (xsd:string, rdf:langString, rdfs:Literal; equals on
  STR(), labels of the configured language), booleans (BooleanSubQuery), the
  rdfs:label of the counted subject (shared names, e.g. ships named
  "Enterprise") and the instance of every other subject (SubjectSubQuery, e.g.
  the homeport Place of the ships; its rdfs:label would mostly duplicate that).
  The max_categorical_values most frequent values are fetched (GROUP BY, ORDER
  BY DESC(count)); values of fewer than min_category_count counted results are
  dropped, so identifiers and names (every value unique) are no categories.
  categorical_samples values are drawn without replacement with probability
  proportional to their frequency (Efraimidis-Spirakis keys from the seeded
  RNG), so frequent values are likelier but rare ones still appear.
Properties a subject already has a subquery on are left out. Candidates are
tried in a seeded random order (an own RNG, so the link sample does not change
with them) until constraint_sample_size of them have values (thresholds or
categories) in the context, in at most CONSTRAINT_ROUNDS rounds: in DBpedia most
datatype properties of a class are unused by the instances of a given query.

Counts are of the distinct bindings of the counted subject (the request's
``count_subject``, by default the first subject of the graph), capped at
``count_limit`` (a count equal to the limit is a lower bound). Similarity
links and vector sorts are dropped before counting (the tensorIndex SERVICE is
too costly per candidate), so their restrictions are not counted. Counts that
fail (invalid graph, endpoint error) or exceed the per-query timeout are None.

Streaming: every count and value distribution of a request runs on one bounded pool
(JobPool, ``parallelism`` threads, per-job timeouts) and each result is streamed the
moment it is in (ProgressiveSampler.stream, the events of the streaming protocol
(protocol.py), sent by the WebSocket /{config_id}/progressive/ws). The counts of the first level
start as soon as its modifications are built; the value distributions of the constraint
candidates run besides them (queued before waiting counts), and the constraint
modifications are counted once their distributions are in; a tree level is expanded once
the previous level's counts are in, each parent's children counted as soon as they are
sampled. Which modifications are sampled stays seeded and deterministic, and the result's
modifications keep their order (links, constraints, then level by level); only the
arrival order of the events varies. A CancelToken stops a sampling, dropping its waiting
jobs. sample() is stream() without events.

Schema lookups (the properties of a class, labels, root classes, the details of
added subjects/links) come from the schema stored by the initialisation
(``schema``: GuidanceManager.schema_index, explorative/schema_index.py), read
from Postgres once and answered in memory; a class it does not know has no
candidates. It has a single domain class and range per property and no
properties without a range. Only labels it lacks (instances) are queried, in
one query per batch; counts and value distributions run on the endpoint.

Tree expansion (``depth`` > 1): the modifications of the request graph are the
first level, as with depth 1 (same sample, ids and counts). Each further level
continues from ``branching`` modifications of the previous one: the modified
graph (request graph + its operations) is sampled like the request graph, with
child_sample_size links and, with constraints, child_constraint_sample_size
constrained properties (values in the context of the modified graph), from a
seed derived from the request's seed and the parent's id. A child's
``operations`` are cumulative (the parent's, then its own ``step_operations``),
so it applies to the request graph like a first-level modification; its id is
``<parent id> > <own key>``, unique across the tree.
- which modifications are expanded (select_expansions): only counted, non-empty
  ones below the count limit (a count of 0 stays 0 below, a capped count is a
  lower bound, so its children's ratios mean little); among them, the nearest
  to ``branching`` positions evenly spread over their log-count range (the
  histogram's axis), so narrow and broad modifications are both continued; ties
  in a seeded order.
- duplicates: the same graph reached by the same steps in another order (A then
  B, B then A) is counted once, the first in tree order (graph_key: the graph
  with the sampler's ids replaced by the paths of links that added them).
- budget: endpoint queries (counts and value distributions, not the cached
  ontology lookups of labels/details) of the whole request are capped by
  max_total_queries. The first level is always sampled in full; deeper levels
  stop expanding, or drop the children that do not fit, once it is spent
  (``budget_exhausted``). A count is spent when it is submitted, a value distribution
  when it is done (see QueryBudget), so the budget's decisions do not depend on the
  order in which the concurrent queries finish.
"""

from __future__ import annotations

import copy
import random
import re
import threading
from contextlib import nullcontext
from typing import TYPE_CHECKING, Callable, Sequence

from pydantic import BaseModel
from rdflib.plugins.stores.sparqlstore import SPARQLStore

from agent.protocol import GraphDetails
from assistant.assistant_model import (
    AssistantLink,
    AssistantNumberConstraintType,
    AssistantStringConstraintType,
    AssistantSubject,
    BooleanSubQuery,
    DateSubQuery,
    NumberSubQuery,
    Operation,
    OperationType,
    QueryGraph,
    QueryPropSubQuery,
    StringSubQuery,
    SubjectSubQuery,
)
from assistant.progressive.candidates import (
    Candidate,
    ConstraintCandidate,
    default_seed,
    graph_ids,
    graph_key,
    max_cost,
    select_expansions,
    slug,
    stable_seed,
)
from assistant.progressive.concurrency import CancelToken, JobPool, QueryBudget, QueryMeter
from assistant.progressive.models import (
    ConstraintKind,
    ModificationKind,
    ProgressiveConstraint,
    ProgressiveModification,
    ProgressiveRequest,
    ProgressiveResult,
    complete,
    summary,
)
from assistant.progressive.protocol import (
    ProgressiveCount,
    ProgressiveDone,
    ProgressiveLevel,
    ProgressiveModifications,
    ProgressiveStart,
)
from assistant.progressive.runners import (
    CountRunner,
    SelectRunner,
    Term,
    counted_graph,
    endpoint_counter,
    endpoint_selector,
    ontology_counter,
    ontology_selector,
)
from assistant.progressive.values import (
    LITERAL_RANGES,
    ORDERED_KINDS,
    XSD,
    ValueDistribution,
    literal_value_kind,
    percentile_rank,
    split_prologue,
    weighted_percentiles,
    weighted_sample,
)
from assistant.sparql_gen import SparqlOptions, format_number
from eval_config import ProgressiveConfig

if TYPE_CHECKING:
    from explorative.schema_index import SchemaIndex
    from ontology import OntologyManager

    # the schema lookups' source: an index or a provider of one (resolved per request)
    SchemaSource = SchemaIndex | Callable[[], SchemaIndex]

# ranges that do not restrict the target, which then stays untyped
UNTYPED_RANGES = {"http://www.w3.org/2002/07/owl#Thing"}
RDFS_LABEL = "rdfs:label"
# subquery id of the value variable of the distribution queries
VALUE_ID = "progressive_value"
# rounds of constraint candidates tried until enough have values (at most this many
# times constraint_sample_size distribution queries)
CONSTRAINT_ROUNDS = 3


class ProgressiveSampler:
    def __init__(
        self,
        ontology_manager: "OntologyManager",
        schema: SchemaSource,
        config: ProgressiveConfig | None = None,
        run_count: CountRunner | None = None,
        run_select: SelectRunner | None = None,
    ):
        self.ontology = ontology_manager
        # schema lookups (properties, labels, root classes, details) from the stored schema
        # (GuidanceManager.schema_index), resolved once per request (metered)
        self._schema_source = schema
        self.schema: SchemaIndex | None = None if callable(schema) else schema
        self.config = config or ProgressiveConfig()
        store = getattr(ontology_manager.onto, "store", None)
        self.native_paths = isinstance(store, SPARQLStore)
        # rdflib's SPARQL parser is not thread-safe, so queries of a local graph
        # (anything but a SPARQLStore, which passes them through) run one at a time
        self._local_lock = nullcontext() if self.native_paths else threading.Lock()
        if run_count is None:
            run_count = (
                endpoint_counter(store.query_endpoint, server_timeout=self.config.server_timeout)
                if self.native_paths
                else ontology_counter(ontology_manager, self._local_lock)
            )
        self.run_count = run_count
        if run_select is None:
            run_select = (
                endpoint_selector(store.query_endpoint, server_timeout=self.config.server_timeout)
                if self.native_paths
                else ontology_selector(ontology_manager, self._local_lock)
            )
        self.run_select = run_select
        # labels by URI (of instances, the schema's are looked up directly)
        self._labels: dict[str, str] = {}

    # --- ontology lookups (cached) ---

    def outgoing(self, cls: str) -> list[tuple[str, str | None]]:
        """(property, range) of the object properties of a class (and its parents)."""
        properties = {}
        for link in self.schema.links_of(cls):
            range_uri = link.range
            # literal ranges, and custom datatypes (stored as to_proptype)
            if (range_uri is not None and self.is_literal(range_uri)) or "DatatypeProperty" in link.link_type:
                continue
            if link.to_id is not None:
                range_uri = self.schema.iri(link.to_id)
            properties[(self.schema.iri(link.property_id), range_uri)] = None
        return list(properties)

    def literal_properties(self, cls: str) -> list[tuple[str, str]]:
        """(property, literal range) of the datatype properties of a class (and its parents)."""
        properties = {}
        for link in self.schema.links_of(cls):
            if link.range is not None and self.is_literal(link.range):
                properties[(self.schema.iri(link.property_id), link.range)] = None
        return list(properties)

    def load_labels(self, uris: list[str]):
        """Fetch the labels of ``uris`` (in the configured language or untagged) in one query."""
        missing = sorted({u for u in uris if u and u not in self._labels})
        known = {u: label for u in missing if (label := self.schema.label(u))}
        self._labels.update(known)
        missing = [u for u in missing if u not in known]
        if not missing:
            return
        language = self.ontology.config.language
        query = f"""
            SELECT ?s ?label WHERE {{
                VALUES ?s {{ {" ".join(self.ontology.wrap_iri(u) for u in missing)} }}
                ?s rdfs:label ?label .
                FILTER (lang(?label) = "{language}" || lang(?label) = "")
            }}"""
        labels: dict[str, str] = {}
        try:
            for s, label in self.ontology.q_to_df(query).itertuples(index=False):
                key = self.ontology.wrap_iri(self.ontology.to_readable(s))
                # prefer the tagged label
                if key not in labels or getattr(label, "language", None):
                    labels[key] = str(label)
        except Exception as e:
            print("Failed to load labels", e)
        for uri in missing:
            local = re.split(r"[/#:]", uri.strip("<>"))[-1] or uri
            self._labels[uri] = labels.get(self.ontology.wrap_iri(uri), local)

    def label(self, uri: str) -> str:
        self.load_labels([uri])
        return self._labels[uri]

    def expand(self, uri: str) -> str:
        """Full IRI (without <>) of an n3 IRI or prefixed name."""
        if uri.startswith("<") and uri.endswith(">"):
            return uri[1:-1]
        prefix, _, local = uri.partition(":")
        namespaces = self.ontology.namespaces()
        return f"{namespaces[prefix]}{local}" if prefix in namespaces and "://" not in uri else uri

    def is_literal(self, range_uri: str) -> bool:
        iri = self.expand(range_uri)
        return iri.startswith(XSD) or iri in LITERAL_RANGES

    def value_kind(self, range_uri: str) -> str | None:
        """Constraint kind of a literal range (see the module docstring), None for none."""
        return literal_value_kind(self.expand(range_uri))

    def target_class(self, range_uri: str | None) -> str:
        if range_uri is None or self.expand(range_uri) in UNTYPED_RANGES:
            return ""
        return range_uri

    def root_classes(self) -> list[str]:
        return self.schema.root_classes()

    def candidates(self, graph: QueryGraph, subject_ids: list[str] | None = None) -> list[Candidate]:
        """All candidate modifications of ``graph``, in a deterministic order."""
        if not graph.subjects:
            return [Candidate(target_uri=cls) for cls in self.root_classes()]
        candidates: dict[str, Candidate] = {}
        for subject in graph.subjects:
            if not subject.uri or (subject_ids is not None and subject.id not in subject_ids):
                continue
            linked = {self.expand(l.uri) for l in graph.links if l.from_subject_id == subject.id and l.uri}
            for prop, range_uri in self.outgoing(subject.uri):
                if self.expand(prop) in linked or (range_uri is not None and self.is_literal(range_uri)):
                    continue
                candidate = Candidate(target_uri=self.target_class(range_uri), from_id=subject.id, prop=prop)
                candidates.setdefault(candidate.key, candidate)
        return list(candidates.values())

    def constraint_candidates(
        self, graph: QueryGraph, count_subject: str, subject_ids: list[str] | None = None
    ) -> list[ConstraintCandidate]:
        """All constrained properties of ``graph``'s typed subjects, in a deterministic order."""
        candidates: list[ConstraintCandidate] = []
        for subject in graph.subjects:
            if not subject.uri or (subject_ids is not None and subject.id not in subject_ids):
                continue
            constrained = {self.expand(sq.property_id) for sq in subject.subqueries if sq.property_id}
            if subject.id == count_subject:
                # its instances are counted once each, only shared labels are categories
                if self.expand(RDFS_LABEL) not in constrained:
                    candidates.append(ConstraintCandidate(subject.id, "label", RDFS_LABEL, "xsd:string"))
            elif not any(isinstance(sq, SubjectSubQuery) and sq.instance_id for sq in subject.subqueries):
                candidates.append(ConstraintCandidate(subject.id, "instance"))
            for prop, range_uri in self.literal_properties(subject.uri):
                kind = self.value_kind(range_uri)
                if kind is not None and self.expand(prop) not in constrained:
                    candidates.append(ConstraintCandidate(subject.id, kind, prop, range_uri))
        return candidates

    # --- value distributions ---

    def distribution_options(self, count_subject: str, **options) -> SparqlOptions:
        return SparqlOptions.from_ontology(
            self.ontology,
            count_subject=count_subject,
            path_ranges="native" if self.native_paths else "expand",
            labels=False,
            **options,
        )

    def value_distribution(
        self, graph: QueryGraph, candidate: ConstraintCandidate, count_subject: str, percentiles: Sequence[float]
    ) -> ValueDistribution:
        """Values of a candidate among the request graph's solutions (see the module docstring)."""
        context = counted_graph(graph)
        group = candidate.subject_id
        if candidate.prop is not None:
            group = VALUE_ID
            context.get_subject_by_id(candidate.subject_id).subqueries.append(
                QueryPropSubQuery(id=VALUE_ID, property_id=candidate.prop)
            )
        timeout = self.config.timeout
        ordered = candidate.value_kind in ORDERED_KINDS
        # one more value than the cap shows that it was reached
        cap = self.config.max_numeric_values + 1 if ordered else self.config.max_categorical_values
        query = context.to_sparql(
            self.distribution_options(
                count_subject,
                mode="count",
                group_by=group,
                group_order="value" if ordered else "count",
                group_language=self.ontology.config.language if candidate.value_kind in ("string", "label") else None,
                limit=cap,
            )
        )
        rows = [(term, int(float(count.value))) for term, count in self.run_select(query, timeout) if term is not None and count is not None]
        if not ordered:
            categories = [(term, count) for term, count in rows if count >= self.config.min_category_count]
            # deterministic order for the seeded sample: most frequent first, then by value
            categories.sort(key=lambda v: (-v[1], v[0].value))
            return ValueDistribution(categories=categories)
        if len(rows) < cap:
            return ValueDistribution(thresholds=weighted_percentiles(candidate.value_kind, rows, percentiles))
        return ValueDistribution(thresholds=self.ranked_percentiles(context, candidate, count_subject, percentiles))

    def ranked_percentiles(
        self, context: QueryGraph, candidate: ConstraintCandidate, count_subject: str, percentiles: Sequence[float]
    ) -> list[tuple[float, Term]]:
        """Percentiles of too many distinct values: the (counted subject, value) pairs by
        value at the nearest ranks, one OFFSET subquery each, after a count of the pairs."""
        timeout = self.config.timeout
        pairs = [count_subject, VALUE_ID]
        total = self.run_count(
            context.to_sparql(self.distribution_options(None, mode="count", projection=pairs)), timeout
        )
        if total == 0 or not percentiles:
            return []
        prologue, branches = "", []
        for i, percentile in enumerate(percentiles):
            generated = context.sparql(
                self.distribution_options(
                    None, projection=[VALUE_ID, count_subject], order_by=[VALUE_ID],
                    limit=1, offset=percentile_rank(percentile, total) - 1,
                )
            )
            prologue, inner = split_prologue(generated.query)
            value_var = generated.var_of("property", VALUE_ID)
            inner = "\n".join("      " + line for line in inner.split("\n"))
            branches.append(f"  {{\n    {{\n{inner}\n    }}\n    BIND({i} AS ?rank)\n    BIND(?{value_var} AS ?value)\n  }}")
        query = f"{prologue}\nSELECT ?rank ?value WHERE {{\n" + "\n  UNION\n".join(branches) + "\n}"
        values = {}
        for rank, value in self.run_select(query, timeout):
            if rank is not None and value is not None:
                values[int(rank.value)] = value
        return [(p, values[i]) for i, p in enumerate(percentiles) if i in values]

    # --- modifications ---

    @staticmethod
    def new_id(label: str, taken: set[str]) -> str:
        """An id of ``label`` that is not in ``taken`` (which is updated)."""
        base, i = slug(label), 1
        while f"{base}_{i}" in taken:
            i += 1
        taken.add(f"{base}_{i}")
        return f"{base}_{i}"

    def constraint_modifications(
        self, graph: QueryGraph, candidate: ConstraintCandidate, distribution: ValueDistribution, taken: set[str]
    ) -> list[tuple[ProgressiveModification, QueryGraph]]:
        """The modifications of a constrained property (its thresholds and sampled
        categories, instance labels loaded) and their modified graphs."""
        subject = graph.get_subject_by_id(candidate.subject_id)
        prop_label = self.label(candidate.prop) if candidate.prop else None
        base = dict(property_id=candidate.prop, property_label=prop_label, property_type=candidate.range_uri)
        info = dict(subject_id=subject.id, property_id=candidate.prop, property_label=prop_label)
        # (subquery, constraint, label text, description)
        constraints: list[tuple] = []
        seen: set[tuple[str, str]] = set()
        for percentile, term in distribution.thresholds:
            below = percentile < 50
            operator = AssistantNumberConstraintType.LESS if below else AssistantNumberConstraintType.GREATER
            if (operator.value, term.value) in seen:
                continue
            seen.add((operator.value, term.value))
            if candidate.value_kind == "number":
                subquery = NumberSubQuery(value=float(term.value), operator=operator, **base)
                value = format_number(subquery.value)
            else:
                subquery = DateSubQuery(value=term.value, operator=operator, **base)
                value = term.value
            constraints.append((
                subquery,
                ProgressiveConstraint(kind=ConstraintKind.PERCENTILE, value=value, percentile=percentile, **info),
                f"{prop_label} {'<' if below else '>'} {value} (p{percentile:g})",
                f"{prop_label} {'below' if below else 'above'} its {percentile:g}th percentile {value}",
            ))
        for term, frequency in distribution.categories:
            if candidate.value_kind == "instance":
                instance = f"<{term.value}>"
                value = self.label(instance)
                subquery = SubjectSubQuery(instance_id=instance, instance_label=value, property_type="owl:Thing")
                text = f"= {value}"
            elif candidate.value_kind == "boolean":
                value = term.value
                subquery = BooleanSubQuery(value=term.value.strip().lower() in ("true", "1"), **base)
                text = f"{prop_label} = {value}"
            else:
                value = term.value
                subquery = StringSubQuery(value=value, operator=AssistantStringConstraintType.EQUALS, **base)
                text = f'{prop_label} = "{value}"'
            constraints.append((
                subquery,
                ProgressiveConstraint(kind=ConstraintKind.CATEGORY, value=value, frequency=frequency, **info),
                text,
                f"{text} ({frequency} of the current results)",
            ))

        results = []
        for subquery, constraint, text, description in constraints:
            subquery.id = self.new_id(prop_label or "instance", taken)
            operation = Operation(operation=OperationType.ADD, data=subquery, subject_id=subject.id)
            modified = graph.model_copy(deep=True)
            modified.apply(operation)
            operator = getattr(subquery, "operator", None)
            value = subquery.instance_id if isinstance(subquery, SubjectSubQuery) else subquery.value
            results.append((
                ProgressiveModification(
                    id=f"{candidate.key}|{operator.value if operator else 'equals'}|{value}",
                    kind=ModificationKind.CONSTRAINT,
                    operations=[operation],
                    label=f"{subject.label}: {text}",
                    description=f"Keep the {subject.label} results with {description}",
                    details=GraphDetails(),
                    constraint=constraint,
                ),
                modified,
            ))
        return results

    def modification(
        self, graph: QueryGraph, candidate: Candidate, taken: set[str]
    ) -> tuple[ProgressiveModification, QueryGraph]:
        """The modification of a candidate (ids unique among ``taken``, which is updated) and the modified graph."""

        def new_id(label: str) -> str:
            return self.new_id(label, taken)

        modified = graph.model_copy(deep=True)
        target_label = self.label(candidate.target_uri) if candidate.target_uri else "thing"
        target = AssistantSubject(uri=candidate.target_uri, label=target_label, id=new_id(target_label))
        modified.add_subject(target)
        operations = [Operation(operation=OperationType.ADD, data=target)]
        if candidate.from_id is None:
            return (
                ProgressiveModification(
                    id=candidate.key,
                    kind=ModificationKind.START,
                    operations=operations,
                    label=target_label,
                    description=f"Start from {target_label}",
                ),
                modified,
            )
        source = graph.get_subject_by_id(candidate.from_id)
        property_label = self.label(candidate.prop)
        link = AssistantLink(
            uri=candidate.prop,
            label=property_label,
            id=new_id(property_label),
            from_subject_id=source.id,
            to_subject_id=target.id,
            from_subject_label=source.label,
            from_subject_uri=source.uri,
            to_subject_label=target.label,
            to_subject_uri=target.uri,
        )
        modified.add_link(link)
        operations.append(Operation(operation=OperationType.ADD, data=link))
        return (
            ProgressiveModification(
                id=candidate.key,
                operations=operations,
                label=f"{source.label} → {property_label} → {target_label}",
                description=f"Link {source.label} by {property_label} to a new {target_label}",
            ),
            modified,
        )

    def details(self, modification: ProgressiveModification) -> GraphDetails:
        """Ontology data of the added elements (from the schema; left out if it does not
        know them), like the agent's add_subject/add_link."""
        details = GraphDetails()
        for operation in modification.operations:
            data = operation.data
            if isinstance(data, AssistantSubject) and data.uri:
                if (subject := self.schema.subject(data.uri)) is not None:
                    details.subjects[data.id] = subject
            elif isinstance(data, AssistantLink):
                if (link := self.schema.link(data.uri)) is not None:
                    details.links[data.id] = link
        return details

    def count_job(self, graph: QueryGraph, count_subject: str, limit: int | None) -> Callable[[], int]:
        options = SparqlOptions.from_ontology(
            self.ontology,
            mode="count",
            count_subject=count_subject,
            limit=limit,
            path_ranges="native" if self.native_paths else "expand",
        )
        timeout = self.config.timeout

        def job() -> int:
            # generation errors (invalid graphs) fail the job, i.e. count None
            return self.run_count(counted_graph(graph).to_sparql(options), timeout)

        return job

    # --- sampling ---

    def metered(self) -> "ProgressiveSampler":
        """A copy for one request (sharing the caches) whose endpoint queries are
        counted by its ``queries`` meter."""
        sampler = copy.copy(self)
        source = self._schema_source
        sampler.schema = source() if callable(source) else source
        if sampler.schema is None:
            raise RuntimeError("the schema index is not available")
        sampler.queries = QueryMeter()
        sampler.run_count = sampler.queries.wrap(self.run_count)
        sampler.run_select = sampler.queries.wrap(self.run_select)
        return sampler

    def sample(self, request: ProgressiveRequest) -> ProgressiveResult:
        """The whole result of a request (its streamed events are dropped)."""
        return self.stream(request)

    def stream(
        self,
        request: ProgressiveRequest,
        emit: Callable[[BaseModel], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> ProgressiveResult:
        """Samples ``request``, calling ``emit`` with each event of the streaming protocol
        (start, count, modifications, level, done; see protocol.py) as soon as it is known, from
        the calling or a pool thread (one at a time), and returns the result.

        Raises ValueError for an invalid request (before any event) and SamplingCancelled
        once ``cancel`` is cancelled (no events follow it then).
        """
        if request.depth > self.config.max_depth:
            raise ValueError(f"depth {request.depth} exceeds the configured max_depth {self.config.max_depth}")
        run = self.metered()
        token = cancel or CancelToken()
        lock = threading.Lock()

        def send(event: BaseModel):
            if emit is None:
                return
            with lock:
                if not token.cancelled:
                    emit(event)

        run.emit, run.token = send, token
        run.pool = JobPool(self.config.parallelism)
        token.on_cancel(run.pool.cancel)
        try:
            result = run._sample(request)
        finally:
            run.pool.close()
        token.check()
        return result

    def submit_count(
        self, modification: ProgressiveModification | None, result: ProgressiveResult,
        graph: QueryGraph, count_subject: str, limit: int | None,
    ):
        """Counts a modification (None: the base count of ``result``) on the pool, storing
        and emitting the count as soon as it is in."""

        def done(count: int | None):
            if modification is None:
                result.base_count = count
            else:
                modification.count = count
            self.emit(ProgressiveCount(id=modification.id if modification else None, count=count))

        self.pool.submit(self.count_job(graph, count_subject, limit), self.config.timeout, done)

    def _sample(self, request: ProgressiveRequest) -> ProgressiveResult:
        graph = request.graph
        seed = request.seed if request.seed is not None else default_seed(request)
        limit = request.count_limit or self.config.count_limit
        sample_size = min(request.sample_size or self.config.default_sample_size, self.config.max_sample_size)

        count_subject = request.count_subject
        if count_subject is None and graph.subjects:
            count_subject = graph.subjects[0].id
        if count_subject is not None and not graph.has_subject(count_subject):
            raise ValueError(f"count_subject {count_subject} is not in the graph")

        candidates = self.candidates(graph, request.subject_ids)
        sampled = random.Random(seed).sample(candidates, k=min(sample_size, len(candidates)))
        # keep the enumeration order, the sample is a set
        order = {c.key: i for i, c in enumerate(candidates)}
        sampled.sort(key=lambda c: order[c.key])

        self.load_labels([c.target_uri for c in sampled] + [c.prop for c in sampled if c.prop])
        taken = graph_ids(graph)
        modifications: list[ProgressiveModification] = []
        # per modification: its graph and counted subject, for the tree expansion
        nodes: dict[str, tuple[QueryGraph, str]] = {}
        for candidate in sampled:
            modification, modified = self.modification(graph, candidate, taken)
            modification.details = self.details(modification)
            modifications.append(modification)
            # a starting point counts its own subject
            counted = count_subject if count_subject is not None else modification.operations[0].data.id
            nodes[modification.id] = (modified, counted)

        constraints = request.sample_constraints
        constraints = self.config.sample_constraints if constraints is None else constraints
        constraints = bool(constraints and graph.subjects)
        constraint_candidates = (
            self.constraint_candidates(graph, count_subject, request.subject_ids) if constraints else None
        )
        result = ProgressiveResult(
            modifications=list(modifications),
            candidate_count=len(candidates),
            count_limit=limit,
            count_subject=count_subject,
            seed=seed,
            constraint_candidate_count=len(constraint_candidates) if constraints else None,
            query_budget=self.config.max_total_queries if request.depth > 1 else None,
        )
        self.emit(ProgressiveStart(
            seed=seed,
            candidate_count=len(candidates),
            count_limit=limit,
            count_subject=count_subject,
            constraint_candidate_count=result.constraint_candidate_count,
            depth=request.depth,
            query_budget=result.query_budget,
            modifications=[m.model_copy() for m in modifications],
        ))

        # every count starts at once and is streamed as it finishes
        if graph.subjects:
            self.submit_count(None, result, graph, count_subject, limit)
        for modification in modifications:
            self.submit_count(modification, result, *nodes[modification.id], limit)

        if constraints:
            # the value distributions run on the pool besides the link counts (queued first)
            constrained, failed, _ = self.sample_constraints(
                request, graph, count_subject, seed, taken, candidates=constraint_candidates
            )
            self.token.check()
            result.failed_constraints = failed
            if constrained:
                result.modifications += [m for m, _ in constrained]
                self.emit(ProgressiveModifications(modifications=[m.model_copy() for m, _ in constrained]))
                for modification, modified in constrained:
                    nodes[modification.id] = (modified, count_subject)
                    self.submit_count(modification, result, modified, count_subject, limit)

        self.pool.join()
        self.token.check()
        if request.depth > 1:
            self.expand_tree(request, result, nodes, constraints)
        result.query_count = self.queries.count
        self.emit(ProgressiveDone(**summary(result).model_dump(), complete=complete(result)))
        return result

    # --- tree expansion ---

    def expand_tree(
        self,
        request: ProgressiveRequest,
        result: ProgressiveResult,
        nodes: dict[str, tuple[QueryGraph, str]],
        constraints: bool,
    ):
        """Adds the levels 2..request.depth to ``result`` (see the module docstring), each
        once the previous level's counts are in; a parent's children are emitted and
        counted as soon as they are sampled. ``nodes``: graph and counted subject of the
        first level's modifications."""
        config = self.config
        branching = min(request.branching or config.default_branching, config.max_branching)
        size = min(request.child_sample_size or config.child_sample_size, config.max_sample_size)
        constraint_size = request.child_constraint_sample_size
        constraint_size = config.child_constraint_sample_size if constraint_size is None else constraint_size
        child_request = request.model_copy(update={"constraint_sample_size": constraint_size})
        limit = result.count_limit
        # the first level is done: its queries are spent
        budget = QueryBudget(config.max_total_queries, spent=self.queries.count)
        result.query_budget = budget.limit

        base_ids = graph_ids(request.graph)
        seen = {graph_key(graph, base_ids) for graph, _ in nodes.values()}
        level = result.modifications
        for depth in range(2, request.depth + 1):
            parents = select_expansions(level, branching, limit, f"{result.seed}:expand:{depth}")
            if parents:
                self.emit(ProgressiveLevel(depth=depth, parent_ids=[p.id for p in parents]))
            children: list[ProgressiveModification] = []
            for parent in parents:
                self.token.check()
                if budget.remaining() <= 0:
                    result.budget_exhausted = True
                    break
                graph, counted = nodes[parent.id]
                own: list[tuple[ProgressiveModification, QueryGraph]] = []
                for child, modified in self.children(child_request, parent, graph, counted, size, constraints, budget):
                    key = graph_key(modified, base_ids)
                    if key in seen:
                        result.duplicate_count += 1
                        continue
                    if budget.remaining() <= 0:
                        result.budget_exhausted = True
                        break
                    seen.add(key)
                    # its count is submitted below
                    budget.spent += 1
                    own.append((child, modified))
                self.token.check()
                result.expanded_ids.append(parent.id)
                for child, modified in own:
                    child.step_operations = child.operations
                    child.operations = parent.operations + child.operations
                    child.id = f"{parent.id} > {child.id}"
                    child.parent_id = parent.id
                    child.depth = depth
                    # the children's details cover all their (cumulative) operations
                    child.details = self.details(child)
                    nodes[child.id] = (modified, counted)
                    children.append(child)
                if own:
                    result.modifications += [child for child, _ in own]
                    self.emit(ProgressiveModifications(
                        depth=depth, parent_id=parent.id, modifications=[c.model_copy() for c, _ in own]
                    ))
                    for child, modified in own:
                        self.submit_count(child, result, modified, counted, limit)
            self.pool.join()
            self.token.check()
            if not children:
                break
            result.depth = depth
            level = children

    def children(
        self,
        request: ProgressiveRequest,
        parent: ProgressiveModification,
        graph: QueryGraph,
        count_subject: str,
        size: int,
        constraints: bool,
        budget: QueryBudget,
    ) -> list[tuple[ProgressiveModification, QueryGraph]]:
        """The (uncounted) modifications of a parent's graph: a sample of ``size`` links and,
        with ``constraints``, of request.constraint_sample_size constrained properties
        (value distributions within the budget), from a seed of the parent."""
        seed = stable_seed(f"{request.seed}:{parent.id}") if request.seed is not None else stable_seed(parent.id)
        subject_ids = request.subject_ids
        if subject_ids is not None:
            # the subjects the path added are continued from as well
            subject_ids = subject_ids + [op.data.id for op in parent.operations if isinstance(op.data, AssistantSubject)]
        candidates = self.candidates(graph, subject_ids)
        sampled = random.Random(seed).sample(candidates, k=min(size, len(candidates)))
        order = {c.key: i for i, c in enumerate(candidates)}
        sampled.sort(key=lambda c: order[c.key])
        self.load_labels([c.target_uri for c in sampled] + [c.prop for c in sampled if c.prop])
        taken = graph_ids(graph)
        results = [self.modification(graph, candidate, taken) for candidate in sampled]
        if constraints and request.constraint_sample_size:
            request = request.model_copy(update={"subject_ids": subject_ids})
            # the links' counts are reserved before the distributions
            budget.reserved += len(results)
            try:
                constrained, _, _ = self.sample_constraints(request, graph, count_subject, seed, taken, budget)
            finally:
                budget.reserved -= len(results)
            results += constrained
        return results

    def sample_constraints(
        self,
        request: ProgressiveRequest,
        graph: QueryGraph,
        count_subject: str,
        seed: int,
        taken: set[str],
        budget: QueryBudget | None = None,
        candidates: list[ConstraintCandidate] | None = None,
    ) -> tuple[list[tuple[ProgressiveModification, QueryGraph]], list[str], int]:
        """Constraint modifications (uncounted) of a sample of the constrained properties,
        the keys of the candidates whose distribution failed, and the number of candidates.

        The distributions of a round run on the pool (before its waiting counts). With a
        ``budget``, a round tries only as many candidates as their distributions can cost
        at most (3 queries of a numeric/date property, see value_distribution), and spends
        the queries they ran (the maximum for a timed-out one).
        """
        config = self.config
        size = request.constraint_sample_size
        size = min(config.constraint_sample_size if size is None else size, config.max_constraint_sample_size)
        percentiles = request.numeric_percentiles if request.numeric_percentiles is not None else config.numeric_percentiles
        # sorted and unique, so equal settings give equal modifications
        percentiles = sorted(set(percentiles))
        categorical_samples = request.categorical_samples or config.categorical_samples

        if candidates is None:
            candidates = self.constraint_candidates(graph, count_subject, request.subject_ids)
        # a seeded random order, from an own RNG, so the link sample is the same with and
        # without constraints
        shuffled = random.Random(f"{seed}:constraints").sample(candidates, k=len(candidates))
        # many properties have no values in the context (or no categories), so the
        # candidates are tried in rounds of the missing number until `size` have some
        # (failed ones count as tried, a failing endpoint is not asked again)
        sampled: list[tuple[ConstraintCandidate, ValueDistribution]] = []
        failed: list[str] = []
        tried = 0
        for _ in range(CONSTRAINT_ROUNDS):
            batch = shuffled[tried : tried + size - len(sampled) - len(failed)]
            if budget is not None:
                allowance, affordable = budget.remaining(), 0
                for candidate in batch:
                    allowance -= max_cost(candidate)
                    if allowance < 0:
                        break
                    affordable += 1
                batch = batch[:affordable]
            if not batch:
                break
            tried += len(batch)
            costs: dict[int, int] = {}
            # two queries per distribution if its values exceed max_numeric_values
            distributions = self.pool.run_all(
                [
                    self.queries.measured(
                        lambda c=c: self.value_distribution(graph, c, count_subject, percentiles), costs, i
                    )
                    for i, c in enumerate(batch)
                ],
                2 * config.timeout,
                urgent=True,
            )
            self.token.check()
            if budget is not None:
                costs = dict(costs)
                budget.spent += sum(costs.get(i, max_cost(c)) for i, c in enumerate(batch))
            for candidate, distribution in zip(batch, distributions):
                if distribution is None:
                    failed.append(candidate.key)
                elif distribution.thresholds or distribution.categories:
                    sampled.append((candidate, distribution))
        order = {c.key: i for i, c in enumerate(candidates)}
        sampled.sort(key=lambda cd: order[cd[0].key])

        for candidate, distribution in sampled:
            # an RNG per candidate, so its values do not depend on the other candidates
            rng = random.Random(f"{seed}:{candidate.key}")
            categories = distribution.categories
            distribution.categories = weighted_sample(categories, [n for _, n in categories], categorical_samples, rng)
        self.load_labels([c.prop for c, _ in sampled if c.prop])
        self.load_labels(
            [f"<{term.value}>" for c, d in sampled if c.value_kind == "instance" for term, _ in d.categories]
        )
        modifications = []
        for candidate, distribution in sampled:
            modifications += self.constraint_modifications(graph, candidate, distribution, taken)
        return modifications, failed, len(candidates)
