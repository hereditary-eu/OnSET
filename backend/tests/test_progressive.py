"""assistant/progressive.py: candidates, sampling and counts on the in-memory ontology, and the endpoint."""

import random
import threading
import time
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
    ModificationKind,
    ProgressiveRequest,
    ProgressiveResult,
    ProgressiveSampler,
    Term,
    complete,
    counted_graph,
    endpoint_counter,
    endpoint_selector,
    run_bounded,
    weighted_percentiles,
    weighted_sample,
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
    return ProgressiveSampler(make_ontology(FLEET_TTL))


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
    sampler = ProgressiveSampler(make_ontology(FLEET_TTL), config=ProgressiveConfig(max_numeric_values=3))
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
