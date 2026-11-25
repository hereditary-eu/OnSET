"""Benchmark with the true ontology: each reference (``references/<dataset>.ttl``) imported as
the builder's own ontology (onto_eval.extraction_ontology) and extracted over the same
evaluation documents as the agent runs, without the agent. This separates how good the agent's
schema is from how well the 350M extractor fills a given schema: on GutBrainIE the instance
metrics against the gold, on Enron (no gold) the KG yield (instances, documents covered).

    ./py.sh reference-baseline.py --dataset gutbrainie enron --max_documents 500

Writes ``results/reference_<dataset>.csv`` (one row per variant: whole documents and, with
``--chunk_chars``, sentence chunks); sessions are saved below ``results/reference``.
"""

import env_setup  # noqa: F401

import argparse
from pathlib import Path

import pandas as pd

from builder_eval import RunConfig, make_builder, score_session, wait_for_build
from datasets import datasets
from onto_eval import extraction_ontology

RESULTS = Path(__file__).resolve().parent / "results"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", nargs="+", default=["gutbrainie", "enron"])
    parser.add_argument("--max_documents", type=int, default=None)
    parser.add_argument("--chunk_chars", type=int, nargs="*", default=[400], help="chunked variants (besides whole)")
    parser.add_argument("--gutbrainie_split", choices=["dev", "gold"], default="dev")
    args = parser.parse_args()
    registry = datasets(args.gutbrainie_split)
    for name in args.dataset:
        dataset = registry[name]
        ref = dataset.reference_schema()
        gold = dataset.gold(ref) if dataset.gold else None
        rows = []
        for chunk in [None, *args.chunk_chars]:
            onto = extraction_ontology(ref)
            onto.chunk_chars = chunk
            run_id = f"reference-{name}-{'whole' if chunk is None else f'c{chunk}'}"
            cfg = RunConfig(dataset, run_id, RESULTS / "reference", max_documents=args.max_documents)
            builder = make_builder(cfg)
            session = builder.session(run_id)
            session.set_ontology(onto)
            complete = wait_for_build(session, 4 * 3600)
            metrics, details = score_session(dataset, session.ontology, session.graph, ref, gold,
                                             len(builder.corpus.documents))
            session.save()
            session.stop()
            rows.append({"dataset": name, "run_id": run_id, "source": "reference", "chunk_chars": chunk,
                         "documents": len(builder.corpus.documents), "build_complete": complete,
                         "extract_errors": session.status.errors, **metrics})
            print(run_id, {k: round(v, 3) for k, v in metrics.items() if k.startswith("kg_") and v == v}, flush=True)
            RESULTS.mkdir(exist_ok=True)
            pd.DataFrame(rows).to_csv(RESULTS / f"reference_{name}.csv", index=False)


if __name__ == "__main__":
    main()
