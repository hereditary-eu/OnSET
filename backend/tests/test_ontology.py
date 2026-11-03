"""ontology.py: OntologyManager on an in-memory rdflib graph."""

import pytest
from rdflib import Literal, URIRef

from model import GeneralizationQuery, InstanceQuery

from fakes import DBO, RES, dbo, make_ontology


def ids(subjects):
    return [s.subject_id for s in subjects]


def test_root_classes(ontology):
    assert set(ids(ontology.get_root_classes())) == {dbo("Vehicle"), dbo("Place"), dbo("Person")}


@pytest.mark.xfail(
    strict=True,
    reason="OntologyConfig.parent_class_query has no DISTINCT and binds ?cls_lbl: "
    "classes with several labels (e.g. per language) are returned once per label",
)
def test_root_classes_are_unique(ontology):
    roots = ids(ontology.get_root_classes())
    assert len(roots) == len(set(roots))


def test_root_classes_fall_back_to_owl_thing():
    ontology = make_ontology(
        """
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <http://ex.org/A> a owl:Class ; rdfs:subClassOf owl:Thing ; rdfs:label "a" .
        """
    )
    assert ids(ontology.get_root_classes()) == ["<http://ex.org/A>"]


def test_subclasses(ontology):
    assert ids(ontology.get_subclasses(dbo("Ship"))) == [dbo("Warship")]
    assert ids(ontology.get_subclasses(dbo("Warship"))) == []
    assert set(ids(ontology.get_all_subclasses(dbo("Vehicle")))) == {dbo("Vehicle"), dbo("Ship"), dbo("Warship")}


def test_named_individuals(ontology):
    individuals = ontology.get_named_individuals(dbo("Ship"))
    assert set(ids(individuals)) == {f"<{RES}Bounty>", f"<{RES}Victory>"}
    assert {s.subject_type for s in individuals} == {"individual"}
    assert len(ontology.get_named_individuals(dbo("Ship"), limit=1)) == 1


def test_instances_search_and_paging(ontology):
    instances = ontology.get_instances(InstanceQuery(cls=dbo("Ship")))
    assert [i.label for i in instances] == ["Bounty", "HMS Victory"]
    assert [i.label for i in ontology.get_instances(InstanceQuery(cls=dbo("Ship"), q="hms"))] == ["HMS Victory"]
    assert [i.label for i in ontology.get_instances(InstanceQuery(cls=dbo("Ship"), limit=1, skip=1))] == ["HMS Victory"]


def test_labels(ontology):
    assert ontology.label_for(dbo("Ship")) == "ship"
    # only the configured language
    assert ontology.label_for(dbo("Vehicle")) == "vehicle"
    assert make_ontology(language="de").label_for(dbo("Vehicle")) == "Fahrzeug"
    assert ontology.label_for("<urn:unknown>") == "<urn:unknown>"


def test_outgoing_edges_for(ontology):
    edges = ontology.outgoing_edges_for(f"<{RES}Bounty>")
    assert set(edges) == {"rdfs:label", "rdf:type", dbo("homeport"), dbo("length")}
    # object labels are resolved, literals converted
    assert [(v.value, v.label) for v in edges[dbo("homeport")].values] == [(f"<{RES}England>", "England")]
    assert edges[dbo("length")].values[0].value == 27.7
    assert {v.value for v in edges["rdf:type"].values} == {dbo("Ship"), "owl:NamedIndividual"}
    # filtered edges
    assert set(ontology.outgoing_edges_for(f"<{RES}Bounty>", ["rdfs:label"])) == {"rdfs:label"}
    # blank nodes are skipped, broken queries return nothing
    assert ontology.outgoing_edges_for("_:b0") == {}
    assert ontology.outgoing_edges_for("not a { term") == {}


def test_enrich_subject(ontology):
    ship = ontology.enrich_subject(f"{DBO}Ship", load_properties=True)
    assert (ship.subject_id, ship.label, ship.subject_type) == (dbo("Ship"), "ship", "class")
    assert set(ship.spos) == {"rdfs:label", "rdf:type", "rdfs:subClassOf"}
    assert ship.instance_count == 2
    assert {k: set(ids(v)) for k, v in ship.properties.items()} == {
        "owl:ObjectProperty": {dbo("homeport"), dbo("commander")},
        "owl:DatatypeProperty": {dbo("length")},
        "rdf:Property": set(),
    }
    assert ship.is_of_type(dbo("Vehicle")) and not ship.is_of_type(dbo("Place"))
    assert ontology.enrich_subject(None) is None
    unknown = ontology.enrich_subject("<urn:unknown>")
    assert unknown.spos == {} and unknown.label == "<urn:unknown>"


