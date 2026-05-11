"""
Automated scheduler for CUMULUS Multi-Source Pipeline.
CIS 600 Master's Project — University of Massachusetts Dartmouth.

Runs all four pipelines every 6 hours using the `schedule` library,
mirroring the production cron cadence from the EGR 500 internship.
After each complete run, triggers PipelineAnalyzer to generate a
quality report for that date.

Usage:
    python scheduler.py

Keep running until Ctrl+C.
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import schedule

sys.path.insert(0, str(Path(__file__).parent))

from pipelines.ww3_pipeline import run_ww3_pipeline
from pipelines.sst_pipeline import run_sst_pipeline
from pipelines.currents_pipeline import run_currents_pipeline
from pipelines.tides_pipeline import run_tides_pipeline
from analysis.data_analyzer import PipelineAnalyzer
from config import LOGS_DIR

# ---- Scheduler-specific file logger ----
LOGS_DIR.mkdir(parents=True, exist_ok=True)
_log_file = LOGS_DIR / "scheduler.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_file, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scheduler")


PIPELINES = [
    ("WW3",      run_ww3_pipeline),
    ("SST",      run_sst_pipeline),
    ("Currents", run_currents_pipeline),
    ("Tides",    run_tides_pipeline),
]


def _run_pipeline_safe(name: str, func) -> dict:
    """
    Run a single pipeline, catching all exceptions so one failure cannot
    prevent subsequent pipelines from running.

    Args:
        name: Human-readable pipeline name for logging.
        func: Pipeline entry-point callable returning a result dict.

    Returns:
        dict: Pipeline result, or a failure dict on exception.
    """
    log.info(f">>> Starting {name} pipeline")
    try:
        result = func()
        status = result.get("status", "unknown")
        pts = result.get("points_processed", 0)
        dur = result.get("duration", 0)
        log.info(f"<<< {name} finished — status={status} points={pts} duration={dur:.2f}s")
        return result
    except Exception as e:
        log.error(f"<<< {name} EXCEPTION: {e}")
        return {"status": "failed", "error": str(e), "points_processed": 0, "duration": 0}


def run_all_scheduled():
    """
    Run all four pipelines in sequence then generate a quality report.
    Called automatically by the schedule every 6 hours.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    log.info("=" * 60)
    log.info(f"SCHEDULED RUN — {datetime.utcnow().isoformat()}")
    log.info("=" * 60)

    results = {}
    for name, func in PIPELINES:
        results[name] = _run_pipeline_safe(name, func)

    # Quality report
    try:
        log.info("Generating quality report…")
        PipelineAnalyzer().generate_quality_report(today)
        log.info(f"Quality report saved for {today}")
    except Exception as e:
        log.error(f"Quality report failed: {e}")

    # Summary
    successes = sum(1 for r in results.values() if r.get("status") == "success")
    log.info(f"Run complete — {successes}/{len(PIPELINES)} pipelines succeeded")
    log.info("=" * 60)
    log.info(f"Next run at: {_next_run_time()}")


def _next_run_time() -> str:
    """Return the timestamp of the next scheduled job as a string."""
    jobs = schedule.get_jobs()
    if not jobs:
        return "N/A"
    nxt = min(j.next_run for j in jobs)
    return str(nxt)


def _print_banner():
    """Print startup information to console."""
    print("\n" + "=" * 60)
    print("  CUMULUS Pipeline Scheduler")
    print("  CIS 600 — University of Massachusetts Dartmouth")
    print("=" * 60)
    print(f"  Start time : {datetime.utcnow().isoformat()}")
    print(f"  Log file   : {_log_file}")
    print(f"  Cadence    : every 6 hours")
    print(f"  Pipelines  : {', '.join(n for n, _ in PIPELINES)}")
    print("=" * 60)
    print("  Running first cycle immediately…")
    print("  Press Ctrl+C to stop.\n")


if __name__ == "__main__":
    _print_banner()

    # Run immediately on first launch
    run_all_scheduled()

    # Then every 6 hours
    schedule.every(6).hours.do(run_all_scheduled)

    log.info(f"Scheduler active — next run at {_next_run_time()}")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Scheduler stopped by user (Ctrl+C).")
        print("\nScheduler stopped.")
