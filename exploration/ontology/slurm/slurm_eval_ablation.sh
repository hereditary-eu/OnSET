#!/bin/bash
# Ablations of the scripted user: blind prompt (no task description) and no refinement turn.
#SBATCH --job-name=onset_onto_ablation
#SBATCH -c 8
#SBATCH --mem 32G
#SBATCH --gres=gpu:1
#SBATCH -a 0-9
#SBATCH --account=bkantz
#SBATCH --output=logs/ablation_%A_%a.out
#SBATCH --error=logs/ablation_%A_%a.err

cd ..
datasets=("gutbrainie" "enron" "llms4ol-scholarly" "llms4ol-engineering" "llms4ol-ecology")
variants=("--prompt blind --refine_turns 1" "--prompt guided --refine_turns 0")
selected_dataset=${datasets[$(($SLURM_ARRAY_TASK_ID % 5))]}
variant=${variants[$(($SLURM_ARRAY_TASK_ID / 5))]}
echo "dataset: $selected_dataset variant: $variant"
extra=()
[ "$selected_dataset" = "enron" ] && extra+=(--max_documents 500)
# a native crash (llama.cpp / Tentris) ends the process: rerun, finished runs are skipped
for attempt in 1 2 3; do
  ./py.sh ontology-eval-agent.py --dataset "$selected_dataset" --runs 3 $variant "${extra[@]}" "$@" && break
done
