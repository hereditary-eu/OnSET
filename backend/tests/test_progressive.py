"""assistant/progressive.py: candidates, sampling and counts on the in-memory ontology, and the endpoint."""

import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from assistant.assistant_model import (
    AssistantLink,
    AssistantSubject,
    LinkQuantifier,
    LinkSemanticType,
    OperationType,
    QueryGraph,
    VectorSortSubQuery,
)
from assistant.progressive import (
    ProgressiveRequest,
    ProgressiveResult,
    ProgressiveSampler,
    complete,
    counted_graph,
    endpoint_counter,
    run_bounded,
)

from eval_config import EvalConfig, ProgressiveConfig
from fakes import ONTOLOGY_TTL, dbo, make_ontology

# many properties of a class, for sampling; dbo:anything has no range, dbo:owner owl:Thing
WIDE_TTL = (
    ONTOLOGY_TTL
    + "\n".join(
        f'dbo:prop{i} a owl:ObjectProperty ; rdfs:label "prop {i}"@en ; rdfs:domain dbo:Person ; rdfs:range dbo:Place .'
        for i in range(20)
    )
    + """
dbo:anything a rdf:Property ; rdfs:label "anything"@en ; rdfs:domain dbo:Ship .
dbo:owner a owl:ObjectProperty ; rdfs:label "owner"@en ; rdfs:domain dbo:Vehicle ; rdfs:range owl:Thing .
dbo:name a rdf:Property ; rdfs:domain dbo:Ship ; rdfs:range rdfs:Literal .
dbr:Bounty dbo:anything dbr:Bligh ; dbo:owner dbr:Bligh .
"""
)


def ship(id="ship", uri=None):
    return AssistantSubject(id=id, uri=dbo("Ship") if uri is None else uri, label="ship")


def ship_graph(*links: tuple[str, str]) -> QueryGraph:
    """A ship linked to a new subject per (property, class) in ``links``."""
    graph = QueryGraph(subjects=[ship()])
    for i, (prop, cls) in enumerate(links):
        graph.subjects.append(AssistantSubject(id=f"t{i}", uri=dbo(cls), label=cls.lower()))
        graph.links.append(
            AssistantLink(id=f"l{i}", uri=dbo(prop), label=prop, from_subject_id="ship", to_subject_id=f"t{i}")
        )
    return graph


@pytest.fixture
def sampler(ontology):
    return ProgressiveSampler(ontology)


@pytest.fixture
def wide():
    return ProgressiveSampler(make_ontology(WIDE_TTL))


def by_label(result: ProgressiveResult) -> dict:
    return {m.label: m.count for m in result.modifications}


# --- candidates ---


def test_candidates_are_outgoing_object_properties(sampler):
    # length is a datatype property, no candidate
    candidates = sampler.candidates(ship_graph())
    assert sorted((c.from_id, c.prop, c.target_uri) for c in candidates) == [
        ("ship", dbo("commander"), dbo("Person")),
        ("ship", dbo("homeport"), dbo("Country")),
    ]


def test_candidates_inherited_filtered_and_untyped(wide):
    # domain of a parent class (Vehicle) and properties without/with owl:Thing range: untyped targets
    warship = QueryGraph(subjects=[ship(uri=dbo("Warship"))])
    targets = {c.prop: c.target_uri for c in wide.candidates(warship)}
    assert targets == {
        dbo("homeport"): dbo("Country"),
        dbo("commander"): dbo("Person"),
        dbo("anything"): "",
        dbo("owner"): "",
    }
    # already linked properties are left out
    assert dbo("homeport") not in {c.prop for c in wide.candidates(ship_graph(("homeport", "Country")))}
    # subject filter and untyped subjects (no domain)
    graph = ship_graph(("homeport", "Country"))
    assert {c.from_id for c in wide.candidates(graph)} == {"ship"}
    assert wide.candidates(graph, subject_ids=["t0"]) == []
    assert wide.candidates(QueryGraph(subjects=[ship(uri="")])) == []


def test_empty_graph_starts_from_root_classes(sampler):
    result = sampler.sample(ProgressiveRequest(graph=QueryGraph(), sample_size=10))
    assert result.base_count is None and result.count_subject is None
    assert result.candidate_count == 3
    assert by_label(result) == {"person": 1, "place": 0, "vehicle": 0}
    for modification in result.modifications:
        (operation,) = modification.operations
        assert operation.operation == OperationType.ADD
        assert isinstance(operation.data, AssistantSubject)
        assert modification.details.subjects[operation.data.id].label == modification.label


