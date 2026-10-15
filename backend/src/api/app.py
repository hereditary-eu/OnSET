from logging import Logger

from fastapi import FastAPI, Query, UploadFile, Body
from fastapi.middleware.cors import CORSMiddleware

from typing import Any

from langchain_classic.smith.evaluation.config import EvalConfig

from api.config import DEFAULT_MANMAN, ManMan
from pydantic import BaseModel
from ontology import Graph
from explorative.exp_model import (
    SparqlQuery,
    Topic,
)
from api.router.classes import classes_router
from api.router.multimodal import multimodal_router
from api.router.nlp_helper import nlp_router
from eval_config import MultimodalConfig

logger = Logger(__name__)

manman = DEFAULT_MANMAN
logger.info(f"Using config: {manman.db_config}")

app = FastAPI(title="Ontology Provenance API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return "Welcome to the Ontology Provenance API"


@app.post("/sparql")
def sparql_query(query: SparqlQuery = Body(...)) -> list[dict[str, Any]]:
    return manman.ontology_manager.q_to_df_values(query.query).to_dict(orient="records")


@app.get("/sparql")
def sparql_query_get(query: str = Query(...)) -> dict[str, Any]:
    data = manman.ontology_manager.q_to_df_values(query).to_dict(orient="records")
    return {"results": {"bindings": data}}


class ConfigCollection(BaseModel):
    multimodal: MultimodalConfig
    name: str

    @classmethod
    def from_manman(cls, manman: ManMan):
        return cls(
            multimodal=manman.db_config.multimodal_config,
            name=manman.config_name,
            model_id=manman.db_config.model_id,
            model_quant=manman.db_config.model_quant,
        )


@app.get("/ontology/config")
def get_ontology_config() -> ConfigCollection:
    return ConfigCollection.from_manman(manman)


@app.post("/management/ontology")
def load_ontology(
    ontology: UploadFile,
):
    graph = Graph().parse(ontology.file, format="turtle")
    for prefix in manman.db_config.ttl_prefixes:
        graph.bind(prefix.ttl_prefix, prefix.uri)

    return {
        "ontology": ontology.filename,
        "prefixes": manman.db_config.ttl_prefixes,
    }


@app.get("/topics/root")
def get_topics_root(force_initialize: bool = Query(False)) -> Topic:
    logger.info("Fetching root topics")
    # guidance_man.initialize_topics(force_initialize)
    return manman.guidance_man.get_topic_tree()


app.include_router(classes_router)
app.include_router(nlp_router)
app.include_router(multimodal_router)
