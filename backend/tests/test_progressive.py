"""assistant/progressive/: candidates, sampling and counts on the in-memory ontology, and the endpoint."""

import json
import random
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from assistant.assistant_model import (
    AssistantLink,
    AssistantSubject,
    BooleanSubQuery,
    LinkQuantifier,
    LinkSemanticType,
    NumberSubQuery,
    OperationType,
    QueryGraph,
    QueryPropSubQuery,
    StringSubQuery,
    SubjectSubQuery,
    VectorSortSubQuery,
)
from assistant.progressive import (
    CancelToken,
    JobPool,
    SamplingCancelled,
    ModificationKind,
    ProgressiveRequest,
    ProgressiveResult,
    ProgressiveSampler,
    Term,
    ProgressiveModification,
    complete,
    counted_graph,
    endpoint_counter,
    endpoint_selector,
    graph_key,
    ontology_counter,
    ontology_selector,
    run_bounded,
    select_expansions,
    weighted_percentiles,
    weighted_sample,
)

from eval_config import EvalConfig, ProgressiveConfig
from fakes import ONTOLOGY_TTL, dbo, make_ontology, make_sampler, schema_of

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
    return make_sampler(ontology)


@pytest.fixture
def wide():
    return make_sampler(make_ontology(WIDE_TTL))


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
    # domain of a parent class (Vehicle) and a property with owl:Thing range: untyped target;
    # dbo:anything has no range, the stored schema has no row of it
    warship = QueryGraph(subjects=[ship(uri=dbo("Warship"))])
    targets = {c.prop: c.target_uri for c in wide.candidates(warship)}
    assert targets == {
        dbo("homeport"): dbo("Country"),
        dbo("commander"): dbo("Person"),
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
    assert set(make_sampler(om).root_classes()) == {dbo(c) for c in roots}


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
        # the details carry the stored ids (prefixed), the graph the wrapped IRIs
        key = wide.schema.key
        assert key(modification.details.links[link.id].property_id) == key(link.uri)
        assert key(modification.details.subjects[subject.id].subject_id) == key(dbo("Place"))


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
    assert counts["ship → owner → thing"] == 1
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

    sampler = make_sampler(ontology, run_count=run_count)
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
    sampler = make_sampler(ontology, config=config, run_count=run_count)
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
    ontology = make_ontology(WIDE_TTL)
    guidance = SimpleNamespace(schema_index=lambda: schema_of(ontology))
    manman = SimpleNamespace(ontology_manager=ontology, db_config=config, guidance_man=guidance)
    sampler = ManMan.progressive.func(manman)
    assert sampler.config is config.progressive
    # schema lookups from the stored schema
    assert sampler._schema_source == guidance.schema_index
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


# --- constraints ---

# ships s0..s9 with homeports (England 6, France 3, Spain 1), lengths 10..100, launch
# dates 1900..1909, a class and whether they are in service; two "Enterprise" without
# homeport and far longer; no ship has a draft
FLEET_TTL = (
    """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix dbr: <http://dbpedia.org/resource/> .

dbo:Ship a owl:Class ; rdfs:label "ship"@en .
dbo:Country a owl:Class ; rdfs:label "country"@en .
dbo:homeport a owl:ObjectProperty ; rdfs:label "homeport"@en ; rdfs:domain dbo:Ship ; rdfs:range dbo:Country .
dbo:length a owl:DatatypeProperty ; rdfs:label "length"@en ; rdfs:domain dbo:Ship ; rdfs:range xsd:double .
dbo:shipLaunch a owl:DatatypeProperty ; rdfs:label "ship launch"@en ; rdfs:domain dbo:Ship ; rdfs:range xsd:date .
dbo:inService a owl:DatatypeProperty ; rdfs:label "in service"@en ; rdfs:domain dbo:Ship ; rdfs:range xsd:boolean .
dbo:shipClass a rdf:Property ; rdfs:label "ship class"@en ; rdfs:domain dbo:Ship ; rdfs:range xsd:string .
dbo:modelStartYear a owl:DatatypeProperty ; rdfs:domain dbo:Ship ; rdfs:range xsd:gYear .
dbo:draft a owl:DatatypeProperty ; rdfs:label "draft"@en ; rdfs:domain dbo:Ship ; rdfs:range xsd:double .
dbr:England a dbo:Country ; rdfs:label "England"@en .
dbr:France a dbo:Country ; rdfs:label "France"@en .
dbr:Spain a dbo:Country ; rdfs:label "Spain"@en .
dbr:e1 a dbo:Ship ; rdfs:label "Enterprise"@en ; dbo:length "1000"^^xsd:double .
dbr:e2 a dbo:Ship ; rdfs:label "Enterprise"@en ; dbo:length "2000"^^xsd:double .
"""
    + "\n".join(
        f'dbr:s{i} a dbo:Ship ; rdfs:label "Ship {i}"@en ; dbo:length "{10 * (i + 1)}"^^xsd:double ; '
        f'dbo:homeport dbr:{"England" if i < 6 else "France" if i < 9 else "Spain"} ; '
        f'dbo:shipLaunch "{1900 + i}-01-01"^^xsd:date ; dbo:inService {"true" if i < 7 else "false"} ; '
        f'dbo:shipClass "{"Frigate" if i < 5 else "Sloop" if i < 8 else f"Unique {i}"}" ; dbo:modelStartYear "1899"^^xsd:gYear .'
        for i in range(10)
    )
)


@pytest.fixture
def fleet():
    return make_sampler(make_ontology(FLEET_TTL))


def homeport_graph() -> QueryGraph:
    return ship_graph(("homeport", "Country"))


def constraints(sampler, graph, **kwargs) -> ProgressiveResult:
    kwargs = {"sample_size": 1, "seed": 1, "sample_constraints": True, "constraint_sample_size": 64, **kwargs}
    return sampler.sample(ProgressiveRequest(graph=graph, **kwargs))


def constrained(result: ProgressiveResult, prop: str | None = None) -> dict:
    """label -> count of the constraint modifications (of a property, None: of instances)."""
    return {
        m.label: m.count
        for m in result.modifications
        if m.kind == ModificationKind.CONSTRAINT and m.constraint.property_id == (dbo(prop) if prop else None)
    }


def test_constraint_candidates(fleet):
    kinds = {(c.subject_id, c.prop, c.value_kind) for c in fleet.constraint_candidates(homeport_graph(), "ship")}
    # gYear is no number/date; the counted ship: its label, the other subject: its instance
    assert kinds == {
        ("ship", "rdfs:label", "label"),
        ("ship", dbo("length"), "number"),
        ("ship", dbo("shipLaunch"), "date"),
        ("ship", dbo("inService"), "boolean"),
        ("ship", dbo("shipClass"), "string"),
        ("ship", dbo("draft"), "number"),
        ("t0", None, "instance"),
    }
    # constrained properties/instances and the subject filter are left out
    graph = homeport_graph()
    graph.subjects[0].subqueries = [NumberSubQuery(id="n", property_id=dbo("length"), value=1)]
    graph.subjects[1].subqueries = [SubjectSubQuery(id="i", instance_id="<http://dbpedia.org/resource/England>")]
    kinds = {(c.subject_id, c.prop) for c in fleet.constraint_candidates(graph, "ship")}
    assert ("ship", dbo("length")) not in kinds and ("t0", None) not in kinds
    assert {c.subject_id for c in fleet.constraint_candidates(graph, "ship", subject_ids=["t0"])} == set()


def test_percentiles_in_graph_context(fleet):
    # the ships with a homeport have lengths 10..100 (the Enterprises are not in the context)
    result = constraints(fleet, homeport_graph())
    assert result.base_count == 10
    assert constrained(result, "length") == {
        "ship: length < 10 (p10)": 0,
        "ship: length < 30 (p25)": 2,
        "ship: length > 50 (p50)": 5,
        "ship: length > 80 (p75)": 2,
        "ship: length > 90 (p90)": 1,
    }
    # all ships: 12 values, the upper percentiles are the Enterprises'
    result = constraints(fleet, ship_graph())
    assert constrained(result, "length")["ship: length > 1000 (p90)"] == 1
    modification = next(m for m in result.modifications if m.label == "ship: length > 1000 (p90)")
    (operation,) = modification.operations
    assert operation.subject_id == "ship" and isinstance(operation.data, NumberSubQuery)
    assert (operation.data.operator, operation.data.value, operation.data.property_type) == ("greater", 1000, "xsd:double")
    assert modification.constraint.kind == "percentile" and modification.constraint.percentile == 90
    # dates the same way, custom percentiles
    result = constraints(fleet, homeport_graph(), numeric_percentiles=[50, 0])
    assert constrained(result, "shipLaunch") == {
        "ship: ship launch < 1900-01-01 (p0)": 0,
        "ship: ship launch > 1904-01-01 (p50)": 5,
    }


def test_percentiles_of_many_values_by_rank():
    # more distinct values than max_numeric_values: OFFSET queries, same percentiles
    sampler = make_sampler(make_ontology(FLEET_TTL), config=ProgressiveConfig(max_numeric_values=3))
    queries = []
    run_select = sampler.run_select
    sampler.run_select = lambda query, timeout: queries.append(query) or run_select(query, timeout)
    result = constraints(sampler, homeport_graph())
    assert set(constrained(result, "length")) == {
        "ship: length < 10 (p10)", "ship: length < 30 (p25)", "ship: length > 50 (p50)",
        "ship: length > 80 (p75)", "ship: length > 90 (p90)",
    }
    assert any("OFFSET 7" in q and "UNION" in q for q in queries)


def test_categories_respect_distribution(fleet):
    # instances of the homeport: England 6, France 3; Spain (1) is below min_category_count
    def picks(seed, k=1):
        # the country only: its instance is the one candidate
        result = constraints(fleet, homeport_graph(), categorical_samples=k, seed=seed, subject_ids=["t0"])
        return list(constrained(result))

    assert picks(3) == picks(3)
    counts = {}
    for seed in range(60):
        (label,) = picks(seed)
        counts[label] = counts.get(label, 0) + 1
    assert set(counts) == {"country: = England", "country: = France"}
    assert counts["country: = England"] > counts["country: = France"]
    result = constraints(fleet, homeport_graph(), categorical_samples=3)
    assert constrained(result) == {"country: = England": 6, "country: = France": 3}
    england = next(m for m in result.modifications if m.label == "country: = England")
    (operation,) = england.operations
    assert operation.subject_id == "t0" and isinstance(operation.data, SubjectSubQuery)
    assert operation.data.instance_id == "<http://dbpedia.org/resource/England>"
    assert (england.constraint.kind, england.constraint.frequency) == ("category", 6)


def test_string_boolean_and_label_categories(fleet):
    result = constraints(fleet, homeport_graph())
    # unique classes are no categories
    assert constrained(result, "shipClass") == {'ship: ship class = "Frigate"': 5, 'ship: ship class = "Sloop"': 3}
    assert constrained(result, "inService") == {"ship: in service = true": 7, "ship: in service = false": 3}
    string = next(m for m in result.modifications if "Frigate" in m.label).operations[0].data
    assert isinstance(string, StringSubQuery) and string.operator == "equals"
    assert isinstance(next(m for m in result.modifications if "in service" in m.label).operations[0].data, BooleanSubQuery)
    # ship names repeat only among all ships
    assert not [m for m in result.modifications if m.constraint and m.constraint.property_id == "rdfs:label"]
    result = constraints(fleet, ship_graph())
    assert {m.label: m.count for m in result.modifications if m.constraint and m.constraint.property_id == "rdfs:label"} == {
        'ship: label = "Enterprise"': 2
    }


def test_constraint_operations_apply(fleet):
    graph = homeport_graph()
    graph.subjects[0].subqueries = [QueryPropSubQuery(id="length_1", property_id=dbo("shipClass"))]
    result = constraints(fleet, graph)
    ids = [op.data.id for m in result.modifications for op in m.operations]
    assert len(ids) == len(set(ids)) and "length_1" not in ids
    assert result.constraint_candidate_count == 6 and complete(result)
    for modification in result.modifications:
        if modification.kind != ModificationKind.CONSTRAINT:
            continue
        modified = graph.model_copy(deep=True)
        for operation in modification.operations:
            modified.apply(operation)
        subject = modified.get_subject_by_id(modification.constraint.subject_id)
        assert subject.subqueries[-1].id == modification.operations[0].data.id
        assert modification.details is not None


def test_constraints_off_is_unchanged(fleet):
    graph = homeport_graph()
    plain = fleet.sample(ProgressiveRequest(graph=graph, sample_size=10, seed=2))
    assert plain == fleet.sample(ProgressiveRequest(graph=graph, sample_size=10, seed=2, sample_constraints=False))
    assert plain.constraint_candidate_count is None
    assert all(m.kind == ModificationKind.LINK and m.constraint is None for m in plain.modifications)
    # with constraints, the link sample stays the same
    with_constraints = fleet.sample(ProgressiveRequest(graph=graph, sample_size=10, seed=2, sample_constraints=True))
    links = [m for m in with_constraints.modifications if m.kind == ModificationKind.LINK]
    assert links == plain.modifications
    # sampled properties, by default the configured number of them
    sampled = {m.constraint.property_id for m in with_constraints.modifications if m.constraint}
    assert 0 < len(sampled) <= ProgressiveConfig().constraint_sample_size
    fewer = constraints(fleet, graph, constraint_sample_size=1)
    assert len({m.constraint.property_id for m in fewer.modifications if m.constraint}) <= 1
    # empty graphs have no constraints
    assert constraints(fleet, QueryGraph()).constraint_candidate_count is None


def test_candidates_without_values_are_replaced(fleet):
    # 5 of the 7 candidates have values (not: the unique ship labels, the draft), the
    # sample has those 5 whatever the seed
    for seed in range(4):
        result = constraints(fleet, homeport_graph(), seed=seed, constraint_sample_size=5)
        sampled = {(m.constraint.subject_id, m.constraint.property_id) for m in result.modifications if m.constraint}
        assert sampled == {
            ("ship", dbo("length")), ("ship", dbo("shipLaunch")), ("ship", dbo("inService")),
            ("ship", dbo("shipClass")), ("t0", None),
        }


def test_failed_distributions(fleet):
    def run_select(query, timeout):
        raise RuntimeError("endpoint down")

    fleet.run_select = run_select
    result = constraints(fleet, homeport_graph())
    assert len(result.failed_constraints) == 7 and "t0|instance" in result.failed_constraints
    assert not [m for m in result.modifications if m.constraint] and not complete(result)
    # failed candidates are not replaced by others
    assert len(constraints(fleet, homeport_graph(), constraint_sample_size=2).failed_constraints) == 2


def test_weighted_sample():
    rng = random.Random(0)
    assert weighted_sample(["a", "b", "c"], [1, 0, 1], 5, rng) == ["a", "c"]
    picks = [weighted_sample(["a", "b"], [9, 1], 1, random.Random(s))[0] for s in range(200)]
    assert picks.count("a") > 150


def test_weighted_percentiles():
    values = [(Term(str(v)), w) for v, w in [(3, 1), (1, 2), (2, 1), ("x", 5)]]
    # sorted 1, 1, 2, 3 (x cannot be ordered)
    assert [(p, t.value) for p, t in weighted_percentiles("number", values, [0, 50, 51, 100])] == [
        (0, "1"), (50, "1"), (51, "2"), (100, "3"),
    ]
    dates = [(Term("2001-01-01"), 1), (Term("1999-12-31T10:00:00Z"), 1)]
    assert weighted_percentiles("date", dates, [0])[0][1].value == "1999-12-31T10:00:00Z"


def test_endpoint_selector(monkeypatch):
    def post(url, data, headers, timeout):
        return httpx.Response(
            200,
            json={
                "head": {"vars": ["v", "count"]},
                "results": {"bindings": [
                    {"v": {"type": "uri", "value": "http://x"}, "count": {"type": "literal", "value": "2"}},
                    {"v": {"type": "literal", "value": "a", "xml:lang": "en"}},
                ]},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    assert endpoint_selector("http://sparql.invalid")("SELECT ...", 1) == [
        (Term("http://x", iri=True), Term("2")),
        (Term("a", lang="en"), None),
    ]


def test_sample_endpoint_constraints(client, fake_manman):
    body = {"graph": ship_graph(("homeport", "Country")).model_dump(), "sample_size": 1, "seed": 3,
            "sample_constraints": True, "numeric_percentiles": [50]}
    result = client.post("/dbpedia/progressive/sample", json=body).json()
    instance = next(m for m in result["modifications"] if m["kind"] == "constraint" and m["constraint"]["property_id"] is None)
    # both fake ships have England as homeport
    assert instance["count"] == 2 and instance["label"] == "country: = England"
    assert instance["operations"] == [{
        "operation": "add", "subject_id": "t0",
        "data": {
            "type": "subject", "id": "instance_1", "property_id": None, "property_label": None,
            "property_type": "owl:Thing", "instance_id": "<http://dbpedia.org/resource/England>",
            "instance_label": "England",
        },
    }]
    assert client.post("/dbpedia/progressive/sample", json={**body, "numeric_percentiles": [101]}).status_code == 422


# --- tree expansion ---

# ships s0..s5: homeports England (s0-s3) and France (s4), builders c0 (s0, s1, s4) and
# c1 (s2); capitals, leaders, mayors, locations and a birth place one level further
TREE_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix dbo: <http://dbpedia.org/ontology/> .
@prefix dbr: <http://dbpedia.org/resource/> .

dbo:Ship a owl:Class ; rdfs:label "ship"@en .
dbo:Country a owl:Class ; rdfs:label "country"@en .
dbo:City a owl:Class ; rdfs:label "city"@en .
dbo:Person a owl:Class ; rdfs:label "person"@en .
dbo:Company a owl:Class ; rdfs:label "company"@en .
dbo:homeport a owl:ObjectProperty ; rdfs:label "homeport"@en ; rdfs:domain dbo:Ship ; rdfs:range dbo:Country .
dbo:builder a owl:ObjectProperty ; rdfs:label "builder"@en ; rdfs:domain dbo:Ship ; rdfs:range dbo:Company .
dbo:capital a owl:ObjectProperty ; rdfs:label "capital"@en ; rdfs:domain dbo:Country ; rdfs:range dbo:City .
dbo:leader a owl:ObjectProperty ; rdfs:label "leader"@en ; rdfs:domain dbo:Country ; rdfs:range dbo:Person .
dbo:mayor a owl:ObjectProperty ; rdfs:label "mayor"@en ; rdfs:domain dbo:City ; rdfs:range dbo:Person .
dbo:location a owl:ObjectProperty ; rdfs:label "location"@en ; rdfs:domain dbo:Company ; rdfs:range dbo:City .
dbo:birthPlace a owl:ObjectProperty ; rdfs:label "birth place"@en ; rdfs:domain dbo:Person ; rdfs:range dbo:City .
dbo:length a owl:DatatypeProperty ; rdfs:label "length"@en ; rdfs:domain dbo:Ship ; rdfs:range xsd:double .
dbr:England a dbo:Country ; rdfs:label "England"@en ; dbo:capital dbr:London ; dbo:leader dbr:p0 .
dbr:France a dbo:Country ; rdfs:label "France"@en ; dbo:capital dbr:Paris .
dbr:London a dbo:City ; rdfs:label "London"@en ; dbo:mayor dbr:p1 .
dbr:Paris a dbo:City ; rdfs:label "Paris"@en .
dbr:p0 a dbo:Person ; rdfs:label "Leader"@en ; dbo:birthPlace dbr:London .
dbr:p1 a dbo:Person ; rdfs:label "Mayor"@en .
dbr:c0 a dbo:Company ; rdfs:label "Yard"@en ; dbo:location dbr:London .
dbr:c1 a dbo:Company ; rdfs:label "Chantier"@en ; dbo:location dbr:Paris .
""" + "\n".join(
    f'dbr:s{i} a dbo:Ship ; rdfs:label "Ship {i}"@en ; dbo:length "{10 * (i + 1)}"^^xsd:double'
    + (f' ; dbo:homeport dbr:{"England" if i < 4 else "France"}' if i < 5 else "")
    + (f' ; dbo:builder dbr:{"c1" if i == 2 else "c0"}' if i in (0, 1, 2, 4) else "")
    + " ."
    for i in range(6)
)


@pytest.fixture
def tree():
    return make_sampler(make_ontology(TREE_TTL))


def counting(sampler: ProgressiveSampler) -> list[str]:
    """The endpoint queries (counts and selects) the sampler runs, appended as they run."""
    queries = []
    run_count, run_select = sampler.run_count, sampler.run_select
    sampler.run_count = lambda q, t: queries.append(q) or run_count(q, t)
    sampler.run_select = lambda q, t: queries.append(q) or run_select(q, t)
    return queries


def applied(graph: QueryGraph, modification: ProgressiveModification) -> QueryGraph:
    graph = graph.model_copy(deep=True)
    for operation in modification.operations:
        graph.apply(operation.model_copy(deep=True))
    return graph


def check_tree(sampler: ProgressiveSampler, graph: QueryGraph, result: ProgressiveResult):
    """Parents, cumulative operations, ids and counts (recounted) of a tree result."""
    by_id = {m.id: m for m in result.modifications}
    assert len(by_id) == len(result.modifications)
    keys = set()
    for m in result.modifications:
        if m.depth == 1:
            assert m.parent_id is None and m.step_operations is None
        else:
            parent = by_id[m.parent_id]
            assert m.depth == parent.depth + 1 and parent.id in result.expanded_ids
            assert m.id.startswith(parent.id + " > ")
            assert m.operations == parent.operations + m.step_operations and m.step_operations
        modified = applied(graph, m)
        keys.add(graph_key(modified, {s.id for s in graph.subjects}))
        # the count of the cumulative graph, from the start's subject for an empty graph
        counted = result.count_subject or m.operations[0].data.id
        assert sampler.count_job(modified, counted, result.count_limit)() == m.count, m.id
        # details of every added subject/link
        added = {op.data.id for op in m.operations if isinstance(op.data, (AssistantSubject, AssistantLink))}
        assert added <= set(m.details.subjects) | set(m.details.links)
    # no two modifications give the same graph
    assert len(keys) == len(result.modifications)


SNAPSHOT = Path(__file__).parent / "snapshots" / "progressive_depth1.json"
TREE_FIELDS = {"parent_id", "depth", "step_operations"}
TREE_RESULT_FIELDS = {"depth", "expanded_ids", "duplicate_count", "query_count", "query_budget", "budget_exhausted"}


def depth1_results() -> str:
    """The snapshot's requests sampled again, without the tree fields (see test_depth1_unchanged)."""
    ttls = {"wide": WIDE_TTL, "empty": ONTOLOGY_TTL, "fleet": FLEET_TTL}
    results = {}
    for name, case in json.loads(SNAPSHOT.read_text()).items():
        request = ProgressiveRequest(**case["request"])
        result = make_sampler(make_ontology(ttls[case["ttl"]])).sample(request)
        assert all(m.depth == 1 and m.parent_id is None and m.step_operations is None for m in result.modifications)
        assert (result.depth, result.expanded_ids, result.duplicate_count, result.query_budget) == (1, [], 0, None)
        dumped = result.model_dump(
            mode="json", exclude={"modifications": {"__all__": TREE_FIELDS}, **{f: True for f in TREE_RESULT_FIELDS}}
        )
        results[name] = {**case, "result": dumped}
    return json.dumps(results, indent=1, sort_keys=True)


def test_depth1_unchanged(tmp_path):
    """Depth 1 gives the results of the sampler before the tree expansion byte for byte
    (without the new fields, which keep their defaults): the snapshot was dumped at commit
    b03a2b7, and again with the schema lookups (SchemaIndex), with PYTHONHASHSEED=0, as the in-memory graph orders query results by hash,
    so it is compared in a subprocess with that seed."""
    import os
    import subprocess
    import sys

    tests = Path(__file__).parent
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": os.pathsep.join([str(tests.parent / "src"), str(tests)])}
    out = tmp_path / "depth1.json"
    code = f"import conftest, test_progressive as t; open({str(out)!r}, 'w').write(t.depth1_results())"
    subprocess.run([sys.executable, "-c", code], env=env, check=True, cwd=tests, capture_output=True)
    assert json.loads(out.read_text()) == json.loads(SNAPSHOT.read_text())
    assert out.read_text() == SNAPSHOT.read_text()
    # an explicit depth 1 is the default
    request = ProgressiveRequest(graph=ship_graph(), sample_size=10, seed=2)
    sampler = make_sampler(make_ontology(WIDE_TTL))
    assert sampler.sample(request) == sampler.sample(request.model_copy(update={"depth": 1}))


def test_depth1_ignores_the_budget(tree):
    # the first level is always sampled in full
    sampler = make_sampler(make_ontology(TREE_TTL), config=ProgressiveConfig(max_total_queries=1))
    request = ProgressiveRequest(graph=QueryGraph(subjects=[ship()]), sample_size=10, seed=1)
    assert sampler.sample(request) == tree.sample(request)


def test_tree_depth_2_and_3(tree):
    graph = QueryGraph(subjects=[ship()])
    flat = tree.sample(ProgressiveRequest(graph=graph, sample_size=10, seed=1))
    for depth in (2, 3):
        result = tree.sample(ProgressiveRequest(graph=graph, sample_size=10, seed=1, depth=depth, child_sample_size=10))
        assert result.depth == depth and result.base_count == 6
        check_tree(tree, graph, result)
        # the first level is the depth-1 sample
        assert [m for m in result.modifications if m.depth == 1] == flat.modifications
        assert {m.depth for m in result.modifications} == set(range(1, depth + 1))
    labels = {
        tuple(m.label.split(" → ")[1] for m in path(result, m)): m.count for m in result.modifications
    }
    assert labels[("homeport",)] == 5 and labels[("builder",)] == 4
    # country → capital continues from the subject the parent added
    assert labels[("homeport", "capital")] == 5
    assert labels[("homeport", "capital", "mayor")] == 4
    # homeport then builder is the builder's homeport: one of them is a duplicate
    assert (("homeport", "builder") in labels) != (("builder", "homeport") in labels)
    assert result.duplicate_count > 0


def path(result: ProgressiveResult, modification: ProgressiveModification) -> list[ProgressiveModification]:
    by_id = {m.id: m for m in result.modifications}
    steps = [modification]
    while steps[0].parent_id:
        steps.insert(0, by_id[steps[0].parent_id])
    return steps


def test_tree_from_empty_graph(tree):
    result = tree.sample(ProgressiveRequest(graph=QueryGraph(), sample_size=10, seed=1, depth=2))
    check_tree(tree, QueryGraph(), result)
    assert result.count_subject is None and result.base_count is None
    children = [m for m in result.modifications if m.depth == 2]
    assert children and all(m.kind == ModificationKind.LINK for m in children)
    # links of the started subject, counted from it: ships with a homeport/builder
    ship_children = {m.label: m.count for m in children if m.parent_id == "start|" + dbo("Ship")}
    assert ship_children == {"ship → homeport → country": 5, "ship → builder → company": 4}


def test_tree_with_constraints(fleet):
    graph = homeport_graph()
    result = fleet.sample(ProgressiveRequest(
        graph=graph, sample_size=10, seed=1, depth=2, sample_constraints=True, child_constraint_sample_size=3,
    ))
    check_tree(fleet, graph, result)
    children = [m for m in result.modifications if m.depth == 2]
    assert children and all(m.kind == ModificationKind.CONSTRAINT for m in children)
    # percentiles of a child are in the parent's context: the lengths of 5 English ships
    england = next((m for m in result.modifications if m.label == "country: = England"), None)
    if england and england.id in result.expanded_ids:
        lengths = {m.constraint.value for m in children if m.parent_id == england.id and m.constraint.property_id == dbo("length")}
        assert lengths <= {"10", "20", "30", "40", "50", "60"}
    # no constraint repeats its parent's property
    by_id = {m.id: m for m in result.modifications}
    for child in children:
        parent = by_id[child.parent_id]
        assert (child.constraint.subject_id, child.constraint.property_id) != (parent.constraint.subject_id, parent.constraint.property_id)


def test_tree_is_seeded(tree):
    graph = QueryGraph(subjects=[ship()])

    def ids(**kwargs):
        request = ProgressiveRequest(graph=graph, sample_size=2, depth=3, child_sample_size=1, branching=2, **kwargs)
        return [m.id for m in tree.sample(request).modifications]

    assert ids(seed=1) == ids(seed=1) and ids() == ids()
    assert len({tuple(ids(seed=s)) for s in range(8)}) > 1


def test_select_expansions():
    def mods(*counts):
        return [ProgressiveModification(id=f"m{i}", label=f"m{i}", count=c) for i, c in enumerate(counts)]

    # failed, empty and capped modifications are not expanded
    assert [m.id for m in select_expansions(mods(None, 0, 5, 100, 7), 4, 100, "s")] == ["m2", "m4"]
    # the extremes and the middle of the log range, in the level's order
    level = mods(1, 9, 99, 999, 9999, 3, 5000)
    assert [m.id for m in select_expansions(level, 3, 10**6, "s")] == ["m0", "m2", "m4"]
    assert [m.id for m in select_expansions(level, 1, 10**6, "s")] == ["m2"]
    assert len(select_expansions(level, 7, 10**6, "s")) == 7
    # ties are seeded
    ties = mods(10, 10, 10, 10, 10, 10)
    picks = {tuple(m.id for m in select_expansions(ties, 2, 100, str(seed))) for seed in range(10)}
    assert len(picks) > 1
    assert select_expansions(ties, 2, 100, "x") == select_expansions(ties, 2, 100, "x")


def test_graph_key_ignores_order_and_ids():
    graph = QueryGraph(subjects=[ship()])

    def add(graph, target_id, prop, cls, link_id):
        graph = graph.model_copy(deep=True)
        graph.add_subject(AssistantSubject(id=target_id, uri=dbo(cls), label=cls))
        graph.add_link(AssistantLink(id=link_id, uri=dbo(prop), label=prop, from_subject_id="ship", to_subject_id=target_id))
        return graph

    a_b = add(add(graph, "country_1", "homeport", "Country", "homeport_1"), "company_1", "builder", "Company", "builder_1")
    b_a = add(add(graph, "company_2", "builder", "Company", "builder_2"), "country_3", "homeport", "Country", "homeport_1")
    base = {"ship"}
    assert graph_key(a_b, base) == graph_key(b_a, base)
    assert graph_key(a_b, base) != graph_key(add(graph, "country_1", "homeport", "Country", "h"), base)
    # a subquery counts, its id does not
    a_b.subjects[1].subqueries.append(SubjectSubQuery(id="i1", instance_id="<x>"))
    assert graph_key(a_b, base) != graph_key(b_a, base)
    b_a.subjects[2].subqueries.append(SubjectSubQuery(id="i2", instance_id="<x>"))
    assert graph_key(a_b, base) == graph_key(b_a, base)


def test_tree_budget():
    graph = QueryGraph(subjects=[ship()])
    request = ProgressiveRequest(graph=graph, sample_size=10, seed=1, depth=3, child_sample_size=10)
    full = make_sampler(make_ontology(TREE_TTL))
    queries = counting(full)
    unlimited = full.sample(request)
    assert unlimited.query_count == len(queries) and not unlimited.budget_exhausted
    first_level = 1 + sum(m.depth == 1 for m in unlimited.modifications)
    for budget in (first_level + 2, first_level + 5):
        sampler = make_sampler(make_ontology(TREE_TTL), config=ProgressiveConfig(max_total_queries=budget))
        queries = counting(sampler)
        result = sampler.sample(request)
        assert len(queries) == result.query_count <= budget and result.query_budget == budget
        assert result.budget_exhausted
        assert len(result.modifications) == len(queries) - 1 < len(unlimited.modifications)
        check_tree(sampler, graph, result)
    # with constraints, the value distributions count as well
    fleet_request = ProgressiveRequest(
        graph=homeport_graph(), sample_size=1, seed=1, depth=3, sample_constraints=True, child_constraint_sample_size=4,
    )
    for budget in (30, 45, 60):
        sampler = make_sampler(make_ontology(FLEET_TTL), config=ProgressiveConfig(max_total_queries=budget))
        queries = counting(sampler)
        result = sampler.sample(fleet_request)
        assert len(queries) == result.query_count <= budget
        check_tree(sampler, homeport_graph(), result)


def test_tree_streams_levels(tree):
    events = []
    request = ProgressiveRequest(graph=QueryGraph(subjects=[ship()]), sample_size=10, seed=1, depth=2)
    result = tree.stream(request, emit=events.append)
    assert result == tree.sample(request)
    types = [e.type for e in events]
    assert types[0] == "start" and types[-1] == "done" and types.count("level") == 1
    level = types.index("level")
    # the level starts once every first-level count is in
    first = {m.id for m in events[0].modifications}
    assert {e.id for e in events[:level] if e.type == "count"} == first | {None}
    assert events[level].parent_ids == result.expanded_ids
    # the children of each parent are emitted (then counted) on their own
    batches = [e for e in events if e.type == "modifications"]
    assert [b.parent_id for b in batches] == [p for p in result.expanded_ids if any(m.parent_id == p for m in result.modifications)]
    children = [m.id for b in batches for m in b.modifications]
    assert children == [m.id for m in result.modifications if m.depth == 2]
    assert all(m.count is None for b in batches for m in b.modifications)
    # every modification and the base are counted exactly once, with the result's count
    counts = [(e.id, e.count) for e in events if e.type == "count"]
    assert sorted(counts, key=str) == sorted([(None, result.base_count)] + [(m.id, m.count) for m in result.modifications], key=str)
    done = events[-1]
    assert done.complete and done.depth == 2 and done.query_count == result.query_count and done.base_count == 6


def test_counts_stream_while_distributions_run():
    """The value distributions run besides the counts: a distribution that waits for a
    count finishes (if counts waited for the distributions, it would time out)."""
    sampler = make_sampler(make_ontology(FLEET_TTL), config=ProgressiveConfig(parallelism=4, timeout=5))
    counted = threading.Event()
    run_count, run_select = sampler.run_count, sampler.run_select

    def count(query, timeout):
        try:
            return run_count(query, timeout)
        finally:
            counted.set()

    def select(query, timeout):
        assert counted.wait(4), "no count finished before the distribution"
        return run_select(query, timeout)

    sampler.run_count, sampler.run_select = count, select
    events = []
    result = sampler.stream(
        ProgressiveRequest(graph=homeport_graph(), sample_size=1, seed=1, sample_constraints=True, constraint_sample_size=3),
        emit=events.append,
    )
    assert not result.failed_constraints and [m for m in result.modifications if m.constraint]
    types = [e.type for e in events]
    assert types[0] == "start" and types[-1] == "done"
    # the base count is in before the constraint modifications are known
    assert types.index("count") < types.index("modifications")


def test_stream_cancel():
    sampler = make_sampler(make_ontology(TREE_TTL), config=ProgressiveConfig(parallelism=1, timeout=10))
    gate, calls = threading.Event(), []
    run_count = sampler.run_count

    def count(query, timeout):
        calls.append(query)
        gate.wait(10)
        return run_count(query, timeout)

    sampler.run_count = count
    token, events, outcome = CancelToken(), [], []

    def run():
        try:
            sampler.stream(ProgressiveRequest(graph=QueryGraph(subjects=[ship()]), sample_size=10, seed=1), events.append, token)
        except SamplingCancelled:
            outcome.append("cancelled")

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 5
    while not calls:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    token.cancel()
    gate.set()
    thread.join(5)
    # the running count finishes, the waiting ones are dropped; no events after start
    assert outcome == ["cancelled"] and len(calls) == 1
    assert [e.type for e in events] == ["start"]


def test_job_pool_order_and_cancel():
    gate, got = threading.Event(), []
    pool = JobPool(1)
    try:
        pool.submit(lambda: gate.wait(5) and "first", 10, got.append)
        while not pool._running:
            time.sleep(0.01)
        pool.submit_all([lambda i=i: i for i in range(3)], 10, [got.append] * 3)
        # urgent jobs are queued before the waiting ones
        pool.submit(lambda: "urgent", 10, got.append, urgent=True)
        gate.set()
        pool.join()
        assert got == ["first", "urgent", 0, 1, 2]
    finally:
        pool.close()

    gate, got, ran = threading.Event(), [], []
    pool = JobPool(1)
    try:
        pool.submit(lambda: gate.wait(5) and ran.append("first"), 10, got.append)
        pool.submit_all([lambda i=i: ran.append(i) for i in range(3)], 10, [got.append] * 3)
        while not pool._running:
            time.sleep(0.01)
        pool.cancel()
        pool.join()
        assert pool.run_all([lambda: 1], 10) == [None]
        gate.set()
        time.sleep(0.1)
        # the running job finished without its callback, the waiting ones never ran
        assert ran == ["first"] and got == []
    finally:
        pool.close()


def test_sample_endpoint_depth(client, fake_manman):
    body = {"graph": ship_graph().model_dump(), "sample_size": 10, "seed": 3}
    flat = client.post("/dbpedia/progressive/sample", json=body).json()
    deep = client.post("/dbpedia/progressive/sample", json={**body, "depth": 2, "branching": 1}).json()
    assert deep["depth"] == 2 and deep["expanded_ids"] == ["ship|<http://dbpedia.org/ontology/homeport>|<http://dbpedia.org/ontology/Country>"]
    (child,) = [m for m in deep["modifications"] if m["depth"] == 2]
    assert child["parent_id"] == deep["expanded_ids"][0] and child["count"] == 0
    assert len(child["operations"]) == 4 and len(child["step_operations"]) == 2
    assert [m for m in deep["modifications"] if m["depth"] == 1] == flat["modifications"]
    # cached per depth
    assert len(fake_manman.progressive_cache.data) == 2
    assert client.post("/dbpedia/progressive/sample", json={**body, "depth": 4}).status_code == 422
    assert "max_depth" in client.post("/dbpedia/progressive/sample", json={**body, "depth": 4}).json()["detail"]
    assert client.post("/dbpedia/progressive/sample", json={**body, "depth": 0}).status_code == 422
    assert client.post("/dbpedia/progressive/sample", json={**body, "branching": 0}).status_code == 422


# --- instance counts of the details ---


def test_details_carry_instance_counts(sampler):
    # links: the triples of the property, subjects: the instances of the class (the
    # stored schema's counts), which the frontend renders as link widths
    result = sampler.sample(ProgressiveRequest(graph=ship_graph(), sample_size=10))
    details = {m.label: m.details for m in result.modifications}
    homeport, commander = details["ship → homeport → country"], details["ship → commander → person"]
    assert {k: l.instance_count for k, l in homeport.links.items()} == {"homeport_1": 2}
    assert {k: l.instance_count for k, l in commander.links.items()} == {"commander_1": 0}
    assert {k: s.instance_count for k, s in homeport.subjects.items()} == {"country_1": 1}
    assert {k: s.instance_count for k, s in commander.subjects.items()} == {"person_1": 1}


def test_cache_key_is_versioned():
    from assistant.progressive import CACHE_VERSION, cache_key

    request = ProgressiveRequest(graph=ship_graph(), sample_size=10)
    key = cache_key(request)
    assert CACHE_VERSION >= 2 and key.startswith(f"progressive:v{CACHE_VERSION}:")
    assert key == cache_key(request.model_copy())
    assert key != cache_key(request.model_copy(update={"seed": 7}))
