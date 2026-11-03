"""Query runners of progressive discovery: counts and result rows of SPARQL queries,
on an endpoint (with timeouts) or through the OntologyManager, and the counted graph."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import httpx
from rdflib import Literal as RDFLiteral, URIRef

from assistant.assistant_model import AssistantSubQueryType, LinkSemanticType, QueryGraph

if TYPE_CHECKING:
    from ontology import OntologyManager

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
        if isinstance(term, RDFLiteral):
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
