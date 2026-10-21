"""agent/session.py: sessions (graph + history) and their LRU store."""

import threading

import pytest

from agent.llm import ResponseDone
from agent.session import AgentSession, AgentSessionStore, SessionBusy
from assistant.assistant_model import AssistantSubject, QueryGraph
from eval_config import AgentConfig

from fakes import BlockingLLM, ScriptedLLM, dbo, final_answer, function_call


def make_session(ontology, guidance, llm, session_id="s1", **config):
    return AgentSession(session_id, llm, ontology, guidance, AgentConfig(**config))


def kinds(messages):
    return [m.type for m in messages]


def test_config_is_applied(ontology, guidance):
    session = make_session(ontology, guidance, ScriptedLLM([]), max_steps=4, retrieve_k=9)
    assert session.agent.max_steps == 4 and session.tools.retrieve_k == 9
    assert session.graph == QueryGraph() and not session.busy


def test_run_turn_and_clear(ontology, guidance):
    llm = ScriptedLLM([[ResponseDone(output=[function_call("c1", "add_subject", uri=dbo("Ship"))])], final_answer("ok")])
    session = make_session(ontology, guidance, llm)
    messages = list(session.run_turn("add a ship"))
    assert messages[-1].reason == "completed"
    assert [s.id for s in session.graph.subjects] == ["ship_1"]
    assert not session.busy

    session.clear()
    assert session.graph == QueryGraph()
    assert len(session.agent.history) == 1
    assert session.tools.details.subjects == {}


def test_sync_graph_prunes_details(ontology, guidance):
    llm = ScriptedLLM([[ResponseDone(output=[function_call("c1", "add_subject", uri=dbo("Ship"))])], final_answer("ok")])
    session = make_session(ontology, guidance, llm)
    list(session.run_turn("add a ship"))
    session.sync_graph(QueryGraph(subjects=[AssistantSubject(id="node_1", uri=dbo("Person"), label="person")]))
    assert [s.id for s in session.graph.subjects] == ["node_1"]
    assert session.tools.details.subjects == {}


def test_agent_exception_ends_turn(ontology, guidance):
    class Broken(ScriptedLLM):
        def respond(self, messages, tools):
            raise RuntimeError("bug")
            yield

    session = make_session(ontology, guidance, Broken([]))
    messages = list(session.run_turn("hi"))
    assert kinds(messages) == ["error", "done"]
    assert "RuntimeError: bug" in messages[0].message and messages[1].reason == "error"
    assert not session.busy


@pytest.fixture
def blocked(ontology, guidance):
    """A session whose turn is running (blocked inside the LLM) in a thread."""
    llm = BlockingLLM()
    session = make_session(ontology, guidance, llm)
    messages = []
    thread = threading.Thread(target=lambda: messages.extend(session.run_turn("go")))
    thread.start()
    assert llm.entered.wait(5)
    yield session, llm, messages, thread
    llm.release()
    thread.join(5)


def test_busy_session_rejects(blocked):
    session, llm, messages, thread = blocked
    assert session.busy
    with pytest.raises(SessionBusy):
        session.sync_graph(QueryGraph())
    with pytest.raises(SessionBusy):
        session.clear()
    assert kinds(session.run_turn("again")) == ["error", "done"]


def test_cancel_stops_running_turn(blocked):
    session, llm, messages, thread = blocked
    session.cancel()
    llm.release()
    thread.join(5)
    assert messages[-1].type == "done" and messages[-1].reason == "cancelled"
    # the call made before the cancellation took effect is answered
    assert llm.calls == 1
    assert not session.busy
    # a new turn resets the cancellation
    llm.answer = "fine"
    assert list(session.run_turn("again"))[-1].reason == "completed"


def test_store_creates_resumes_and_evicts():
    created = []

    def factory(session_id):
        created.append(session_id)
        return type("S", (), {"session_id": session_id})()

    store = AgentSessionStore(factory, max_sessions=2)
    a, resumed = store.get_or_create("a")
    assert not resumed and a.session_id == "a"
    assert store.get_or_create("a") == (a, True)

    generated, resumed = store.get_or_create(None)
    assert not resumed and len(generated.session_id) == 32
    # using "a" again makes the generated session the least recently used one
    store.get_or_create("a")
    store.get_or_create("c")
    # ... so "c" evicted it
    assert store.get_or_create(generated.session_id)[1] is False
    assert created == ["a", generated.session_id, "c", generated.session_id]
    # unknown ids are created under the requested id
    assert store.get_or_create("zzz")[0].session_id == "zzz"
