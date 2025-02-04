#!/bin/bash
#SBATCH --job-name=run_eval
#SBATCH -c 1
#SBATCH --mem 11G
#SBATCH -a 0-6%1
#SBATCH --account=bkantz
#SBATCH --output=logs/eval_%A_%a.out
#SBATCH --error=logs/eval_%A_%a.err

cd ..
source ../../backend/.venv/bin/activate

datasets=("dbpedia" "bto" "uniprot")

dataset_id=$(($SLURM_ARRAY_TASK_ID % 3))
zeroshot=$(($SLURM_ARRAY_TASK_ID / 3))
cfg_idx=0
selected_dataset=${datasets[$dataset_id]}
echo "dataset_id: $dataset_id"
echo "selected_dataset: $selected_dataset"
echo "zeroshot: $zeroshot"
echo "cfg_idx: $cfg_idx"

if [ $zeroshot -eq 1 ]
then
    echo "Running zeroshot"
    python query-eval.py --dataset $selected_dataset --cfg_idx $cfg_idx --zeroshot
else
    echo "Running normal"
    python query-eval.py --dataset $selected_dataset --cfg_idx $cfg_idx
fi
