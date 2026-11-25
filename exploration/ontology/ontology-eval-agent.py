"""Runs the ontology builder agent headlessly on evaluation datasets and scores the result.

    ./py.sh ontology-eval-agent.py --dataset gutbrainie --runs 3
    ./py.sh ontology-eval-agent.py --dataset all --prompt blind --refine_turns 0

Per dataset and run (seed): the agent builds an ontology from scripted user turns (the
task, then ``--refine_turns`` "inspect the KG and refine" turns, the build running in
between), the KG is built from the dataset's evaluation documents and both are scored
(builder_eval.score_session). One row per run is appended to
``results/ontology_eval_<dataset>_<tag>.csv``; the chat, ontology and TTL of each run are in
``results/<tag>/runs``. ``--blind`` (LLMs4OL) also extracts the official test documents with
the final ontology and writes the submission lists (``results/<tag>/submissions``).
"""

import env_setup  # noqa: F401  (paths, .env)

import argparse
import json
import time
import traceback
from pathlib import Path

import pandas as pd

from builder.corpus import Corpus
from builder_eval import RunConfig, make_builder, run_agent, score_session, text2onto_lists, wait_for_build
from datasets import DATASETS, datasets, llms4ol_split

RESULTS = Path(__file__).resolve().parent / "results"


def blind_submission(cfg: RunConfig, onto, out: Path) -> dict:
    """Extract the official (blind) test documents with ``onto``; write terms.txt/types.txt."""
    builder = make_builder(cfg)
    text_set = builder.config.text_set.model_copy(update={"path": str(llms4ol_split(cfg.dataset.llms4ol, "blind"))})
    builder.corpus = Corpus.load(text_set)
    session = builder.session(f"{cfg.run_id}-blind")
    session.set_ontology(onto)
    complete = wait_for_build(session, cfg.final_build_timeout)
    lists = text2onto_lists(session.graph, session.ontology)
    out.mkdir(parents=True, exist_ok=True)
    for kind, items in lists.items():
        (out / f"{kind}.txt").write_text("".join(f"{x}\n" for x in items))
    return {"blind_complete": complete, "blind_terms": len(lists["terms"]), "blind_types": len(lists["types"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", nargs="+", default=["gutbrainie"], help=f"{list(DATASETS)} or all")
    parser.add_argument("--runs", type=int, default=3, help="runs (seeds) per dataset")
    parser.add_argument("--seed0", type=int, default=0)
    parser.add_argument("--prompt", choices=["guided", "blind"], default="guided")
    parser.add_argument("--refine_turns", type=int, default=1)
    parser.add_argument("--max_documents", type=int, default=None, help="documents of the evaluated KG")
    parser.add_argument("--gutbrainie_split", choices=["dev", "gold"], default="dev")
    parser.add_argument("--model", default=None, help="agent model (default: config / AGENT_LLM_MODEL)")
    parser.add_argument("--base_url", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max_steps", type=int, default=30, help="agent LLM calls per turn")
    parser.add_argument("--extract_model", default=None, help="e.g. LiquidAI/LFM2-1.2B-Extract-GGUF")
    parser.add_argument("--extract_instances", type=int, default=None)
    parser.add_argument("--turn_build_timeout", type=float, default=300)
    parser.add_argument("--final_build_timeout", type=float, default=1800)
    parser.add_argument("--blind", action="store_true", help="LLMs4OL: also write blind test submissions")
    parser.add_argument("--tag", default=None, help="results name (default: <prompt>_r<refine_turns>)")
    args = parser.parse_args()

    registry = datasets(args.gutbrainie_split)
    names = list(registry) if args.dataset == ["all"] else args.dataset
    tag = args.tag or f"{args.prompt}_r{args.refine_turns}" + (
        f"_{args.extract_model.split('/')[-1].replace('-GGUF', '')}" if args.extract_model else "")
    out_dir = RESULTS / tag
    overrides = {k: v for k, v in {"model": args.model, "base_url": args.base_url, "temperature": args.temperature,
                                   "max_steps": args.max_steps}.items() if v is not None}
    for name in names:
        dataset = registry[name]
        ref = dataset.reference_schema()
        gold = dataset.gold(ref) if dataset.gold else None
        model = overrides.get("model") or dataset.builder_config().agent.model or "default"
        csv = RESULTS / f"ontology_eval_{name}_{tag}.csv"
        rows = pd.read_csv(csv).to_dict("records") if csv.exists() else []
        # failed runs are retried (their rows replaced)
        rows = [r for r in rows if pd.isna(r.get("error", float("nan")))]
        done = {r["run_id"] for r in rows}
        for seed in range(args.seed0, args.seed0 + args.runs):
            run_id = f"{name}-{model.split('/')[-1].replace('.gguf', '')}-s{seed}".replace(".", "_")
            if run_id in done:
                print(f"Skipping {run_id} (in {csv})", flush=True)
                continue
            cfg = RunConfig(dataset, run_id, out_dir, prompt=args.prompt, refine_turns=args.refine_turns,
                            max_documents=args.max_documents, seed=seed, agent_overrides=overrides,
                            extract_instances=args.extract_instances, extract_model=args.extract_model, turn_build_timeout=args.turn_build_timeout,
                            final_build_timeout=args.final_build_timeout)
            print(f"=== {run_id}", flush=True)
            start = time.monotonic()
            try:
                session, stats = run_agent(cfg)
                metrics, details = score_session(dataset, session.ontology, session.graph, ref, gold,
                                                  stats["documents"])
                (out_dir / "runs" / f"{run_id}.scores.json").write_text(json.dumps(
                    {"metrics": metrics, "details": details}, indent=1, default=str))
                row = {
                    "dataset": name, "run_id": run_id, "seed": seed, "source": "agent", "model": model,
                    "extract_model": cfg.extract_model or dataset.builder_config().extract_model_id, "prompt": args.prompt, "refine_turns": args.refine_turns, "documents": stats["documents"],
                    "build_complete": stats["build_complete"], "agent_seconds": stats["agent_seconds"],
                    "tool_calls": sum(t.get("tool_calls", 0) for t in stats["turns"]),
                    "tool_errors": sum(t.get("tool_errors", 0) for t in stats["turns"]),
                    "max_steps_hit": sum(t.get("done_max_steps", 0) for t in stats["turns"]),
                    "extract_errors": stats["status"]["errors"], **metrics,
                }
                if args.blind and dataset.llms4ol:
                    row |= blind_submission(cfg, session.ontology, out_dir / "submissions" / run_id)
                session.stop()
            except Exception as e:
                traceback.print_exc()
                row = {"dataset": name, "run_id": run_id, "seed": seed, "source": "agent", "model": model,
                       "prompt": args.prompt, "refine_turns": args.refine_turns, "error": f"{type(e).__name__}: {e}"}
            row["seconds"] = time.monotonic() - start
            rows.append(row)
            RESULTS.mkdir(exist_ok=True)
            pd.DataFrame(rows).to_csv(csv, index=False)
            print(json.dumps({k: v for k, v in row.items() if "f1" in k and "_p" not in k}, default=str), flush=True)


if __name__ == "__main__":
    main()
