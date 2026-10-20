"""LLM access of the agent: a tool-calling model behind the OpenAI Responses API.

``AgentLLM`` talks to an OpenAI-compatible server (a local ``llama-server``
started with ``--jinja`` in exploration/llm_tool_exploration.ipynb) and turns
one model response into a stream of ``LLMEvent``s:

- ``TextDelta`` / ``ReasoningDelta`` while the response is generated,
- one ``ResponseDone`` with the complete output items (messages, reasoning,
  function calls) as plain dicts, ready to be appended to the history.

Reasoning arrives as separate ``reasoning`` items when the server parses it;
otherwise ``ThinkTagSplitter`` separates inline ``<think>...</think>`` blocks
from the answer text. Anything implementing ``AgentLLMBase.respond`` (e.g. a
stub in tests) can drive the agent.
"""

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Iterator

from eval_config import AgentConfig


@dataclass
class TextDelta:
    item_id: str
    delta: str


@dataclass
class ReasoningDelta:
    item_id: str
    delta: str


@dataclass
class ResponseDone:
    output: list[dict] = field(default_factory=list)


LLMEvent = TextDelta | ReasoningDelta | ResponseDone


class LLMError(Exception):
    pass


def item_text(item: dict, part_types: tuple[str, ...]) -> str:
    """Concatenated text of an output item's content parts of the given types."""
    parts = item.get("content") or []
    if isinstance(parts, str):
        return parts
    return "".join(p.get("text", "") for p in parts if p.get("type") in part_types)


def message_text(item: dict) -> str:
    return item_text(item, ("output_text", "text", "input_text"))


def reasoning_text(item: dict) -> str:
    text = item_text(item, ("reasoning_text",))
    if not text:
        text = "".join(s.get("text", "") for s in item.get("summary") or [])
    return text


class ThinkTagSplitter:
    """Splits streamed text into answer and ``<think>`` reasoning parts.

    Tags may be split across deltas, so a possible tag prefix at the end of a
    delta is held back until the next one.
    """

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self):
        self.thinking = False
        self._pending = ""

    def feed(self, delta: str) -> list[tuple[bool, str]]:
        """(is_thinking, text) chunks of ``delta``."""
        text = self._pending + delta
        self._pending = ""
        chunks: list[tuple[bool, str]] = []
        while text:
            tag = self.CLOSE if self.thinking else self.OPEN
            index = text.find(tag)
            if index >= 0:
                if index > 0:
                    chunks.append((self.thinking, text[:index]))
                text = text[index + len(tag) :]
                self.thinking = not self.thinking
                continue
            # hold back a suffix that might be the start of the tag
            keep = 0
            for n in range(min(len(tag) - 1, len(text)), 0, -1):
                if tag.startswith(text[-n:]):
                    keep = n
                    break
            if keep:
                self._pending = text[-keep:]
                text = text[:-keep]
            if text:
                chunks.append((self.thinking, text))
            break
        return chunks

    def flush(self) -> list[tuple[bool, str]]:
        pending, self._pending = self._pending, ""
        return [(self.thinking, pending)] if pending else []

    @classmethod
    def split(cls, text: str) -> tuple[str, str]:
        """(reasoning, answer) of a complete text."""
        splitter = cls()
        chunks = splitter.feed(text) + splitter.flush()
        thinking = "".join(t for is_thinking, t in chunks if is_thinking)
        answer = "".join(t for is_thinking, t in chunks if not is_thinking)
        return thinking, answer


class AgentLLMBase:
    def respond(self, messages: list[dict], tools: list[dict]) -> Iterator[LLMEvent]:
        """Generate one response to the conversation ``messages`` (input items)."""
        raise NotImplementedError


def _dump(obj: Any) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    return dict(obj)


class AgentLLM(AgentLLMBase):
    """OpenAI-compatible tool-calling model, the client is created on first use."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._client = None
        self._model: str | None = config.model
        self._lock = Lock()

    @property
    def client(self):
        with self._lock:
            if self._client is None:
                from openai import OpenAI

                self._client = OpenAI(
                    base_url=self.config.base_url, api_key=self.config.api_key
                )
            return self._client

    @property
    def model(self) -> str:
        if self._model is None:
            models = self.client.models.list().data
            if not models:
                raise LLMError(f"No model served at {self.config.base_url}")
            self._model = models[0].id
        return self._model

    def _request(self, messages: list[dict], tools: list[dict]) -> dict:
        request = {"model": self.model, "input": messages, "tools": tools}
        if self.config.temperature is not None:
            request["temperature"] = self.config.temperature
        return request

    def respond(self, messages: list[dict], tools: list[dict]) -> Iterator[LLMEvent]:
        try:
            if self.config.stream:
                yield from self._respond_stream(messages, tools)
            else:
                response = self.client.responses.create(**self._request(messages, tools))
                yield ResponseDone(output=[_dump(item) for item in response.output])
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"LLM request to {self.config.base_url} failed: {e}") from e

    def _respond_stream(self, messages: list[dict], tools: list[dict]) -> Iterator[LLMEvent]:
        done_items: dict[int, dict] = {}
        final_output: list[dict] | None = None
        stream = self.client.responses.create(**self._request(messages, tools), stream=True)
        for event in stream:
            kind = event.type
            if kind == "response.output_text.delta":
                yield TextDelta(item_id=event.item_id, delta=event.delta)
            elif kind in (
                "response.reasoning_text.delta",
                "response.reasoning_summary_text.delta",
            ):
                yield ReasoningDelta(item_id=event.item_id, delta=event.delta)
            elif kind == "response.output_item.done":
                done_items[event.output_index] = _dump(event.item)
            elif kind == "response.completed":
                final_output = [_dump(item) for item in event.response.output or []]
            elif kind in ("response.failed", "response.incomplete"):
                error = getattr(event.response, "error", None) or getattr(
                    event.response, "incomplete_details", None
                )
                raise LLMError(f"Response {kind.split('.')[-1]}: {error}")
            elif kind == "error":
                raise LLMError(f"LLM stream error: {event.message}")
        if not final_output:
            final_output = [done_items[i] for i in sorted(done_items)]
        yield ResponseDone(output=final_output)
