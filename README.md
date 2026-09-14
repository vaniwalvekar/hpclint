# hpclint

**The missing pre-flight check for HPC jobs — and the first piece of a
complete Slurm job assistant.**

Every HPC user has felt this: you write a job script, submit it, wait in
queue for twenty minutes, and watch it die in the first second because you
asked for more memory than any node has. Or worse — it runs for six hours,
using 100% CPU the whole time, and produces nothing, because it was quietly
stuck the entire way through.

hpclint exists so that stops happening.

## The idea

A Slurm job goes through a lifecycle — written, submitted, queued, run,
finished (or not) — and at almost every stage, something can quietly go
wrong that nobody notices until it's too late. hpclint is being built to
watch the whole lifecycle, not just one moment of it.

### 🧭 Before you submit
*Catch the mistake while it's still free to fix.*
- Check `#SBATCH` resource requests against your cluster's real hardware
- Understand how a job actually parallelizes (MPI vs. threaded vs. hybrid)
  so it's never flagged for doing the right thing the "wrong" way
- Warn about slow storage paths (`$HOME`) before a data-heavy job crawls
- Catch core-overflow mistakes and missing referenced files

### 📡 While it runs
*A job that's "running" isn't the same as a job that's working.*
- A unified live view combining `squeue` state and `sstat` resource usage
- **Detect a job that's stuck, not working** — running, maybe even pegged
  at 100% CPU, but producing nothing: no new output files, no progress.
  That combination — busy but silent — is one of the hardest failure
  modes to notice manually, and one of the most expensive, since it can
  burn an entire walltime allocation before anyone checks in

### 🔍 After it finishes
*Turn "it failed" into "here's why, and here's the fix." (planned)*
- Translate cryptic exit codes, OOM kills, and segfaults into plain
  language with a likely cause
- Track your own jobs over time and spot recurring over-request patterns

### 🗺️ Anywhere on the cluster
*The stuff that has nothing to do with any one job, but eats time anyway. (planned)*
- "I need GROMACS" → the right `module load` command, instantly
- Storage quota checks before `$HOME` quietly fills up
- "Which partition should I use?" — recommend resources from a plain
  description of the workload

## Where things stand today

**Before you submit** and **While it runs** are both functional:

- `hpclint check` — validates `#SBATCH` directives against a cluster's
  real hardware and rules (YAML-configured, works on any Slurm cluster),
  MPI-vs-threaded aware, catches core-overflow math and missing
  referenced files, unit-safe memory parsing
- `hpclint watch` — combines live `squeue`/`sstat` status with output
  directory activity to flag the "busy but silent" stuck-job pattern
- 29-test regression suite covering both, including realistic fixture
  `squeue`/`sstat` output text (the actual subprocess calls will be
  verified against real Slurm on Libra once more of the roadmap is built)

```
$ hpclint check my_job.sh --config myuniversity.yaml

Checks completed. Here's the result:

Cluster:       My University HPC
File checked:  my_job.sh

Parameters checked:
  --partition = compute
  --nodes = 1
  --gpus = (not set)
  --account = (not set)
  --cpus-per-task = 4
  --mem = 16G
  --time = 01:00:00

Found 2 issue(s):

1. No --gpus set. This cluster requires a GPU count on every job script
   (use --gpus=0 on 'compute', which has no GPUs).
2. No --account set. This cluster recommends always setting --account.
```

It's published on TestPyPI for now, with a real PyPI release planned once
more of the roadmap is built out and verified end-to-end on a real
cluster. **After it finishes** and **Anywhere on the cluster** are still
the roadmap, not built yet. It's an early, actively-developed project,
built in the open on purpose: if you run Slurm and any of this resonates,
your cluster's quirks and your ideas are exactly what would make this
better.

## Why this doesn't already exist

Plenty of great tools cover pieces of this — `jobstats`, `seff`, and
`reportseff` are all excellent at telling you how a *completed* job
performed. Nothing widely adopted watches the whole journey: before,
during, and after, tuned to your specific cluster's rules. That's the gap
hpclint is aiming to fill.

## Installation

**From TestPyPI** (current release, while the project is still early):

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ hpclint
```

**From source** (for development, or to get the latest unreleased changes):

```bash
git clone https://github.com/vaniwalvekar/hpclint.git
cd hpclint
pip install -e .
```

## Usage

**Check a script before submitting:**
```bash
hpclint check <path_to_script> --config <path_to_cluster_config.yaml>
```

**Watch a running job's live status:**
```bash
hpclint watch <jobid> --output-dir <path_the_job_writes_to> [--stale-minutes 30]
```
Flags a job that's `RUNNING` and burning CPU time, but hasn't changed
anything in its output directory recently — the "busy but silent" pattern
that's easy to miss manually and can burn an entire walltime allocation
before anyone notices.

Exit codes (for `check`): `0` = no issues found, `1` = issues found,
`2` = usage/file error.

## Writing a config for your cluster

See [`configs/libra.yaml`](configs/libra.yaml) for a full real-world
example. The shape is:

```yaml
cluster_name: "My University HPC"

partitions:
  compute:
    is_default: true
    has_gpu: false
    cpus_per_task_max: 64
    mem_gb_max: 1024

  gpu:
    is_default: false
    has_gpu: true
    gpu_max: 4
    cpus_per_task_max: 64
    mem_gb_max: 512

required_fields: ["nodes", "gpus"]
recommended_fields: ["account"]
default_time_days: 7

slow_io_paths:
  - path_markers: ["/home/", "$HOME"]
    recommend: "$SCRATCH"
```

Omit any section your cluster doesn't need — missing sections are treated
as "not applicable," not errors.

## Running the tests

```bash
pip install -e ".[dev]"
python3 -m pytest tests/ -v
```

The suite locks in real bugs found during development (an MPI false
positive, a memory-unit parsing bug, core-overflow math) and validates
the monitoring logic against realistic sample Slurm output, so these
can't silently break later.

## Contributing

Contributions are welcome — cluster configs for other institutions, new
checks for parallelism patterns, or a hand with any item on the roadmap
above. Open an issue before a large PR so we can talk it through first.

## License

MIT — see [LICENSE](LICENSE).
