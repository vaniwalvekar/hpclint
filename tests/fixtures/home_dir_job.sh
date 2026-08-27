#!/bin/bash
#SBATCH --job-name=data_summary
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00

module load python/3.10

cd $HOME/projects/data_summary
python real_script.py
