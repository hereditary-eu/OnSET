"""Ontology builder (builder/): corpus search, extraction to triples, the progressive
build, TTL import/export, the REST API and the agent's tools, all with a fake
extractor instead of the llama.cpp model."""

import json
import time

import pytest
from fakes import ScriptedLLM, final_answer
from agent.llm import ResponseDone
from rdflib import RDFS, Graph

from builder.agent import BuilderAgent, BuilderStateMessage
from builder.ontology import Ontology, OntoClass, OntoField, OntoLink, extraction_schema, extraction_triples
from builder.session import Builder, class_query
from eval_config import BuilderConfig, TextSetConfig

def function_call(call_id: str, tool: str, **arguments) -> dict:
    # fakes.function_call takes the tool as ``name``, which is also an argument here
    return {"type": "function_call", "id": f"fc_{call_id}", "call_id": call_id,
            "name": tool, "arguments": json.dumps(arguments)}


DOCS = {
    "d1": {"title": "Hiring", "text": "Alice Smith joined Acme Corp in 2001. She is 34 years old."},
    "d2": {"title": "Merger", "text": "Bob Jones works for Globex. The merger was announced on Monday."},
}


class FakeExtractor:
    """People named in a document, with an age if the text says so, working for a company."""

    def extract(self, onto, text):
        out = {"Person": [], "Company": []}
        if "Alice" in text:
            out["Person"].append({"name": "Alice Smith", "age": 34, "worksFor": ["Acme Corp"]})
        if "Bob" in text:
            out["Person"].append({"name": "Bob Jones", "worksFor": ["Globex"], "bogus": 1})
        return {k: v for k, v in out.items() if onto.get_class(k)}


def ontology() -> Ontology:
    return Ontology(
        prefix="http://ex.org/o/",
        classes=[
            OntoClass(id="Person", fields=[OntoField(name="age", type="integer")]),
            OntoClass(id="Company"),
        ],
        links=[OntoLink(id="worksFor", source="Person", target="Company")],
    )


@pytest.fixture
def builder(tmp_path):
    path = tmp_path / "docs.json"
    path.write_text(json.dumps(DOCS))
    config = BuilderConfig(
        name="Test", save_dir=str(tmp_path / "saves"),
        text_set=TextSetConfig(format="json", path=str(path), text_fields=["text"]),
    )
    b = Builder("test", config)
    b.extractor = FakeExtractor()
    return b


def wait_built(session, timeout=5):
    end = time.time() + timeout
    while session.status.running and time.time() < end:
        time.sleep(0.01)
    assert not session.status.running


def test_corpus_search(builder):
    hits = builder.corpus.search("merger announced", 3)
    assert hits[0].doc_id == "d2" and "merger" in hits[0].text


def test_extraction_schema_and_triples():
    onto = ontology()
    schema = extraction_schema(onto)
    person = schema["properties"]["Person"]["items"]["properties"]
    assert person["age"] == {"type": "integer"} and person["worksFor"]["type"] == "array"
    triples = extraction_triples(onto, FakeExtractor().extract(onto, "Bob and Alice"))
    g = Graph()
    for t in triples:
        g.add(t)
    alice = onto.instance("Person", "Alice Smith")
    assert int(g.value(alice, onto.term("age"))) == 34
    assert g.value(alice, onto.term("worksFor")) == onto.instance("Company", "Acme Corp")
    # unknown keys are ignored
    assert not any("bogus" in str(p) for _, p, _ in g)
    # leaked markup is no name, trailing punctuation is dropped
    onto.classes[0].description = "a human, e.g. a scientist"
    junk = extraction_triples(onto, {"Person": [
        {"name": "Prevotella</name>], {"}, {"name": "Eve."}, {"name": "E.g. a scientist"}]})
    assert {str(o) for _, p, o in junk if p == RDFS.label} == {"Eve"}