def test_root_classes_fall_back_to_owl_thing_subclasses():
    # as in DBpedia, every class has a parent, so parent_class_query finds none
    roots = ("Vehicle", "Place", "Person")
    om = make_ontology(ONTOLOGY_TTL + "".join(f"\ndbo:{c} rdfs:subClassOf owl:Thing ." for c in roots))
    assert om.q_to_df(om.config.parent_class_query).empty
    assert set(ProgressiveSampler(om).root_classes()) == {dbo(c) for c in roots}


# --- sampling ---


def test_sampling_is_seeded(wide):
    person = QueryGraph(subjects=[AssistantSubject(id="p", uri=dbo("Person"), label="person")])

    def sample(**kwargs):
        result = wide.sample(ProgressiveRequest(graph=person, sample_size=5, **kwargs))
        assert result.candidate_count == 20 and len(result.modifications) == 5
        return [m.id for m in result.modifications]

    assert sample(seed=1) == sample(seed=1)
    assert len({tuple(sample(seed=s)) for s in range(5)}) > 1
    # without a seed, one is derived from the graph: stable as well
    assert sample() == sample()
    assert wide.sample(ProgressiveRequest(graph=person, sample_size=1)).seed is not None


def test_modification_ids_unique(wide):
    # every modification adds a subject named after its range: ids must not collide
    graph = QueryGraph(subjects=[AssistantSubject(id="place_1", uri=dbo("Person"), label="person")])
    result = wide.sample(ProgressiveRequest(graph=graph, sample_size=20))
    ids = [op.data.id for m in result.modifications for op in m.operations]
    assert len(ids) == len(set(ids)) == 40 and "place_1" not in ids
    for modification in result.modifications:
        subject, link = (op.data for op in modification.operations)
        assert (link.from_subject_id, link.to_subject_id) == ("place_1", subject.id)
        assert modification.details.links[link.id].property_id == link.uri
        assert modification.details.subjects[subject.id].subject_id == dbo("Place")


# --- counts ---


def test_counts(sampler):
    result = sampler.sample(ProgressiveRequest(graph=ship_graph(), sample_size=10))
    assert (result.base_count, result.count_subject, result.candidate_count) == (2, "ship", 2)
    assert by_label(result) == {"ship → homeport → country": 2, "ship → commander → person": 0}
    assert complete(result)
    # the modifications apply to the request graph
    homeport = next(m for m in result.modifications if "homeport" in m.label)
    graph = ship_graph()
    for op in homeport.operations:
        (graph.add_subject if isinstance(op.data, AssistantSubject) else graph.add_link)(op.data)
    assert graph.links[0].from_subject_id == "ship"


def test_counts_untyped_and_capped(wide):
    result = wide.sample(ProgressiveRequest(graph=ship_graph(), sample_size=10, count_limit=1))
    assert result.count_limit == 1 and result.base_count == 1
    counts = by_label(result)
    assert counts["ship → anything → thing"] == 1
    assert counts["ship → commander → person"] == 0
    # uncapped
    result = wide.sample(ProgressiveRequest(graph=ship_graph(), sample_size=10))
    assert by_label(result)["ship → owner → thing"] == 1 and result.base_count == 2


def test_count_subject(sampler):
    graph = ship_graph(("homeport", "Country"))
    result = sampler.sample(ProgressiveRequest(graph=graph, sample_size=10, count_subject="t0"))
    # both ships share one homeport
    assert result.base_count == 1 and result.count_subject == "t0"
    with pytest.raises(ValueError, match="count_subject"):
        sampler.sample(ProgressiveRequest(graph=graph, count_subject="nope"))


def test_similarity_links_and_vector_sorts_not_counted():
    graph = ship_graph(("homeport", "Country"))
    graph.links.append(
        AssistantLink(
            id="sim", uri=dbo("thumbnail_embedding"), label="similar",
            from_subject_id="ship", to_subject_id="t0", semantic_link_type=LinkSemanticType.SIMILARITY,
        )
    )
    graph.subjects[0].subqueries = [VectorSortSubQuery(id="v", vector=[1.0])]
    counted = counted_graph(graph)
    assert [l.id for l in counted.links] == ["l0"] and counted.subjects[0].subqueries == []
    # the request graph is not changed
    assert len(graph.links) == 2 and graph.subjects[0].subqueries


def test_failed_counts_are_none(ontology):
    def run_count(query, timeout):
        if "commander" in query:
            raise RuntimeError("endpoint down")
        return 7

    sampler = ProgressiveSampler(ontology, run_count=run_count)
    result = sampler.sample(ProgressiveRequest(graph=ship_graph(), sample_size=10))
    assert result.base_count == 7
    assert by_label(result) == {"ship → homeport → country": 7, "ship → commander → person": None}
    assert not complete(result)

    # an invalid graph (EXACTLY without bound) cannot be counted at all
    graph = ship_graph(("homeport", "Country"))
    graph.links[0].quantifier = LinkQuantifier(type="EXACTLY")
    result = sampler.sample(ProgressiveRequest(graph=graph, sample_size=10))
    assert result.base_count is None and all(m.count is None for m in result.modifications)


