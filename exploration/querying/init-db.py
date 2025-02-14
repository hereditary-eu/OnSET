import sys
import os

sys.path.insert(0, os.path.abspath("../.."))
sys.path.append(os.path.abspath("../../backend"))
sys.path.append(os.path.abspath(""))

from rdflib.plugins.stores.sparqlstore import SPARQLStore

from backend.ontology import OntologyManager, OntologyConfig, Graph
from backend.datasetmatcher import DatasetManager
from backend.explorative_support import GuidanceManager
from backend.llm_query import (
    EnrichedEntitiesRelations,
    LLMQuery,
    QueryProgress,
)
from tqdm import tqdm
import pandas as pd

# %%
from backend.eval_config import DBPEDIA_CONFIGS, OMA_CONFIGS, UNIPROT_CONFIGS, BTO_CONFIGS

# db_setups = [DBPEDIA_CONFIGS[1], UNIPROT_CONFIGS[1], BTO_CONFIGS[1]]
db_setups = [BTO_CONFIGS[1]]
if __name__ == "__main__":
    print("Starting")
    # %%
    for setup in db_setups:
        print("Setup for ", setup.name)
        store = SPARQLStore(
            setup.sparql_endpoint,
            method="POST_FORM",
            params={"infer": False, "sameAs": False},
            retries=10,
        )
        graph = Graph(store=store)

        config = OntologyConfig()

        ontology_manager = OntologyManager(config, graph)
        dataset_manager = DatasetManager(ontology_manager)
        dataset_manager.initialise(glob_path="data/datasets/ALS/**/*.csv")
        topic_man = GuidanceManager(
            ontology_manager, conn_str=setup.conn_str, llm_model_id=setup.model_id
        )
        topic_man.llama_model
        print(topic_man.identifier)
        topic_man.initialize_topics(force=True, delete_tables=True)

# %%
