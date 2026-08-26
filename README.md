# hpclint

**A cluster-agnostic linter for Slurm job scripts.**

hpclint checks a job script against your HPC cluster's real hardware and
submission rules *before* you submit it — catching bad resource requests,
missing required fields, and misconfigurations while they're still free to
fix, instead of after a job has failed or wasted hours in the queue.

## What we're building

Most HPC tooling tells you how a job performed *after* it ran. hpclint is
built to catch the problem earlier — at the moment a script is written,
before a single core is ever allocated.

The end goal is a tool that:

- **Works on any Slurm cluster**, not just one institution's — hardware
  limits, partitions, and policies are supplied as configuration, not
  hardcoded, so any HPC center can adopt it for their own environment
- **Understands how HPC jobs actually parallelize** — distinguishing MPI
  jobs from threaded jobs, array jobs, hybrid MPI+OpenMP jobs, and GPU
  workloads, so it never flags a script for doing the right thing the
  "wrong" way
- **Explains itself in plain language** — every flag comes with a reason a
  new HPC user can understand, not just a cryptic warning
- **Fits into how people actually submit jobs** — usable as a standalone
  command, wrapped around `sbatch` itself for automatic pre-submission
  checks, integrated into web portals like Open OnDemand, and available
  as real-time feedback inside an editor while a script is being written
- **Optionally goes beyond fixed rules** — for issues too subtle for static
  checks (e.g. a script's actual commands not matching its resource
  request), an optional analysis layer can reason about the script more
  flexibly, without requiring it for the tool's core functionality
- **Closes the loop with monitoring** — connecting pre-submission checks
  with live job monitoring and post-run efficiency data, so the advice
  a user gets before submitting is grounded in how similar jobs actually
  performed
- **Is genuinely useful to adopt** — clear documentation, example configs
  for real clusters, and a contribution path so other HPC centers can add
  their own cluster's rules and share them back

## Why this matters

Overestimated resource requests slow down queues for everyone. Undetected
misconfigurations waste walltime and confuse new users. Existing tools
like `jobstats`, `seff`, and `reportseff` are excellent at post-run
analysis, but nothing widely adopted stops a bad job script before it's
ever submitted, tailored to the specific cluster it's headed for.

hpclint aims to be that missing first line of defense — free, open,
fast, and useful on day one for a single user, while being architected to
scale to an entire HPC center's worth of users and, eventually, to any
Slurm-based cluster willing to write a config file for it.

## License

MIT