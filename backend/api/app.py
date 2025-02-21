from fastapi import FastAPI, Query, File, UploadFile, Body, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from typing import Any
from rdflib.plugins.stores.sparqlstore import SPARQLStore

from model import Subject, SparseOutLinks, Instance, Property
from ontology import OntologyManager, OntologyConfig, Graph, InstanceQuery
from datasetmatcher import DatasetManager
from explorative.explorative_support import GuidanceManager
from explorative.exp_model import (
    SparqlQuery,
    Topic,
    SubjectLink,
    FuzzyQuery,
    FuzzyQueryResults,
)
from explorative.llm_query import LLMQuery, QueryProgress, EnrichedEntitiesRelations
from eval_config import BTO_CONFIGS, DBPEDIA_CONFIGS, UNIPROT_CONFIGS
from initiator import InitatorManager

db_config = DBPEDIA_CONFIGS[0]

base_path = "../data"
onto_path = f"{base_path}/hero-ontology/hereditary_clinical.ttl"


# graph = Graph().parse(onto_path, format="turtle")
# graph.bind("bto", "http://www.semanticweb.org/ontologies/2020/3/bto#")
# graphdb
# store = SPARQLStore(
#     "http://localhost:7200/repositories/dpedia",
#     method="POST_FORM",
#     params={"infer": False, "sameAs": False},
# )
# store = SPARQLStore(
#     "http://localhost:3030/dbpedia/query",
#     method="POST_FORM",
#     params={"infer": False, "sameAs": False},
# )


store = SPARQLStore(
    db_config.sparql_endpoint,
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
    timeout=300,
)
# store = SPARQLStore(
#     "http://examode.dei.unipd.it:7200/repositories/TUGraz_test",
#     method="POST_FORM",
#     params={"infer": False, "sameAs": False},
#     headers={
#         "Authorization": "GDB eyJ1c2VybmFtZSI6ImJlbmVkaWt0LmthbnR6IiwiYXV0aGVudGljYXRlZEF0IjoxNzMzODMxOTk3NTIzfQ==.QqebiiJt752/OThRujrJyNg0XXKrrteU7MhNPUCoSBI="
#     },
# )
graph = Graph(store=store)

config = OntologyConfig()

ontology_manager = OntologyManager(config, graph)
dataset_manager = DatasetManager(ontology_manager)
# dataset_manager.initialise(glob_path="data/datasets/ALS/**/*.csv")

# ontology_manager.load_full_graph()

guidance_man = GuidanceManager(
    ontology_manager, conn_str=db_config.conn_str, llm_model_id=db_config.model_id
)
# topic_man.initialize_topics(force=False)

llm_query = LLMQuery(topic=guidance_man)

initatior = InitatorManager()
initatior.register(guidance_man)
initatior.register(llm_query)


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
    return ontology_manager.q_to_df_values(query.query).to_dict(orient="records")


@app.get("/sparql")
def sparql_query_get(query: str = Query(...)) -> dict[str, Any]:
    data = ontology_manager.q_to_df_values(query).to_dict(orient="records")
    return {"results": {"bindings": data}}


@app.post("/management/ontology")
def load_ontology(
    ontology: UploadFile,
):
    brainteaser_graph = Graph().parse(ontology.file, format="turtle")
    for prefix in db_config.ttl_prefixes:
        brainteaser_graph.bind(prefix.ttl_prefix, prefix.uri)
    return {"ontology": ontology.filename, "prefixes": db_config}


@app.get("/classes/full")
def get_full_classes() -> list[Subject]:
    roots = ontology_manager.get_full_classes()
    return roots


@app.get("/classes/roots")
def get_root_classes() -> list[Subject]:
    return ontology_manager.get_root_classes()


@app.get("/classes/subclasses")
def get_class(cls: str = Query()) -> list[Subject]:
    return ontology_manager.get_classes(cls)


@app.get("/classes/instances")
def get_named_instance(cls: str = Query()) -> list[Subject]:
    return ontology_manager.get_named_individuals(cls)


@app.get("/classes/instances/search")
def get_named_instance_search(query: InstanceQuery = Query()) -> list[Instance]:
    return ontology_manager.get_instances(query)


@app.get("/classes/instances/properties")
def get_named_instance_properties(instance_id: str = Query()) -> dict[str, Property]:
    return ontology_manager.outgoing_edges_for(instance_id)


@app.get("/topics/root")
def get_topics_root(force_initialize: bool = Query(False)) -> Topic:
    guidance_man.initialize_topics(force_initialize)
    return guidance_man.get_topic_tree()


@app.get("/classes/links")
def get_links(subject_id: str = Query()) -> SparseOutLinks:
    if not hasattr(dataset_manager, "engine"):
        dataset_manager.initialise(glob_path=f"{base_path}/datasets/ALS/**/*.csv")
    return dataset_manager.target_outlinks(subject_id)


@app.post("/classes/search")
def search_classes(
    q: FuzzyQuery = Body("working field of person"),
) -> FuzzyQueryResults:
    return guidance_man.search_fuzzy(q)


@app.get("/classes/relations")
def get_relations(
    q: str | None = Query(None),
    from_id: str | None = Query(None),
    to_id: str | None = Query(None),
) -> list[SubjectLink]:
    return guidance_man.search_links(q, from_id, to_id)


@app.get("/classes/search/llm")
def get_llm_results(
    background_tasks: BackgroundTasks,
    q: str = Query("working field of person"),
) -> QueryProgress:
    return llm_query.start_query(q, background_tasks)


@app.get("/classes/search/llm/running")
def get_llm_results_running(
    query_id: str = Query(),
) -> QueryProgress | None:
    return llm_query.query_progress(query_id)


@app.get("/classes/search/llm/examples")
def get_llm_examples() -> list[EnrichedEntitiesRelations]:
    return llm_query.get_examples()
