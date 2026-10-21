"""api/router/agent.py: the agent chat WebSocket with a scripted LLM."""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent.llm import ResponseDone

from fakes import BlockingLLM, FakeManMan, dbo, final_answer, function_call

WS = "/dbpedia/agent/ws"


def collect_turn(ws):
    messages = []
    while True:
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == "done":
            return messages


def of_type(messages, kind):
    return [m for m in messages if m["type"] == kind]


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


@pytest.fixture
def blocking_manman():
    return FakeManMan(llm=BlockingLLM(answer="All done."))


@pytest.fixture
def blocking_client(app, blocking_manman):
    from api.app import config_app
    from api.config import get_manman

    config_app.dependency_overrides[get_manman] = lambda: blocking_manman
    try:
        yield TestClient(app)
    finally:
        blocking_manman.llm.release()
        config_app.dependency_overrides.pop(get_manman, None)


def test_session_frame_and_generated_id(client):
    with client.websocket_connect(WS) as ws:
        hello = ws.receive_json()
    assert hello["type"] == "session" and hello["resumed"] is False
    assert len(hello["session_id"]) == 32


def test_full_turn_and_follow_up(client, fake_manman):
    with client.websocket_connect(f"{WS}?session_id=s1") as ws:
        assert ws.receive_json() == {"type": "session", "session_id": "s1", "resumed": False}

        # the editor already has a node
        ws.send_json({"type": "graph_sync", "graph": {"subjects": [
            {"id": "node_1", "uri": dbo("Person"), "label": "person"}], "links": []}})
        ws.send_json({"type": "user_message", "content": "Add a ship that has a homeport in a country."})
        messages = collect_turn(ws)
        assert messages[-1] == {"type": "done", "reason": "completed"}

        thinking = of_type(messages, "thinking")
        assert thinking[0]["delta"] and any(t["final"] for t in thinking)
        answer = of_type(messages, "assistant_message")
        assert "".join(a["delta"] for a in answer if not a["final"]) == "Added a ship with a homeport in a country."
        assert answer[-1]["final"] and answer[-1]["id"] == "msg_1"

        calls = of_type(messages, "tool_call")
        add_link = [c for c in calls if c["name"] == "add_link" and c["status"] == "success"][0]
        assert {s["id"] for s in add_link["changes"]["context"]} == {"ship_1", "country_1"}
        assert add_link["details"]["links"]["homeport_1"]["instance_count"] == 42

        states = of_type(messages, "graph_state")
        assert len(states) == 2
        final = states[-1]["graph"]
        assert {s["id"] for s in final["subjects"]} == {"node_1", "ship_1", "country_1"}
        first_user = [m for m in fake_manman.llm.calls[0] if m.get("role") == "user"][0]["content"]
        assert "node_1" in first_user

        # the editor syncs back (with its own link id), the next turn removes a subject
        final["links"][0]["id"] = "editor_link"
        ws.send_json({"type": "graph_sync", "graph": final})
        fake_manman.llm.responses = [
            [ResponseDone(output=[function_call("c9", "remove_subject", subject_id="country_1")])],
            final_answer("Removed the country."),
        ]
        ws.send_json({"type": "user_message", "content": "remove the country"})
        messages = collect_turn(ws)
        removed = [c for c in of_type(messages, "tool_call") if c["status"] == "success"][0]
        assert removed["changes"]["removed"]["subjects"][0]["id"] == "country_1"
        assert removed["changes"]["removed"]["links"][0]["id"] == "editor_link"
        state = of_type(messages, "graph_state")[-1]
        assert {s["id"] for s in state["graph"]["subjects"]} == {"node_1", "ship_1"}
        assert set(state["details"]["subjects"]) == {"ship_1"}


def test_invalid_frame_keeps_connection(client):
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        ws.send_text('{"type": "nope"}')
        error = ws.receive_json()
        assert error["type"] == "error" and not error["fatal"]
        assert error["message"].startswith("Invalid message")
        ws.send_text("not json at all")
        assert ws.receive_json()["type"] == "error"
        # still usable
        ws.send_json({"type": "clear"})
        assert ws.receive_json()["type"] == "session"
        assert ws.receive_json() == {"type": "done", "reason": "cleared"}