def test_property_to_link(ontology):
    link = ontology.enrich_subject(dbo("homeport")).to_link()
    assert (link.property_id, link.from_id, link.to_id, link.label) == (
        dbo("homeport"), dbo("Ship"), dbo("Country"), "homeport",
    )


def test_counts_and_ranges(ontology):
    assert int(ontology.instance_count(dbo("Ship"))) == 2
    assert int(ontology.property_count(dbo("homeport"))) == 2
    assert ids(ontology.range_of(dbo("homeport"))) == [dbo("Country")]
    assert ids(ontology.properties_for(dbo("Ship"), "owl:DatatypeProperty")) == [dbo("length")]
    assert ontology.properties_for("_:b0") == []


def test_most_generic_class(ontology):
    query = GeneralizationQuery(cls=dbo("Warship"), out_link_ids=[dbo("homeport")])
    # the highest parent with a matching link
    assert ontology.get_most_generic_classes(query).subject_id == dbo("Ship")
    query = GeneralizationQuery(cls=dbo("Warship"))
    assert ontology.get_most_generic_classes(query).subject_id in {dbo("Vehicle"), dbo("Ship"), dbo("Warship")}


def test_ontology_extension_is_queried():
    ontology = make_ontology(
        ontology_extension="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <http://ex.org/Extra> a owl:Class ; rdfs:label "extra"@en .
        """
    )
    roots = ids(ontology.get_root_classes())
    assert "<http://ex.org/Extra>" in roots and dbo("Ship") not in roots
    assert ontology.label_for("<http://ex.org/Extra>") == "extra"


def test_invalid_ontology_extension():
    from rdflib.plugins.parsers.notation3 import BadSyntax

    with pytest.raises(BadSyntax):
        make_ontology(ontology_extension="this is { not turtle")


def test_to_readable(ontology):
    xsd = "http://www.w3.org/2001/XMLSchema#"
    assert ontology.to_readable(Literal("3", datatype=URIRef(f"{xsd}integer"))) == 3
    assert ontology.to_readable(Literal("2.5", datatype=URIRef(f"{xsd}double"))) == 2.5
    assert ontology.to_readable(Literal("12", datatype=URIRef(f"{DBO}kilogram"))) == 12.0
    # plain literals are kept as they are
    assert ontology.to_readable(Literal("HMS Victory")) == "HMS Victory"
    # unconvertible values are kept
    assert ontology.to_readable(Literal("x", datatype=URIRef(f"{xsd}integer"))) == "x"
    assert ontology.to_readable(URIRef("http://www.w3.org/2002/07/owl#Class")) == "owl:Class"
    assert ontology.to_readable(URIRef(f"{DBO}Ship")) == dbo("Ship")
    assert ontology.to_readable(5) == 5


def test_q_to_df_values_columns(ontology):
    df = ontology.q_to_df_values(f"SELECT ?s ?len WHERE {{ ?s <{DBO}length> ?len }}")
    assert list(df.columns) == ["s", "len"] and len(df) == 1


def test_q_to_df_values_readable(ontology):
    # the DataFrame keeps the rdflib terms (pandas 3 would turn them into str with pyarrow installed)
    df = ontology.q_to_df_values(f"SELECT ?s ?len WHERE {{ ?s <{DBO}length> ?len }}")
    assert df.to_dict(orient="records") == [{"s": f"<{RES}Bounty>", "len": 27.7}]


def test_get_parents_match_subject_ids(ontology):
    assert ontology.get_parents(dbo("Warship")) == [dbo("Warship"), dbo("Ship"), dbo("Vehicle")]


def test_get_parents(ontology):
    assert ontology.get_parents(f"{DBO}Place") == [dbo("Place")]
    assert ontology.get_parents("<urn:unknown>") == ["<urn:unknown>"]
