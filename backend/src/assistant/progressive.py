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

Counts are of the distinct bindings of the counted subject (the request's
``count_subject``, by default the first subject of the graph), capped at
``count_limit`` (a count equal to the limit is a lower bound). Similarity
links and vector sorts are dropped before counting (the tensorIndex SERVICE is
too costly per candidate), so their restrictions are not counted. Counts that
fail (invalid graph, endpoint error) or exceed the per-query timeout are None.

All counts (and the ontology details of the sampled candidates) run
concurrently on a bounded thread pool, see run_bounded.

Timeouts, parallelism and the sample/count caps are per configuration, the
``progressive`` object of backend/config.json (eval_config.ProgressiveConfig).
"""

from __future__ import annotations

import hashlib
import random
import re
import threading
import time
from contextlib import nullcontext
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, TypeVar

import httpx
from pydantic import BaseModel, Field
from rdflib import URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLStore

from agent.protocol import GraphDetails
from assistant.assistant_model import (
    AssistantLink,
    AssistantSubject,
    AssistantSubQueryType,
    LinkSemanticType,
    Operation,
    OperationType,
    QueryGraph,
)
from assistant.sparql_gen import SparqlOptions
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


class ProgressiveModification(BaseModel):
    id: str
    # operations applied to the request graph (add subjects, links)
    operations: list[Operation] = Field([])
    # count of the modified graph, None if it failed or timed out
    count: int | None = None
    label: str
    description: str | None = None
    # ontology data of the added subjects/links keyed by graph id (as the agent sends it)
    details: GraphDetails | None = None


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


# --- counting ---

# count of a SPARQL query (with a single ?count binding) within a timeout in seconds
CountRunner = Callable[[str, float], int]


def endpoint_counter(endpoint: str, count_var: str = "count", server_timeout: bool = True) -> CountRunner:
    """Counts by POSTing to a SPARQL endpoint (as the SPARQLStore does), with timeouts."""

    def run(query: str, timeout: float) -> int:
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
        bindings = response.json()["results"]["bindings"]
        return int(bindings[0][count_var]["value"]) if bindings else 0

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


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "subject"


def default_seed(request: ProgressiveRequest) -> int:
    """Seed derived from the graph and sampling parameters, stable across processes."""
    key = request.model_dump_json(include={"graph", "subject_ids", "sample_size"})
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")


class ProgressiveSampler:
    def __init__(
        self,
        ontology_manager: "OntologyManager",
        config: ProgressiveConfig | None = None,
        run_count: CountRunner | None = None,
    ):
        self.ontology = ontology_manager
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
        # per class / URI, the ontology does not change while the server runs
        self._properties: dict[str, list[tuple[str, str | None]]] = {}
        self._subjects: dict[str, Subject] = {}
        self._labels: dict[str, str] = {}

    # --- ontology lookups (cached) ---

    def outgoing(self, cls: str) -> list[tuple[str, str | None]]:
        if cls not in self._properties:
            self._properties[cls] = self.ontology.outgoing_properties(cls)
        return self._properties[cls]

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

    # --- modifications ---

    def modification(
        self, graph: QueryGraph, candidate: Candidate, taken: set[str]
    ) -> tuple[ProgressiveModification, QueryGraph]:
        """The modification of a candidate (ids unique among ``taken``, which is updated) and the modified graph."""

        def new_id(label: str) -> str:
            base, i = slug(label), 1
            while f"{base}_{i}" in taken:
                i += 1
            taken.add(f"{base}_{i}")
            return f"{base}_{i}"

        modified = graph.model_copy(deep=True)
        target_label = self.label(candidate.target_uri) if candidate.target_uri else "thing"
        target = AssistantSubject(uri=candidate.target_uri, label=target_label, id=new_id(target_label))
        modified.add_subject(target)
        operations = [Operation(operation=OperationType.ADD, data=target)]
        if candidate.from_id is None:
            return (
                ProgressiveModification(
                    id=candidate.key,
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
        with self._local_lock:
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

    def sample(self, request: ProgressiveRequest) -> ProgressiveResult:
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
        taken = {s.id for s in graph.subjects} | {l.id for l in graph.links}
        modifications: list[ProgressiveModification] = []
        jobs: list[Callable] = []
        if graph.subjects:
            jobs.append(self.count_job(graph, count_subject, limit))
        for candidate in sampled:
            modification, modified = self.modification(graph, candidate, taken)
            modifications.append(modification)
            # a starting point counts its own subject
            counted = count_subject if count_subject is not None else modification.operations[0].data.id
            jobs.append(self.count_job(modified, counted, limit))
        for modification in modifications:
            jobs.append(lambda m=modification: self.guarded(self.details, m))

        results = run_bounded(jobs, self.config.parallelism, self.config.timeout)
        base_count = results.pop(0) if graph.subjects else None
        for i, modification in enumerate(modifications):
            modification.count = results[i]
            modification.details = results[len(modifications) + i]
        return ProgressiveResult(
            base_count=base_count,
            modifications=modifications,
            candidate_count=len(candidates),
            count_limit=limit,
            count_subject=count_subject,
            seed=seed,
        )


def cache_key(request: ProgressiveRequest) -> str:
    return "progressive:" + hashlib.sha256(request.model_dump_json().encode()).hexdigest()


def complete(result: ProgressiveResult) -> bool:
    """Whether every count and lookup succeeded, only then a result is worth caching."""
    counts = [m.count for m in result.modifications]
    if result.count_subject is not None:
        # an empty graph has no base count
        counts.append(result.base_count)
    return all(c is not None for c in counts) and all(m.details is not None for m in result.modifications)
