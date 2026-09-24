"""
Tests for hpclint.monitor — parsing and health-assessment logic only.

These test the pure functions against realistic fixture text, not the
actual subprocess calls (run_squeue/run_sstat), since that needs a real
Slurm cluster. Those two functions get exercised for real once this is
tested on Libra, per the project's plan to verify everything end-to-end
at that point rather than piecemeal.
"""

import os
import time

from hpclint.monitor import (
    parse_squeue_line,
    parse_sstat_line,
    check_output_activity,
    assess_job_health,
    _parse_cpu_time_to_seconds,
)

# --- CPU/elapsed time parsing (HPC-1: D-HH:MM:SS crash) --------------------

def test_parse_time_hhmmss():
    assert _parse_cpu_time_to_seconds("01:23:45") == 5025

def test_parse_time_mmss():
    assert _parse_cpu_time_to_seconds("23:45") == 1425

def test_parse_time_seconds_only():
    assert _parse_cpu_time_to_seconds("45") == 45

def test_parse_time_with_days_no_crash():
    # '2-03:04:05' == 2 days, 3h, 4m, 5s  -> the crash case from HPC-1
    assert _parse_cpu_time_to_seconds("2-03:04:05") == 2 * 86400 + 3 * 3600 + 4 * 60 + 5

def test_parse_time_days_only():
    assert _parse_cpu_time_to_seconds("5-00:00:00") == 5 * 86400

def test_parse_time_garbage_returns_none():
    assert _parse_cpu_time_to_seconds("N/A") is None
    assert _parse_cpu_time_to_seconds("bogus") is None

def test_assess_health_long_job_does_not_crash():
    info = {"jobid": "9", "state": "RUNNING", "time_used": "2-03:04:05",
            "nodes": "1", "cpus": "8"}
    activity = {"exists": True, "file_count": 0, "stale": False, "minutes_since_change": None}
    verdict = assess_job_health(info, activity)
    assert isinstance(verdict, str) and "RUNNING" in verdict


# --- squeue parsing ---------------------------------------------------------

def test_parse_squeue_line_running_job():
    line = "12345|RUNNING|01:23:45|1-00:00:00|2|16"
    info = parse_squeue_line(line)
    assert info == {
        "jobid": "12345",
        "state": "RUNNING",
        "time_used": "01:23:45",
        "time_limit": "1-00:00:00",
        "nodes": 2,
        "cpus": 16,
    }


def test_parse_squeue_line_pending_job():
    line = "99999|PENDING|0:00|02:00:00|1|4"
    info = parse_squeue_line(line)
    assert info["state"] == "PENDING"


def test_parse_squeue_line_empty_returns_none():
    assert parse_squeue_line("") is None
    assert parse_squeue_line(None) is None


def test_parse_squeue_line_malformed_returns_none():
    assert parse_squeue_line("not|enough|fields") is None


# --- sstat parsing -----------------------------------------------------------

def test_parse_sstat_line():
    line = "12345.batch|00:45:12|2048576K|1024288K"
    info = parse_sstat_line(line)
    assert info == {
        "jobid": "12345.batch",
        "ave_cpu": "00:45:12",
        "max_rss": "2048576K",
        "ave_rss": "1024288K",
    }


def test_parse_sstat_line_empty_returns_none():
    assert parse_sstat_line("") is None
    assert parse_sstat_line(None) is None


# --- output directory activity ----------------------------------------------

def test_output_activity_missing_dir(tmp_path):
    result = check_output_activity(str(tmp_path / "does_not_exist"))
    assert result["exists"] is False


def test_output_activity_fresh_file_not_stale(tmp_path):
    f = tmp_path / "output.log"
    f.write_text("progress...")
    result = check_output_activity(str(tmp_path), stale_after_minutes=30)
    assert result["exists"] is True
    assert result["stale"] is False


def test_output_activity_old_file_is_stale(tmp_path):
    f = tmp_path / "output.log"
    f.write_text("progress...")
    old_time = time.time() - (60 * 60)  # 1 hour ago
    os.utime(f, (old_time, old_time))
    result = check_output_activity(str(tmp_path), stale_after_minutes=30)
    assert result["exists"] is True
    assert result["stale"] is True