def test_resume_on_reconnect_and_clear(client, fake_manman):
    with client.websocket_connect(f"{WS}?session_id=s1") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "content": "Add a ship with a homeport."})
        collect_turn(ws)

    with client.websocket_connect(f"{WS}?session_id=s1") as ws:
        assert ws.receive_json() == {"type": "session", "session_id": "s1", "resumed": True}
        session, _ = fake_manman.agent_sessions.get_or_create("s1")
        assert len(session.agent.history) > 5 and session.graph.subjects
        ws.send_json({"type": "clear"})
        assert ws.receive_json() == {"type": "session", "session_id": "s1", "resumed": False}
        assert ws.receive_json() == {"type": "done", "reason": "cleared"}
        assert len(session.agent.history) == 1 and session.graph.subjects == []

    # another id is another session
    with client.websocket_connect(f"{WS}?session_id=s2") as ws:
        assert ws.receive_json()["resumed"] is False


def test_busy_rejects_message_and_graph_sync(blocking_client, blocking_manman):
    llm = blocking_manman.llm
    with blocking_client.websocket_connect(f"{WS}?session_id=b") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "content": "first"})
        assert llm.entered.wait(5)

        ws.send_json({"type": "user_message", "content": "second"})
        error = ws.receive_json()
        assert error["type"] == "error" and "still working" in error["message"]

        ws.send_json({"type": "graph_sync", "graph": {"subjects": [
            {"id": "node_1", "uri": dbo("Person"), "label": "person"}], "links": []}})
        error = ws.receive_json()
        assert error["type"] == "error" and "sync rejected" in error["message"]

        llm.release()
        messages = collect_turn(ws)
        assert messages[-1] == {"type": "done", "reason": "completed"}
        assert of_type(messages, "assistant_message")[-1]["content"] == "All done."
        session, _ = blocking_manman.agent_sessions.get_or_create("b")
        assert session.graph.subjects == []

        # idle again: syncing works
        ws.send_json({"type": "graph_sync", "graph": {"subjects": [
            {"id": "node_1", "uri": dbo("Person"), "label": "person"}], "links": []}})
        wait_for(lambda: len(session.graph.subjects) == 1)


def test_clear_cancels_running_turn(blocking_client, blocking_manman):
    llm = blocking_manman.llm
    llm.answer = None  # keep calling tools until cancelled
    with blocking_client.websocket_connect(f"{WS}?session_id=c") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "content": "loop"})
        assert llm.entered.wait(5)
        session, _ = blocking_manman.agent_sessions.get_or_create("c")
        ws.send_json({"type": "clear"})
        wait_for(session._cancel.is_set)
        llm.release()

        messages = []
        while not (messages and messages[-1] == {"type": "done", "reason": "cleared"}):
            messages.append(ws.receive_json())
        dones = of_type(messages, "done")
        assert dones == [{"type": "done", "reason": "cancelled"}, {"type": "done", "reason": "cleared"}]
        assert messages[-2] == {"type": "session", "session_id": "c", "resumed": False}
        assert len(session.agent.history) == 1 and not session.busy


def test_cancel_frame(blocking_client, blocking_manman):
    llm = blocking_manman.llm
    llm.answer = None
    with blocking_client.websocket_connect(WS) as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "content": "loop"})
        assert llm.entered.wait(5)
        ws.send_json({"type": "cancel"})
        session = next(iter(blocking_manman.agent_sessions._sessions.values()))
        wait_for(session._cancel.is_set)
        llm.release()
        assert collect_turn(ws)[-1] == {"type": "done", "reason": "cancelled"}


def test_disconnect_cancels_running_turn(blocking_client, blocking_manman):
    llm = blocking_manman.llm
    llm.answer = None
    with blocking_client.websocket_connect(f"{WS}?session_id=d") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "content": "loop"})
        assert llm.entered.wait(5)
        session, _ = blocking_manman.agent_sessions.get_or_create("d")
        # the TestClient waits for the turn on close, release it once it is cancelled
        releaser = threading.Thread(target=lambda: (wait_for(session._cancel.is_set), llm.release()))
        releaser.start()
    releaser.join(5)
    wait_for(lambda: not session.busy)
    # no further LLM call after the cancellation
    assert llm.calls == 1
    # the session survives the disconnect
    assert blocking_manman.agent_sessions.get_or_create("d") == (session, True)


def test_unknown_config_closes_1008(raw_client):
    with pytest.raises(WebSocketDisconnect) as error:
        with raw_client.websocket_connect("/nonexistent/agent/ws") as ws:
            ws.receive_json()
    assert error.value.code == 1008
    assert "nonexistent" in error.value.reason

