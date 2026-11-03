"""Progressive discovery: counts of sampled modifications of the editor graph, see assistant/progressive.py."""

from fastapi import APIRouter, Body, HTTPException

from api.config import ManManDep
from assistant.progressive import ProgressiveRequest, ProgressiveResult, cache_key, complete

progressive_router = APIRouter(prefix="/progressive")


@progressive_router.post("/sample")
def sample_modifications(
    manman: ManManDep, request: ProgressiveRequest = Body(...)
) -> ProgressiveResult:
    key = f"{manman.config_id}:{cache_key(request)}"
    try:
        cached = manman.progressive_cache.get(key)
    except Exception as e:
        print("Progressive cache unavailable:", e)
        cached = None
    if cached is not None:
        return cached
    try:
        result = manman.progressive.sample(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # results with failed/timed-out counts are not cached, a retry may succeed
    if complete(result):
        try:
            manman.progressive_cache.set(key, result)
        except Exception as e:
            print("Progressive cache unavailable:", e)
    return result
