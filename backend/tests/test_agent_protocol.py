"""agent/protocol.py: message (de)serialisation and graph diffs."""

import json

import pytest
from pydantic import ValidationError

from agent.protocol import (
    CLIENT_MESSAGE,
    SERVER_MESSAGE,
    AssistantMessage,
    Cancel,
    Clear,
    Done,
    ErrorMessage,
    GraphChange,
    GraphState,
    GraphSync,
    SessionInfo,
    Thinking,
    ToolCall,
    UserMessage,
    describe_graph,
    diff_graphs,
)
from assistant.assistant_model import AssistantLink, AssistantSubject, QueryGraph, StringSubQuery


def subject(id, label=None):
    return AssistantSubject(id=id, uri=f"<urn:{id}>", label=label or id)


def link(id, from_id, to_id):
    return AssistantLink(id=id, uri=f"<urn:{id}>", label=id, from_subject_id=from_id, to_subject_id=to_id)


@pytest.mark.parametrize(
    "raw, cls",
    [
        ({"type": "user_message", "content": "hi"}, UserMessage),
        ({"type": "graph_sync", "graph": {"subjects": [], "links": []}}, GraphSync),
        ({"type": "cancel"}, Cancel),
        ({"type": "clear"}, Clear),
    ],
)
def test_client_messages_parse(raw, cls):
    assert isinstance(CLIENT_MESSAGE.validate_json(json.dumps(raw)), cls)


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "nope"},
        {"content": "missing type"},
        {"type": "user_message"},
        {"type": "graph_sync", "graph": {"subjects": [{"id": "x"}]}},
        # server messages are no client messages
        {"type": "done"},
    ],
)
def test_client_messages_invalid(raw):
    with pytest.raises(ValidationError):
        CLIENT_MESSAGE.validate_json(json.dumps(raw))


def test_graph_sync_parses_subqueries():
    raw = {
        "type": "graph_sync",
        "graph": {
            "subjects": [
                {
                    "id": "n1",
                    "uri": "<urn:n1>",
                    "label": "n1",
                    "subqueries": [{"type": "string", "property_id": "rdfs:label", "value": "Bounty"}],
                }
            ],
            "links": [],
        },
    }
    message = CLIENT_MESSAGE.validate_python(raw)
    assert isinstance(message.graph.subjects[0].subqueries[0], StringSubQuery)


@pytest.mark.parametrize(
    "message",
    [
        SessionInfo(session_id="s1", resumed=True),
        Thinking(id="t", delta="a"),
        AssistantMessage(id="m", content="answer", final=True),
        ToolCall(call_id="c", name="add_subject", arguments={"uri": "x"}, status="error", error="bad"),
        GraphState(graph=QueryGraph(subjects=[subject("a")])),
        ErrorMessage(message="busy", fatal=True),
        Done(reason="max_steps"),
    ],
)
def test_server_messages_round_trip(message):
    raw = message.model_dump_json()
    assert json.loads(raw)["type"] == message.type
    assert SERVER_MESSAGE.validate_json(raw) == message


def test_server_message_defaults():
    assert json.loads(SessionInfo(session_id="s").model_dump_json()) == {
        "type": "session",
        "session_id": "s",
        "resumed": False,
    }
    assert Done().reason == "completed"
    tool_call = ToolCall(call_id="c", name="n")
    assert (tool_call.status, tool_call.arguments, tool_call.changes) == ("running", {}, None)
    with pytest.raises(ValidationError):
        Done(reason="nope")


def test_diff_graphs_added_and_removed():
    before = QueryGraph(subjects=[subject("a"), subject("b")], links=[link("ab", "a", "b")])
    after = QueryGraph(subjects=[subject("a"), subject("c")], links=[link("ac", "a", "c")])
    change = diff_graphs(before, after)
    assert [s.id for s in change.added.subjects] == ["c"]
    assert [s.id for s in change.removed.subjects] == ["b"]
    assert [l.id for l in change.added.links] == ["ac"]
    assert [l.id for l in change.removed.links] == ["ab"]
    # "a" is unchanged but needed to draw both links
    assert [s.id for s in change.context] == ["a"]
    assert not change.empty


def test_diff_graphs_context_from_before_graph():
    before = QueryGraph(subjects=[subject("a"), subject("b")], links=[link("ab", "a", "b")])
    after = QueryGraph(subjects=[subject("a"), subject("b")])
    change = diff_graphs(before, after)
    assert [l.id for l in change.removed.links] == ["ab"]
    assert {s.id for s in change.context} == {"a", "b"}


def test_diff_graphs_identical_is_empty():
    graph = QueryGraph(subjects=[subject("a")])
    change = diff_graphs(graph, graph.model_copy(deep=True))
    assert change.empty and change.context == []
    assert GraphChange().empty


def test_describe_graph_is_compact():
    graph = QueryGraph(subjects=[subject("a")], links=[link("aa", "a", "a")])
    graph.links[0].from_subject_label = "dropped"
    described = json.loads(describe_graph(graph))
    assert described["subjects"] == [{"id": "a", "uri": "<urn:a>", "label": "a", "subqueries": []}]
    assert set(described["links"][0]) == {"id", "uri", "label", "from_subject_id", "to_subject_id"}
