from fastapi import FastAPI, Query, File, UploadFile, Body, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from rdflib.plugins.stores.sparqlstore import SPARQLStore

from model import *
from ontology import *
from datasetmatcher import *
from explorative_support import *
from llm_query import *

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
    "http://localhost:7012/",
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
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

topic_man = TopicModelling(ontology_manager)
# topic_man.initialize_topics(force=False)

llm_query = LLMQuery(topic=topic_man)

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


@app.post("/management/ontology")
def load_ontology(
    ontology: UploadFile,
):
    brainteaser_graph = Graph().parse(ontology.file, format="turtle")
    for prefix in config.ttl_prefixes:
        brainteaser_graph.bind(prefix.ttl_prefix, prefix.uri)
    return {"ontology": ontology.filename, "prefixes": config}


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
    topic_man.initialize_topics(force_initialize)
    return topic_man.get_topic_tree()


@app.get("/classes/links")
def get_links(subject_id: str = Query()) -> SparseOutLinks:
    if not hasattr(dataset_manager, "engine"):
        dataset_manager.initialise(glob_path=f"{base_path}/datasets/ALS/**/*.csv")
    return dataset_manager.target_outlinks(subject_id)


@app.post("/classes/search")
def search_classes(
    q: FuzzyQuery = Body("working field of person"),
) -> FuzzyQueryResults:
    return topic_man.search_fuzzy(q)


@app.get("/classes/relations")
def get_relations(
    q: str | None = Query(None),
    from_id: str | None = Query(None),
    to_id: str | None = Query(None),
) -> list[SubjectLink]:
    return topic_man.search_links(q, from_id, to_id)


@app.get("/classes/search/llm")
def get_llm_results(
    background_tasks: BackgroundTasks,
    q: str = Query("working field of person"),
) -> QueryProgress:
    return llm_query.start_query(q, background_tasks)


@app.get("/classes/search/llm/running")
def get_llm_results_running(
    query_id: str = Query(),
) -> QueryProgress:
    return llm_query.query_progress(query_id)