def test_progressive_build_and_query(builder):
    session = builder.session("s1")
    session.set_ontology(ontology())
    wait_built(session)
    assert session.status.processed == 2 and session.status.errors == 0
    result = session.run_query(class_query(session.ontology, "Person"))
    assert result.columns == ["instance", "label", "age", "worksFor"]
    labels = {row[1].value: row for row in result.rows}
    assert set(labels) == {"Alice Smith", "Bob Jones"}
    # IRIs carry their label
    assert labels["Bob Jones"][3].label == "Globex"
    # layout-only changes keep the KG, schema changes rebuild it
    onto = session.ontology.model_copy(deep=True)
    onto.classes[0].x = 10
    triples = len(session.graph)
    session.set_ontology(onto)
    assert len(session.graph) == triples
    session.set_ontology(Ontology(prefix=onto.prefix, classes=[OntoClass(id="Company")]))
    wait_built(session)
    assert session.run_query(class_query(session.ontology, "Company")).rows == []


def test_export_import_roundtrip(builder):
    session = builder.session("s1")
    session.set_ontology(ontology())
    wait_built(session)
    ttl = session.export("all", prefix="http://new.org/")
    assert "http://ex.org/o/" not in ttl
    other = builder.session("s2")
    onto = other.import_ttl(ttl)
    assert onto.prefix == "http://new.org/"
    assert {c.id for c in onto.classes} == {"Person", "Company"}
    assert onto.classes[[c.id for c in onto.classes].index("Person")].fields[0].type == "integer"
    assert [(l.id, l.source, l.target) for l in onto.links] == [("worksFor", "Person", "Company")]
    # imported instances are in the KG, next to the rebuilt ones
    wait_built(other)
    rows = other.run_query(class_query(onto, "Person")).rows
    assert {r[1].value for r in rows} == {"Alice Smith", "Bob Jones"}
    # saved sessions are restored
    session.set_query("SELECT * WHERE { ?s ?p ?o }", visual_query='{"nodes":[]}')
    session.save("ontology")
    del builder.sessions["s1"]
    assert builder.session("s1").query == "SELECT * WHERE { ?s ?p ?o }"
    assert builder.session("s1").visual_query == '{"nodes":[]}'


def test_api(builder, client, monkeypatch):
    import api.router.builder as router

    monkeypatch.setitem(router._builders, "test", builder)
    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    state = client.put("/onto-builder/test/sessions/a/ontology", json=ontology().model_dump()).json()
    assert state["version"] == 1
    wait_built(builder.session("a"))
    query = client.get("/onto-builder/test/sessions/a/class-query/Person").json()["query"]
    # a visual query is kept with the SPARQL it generated, a plain query drops it
    state = client.put("/onto-builder/test/sessions/a/query", json={"query": query, "visual_query": '{"nodes":[]}'}).json()
    assert state["visual_query"] == '{"nodes":[]}'
    state = client.put("/onto-builder/test/sessions/a/query", json={"query": query}).json()
    assert state["visual_query"] is None
    results = client.get("/onto-builder/test/sessions/a/results").json()
    assert len(results["rows"]) == 2 and not results["status"]["running"]
    ttl = client.get("/onto-builder/test/sessions/a/export", params={"content": "ontology"})
    assert ttl.headers["content-type"].startswith("text/turtle") and "owl:Class" in ttl.text
    imported = client.post("/onto-builder/test/sessions/b/import", files={"file": ("o.ttl", ttl.content)})
    assert len(imported.json()["ontology"]["classes"]) == 2
    assert client.get("/onto-builder/test/search", params={"q": "Globex"}).json()[0]["doc_id"] == "d2"
    assert client.get("/onto-builder/test/documents/d1").json()["title"] == "Hiring"
    assert client.get("/onto-builder/nope/search", params={"q": "x"}).status_code == 404


