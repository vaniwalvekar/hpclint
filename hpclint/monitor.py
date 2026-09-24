"""
hpclint.monitor — live monitoring for a running Slurm job: unified
squeue/sstat status, plus detection of jobs that are running but not
actually making progress (busy-but-silent / stuck).

Split deliberately into:
  - parsing functions (pure, testable against fixture text)
  - a thin subprocess wrapper (talks to the real squeue/sstat commands)

so the logic can be developed and tested without a live Slurm cluster,
and only the wrapper needs a real cluster to exercise.
"""

import os
import subprocess
import time


# --- Subprocess wrappers (need a real Slurm cluster to actually run) ------

def select_squeue_line(text, jobid):
    """Pick the single relevant line from multi-line squeue output.

    `squeue -j <id>` can emit more than one line: one per array task
    (12345_0, 12345_1, ...) or per job step (.batch/.extern). We want the
    main job, so prefer the line whose JobID exactly equals the requested
    id; otherwise fall back to the first non-empty line. Returns None when
    there is no output (job not in queue).
    """
    if not text:
        return None
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None
    wanted = str(jobid)
    for line in lines:
        if line.split("|")[0].strip() == wanted:
            return line
    return lines[0]


def run_squeue(jobid):
    """Run squeue for one job and return its raw pipe-delimited output line,
    or None if the job isn't found (e.g. already finished)."""
    cmd = ["squeue", "-h", "-j", str(jobid), "-o", "%i|%T|%M|%l|%D|%C"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return select_squeue_line(result.stdout, jobid)


def run_sstat(jobid):
    """Run sstat for one job and return its raw pipe-delimited output line,
    or None if no stats are available yet (e.g. job just started)."""
    cmd = ["sstat", "-j", str(jobid), "--format=JobID,AveCPU,MaxRSS,AveRSS", "-P", "-n"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    line = result.stdout.strip().split("\n")[0] if result.stdout.strip() else None
    return line


# --- Parsing (pure functions, testable with fixture text) -----------------

def parse_squeue_line(line):
    """Parse one line of `squeue -o "%i|%T|%M|%l|%D|%C"` output."""
    if not line:
        return None
    parts = line.strip().split("|")
    if len(parts) != 6:
        return None
    jobid, state, time_used, time_limit, nodes, cpus = parts
    return {
        "jobid": jobid,
        "state": state,
        "time_used": time_used,
        "time_limit": time_limit,
        "nodes": int(nodes),
        "cpus": int(cpus),
    }


def parse_sstat_line(line):
    """Parse one line of `sstat --format=JobID,AveCPU,MaxRSS,AveRSS -P` output."""
    if not line:
        return None
    parts = line.strip().split("|")
    if len(parts) != 4:
        return None
    jobid, ave_cpu, max_rss, ave_rss = parts
    return {
        "jobid": jobid,
        "ave_cpu": ave_cpu,
        "max_rss": max_rss,
        "ave_rss": ave_rss,
    }


# --- Output directory activity (works on any filesystem, no Slurm needed) -

def check_output_activity(output_dir, stale_after_minutes=30):
    """Look at every file's modification time under output_dir and report
    how long it's been since anything changed. Used to detect a job that's
    running but not actually producing anything.

    Distinguishes two different problems:
      - the directory has files, but none have changed in a while (stale)
      - the directory has never had a single file written to it (empty)
    These call for different messages: "stalled partway through" reads very
    differently from "never started producing anything at all."
    """
    if not os.path.isdir(output_dir):
        return {
            "exists": False, "stale": None, "minutes_since_change": None,
            "most_recent_file": None, "file_count": 0,
        }

    most_recent_mtime = None
    most_recent_file = None
    file_count = 0
    for root, _, files in os.walk(output_dir):
        for name in files:
            file_count += 1
            path = os.path.join(root, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if most_recent_mtime is None or mtime > most_recent_mtime:
                most_recent_mtime = mtime
                most_recent_file = path

    if most_recent_mtime is None:
        return {
            "exists": True, "stale": True, "minutes_since_change": None,
            "most_recent_file": None, "file_count": file_count,
        }

    minutes_since_change = (time.time() - most_recent_mtime) / 60
    return {
        "exists": True,
        "stale": minutes_since_change > stale_after_minutes,
        "minutes_since_change": minutes_since_change,
        "most_recent_file": most_recent_file,
        "file_count": file_count,
    }


# --- Combined health verdict ------------------------------------------------

def _parse_cpu_time_to_seconds(time_str):
    """Parse a Slurm time string into seconds.

    Handles every format Slurm emits for Time/TimeUsed:
      'MM:SS', 'HH:MM:SS', and 'D-HH:MM:SS' (and 'D-HH:MM').
    Returns None if the value cannot be parsed (e.g. 'N/A').
    """
    if not time_str:
        return 0
    s = time_str.strip()
    days = 0
    if "-" in s:
        day_part, _, s = s.partition("-")
        try:
            days = int(day_part)
        except ValueError:
            return None
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    while len(nums) < 3:
        nums.insert(0, 0)
    hours, minutes, seconds = nums[-3:]
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def assess_job_health(squeue_info, activity_info, sstat_info=None, high_cpu_time_threshold_seconds=60):
    """Combine job state, CPU time accrued, and output-directory activity
    into a plain-language verdict.

    The interesting case: a job can be RUNNING and even accruing real CPU
    time while producing nothing at all. That combination — busy but
    silent — is much harder to notice than a job that's just idle, and
    much more expensive, since it can burn an entire walltime allocation
    before anyone checks in.
    """
    if squeue_info is None:
        return "Job not found in the queue — it may have already finished. Check its final status with sacct/jobstats."

    state = squeue_info["state"]
    if state != "RUNNING":
        return f"Job is in state '{state}' — not yet running, nothing to assess."

    wall_seconds = _parse_cpu_time_to_seconds(squeue_info.get("time_used"))
    ave_cpu_seconds = (
        _parse_cpu_time_to_seconds(sstat_info.get("ave_cpu"))
        if sstat_info and sstat_info.get("ave_cpu") else None
    )
    if ave_cpu_seconds is not None:
        # Real CPU usage is the trustworthy "is it actually working" signal.
        has_accrued_cpu_time = ave_cpu_seconds >= high_cpu_time_threshold_seconds
        cpu_known = True
    else:
        # No CPU stats yet (e.g. job just started) - fall back to elapsed time.
        has_accrued_cpu_time = wall_seconds is not None and wall_seconds >= high_cpu_time_threshold_seconds
        cpu_known = False

    if not activity_info.get("exists"):
        return (
            "Job is RUNNING, but the expected output directory doesn't exist yet. "
            "Too early to tell if it's making progress."
        )

    if activity_info.get("file_count") == 0:
        elapsed = squeue_info.get("time_used", "an unknown amount of time")
        if (cpu_known and not has_accrued_cpu_time
                and wall_seconds is not None
                and wall_seconds >= high_cpu_time_threshold_seconds):
            return (
                f"Job has been running {elapsed} but its average CPU time is only "
                f"{sstat_info.get('ave_cpu')} - it is using almost no CPU and has written "
                f"nothing. This looks blocked or deadlocked (waiting on I/O, a lock, or a "
                f"resource) rather than making progress."
            )
        if has_accrued_cpu_time:
            return (
                f"Job is RUNNING and has been going for {elapsed}, but has never written a single "
                f"file to the output directory. For a job running this long, that's a strong sign "
                f"it's stuck, deadlocked, or writing somewhere other than where you're checking — "
                f"worth investigating directly."
            )
        else:
            return (
                f"Job is RUNNING ({elapsed} so far) and hasn't written anything to the output "
                f"directory yet. Likely still starting up (loading modules, reading input) — "
                f"not concerning yet, but worth another look if it's still empty later."
            )

    if activity_info.get("stale"):
        if has_accrued_cpu_time:
            minutes = activity_info.get("minutes_since_change")
            minutes_str = f"{minutes:.0f}" if minutes is not None else "an unknown number of"
            return (
                f"Job is RUNNING and has accrued CPU time, but nothing in the output directory "
                f"has changed in {minutes_str} minutes. This is the busy-but-silent pattern — "
                f"worth checking manually, it may be stuck in a loop or waiting on something that "
                f"will never resolve."
            )
        else:
            return (
                "Job is RUNNING but has used very little CPU time and the output directory is "
                "stale. It may just be starting up (loading modules, reading input), or it may be "
                "waiting on a resource. Worth a look if this persists."
            )

    return "Job is RUNNING and the output directory is being actively updated. Looks healthy."
