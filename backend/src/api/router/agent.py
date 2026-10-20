"""WebSocket endpoint of the agent chat, the protocol is documented in agent/protocol.py."""

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from agent.protocol import (
    CLIENT_MESSAGE,
    Cancel,
    Clear,
    Done,
    ErrorMessage,
    GraphSync,
    SessionInfo,
    UserMessage,
)
from agent.session import AgentSession, SessionBusy
from api.config import ManManDep

agent_router = APIRouter(prefix="/agent")


class _Connection:
    """Serialises sends of the receive loop and the running turn."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.open = True
        self._lock = asyncio.Lock()

    async def send(self, message: BaseModel):
        if not self.open:
            return
        async with self._lock:
            try:
                await self.websocket.send_text(message.model_dump_json())
            except (WebSocketDisconnect, RuntimeError):
                self.open = False


async def _run_turn(connection: _Connection, session: AgentSession, content: str):
    """Run the (blocking) agent turn in a worker thread and forward its messages."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def work():
        try:
            for message in session.run_turn(content):
                loop.call_soon_threadsafe(queue.put_nowait, message)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker = loop.run_in_executor(None, work)
    while (message := await queue.get()) is not None:
        await connection.send(message)
    await worker


@agent_router.websocket("/ws")
async def agent_ws(
    websocket: WebSocket,
    manman: ManManDep,
    session_id: str | None = Query(None),
):
    await websocket.accept()
    connection = _Connection(websocket)
    session, resumed = manman.agent_sessions.get_or_create(session_id)
    await connection.send(SessionInfo(session_id=session.session_id, resumed=resumed))

    turn: asyncio.Task | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = CLIENT_MESSAGE.validate_json(raw)
            except ValidationError as e:
                await connection.send(ErrorMessage(message=f"Invalid message: {e}"))
                continue
            busy = turn is not None and not turn.done()

            if isinstance(message, UserMessage):
                if busy:
                    await connection.send(
                        ErrorMessage(message="The agent is still working on the last message.")
                    )
                else:
                    turn = asyncio.create_task(_run_turn(connection, session, message.content))
            elif isinstance(message, GraphSync):
                try:
                    session.sync_graph(message.graph)
                except SessionBusy as e:
                    await connection.send(ErrorMessage(message=str(e)))
            elif isinstance(message, Cancel):
                session.cancel()
            elif isinstance(message, Clear):
                if busy:
                    session.cancel()
                    await turn
                session.clear()
                await connection.send(SessionInfo(session_id=session.session_id))
                await connection.send(Done(reason="cleared"))
    except WebSocketDisconnect:
        pass
    finally:
        connection.open = False
        # the session is kept for a reconnect, but its running turn is stopped
        if turn is not None and not turn.done():
            session.cancel()
