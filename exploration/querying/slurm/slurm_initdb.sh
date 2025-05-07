#!/bin/bash
#SBATCH --job-name=onset_initdb
#SBATCH -c 3
#SBATCH --mem 8G
#SBATCH -a 0-3%1
#SBATCH --account=bkantz
#SBATCH --output=logs/init_%A_%a.out
#SBATCH --error=logs/init_%A_%a.err

cd ..
source ../../backend/.venv/bin/activate

echo "Running init-db for dataset $SLURM_ARRAY_TASK_ID"
python init-db.py --dataset "$SLURM_ARRAY_TASK_ID"