#!/bin/bash
#SBATCH --job-name=plain_test
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --account=proj
#SBATCH --gpus=0

module load python/3.10
python real_script.py
