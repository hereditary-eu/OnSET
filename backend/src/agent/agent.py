"""The tool-calling loop of the graph editing agent.

One user message is one turn: the model is called repeatedly, every function
call it makes is executed on the query graph and its result is fed back,
until it answers without calling a tool (or ``max_steps`` is reached). The
turn is a generator of protocol messages (agent.protocol), so the caller
decides how to deliver them.

The history holds Responses API input items as plain dicts: the system prompt,
user messages, and the model's output items (reasoning, messages, function
calls) followed by the function_call_output of each call.
"""

import json
import uuid
from typing import Callable, Iterator

from agent.graph_tools import GraphEditorTools
from agent.llm import (
    AgentLLMBase,
    LLMError,
    ReasoningDelta,
    ResponseDone,
    TextDelta,
    ThinkTagSplitter,
    message_text,
    reasoning_text,
)
from agent.protocol import (
    AssistantMessage,
    Done,
    ErrorMessage,
    GraphState,
    ServerMessage,
    Thinking,
    ToolCall,
    describe_graph,
    diff_graphs,
)

SYSTEM_PROMPT = """You are an agentic editor of a visual SPARQL query graph over a knowledge graph.
The query graph consists of subjects (nodes, each an ontology class) and links (ontology properties) between them.
Always keep in mind the following rules when editing the graph:
- The class hierarchy is always considered in the search results, so if a link is valid for a superclass, it is also valid for its subclasses, e.g. a link valid for "Person" is also valid for "Scientist", and a link for owl:Thing is valid for all classes - this holds for both sides of the link.
- When searching for new links always start from one of the existing subjects in the graph, i.e. you can use their URIs to find links that connect them to other classes.
- You should never add a subject or link that is not in the ontology, and it should never invent a URI. Always search for the most relevant classes and links before adding anything; only use URIs returned by a search.
- You can also search for links between two existing subjects in the graph, and add them if they are relevant.
For each user request:
1. Inspect the current query graph (it is given with the request when it changed, or call get_query_graph).
2. Always search for the most relevant classes (search_classes) and links (search_links) before adding anything; only use URIs returned by a search. If they do not fit the request, you can also search for general classes by using `include_thing`.
3. Edit the graph with add_subject, add_link, remove_subject and remove_link. Subjects and links are referenced by their graph "id", but searched by their ontology URI. If a subject or link is removed, all its connected links or subjects are also removed.
4. Finish with a short answer summarising what you changed.

You do not speculate about the class hierarchy, as all tool calls are validated against the ontology, each response of the tools is guaranteed to be correct and can be, given the intent, directly used to edit the graph. You can also use the search results to find more relevant classes and links, and you can always search for links between two existing subjects in the graph.
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class _StreamIds:
    """Keeps the ids of streamed text blocks so their final frame reuses them.

    Servers that stream without item ids would otherwise produce a second,
    duplicate block for the final frame.
    """

    def __init__(self, step_prefix: str):
        self.step_prefix = step_prefix
        self.streamed: dict[str, list[str]] = {"thinking": [], "message": []}

    def for_delta(self, kind: str, item_id: str | None) -> str:
        block_id = item_id or f"{self.step_prefix}_{kind}"
        if block_id not in self.streamed[kind]:
            self.streamed[kind].append(block_id)
        return block_id

    def for_final(self, kind: str, item_id: str | None, index: int) -> str:
        if item_id and item_id in self.streamed[kind]:
            self.streamed[kind].remove(item_id)
            return item_id
        if self.streamed[kind]:
            return self.streamed[kind].pop(0)
        return item_id or f"{self.step_prefix}_{kind}_{index}"


class GraphAgent:
    def __init__(
        self,
        llm: AgentLLMBase,
        tools: GraphEditorTools,
        max_steps: int = 12,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.reset()

    def reset(self):
        self.history: list[dict] = [
            {
                "role": "system",
                "content": self.system_prompt,
                # + "\n"
                # + json.dumps(self.tools.definitions(), indent=2),
            }
        ]
        # the graph as the model last saw it, to only repeat it when it changed
        self._seen_graph: str | None = None

    def _user_content(self, content: str) -> str:
        graph = describe_graph(self.tools.graph)
        if graph == self._seen_graph:
            return content
        self._seen_graph = graph
        return f"{content}\n\nCurrent query graph:\n{graph}"

    def run_turn(
        self, content: str, cancelled: Callable[[], bool] = lambda: False
    ) -> Iterator[ServerMessage]:
        self.history.append({"role": "user", "content": self._user_content(content)})
        turn_id = new_id("turn")
        try:
            for step in range(self.max_steps):
                if cancelled():
                    yield Done(reason="cancelled")
                    return
                output = yield from self._generate(f"{turn_id}_{step}")
                self.history.extend(output)
                calls = [item for item in output if item.get("type") == "function_call"]
                if not calls:
                    yield Done(reason="completed")
                    return
                graph_changed = False
                for call in calls:
                    if cancelled():
                        # every call needs an output, or the history is invalid
                        self._add_output(
                            call, json.dumps({"error": "Cancelled by the user."})
                        )
                        continue
                    graph_changed |= yield from self._run_tool(call)
                if graph_changed:
                    self._seen_graph = describe_graph(self.tools.graph)
                    yield GraphState(
                        graph=self.tools.graph.model_copy(deep=True),
                        details=self.tools.details_for(self.tools.graph),
                    )
            yield ErrorMessage(
                message=f"Stopped after {self.max_steps} steps without a final answer."
            )
            yield Done(reason="max_steps")
        except LLMError as e:
            yield ErrorMessage(message=str(e))
            yield Done(reason="error")

    def _generate(self, step_prefix: str) -> Iterator[ServerMessage]:
        """Stream one model response, returns its output items."""
        ids = _StreamIds(step_prefix)
        splitter = ThinkTagSplitter()
        output: list[dict] = []

        def text_chunks(item_id: str | None, chunks) -> Iterator[ServerMessage]:
            for is_thinking, text in chunks:
                if is_thinking:
                    block = ids.for_delta(
                        "thinking", f"{item_id}:think" if item_id else None
                    )
                    yield Thinking(id=block, delta=text)
                else:
                    yield AssistantMessage(
                        id=ids.for_delta("message", item_id), delta=text
                    )

        last_text_item = None
        for event in self.llm.respond(self.history, self.tools.definitions()):
            if isinstance(event, TextDelta):
                last_text_item = event.item_id
                yield from text_chunks(event.item_id, splitter.feed(event.delta))
            elif isinstance(event, ReasoningDelta):
                yield Thinking(
                    id=ids.for_delta("thinking", event.item_id), delta=event.delta
                )
            elif isinstance(event, ResponseDone):
                output = event.output
        yield from text_chunks(last_text_item, splitter.flush())

        for index, item in enumerate(output):
            item_id = item.get("id")
            if item.get("type") == "reasoning":
                text = reasoning_text(item)
                if text:
                    block = ids.for_final("thinking", item_id, index)
                    yield Thinking(id=block, content=text, final=True)
            elif item.get("type") == "message":
                thinking, answer = ThinkTagSplitter.split(message_text(item))
                if thinking:
                    block = ids.for_final(
                        "thinking", f"{item_id}:think" if item_id else None, index
                    )
                    yield Thinking(id=block, content=thinking, final=True)
                block = ids.for_final("message", item_id, index)
                yield AssistantMessage(id=block, content=answer.strip(), final=True)
        return output

    def _add_output(self, call: dict, output: str):
        self.history.append(
            {
                "type": "function_call_output",
                "call_id": call["call_id"],
                "output": output,
            }
        )

    def _run_tool(self, call: dict) -> Iterator[ServerMessage]:
        """Execute one function call, returns whether it changed the graph."""
        name = call.get("name", "")
        call_id = call.get("call_id") or new_id("call")
        call["call_id"] = call_id
        try:
            arguments = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {"raw": call.get("arguments")}
        if not isinstance(arguments, dict):
            arguments = {"raw": arguments}
        yield ToolCall(call_id=call_id, name=name, arguments=arguments)

        before = self.tools.graph.model_copy(deep=True)
        result = self.tools.call(name, call.get("arguments"))
        change = diff_graphs(before, self.tools.graph)
        self._add_output(call, result.for_model())
        yield ToolCall(
            call_id=call_id,
            name=name,
            arguments=arguments,
            status="success" if result.ok else "error",
            result=result.output,
            error=result.error,
            changes=None if change.empty else change,
            details=None if change.empty else self.tools.details_for(change.added),
        )
        return not change.empty
