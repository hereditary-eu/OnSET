"""Ontology builder API (/onto-builder), see builder/.

Builders are configured in the ``builders`` section of config.json. A session
(``/{builder_id}/sessions/{session_id}``) is created on first access (or, after a
restart, restored from its save; ``?create=false`` answers 404 instead of creating
an unknown session); its ontology and query are changed with PUT (and saved), its state is polled (``version``
changes with every ontology/query change, ``status`` reports the build), and
the agent chat runs over the WebSocket ``/{builder_id}/agent/ws`` with the
protocol of agent/protocol.py plus ``builder_state`` messages. The chat history is part
of the session (saved with it): a connection gets it as ``history`` after ``session``,
and only ``clear`` deletes it.
"""

import asyncio
import threading

from fastapi import APIRouter, Body, HTTPException, Path, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError

from agent.protocol import CLIENT_MESSAGE, Cancel, ChatHistory, Clear, Done, ErrorMessage, SessionInfo, UserMessage
from agent.session import SessionBusy
from api.router.agent import _Connection, _run_turn
from builder.agent import BuilderChat
from builder.corpus import Snippet
from builder.ontology import Ontology
from builder.session import (
    Builder, BuilderSession, DisambiguationState, ExportContent, InstanceProvenance, LinkCounts, QueryResult,
    SessionState, class_query,
)
from eval_config import CONFIG_FILE, DisambiguationSettings

builder_router = APIRouter(prefix="/onto-builder", tags=["onto-builder"])

_builders: dict[str, Builder] = {}
_lock = threading.Lock()


def get_builder(builder_id: str) -> Builder:
    with _lock:
        if builder_id not in _builders:
            if builder_id not in CONFIG_FILE.builders:
                raise HTTPException(404, f"Unknown ontology builder '{builder_id}'")
            _builders[builder_id] = Builder(builder_id, CONFIG_FILE.builder(builder_id))
        return _builders[builder_id]


def get_session(builder_id: str, session_id: str, create: bool = True) -> BuilderSession:
    builder = get_builder(builder_id)
    try:
        return builder.session(session_id, create=create)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, f"No session '{session_id}' in '{builder_id}'")


class BuilderSummary(BaseModel):
    id: str
    name: str
    description: str
    prefix: str


class DocumentOut(BaseModel):
    id: str
    title: str
    # its file, relative to the text set's path
    path: str
    text: str


@builder_router.get("/configs")
def list_builders() -> list[BuilderSummary]:
    out = []
    for key in CONFIG_FILE.builders:
        config = CONFIG_FILE.builder(key)
        out.append(BuilderSummary(id=key, name=config.name, description=config.description, prefix=config.prefix))
    return out


@builder_router.get("/{builder_id}/search")
def search_text(builder_id: str, q: str = Query(...), k: int = Query(20, ge=1, le=100)) -> list[Snippet]:
    return get_builder(builder_id).corpus.search(q, k)


@builder_router.get("/{builder_id}/documents/{doc_id:path}")
def get_document(builder_id: str, doc_id: str) -> DocumentOut:
    """A document of the corpus by its id (a ``Snippet``'s ``doc_id``, a ``SourceDocument``'s
    ``doc_id``); only ids of the loaded corpus, so no other file can be read."""
    doc = get_builder(builder_id).corpus.by_id.get(doc_id)
    if doc is None:
        raise HTTPException(404, f"No document '{doc_id}'")
    return DocumentOut(id=doc.id, title=doc.title, path=doc.path, text=doc.text)


@builder_router.get("/{builder_id}/sessions/{session_id}")
def get_state(
    builder_id: str, session_id: str,
    create: bool = Query(True, description="create an unknown session (else 404)"),
) -> SessionState:
    return get_session(builder_id, session_id, create).state()


@builder_router.put("/{builder_id}/sessions/{session_id}/ontology")
def put_ontology(builder_id: str, session_id: str, ontology: Ontology = Body(...)) -> SessionState:
    session = get_session(builder_id, session_id)
    session.set_ontology(ontology)
    return session.state()


class QueryIn(BaseModel):
    query: str
    # the visual query that generated ``query`` (frontend NodeLinkRepository JSON)
    visual_query: str | None = None


@builder_router.put("/{builder_id}/sessions/{session_id}/query")
def put_query(builder_id: str, session_id: str, body: QueryIn = Body(...)) -> SessionState:
    session = get_session(builder_id, session_id)
    session.set_query(body.query, body.visual_query)
    return session.state()


@builder_router.get("/{builder_id}/sessions/{session_id}/class-query/{class_id}")
def get_class_query(builder_id: str, session_id: str, class_id: str) -> QueryIn:
    try:
        return QueryIn(query=class_query(get_session(builder_id, session_id).ontology, class_id))
    except KeyError as e:
        raise HTTPException(404, str(e))


@builder_router.get("/{builder_id}/sessions/{session_id}/results")
def get_results(builder_id: str, session_id: str, limit: int = Query(500, ge=1, le=5000)) -> QueryResult:
    return get_session(builder_id, session_id).run_query(limit=limit)


