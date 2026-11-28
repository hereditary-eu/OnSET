"""Sessions of the visual query editor (the explore view), the counterpart of the ontology
builder's sessions (builder/session.py) for querying a configured KG.

A session holds the editor's current query (SPARQL and the serialized visual query, the
frontend's NodeLinkRepository) and its edit history (session_history.py). Sessions are saved on
every change, as ``<query_session_dir>/<config dir>/<session_id>.json`` and
``<session_id>.history.json``, so a session can be reopened by its id after a restart or from
another browser. ``QuerySessionStore`` keeps the recently used sessions of one configuration.
"""

import json
import re
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from pydantic import BaseModel

from session_history import (
    SESSION_ID_PATTERN, EditHistory, HistoryInfo, HistoryRecord, HistoryUpdate, check_session_id, now_ms, write_atomic,
)

HISTORY_SUFFIX = ".history.json"


def config_dir_name(config_id: str) -> str:
    """A directory name for a config id (builder session configs contain ``:``)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", config_id)


class QueryIn(BaseModel):
    query: str
    # the visual query that generated ``query`` (frontend NodeLinkRepository, serialized)
    visual_query: str | None = None


class QuerySessionState(BaseModel):
    session_id: str
    config_id: str
    # bumped on every change of the query (clients refetch the state)
    version: int
    query: str = ""
    visual_query: str | None = None
    # server epoch ms of the session's creation and its last change (query or history)
    created_at: int
    updated_at: int
    history: HistoryInfo


class QuerySessionSummary(BaseModel):
    session_id: str
    created_at: int
    updated_at: int
    query: str
    history_entries: int


class QuerySession:
    def __init__(self, session_id: str, config_id: str, save_dir: Path):
        self.session_id = check_session_id(session_id)
        self.config_id = config_id
        self.save_dir = save_dir
        self.query = ""
        self.visual_query: str | None = None
        self.version = 0
        self.created_at = self.updated_at = now_ms()
        self.history = EditHistory()
        self._lock = threading.RLock()
        self.restore()

    @property
    def state_path(self) -> Path:
        return self.save_dir / f"{self.session_id}.json"

    @property
    def history_path(self) -> Path:
        return self.save_dir / f"{self.session_id}{HISTORY_SUFFIX}"

    def state(self) -> QuerySessionState:
        with self._lock:
            return QuerySessionState(
                session_id=self.session_id, config_id=self.config_id, version=self.version,
                query=self.query, visual_query=self.visual_query,
                created_at=self.created_at, updated_at=self.updated_at, history=self.history.info(),
            )

    def summary(self) -> QuerySessionSummary:
        with self._lock:
            return QuerySessionSummary(
                session_id=self.session_id, created_at=self.created_at, updated_at=self.updated_at,
                query=self.query, history_entries=len(self.history),
            )

    def set_query(self, query: str, visual_query: str | None = None):
        with self._lock:
            if (query, visual_query) == (self.query, self.visual_query):
                return
            self.query, self.visual_query = query, visual_query
            self.version += 1
            self.updated_at = now_ms()
            self.persist()

    def history_records(self) -> list[HistoryRecord]:
        return self.history.records()

    def update_history(self, update: HistoryUpdate) -> HistoryInfo:
        with self._lock:
            if self.history.apply(update):
                self.updated_at = now_ms()
                write_atomic(self.history_path, self.history.dumps())
                # the state file has the session's times (and makes it listed)
                self.persist()
            return self.history.info()

    def persist(self):
        with self._lock:
            state = {
                "query": self.query, "visual_query": self.visual_query,
                "created_at": self.created_at, "updated_at": self.updated_at,
                # for listing the saved sessions without reading their histories
                "history_entries": len(self.history),
            }
            write_atomic(self.state_path, json.dumps(state))

    def restore(self) -> bool:
        if self.history_path.exists():
            self.history = EditHistory(json.loads(self.history_path.read_text()))
        if not self.state_path.exists():
            return False
        state = json.loads(self.state_path.read_text())
        self.query = state.get("query", "")
        self.visual_query = state.get("visual_query")
        self.created_at = state.get("created_at", self.created_at)
        self.updated_at = state.get("updated_at", self.created_at)
        return True


class QuerySessionStore:
    """The query sessions of one configuration: loaded ones (LRU) and saved ones."""

    def __init__(self, config_id: str, save_dir: Path, max_sessions: int = 32):
        self.config_id = config_id
        self.save_dir = Path(save_dir)
        self.max_sessions = max_sessions
        self.sessions: OrderedDict[str, QuerySession] = OrderedDict()
        self._lock = threading.Lock()

    def exists(self, session_id: str) -> bool:
        return session_id in self.sessions or (self.save_dir / f"{check_session_id(session_id)}.json").exists()

    def session(self, session_id: str | None = None, create: bool = True) -> QuerySession:
        """The session ``session_id``: loaded, else restored from its save, else (``create``) a
        new one; KeyError if it does not exist and ``create`` is off, ValueError for an invalid id."""
        session_id = check_session_id(session_id or uuid.uuid4().hex)
        with self._lock:
            if session_id in self.sessions:
                self.sessions.move_to_end(session_id)
                return self.sessions[session_id]
            if not create and not self.exists(session_id):
                raise KeyError(f"No session '{session_id}'")
            session = self.sessions[session_id] = QuerySession(session_id, self.config_id, self.save_dir)
            while len(self.sessions) > self.max_sessions:
                self.sessions.popitem(last=False)
            return session

    def list(self, limit: int = 50) -> list[QuerySessionSummary]:
        """The saved sessions (and loaded ones with changes), most recently changed first."""
        summaries: dict[str, QuerySessionSummary] = {}
        if self.save_dir.is_dir():
            for path in self.save_dir.glob("*.json"):
                session_id = path.name.removesuffix(".json")
                if path.name.endswith(HISTORY_SUFFIX) or not SESSION_ID_PATTERN.fullmatch(session_id):
                    continue
                try:
                    state = json.loads(path.read_text())
                except (OSError, ValueError):
                    continue
                summaries[session_id] = QuerySessionSummary(
                    session_id=session_id, created_at=state.get("created_at", 0),
                    updated_at=state.get("updated_at", 0), query=state.get("query", ""),
                    history_entries=state.get("history_entries", 0),
                )
        with self._lock:
            loaded = list(self.sessions.values())
        for session in loaded:
            if session.state_path.exists():
                summaries[session.session_id] = session.summary()
        return sorted(summaries.values(), key=lambda s: s.updated_at, reverse=True)[:limit]
