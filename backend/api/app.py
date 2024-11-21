from fastapi import FastAPI, Query, File, UploadFile, Body, Form
from fastapi.middleware.cors import CORSMiddleware


from model import *
from ontology import *
from datasetmatcher import *
from explorative_support import *

base_path = "../data"
onto_path = f"{base_path}/hero-ontology/hereditary_clinical.ttl"


# graph = Graph().parse(onto_path, format="turtle")
# graph.bind("bto", "http://www.semanticweb.org/ontologies/2020/3/bto#")

store = SPARQLStore(
    "http://localhost:7200/repositories/dpedia",
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
)
graph = Graph(store=store)

config = OntologyConfig()

ontology_manager = OntologyManager(config, graph)
dataset_manager = DatasetManager(ontology_manager)
# dataset_manager.initialise(glob_path="data/datasets/ALS/**/*.csv")

# ontology_manager.load_full_graph()

topic_man = TopicModelling(ontology_manager)


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


@app.get("/classes/named-individuals")
def get_named_individuals(cls: str = Query()) -> list[Subject]:
    return ontology_manager.get_named_individuals(cls)


@app.get("/topics/root")
def get_topics_root() -> Topic:
    topic_man.initialize_topics()
    return topic_man.get_topic_tree()


@app.get("/classes/links")
def get_links(subject_id: str = Query()) -> SparseOutLinks:
    if dataset_manager.engine is None:
        dataset_manager.initialise(glob_path=f"{base_path}/datasets/ALS/**/*.csv")
    return dataset_manager.target_outlinks(subject_id)
