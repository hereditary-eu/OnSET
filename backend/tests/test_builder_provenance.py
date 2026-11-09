"""Provenance of the builder's instances: every instance is prov:wasDerivedFrom the corpus
documents it was extracted from (all of them once names are merged), which the API lists
per instance and serves by their corpus id, with fake extractors instead of the model."""

import json

import pytest
from rdflib import DCTERMS, RDFS, Literal

from builder.corpus import load_documents
from builder.ontology import document_iri
from builder.session import Builder
from eval_config import BuilderConfig, DisambiguationSettings, TextSetConfig
from test_builder import FakeExtractor, ontology, wait_built
from test_builder_disambiguation import DOCS as VARIANT_DOCS, ONTO, VariantExtractor


def make_builder(tmp_path, docs: dict, extractor, mode: str = "off") -> Builder:
    path = tmp_path / "docs.json"
    path.write_text(json.dumps(docs))
    config = BuilderConfig(
        name="Test", save_dir=str(tmp_path / "saves"),
        text_set=TextSetConfig(format="json", path=str(path), text_fields=["text"]),
        disambiguation=DisambiguationSettings(mode=mode),
    )
    b = Builder("test", config)
    b.extractor = extractor
    return b


@pytest.fixture
def routed(client, monkeypatch):
    """Registers a builder as ``test`` with the API."""
    import api.router.builder as router

    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    return lambda b: monkeypatch.setitem(router._builders, "test", b)


def test_document_iris_and_paths(tmp_path):
    # ids with spaces, '#' and non-ASCII characters still make valid IRIs
    iri = document_iri("http://ex.org/o/", "a dir/train.json#k ü")
    assert str(iri) == "http://ex.org/o/doc/a%20dir/train.json%23k%20%C3%BC"
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "train.json").write_text(json.dumps({"d1": {"text": "x"}}))
    (tmp_path / "mail").mkdir()
    (tmp_path / "mail" / "1.").write_text("Subject: Hi\nFrom: a@b.c\n\nhello")
    docs = load_documents(TextSetConfig(format="json", path=str(tmp_path), text_fields=["text"]))
    assert [(d.id, d.path) for d in docs] == [("a/train.json#d1", "a/train.json")]
    docs = load_documents(TextSetConfig(format="files", path=str(tmp_path / "mail")))
    assert [(d.id, d.path, d.title) for d in docs] == [("1.", "1.", "Hi")]
    single = load_documents(TextSetConfig(format="json", path=str(tmp_path / "a" / "train.json"), text_fields=["text"]))
    assert [(d.id, d.path) for d in single] == [("d1", "train.json")]


def test_instances_derive_from_their_documents(tmp_path):
    session = make_builder(tmp_path, {
        "d1": {"title": "Hiring", "text": "Alice Smith joined Acme Corp."},
        "d2": {"title": "Merger", "text": "Bob Jones works for Globex."},
        "d3": {"title": "Lunch", "text": "Alice Smith met Bob Jones."},
        "d4": {"title": "Empty", "text": "Nobody here."},
    }, FakeExtractor()).session("p")
    onto = ontology()
    session.set_ontology(onto)
    wait_built(session)
    alice = session.provenance(str(onto.instance("Person", "Alice Smith")))
    assert alice.label == "Alice Smith" and alice.aliases == []
    assert [(d.doc_id, d.title) for d in alice.documents] == [("d1", "Hiring"), ("d3", "Lunch")]
    assert alice.documents[0].iri == str(document_iri(onto.prefix, "d1"))
    # link targets are derived from the documents they are extracted from too (the fake
    # extractor has Alice work for Acme wherever she is named)
    acme = session.provenance(str(onto.instance("Company", "Acme Corp")))
    assert [d.doc_id for d in acme.documents] == ["d1", "d3"]
    # documents without instances add no triples, a document's own triples are added once
    d1 = document_iri(onto.prefix, "d1")
    assert (document_iri(onto.prefix, "d4"), None, None) not in session.graph
    assert list(session.graph.objects(d1, DCTERMS.identifier)) == [Literal("d1")]
    # SPARQL sees them, dcterms: is predefined
    rows = session.run_query(
        "SELECT ?id WHERE { ?i rdfs:label 'Bob Jones' ; prov:wasDerivedFrom ?d . ?d dcterms:identifier ?id }"
    ).rows
    assert sorted(r[0].value for r in rows) == ["d2", "d3"]
    # unknown instances have no provenance
    assert session.provenance("http://ex.org/o/Person/nobody").documents == []


