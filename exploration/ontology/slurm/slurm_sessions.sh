#!/bin/bash
# Scores the users' saved builder sessions (default: the backend's save_dir), rebuilding their KGs.
# `sbatch slurm_sessions.sh --sessions_dir /path/to/builder-saves`
#SBATCH --job-name=onset_onto_sessions
#SBATCH -c 8
#SBATCH --mem 32G
#SBATCH --gres=gpu:1
#SBATCH --account=bkantz
#SBATCH --output=logs/sessions_%j.out
#SBATCH --error=logs/sessions_%j.err

cd ..
./py.sh compare-sessions.py --with_kg --max_documents 500 "$@"
