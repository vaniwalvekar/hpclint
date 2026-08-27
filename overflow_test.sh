#!/bin/bash
#SBATCH --job-name=overflow_test
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --account=myproj
#SBATCH --gpus=0

module load python/3.10
srun python analyze.py