def test_documents_in_query_editor(tmp_path):
    """The editor offers the source documents as a class, linked from every class with their id."""
    from explorative.exp_model import FuzzyQuery, RETURN_TYPE

    session = make_builder(tmp_path, {
        "d1": {"title": "Hiring", "text": "Alice Smith joined Acme Corp."},
        "d2": {"title": "Merger", "text": "Bob Jones and Acme Corp."},
    }, FakeExtractor()).session("e")
    session.set_ontology(ontology())
    wait_built(session)
    guidance = session.kg.guidance_man
    subjects = guidance.search_fuzzy(FuzzyQuery(q="doc", type=RETURN_TYPE.SUBJECT)).results
    assert [(r.subject.subject_id, r.subject.label, r.subject.instance_count) for r in subjects] == [
        ("foaf:Document", "Document", 2)]
    derived = {l.property_id: l for l in guidance.search_links(from_id="onto:Person")}["prov:wasDerivedFrom"]
    assert (derived.label, derived.to_id, derived.to_subject.label, derived.instance_count) == (
        "extracted from", "foaf:Document", "Document", 2)
    fields = guidance.search_links(from_id="foaf:Document")
    assert [(l.property_id, l.to_proptype, l.instance_count) for l in fields] == [("dcterms:identifier", "xsd:string", 2)]
    # the editor's query: documents are typed and foaf: is predefined
    rows = session.run_query(
        "SELECT ?id WHERE { ?p a onto:Person ; prov:wasDerivedFrom ?d . ?d a foaf:Document ; dcterms:identifier ?id ."
        " OPTIONAL { ?d foaf:name ?n } }"
    ).rows
    assert sorted(r[0].value for r in rows) == ["d1", "d2"]


def test_merged_instance_accumulates_documents(tmp_path):
    builder = make_builder(tmp_path, VARIANT_DOCS, VariantExtractor(), mode="normalized")
    session = builder.session("m")
    session.set_ontology(ONTO)
    wait_built(session)
    enron = session.provenance(str(ONTO.instance("Company", "Enron Corp")))
    assert enron.label in {"Enron Corp", "ENRON  corp"}
    assert enron.aliases == sorted({"Enron Corp", "ENRON  corp"} - {enron.label})
    assert [d.doc_id for d in enron.documents] == ["d1", "d2"]


def test_provenance_survives_export_import(tmp_path):
    builder = make_builder(tmp_path, {"d1": {"title": "Hiring", "text": "Alice Smith joined Acme Corp."}}, FakeExtractor())
    session = builder.session("a")
    onto = ontology()
    session.set_ontology(onto)
    wait_built(session)
    ttl = session.export("all")
    assert "dcterms:identifier" in ttl
    other = builder.session("b")
    other.import_ttl(ttl)
    other.stop()
    # the imported KG's documents are found in the corpus by their identifier
    docs = other.provenance(str(onto.instance("Person", "Alice Smith"))).documents
    assert [(d.doc_id, d.title) for d in docs] == [("d1", "Hiring")]
    # documents unknown to the corpus are listed without an id
    session.graph.set((document_iri(onto.prefix, "d1"), DCTERMS.identifier, Literal("gone")))
    session.graph.remove((document_iri(onto.prefix, "d1"), RDFS.label, None))
    docs = session.provenance(str(onto.instance("Person", "Alice Smith"))).documents
    assert [(d.doc_id, d.title) for d in docs] == [(None, str(document_iri(onto.prefix, "d1")))]


def test_provenance_and_document_routes(tmp_path, client, routed):
    builder = make_builder(tmp_path, VARIANT_DOCS, VariantExtractor(), mode="normalized")
    routed(builder)
    client.put("/onto-builder/test/sessions/r/ontology", json=ONTO.model_dump())
    wait_built(builder.session("r"))
    out = client.get(
        "/onto-builder/test/sessions/r/provenance", params={"iri": str(ONTO.instance("Company", "Enron Corp"))},
    ).json()
    assert [d["doc_id"] for d in out["documents"]] == ["d1", "d2"]
    doc = client.get(f"/onto-builder/test/documents/{out['documents'][1]['doc_id']}").json()
    assert doc == {"id": "d2", "title": "Two", "path": "docs.json", "text": "Bob works for ENRON  corp"}
    assert client.get("/onto-builder/test/sessions/r/provenance").status_code == 422
    # only corpus ids: no file paths, also not of files next to the corpus
    for bad in ["docs.json", "../docs.json", "%2E%2E/saves", "/etc/passwd"]:
        assert client.get(f"/onto-builder/test/documents/{bad}").status_code == 404, bad


def test_document_route_with_path_ids(tmp_path, client, routed):
    """Maildir-like ids are paths below the text set (slashes, trailing dots)."""
    root = tmp_path / "maildir"
    (root / "allen-p" / "sent").mkdir(parents=True)
    (root / "allen-p" / "sent" / "1.").write_text("Subject: Gas\nFrom: a@b.c\n\nPhillip Allen sells gas.")
    (tmp_path / "secret.txt").write_text("secret")
    config = BuilderConfig(name="Mail", save_dir=str(tmp_path / "saves"), text_set=TextSetConfig(format="files", path=str(root)))
    routed(Builder("test", config))
    doc = client.get("/onto-builder/test/documents/allen-p/sent/1.").json()
    assert doc["path"] == "allen-p/sent/1." and doc["title"] == "Gas" and "Phillip Allen" in doc["text"]
    assert client.get("/onto-builder/test/documents/allen-p/sent/..%2F..%2F..%2Fsecret.txt").status_code == 404
    assert client.get("/onto-builder/test/documents/secret.txt").status_code == 404
