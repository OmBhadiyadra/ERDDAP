"""
Tests for core/database.py — run logging, retrieval, and duplicate prevention.
CIS 600 Master's Project — University of Massachusetts Dartmouth.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import PipelineDatabase


@pytest.fixture
def db(tmp_path):
    """Create a fresh PipelineDatabase backed by a temp SQLite file."""
    db_path = tmp_path / "test_rds.db"
    with patch("core.database.DATABASE_PATH", db_path):
        instance = PipelineDatabase()
        instance.db_path = db_path
        yield instance


class TestLogRun:
    def test_log_run_returns_true(self, db):
        result = db.log_run(
            pipeline_name="sst",
            status="success",
            points_processed=300,
            duration_seconds=4.2,
            output_s3_key="sst/2024-01-01/sst_global.json.gz",
            file_size_bytes=8192,
            pipeline_version="1.0",
        )
        assert result is True

    def test_logged_run_is_retrievable(self, db):
        db.log_run("ww3", "success", 500, 3.1, "ww3/2024-01-01/f006.json.gz", 4096, "1.0")
        runs = db.get_runs(pipeline_name="ww3")
        assert len(runs) == 1
        assert runs[0]["pipeline_name"] == "ww3"
        assert runs[0]["status"] == "success"
        assert runs[0]["points_processed"] == 500

    def test_failed_run_logged_correctly(self, db):
        db.log_run("currents", "failed", 0, 1.0, error_message="Timeout")
        runs = db.get_runs(pipeline_name="currents")
        assert runs[0]["status"] == "failed"
        assert runs[0]["error_message"] == "Timeout"


class TestGetRuns:
    def test_get_runs_all_pipelines(self, db):
        db.log_run("sst", "success", 100, 1.0)
        db.log_run("ww3", "success", 200, 2.0)
        all_runs = db.get_runs()
        assert len(all_runs) == 2

    def test_get_runs_filter_by_pipeline(self, db):
        db.log_run("sst", "success", 100, 1.0)
        db.log_run("ww3", "success", 200, 2.0)
        sst_runs = db.get_runs(pipeline_name="sst")
        assert len(sst_runs) == 1
        assert sst_runs[0]["pipeline_name"] == "sst"

    def test_limit_respected(self, db):
        for i in range(10):
            db.log_run("tides", "success", i * 10, float(i))
        runs = db.get_runs(limit=3)
        assert len(runs) == 3

    def test_empty_database_returns_empty_list(self, db):
        assert db.get_runs() == []


class TestDuplicatePrevention:
    def test_already_processed_true_after_success(self, db):
        db.log_run(
            "sst", "success", 300, 4.0,
            output_s3_key="sst/2024-01-15/sst_global.json.gz",
        )
        assert db.is_already_processed("sst", "2024-01-15") is True

    def test_already_processed_false_for_new_date(self, db):
        db.log_run(
            "sst", "success", 300, 4.0,
            output_s3_key="sst/2024-01-15/sst_global.json.gz",
        )
        assert db.is_already_processed("sst", "2024-01-16") is False

    def test_already_processed_false_for_failed_run(self, db):
        db.log_run("sst", "failed", 0, 1.0, output_s3_key="sst/2024-01-15/sst_global.json.gz")
        assert db.is_already_processed("sst", "2024-01-15") is False


class TestGetSummary:
    def test_summary_counts(self, db):
        db.log_run("sst", "success", 300, 4.0)
        db.log_run("ww3", "success", 500, 3.0)
        db.log_run("tides", "failed", 0, 1.0)
        summary = db.get_summary()
        assert summary["total_runs"] == 3
        assert summary["successful_runs"] == 2
        assert summary["total_points_processed"] == 800
