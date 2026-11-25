#!/bin/bash
# Extraction with the true (reference) ontologies, no agent: GutBrainIE dev and 500 Enron mails.
#SBATCH --job-name=onset_onto_reference
#SBATCH -c 8
#SBATCH --mem 32G
#SBATCH --gres=gpu:1
#SBATCH -a 0-1
#SBATCH --account=bkantz
#SBATCH --output=logs/reference_%A_%a.out
#SBATCH --error=logs/reference_%A_%a.err

cd ..
datasets=("gutbrainie" "enron")
./py.sh reference-baseline.py --dataset "${datasets[$SLURM_ARRAY_TASK_ID]}" --max_documents 500 "$@"
