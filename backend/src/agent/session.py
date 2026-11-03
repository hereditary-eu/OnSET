"""Server-side agent chat sessions: the synced query graph plus the chat history.

A session outlives its WebSocket connection, so a frontend that reconnects
with the same ``session_id`` continues the conversation. ``AgentSessionStore``
keeps the most recently used sessions of one configuration.
"""

import threading
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING, Callable, Iterator

from agent.agent import GraphAgent
from agent.graph_tools import GraphEditorTools
from agent.llm import AgentLLMBase
from agent.protocol import Done, ErrorMessage, ServerMessage
from assistant.assistant_model import QueryGraph
from eval_config import AgentConfig

if TYPE_CHECKING:
    from explorative.explorative_support import GuidanceManager
    from ontology import OntologyManager


class SessionBusy(Exception):
    pass


class AgentSession:
    def __init__(
        self,
        session_id: str,
        llm: AgentLLMBase,
        ontology_manager: "OntologyManager",
        guidance: "GuidanceManager",
        config: AgentConfig,
    ):
        self.session_id = session_id
        self.tools = GraphEditorTools(
            ontology_manager,
            guidance,
            retrieve_k=config.retrieve_k,
            constraint_tools=config.constraint_tools,
        )
        self.agent = GraphAgent(llm, self.tools, max_steps=config.max_steps)
        self._lock = threading.Lock()
        self._busy = False
        self._cancel = threading.Event()

    @property
    def graph(self) -> QueryGraph:
        return self.tools.graph

    @property
    def busy(self) -> bool:
        return self._busy

    def sync_graph(self, graph: QueryGraph):
        """Replace the server graph by the editor's graph."""
        with self._lock:
            if self._busy:
                raise SessionBusy("The agent is editing the graph, sync rejected.")
            self.tools.graph = graph
            self.tools.prune_details()

    def cancel(self):
        self._cancel.set()

    def clear(self):
        with self._lock:
            if self._busy:
                raise SessionBusy("Cancel the running turn before clearing.")
            self.agent.reset()
            self.tools.graph = QueryGraph()
            self.tools.prune_details()

    def run_turn(self, content: str) -> Iterator[ServerMessage]:
        """Messages of one agent turn, always ending with ``done``."""
        with self._lock:
            if self._busy:
                yield ErrorMessage(message="The agent is still working on the last message.")
                yield Done(reason="error")
                return
            self._busy = True
            self._cancel.clear()
        try:
            yield from self.agent.run_turn(content, cancelled=self._cancel.is_set)
        except Exception as e:
            yield ErrorMessage(message=f"Agent failed: {type(e).__name__}: {e}")
            yield Done(reason="error")
        finally:
            with self._lock:
                self._busy = False


class AgentSessionStore:
    """The ``max_sessions`` most recently used sessions, by id."""

    def __init__(self, factory: Callable[[str], AgentSession], max_sessions: int = 64):
        self.factory = factory
        self.max_sessions = max_sessions
        self._sessions: OrderedDict[str, AgentSession] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str | None = None) -> tuple[AgentSession, bool]:
        """The session ``session_id`` (resumed=True) or a new one."""
        with self._lock:
            if session_id and session_id in self._sessions:
                self._sessions.move_to_end(session_id)
                return self._sessions[session_id], True
            session = self.factory(session_id or uuid.uuid4().hex)
            self._sessions[session.session_id] = session
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
            return session, False
