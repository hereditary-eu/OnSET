#!/bin/bash
# Extraction-aid ablation without the agent (fixed Type/Term ontology), one LLMs4OL domain per task.
#SBATCH --job-name=onset_onto_aids
#SBATCH -c 8
#SBATCH --mem 32G
#SBATCH --gres=gpu:1
#SBATCH -a 0-2
#SBATCH --account=bkantz
#SBATCH --output=logs/aids_%A_%a.out
#SBATCH --error=logs/aids_%A_%a.err

cd ..
datasets=("llms4ol-scholarly" "llms4ol-engineering" "llms4ol-ecology")
./py.sh extraction-aids.py --dataset "${datasets[$SLURM_ARRAY_TASK_ID]}" "$@"
