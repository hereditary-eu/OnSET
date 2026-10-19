from fastapi import (
    APIRouter,
    Query,
    BackgroundTasks,
)

from api.config import ManManDep
from explorative.llm_query import QueryProgress, EnrichedEntitiesRelations



search_llm_router = APIRouter(prefix="/llm")


@search_llm_router.get("")
def get_llm_results(
    manman: ManManDep,
    background_tasks: BackgroundTasks,
    q: str = Query("working field of person"),
) -> QueryProgress:
    return manman.llm_query.start_query(q, background_tasks)


@search_llm_router.get("/running")
def get_llm_results_running(
    manman: ManManDep,
    query_id: str = Query(),
) -> QueryProgress | None:
    return manman.llm_query.query_progress(query_id)


@search_llm_router.get("/examples")
def get_llm_examples(manman: ManManDep) -> list[EnrichedEntitiesRelations]:
    return manman.llm_query.get_examples()
