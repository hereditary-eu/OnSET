"""agent/agent.py: the tool-calling loop of one turn."""

import json

import pytest

from agent.agent import SYSTEM_PROMPT, GraphAgent
from agent.graph_tools import GraphEditorTools
from agent.llm import AgentLLMBase, LLMError, ReasoningDelta, ResponseDone, TextDelta
from assistant.assistant_model import AssistantSubject, QueryGraph

from fakes import ScriptedLLM, dbo, final_answer, function_call, message, reasoning, ship_scenario


@pytest.fixture
def tools(ontology, guidance):
    return GraphEditorTools(ontology, guidance)


def run(agent, content="Add a ship that has a homeport in a country.", **kwargs):
    return [m.model_dump(mode="json") for m in agent.run_turn(content, **kwargs)]


def of_type(messages, kind):
    return [m for m in messages if m["type"] == kind]


def test_full_turn(tools):
    tools.graph = QueryGraph(subjects=[AssistantSubject(id="node_1", uri=dbo("Person"), label="person")])
    llm = ScriptedLLM(ship_scenario())
    agent = GraphAgent(llm, tools, max_steps=8)
    messages = run(agent)

    assert messages[-1] == {"type": "done", "reason": "completed"}
    assert len(llm.calls) == 5

    thinking = of_type(messages, "thinking")
    assert [t["delta"] for t in thinking if t["id"] == "rs_1" and not t["final"]] == [
        "The user wants a ship ",
        "with a homeport.",
    ]
    assert [t["content"] for t in thinking if t["id"] == "rs_1" and t["final"]] == [
        "The user wants a ship with a homeport."
    ]
    inline = [t for t in thinking if t["id"] == "msg_1:think"]
    assert "".join(t["delta"] for t in inline if not t["final"]) == "Done, summarise."
    assert inline[-1]["final"] and inline[-1]["content"] == "Done, summarise."

    answer = of_type(messages, "assistant_message")
    assert "".join(a["delta"] for a in answer if not a["final"]) == "Added a ship with a homeport in a country."
    assert answer[-1] == {
        "type": "assistant_message",
        "id": "msg_1",
        "delta": "",
        "content": "Added a ship with a homeport in a country.",
        "final": True,
    }

    calls = of_type(messages, "tool_call")
    assert [(c["name"], c["status"]) for c in calls] == [
        (name, status)
        for name in ["search_classes", "search_classes", "add_subject", "add_subject", "search_links", "add_link"]
        for status in ["running", "success"]
    ]
    # searches do not change the graph
    assert calls[1]["changes"] is None and calls[1]["details"] is None
    add_ship = calls[5]
    assert add_ship["changes"]["added"]["subjects"][0]["id"] == "ship_1"
    assert set(add_ship["details"]["subjects"]) == {"ship_1"}
    add_link = calls[-1]
    assert [l["id"] for l in add_link["changes"]["added"]["links"]] == ["homeport_1"]
    assert {s["id"] for s in add_link["changes"]["context"]} == {"ship_1", "country_1"}
    assert add_link["details"]["links"]["homeport_1"]["instance_count"] == 42

    # one graph_state per step that changed the graph (add subjects, add link)
    states = of_type(messages, "graph_state")
    assert len(states) == 2
    final = states[-1]
    assert [s["id"] for s in final["graph"]["subjects"]] == ["node_1", "ship_1", "country_1"]
    assert final["graph"]["links"][0]["from_subject_id"] == "ship_1"
    # editor subjects have no details
    assert set(final["details"]["subjects"]) == {"ship_1", "country_1"}

    # the synced graph is sent with the request
    user = [m for m in llm.calls[0] if m.get("role") == "user"]
    assert "node_1" in user[0]["content"]
    assert llm.calls[0][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert {t["name"] for t in llm.tools[0]} >= {"search_classes", "add_subject", "add_link"}


def test_history_has_an_output_per_call(tools):
    agent = GraphAgent(ScriptedLLM(ship_scenario()), tools)
    run(agent)
    call_ids = [m["call_id"] for m in agent.history if m.get("type") == "function_call"]
    output_ids = [m["call_id"] for m in agent.history if m.get("type") == "function_call_output"]
    assert call_ids == output_ids == ["c1", "c2", "c3", "c4", "c5", "c6"]
    outputs = {m["call_id"]: json.loads(m["output"]) for m in agent.history if m.get("type") == "function_call_output"}
    assert outputs["c1"] == [{"uri": dbo("Ship"), "label": "ship", "parents": [dbo("Ship"), dbo("Vehicle")]}]
    assert outputs["c3"]["id"] == "ship_1"


def test_graph_only_resent_when_changed(tools):
    llm = ScriptedLLM([final_answer("one"), final_answer("two"), *ship_scenario(), final_answer("four")])
    agent = GraphAgent(llm, tools)
    run(agent, "first")
    run(agent, "second")
    users = [m["content"] for m in agent.history if m.get("role") == "user"]
    assert "Current query graph" in users[0]
    # unchanged since the model saw it
    assert users[1] == "second"

    # graph edits by the agent count as seen
    run(agent, "third")
    run(agent, "fourth")
    assert [m["content"] for m in agent.history if m.get("role") == "user"][-1] == "fourth"

    # an editor sync changes it
    tools.graph = QueryGraph()
    llm.responses.append(final_answer("five"))
    run(agent, "fifth")
    assert [m["content"] for m in agent.history if m.get("role") == "user"][-1].startswith(
        "fifth\n\nCurrent query graph:"
    )


def test_max_steps(tools):
    llm = ScriptedLLM([], fallback=[ResponseDone(output=[function_call("c", "get_query_graph")])])
    agent = GraphAgent(llm, tools, max_steps=3)
    messages = run(agent)
    assert len(llm.calls) == 3
    assert messages[-2]["type"] == "error" and "3 steps" in messages[-2]["message"]
    assert messages[-1] == {"type": "done", "reason": "max_steps"}
    assert of_type(messages, "graph_state") == []


def test_tool_errors_are_fed_back(tools):
    llm = ScriptedLLM(
        [
            [ResponseDone(output=[function_call("c1", "add_subject", uri=dbo("Unicorn"))])],
            [ResponseDone(output=[function_call("c2", "no_such_tool")])],
            [ResponseDone(output=[{**function_call("c3", "remove_link"), "arguments": "{oops"}])],
            final_answer("Sorry."),
        ]
    )
    agent = GraphAgent(llm, tools)
    messages = run(agent)
    errors = [m for m in of_type(messages, "tool_call") if m["status"] == "error"]
    assert [e["call_id"] for e in errors] == ["c1", "c2", "c3"]
    assert "does not exist" in errors[0]["error"]
    # undecodable arguments are shown raw
    assert errors[2]["arguments"] == {"raw": "{oops"}
    assert messages[-1]["reason"] == "completed"
    fed_back = [json.loads(m["output"]) for m in agent.history if m.get("type") == "function_call_output"]
    assert all("error" in f for f in fed_back)


def test_missing_call_id_is_assigned(tools):
    call = function_call("x", "get_query_graph")
    del call["call_id"]
    agent = GraphAgent(ScriptedLLM([[ResponseDone(output=[call])], final_answer("ok")]), tools)
    messages = run(agent)
    call_id = of_type(messages, "tool_call")[0]["call_id"]
    assert call_id.startswith("call_")
    assert [m["call_id"] for m in agent.history if m.get("type") == "function_call_output"] == [call_id]


def test_cancel_before_step(tools):
    agent = GraphAgent(ScriptedLLM([]), tools)
    assert run(agent, cancelled=lambda: True) == [{"type": "done", "reason": "cancelled"}]


def test_cancel_between_calls_keeps_history_valid(tools):
    state = {"cancelled": False}

    class CancellingTools(GraphEditorTools):
        def call(self, name, arguments):
            state["cancelled"] = True
            return super().call(name, arguments)

    tools = CancellingTools(tools.ontology_manager, tools.guidance)
    llm = ScriptedLLM(
        [[ResponseDone(output=[function_call("c1", "add_subject", uri=dbo("Ship")), function_call("c2", "get_query_graph")])]]
    )
    agent = GraphAgent(llm, tools)
    messages = run(agent, cancelled=lambda: state["cancelled"])
    assert [m["call_id"] for m in of_type(messages, "tool_call")] == ["c1", "c1"]
    # the step's graph change is still reported
    assert messages[-2]["type"] == "graph_state"
    assert messages[-1] == {"type": "done", "reason": "cancelled"}
    outputs = [m for m in agent.history if m.get("type") == "function_call_output"]
    assert [o["call_id"] for o in outputs] == ["c1", "c2"]
    assert "Cancelled" in outputs[1]["output"]


def test_llm_error_ends_turn(tools):
    class FailingLLM(AgentLLMBase):
        def respond(self, messages, tools):
            yield TextDelta("m", "partial")
            raise LLMError("server down")

    messages = run(GraphAgent(FailingLLM(), tools))
    assert messages[-2] == {"type": "error", "message": "server down", "fatal": False}
    assert messages[-1] == {"type": "done", "reason": "error"}


def test_non_streamed_response_and_missing_ids(tools):
    # no deltas, no item ids: one final frame per block with generated ids
    llm = ScriptedLLM(
        [[ResponseDone(output=[{**reasoning(None, "hmm"), "id": None}, message(None, "<think>inner</think> Done. ")])]]
    )
    messages = run(GraphAgent(llm, tools))
    thinking = of_type(messages, "thinking")
    assert [t["content"] for t in thinking] == ["hmm", "inner"]
    assert all(t["final"] for t in thinking)
    assert len({t["id"] for t in thinking}) == 2
    answer = of_type(messages, "assistant_message")
    assert len(answer) == 1 and answer[0]["content"] == "Done."


def test_streamed_without_item_ids_reuses_block_id(tools):
    # servers that stream without item ids must not produce a duplicate final block
    llm = ScriptedLLM([[TextDelta(None, "Hel"), TextDelta(None, "lo"), ReasoningDelta(None, "r"),
                        ResponseDone(output=[reasoning(None, "r"), message(None, "Hello")])]])
    messages = run(GraphAgent(llm, tools))
    answer = of_type(messages, "assistant_message")
    assert len({a["id"] for a in answer}) == 1
    thinking = of_type(messages, "thinking")
    assert len({t["id"] for t in thinking}) == 1


def test_reset(tools):
    agent = GraphAgent(ScriptedLLM([final_answer("a")]), tools)
    run(agent)
    assert len(agent.history) > 1
    agent.reset()
    assert agent.history == [{"role": "system", "content": SYSTEM_PROMPT}]
