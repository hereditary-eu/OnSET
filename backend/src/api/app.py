from logging import Logger

from fastapi import FastAPI, Query, UploadFile, Body
from fastapi.middleware.cors import CORSMiddleware

from typing import Any

from api.config import CONFIG_PATH_PARAM, ManMan, ManManDep
from pydantic import BaseModel
from ontology import Graph
from explorative.exp_model import (
    SparqlQuery,
    Topic,
)
from api.router.classes import classes_router
from api.router.multimodal import multimodal_router
from api.router.nlp_helper import nlp_router
from eval_config import CONFIG_FILE, MultimodalConfig

logger = Logger(__name__)
logger.info(f"Available configs: {CONFIG_FILE.keys()}, default: {CONFIG_FILE.default}")

app = FastAPI(title="Ontology Provenance API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every ontology/data operation is scoped to a configuration, which is selected
# by the first URL segment: /{config_id}/... (see api.config.get_manman).
# Its own OpenAPI schema lives at /{config_id}/openapi.json and is the same for
# every configuration, so clients set /{config_id} as their base URL.
config_app = FastAPI(
    title="Ontology Provenance API (configuration scoped)",
    version="0.1.0",
    root_path_in_servers=False,
)


@app.get("/")
def read_root():
    return "Welcome to the Ontology Provenance API"


class ConfigSummary(BaseModel):
    id: str
    name: str
    description: str
    multimodal: bool
    default: bool


@app.get("/configs")
def list_configs() -> list[ConfigSummary]:
    summaries = []
    for key in CONFIG_FILE.keys():
        config = CONFIG_FILE.base(key)
        summaries.append(
            ConfigSummary(
                id=key,
                name=config.name,
                description=config.description,
                multimodal=config.multimodal_config is not None,
                default=key == CONFIG_FILE.default,
            )
        )
    return summaries


@config_app.post("/sparql")
def sparql_query(
    manman: ManManDep, query: SparqlQuery = Body(...)
) -> list[dict[str, Any]]:
    return manman.ontology_manager.q_to_df_values(query.query).to_dict(orient="records")


@config_app.get("/sparql")
def sparql_query_get(manman: ManManDep, query: str = Query(...)) -> dict[str, Any]:
    data = manman.ontology_manager.q_to_df_values(query).to_dict(orient="records")
    return {"results": {"bindings": data}}


class ConfigCollection(BaseModel):
    id: str
    name: str
    description: str
    multimodal: MultimodalConfig

    @classmethod
    def from_manman(cls, manman: ManMan):
        return cls(
            id=manman.config_id,
            name=manman.db_config.name,
            description=manman.db_config.description,
            multimodal=manman.config.multimodal_config,
        )


@config_app.get("/ontology/config")
def get_ontology_config(manman: ManManDep) -> ConfigCollection:
    return ConfigCollection.from_manman(manman)


@config_app.post("/management/ontology")
def load_ontology(
    manman: ManManDep,
    ontology: UploadFile,
):
    graph = Graph().parse(ontology.file, format="turtle")
    for prefix in manman.db_config.ttl_prefixes:
        graph.bind(prefix.ttl_prefix, prefix.uri)

    return {
        "ontology": ontology.filename,
        "prefixes": manman.db_config.ttl_prefixes,
    }


@config_app.get("/topics/root")
def get_topics_root(
    manman: ManManDep, force_initialize: bool = Query(False)
) -> Topic:
    logger.info("Fetching root topics")
    # guidance_man.initialize_topics(force_initialize)
    return manman.guidance_man.get_topic_tree()


config_app.include_router(classes_router)
config_app.include_router(nlp_router)
config_app.include_router(multimodal_router)

app.mount(f"/{{{CONFIG_PATH_PARAM}}}", config_app)