@builder_router.get("/{builder_id}/sessions/{session_id}/provenance")
def get_provenance(
    builder_id: str, session_id: str, iri: str = Query(..., description="an instance of the KG"),
) -> InstanceProvenance:
    """The corpus documents an instance was extracted from (all of them for a merged instance),
    open them with ``/{builder_id}/documents/{doc_id}``."""
    return get_session(builder_id, session_id).provenance(iri)


@builder_router.get("/{builder_id}/sessions/{session_id}/link-counts")
def get_link_counts(builder_id: str, session_id: str) -> LinkCounts:
    """Triples of every link and field of the ontology in the KG (the query editor's link widths);
    refetch when the build status' triple count changes."""
    return get_session(builder_id, session_id).link_counts()


@builder_router.get("/{builder_id}/sessions/{session_id}/disambiguation")
def get_disambiguation(builder_id: str, session_id: str) -> DisambiguationState:
    """How extracted names are merged into instances, and the merges of the current build."""
    return get_session(builder_id, session_id).disambiguation_state()


@builder_router.put("/{builder_id}/sessions/{session_id}/disambiguation")
def put_disambiguation(
    builder_id: str, session_id: str, settings: DisambiguationSettings = Body(...),
) -> DisambiguationState:
    """Change the disambiguation settings (saved with the session); a change rebuilds the KG from scratch."""
    session = get_session(builder_id, session_id)
    session.set_disambiguation(settings)
    return session.disambiguation_state()


@builder_router.post("/{builder_id}/sessions/{session_id}/rebuild")
def rebuild(builder_id: str, session_id: str) -> SessionState:
    session = get_session(builder_id, session_id)
    session.rebuild()
    return session.state()


@builder_router.get("/{builder_id}/sessions/{session_id}/export")
def export_ttl(
    builder_id: str, session_id: str,
    content: ExportContent = Query("all"), prefix: str | None = Query(None),
) -> Response:
    ttl = get_session(builder_id, session_id).export(content, prefix)
    return Response(
        ttl, media_type="text/turtle",
        headers={"Content-Disposition": f'attachment; filename="{builder_id}-{content}.ttl"'},
    )


@builder_router.post("/{builder_id}/sessions/{session_id}/import")
def import_ttl(builder_id: str, session_id: str, file: UploadFile, prefix: str | None = Query(None)) -> SessionState:
    session = get_session(builder_id, session_id)
    try:
        session.import_ttl(file.file.read(), prefix or None)
    except Exception as e:
        raise HTTPException(400, f"Could not import {file.filename}: {e}")
    return session.state()


class SaveOut(BaseModel):
    path: str


@builder_router.post("/{builder_id}/sessions/{session_id}/save")
def save_session(
    builder_id: str, session_id: str,
    content: ExportContent = Query("all"), prefix: str | None = Query(None),
) -> SaveOut:
    return SaveOut(path=get_session(builder_id, session_id).save(content, prefix))


@builder_router.websocket("/{builder_id}/agent/ws")
async def builder_agent_ws(websocket: WebSocket, builder_id: str = Path(...), session_id: str = Query(...)):
    await websocket.accept()
    connection = _Connection(websocket)
    # restoring the session and creating the chat block: not on the event loop
    try:
        session = await run_in_threadpool(get_session, builder_id, session_id)
    except HTTPException as e:
        await connection.send(ErrorMessage(message=e.detail, fatal=True))
        await websocket.close()
        return

    def attach_chat() -> tuple[bool, BuilderChat, list[dict]]:
        with _lock:
            chat = session.chat
        if chat is None:
            # outside the global lock: reads the session's history under the session's lock
            new = BuilderChat(session)
            with _lock:
                chat = session.chat = session.chat or new
        transcript = session.chat_transcript()
        # resumed: the agent remembers earlier messages (also after a restart, from the save)
        return bool(transcript or len(chat.agent.history) > 1), chat, transcript

    resumed, chat, transcript = await run_in_threadpool(attach_chat)
    await connection.send(SessionInfo(session_id=session_id, resumed=resumed))
    await connection.send(ChatHistory(entries=transcript))

    turn: asyncio.Task | None = None
    try:
        while True:
            try:
                message = CLIENT_MESSAGE.validate_json(await websocket.receive_text())
            except ValidationError as e:
                await connection.send(ErrorMessage(message=f"Invalid message: {e}"))
                continue
            busy = turn is not None and not turn.done()
            if isinstance(message, UserMessage):
                if busy:
                    await connection.send(ErrorMessage(message="The agent is still working on the last message."))
                else:
                    turn = asyncio.create_task(_run_turn(connection, chat, message.content))
            elif isinstance(message, Cancel):
                chat.cancel()
            elif isinstance(message, Clear):
                if busy:
                    chat.cancel()
                    await turn
                try:
                    await run_in_threadpool(chat.clear)
                except SessionBusy as e:
                    # a turn of another connection to the session is still running
                    await connection.send(ErrorMessage(message=str(e)))
                    await connection.send(Done(reason="error"))
                    continue
                await connection.send(SessionInfo(session_id=session_id))
                await connection.send(Done(reason="cleared"))
            # graph_sync does not apply: the ontology is synced through PUT .../ontology
    except WebSocketDisconnect:
        pass
    finally:
        connection.open = False
        if turn is not None and not turn.done():
            chat.cancel()
