"""Edit histories saved with sessions (session_history.py): the builder's ontology history and
the query sessions of the explore view (query_session.py, api/router/query_session.py)."""

import json

import pytest

from session_history import EditHistory, HistoryUpdate
from test_builder import builder  # noqa: F401 (fixture)


def entry(timestamp, **data):
    return {"timestamp": timestamp, "entry": {"label": f"e{timestamp}", **data}}


def test_edit_history_upsert_remove_trim():
    history = EditHistory(max_entries=3)
    assert history.apply(HistoryUpdate(upsert=[entry(2), entry(1)]), now=100)
    assert [r.timestamp for r in history.records()] == [1, 2]
    assert history.records()[0].created_at == history.records()[0].updated_at == 100
    # a coalesced edit replaces its entry: created_at stays, updated_at moves
    assert history.apply(HistoryUpdate(upsert=[entry(2, more=True)]), now=200)
    record = history.records()[1]
    assert (record.created_at, record.updated_at, record.entry["more"]) == (100, 200, True)
    # unchanged entries change nothing (and do not bump the version)
    version = history.version
    assert not history.apply(HistoryUpdate(upsert=[entry(2, more=True)], remove=[99]), now=300)
    assert history.version == version
    # the oldest are dropped beyond max_entries
    history.apply(HistoryUpdate(upsert=[entry(3), entry(4)], remove=[2]), now=400)
    assert [r.timestamp for r in history.records()] == [1, 3, 4]
    history.apply(HistoryUpdate(upsert=[entry(5)]), now=500)
    assert [r.timestamp for r in history.records()] == [3, 4, 5]
    # clear goes first, so an update can replace the whole history
    history.apply(HistoryUpdate(clear=True, upsert=[entry(9)]), now=600)
    assert [r.timestamp for r in history.records()] == [9]
    assert EditHistory(history.dump()).records() == history.records()


def test_builder_session_history_saved(builder):  # noqa: F811
    session = builder.session("h1")
    info = session.update_history(HistoryUpdate(upsert=[entry(10), entry(11)]))
    assert info.entries == 2
    assert session.history_path.exists()
    # restored with the session, also without a saved state
    del builder.sessions["h1"]
    records = builder.session("h1").history_records()
    assert [(r.timestamp, r.entry["label"]) for r in records] == [(10, "e10"), (11, "e11")]
    assert all(r.created_at > 0 for r in records)


def test_builder_history_api(builder, client, monkeypatch):  # noqa: F811
    import api.router.builder as router

    monkeypatch.setitem(router._builders, "test", builder)
    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    base = "/onto-builder/test/sessions/a/history"
    assert client.get(base).json() == []
    info = client.patch(base, json={"upsert": [entry(1), entry(2)]}).json()
    assert (info["entries"], info["version"]) == (2, 1)
    client.patch(base, json={"remove": [1]})
    assert [r["timestamp"] for r in client.get(base).json()] == [2]
    assert client.patch("/onto-builder/test/sessions/a.b/history", json={}).status_code == 400


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    import api.router.query_session as router

    monkeypatch.setattr(router.CONFIG_FILE, "query_session_dir", str(tmp_path / "qs"))
    monkeypatch.setattr(router, "_stores", {})
    return tmp_path / "qs"


def test_query_sessions_api(client, sessions_dir):
    base = "/dbpedia/query-sessions"
    assert client.get(f"{base}/s1", params={"create": False}).status_code == 404
    state = client.get(f"{base}/s1").json()
    assert (state["session_id"], state["config_id"], state["query"], state["history"]["entries"]) == ("s1", "dbpedia", "", 0)
    # a new session is only listed (saved) once it changes
    assert client.get(base).json() == []

    state = client.put(f"{base}/s1/query", json={"query": "SELECT * {}", "visual_query": '[{"nodes":"1"}]'}).json()
    assert (state["version"], state["visual_query"]) == (1, '[{"nodes":"1"}]')
    # the query editor's history entries are opaque (e.g. a flatted string)
    info = client.patch(f"{base}/s1/history", json={"upsert": [{"timestamp": 5, "entry": "[{}]"}]}).json()
    assert info["entries"] == 1
    records = client.get(f"{base}/s1/history").json()
    assert records[0]["entry"] == "[{}]" and records[0]["created_at"] == records[0]["updated_at"]

    [summary] = client.get(base).json()
    assert (summary["session_id"], summary["query"], summary["history_entries"]) == ("s1", "SELECT * {}", 1)
    saved = json.loads((sessions_dir / "dbpedia" / "s1.json").read_text())
    assert saved["visual_query"] == '[{"nodes":"1"}]'
    assert json.loads((sessions_dir / "dbpedia" / "s1.history.json").read_text())[0]["timestamp"] == 5

    # sessions are per configuration
    assert client.get("/oma/query-sessions/s1", params={"create": False}).status_code == 404
    assert client.get("/nope/query-sessions/s1").status_code == 404
    assert client.get(f"{base}/bad.id").status_code == 400


def test_query_session_restored(client, sessions_dir):
    import api.router.query_session as router

    base = "/dbpedia/query-sessions"
    client.put(f"{base}/s2/query", json={"query": "ASK {}"})
    client.patch(f"{base}/s2/history", json={"upsert": [entry(1)]})
    created = client.get(f"{base}/s2").json()["created_at"]
    # after a restart
    router._stores.clear()
    state = client.get(f"{base}/s2", params={"create": False}).json()
    assert (state["query"], state["visual_query"], state["created_at"], state["history"]["entries"]) == ("ASK {}", None, created, 1)
    assert client.get(f"{base}/s2/history").json()[0]["entry"] == {"label": "e1"}
