#!/bin/bash
#SBATCH --job-name=gromacs_md
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --mem=8000MB
#SBATCH --time=04:00:00
#SBATCH --account=earm

module load gromacs
mpirun -np 8 mdrun_mpi -deffnm md
