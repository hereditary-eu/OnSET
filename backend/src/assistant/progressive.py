"""Progressive discovery: counts of candidate modifications of a query graph.

Given the editor's QueryGraph, the sampler enumerates the modifications the
user could make next, samples some of them, and counts the results of every
modified graph (and of the graph itself), so the frontend can show how each
step would change the result (frontend/src/utils/progressive, the panel in
components/explore/progressive).

Candidates
- non-empty graph: every outgoing link of a (typed) subject, i.e. each
  (property, range) of the object properties (owl:ObjectProperty,
  rdf:Property) whose rdfs:domain is the subject's class or a parent
  (OntologyManager.outgoing_properties). A candidate adds the link and a new
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

All counts (and the ontology details of the sampled candidates) run
concurrently on a bounded thread pool, see run_bounded.

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
  (``budget_exhausted``). Counts of a whole level run on one bounded pool.

Timeouts, parallelism and the sample/count caps are per configuration, the
``progressive`` object of backend/config.json (eval_config.ProgressiveConfig).
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import math
import random
import re
import threading
import time
from contextlib import nullcontext
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Callable, Sequence, TypeVar

import httpx
from pydantic import BaseModel, Field
from rdflib import Literal, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLStore

from agent.protocol import GraphDetails
from assistant.assistant_model import (
    AssistantLink,
    AssistantNumberConstraintType,
    AssistantStringConstraintType,
    AssistantSubject,
    AssistantSubQueryType,
    BooleanSubQuery,
    DateSubQuery,
    LinkSemanticType,
    NumberSubQuery,
    Operation,
    OperationType,
    QueryGraph,
    QueryPropSubQuery,
    StringSubQuery,
    SubjectSubQuery,
)
from assistant.sparql_gen import INTEGER_TYPES, SparqlOptions, format_number
from eval_config import ProgressiveConfig
from model import Subject, SubjectLink

if TYPE_CHECKING:
    from ontology import OntologyManager

T = TypeVar("T")

XSD = "http://www.w3.org/2001/XMLSchema#"
# ranges that are literals, i.e. of datatype properties declared as rdf:Property
LITERAL_RANGES = {
    "http://www.w3.org/2000/01/rdf-schema#Literal",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#HTML",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#XMLLiteral",
}
# ranges that do not restrict the target, which then stays untyped
UNTYPED_RANGES = {"http://www.w3.org/2002/07/owl#Thing"}
RDFS_LABEL = "rdfs:label"

# value kinds of constraint candidates by literal range (local names of xsd types)
NUMERIC_TYPES = {"decimal", "double", "float"} | (INTEGER_TYPES - {"gYear"})
DATE_TYPES = {"date", "dateTime"}
STRING_RANGES = {
    XSD + "string",
    "http://www.w3.org/2000/01/rdf-schema#Literal",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
}
# value kinds with percentile thresholds, the others are categorical
ORDERED_KINDS = {"number", "date"}
# subquery id of the value variable of the distribution queries
VALUE_ID = "progressive_value"
# rounds of constraint candidates tried until enough have values (at most this many
# times constraint_sample_size distribution queries)
CONSTRAINT_ROUNDS = 3

Percentile = Annotated[float, Field(ge=0, le=100)]


# --- API models (frontend/src/utils/progressive/types.ts) ---


class ProgressiveRequest(BaseModel):
    graph: QueryGraph
    # maximum number of candidate modifications to sample and count (capped by
    # the configured max_sample_size), None for the configured default
    sample_size: int | None = Field(None, ge=1)
    # subjects whose outgoing links are candidates, None for all subjects
    subject_ids: list[str] | None = None
    # seed of the sampling, None for one derived from the graph (stable re-runs)
    seed: int | None = None
    # subject whose distinct bindings are counted, None for the first subject
    count_subject: str | None = None
    # cap of every count, None for the configured default
    count_limit: int | None = Field(None, ge=1)
    # constraint modifications (subqueries of the graph's subjects); the settings
    # below are None for the configured defaults
    sample_constraints: bool | None = None
    # constrained properties with values to sample (capped by max_constraint_sample_size)
    constraint_sample_size: int | None = Field(None, ge=0)
    # percentiles (0-100) of numeric/date values that become thresholds
    numeric_percentiles: list[Percentile] | None = None
    # values sampled per categorical property
    categorical_samples: int | None = Field(None, ge=1)
    # tree expansion: levels of modifications (1: of the request graph only), at most
    # the configured max_depth; each level below the first expands `branching`
    # modifications of the previous one (capped by max_branching), sampling
    # child_sample_size links (capped by max_sample_size) and, with constraints,
    # child_constraint_sample_size constrained properties of each; None for the
    # configured defaults
    depth: int = Field(1, ge=1)
    branching: int | None = Field(None, ge=1)
    child_sample_size: int | None = Field(None, ge=1)
    child_constraint_sample_size: int | None = Field(None, ge=0)


class ModificationKind(str, enum.Enum):
    # a starting point of an empty graph
    START = "start"
    # a link to a new subject
    LINK = "link"
    # a subquery of a subject
    CONSTRAINT = "constraint"


class ConstraintKind(str, enum.Enum):
    # a numeric/date threshold at a percentile
    PERCENTILE = "percentile"
    # equals a sampled value (or instance)
    CATEGORY = "category"


class ProgressiveConstraint(BaseModel):
    """What a constraint modification restricts, for display."""

    kind: ConstraintKind
    subject_id: str
    # constrained property, None for the instance of the subject
    property_id: str | None = None
    property_label: str | None = None
    # readable threshold, value or instance label
    value: str
    # percentile kind: the percentile of the threshold
    percentile: float | None = None
    # category kind: counted results with the value in the request graph
    frequency: int | None = None


class ProgressiveModification(BaseModel):
    id: str
    kind: ModificationKind = ModificationKind.LINK
    # operations applied to the request graph (add subjects, links, or a subquery
    # of the subject operation.subject_id)
    operations: list[Operation] = Field([])
    # count of the modified graph, None if it failed or timed out
    count: int | None = None
    label: str
    description: str | None = None
    # ontology data of the added subjects/links keyed by graph id (as the agent sends it)
    details: GraphDetails | None = None
    # constraint modifications: what they restrict
    constraint: ProgressiveConstraint | None = None
    # tree expansion: the modification this one continues (None on the first level),
    # its level (1: a modification of the request graph), and its own operations after
    # the parent's (None on the first level, where they are `operations`); `operations`
    # are cumulative, label/description/constraint describe the own step
    parent_id: str | None = None
    depth: int = 1
    step_operations: list[Operation] | None = None


class ProgressiveResult(BaseModel):
    # count of the request graph, None for an empty graph or a failed count
    base_count: int | None = None
    modifications: list[ProgressiveModification] = Field([])
    # candidates before sampling (>= len(modifications))
    candidate_count: int | None = None
    # cap of the counts, a count equal to it is a lower bound
    count_limit: int | None = None
    # subject id the counts are of (of the request graph, None if empty)
    count_subject: str | None = None
    seed: int | None = None
    # constrained properties before sampling, None if constraints were not sampled
    constraint_candidate_count: int | None = None
    # keys (subject|property) of sampled constraint candidates whose value
    # distribution failed or timed out, so they have no modifications
    failed_constraints: list[str] = Field([])
    # tree expansion: levels sampled (fewer than requested if none could be expanded),
    # ids of the modifications whose children were sampled, children left out as their
    # graph is another modification's (same steps in another order), endpoint queries
    # (counts, value distributions) of the request, their cap (max_total_queries) and
    # whether deeper levels were cut short by it
    depth: int = 1
    expanded_ids: list[str] = Field([])
    duplicate_count: int = 0
    query_count: int | None = None
    query_budget: int | None = None
    budget_exhausted: bool = False


# --- bounded concurrent execution ---


def run_bounded(
    jobs: list[Callable[[], T]], parallelism: int, timeout: float
) -> list[T | None]:
    """Results of ``jobs`` run on ``parallelism`` threads; None where a job raised
    or ran longer than ``timeout`` seconds.

    Timed-out jobs cannot be interrupted, their threads finish in the background
    (the endpoint counter has its own HTTP timeout). Jobs still waiting when the
    whole budget (every job timing out in turn) is spent are dropped as well.
    """
    results: list[T | None] = [None] * len(jobs)
    if not jobs:
        return results
    started: dict[int, float] = {}
    lock = threading.Lock()

    def job_runner(i: int):
        with lock:
            started[i] = time.monotonic()
        return jobs[i]()

    executor = ThreadPoolExecutor(max_workers=max(1, parallelism), thread_name_prefix="progressive")
    try:
        futures: dict[Future, int] = {executor.submit(job_runner, i): i for i in range(len(jobs))}
        rounds = -(-len(jobs) // max(1, parallelism))
        deadline = time.monotonic() + timeout * (rounds + 1)
        pending = set(futures)
        while pending:
            now = time.monotonic()
            with lock:
                running = {f: started[futures[f]] for f in pending if futures[f] in started}
            expired = {f for f, start in running.items() if now - start > timeout}
            if now >= deadline:
                expired = set(pending)
            for future in expired:
                future.cancel()
                print(f"Progressive job {futures[future]} timed out")
            pending -= expired
            if not pending:
                break
            next_expiry = min(
                [start + timeout for f, start in running.items() if f in pending] + [deadline]
            )
            done, pending = wait(pending, timeout=max(0.01, next_expiry - time.monotonic()), return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    results[futures[future]] = future.result()
                except Exception as e:
                    print(f"Progressive job {futures[future]} failed: {e!r}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results


class QueryMeter:
    """Counts the calls of the wrapped query runners (thread-safe)."""

    def __init__(self):
        self.count = 0
        self._lock = threading.Lock()

    def wrap(self, run: Callable[[str, float], T]) -> Callable[[str, float], T]:
        def metered(query: str, timeout: float) -> T:
            with self._lock:
                self.count += 1
            return run(query, timeout)

        return metered


@dataclass
class QueryBudget:
    """Endpoint queries left of a request: the cap minus the queries run and the
    counts reserved for modifications that are not counted yet."""

    limit: int
    meter: QueryMeter
    reserved: int = 0

    def remaining(self) -> int:
        return self.limit - self.meter.count - self.reserved


# --- counting and value queries ---

# count of a SPARQL query (with a single ?count binding) within a timeout in seconds
CountRunner = Callable[[str, float], int]


@dataclass(frozen=True)
class Term:
    """An RDF term of a query result: an IRI (full, without <>) or a literal."""

    value: str
    iri: bool = False
    datatype: str | None = None
    lang: str | None = None

    @staticmethod
    def of(term) -> "Term | None":
        """Term of an rdflib node (None for unbound variables and blank nodes)."""
        if isinstance(term, URIRef):
            return Term(str(term), iri=True)
        if isinstance(term, Literal):
            return Term(str(term), datatype=str(term.datatype) if term.datatype else None, lang=term.language)
        return None


# rows (terms in projection order, None if unbound) of a SPARQL query within a timeout
SelectRunner = Callable[[str, float], list[tuple["Term | None", ...]]]


def endpoint_post(endpoint: str, query: str, timeout: float, server_timeout: bool) -> dict:
    """SPARQL JSON results of POSTing a query (as the SPARQLStore does), with timeouts."""
    data = {"query": query}
    if server_timeout:
        data["timeout"] = f"{max(1, round(timeout))}s"
    response = httpx.post(
        endpoint,
        data=data,
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout + 1,
    )
    if response.status_code == 400 and server_timeout:
        # an endpoint without the timeout parameter
        data.pop("timeout")
        response = httpx.post(
            endpoint, data=data, headers={"Accept": "application/sparql-results+json"}, timeout=timeout + 1
        )
    response.raise_for_status()
    return response.json()


def endpoint_counter(endpoint: str, count_var: str = "count", server_timeout: bool = True) -> CountRunner:
    """Counts by POSTing to a SPARQL endpoint, with timeouts."""

    def run(query: str, timeout: float) -> int:
        bindings = endpoint_post(endpoint, query, timeout, server_timeout)["results"]["bindings"]
        return int(bindings[0][count_var]["value"]) if bindings else 0

    return run


def endpoint_selector(endpoint: str, server_timeout: bool = True) -> SelectRunner:
    """Result rows by POSTing to a SPARQL endpoint, with timeouts."""

    def term(binding: dict | None) -> Term | None:
        if binding is None or binding.get("type") == "bnode":
            return None
        if binding.get("type") == "uri":
            return Term(binding["value"], iri=True)
        return Term(binding["value"], datatype=binding.get("datatype"), lang=binding.get("xml:lang"))

    def run(query: str, timeout: float) -> list[tuple[Term | None, ...]]:
        results = endpoint_post(endpoint, query, timeout, server_timeout)
        variables = results["head"]["vars"]
        return [tuple(term(row.get(v)) for v in variables) for row in results["results"]["bindings"]]

    return run


def ontology_counter(ontology_manager: "OntologyManager", lock=None) -> CountRunner:
    """Counts through the OntologyManager (e.g. an in-memory graph); timeouts by run_bounded only.

    ``lock`` serialises the queries (see ProgressiveSampler._local_lock); time spent
    waiting for it counts against the timeout.
    """
    lock = lock if lock is not None else threading.Lock()

    def run(query: str, timeout: float) -> int:
        with lock:
            df = ontology_manager.q_to_df(query)
        return int(df.iloc[0, 0]) if not df.empty else 0

    return run


def ontology_selector(ontology_manager: "OntologyManager", lock=None) -> SelectRunner:
    """Result rows through the OntologyManager, serialised by ``lock`` like ontology_counter."""
    lock = lock if lock is not None else threading.Lock()

    def run(query: str, timeout: float) -> list[tuple[Term | None, ...]]:
        with lock:
            rows = ontology_manager.q_rows(query)
        return [tuple(Term.of(t) for t in row) for row in rows]

    return run


def counted_graph(graph: QueryGraph) -> QueryGraph:
    """The graph without similarity links and vector sorts, which are not counted."""
    graph = graph.model_copy(deep=True)
    graph.links = [l for l in graph.links if l.semantic_link_type != LinkSemanticType.SIMILARITY]
    for subject in graph.subjects:
        subject.subqueries = [sq for sq in subject.subqueries if sq.type != AssistantSubQueryType.VECTOR_SORT]
    return graph


# --- candidates ---


@dataclass
class Candidate:
    """A modification before counting: the subject to add, linked from ``from_id`` by ``prop``."""

    # class of the added subject, "" for an untyped one
    target_uri: str
    # None: a starting point of an empty graph
    from_id: str | None = None
    prop: str | None = None

    @property
    def key(self) -> str:
        if self.from_id is None:
            return f"start|{self.target_uri}"
        return f"{self.from_id}|{self.prop}|{self.target_uri}"


@dataclass
class ConstraintCandidate:
    """A constrained property of a subject before sampling: ``prop`` None for its instance."""

    subject_id: str
    # number, date (percentiles), boolean, string, label, instance (categories)
    value_kind: str
    prop: str | None = None
    # literal range of prop, the property_type of the subqueries
    range_uri: str | None = None

    @property
    def key(self) -> str:
        return f"{self.subject_id}|{self.prop or 'instance'}"


@dataclass
class ValueDistribution:
    """Values of a constraint candidate in the request graph's context.

    ordered kinds: the thresholds (percentile, value); categories: the most frequent
    (value, count of counted results) that pass min_category_count, most frequent first.
    """

    thresholds: list[tuple[float, Term]] = field(default_factory=list)
    categories: list[tuple[Term, int]] = field(default_factory=list)


def sort_key(kind: str, term: Term):
    """Order of numeric/date values, None for values that cannot be compared."""
    try:
        if kind == "number":
            return float(term.value)
        value = term.value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        # dates and naive date-times compare as naive (time zones are dropped)
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def percentile_rank(percentile: float, total: int) -> int:
    """1-based nearest rank of a percentile among ``total`` (weighted) values."""
    return min(total, max(1, math.ceil(percentile / 100 * total)))


def weighted_percentiles(kind: str, values: list[tuple[Term, int]], percentiles: Sequence[float]) -> list[tuple[float, Term]]:
    """(percentile, value) by weighted nearest rank; values that cannot be ordered are left out."""
    keyed = sorted(
        ((key, term, weight) for term, weight in values if weight > 0 and (key := sort_key(kind, term)) is not None),
        key=lambda v: v[0],
    )
    total = sum(weight for _, _, weight in keyed)
    if total == 0:
        return []
    thresholds = []
    for percentile in percentiles:
        rank, cumulative = percentile_rank(percentile, total), 0
        for _, term, weight in keyed:
            cumulative += weight
            if cumulative >= rank:
                thresholds.append((percentile, term))
                break
    return thresholds


def weighted_sample(items: Sequence[T], weights: Sequence[float], k: int, rng: random.Random) -> list[T]:
    """``k`` items drawn without replacement, each draw proportional to the weights.

    Efraimidis-Spirakis: the k largest keys u^(1/weight), u uniform from ``rng``, in the
    order of ``items`` (which must be deterministic for a seeded sample).
    """
    keys = [(rng.random() ** (1 / weight), i) for i, weight in enumerate(weights) if weight > 0]
    chosen = sorted(i for _, i in sorted(keys, reverse=True)[:k])
    return [items[i] for i in chosen]


def split_prologue(query: str) -> tuple[str, str]:
    """PREFIX lines and the rest of a generated query."""
    lines = query.split("\n")
    prologue = [line for line in lines if line.startswith("PREFIX ")]
    return "\n".join(prologue), "\n".join(lines[len(prologue):])


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "subject"


def stable_seed(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")


def default_seed(request: ProgressiveRequest) -> int:
    """Seed derived from the graph and sampling parameters, stable across processes."""
    return stable_seed(request.model_dump_json(include={"graph", "subject_ids", "sample_size"}))


def graph_ids(graph: QueryGraph) -> set[str]:
    """Ids of the subjects, links and subqueries of a graph (taken for new elements)."""
    taken = {s.id for s in graph.subjects} | {l.id for l in graph.links}
    return taken | {sq.id for s in graph.subjects for sq in s.subqueries if sq.id}


def graph_key(graph: QueryGraph, base_ids: set[str]) -> str:
    """Key of a modified graph that does not depend on the ids the sampler assigned.

    Subjects of the request graph (``base_ids``) keep their ids, an added subject is
    named by the path of links that added it (``from>property>class``), a starting
    point by its class; subqueries and links are compared without their ids.
    """
    names = {s.id: s.id for s in graph.subjects if s.id in base_ids}
    changed = True
    while changed:
        changed = False
        for link in graph.links:
            if link.from_subject_id in names and link.to_subject_id not in names:
                target = graph.get_subject_by_id(link.to_subject_id)
                names[target.id] = f"{names[link.from_subject_id]}>{link.uri}>{target.uri}"
                changed = True
    for subject in graph.subjects:
        names.setdefault(subject.id, f"+{subject.uri}")

    def dump(model, exclude: set[str]) -> str:
        return json.dumps(model.model_dump(mode="json", exclude=exclude), sort_keys=True)

    subjects = sorted(
        (names[s.id], s.uri, sorted(dump(sq, {"id"}) for sq in s.subqueries)) for s in graph.subjects
    )
    link_fields = {"id", "from_subject_id", "to_subject_id", "label", "from_subject_label", "to_subject_label"}
    links = sorted(
        (names.get(l.from_subject_id, ""), names.get(l.to_subject_id, ""), dump(l, link_fields)) for l in graph.links
    )
    return json.dumps([subjects, links])


def select_expansions(
    modifications: list[ProgressiveModification], branching: int, limit: int, seed: str
) -> list[ProgressiveModification]:
    """The modifications of a level to expand, in their order (see the module docstring).

    Eligible: counted, non-empty and below the count ``limit``. Of more than
    ``branching`` eligible ones, the nearest to ``branching`` targets evenly spread over
    their log-count range (the middle of the range for one), each chosen once; ties are
    broken by a seeded shuffle.
    """
    eligible = [m for m in modifications if m.count is not None and 0 < m.count < limit]
    if len(eligible) <= branching:
        return eligible
    order = {m.id: i for i, m in enumerate(modifications)}
    # the seeded shuffle orders ties of equal distance (min is stable)
    pool = random.Random(seed).sample(eligible, k=len(eligible))
    position = {m.id: math.log10(m.count + 1) for m in pool}
    lo, hi = min(position.values()), max(position.values())
    targets = [(lo + hi) / 2] if branching == 1 else [lo + i * (hi - lo) / (branching - 1) for i in range(branching)]
    chosen: list[ProgressiveModification] = []
    for target in targets:
        best = min(pool, key=lambda m: abs(position[m.id] - target))
        pool.remove(best)
        chosen.append(best)
    return sorted(chosen, key=lambda m: order[m.id])


class ProgressiveSampler:
    def __init__(
        self,
        ontology_manager: "OntologyManager",
        config: ProgressiveConfig | None = None,
        run_count: CountRunner | None = None,
        run_select: SelectRunner | None = None,
    ):
        self.ontology = ontology_manager
        self.config = config or ProgressiveConfig()
        store = getattr(ontology_manager.onto, "store", None)
        self.native_paths = isinstance(store, SPARQLStore)
        # rdflib's SPARQL parser is not thread-safe, so queries of a local graph
        # (anything but a SPARQLStore, which passes them through) run one at a time
        self._local_lock = nullcontext() if self.native_paths else threading.Lock()
        # ontology lookups (labels, details) go through rdflib's parser with a SPARQLStore
        # as well, so the concurrent ones (the details jobs) always run one at a time
        self._ontology_lock = threading.Lock() if self.native_paths else self._local_lock
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
        # per class / URI, the ontology does not change while the server runs
        self._properties: dict[str, list[tuple[str, str | None]]] = {}
        self._literal_properties: dict[str, list[tuple[str, str]]] = {}
        self._subjects: dict[str, Subject] = {}
        self._labels: dict[str, str] = {}

    # --- ontology lookups (cached) ---

    def outgoing(self, cls: str) -> list[tuple[str, str | None]]:
        if cls not in self._properties:
            self._properties[cls] = self.ontology.outgoing_properties(cls)
        return self._properties[cls]

    def literal_properties(self, cls: str) -> list[tuple[str, str]]:
        """(property, literal range) of the datatype properties of a class (and its parents)."""
        if cls not in self._literal_properties:
            properties = self.ontology.outgoing_properties(
                cls, ("owl:ObjectProperty", "owl:DatatypeProperty", "rdf:Property")
            )
            self._literal_properties[cls] = [(p, r) for p, r in properties if r is not None and self.is_literal(r)]
        return self._literal_properties[cls]

    def subject(self, uri: str) -> Subject:
        if uri not in self._subjects:
            self._subjects[uri] = self.ontology.enrich_subject(uri)
        return self._subjects[uri]

    def load_labels(self, uris: list[str]):
        """Fetch the labels of ``uris`` (in the configured language or untagged) in one query."""
        missing = sorted({u for u in uris if u and u not in self._labels})
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
        iri = self.expand(range_uri)
        local = iri[len(XSD):] if iri.startswith(XSD) else None
        if local in NUMERIC_TYPES:
            return "number"
        if local in DATE_TYPES:
            return "date"
        if local == "boolean":
            return "boolean"
        if iri in STRING_RANGES:
            return "string"
        return None

    def target_class(self, range_uri: str | None) -> str:
        if range_uri is None or self.expand(range_uri) in UNTYPED_RANGES:
            return ""
        return range_uri

    def root_classes(self) -> list[str]:
        # in the form of outgoing_properties/enrich_subject (n3 or prefixed)
        return list(dict.fromkeys(self.ontology.to_readable(URIRef(str(c))) for c in self.ontology.root_class_ids()))

    def candidates(self, graph: QueryGraph, subject_ids: list[str] | None = None) -> list[Candidate]:
        """All candidate modifications of ``graph``, in a deterministic order."""
        if not graph.subjects:
            return [Candidate(target_uri=cls) for cls in self.root_classes()]
        candidates: dict[str, Candidate] = {}
        for subject in graph.subjects:
            if not subject.uri or (subject_ids is not None and subject.id not in subject_ids):
                continue
            linked = {
                self.ontology.wrap_iri(l.uri) for l in graph.links if l.from_subject_id == subject.id and l.uri
            }
            for prop, range_uri in self.outgoing(subject.uri):
                if self.ontology.wrap_iri(prop) in linked or (range_uri is not None and self.is_literal(range_uri)):
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
            constrained = {self.ontology.wrap_iri(sq.property_id) for sq in subject.subqueries if sq.property_id}
            if subject.id == count_subject:
                # its instances are counted once each, only shared labels are categories
                if self.ontology.wrap_iri(RDFS_LABEL) not in constrained:
                    candidates.append(ConstraintCandidate(subject.id, "label", RDFS_LABEL, "xsd:string"))
            elif not any(isinstance(sq, SubjectSubQuery) and sq.instance_id for sq in subject.subqueries):
                candidates.append(ConstraintCandidate(subject.id, "instance"))
            for prop, range_uri in self.literal_properties(subject.uri):
                kind = self.value_kind(range_uri)
                if kind is not None and self.ontology.wrap_iri(prop) not in constrained:
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

    def guarded(self, fn: Callable[..., T], *args) -> T:
        with self._ontology_lock:
            return fn(*args)

    def details(self, modification: ProgressiveModification) -> GraphDetails:
        """Ontology data of the added elements, like the agent's add_subject/add_link."""
        details = GraphDetails()
        for operation in modification.operations:
            data = operation.data
            if isinstance(data, AssistantSubject) and data.uri:
                details.subjects[data.id] = self.subject(data.uri)
            elif isinstance(data, AssistantLink):
                prop = self.subject(data.uri)
                link: SubjectLink = prop.to_link()
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
        sampler.queries = QueryMeter()
        sampler.run_count = sampler.queries.wrap(self.run_count)
        sampler.run_select = sampler.queries.wrap(self.run_select)
        return sampler

    def sample(self, request: ProgressiveRequest) -> ProgressiveResult:
        if request.depth > self.config.max_depth:
            raise ValueError(f"depth {request.depth} exceeds the configured max_depth {self.config.max_depth}")
        return self.metered()._sample(request)

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
        jobs: list[Callable] = []
        if graph.subjects:
            jobs.append(self.count_job(graph, count_subject, limit))
        for candidate in sampled:
            modification, modified = self.modification(graph, candidate, taken)
            modifications.append(modification)
            # a starting point counts its own subject
            counted = count_subject if count_subject is not None else modification.operations[0].data.id
            nodes[modification.id] = (modified, counted)
            jobs.append(self.count_job(modified, counted, limit))
        link_modifications = list(modifications)

        constraints = request.sample_constraints
        constraints = self.config.sample_constraints if constraints is None else constraints
        constraint_candidate_count, failed = None, []
        if constraints and graph.subjects:
            constrained, failed, constraint_candidate_count = self.sample_constraints(
                request, graph, count_subject, seed, taken
            )
            for modification, modified in constrained:
                modifications.append(modification)
                nodes[modification.id] = (modified, count_subject)
                jobs.append(self.count_job(modified, count_subject, limit))
        for modification in link_modifications:
            jobs.append(lambda m=modification: self.guarded(self.details, m))

        results = run_bounded(jobs, self.config.parallelism, self.config.timeout)
        base_count = results.pop(0) if graph.subjects else None
        for i, modification in enumerate(modifications):
            modification.count = results[i]
        for i, modification in enumerate(link_modifications):
            modification.details = results[len(modifications) + i]
        result = ProgressiveResult(
            base_count=base_count,
            modifications=modifications,
            candidate_count=len(candidates),
            count_limit=limit,
            count_subject=count_subject,
            seed=seed,
            constraint_candidate_count=constraint_candidate_count,
            failed_constraints=failed,
        )
        if request.depth > 1:
            self.expand_tree(request, result, nodes, constraints)
        result.query_count = self.queries.count
        return result

    # --- tree expansion ---

    def expand_tree(
        self,
        request: ProgressiveRequest,
        result: ProgressiveResult,
        nodes: dict[str, tuple[QueryGraph, str]],
        constraints: bool,
    ):
        """Adds the levels 2..request.depth to ``result`` (see the module docstring);
        ``nodes``: graph and counted subject of the first level's modifications."""
        config = self.config
        branching = min(request.branching or config.default_branching, config.max_branching)
        size = min(request.child_sample_size or config.child_sample_size, config.max_sample_size)
        constraint_size = request.child_constraint_sample_size
        constraint_size = config.child_constraint_sample_size if constraint_size is None else constraint_size
        child_request = request.model_copy(update={"constraint_sample_size": constraint_size})
        limit = result.count_limit
        budget = QueryBudget(config.max_total_queries, self.queries)
        result.query_budget = budget.limit

        base_ids = graph_ids(request.graph)
        seen = {graph_key(graph, base_ids) for graph, _ in nodes.values()}
        level = result.modifications
        for depth in range(2, request.depth + 1):
            parents = select_expansions(level, branching, limit, f"{result.seed}:expand:{depth}")
            children: list[ProgressiveModification] = []
            jobs: list[Callable] = []
            for parent in parents:
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
                    budget.reserved += 1
                    own.append((child, modified))
                result.expanded_ids.append(parent.id)
                for child, modified in own:
                    child.step_operations = child.operations
                    child.operations = parent.operations + child.operations
                    child.id = f"{parent.id} > {child.id}"
                    child.parent_id = parent.id
                    child.depth = depth
                    nodes[child.id] = (modified, counted)
                    children.append(child)
                    jobs.append(self.count_job(modified, counted, limit))
            # the children's details cover all their (cumulative) operations
            jobs += [lambda m=child: self.guarded(self.details, m) for child in children]
            results = run_bounded(jobs, config.parallelism, config.timeout)
            budget.reserved = 0
            for i, child in enumerate(children):
                child.count = results[i]
                child.details = results[len(children) + i]
            if not children:
                break
            result.modifications += children
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
    ) -> tuple[list[tuple[ProgressiveModification, QueryGraph]], list[str], int]:
        """Constraint modifications (uncounted) of a sample of the constrained properties,
        the keys of the candidates whose distribution failed, and the number of candidates.

        With a ``budget``, a round tries only as many candidates as their distributions can
        cost at most (3 queries of a numeric/date property, see value_distribution).
        """
        config = self.config
        size = request.constraint_sample_size
        size = min(config.constraint_sample_size if size is None else size, config.max_constraint_sample_size)
        percentiles = request.numeric_percentiles if request.numeric_percentiles is not None else config.numeric_percentiles
        # sorted and unique, so equal settings give equal modifications
        percentiles = sorted(set(percentiles))
        categorical_samples = request.categorical_samples or config.categorical_samples

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
                    allowance -= 3 if candidate.value_kind in ORDERED_KINDS else 1
                    if allowance < 0:
                        break
                    affordable += 1
                batch = batch[:affordable]
            if not batch:
                break
            tried += len(batch)
            # two queries per distribution if its values exceed max_numeric_values
            distributions = run_bounded(
                [lambda c=c: self.value_distribution(graph, c, count_subject, percentiles) for c in batch],
                config.parallelism,
                2 * config.timeout,
            )
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


def cache_key(request: ProgressiveRequest) -> str:
    return "progressive:" + hashlib.sha256(request.model_dump_json().encode()).hexdigest()


def complete(result: ProgressiveResult) -> bool:
    """Whether every count and lookup succeeded, only then a result is worth caching."""
    counts = [m.count for m in result.modifications]
    if result.count_subject is not None:
        # an empty graph has no base count
        counts.append(result.base_count)
    return (
        all(c is not None for c in counts)
        and all(m.details is not None for m in result.modifications)
        and not result.failed_constraints
    )
