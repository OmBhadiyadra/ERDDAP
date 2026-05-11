"""
Tests for core/compressor.py — compress/decompress round-trips and GeoJSON structure.
CIS 600 Master's Project — University of Massachusetts Dartmouth.
"""

import gzip
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.compressor import compress_json, compress_geojson


SAMPLE_RECORDS = [
    {"lat": 10.0, "lon": -20.0, "sst_celsius": 25.5},
    {"lat": 20.0, "lon": -30.0, "sst_celsius": 22.1},
]

SAMPLE_FEATURES = [
    {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-20.0, 10.0]},
        "properties": {"sst_celsius": 25.5},
    },
    {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-30.0, 20.0]},
        "properties": {"sst_celsius": 22.1},
    },
]


class TestCompressJson:
    def test_returns_true_on_success(self, tmp_path):
        out = tmp_path / "out.json.gz"
        assert compress_json(SAMPLE_RECORDS, str(out)) is True

    def test_file_is_created(self, tmp_path):
        out = tmp_path / "out.json.gz"
        compress_json(SAMPLE_RECORDS, str(out))
        assert out.exists()

    def test_round_trip_data_matches(self, tmp_path):
        out = tmp_path / "out.json.gz"
        compress_json(SAMPLE_RECORDS, str(out))
        with gzip.open(out, "rt", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == SAMPLE_RECORDS

    def test_record_count_preserved(self, tmp_path):
        out = tmp_path / "out.json.gz"
        compress_json(SAMPLE_RECORDS, str(out))
        with gzip.open(out, "rt", encoding="utf-8") as f:
            loaded = json.load(f)
        assert len(loaded) == len(SAMPLE_RECORDS)

    def test_empty_list_handled(self, tmp_path):
        out = tmp_path / "empty.json.gz"
        result = compress_json([], str(out))
        assert result is True
        with gzip.open(out, "rt", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == []

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "out.json.gz"
        assert compress_json(SAMPLE_RECORDS, str(out)) is True
        assert out.exists()


class TestCompressGeoJson:
    def test_returns_true_on_success(self, tmp_path):
        out = tmp_path / "out.geojson.gz"
        assert compress_geojson(SAMPLE_FEATURES, str(out)) is True

    def test_file_is_created(self, tmp_path):
        out = tmp_path / "out.geojson.gz"
        compress_geojson(SAMPLE_FEATURES, str(out))
        assert out.exists()

    def test_output_is_feature_collection(self, tmp_path):
        out = tmp_path / "out.geojson.gz"
        compress_geojson(SAMPLE_FEATURES, str(out))
        with gzip.open(out, "rt", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["type"] == "FeatureCollection"

    def test_feature_count_matches(self, tmp_path):
        out = tmp_path / "out.geojson.gz"
        compress_geojson(SAMPLE_FEATURES, str(out))
        with gzip.open(out, "rt", encoding="utf-8") as f:
            loaded = json.load(f)
        assert len(loaded["features"]) == len(SAMPLE_FEATURES)

    def test_feature_type_field(self, tmp_path):
        out = tmp_path / "out.geojson.gz"
        compress_geojson(SAMPLE_FEATURES, str(out))
        with gzip.open(out, "rt", encoding="utf-8") as f:
            loaded = json.load(f)
        for feature in loaded["features"]:
            assert feature["type"] == "Feature"
