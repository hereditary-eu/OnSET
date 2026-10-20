"""WebSocket protocol of the agent chat (``/{config_id}/agent/ws``).

One connection per frontend session. Every frame is one JSON object whose
``type`` field selects the message (pydantic discriminated unions below). The
query graph is always exchanged as ``assistant_model.QueryGraph``; the
frontend converts it from/to its editor representation
(frontend/src/utils/agent/graph_sync.ts), and its TS mirror of this protocol
is frontend/src/utils/agent/protocol.ts.

Connecting: ``/{config_id}/agent/ws?session_id=<id>``. The server keeps the
session (synced graph + chat history) for a while after a disconnect, so a
reconnect with the same id resumes it. The first frame is always ``session``.

Client -> server
    user_message  {content}            run one agent turn on the request
    graph_sync    {graph}              full editor graph; replaces the server
                                       graph (ignored with an error while busy)
    cancel        {}                   stop the running turn after the current step
    clear         {}                   reset chat history and server graph

Server -> client (per turn, in order of occurrence)
    session          {session_id, resumed}  after connecting and after ``clear``
    thinking         {id, delta, content, final}
                                        reasoning of the model; streamed as
                                        deltas, ``final`` carries the full text
    assistant_message {id, delta, content, final}
                                        answer text, same streaming scheme
                                        (one final frame if streaming is off)
    tool_call        {call_id, name, arguments, status, result, error, changes}
                                        sent with status "running" before and
                                        "success"/"error" after the tool ran;
                                        ``changes`` holds the subjects/links it
                                        added/removed as a mini graph
    graph_state      {graph, details}   full server graph after the agent
                                        changed it; ``details`` carries the
                                        ontology data of agent-added elements
    error            {message, fatal}   e.g. busy, invalid frame, LLM failure
    done             {reason}           the turn (or clear) finished

A turn always ends with ``done``. Ids in ``graph``/``changes`` are the ids of
the frontend editor (synced via ``graph_sync``) or new ids the agent assigned.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from assistant.assistant_model import AssistantLink, AssistantSubject, QueryGraph
from model import Subject, SubjectLink

# --- graph payloads ---


class GraphDetails(BaseModel):
    """Ontology data (keyed by graph id) the editor needs to render new elements."""

    subjects: dict[str, Subject] = Field({})
    links: dict[str, SubjectLink] = Field({})


class GraphChange(BaseModel):
    """Subjects/links a tool call added or removed, renderable as a mini graph."""

    added: QueryGraph = Field(default_factory=QueryGraph)
    removed: QueryGraph = Field(default_factory=QueryGraph)
    # unchanged subjects the changed links attach to
    context: list[AssistantSubject] = Field([])

    @property
    def empty(self) -> bool:
        return not (
            self.added.subjects
            or self.added.links
            or self.removed.subjects
            or self.removed.links
        )


# --- client -> server ---


class UserMessage(BaseModel):
    type: Literal["user_message"] = "user_message"
    content: str


class GraphSync(BaseModel):
    type: Literal["graph_sync"] = "graph_sync"
    graph: QueryGraph


class Cancel(BaseModel):
    type: Literal["cancel"] = "cancel"


class Clear(BaseModel):
    type: Literal["clear"] = "clear"


ClientMessage = Annotated[
    UserMessage | GraphSync | Cancel | Clear, Field(discriminator="type")
]
CLIENT_MESSAGE = TypeAdapter(ClientMessage)


# --- server -> client ---


class SessionInfo(BaseModel):
    type: Literal["session"] = "session"
    session_id: str
    # True if an existing server session (history + graph) was picked up
    resumed: bool = False


class StreamedText(BaseModel):
    # id of the text block, deltas with the same id belong together
    id: str
    delta: str = ""
    # full text, set on the final frame
    content: str | None = None
    final: bool = False


class Thinking(StreamedText):
    type: Literal["thinking"] = "thinking"


class AssistantMessage(StreamedText):
    type: Literal["assistant_message"] = "assistant_message"


class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, Any] = Field({})
    status: Literal["running", "success", "error"] = "running"
    result: Any = None
    error: str | None = None
    changes: GraphChange | None = None
    details: GraphDetails | None = None


class GraphState(BaseModel):
    type: Literal["graph_state"] = "graph_state"
    graph: QueryGraph
    details: GraphDetails = Field(default_factory=GraphDetails)


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
    # the connection is closed after a fatal error
    fatal: bool = False


class Done(BaseModel):
    type: Literal["done"] = "done"
    reason: Literal["completed", "max_steps", "cancelled", "error", "cleared"] = (
        "completed"
    )


ServerMessage = Annotated[
    SessionInfo
    | Thinking
    | AssistantMessage
    | ToolCall
    | GraphState
    | ErrorMessage
    | Done,
    Field(discriminator="type"),
]
SERVER_MESSAGE = TypeAdapter(ServerMessage)


# --- graph helpers ---


def diff_graphs(before: QueryGraph, after: QueryGraph) -> GraphChange:
    """Subjects/links (by id) that are only in ``after`` (added) or only in ``before`` (removed)."""
    before_subjects = {s.id: s for s in before.subjects}
    after_subjects = {s.id: s for s in after.subjects}
    before_links = {l.id: l for l in before.links}
    after_links = {l.id: l for l in after.links}

    change = GraphChange(
        added=QueryGraph(
            subjects=[s for i, s in after_subjects.items() if i not in before_subjects],
            links=[l for i, l in after_links.items() if i not in before_links],
        ),
        removed=QueryGraph(
            subjects=[s for i, s in before_subjects.items() if i not in after_subjects],
            links=[l for i, l in before_links.items() if i not in after_links],
        ),
    )
    changed_ids = {s.id for s in change.added.subjects + change.removed.subjects}
    context: dict[str, AssistantSubject] = {}
    for link in change.added.links + change.removed.links:
        for subject_id in (link.from_subject_id, link.to_subject_id):
            subject = after_subjects.get(subject_id) or before_subjects.get(subject_id)
            if subject is not None and subject_id not in changed_ids:
                context[subject_id] = subject
    change.context = list(context.values())
    return change


def describe_graph(graph: QueryGraph) -> str:
    """Compact JSON of a graph for the model's context."""
    return graph.model_dump_json(
        include={
            "subjects": {"__all__": {"id", "uri", "label", "subqueries"}},
            "links": {"__all__": {"id", "uri", "label", "from_subject_id", "to_subject_id"}},
        }
    )


__all__ = [
    "AssistantLink",
    "AssistantSubject",
    "QueryGraph",
    "GraphDetails",
    "GraphChange",
    "UserMessage",
    "GraphSync",
    "Cancel",
    "Clear",
    "ClientMessage",
    "CLIENT_MESSAGE",
    "SessionInfo",
    "Thinking",
    "AssistantMessage",
    "ToolCall",
    "GraphState",
    "ErrorMessage",
    "Done",
    "ServerMessage",
    "SERVER_MESSAGE",
    "diff_graphs",
    "describe_graph",
]
