"""Query sessions of the explore view (/{config_id}/query-sessions, query_session.py).

A session is created on first access (or restored from its save; ``?create=false`` answers 404
for an unknown session). The editor PUTs its query (SPARQL plus the serialized visual query) and
PATCHes its edit history; both are saved with the session, the history entries with the server's
timestamps. The sessions need none of the configuration's services, so these routes do not load
its ManMan.
"""

import threading
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from starlette.requests import HTTPConnection

from api.config import BUILDER_CONFIG_PREFIX, CONFIG_PATH_PARAM
from eval_config import CONFIG_FILE
from query_session import QueryIn, QuerySession, QuerySessionState, QuerySessionStore, QuerySessionSummary, config_dir_name
from session_history import HistoryInfo, HistoryRecord, HistoryUpdate

query_session_router = APIRouter(prefix="/query-sessions", tags=["query-sessions"])

_stores: dict[str, QuerySessionStore] = {}
_lock = threading.Lock()


def get_store(connection: HTTPConnection) -> QuerySessionStore:
    """The session store of the configuration in the URL (a configured KG or a builder session)."""
    config_id = connection.path_params.get(CONFIG_PATH_PARAM)
    if config_id is None or (config_id not in CONFIG_FILE.keys() and not config_id.startswith(BUILDER_CONFIG_PREFIX)):
        raise HTTPException(404, f"Unknown configuration '{config_id}'")
    with _lock:
        if config_id not in _stores:
            _stores[config_id] = QuerySessionStore(config_id, CONFIG_FILE.query_session_path() / config_dir_name(config_id))
        return _stores[config_id]


StoreDep = Annotated[QuerySessionStore, Depends(get_store)]


def get_session(store: QuerySessionStore, session_id: str, create: bool = True) -> QuerySession:
    try:
        return store.session(session_id, create=create)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, f"No query session '{session_id}'")


@query_session_router.get("")
def list_query_sessions(store: StoreDep, limit: int = Query(50, ge=1, le=500)) -> list[QuerySessionSummary]:
    """The saved sessions of the configuration, most recently changed first."""
    return store.list(limit)


@query_session_router.get("/{session_id}")
def get_query_session(
    store: StoreDep, session_id: str,
    create: bool = Query(True, description="create an unknown session (else 404)"),
) -> QuerySessionState:
    return get_session(store, session_id, create).state()


@query_session_router.put("/{session_id}/query")
def put_query_session_query(store: StoreDep, session_id: str, body: QueryIn = Body(...)) -> QuerySessionState:
    session = get_session(store, session_id)
    session.set_query(body.query, body.visual_query)
    return session.state()


@query_session_router.get("/{session_id}/history")
def get_query_session_history(store: StoreDep, session_id: str) -> list[HistoryRecord]:
    """The edit history of the query, oldest first, with the server's timestamps."""
    return get_session(store, session_id).history_records()


@query_session_router.patch("/{session_id}/history")
def patch_query_session_history(store: StoreDep, session_id: str, update: HistoryUpdate = Body(...)) -> HistoryInfo:
    """Add, replace (same ``timestamp``) or remove entries of the edit history (saved with the session)."""
    return get_session(store, session_id).update_history(update)
