#!/usr/bin/env python3
"""
hpc_preflight — check a Slurm job script against a cluster's real hardware
limits and submission rules, before you submit it.

Usage:
    python3 hpc_preflight.py <path_to_slurm_script> --config <path_to_cluster_config.yaml>
"""

import re
import sys
import argparse

try:
    import yaml
except ImportError:
    print("Missing dependency: PyYAML. Install with: pip install pyyaml")
    sys.exit(2)


def read_script(path):
    with open(path, "r") as f:
        return f.read()


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def find_sbatch_value(content, key):
    match = re.search(rf"#SBATCH\s+--{key}=(\S+)", content)
    return match.group(1) if match else None


def parse_mem_to_gb(mem_str):
    if mem_str is None:
        return None
    num = float(re.sub(r"[A-Za-z]", "", mem_str))
    unit = re.sub(r"[0-9.]", "", mem_str).upper().rstrip("B")
    if unit == "T":
        return num * 1024
    elif unit == "M":
        return num / 1024
    elif unit == "K":
        return num / (1024 * 1024)
    return num  # assume GB if no unit or 'G'


def check_script(script_path, config):
    content = read_script(script_path)
    issues = []

    partitions = config.get("partitions", {})
    valid_partitions = set(partitions.keys())
    default_partition = next(
        (name for name, spec in partitions.items() if spec.get("is_default")),
        next(iter(valid_partitions), None),
    )
    required_fields = config.get("required_fields", [])
    recommended_fields = config.get("recommended_fields", [])
    default_time_days = config.get("default_time_days")
    slow_io_paths = config.get("slow_io_paths", [])

    partition = find_sbatch_value(content, "partition")
    cpus = find_sbatch_value(content, "cpus-per-task")
    mem = find_sbatch_value(content, "mem")
    time_limit = find_sbatch_value(content, "time")
    nodes = find_sbatch_value(content, "nodes")
    gpus = find_sbatch_value(content, "gpus")
    account = find_sbatch_value(content, "account")
    ntasks = find_sbatch_value(content, "ntasks")
    ntasks_per_node = find_sbatch_value(content, "ntasks-per-node")

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

    # --- Partition validity ---
    if partition and partition not in valid_partitions:
        issues.append(
            f"Partition '{partition}' is not valid for {config.get('cluster_name', 'this cluster')}. "
            f"Valid options are: {', '.join(sorted(valid_partitions))}."
        )
    effective_partition = partition if partition in valid_partitions else default_partition
    partition_spec = partitions.get(effective_partition, {})

    # --- Required / recommended fields (generic to any Slurm cluster) ---
    if "nodes" in required_fields and not nodes:
        issues.append("No --nodes set. This cluster requires --nodes on every job script.")

    has_gpu = partition_spec.get("has_gpu", False)
    gpu_max = partition_spec.get("gpu_max")
    if "gpus" in required_fields and gpus is None:
        note = f" (use --gpus=0 on '{effective_partition}', which has no GPUs)" if not has_gpu else ""
        issues.append(f"No --gpus set. This cluster requires a GPU count on every job script{note}.")
    elif gpus is not None:
        if not has_gpu and gpus != "0":
            issues.append(
                f"Requested --gpus={gpus}, but '{effective_partition}' has no GPUs. Set --gpus=0 or use a GPU partition."
            )
        elif has_gpu and gpu_max is not None and int(gpus) > gpu_max:
            issues.append(
                f"Requested --gpus={gpus}, but '{effective_partition}' nodes only have {gpu_max} GPUs. Lower --gpus."
            )

    for field in recommended_fields:
        if not find_sbatch_value(content, field):
            issues.append(f"No --{field} set. This cluster recommends always setting --{field}.")

    # --- Resource ceilings for the resolved partition ---
    cpus_max = partition_spec.get("cpus_per_task_max")
    if cpus:
        if cpus_max is not None and int(cpus) > cpus_max:
            issues.append(
                f"Requested {cpus} CPUs, but '{effective_partition}' nodes only have {cpus_max} threads. "
                f"Lower --cpus-per-task."
            )
    elif not is_mpi_job:
        issues.append("No --cpus-per-task set (the scheduler will default to 1, which may waste your time budget).")
    # If it's an MPI job, absence of --cpus-per-task is expected (parallelism comes from --ntasks instead).

    # --- Total cores per node overflow check (ntasks-per-node x cpus-per-task) ---
    # Each piece can look fine alone; only the combination reveals it won't fit on one node.
    tasks_per_node = None
    if ntasks_per_node:
        tasks_per_node = int(ntasks_per_node)
    elif ntasks and nodes:
        # ntasks is a total across all nodes; estimate the per-node share.
        tasks_per_node = -(-int(ntasks) // int(nodes))  # ceiling division

    if tasks_per_node and cpus_max is not None:
        cpus_per_task_int = int(cpus) if cpus else 1  # Slurm defaults --cpus-per-task to 1 if unset
        total_cores_per_node = tasks_per_node * cpus_per_task_int
        if total_cores_per_node > cpus_max:
            issues.append(
                f"{tasks_per_node} tasks/node x {cpus_per_task_int} cpus-per-task = {total_cores_per_node} "
                f"cores per node, but '{effective_partition}' nodes only have {cpus_max} threads. "
                f"Lower --ntasks-per-node or --cpus-per-task."
            )

    mem_max = partition_spec.get("mem_gb_max")
    if mem:
        mem_gb = parse_mem_to_gb(mem)
        if mem_max is not None and mem_gb > mem_max:
            issues.append(
                f"Requested {mem} (~{mem_gb:.0f}G), but '{effective_partition}' nodes only have {mem_max}G RAM. "
                f"Lower --mem."
            )
    else:
        issues.append("No --mem set (job may get a low default allocation).")

    if not time_limit and default_time_days is not None:
        issues.append(
            f"No --time set. This cluster defaults to a {default_time_days}-day walltime if omitted — "
            f"fine for short jobs, but set it explicitly for anything you want the scheduler to plan around."
        )

    for rule in slow_io_paths:
        if any(marker in content for marker in rule.get("path_markers", [])):
            issues.append(
                f"Script references a slow storage path. Consider using {rule.get('recommend', 'a faster filesystem')} "
                f"for data-intensive read/write instead."
            )

    return params_checked, issues


def main():
    parser = argparse.ArgumentParser(description="Check a Slurm job script against your cluster's real limits.")
    parser.add_argument("script", help="Path to the Slurm job script (.sh/.slurm) to check")
    parser.add_argument("--config", required=True, help="Path to your cluster's YAML config file")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: could not find config file '{args.config}'")
        sys.exit(2)

    try:
        params_checked, issues = check_script(args.script, config)
    except FileNotFoundError:
        print(f"Error: could not find script file '{args.script}'")
        sys.exit(2)

    print("Checks completed. Here's the result:\n")
    print(f"Cluster:       {config.get('cluster_name', 'unknown')}")
    print(f"File checked:  {args.script}\n")

    print("Parameters checked:")
    for key, value in params_checked.items():
        display_value = value if value is not None else "(not set)"
        print(f"  --{key} = {display_value}")
    print()

    if issues:
        print(f"Found {len(issues)} issue(s):\n")
        for i, issue in enumerate(issues, 1):
            print(f"{i}. {issue}")
        sys.exit(1)
    else:
        print("No issues found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