def test_session_as_config(builder, app, monkeypatch):
    """A session serves the config-scoped routes of the query editor at /builder:<builder>:<session>."""
    from fastapi.testclient import TestClient
    import api.router.builder as router

    monkeypatch.setitem(router._builders, "test", builder)
    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    session = builder.session("v")
    session.set_ontology(ontology())
    wait_built(session)
    client = TestClient(app)
    base = "/builder:test:v"
    assert client.get(f"{base}/ontology/config").json()["id"] == "builder:test:v"
    classes = client.post(f"{base}/classes/search", json={"q": "pers", "type": "subject"}).json()["results"]
    assert [(r["subject"]["subject_id"], r["subject"]["instance_count"]) for r in classes] == [("onto:Person", 2)]
    links = client.post(f"{base}/classes/search", json={"from_id": "onto:Person", "type": "link"}).json()["results"]
    assert [(l["link"]["property_id"], l["link"]["to_subject"]["label"]) for l in links] == [("onto:worksFor", "Company")]
    props = client.post(f"{base}/classes/search", json={
        "from_id": "onto:Person", "type": "link", "relation_type": "property"}).json()["results"]
    assert [(l["link"]["property_id"], l["link"]["to_proptype"]) for l in props] == [("onto:age", "xsd:integer")]
    assert client.post(f"{base}/classes/search", json={"to_id": "onto:Person", "type": "link"}).json()["results"] == []
    sub = client.post(f"{base}/classes/subclasses/search", json={"from_id": "onto:Company"}).json()["results"]
    assert [r["subject"]["label"] for r in sub] == ["Company"]
    instances = client.get(f"{base}/classes/instances/search", params={"cls": "onto:Person", "q": "ali"}).json()
    assert [i["label"] for i in instances] == ["Alice Smith"]
    rows = client.post(f"{base}/sparql", json={"query": (
        "SELECT ?p ?l ?c WHERE { ?p a onto:Person ; rdfs:label ?l ; onto:worksFor ?c } ORDER BY ?l")}).json()
    assert [(r["l"], r["c"]) for r in rows] == [
        ("Alice Smith", "<http://ex.org/o/Company/acme-corp>"), ("Bob Jones", "<http://ex.org/o/Company/globex>")]
    # renamed labels show without a rebuild, the KG export keeps out the ontology
    onto = session.ontology.model_copy(deep=True)
    onto.classes[0].label = "Human"
    session.set_ontology(onto)
    assert client.get(f"{base}/classes/subjects", params={"subject_id": "onto:Person"}).json()["label"] == "Human"
    assert "owl:Class" not in session.export("kg") and session.status.triples == len(session.graph) - len(session.schema)


def test_agent_edits_ontology(builder):
    session = builder.session("s1")
    llm = ScriptedLLM([
        [ResponseDone(output=[
            function_call("c1", "add_class", name="Person", description="a human"),
            function_call("c2", "add_class", name="company", description="a firm"),
        ])],
        [ResponseDone(output=[
            function_call("c3", "add_field", class_id="Person", name="age", type="integer", description="years"),
            function_call("c4", "add_link", name="works for", source="Person", target="Company", description=""),
            function_call("c5", "search_text", query="Globex"),
        ])],
        [ResponseDone(output=[function_call("c6", "query_class", class_id="Person")])],
        final_answer("Done."),
    ])
    agent = BuilderAgent(llm, session)
    messages = list(agent.run_turn("model people and companies"))
    assert session.ontology.schema_key() == ontology().model_copy(update={"prefix": session.ontology.prefix}).schema_key()
    assert any(isinstance(m, BuilderStateMessage) for m in messages)
    errors = [m for m in messages if getattr(m, "status", None) == "error"]
    assert not errors, errors
    search = next(m for m in messages if getattr(m, "name", "") == "search_text" and m.status == "success")
    assert search.result[0]["doc_id"] == "d2"
    assert session.query.startswith("SELECT ?instance ?label ?age ?worksFor")
    # the model saw the ontology with the request
    assert "Current ontology" in llm.calls[0][-1]["content"]
