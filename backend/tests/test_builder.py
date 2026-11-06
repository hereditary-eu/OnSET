"""Ontology builder (builder/): corpus search, extraction to triples, the progressive
build, TTL import/export, the REST API and the agent's tools, all with a fake
extractor instead of the llama.cpp model."""

import json
import threading
import time
from collections import Counter

import pytest
from fakes import ScriptedLLM, final_answer
from agent.llm import ResponseDone
from rdflib import RDFS, Graph

from builder.corpus import load_documents
from builder.agent import BuilderAgent, BuilderStateMessage
from builder.ontology import Ontology, OntoClass, OntoField, OntoLink, extraction_schema, extraction_triples
from builder.session import IDLE_PAUSE_SECONDS, Builder, class_query
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


def test_json_text_set_glob(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "train.json").write_text(json.dumps(DOCS))
    (tmp_path / "dev.json").write_text(json.dumps([{"title": "Dev", "text": "dev text"}]))
    (tmp_path / "notes.txt").write_text("not json")
    config = TextSetConfig(format="json", path=str(tmp_path), text_fields=["text"])
    assert [d.id for d in load_documents(config)] == ["a/train.json#d1", "a/train.json#d2", "dev.json#0"]
    config.glob, config.max_documents = "a/*.json", 1
    assert [d.title for d in load_documents(config)] == ["Hiring"]


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


def test_chat_history_persists_until_cleared(builder, client, monkeypatch):
    """The agent chat is part of the session: replayed on every connection, kept across
    ontology changes and restarts (saved with the session), deleted only by a clear."""
    import api.router.builder as router

    monkeypatch.setitem(router._builders, "test", builder)
    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    builder.agent_llm = ScriptedLLM([
        [ResponseDone(output=[function_call("c1", "add_class", name="Person", description="a human")])],
        final_answer("Added Person."),
    ], fallback=final_answer("Still here."))
    ws_url = "/onto-builder/test/agent/ws?session_id=chat"

    def turn(ws, content):
        ws.send_json({"type": "user_message", "content": content})
        frames = []
        while (frame := ws.receive_json())["type"] != "done":
            frames.append(frame)
        return frames

    with client.websocket_connect(ws_url) as ws:
        assert ws.receive_json() == {"type": "session", "session_id": "chat", "resumed": False}
        assert ws.receive_json() == {"type": "history", "entries": []}
        turn(ws, "add people")
    # a reconnect (e.g. a page reload) gets the chat as the UI shows it
    with client.websocket_connect(ws_url) as ws:
        assert ws.receive_json()["resumed"] is True
        entries = ws.receive_json()["entries"]
    assert [e["type"] for e in entries] == ["user_message", "tool_call", "assistant_message", "done"]
    assert entries[0]["content"] == "add people" and entries[1]["status"] == "success"
    assert entries[2]["content"] == "Added Person."

    # ontology and query changes keep it; a restarted backend restores it from the save
    session = builder.session("chat")
    session.set_ontology(ontology())
    session.set_query("SELECT * WHERE { ?s ?p ?o }")
    restarted = Builder("test", builder.config)
    restarted.extractor = FakeExtractor()
    restarted.agent_llm = llm = ScriptedLLM([], fallback=final_answer("Still here."))
    monkeypatch.setitem(router._builders, "test", restarted)
    with client.websocket_connect(ws_url) as ws:
        assert ws.receive_json()["resumed"] is True
        assert ws.receive_json()["entries"] == entries
        turn(ws, "and now?")
    # the model got the earlier turn as context
    assert [m.get("content") for m in llm.calls[0] if m.get("role") == "user"][0].startswith("add people")
    assert sum(m.get("type") == "function_call" for m in llm.calls[0]) == 1

    # an evicted session is restored with its chat too
    restarted.sessions.clear()
    with client.websocket_connect(ws_url) as ws:
        ws.receive_json()
        assert [e.get("content") for e in ws.receive_json()["entries"] if e["type"] == "user_message"] == [
            "add people", "and now?"]
        ws.send_json({"type": "clear"})
        assert ws.receive_json()["type"] == "session"
        assert ws.receive_json() == {"type": "done", "reason": "cleared"}
    saved = json.loads(restarted.state_file("chat").read_text())
    assert saved["chat"] == {"history": [], "log": []}
    assert saved["query"] == "SELECT * WHERE { ?s ?p ?o }"
    with client.websocket_connect(ws_url) as ws:
        assert ws.receive_json()["resumed"] is False
        assert ws.receive_json() == {"type": "history", "entries": []}
    restarted.sessions.clear()
    assert restarted.session("chat").chat_history == []
    wait_built(restarted.session("chat"))


def test_session_restored_without_chat(builder):
    """Saves from before the chat history was kept still load."""
    path = builder.state_file("old")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ontology": ontology().model_dump(), "query": "SELECT * WHERE { ?s ?p ?o }"}))
    session = builder.session("old", create=False)
    assert session.chat_history == [] and session.chat_log == []
    assert session.query == "SELECT * WHERE { ?s ?p ?o }"
    wait_built(session)