def test_timed_out_counts_are_none(ontology):
    release = threading.Event()

    def run_count(query, timeout):
        if "commander" in query:
            # blocks until the test is done, far beyond the timeout
            release.wait(30)
        return 3

    config = ProgressiveConfig(timeout=1, parallelism=2)
    sampler = ProgressiveSampler(ontology, config=config, run_count=run_count)
    start = time.monotonic()
    try:
        result = sampler.sample(ProgressiveRequest(graph=ship_graph(), sample_size=10))
    finally:
        release.set()
    # the blocked count is given up after its timeout (generous bound for slow machines)
    assert time.monotonic() - start < 10
    assert by_label(result) == {"ship → homeport → country": 3, "ship → commander → person": None}


def test_run_bounded():
    active, peak = [0], [0]
    lock = threading.Lock()
    release = threading.Event()

    def job(i):
        def run():
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1
            if i == 3:
                raise ValueError("boom")
            if i == 4:
                # blocks far beyond the timeout, until the test is done
                release.wait(30)
            return i

        return run

    start = time.monotonic()
    try:
        results = run_bounded([job(i) for i in range(8)], parallelism=3, timeout=1)
    finally:
        release.set()
    assert results == [0, 1, 2, None, None, 5, 6, 7]
    # the blocked job is given up after its timeout (generous bound for slow machines)
    assert peak[0] <= 3 and time.monotonic() - start < 10
    assert run_bounded([], 2, 1) == []


def test_endpoint_counter(monkeypatch):
    calls = []

    def post(url, data, headers, timeout):
        calls.append(dict(data))
        if "timeout" in data and len(calls) == 1:
            return httpx.Response(400, request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            json={"head": {"vars": ["count"]}, "results": {"bindings": [{"count": {"type": "literal", "value": "42"}}]}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    run = endpoint_counter("http://sparql.invalid")
    # an endpoint rejecting the timeout parameter is retried without it
    assert run("SELECT ...", 2.4) == 42
    assert calls == [{"query": "SELECT ...", "timeout": "2s"}, {"query": "SELECT ..."}]
    assert run("SELECT ...", 2) == 42 and calls[-1]["timeout"] == "2s"


def test_sampler_uses_config(ontology):
    """ManMan builds the sampler from the configuration's ``progressive`` settings."""
    from api.config import ManMan

    config = EvalConfig(progressive={"default_sample_size": 3, "max_sample_size": 5, "count_limit": 7})
    manman = SimpleNamespace(ontology_manager=make_ontology(WIDE_TTL), db_config=config)
    sampler = ManMan.progressive.func(manman)
    assert sampler.config is config.progressive
    person = QueryGraph(subjects=[AssistantSubject(id="p", uri=dbo("Person"), label="person")])
    # without a sample size the configured default, a larger one is capped
    assert len(sampler.sample(ProgressiveRequest(graph=person)).modifications) == 3
    result = sampler.sample(ProgressiveRequest(graph=person, sample_size=50))
    assert len(result.modifications) == 5 and result.count_limit == 7
    assert sampler.sample(ProgressiveRequest(graph=person, sample_size=2, count_limit=9)).count_limit == 9


# --- endpoint ---


def test_sample_endpoint(client, fake_manman):
    body = {"graph": ship_graph().model_dump(), "sample_size": 10, "seed": 3}
    response = client.post("/dbpedia/progressive/sample", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["base_count"] == 2 and result["seed"] == 3
    assert {m["label"]: m["count"] for m in result["modifications"]} == {
        "ship → homeport → country": 2,
        "ship → commander → person": 0,
    }
    modification = result["modifications"][0]
    assert [op["operation"] for op in modification["operations"]] == ["add", "add"]
    link = modification["operations"][1]["data"]
    assert link["id"] in modification["details"]["links"]
    # complete results are cached
    (key,) = fake_manman.progressive_cache.data
    assert key.startswith("dbpedia:progressive:")
    fake_manman.progressive = None  # a second request must not sample again
    assert client.post("/dbpedia/progressive/sample", json=body).json() == result


def test_sample_endpoint_errors(client):
    response = client.post(
        "/dbpedia/progressive/sample", json={"graph": ship_graph().model_dump(), "count_subject": "nope"}
    )
    assert response.status_code == 422 and "count_subject" in response.json()["detail"]
    assert client.post("/dbpedia/progressive/sample", json={"graph": {}, "sample_size": 0}).status_code == 422
