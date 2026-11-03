"""Progressive discovery: counts of sampled modifications of the editor graph, see assistant/progressive.py.

``WS /progressive/ws`` streams each count as soon as it is in (the protocol is documented
in assistant/progressive.py, "streaming protocol"); ``POST /progressive/sample`` returns
the whole result at once. Both share the Redis cache of complete results.
"""

import asyncio

from fastapi import APIRouter, Body, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from api.config import ManMan, ManManDep
from assistant.progressive import (
    PROGRESSIVE_CLIENT_MESSAGE,
    CancelToken,
    ProgressiveDone,
    ProgressiveError,
    ProgressiveRequest,
    ProgressiveResult,
    ProgressiveSample,
    SamplingCancelled,
    cache_key,
    complete,
    replay,
)

progressive_router = APIRouter(prefix="/progressive")


def _cached(manman: ManMan, key: str) -> ProgressiveResult | None:
    try:
        return manman.progressive_cache.get(key)
    except Exception as e:
        print("Progressive cache unavailable:", e)
        return None


def _store(manman: ManMan, key: str, result: ProgressiveResult):
    # results with failed/timed-out counts are not cached, a retry may succeed
    if complete(result):
        try:
            manman.progressive_cache.set(key, result)
        except Exception as e:
            print("Progressive cache unavailable:", e)


@progressive_router.post("/sample")
def sample_modifications(
    manman: ManManDep, request: ProgressiveRequest = Body(...)
) -> ProgressiveResult:
    key = f"{manman.config_id}:{cache_key(request)}"
    cached = _cached(manman, key)
    if cached is not None:
        return cached
    try:
        result = manman.progressive.sample(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _store(manman, key, result)
    return result


class _Run:
    """One sampling of a connection; its events are sent until it is cancelled."""

    def __init__(self, request_id: str | None):
        self.request_id = request_id
        self.token = CancelToken()


class _Connection:
    """Serialises the sends of the receive loop and the running sampling."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.open = True
        self._lock = asyncio.Lock()

    async def send(self, run: _Run, event: BaseModel):
        if not self.open or run.token.cancelled:
            return
        event = event.model_copy(update={"request_id": run.request_id})
        async with self._lock:
            try:
                await self.websocket.send_text(event.model_dump_json())
            except (WebSocketDisconnect, RuntimeError):
                self.open = False


async def _sample(connection: _Connection, manman: ManMan, run: _Run, request: ProgressiveRequest):
    """Stream a cached result, or run the (blocking) sampler in a worker thread and
    forward its events as they come; complete results are cached."""
    key = f"{manman.config_id}:{cache_key(request)}"
    loop = asyncio.get_running_loop()
    cached = await loop.run_in_executor(None, _cached, manman, key)
    if cached is not None:
        for event in replay(cached):
            await connection.send(run, event)
        return

    queue: asyncio.Queue = asyncio.Queue()

    def work() -> ProgressiveResult:
        try:
            return manman.progressive.stream(
                request, emit=lambda event: loop.call_soon_threadsafe(queue.put_nowait, event), cancel=run.token
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker = loop.run_in_executor(None, work)
    # done is held back until the result is cached, so a request after it hits the cache
    done = None
    while (event := await queue.get()) is not None:
        if isinstance(event, ProgressiveDone):
            done = event
        else:
            await connection.send(run, event)
    try:
        result = await worker
    except SamplingCancelled:
        return
    except ValueError as e:
        await connection.send(run, ProgressiveError(message=str(e)))
        return
    except Exception as e:
        print("Progressive sampling failed:", repr(e))
        await connection.send(run, ProgressiveError(message=f"Sampling failed: {e}"))
        return
    await loop.run_in_executor(None, _store, manman, key, result)
    if done is not None:
        await connection.send(run, done)


@progressive_router.websocket("/ws")
async def progressive_ws(websocket: WebSocket, manman: ManManDep):
    await websocket.accept()
    connection = _Connection(websocket)
    run: _Run | None = None
    # running samplings (a cancelled one finishes in the background)
    tasks: set[asyncio.Task] = set()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = PROGRESSIVE_CLIENT_MESSAGE.validate_json(raw)
            except ValidationError as e:
                await connection.send(_Run(None), ProgressiveError(message=f"Invalid message: {e}"))
                continue
            # a new request or a cancel stops the running sampling (pending counts dropped)
            if run is not None:
                run.token.cancel()
                run = None
            if isinstance(message, ProgressiveSample):
                run = _Run(message.request_id)
                task = asyncio.create_task(_sample(connection, manman, run, message.request))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
    except WebSocketDisconnect:
        pass
    finally:
        connection.open = False
        if run is not None:
            run.token.cancel()
