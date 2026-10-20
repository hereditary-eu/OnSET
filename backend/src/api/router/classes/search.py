from fastapi import (
    APIRouter,
    Body,
    Query,
)

from api.config import ManManDep
from assistant.assistant_model import QueryGraph, Operations
from explorative.exp_model import FuzzyQuery, FuzzyQueryResults
from api.router.classes.search_llm import search_llm_router


search_router = APIRouter(prefix="/search")
search_router.include_router(search_llm_router)


@search_router.post("")
def search_classes(
    manman: ManManDep,
    q: FuzzyQuery = Body(FuzzyQuery()),
) -> FuzzyQueryResults:
    return manman.guidance_man.search_fuzzy(q)


@search_router.post("/assistant")
def get_assistant_results(
    manman: ManManDep,
    q: str = Query("working field of person"),
    graph: QueryGraph = Body(...),
) -> Operations:
    return manman.assistant_cache.get_or_set(
        f"{q}_{graph.model_dump_json()}",
        lambda: manman.iterative_assistant.run_query(q, graph),
    )
