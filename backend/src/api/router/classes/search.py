import io
import urllib
from urllib.parse import urlencode
import urllib.parse

from fastapi import (
    APIRouter,
    Body,
    Query,
)
import urllib3.util

from api.config import ManManDep
from assistant.model import QueryGraph, Operations
from api.validator import validate_image_file
from backend.src.explorative.data_tensor import DataTensor, DataTensorResp
from explorative.exp_model import FuzzyQuery, FuzzyQueryResults
from api.router.classes.search_llm import search_llm_router
from fastapi import UploadFile, File
from PIL import Image
from base64 import b64decode
import urllib3
import re


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
    key = f"{q}_{graph.model_dump_json()}"
    cache = manman.assistant_cache[key]
    if cache:
        return cache
    else:
        operations = manman.iterative_assistant.run_query(q, graph)
        manman.assistant_cache[key] = operations
        return operations
