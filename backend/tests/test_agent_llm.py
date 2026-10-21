"""agent/llm.py: <think> splitting and AgentLLM against a fake OpenAI-compatible server."""

import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agent.llm import (
    AgentLLM,
    LLMError,
    ReasoningDelta,
    ResponseDone,
    TextDelta,
    ThinkTagSplitter,
    message_text,
    reasoning_text,
)
from eval_config import AgentConfig

# --- ThinkTagSplitter ---


def feed_all(deltas):
    splitter = ThinkTagSplitter()
    chunks = [c for d in deltas for c in splitter.feed(d)] + splitter.flush()
    thinking = "".join(t for is_thinking, t in chunks if is_thinking)
    answer = "".join(t for is_thinking, t in chunks if not is_thinking)
    return thinking, answer, chunks


@pytest.mark.parametrize(
    "text, expected",
    [
        ("<think>a</think>b", ("a", "b")),
        ("no tags", ("", "no tags")),
        ("<think>only thinking", ("only thinking", "")),
        ("pre<think>x</think>post<think>y</think>end", ("xy", "prepostend")),
        ("a < b and c <th", ("", "a < b and c <th")),
    ],
)
def test_split(text, expected):
    assert ThinkTagSplitter.split(text) == expected


@pytest.mark.parametrize(
    "deltas",
    [
        ["<thi", "nk>Done, summarise", ".</th", "ink>Added a ship."],
        ["<", "t", "h", "i", "n", "k", ">", "Done, summarise.", "<", "/", "think>", "Added a ship."],
        ["<think>Done, summarise.</think>Added a ship."],
        ["<think>Done, summarise.</", "think", ">Added a ship."],
    ],
)
def test_feed_tags_split_across_deltas(deltas):
    thinking, answer, chunks = feed_all(deltas)
    assert (thinking, answer) == ("Done, summarise.", "Added a ship.")
    # no tag fragment ever leaks into a chunk
    assert not any("<" in text and "think" in text for _, text in chunks)


def test_feed_holds_back_only_tag_prefixes():
    splitter = ThinkTagSplitter()
    assert splitter.feed("a <t") == [(False, "a ")]
    # "<tx" can no longer become a tag, it is released
    assert splitter.feed("x") == [(False, "<tx")]
    assert splitter.feed("<b") == [(False, "<b")]
    assert splitter.feed("end<") == [(False, "end")]
    assert splitter.flush() == [(False, "<")]
    assert splitter.flush() == []


def test_item_texts():
    assert message_text({"content": [{"type": "output_text", "text": "a"}, {"type": "refusal", "text": "x"}, {"type": "text", "text": "b"}]}) == "ab"
    assert message_text({"content": "plain"}) == "plain"
    assert message_text({}) == ""
    assert reasoning_text({"content": [{"type": "reasoning_text", "text": "r"}]}) == "r"
    # summaries are the fallback
    assert reasoning_text({"content": [], "summary": [{"type": "summary_text", "text": "s"}]}) == "s"


# --- fake OpenAI-compatible server ---

OUTPUT = [
    {"type": "reasoning", "id": "rs_1", "summary": [], "status": "completed",
     "content": [{"type": "reasoning_text", "text": "Think."}]},
    {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "search_classes",
     "arguments": "{\"query\":\"ship\"}", "status": "completed"},
    {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
     "content": [{"type": "output_text", "text": "Hi there", "annotations": []}]},
]
RESPONSE = {"id": "resp_1", "object": "response", "created_at": 0, "model": "fake",
            "status": "completed", "output": OUTPUT, "parallel_tool_calls": True,
            "tool_choice": "auto", "tools": []}


def stream_events(mode: str) -> list[dict]:
    created = {"type": "response.created", "response": {**RESPONSE, "status": "in_progress", "output": []}}
    if mode == "failed":
        return [created, {"type": "response.failed",
                          "response": {**RESPONSE, "status": "failed", "output": [],
                                       "error": {"code": "server_error", "message": "out of memory"}}}]
    if mode == "error":
        return [created, {"type": "error", "code": "x", "message": "context too long", "param": None}]
    events = [
        created,
        {"type": "response.reasoning_text.delta", "item_id": "rs_1", "output_index": 0, "content_index": 0, "delta": "Thi"},
        {"type": "response.reasoning_text.delta", "item_id": "rs_1", "output_index": 0, "content_index": 0, "delta": "nk."},
        {"type": "response.output_item.done", "output_index": 0, "item": OUTPUT[0]},
        {"type": "response.output_item.done", "output_index": 1, "item": OUTPUT[1]},
        {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 2, "content_index": 0, "delta": "Hi ", "logprobs": []},
        {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 2, "content_index": 0, "delta": "there", "logprobs": []},
        {"type": "response.output_item.done", "output_index": 2, "item": OUTPUT[2]},
    ]
    if mode == "completed":
        events.append({"type": "response.completed", "response": RESPONSE})
    # mode "no_completed": the output is assembled from the output_item.done events
    return events


