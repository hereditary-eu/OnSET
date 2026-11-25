#!/bin/bash
# Continues an interrupted run_local.sh (finished runs are skipped): remaining main runs, the
# true-ontology baseline, extraction-aid ablation, user sessions, prompt/refinement ablations on
# the smaller datasets and the figures.
cd "$(dirname "$0")"
retry() { for attempt in 1 2 3; do "$@" && return 0; echo "attempt $attempt failed: $*"; done; return 1; }
# wait for an agent run still in progress (started by the interrupted driver)
while pgrep -f "python3.*ontology-eval-agent" > /dev/null; do sleep 60; done
extra_for() { case "$1" in enron) echo "--max_documents 500";; llms4ol-*) echo "--blind";; esac; }
for d in llms4ol-ecology enron; do
  retry ./py.sh ontology-eval-agent.py --dataset "$d" --runs ${RUNS:-3} $(extra_for "$d")
done
retry ./py.sh reference-baseline.py --max_documents 500
retry ./py.sh extraction-aids.py
retry ./py.sh compare-sessions.py --with_kg --max_documents 500
for d in gutbrainie llms4ol-scholarly llms4ol-engineering; do
  retry ./py.sh ontology-eval-agent.py --dataset "$d" --runs ${ABLATION_RUNS:-2} --prompt blind
  retry ./py.sh ontology-eval-agent.py --dataset "$d" --runs ${ABLATION_RUNS:-2} --refine_turns 0
done
./py.sh make-figures.py
