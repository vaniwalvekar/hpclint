"""
hpclint.cli — command-line entry point for hpclint.
"""

import sys
import argparse

from .checker import check_script, load_config


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
