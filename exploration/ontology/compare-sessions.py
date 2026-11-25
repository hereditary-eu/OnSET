"""Scores users' saved builder sessions against the references, like the agent runs.

    ./py.sh compare-sessions.py                                   # backend's save_dir
    ./py.sh compare-sessions.py --sessions_dir /path/to/builder-saves --with_kg

Sessions are ``<sessions_dir>/<builder>/<id>.json`` (BuilderSession.persist); the builder id
names the dataset (``enron``, ``gutbrainie``, ``llms4ol-<domain>``). The default directory
is the backend's builder ``save_dir`` (config.json). Every session with at least
``--min_classes`` classes is scored on its ontology; ``--with_kg`` also rebuilds its KG on the
dataset's evaluation documents (its own KG may be of other documents) for the instance metrics.

Writes ``results/sessions_<name>.csv`` (one row per session) and prints the per-dataset median
and best (max) of the main metrics, the aggregation make-figures.py compares with the agent.
"""

import env_setup  # noqa: F401  (paths, .env)

import argparse
from pathlib import Path

import pandas as pd

from builder_eval import aggregate, default_sessions_dir, score_saved_sessions
from datasets import datasets

RESULTS = Path(__file__).resolve().parent / "results"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sessions_dir", type=Path, default=None, help="default: the backend's builder save_dir")
    parser.add_argument("--name", default=None, help="results name (default: the directory's name)")
    parser.add_argument("--min_classes", type=int, default=1)
    parser.add_argument("--with_kg", action="store_true", help="rebuild each session's KG on the eval documents")
    parser.add_argument("--max_documents", type=int, default=None)
    parser.add_argument("--gutbrainie_split", choices=["dev", "gold"], default="dev")
    args = parser.parse_args()

    sessions_dir = args.sessions_dir or default_sessions_dir()
    name = args.name or sessions_dir.name
    df = score_saved_sessions(sessions_dir, datasets(args.gutbrainie_split), args.min_classes, args.with_kg,
                              args.max_documents, RESULTS / f"sessions_{name}")
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / f"sessions_{name}.csv", index=False)
    print(f"{len(df)} sessions -> {RESULTS / f'sessions_{name}.csv'}")
    if len(df):
        with pd.option_context("display.width", 200, "display.max_columns", 30):
            print(aggregate(df).round(3))


if __name__ == "__main__":
    main()