def test_output_activity_empty_dir_is_stale(tmp_path):
    result = check_output_activity(str(tmp_path), stale_after_minutes=30)
    assert result["exists"] is True
    assert result["stale"] is True
    assert result["most_recent_file"] is None
    assert result["file_count"] == 0


def test_output_activity_reports_file_count(tmp_path):
    (tmp_path / "a.log").write_text("x")
    (tmp_path / "b.log").write_text("y")
    result = check_output_activity(str(tmp_path))
    assert result["file_count"] == 2


# --- combined health verdict --------------------------------------------------

def test_assess_health_job_not_found():
    verdict = assess_job_health(None, {"exists": False})
    assert "not found" in verdict.lower()


def test_assess_health_not_yet_running():
    squeue_info = {"jobid": "1", "state": "PENDING", "time_used": "0:00", "time_limit": "1:00:00", "nodes": 1, "cpus": 1}
    verdict = assess_job_health(squeue_info, {"exists": False})
    assert "PENDING" in verdict


def test_assess_health_busy_but_silent_flagged():
    # Regression target: this is the exact pattern we set out to catch —
    # real accrued CPU time, but the output directory has gone stale.
    squeue_info = {"jobid": "1", "state": "RUNNING", "time_used": "02:15:00", "time_limit": "1-00:00:00", "nodes": 1, "cpus": 8}
    activity_info = {"exists": True, "stale": True, "minutes_since_change": 90, "most_recent_file": "/data/out.log"}
    verdict = assess_job_health(squeue_info, activity_info)
    assert "busy-but-silent" in verdict or "stuck" in verdict.lower()


def test_assess_health_healthy_job_not_flagged():
    squeue_info = {"jobid": "1", "state": "RUNNING", "time_used": "02:15:00", "time_limit": "1-00:00:00", "nodes": 1, "cpus": 8}
    activity_info = {"exists": True, "stale": False, "minutes_since_change": 2, "most_recent_file": "/data/out.log"}
    verdict = assess_job_health(squeue_info, activity_info)
    assert "healthy" in verdict.lower() or "actively updated" in verdict.lower()


def test_assess_health_early_startup_not_flagged_as_stuck():
    # Low CPU time + stale output is treated differently from high CPU +
    # stale output — this is likely just startup, not the busy-but-silent case.
    squeue_info = {"jobid": "1", "state": "RUNNING", "time_used": "0:05", "time_limit": "1-00:00:00", "nodes": 1, "cpus": 8}
    activity_info = {"exists": True, "stale": True, "minutes_since_change": 40, "most_recent_file": None}
    verdict = assess_job_health(squeue_info, activity_info)
    assert "busy-but-silent" not in verdict


def test_assess_health_long_running_with_zero_files_ever_flagged():
    # The specific gap being fixed: a job that has run a long time and
    # never written a single file, not just one that's gone stale partway.
    squeue_info = {"jobid": "1", "state": "RUNNING", "time_used": "05:00:00", "time_limit": "1-00:00:00", "nodes": 1, "cpus": 8}
    activity_info = {"exists": True, "stale": True, "minutes_since_change": None, "most_recent_file": None, "file_count": 0}
    verdict = assess_job_health(squeue_info, activity_info)
    assert "never written" in verdict.lower()
    assert "05:00:00" in verdict


def test_assess_health_just_started_with_zero_files_not_alarming():
    # Same zero-files situation, but the job just started — this should
    # read as "too early to tell," not "stuck."
    squeue_info = {"jobid": "1", "state": "RUNNING", "time_used": "0:10", "time_limit": "1-00:00:00", "nodes": 1, "cpus": 8}
    activity_info = {"exists": True, "stale": True, "minutes_since_change": None, "most_recent_file": None, "file_count": 0}
    verdict = assess_job_health(squeue_info, activity_info)
    assert "hasn't written anything" in verdict.lower()
    assert "not concerning yet" in verdict.lower()
