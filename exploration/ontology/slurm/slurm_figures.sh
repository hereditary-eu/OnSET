#!/bin/bash
#SBATCH --job-name=onset_onto_figures
#SBATCH -c 2
#SBATCH --mem 8G
#SBATCH --account=bkantz
#SBATCH --output=logs/figures_%j.out
#SBATCH --error=logs/figures_%j.err

cd ..
./py.sh make-figures.py "$@"
