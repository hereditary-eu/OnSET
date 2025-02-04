#!/bin/bash
#SBATCH --job-name=run_eval
#SBATCH -c 3
#SBATCH --mem 8G
#SBATCH -a 0-2
#SBATCH --account=bkantz
#SBATCH --output=test_gpu_%A_%a.out
#SBATCH --error=test_gpu_%A_%a.err

cd ..
source ../../backend/.venv/bin/activate

datasets=("dbpedia" "bto" "uniprot")
selected_dataset=${datasets[$SLURM_ARRAY_TASK_ID]}

python init-db.py