class FakeServer:
    def __init__(self):
        self.requests: list[dict] = []
        self.model_lists = 0
        self.mode = "completed"
        self.app = FastAPI()

        @self.app.get("/v1/models")
        def models():
            self.model_lists += 1
            return {"object": "list", "data": [
                {"id": "/gguf/fake.gguf", "object": "model", "created": 0, "owned_by": "me"},
                {"id": "second", "object": "model", "created": 0, "owned_by": "me"},
            ]}

        @self.app.post("/v1/responses")
        async def responses(request: Request):
            body = await request.json()
            self.requests.append(body)
            if not body.get("stream"):
                return JSONResponse(RESPONSE)
            events = stream_events(self.mode)

            def generate():
                for i, event in enumerate(events):
                    event = {**event, "sequence_number": i}
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")


@pytest.fixture(scope="module")
def server_url():
    fake = FakeServer()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(fake.app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "fake LLM server did not start"
    yield f"http://127.0.0.1:{port}/v1", fake
    server.should_exit = True
    thread.join(5)
    sock.close()


@pytest.fixture
def server(server_url):
    url, fake = server_url
    fake.requests.clear()
    fake.model_lists = 0
    fake.mode = "completed"
    return url, fake


MESSAGES = [{"role": "user", "content": "hi"}]
TOOLS = [{"type": "function", "name": "x", "parameters": {}}]


@pytest.mark.parametrize("mode", ["completed", "no_completed"])
def test_streaming(server, mode):
    url, fake = server
    fake.mode = mode
    llm = AgentLLM(AgentConfig(base_url=url, stream=True))
    events = list(llm.respond(MESSAGES, TOOLS))
    done = events[-1]
    assert isinstance(done, ResponseDone)
    assert [o["type"] for o in done.output] == ["reasoning", "function_call", "message"]
    assert done.output[1]["call_id"] == "call_1"
    assert "".join(e.delta for e in events if isinstance(e, ReasoningDelta)) == "Think."
    assert "".join(e.delta for e in events if isinstance(e, TextDelta)) == "Hi there"
    assert {e.item_id for e in events if isinstance(e, TextDelta)} == {"msg_1"}
    request = fake.requests[-1]
    assert request["stream"] is True and request["input"] == MESSAGES
    assert request["tools"][0]["name"] == "x"


def test_non_streaming(server):
    url, fake = server
    llm = AgentLLM(AgentConfig(base_url=url, stream=False, temperature=0.2))
    events = list(llm.respond(MESSAGES, TOOLS))
    assert len(events) == 1 and isinstance(events[0], ResponseDone)
    assert [o["type"] for o in events[0].output] == ["reasoning", "function_call", "message"]
    # None values are dropped from the dumped items
    assert all(v is not None for item in events[0].output for v in item.values())
    request = fake.requests[-1]
    assert not request.get("stream") and request["temperature"] == 0.2


def test_model_auto_pick_is_cached(server):
    url, fake = server
    llm = AgentLLM(AgentConfig(base_url=url, stream=False))
    list(llm.respond(MESSAGES, TOOLS))
    list(llm.respond(MESSAGES, TOOLS))
    assert llm.model == "/gguf/fake.gguf"
    assert fake.requests[-1]["model"] == "/gguf/fake.gguf"
    assert fake.model_lists == 1
    assert "temperature" not in fake.requests[-1]


def test_configured_model_skips_listing(server):
    url, fake = server
    llm = AgentLLM(AgentConfig(base_url=url, stream=False, model="second"))
    list(llm.respond(MESSAGES, TOOLS))
    assert fake.requests[-1]["model"] == "second" and fake.model_lists == 0


@pytest.mark.parametrize("mode, error", [("failed", "Response failed"), ("error", "context too long")])
def test_stream_failures_raise_llm_error(server, mode, error):
    url, fake = server
    fake.mode = mode
    llm = AgentLLM(AgentConfig(base_url=url, stream=True))
    with pytest.raises(LLMError, match=error):
        list(llm.respond(MESSAGES, TOOLS))


def test_unreachable_server_raises_llm_error():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    llm = AgentLLM(AgentConfig(base_url=f"http://127.0.0.1:{port}/v1", model="m", stream=False))
    llm.client.max_retries = 0
    with pytest.raises(LLMError, match="failed"):
        list(llm.respond(MESSAGES, TOOLS))


def test_client_is_created_lazily():
    llm = AgentLLM(AgentConfig(base_url="http://llm.invalid/v1"))
    assert llm._client is None
    assert str(llm.client.base_url).startswith("http://llm.invalid/v1")
    assert llm.client is llm.client
