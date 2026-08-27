import re
import sys

# Hard limits for the 'compute' partition on Libra
LIMITS = {
    "cpus_per_task_max": 64,   # 32C/64T per node
    "mem_gb_max": 1024,        # 1 TB per node
}

VALID_PARTITIONS = {"compute", "gpu", "machinelearning"}

def read_script(path):
    with open(path, "r") as f:
        return f.read()

def find_sbatch_value(content, key):
    # Looks for lines like: #SBATCH --key=value
    match = re.search(rf"#SBATCH\s+--{key}=(\S+)", content)
    return match.group(1) if match else None

def parse_mem_to_gb(mem_str):
    # Handles values like 1200G, 500M, 2T, 8000MB, 500GB, etc.
    if mem_str is None:
        return None
    num = float(re.sub(r"[A-Za-z]", "", mem_str))
    unit = re.sub(r"[0-9.]", "", mem_str).upper().rstrip("B")  # normalize MB->M, GB->G, TB->T, KB->K
    if unit == "T":
        return num * 1024
    elif unit == "M":
        return num / 1024
    elif unit == "K":
        return num / (1024 * 1024)
    return num  # assume G if no unit or 'G'

def check_script(path):
    content = read_script(path)
    issues = []

    partition = find_sbatch_value(content, "partition")
    cpus = find_sbatch_value(content, "cpus-per-task")
    mem = find_sbatch_value(content, "mem")
    time_limit = find_sbatch_value(content, "time")
    nodes = find_sbatch_value(content, "nodes")
    gpus = find_sbatch_value(content, "gpus")
    account = find_sbatch_value(content, "account")
    ntasks = find_sbatch_value(content, "ntasks")
    ntasks_per_node = find_sbatch_value(content, "ntasks-per-node")

    # An MPI job parallelizes across ranks (ntasks), not threads-per-rank (cpus-per-task).
    # Detect MPI usage so we don't wrongly flag a missing --cpus-per-task on a pure-MPI job.
    is_mpi_job = bool(
        (ntasks or ntasks_per_node)
        and re.search(r"\b(mpirun|mpiexec|srun)\b", content)
    )

    params_checked = {
        "partition": partition,
        "nodes": nodes,
        "gpus": gpus,
        "account": account,
        "cpus-per-task": cpus,
        "ntasks": ntasks,
        "ntasks-per-node": ntasks_per_node,
        "mem": mem,
        "time": time_limit,
    }

    if partition and partition not in VALID_PARTITIONS:
        issues.append(
            f"Partition '{partition}' is not a valid Libra partition. "
            f"Valid options are: {', '.join(sorted(VALID_PARTITIONS))}."
        )
    # No --partition line at all is fine — 'compute' is the cluster default.

    effective_partition = partition if partition in VALID_PARTITIONS else "compute"
    if effective_partition != "compute":
        issues.append(
            f"Note: this checker's resource limits (CPU/mem/GPU) are currently only validated for "
            f"the 'compute' partition. Partition '{effective_partition}' was detected but not fully checked yet."
        )

    # Per Libra docs: nodes, time, and gpus are the minimum required options
    if not nodes:
        issues.append("No --nodes set. Libra requires --nodes on every job script.")

    if gpus is None:
        issues.append(
            "No --gpus set. Libra requires a GPU count on every job script "
            "(use --gpus=0 on the 'compute' partition, which has no GPUs)."
        )
    elif effective_partition == "compute" and gpus != "0":
        issues.append(
            f"Requested --gpus={gpus}, but 'compute' nodes have no GPUs. Set --gpus=0 or use the 'gpu' partition."
        )

    if not account:
        issues.append("No --account set. Libra recommends always setting --account=<project_name>.")

    if effective_partition == "compute":
        if cpus:
            cpus_int = int(cpus)
            if cpus_int > LIMITS["cpus_per_task_max"]:
                issues.append(
                    f"Requested {cpus_int} CPUs, but 'compute' nodes only have "
                    f"{LIMITS['cpus_per_task_max']} threads. Lower --cpus-per-task."
                )
        elif is_mpi_job:
            pass  # MPI jobs parallelize via --ntasks/--ntasks-per-node, not --cpus-per-task; absence is fine
        else:
            issues.append("No --cpus-per-task set (Slurm will default to 1, which may waste your time budget).")

    if effective_partition == "compute":
        if mem:
            mem_gb = parse_mem_to_gb(mem)
            if mem_gb > LIMITS["mem_gb_max"]:
                issues.append(
                    f"Requested {mem} (~{mem_gb:.0f}G), but 'compute' nodes only have "
                    f"{LIMITS['mem_gb_max']}G RAM. Lower --mem."
                )
        else:
            issues.append("No --mem set (job may get a low default allocation).")

    if not time_limit:
        issues.append(
            "No --time set. Libra defaults to a 7-day walltime if omitted — "
            "fine for short jobs, but set it explicitly for anything you want the scheduler to plan around."
        )

    if "/home/" in content or "$HOME" in content:
        issues.append(
            "Script references /home or $HOME for file operations. Libra's home file system isn't "
            "tuned for high-performance I/O — use $SCRATCH for data-intensive read/write instead."
        )

    return params_checked, issues

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 check_script.py <path_to_slurm_script>")
        sys.exit(2)

    path = sys.argv[1]

    try:
        params_checked, issues = check_script(path)
    except FileNotFoundError:
        print(f"Error: could not find file '{path}'")
        sys.exit(2)

    print("Checks completed. Here's the result:\n")

    print(f"File checked: {path}\n")

    print("Parameters checked:")
    for key, value in params_checked.items():
        display_value = value if value is not None else "(not set)"
        print(f"  --{key} = {display_value}")
    print()

    if issues:
        print(f"Found {len(issues)} issue(s):\n")
        for i, issue in enumerate(issues, 1):
            print(f"{i}. {issue}")
        sys.exit(1)  # non-zero exit = issues found, useful if this gets called from other tools later
    else:
        print("No issues found.")
        sys.exit(-1)
