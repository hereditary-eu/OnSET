# %%

import numpy as np

# %%
import sys
import os

sys.path.insert(0, os.path.abspath("../.."))
sys.path.append(os.path.abspath("../../backend"))
sys.path.append(os.path.abspath(""))

import networkx as nx
from rdflib.plugins.stores.sparqlstore import SPARQLStore

from backend.ontology import OntologyManager, OntologyConfig, Graph
from backend.explorative.explorative_support import GuidanceManager
from backend.explorative.llm_query import (
    EnrichedEntitiesRelations,
    EntitiesRelations,
    LLMQuery,
    QueryProgress,
)
from tqdm import tqdm
import pandas as pd

# %%
import networkx as nx

import argparse
import glob
from backend.eval_config import (
    DBPEDIA_CONFIGS,
    OMA_CONFIGS,
    DNB_CONFIGS,
    UNIPROT_CONFIGS,
    BTO_CONFIGS,
    YAGO_CONFIGS,
    GUTBRAINIE_CONFIGS,
    EvalConfig,
)
# %%

parser = argparse.ArgumentParser()


configs = {
    "dbpedia": DBPEDIA_CONFIGS,
    "uniprot": UNIPROT_CONFIGS,
    "bto": BTO_CONFIGS,
    "dnb": DNB_CONFIGS,
    "oma": OMA_CONFIGS,
    "yago": YAGO_CONFIGS,
    "gutbrainie": GUTBRAINIE_CONFIGS,
}
parser.add_argument(
    "--dataset", type=str, choices=list(configs.keys()), default="dbpedia"
)
parser.add_argument("--cfg_idx", type=int, default=-1)
parser.add_argument("--zero_shot", action="store_true")
parser.add_argument("--n_samples", type=int, default=None)
args = parser.parse_args()


setup: EvalConfig = configs[args.dataset][args.cfg_idx]
setup_base = configs[args.dataset][-1]
print("Started with args", args)
print("Setup for", setup)

store = SPARQLStore(
    setup.sparql_endpoint,
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
)
graph = Graph(store=store)

config = OntologyConfig()

ontology_manager = OntologyManager(config, graph)
topic_man = GuidanceManager(
    ontology_manager,
    llm_model_id=setup.model_id,
    ctx_size=6000,
    conn_str=setup.conn_str,
    llm_quant_model=setup.model_quant,
)

query_man = LLMQuery(topic_man)

# %%
csvs = glob.glob(f"examples/examples_{setup_base.name}*.csv")
print(csvs)
generated_queries = pd.concat([pd.read_csv(csv, index_col=0) for csv in csvs])
generated_queries["erl_loaded"] = generated_queries["erl"].apply(
    lambda x: EnrichedEntitiesRelations.model_validate_json(x)
)


# %%
def graph_from_erl(erl: EnrichedEntitiesRelations | EntitiesRelations):
    G = nx.DiGraph()
    for node in erl.entities:
        G.add_node(node.identifier, label=node.type)
    for link in erl.relations:
        G.add_edge(
            link.entity,
            link.target,
            weight=link.link.instance_count if hasattr(link, "link") else 1,
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
        return 0, 0, 0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall), precision, recall


# %%
def run_eval(query: pd.Series, llm_query: LLMQuery):
    target_erl: EnrichedEntitiesRelations = query["erl_loaded"]
    query = query["response"]
    progress = QueryProgress(id="0", max_steps=1, start_time="0")
    llm_query.run_query(query=query, progress=progress)
    eval_erls: dict[str, EntitiesRelations | EnrichedEntitiesRelations] = {
        "raw": progress.relations_steps[0],
        "constrained": progress.relations_steps[-2],
        "aligned": progress.enriched_relations,
    }
    results: list[dict, any] = []
    for key, erl in eval_erls.items():
        f1_score_ents, precision, recall = f1k(
            [ent.type for ent in target_erl.entities],
            [ent.type for ent in erl.entities],
        )
        f1_score_rel, precision_rel, recall_rel = f1k(
            [rel.relation for rel in target_erl.relations],
            [rel.relation for rel in erl.relations],
        )
        target_graph = graph_from_erl(target_erl)
        retrieved_grah = graph_from_erl(erl)
        ged = nx.graph_edit_distance(
            target_graph,
            retrieved_grah,
            edge_match=edge_match,
            node_match=node_match,
            timeout=20,
        )
        normed_ged = 1 - ged / (
            max(len(target_graph.nodes), len(retrieved_grah.nodes))
            + max(len(target_graph.edges), len(retrieved_grah.edges))
        )

        results.append(
            {
                "f1_score": f1_score_ents,
                "precision": precision,
                "recall": recall,
                "f1_score_rel": f1_score_rel,
                "precision_rel": precision_rel,
                "recall_rel": recall_rel,
                "ged": ged,
                "normed_ged": normed_ged,
                "response": erl.model_dump_json(),
                "model": setup.model_id,
                "cfg_name": setup_base.name,
                "zeroshot": args.zero_shot,
                "stage": key,
            }
        )
    return results


def run_evals(queries: pd.DataFrame, llm_query: LLMQuery, outfile=None):
    results = []
    print(f"Running evals for {len(queries)} queries")
    for i, query in tqdm(queries.iterrows(), total=len(queries)):
        print(f"Running eval for query {i}: {query['response']}", flush=True)
        try:
            scores = run_eval(query, llm_query)
            for s in scores:
                s.update(query.to_dict())
                results.append(s)
            print(f"Writing results to {outfile}", flush=True)
            if outfile is not None:
                pd.DataFrame(results).to_csv(outfile)
                # results = pd.concat([results, pd.DataFrame([s])], ignore_index=True)
        except Exception as e:
            print(e)
            # print stack trace
            import traceback

            traceback.print_exc()
            print(f"Error running eval for query {i}: {query['response']}", flush=True)
    return pd.DataFrame(results)


if __name__ == "__main__":
    print("Running evals with setup", setup)
    # n_samples = 5
    n_samples = args.n_samples
    zero_shot = args.zero_shot
    print(
        f"zero_shot={zero_shot}, n_samples={n_samples}, llm_model_id={setup.model_id}"
    )
    query_man = LLMQuery(topic_man, zero_shot=zero_shot, max_tokens=4096)
    output_file = f"results/eval_results_{setup_base.name}_{'zeroshot' if zero_shot else 'oneshot'}_{topic_man.llm_model_id.replace('/', '-')}.csv"
    results = run_evals(
        generated_queries.iloc[:n_samples], llm_query=query_man, outfile=output_file
    )
    results.to_csv(output_file)
    
    print(f"Done, esults saved to {output_file}")
