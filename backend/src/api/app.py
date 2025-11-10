from fastapi import FastAPI, Query, UploadFile, Body
from fastapi.middleware.cors import CORSMiddleware

from typing import Any

from api.config import DEFAULT_MANMAN
from ontology import Graph
from explorative.exp_model import (
    SparqlQuery,
    Topic,
)
from api.router.classes import classes_router
from api.router.nlp_helper import nlp_router



manman = DEFAULT_MANMAN

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


@app.post("/management/ontology")
def load_ontology(
    ontology: UploadFile,
):
    brainteaser_graph = Graph().parse(ontology.file, format="turtle")
    for prefix in manman.db_config.ttl_prefixes:
        brainteaser_graph.bind(prefix.ttl_prefix, prefix.uri)
    return {"ontology": ontology.filename, "prefixes": manman.db_config.ttl_prefixes}


@app.get("/topics/root")
def get_topics_root(force_initialize: bool = Query(False)) -> Topic:
    # guidance_man.initialize_topics(force_initialize)
    return manman.guidance_man.get_topic_tree()

app.include_router(classes_router)
app.include_router(nlp_router)