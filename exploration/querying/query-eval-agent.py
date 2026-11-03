# %%
import os
import sys
import dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
dotenv.load_dotenv(env_path)
print("Loaded environment variables from", env_path)
sys.path.insert(0, os.path.abspath("../../"))
sys.path.append(os.path.abspath("../../backend/src"))
sys.path.append(os.path.abspath("backend/src"))

import argparse
import glob

# %%
import networkx as nx
import pandas as pd
from tqdm import tqdm

from backend.src.api import ManMan
from backend.src.eval_config import ALL_CONFIG_MAP, get_config
from backend.src.explorative.llm_query import (
    EnrichedEntitiesRelations,
    EnrichedEntity,
    EnrichedRelation,
    EntitiesRelations,
    LLMQuery,
    QueryProgress,
)
from backend.src.agent.graph_tools import QueryGraph

# %%

parser = argparse.ArgumentParser()


configs = ALL_CONFIG_MAP
parser.add_argument(
    "--dataset", type=str, choices=list(configs.keys()), default="dbpedia"
)
parser.add_argument("--cfg_idx", type=int, default=-1)
parser.add_argument("--n_samples", type=int, default=None)
args = parser.parse_args()

setup = get_config(args.dataset, args.cfg_idx)
csvs = glob.glob(f"examples/examples_{setup.name}*.csv")
print(csvs)
generated_queries = pd.concat([pd.read_csv(csv, index_col=0) for csv in csvs])

man_man = ManMan(
    config_id=id,
    eval_cfg=setup,
)


def load_erl(erl_str: str) -> EnrichedEntitiesRelations:
    erl = EnrichedEntitiesRelations.model_validate_json(erl_str)
    for ent in erl.entities:
        ent.subject.subject_id = man_man.ontology_manager.to_prefix(
            ent.subject.subject_id
        )
    for rel in erl.relations:
        rel.link.property_id = man_man.ontology_manager.to_prefix(rel.link.property_id)
    return erl


generated_queries["erl_loaded"] = generated_queries["erl"].apply(load_erl)
setup.agent.max_steps = generated_queries["n_nodes"].max() * 2
man_man = ManMan(
    config_id=id,
    eval_cfg=setup,
)
print("Running agent against", setup.agent.base_url)


def graph_to_erl(graph: QueryGraph) -> EnrichedEntitiesRelations:
    entities = []
    for subject in graph.subjects:
        print(f"Processing subject {subject.id} with URI {subject.uri}")
        subject_full = subject.get_full(man_man, load_properties=False)
        entities.append(
            EnrichedEntity(
                subject=subject_full,
                identifier=subject.id,
                constraints=[],
                type=subject.uri,
            )
        )
    links = []
    for relation in graph.links:
        print(
            f"Processing relation {relation.uri} from {relation.from_subject_id} to {relation.to_subject_id}"
        )
        relation_full = relation.get_full(man_man)
        links.append(
            EnrichedRelation(
                link=relation_full,
                relation=relation.uri,
                entity=relation.from_subject_id,
                target=relation.to_subject_id,
            )
        )
    return EnrichedEntitiesRelations(
        entities=entities,
        relations=links,
    )


# %%
def graph_from_erl(erl: EnrichedEntitiesRelations | EntitiesRelations):
    G = nx.DiGraph()
    for node in erl.entities:
        G.add_node(node.identifier, id=node.subject.subject_id, type=node.type)
    for link in erl.relations:
        G.add_edge(
            link.entity,
            link.target,
            weight=link.link.instance_count if hasattr(link, "link") else 1,
            label=link.relation,
            id=link.link.property_id,
        )
    return G


def edge_match(a, b):
    return a["id"] == b["id"] if "id" in a and "id" in b else False


def node_match(a, b):
    return a["id"] == b["id"] if "id" in a and "id" in b else False


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
def run_eval(query: pd.Series):
    target_erl: EnrichedEntitiesRelations = query["erl_loaded"]
    for ent in target_erl.entities:
        ent.type = man_man.ontology_manager.to_prefix(ent.type)
    for rel in target_erl.relations:
        rel.relation = man_man.ontology_manager.to_prefix(rel.relation)
    query_string: str = query["response"]
    session = man_man.build_agent_session(f"test_{query_string}")
    print(
        f"Running query {query_string} with {len(target_erl.entities)} nodes and {len(target_erl.relations)} edges"
    )
    for resp in session.run_turn(
        content=query_string,
    ):
        if hasattr(resp, "delta") and resp.delta:
            print(resp.delta, end="")
    print(f"Query {query_string} completed")
    # convert the graph to the erl format and compare with the expected erl
    erl_result = graph_to_erl(session.graph)

    eval_erls: dict[str, EntitiesRelations | EnrichedEntitiesRelations] = {
        "agent": erl_result,
    }
    results: list[dict, any] = []
    for key, erl in eval_erls.items():
        f1_score_ents, precision, recall = f1k(
            [ent.subject.subject_id for ent in target_erl.entities],
            [ent.subject.subject_id for ent in erl.entities],
        )
        f1_score_rel, precision_rel, recall_rel = f1k(
            [rel.link.property_id for rel in target_erl.relations],
            [rel.link.property_id for rel in erl.relations],
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
                "cfg_name": setup.name,
                "stage": key,
            }
        )
    return results


def run_evals(queries: pd.DataFrame, outfile=None):
    results = []
    print(f"Running evals for {len(queries)} queries")
    for i, query in tqdm(queries.iterrows(), total=len(queries)):
        print(f"Running eval for query {i}: {query['response']}", flush=True)
        try:
            scores = run_eval(query)
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
    output_file = f"results/eval_results_{setup.name}_agent_{setup.agent.model.replace('/', '_')}.csv"
    results = run_evals(generated_queries.iloc[:n_samples], outfile=output_file)
    results.to_csv(output_file)

    print(f"Done, esults saved to {output_file}")
