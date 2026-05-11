"""
Tests for analysis/data_analyzer.py — statistics, latitude bands, categories.
Uses tmp_path to create gzipped fixture files. No network calls.
CIS 600 Master's Project — University of Massachusetts Dartmouth.
"""

import gzip
import json
import math
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.data_analyzer import PipelineAnalyzer, _compass_bucket, _safe_mean


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def write_gz(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------

class TestSafeMean:
    def test_empty_list_returns_zero(self):
        assert _safe_mean([]) == 0.0

    def test_single_value(self):
        assert _safe_mean([5.0]) == 5.0

    def test_average_correct(self):
        assert _safe_mean([1.0, 2.0, 3.0]) == 2.0


class TestCompassBucket:
    def test_north(self):
        assert _compass_bucket(0) == "N"
        assert _compass_bucket(360) == "N"

    def test_east(self):
        assert _compass_bucket(90) == "E"

    def test_south(self):
        assert _compass_bucket(180) == "S"

    def test_west(self):
        assert _compass_bucket(270) == "W"

    def test_northeast(self):
        assert _compass_bucket(45) == "NE"


# ------------------------------------------------------------------
# SST analyzer
# ------------------------------------------------------------------

class TestAnalyzeSst:
    def test_mean_computed_correctly(self, tmp_path):
        records = [
            {"lat": 10.0, "lon": 0.0, "sst_celsius": 20.0, "flagged": False},
            {"lat": 20.0, "lon": 0.0, "sst_celsius": 30.0, "flagged": False},
        ]
        gz = tmp_path / "sst.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_sst(gz)
        assert result["mean_sst_celsius"] == 25.0

    def test_flagged_count(self, tmp_path):
        records = [
            {"lat": 5.0, "lon": 0.0, "sst_celsius": 25.0, "flagged": False},
            {"lat": 5.0, "lon": 1.0, "sst_celsius": 36.0, "flagged": True},
        ]
        gz = tmp_path / "sst.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_sst(gz)
        assert result["flagged_count"] == 1
        assert result["flagged_pct"] == 50.0

    def test_latitude_band_tropical(self, tmp_path):
        records = [{"lat": 15.0, "lon": 0.0, "sst_celsius": 28.0, "flagged": False}]
        gz = tmp_path / "sst.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_sst(gz)
        assert result["by_latitude_band"]["tropical_0_30"]["count"] == 1

    def test_latitude_band_polar(self, tmp_path):
        records = [{"lat": 75.0, "lon": 0.0, "sst_celsius": 2.0, "flagged": False}]
        gz = tmp_path / "sst.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_sst(gz)
        assert result["by_latitude_band"]["polar_gt60"]["count"] == 1

    def test_missing_file_returns_error(self, tmp_path):
        result = PipelineAnalyzer().analyze_sst(tmp_path / "missing.json.gz")
        assert "error" in result


# ------------------------------------------------------------------
# Tides analyzer
# ------------------------------------------------------------------

class TestAnalyzeTides:
    def test_tidal_range_computed(self, tmp_path):
        records = [
            {"station_id": "001", "name": "A", "lat": 40.0, "lon": -74.0,
             "next_high_time": "08:00", "next_high_m": 2.0,
             "next_low_time": "14:00", "next_low_m": 0.5},
            {"station_id": "002", "name": "B", "lat": 41.0, "lon": -73.0,
             "next_high_time": "09:00", "next_high_m": 3.0,
             "next_low_time": "15:00", "next_low_m": 1.0},
        ]
        gz = tmp_path / "tides.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_tides(gz)
        assert result["mean_tidal_range_m"] == 1.75  # (1.5 + 2.0) / 2

    def test_error_stations_counted(self, tmp_path):
        records = [
            {"station_id": "001", "name": "A", "lat": 40.0, "lon": -74.0,
             "next_high_time": "ERROR", "next_high_m": 0, "next_low_time": "ERROR", "next_low_m": 0},
            {"station_id": "002", "name": "B", "lat": 41.0, "lon": -73.0,
             "next_high_time": "08:00", "next_high_m": 2.0, "next_low_time": "14:00", "next_low_m": 0.5},
        ]
        gz = tmp_path / "tides.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_tides(gz)
        assert result["error_stations"] == 1
        assert result["valid_stations"] == 1


# ------------------------------------------------------------------
# WW3 analyzer
# ------------------------------------------------------------------

class TestAnalyzeWw3:
    def test_wave_categories_assigned(self, tmp_path):
        records = [
            {"lat": 0, "lon": 0, "swh": 0.5, "mwd": 90, "u": 0.5, "v": 0.0},   # calm
            {"lat": 1, "lon": 0, "swh": 2.0, "mwd": 45, "u": 1.4, "v": 1.4},    # moderate
            {"lat": 2, "lon": 0, "swh": 4.5, "mwd": 180, "u": 0.0, "v": 4.5},   # rough
            {"lat": 3, "lon": 0, "swh": 7.0, "mwd": 270, "u": -7.0, "v": 0.0},  # extreme
        ]
        gz = tmp_path / "ww3.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_ww3(gz)
        cats = result["wave_categories"]
        assert cats["calm_lt1m"] == 1
        assert cats["moderate_1_3m"] == 1
        assert cats["rough_3_6m"] == 1
        assert cats["extreme_gt6m"] == 1

    def test_mean_wave_height(self, tmp_path):
        records = [
            {"lat": 0, "lon": 0, "swh": 2.0, "mwd": 90, "u": 0, "v": 0},
            {"lat": 1, "lon": 0, "swh": 4.0, "mwd": 90, "u": 0, "v": 0},
        ]
        gz = tmp_path / "ww3.json.gz"
        write_gz(gz, records)
        result = PipelineAnalyzer().analyze_ww3(gz)
        assert result["mean_swh_m"] == 3.0


# ------------------------------------------------------------------
# Tides synthetic data
# ------------------------------------------------------------------

class TestTidesSyntheticData:
    def test_all_required_fields_present(self):
        from pipelines.tides_pipeline import generate_synthetic_tide_data
        records = generate_synthetic_tide_data(5)
        required = {"station_id", "name", "lat", "lon",
                    "next_high_time", "next_high_m", "next_low_time", "next_low_m"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing keys in {r}"

    def test_high_tide_greater_than_low(self):
        from pipelines.tides_pipeline import generate_synthetic_tide_data
        records = generate_synthetic_tide_data(10)
        for r in records:
            assert r["next_high_m"] > r["next_low_m"], (
                f"High tide {r['next_high_m']} not > low tide {r['next_low_m']}"
            )
