"""Ablation of the extraction aids without the agent: a fixed, hand-made Text2Onto ontology
(``Type``, ``Term``, ``hasType``, mapped to the annotations' ``types`` / ``terms.term``,
sentence chunks of 150 characters) extracted with each combination of retrieved examples
and vocabulary matching, so their effect is separated from the agent's choices.

    ./py.sh extraction-aids.py --dataset llms4ol-scholarly llms4ol-engineering llms4ol-ecology

Writes ``results/aids_<dataset>.csv`` (one row per variant, the metrics of builder_eval).
"""

import env_setup  # noqa: F401

import argparse
from pathlib import Path

import pandas as pd

from builder.ontology import OntoClass, OntoLink, Ontology
from builder_eval import RunConfig, make_builder, score_session, wait_for_build
from datasets import DATASETS

RESULTS = Path(__file__).resolve().parent / "results"
BASE = Ontology(
    classes=[
        OntoClass(id="Type", label="Type", description="A general concept or category name mentioned in the text "
                                                       "(a class in a taxonomy), as a lowercase noun phrase."),
        OntoClass(id="Term", label="Term", description="A specific named item that belongs to a category "
                                                       "(an instance of a type)."),
    ],
    links=[OntoLink(id="hasType", source="Term", target="Type", description="the type of the term")],
    annotation_map={"Type": "types", "Term": "terms.term"}, chunk_chars=150,
)
VARIANTS = {
    "none": {},
    "retrieved": {"retrieved_examples": 3},
    "vocab_terms": {"vocabulary_classes": ["Term"]},
    "vocab_types": {"vocabulary_classes": ["Type"]},
    "vocab_both": {"vocabulary_classes": ["Type", "Term"]},
    "retrieved_vocab_terms": {"retrieved_examples": 3, "vocabulary_classes": ["Term"]},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", nargs="+", default=["llms4ol-scholarly", "llms4ol-engineering", "llms4ol-ecology"])
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS))
    parser.add_argument("--max_documents", type=int, default=None)
    args = parser.parse_args()
    for name in args.dataset:
        dataset, rows = DATASETS[name], []
        for variant in args.variants:
            onto = BASE.model_copy(deep=True, update=VARIANTS[variant])
            cfg = RunConfig(dataset, f"aids-{variant}", RESULTS / "aids", max_documents=args.max_documents)
            session = make_builder(cfg).session(cfg.run_id)
            session.set_ontology(onto)
            complete = wait_for_build(session, 7200)
            metrics, _ = score_session(dataset, session.ontology, session.graph, None, dataset.gold(None))
            session.stop()
            rows.append({"dataset": name, "variant": variant, "build_complete": complete, **metrics})
            print(name, variant, {k: round(v, 3) for k, v in metrics.items() if k.endswith("f1")}, flush=True)
            RESULTS.mkdir(exist_ok=True)
            pd.DataFrame(rows).to_csv(RESULTS / f"aids_{name}.csv", index=False)


if __name__ == "__main__":
    main()
