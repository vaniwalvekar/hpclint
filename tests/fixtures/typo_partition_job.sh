#!/bin/bash
#SBATCH --job-name=test
#SBATCH --partition=compue
#SBATCH --nodes=1
#SBATCH --gpus=0
#SBATCH --account=myproject
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
echo hello
