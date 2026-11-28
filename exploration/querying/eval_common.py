"""Shared helpers for the query-generation evaluations (query-eval.py, query-eval-agent.py)."""

import argparse
import glob
import time
import traceback
import urllib.request
from enum import Enum
from typing import Callable

import networkx as nx
import pandas as pd
from tqdm import tqdm

# ERLs are compared by ontology ids (subject_id / property_id), normalised by `normalize`
# (e.g. OntologyManager.to_prefix) so `<http://...>` and `prefix:...` forms match.
# ERLs without ids (the raw LLM stage) fall back to the entity type / relation name.
Normalize = Callable[[str], str]


def _identity(s: str) -> str:
    return s


def is_enriched(erl) -> bool:
    return all(getattr(e, "subject", None) is not None for e in erl.entities) and all(
        getattr(r, "link", None) is not None for r in erl.relations
    )


def as_str(value) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def entity_id(ent, use_ids: bool = True, normalize: Normalize = _identity) -> str:
    return normalize(as_str(ent.subject.subject_id if use_ids else ent.type))


def relation_id(rel, use_ids: bool = True, normalize: Normalize = _identity) -> str:
    return normalize(as_str(rel.link.property_id if use_ids else rel.relation))


def graph_from_erl(erl, use_ids: bool = True, normalize: Normalize = _identity):
    G = nx.DiGraph()
    for node in erl.entities:
        G.add_node(node.identifier, id=entity_id(node, use_ids, normalize))
    for link in erl.relations:
        G.add_edge(
            link.entity,
            link.target,
            weight=link.link.instance_count if getattr(link, "link", None) else 1,
            id=relation_id(link, use_ids, normalize),
        )
    return G


def edge_match(a, b):
    return a["id"] == b["id"] if "id" in a and "id" in b else False


def node_match(a, b):
    return a["id"] == b["id"] if "id" in a and "id" in b else False


def f1k(y_true, y_pred, k: int = None):
    rel_set = set(y_true)
    doc_set = set(y_pred[:k])
    tp = len(doc_set & rel_set)
    fp = len(doc_set - rel_set)
    fn = len(rel_set - doc_set)
    if tp == 0:
        return 0, 0, 0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall), precision, recall


def score_erl(target_erl, erl, normalize: Normalize = _identity, ged_timeout=20) -> dict:
    """Entity/relation F1 and graph edit distance of `erl` against `target_erl`."""
    use_ids = is_enriched(erl)
    f1_ents, precision, recall = f1k(
        [entity_id(e, use_ids, normalize) for e in target_erl.entities],
        [entity_id(e, use_ids, normalize) for e in erl.entities],
    )
    f1_rel, precision_rel, recall_rel = f1k(
        [relation_id(r, use_ids, normalize) for r in target_erl.relations],
        [relation_id(r, use_ids, normalize) for r in erl.relations],
    )
    target_graph = graph_from_erl(target_erl, use_ids, normalize)
    retrieved_graph = graph_from_erl(erl, use_ids, normalize)
    ged = nx.graph_edit_distance(
        target_graph,
        retrieved_graph,
        edge_match=edge_match,
        node_match=node_match,
        timeout=ged_timeout,
    )
    size = max(len(target_graph.nodes), len(retrieved_graph.nodes)) + max(
        len(target_graph.edges), len(retrieved_graph.edges)
    )
    # ged is None when the timeout hits before any edit path is found
    normed_ged = None if ged is None else (1 - ged / size if size else 1.0)
    return {
        "f1_score": f1_ents,
        "precision": precision,
        "recall": recall,
        "f1_score_rel": f1_rel,
        "precision_rel": precision_rel,
        "recall_rel": recall_rel,
        "ged": ged,
        "normed_ged": normed_ged,
        "matched_by": "id" if use_ids else "label",
        "response": erl.model_dump_json(),
    }


def wait_for_endpoint(url: str, timeout: float = 600, interval: float = 10):
    """Blocks until the SPARQL endpoint answers, QLever may still be starting up."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            urllib.request.urlopen(f"{url}?query=ASK%7B%7D", timeout=interval)
            return
        except Exception as e:
            if time.monotonic() > deadline:
                raise RuntimeError(f"SPARQL endpoint {url} unreachable") from e
            print(f"Waiting for SPARQL endpoint {url}: {e}", flush=True)
            time.sleep(interval)


def base_arg_parser(datasets) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, choices=list(datasets), default="dbpedia")
    parser.add_argument("--cfg_idx", type=int, default=-1)
    parser.add_argument("--n_samples", type=int, default=None)
    return parser


def load_examples(name: str, load_erl: Callable[[str], object]) -> pd.DataFrame:
    csvs = glob.glob(f"examples/examples_{name}*.csv")
    print(csvs)
    queries = pd.concat([pd.read_csv(csv, index_col=0) for csv in csvs])
    queries["erl_loaded"] = queries["erl"].apply(load_erl)
    return queries


def run_evals(
    queries: pd.DataFrame,
    run_eval: Callable[[pd.Series], list[dict]],
    outfile: str | None = None,
) -> pd.DataFrame:
    results = []
    print(f"Running evals for {len(queries)} queries")
    for i, query in tqdm(queries.iterrows(), total=len(queries)):
        print(f"Running eval for query {i}: {query['response']}", flush=True)
        try:
            for s in run_eval(query):
                s.update(query.to_dict())
                results.append(s)
            if outfile is not None:
                print(f"Writing results to {outfile}", flush=True)
                pd.DataFrame(results).to_csv(outfile)
        except Exception as e:
            print(e)
            traceback.print_exc()
            print(f"Error running eval for query {i}: {query['response']}", flush=True)
    results = pd.DataFrame(results)
    if outfile is not None:
        results.to_csv(outfile)
        print(f"Done, results saved to {outfile}")
    return results