def test_session_restored_after_restart(builder):
    """Every change is saved, a fresh Builder (a restarted backend) restores the session by its id."""
    session = builder.session("keep")
    session.set_ontology(ontology())
    session.set_query("SELECT * WHERE { ?s ?p ?o }", visual_query='{"nodes":[]}')
    wait_built(session)
    other = builder.session("imp")
    other.import_ttl(session.export("all"))
    wait_built(other)

    restarted = Builder("test", builder.config)
    restarted.extractor = FakeExtractor()
    restored = restarted.session("keep", create=False)
    assert restored.ontology == session.ontology
    assert restored.query == "SELECT * WHERE { ?s ?p ?o }" and restored.visual_query == '{"nodes":[]}'
    # the build restarts
    wait_built(restored)
    assert restored.status.processed == 2
    rows = restored.run_query(class_query(restored.ontology, "Person")).rows
    assert {r[1].value for r in rows} == {"Alice Smith", "Bob Jones"}
    # imported instance triples are restored too
    imported = restarted.session("imp", create=False)
    assert len(imported.imported) == len(other.imported) > 0
    wait_built(imported)


def test_unknown_and_invalid_session_ids(builder, client, monkeypatch):
    import api.router.builder as router

    with pytest.raises(KeyError):
        builder.session("missing", create=False)
    assert "missing" not in builder.sessions
    for bad in ("../x", "..", "a.b", "a/b", "x" * 65):
        with pytest.raises(ValueError):
            builder.session(bad)
    monkeypatch.setitem(router._builders, "test", builder)
    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    assert client.get("/onto-builder/test/sessions/missing", params={"create": False}).status_code == 404
    assert client.get("/onto-builder/test/sessions/..", params={"create": False}).status_code in (400, 404)
    assert client.get("/onto-builder/test/sessions/a.json").status_code == 400
    # a loaded (not yet saved) session is found, and so is a saved one
    client.get("/onto-builder/test/sessions/fresh")
    assert client.get("/onto-builder/test/sessions/fresh", params={"create": False}).status_code == 200
    builder.session("fresh").set_query("SELECT * WHERE { ?s ?p ?o }")
    builder.sessions.clear()
    state = client.get("/onto-builder/test/sessions/fresh", params={"create": False}).json()
    assert state["query"] == "SELECT * WHERE { ?s ?p ?o }"


class SlowExtractor:
    """The person (and company) of a "<person> works for <company>" document, after a delay;
    counts the calls per text and how many run at once."""

    def __init__(self, delay: float):
        self.delay = delay
        self.calls = Counter()
        self.running = self.max_running = 0
        self._lock = threading.Lock()

    def extract(self, onto, text):
        with self._lock:
            self.calls[text] += 1
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        time.sleep(self.delay)
        with self._lock:
            self.running -= 1
        person, company = text.split(" works for ")
        out = {"Person": [{"name": person, "worksFor": [company]}], "Company": [{"name": company}]}
        return {k: v for k, v in out.items() if onto.get_class(k)}


def slow_builder(tmp_path, instances: int, docs: int, delay: float) -> Builder:
    path = tmp_path / f"docs-{instances}.json"
    path.write_text(json.dumps({
        f"d{i}": {"title": f"Doc {i}", "text": f"Person {i} works for Company {i % 5}"} for i in range(docs)
    }))
    config = BuilderConfig(
        name="Test", save_dir=str(tmp_path / f"saves-{instances}"), extract_instances=instances,
        text_set=TextSetConfig(format="json", path=str(path), text_fields=["text"]),
    )
    b = Builder("test", config)
    b.extractor = SlowExtractor(delay)
    return b


def test_parallel_build_matches_serial(tmp_path):
    graphs = {}
    for instances in (1, 4):
        b = slow_builder(tmp_path, instances, docs=30, delay=0.005)
        session = b.session("s")
        session.set_ontology(ontology())
        wait_built(session, timeout=10)
        assert session.status.processed == 30 and session.status.errors == 0
        # every document extracted once, by up to ``instances`` threads at once
        assert len(b.extractor.calls) == 30 and set(b.extractor.calls.values()) == {1}
        assert b.extractor.max_running == 1 if instances == 1 else 1 < b.extractor.max_running <= instances
        graphs[instances] = set(session.graph)
    assert graphs[1] == graphs[4]


def test_parallel_build_stops_and_pauses(tmp_path):
    b = slow_builder(tmp_path, 4, docs=60, delay=0.05)
    session = b.session("s")
    session.set_ontology(ontology())

    def settled() -> int:
        """Extraction calls, once no more are started."""
        calls = -1
        while calls != (calls := b.extractor.calls.total()):
            time.sleep(0.2)
        return calls

    # stop: queued documents are dropped, the ones in progress don't count
    while session.status.processed < 4:
        time.sleep(0.01)
    session.stop()
    processed = session.status.processed
    assert settled() < 60 and not session.status.running
    assert session.status.processed == processed

    # pause while nobody looks at the session, resume on the next access
    session.set_ontology(ontology().model_copy(update={"links": []}))
    while session.status.processed < 4:
        time.sleep(0.01)
    session.last_access = time.monotonic() - IDLE_PAUSE_SECONDS - 1
    calls = settled()
    assert session.status.running and session.status.processed < 60
    session.state()
    wait_built(session, timeout=10)
    assert session.status.processed == 60 and b.extractor.calls.total() > calls

    # a schema change restarts the build, results of the old one don't leak into the new KG
    session.set_ontology(ontology())
    while session.status.processed < 4:
        time.sleep(0.01)
    session.set_ontology(Ontology(prefix="http://ex.org/o/", classes=[OntoClass(id="Company")]))
    wait_built(session, timeout=10)
    assert session.status.processed == 60
    labels = {str(o) for _, p, o in session.graph if p == RDFS.label}
    assert not any(label.startswith("Person") for label in labels)
    assert {f"Company {i}" for i in range(5)} <= labels
