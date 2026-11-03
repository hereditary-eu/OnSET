"""explorative/schema_index.py and the progressive sampler's schema lookups through it,
on the stored schema of the test ontologies (fakes.schema_of)."""

import threading

import pytest

from assistant.assistant_model import QueryGraph
from assistant.progressive import ModificationKind, ProgressiveRequest, ProgressiveSampler, complete
from explorative.schema_index import SchemaIndex
from fakes import DBO, dbo, make_ontology, make_sampler, schema_of
from test_progressive import FLEET_TTL, WIDE_TTL, constraints, homeport_graph, ship_graph

OWL = "http://www.w3.org/2002/07/owl#"


def no_ontology_lookups(monkeypatch, ontology) -> list[str]:
    """Make the OntologyManager's schema lookups fail; returns the recorded label queries."""
    label_queries = []

    def fail(*args, **kwargs):
        raise AssertionError("schema lookup through SPARQL")

    for name in ("outgoing_properties", "enrich_subject", "root_class_ids"):
        monkeypatch.setattr(ontology, name, fail)
    q_to_df = ontology.q_to_df

    def recording(query):
        if "VALUES ?s" in query:
            label_queries.append(query)
        return q_to_df(query)

    monkeypatch.setattr(ontology, "q_to_df", recording)
    return label_queries


def candidate_set(sampler, graph) -> set:
    return {
        (c.from_id, sampler.expand(c.prop), sampler.expand(c.target_uri) if c.target_uri else "")
        for c in sampler.candidates(graph)
    }


def test_schema_index_lookups():
    schema = schema_of(make_ontology(WIDE_TTL))
    # prefixed and wrapped ids are the same
    assert schema.key("dbo:Ship") == schema.key(dbo("Ship")) == f"{DBO}Ship"
    assert schema.has_class(dbo("Warship")) and not schema.has_class(dbo("homeport"))
    # nearest first, owl:Thing only by itself
    assert schema.ancestors("dbo:Warship") == [f"{DBO}{c}" for c in ("Warship", "Ship", "Vehicle")]
    assert schema.ancestors("owl:Thing") == [f"{OWL}Thing"]
    props = {l.property_id for l in schema.links_of(dbo("Warship"))}
    # inherited; dbo:anything (no range) is not stored
    assert props == {"dbo:homeport", "dbo:commander", "dbo:length", "dbo:owner", "dbo:name"}
    assert schema.root_classes() == [dbo(c) for c in ("Person", "Place", "Vehicle")]
    assert schema.label(dbo("homeport")) == "homeport" and schema.label("dbo:Ship") == "ship"
    assert schema.label(dbo("Nothing")) is None
    subject = schema.subject(dbo("Warship"))
    assert (subject.label, subject.spos["rdfs:subClassOf"].first_value()) == ("warship", "dbo:Ship")
    link = schema.link(dbo("homeport"))
    assert (link.property_id, link.from_id, link.to_id, link.to_proptype) == (
        "dbo:homeport", "dbo:Ship", "dbo:Country", None,
    )
    assert schema.link(dbo("length")).to_proptype == "xsd:double"
    assert schema.subject(dbo("Nothing")) is None and schema.link(dbo("nothing")) is None


def test_schema_candidates(monkeypatch):
    ontology = make_ontology(WIDE_TTL)
    no_ontology_lookups(monkeypatch, ontology)
    sampler = make_sampler(ontology).metered()
    props = {(p, t) for _, p, t in candidate_set(sampler, ship_graph())}
    # object properties of Ship and Vehicle; owner's owl:Thing range is untyped, anything
    # (no range) is not stored, length/name are literal
    assert props == {(f"{DBO}homeport", f"{DBO}Country"), (f"{DBO}commander", f"{DBO}Person"), (f"{DBO}owner", "")}
    assert sampler.root_classes() == [dbo(c) for c in ("Person", "Place", "Vehicle")]
    # details of the added links/subjects from the schema
    result = sampler.sample(ProgressiveRequest(graph=ship_graph(), sample_size=64))
    assert complete(result) and len(result.modifications) == 3
    for modification in result.modifications:
        (link,) = modification.details.links.values()
        assert link.property_id.startswith("dbo:") and link.label
        assert all(s.label for s in modification.details.subjects.values())
    # an existing link is no candidate
    assert f"{DBO}homeport" not in {p for _, p, _ in candidate_set(sampler, ship_graph(("homeport", "Country")))}
    # a class the schema does not know has none
    unknown = QueryGraph(subjects=[ship_graph().subjects[0].model_copy(update={"uri": dbo("Unknown")})])
    assert sampler.candidates(unknown) == []


def test_schema_sampling_without_ontology_lookups(monkeypatch):
    ontology = make_ontology(FLEET_TTL)
    label_queries = no_ontology_lookups(monkeypatch, ontology)
    sampler = make_sampler(ontology)
    result = constraints(sampler, homeport_graph(), sample_size=64)
    assert complete(result)
    assert any(m.constraint and m.constraint.property_id == dbo("length") for m in result.modifications)
    assert complete(constraints(sampler, homeport_graph(), sample_size=4, depth=2))
    # only instance labels (the homeports) are queried, the schema has the rest
    assert label_queries and all(DBO not in q for q in label_queries)
    # starting points of an empty graph
    start = sampler.sample(ProgressiveRequest(graph=QueryGraph()))
    assert {m.label for m in start.modifications} == {"ship", "country"}


def test_schema_provider_resolved_per_request():
    ontology = make_ontology(WIDE_TTL)
    calls = []
    sampler = ProgressiveSampler(ontology, schema=lambda: calls.append(1) or schema_of(ontology))
    sampler.sample(ProgressiveRequest(graph=ship_graph()))
    sampler.sample(ProgressiveRequest(graph=ship_graph()))
    assert len(calls) == 2
    with pytest.raises(RuntimeError):
        ProgressiveSampler(ontology, schema=lambda: None).sample(ProgressiveRequest(graph=ship_graph()))


def test_guidance_schema_index_loaded_once():
    from explorative.explorative_support import GuidanceManager

    guidance = GuidanceManager.__new__(GuidanceManager)
    guidance._schema_index = None
    guidance._schema_index_lock = threading.Lock()
    guidance.identifier = "test"
    index = schema_of(make_ontology())
    results = [SchemaIndex([], []), index]
    loads = []

    def load():
        loads.append(1)
        return results.pop(0)

    guidance.load_schema_index = load
    # an empty index: the ontology is not initialised
    with pytest.raises(RuntimeError):
        guidance.schema_index()
    assert guidance.schema_index() is index
    assert guidance.schema_index() is index and len(loads) == 2
