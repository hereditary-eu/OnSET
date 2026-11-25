#!/bin/bash
# Agent runs on every evaluation dataset (one array task per dataset), guided prompt + 1 refinement.
# Extra arguments are passed to ontology-eval-agent.py, e.g. `sbatch slurm_eval_builder.sh --runs 5`.
#SBATCH --job-name=onset_onto_eval
#SBATCH -c 8
#SBATCH --mem 32G
#SBATCH --gres=gpu:1
#SBATCH -a 0-4
#SBATCH --account=bkantz
#SBATCH --output=logs/eval_%A_%a.out
#SBATCH --error=logs/eval_%A_%a.err

cd ..
datasets=("gutbrainie" "enron" "llms4ol-scholarly" "llms4ol-engineering" "llms4ol-ecology")
selected_dataset=${datasets[$SLURM_ARRAY_TASK_ID]}
echo "dataset: $selected_dataset"
extra=()
# Enron: a random sample of the ~30k sent mails; LLMs4OL: also the blind (official test) submission
[ "$selected_dataset" = "enron" ] && extra+=(--max_documents 500)
[[ "$selected_dataset" == llms4ol-* ]] && extra+=(--blind)
# a native crash (llama.cpp / Tentris) ends the process: rerun, finished runs are skipped
for attempt in 1 2 3; do
  ./py.sh ontology-eval-agent.py --dataset "$selected_dataset" --runs 3 "${extra[@]}" "$@" && break
done
