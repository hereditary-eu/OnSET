# %%

import numpy as np

# %%
import sys
import os

sys.path.insert(0, os.path.abspath("../.."))
sys.path.append(os.path.abspath("../../backend"))
sys.path.append(os.path.abspath(""))

import networkx as nx
from typing import TypeVar
from sqlalchemy.orm import aliased
from sqlalchemy.sql import text
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from backend.model import (
    Session,
)

from backend.ontology import OntologyManager, OntologyConfig, Graph
from backend.explorative_support import TopicModelling, select
from backend.llm_query import (
    Entity,
    Relation,
    EntitiesRelations,
    EnrichedEntity,
    EnrichedRelation,
    EnrichedEntitiesRelations,
    SubjectLink,
    SubjectInDB,
    SubjectLinkDB,
    LLMQuery,
    QueryProgress,
)
from tqdm import tqdm
import pandas as pd

# %%
from seqeval import metrics
from sklearn.metrics import f1_score
import networkx as nx

import argparse
# %%

parser = argparse.ArgumentParser()

parser.add_argument(
    "--llm_model_id", type=str, default="NousResearch/Hermes-3-Llama-3.2-3B-GGUF"
)
parser.add_argument("--zero_shot", type=bool, default=False)
parser.add_argument("--n_samples", type=int, default=None)
args = parser.parse_args()


store = SPARQLStore(
    "http://localhost:7012/",
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
)
graph = Graph(store=store)

config = OntologyConfig()

ontology_manager = OntologyManager(config, graph)
topic_man = TopicModelling(ontology_manager, llm_model_id=args.llm_model_id, ctx_size=4096)

query_man = LLMQuery(topic_man)

# %%
generated_queries = pd.read_csv("llama_examples.csv", index_col=0)
generated_queries["erl_loaded"] = generated_queries["erl"].apply(
    lambda x: EnrichedEntitiesRelations.model_validate_json(x)
)


# %%
def graph_from_erl(erl: EnrichedEntitiesRelations):
    G = nx.DiGraph()
    for node in erl.entities:
        G.add_node(node.identifier, label=node.type)
    for link in erl.relations:
        G.add_edge(
            link.entity,
            link.target,
            weight=link.link.instance_count,
            label=link.relation,
        )
    return G


def edge_match(a, b):
    return a["label"] == b["label"] if "label" in a and "label" in b else False


def node_match(a, b):
    return a["label"] == b["label"] if "label" in a and "label" in b else False


# %%
def f1k(y_true, y_pred, k: int = None):
    rel_set = set(y_true)
    # print(rel_set)
    doc_set = set(y_pred[:k])
    tp = len(doc_set.intersection(rel_set))  # docs that are in both -relevant docs
    fp = len(
        doc_set.difference(rel_set)
    )  # docs that are not in relevant set - irrelevant docs (false positiv)
    fn = len(
        rel_set.difference(doc_set)
    )  # relevant docs that are not present in doc set - missing docs
    if tp == 0:
        return 0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall), precision, recall


# %%
def run_eval(query: pd.Series, llm_query: LLMQuery):
    target_erl: EnrichedEntitiesRelations = query["erl_loaded"]
    query = query["response"]
    progress = QueryProgress(id="0", max_steps=1, start_time="0")
    llm_query.run_query(query=query, progress=progress)
    f1_score_ents, precision, recall = f1k(
        [ent.type for ent in target_erl.entities],
        [ent.type for ent in progress.enriched_relations.entities],
    )
    target_graph = graph_from_erl(target_erl)
    retrieved_grap = graph_from_erl(progress.enriched_relations)
    edit_distance = 1 - nx.graph_edit_distance(
        target_graph,
        retrieved_grap,
        edge_match=edge_match,
        node_match=node_match,
        timeout=10,
    ) / (
        max(
            len(target_graph.nodes),
            len(retrieved_grap.nodes),
        )
        + max(
            len(target_graph.edges),
            len(retrieved_grap.edges),
        )
    )
    return {
        "f1_score": f1_score_ents,
        "precision": precision,
        "recall": recall,
        "edit_distance": edit_distance,
    }


def run_evals(queries: pd.DataFrame, llm_query: LLMQuery):
    results = queries.copy()
    for i, query in tqdm(queries.iterrows(), total=len(queries)):
        try:
            scores = run_eval(query, llm_query)
            for key, value in scores.items():
                results.loc[i, key] = value
        except Exception as e:
            print(e)
    return results


if __name__ == "__main__":
    # n_samples = 5
    n_samples = args.n_samples
    zero_shot = args.zero_shot
    print(f"zero_shot={zero_shot}, n_samples={n_samples}, llm_model_id={args.llm_model_id}")
    query_man = LLMQuery(topic_man, zero_shot=zero_shot)
    results = run_evals(generated_queries.iloc[:n_samples], llm_query=query_man)
    results.to_csv(
        f"results/eval_results_{'zeroshot' if zero_shot else 'oneshot'}_{topic_man.llm_model_id.replace('/', '-')}.csv"
    )
