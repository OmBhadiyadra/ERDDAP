"""
Tests for ERDDAP response parsers in sst_pipeline and currents_pipeline.
Uses mock response dicts — no real network calls.
CIS 600 Master's Project — University of Massachusetts Dartmouth.
"""

import math
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipelines.sst_pipeline import parse_erddap_sst_response
from pipelines.currents_pipeline import parse_erddap_currents_response


# ------------------------------------------------------------------
# SST parser
# ------------------------------------------------------------------

def _sst_response(rows):
    return {
        "table": {
            "columnNames": ["time", "altitude", "latitude", "longitude", "sst"],
            "columnTypes": ["String", "float", "float", "float", "float"],
            "rows": rows,
        }
    }


class TestSstParser:
    def test_valid_response_parsed(self):
        data = _sst_response([
            ["2024-01-01T00:00:00Z", 0.0, 10.0, -20.0, 25.5],
            ["2024-01-01T00:00:00Z", 0.0, 20.0, -30.0, 22.1],
        ])
        records = parse_erddap_sst_response(data)
        assert records is not None
        assert len(records) == 2
        assert records[0]["sst_celsius"] == 25.5
        assert records[0]["lat"] == 10.0
        assert records[0]["lon"] == -20.0

    def test_missing_table_key_returns_none(self):
        assert parse_erddap_sst_response({}) is None

    def test_missing_rows_key_returns_none(self):
        assert parse_erddap_sst_response({"table": {}}) is None

    def test_nan_values_are_skipped(self):
        data = _sst_response([
            ["2024-01-01T00:00:00Z", 0.0, 10.0, -20.0, float("nan")],
            ["2024-01-01T00:00:00Z", 0.0, 20.0, -30.0, 22.1],
        ])
        records = parse_erddap_sst_response(data)
        assert len(records) == 1
        assert records[0]["sst_celsius"] == 22.1

    def test_flagged_below_minus_2_5(self):
        data = _sst_response([
            ["2024-01-01T00:00:00Z", 0.0, 80.0, 0.0, -3.0],
        ])
        records = parse_erddap_sst_response(data)
        assert records[0]["flagged"] is True

    def test_flagged_above_35(self):
        data = _sst_response([
            ["2024-01-01T00:00:00Z", 0.0, 5.0, 90.0, 36.5],
        ])
        records = parse_erddap_sst_response(data)
        assert records[0]["flagged"] is True

    def test_normal_value_not_flagged(self):
        data = _sst_response([
            ["2024-01-01T00:00:00Z", 0.0, 30.0, -60.0, 18.0],
        ])
        records = parse_erddap_sst_response(data)
        assert records[0]["flagged"] is False

    def test_empty_rows_returns_none(self):
        data = _sst_response([])
        assert parse_erddap_sst_response(data) is None

    def test_short_row_skipped(self):
        data = _sst_response([
            ["2024-01-01T00:00:00Z", 0.0, 10.0],  # only 3 columns
            ["2024-01-01T00:00:00Z", 0.0, 20.0, -30.0, 22.1],
        ])
        records = parse_erddap_sst_response(data)
        assert len(records) == 1


# ------------------------------------------------------------------
# Currents parser
# ------------------------------------------------------------------

def _currents_response(rows):
    return {
        "table": {
            "columnNames": ["time", "altitude", "latitude", "longitude", "u", "v"],
            "rows": rows,
        }
    }


class TestCurrentsParser:
    def test_valid_response_parsed(self):
        data = _currents_response([
            ["2024-01-01T00:00:00Z", 0.0, 10.0, -20.0, 0.3, 0.4],
        ])
        records = parse_erddap_currents_response(data)
        assert records is not None
        assert len(records) == 1
        assert records[0]["u"] == 0.3
        assert records[0]["v"] == 0.4

    def test_speed_computed_correctly(self):
        data = _currents_response([
            ["2024-01-01T00:00:00Z", 0.0, 0.0, 0.0, 3.0, 4.0],
        ])
        records = parse_erddap_currents_response(data)
        assert math.isclose(records[0]["speed_ms"], 5.0, rel_tol=1e-3)

    def test_direction_computed_for_east(self):
        # u=1, v=0 → atan2(u,v) = atan2(1,0) = 90°
        data = _currents_response([
            ["2024-01-01T00:00:00Z", 0.0, 0.0, 0.0, 1.0, 0.0],
        ])
        records = parse_erddap_currents_response(data)
        assert math.isclose(records[0]["direction_deg"], 90.0, rel_tol=1e-3)

    def test_none_u_skipped(self):
        data = _currents_response([
            ["2024-01-01T00:00:00Z", 0.0, 0.0, 0.0, None, 0.4],
            ["2024-01-01T00:00:00Z", 0.0, 1.0, 0.0, 0.2, 0.3],
        ])
        records = parse_erddap_currents_response(data)
        assert len(records) == 1

    def test_none_v_skipped(self):
        data = _currents_response([
            ["2024-01-01T00:00:00Z", 0.0, 0.0, 0.0, 0.3, None],
            ["2024-01-01T00:00:00Z", 0.0, 1.0, 0.0, 0.2, 0.3],
        ])
        records = parse_erddap_currents_response(data)
        assert len(records) == 1

    def test_missing_table_returns_none(self):
        assert parse_erddap_currents_response({}) is None

    def test_direction_negative_wraps_to_positive(self):
        # u=0, v=1 → atan2(0,1) = 0° → direction = 0
        data = _currents_response([
            ["2024-01-01T00:00:00Z", 0.0, 0.0, 0.0, 0.0, 1.0],
        ])
        records = parse_erddap_currents_response(data)
        assert records[0]["direction_deg"] >= 0
