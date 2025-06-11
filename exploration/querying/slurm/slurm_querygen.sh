#!/bin/bash
#SBATCH --job-name=onset_querygen
#SBATCH -c 1
#SBATCH --mem 8G
#SBATCH -a 0-4%2
#SBATCH --account=bkantz
#SBATCH --output=logs/gen_%A_%a.out
#SBATCH --error=logs/gen_%A_%a.err

cd ..
source ../../backend/.venv/bin/activate

echo "Running query generator for dataset $SLURM_ARRAY_TASK_ID"
python querygen.py --dataset "$SLURM_ARRAY_TASK_ID"