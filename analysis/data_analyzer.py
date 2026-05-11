"""
Data analysis module for CUMULUS Multi-Source Pipeline.
CIS 600 Master's Project — University of Massachusetts Dartmouth.

Reads compressed pipeline output files and computes descriptive statistics,
quality metrics, and cross-pipeline summaries. Called automatically after
each pipeline run and by the Flask API's /api/analysis/latest endpoint.
"""

import gzip
import json
import math
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUT_DIR
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)

REPORTS_DIR = OUTPUT_DIR / "reports"


def _load_gz_json(path: Path) -> list:
    """
    Load a gzipped JSON file and return parsed contents.

    Args:
        path: Path to the .json.gz file.

    Returns:
        list: Parsed records, or empty list if file missing or corrupt.
    """
    if not path.exists():
        logger.log_warning(f"File not found: {path}")
        return []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.log_error(f"Failed to read {path}: {e}")
        return []


def _safe_mean(values: list) -> float:
    """Return mean of a non-empty list, or 0.0."""
    return round(sum(values) / len(values), 4) if values else 0.0


def _compass_bucket(direction_deg: float) -> str:
    """Map a bearing in degrees to one of 8 compass labels."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((direction_deg + 22.5) / 45) % 8
    return dirs[idx]


class PipelineAnalyzer:
    """
    Computes statistics and quality metrics from pipeline output files.

    Each analyze_* method accepts the path to a gzipped JSON file produced
    by the corresponding pipeline and returns a dict of computed metrics.
    generate_quality_report orchestrates all four and saves the combined
    result to output/reports/YYYY-MM-DD/quality_report.json.
    """

    # ------------------------------------------------------------------
    # SST
    # ------------------------------------------------------------------

    def analyze_sst(self, json_gz_path: Path) -> dict:
        """
        Analyse Sea Surface Temperature output.

        Args:
            json_gz_path: Path to sst_global.json.gz.

        Returns:
            dict: SST statistics including latitude-band breakdown and
                  anomaly counts.
        """
        records = _load_gz_json(Path(json_gz_path))
        if not records:
            return {"error": "no data", "total_points": 0}

        temps = [r["sst_celsius"] for r in records]
        flagged = [r for r in records if r.get("flagged", False)]

        # Latitude band breakdown
        polar = [r["sst_celsius"] for r in records if abs(r["lat"]) > 60]
        temperate = [r["sst_celsius"] for r in records if 30 < abs(r["lat"]) <= 60]
        tropical = [r["sst_celsius"] for r in records if abs(r["lat"]) <= 30]

        north = [r["sst_celsius"] for r in records if r["lat"] >= 0]
        south = [r["sst_celsius"] for r in records if r["lat"] < 0]

        mean_sst = _safe_mean(temps)
        variance = _safe_mean([(t - mean_sst) ** 2 for t in temps])

        return {
            "total_points": len(records),
            "mean_sst_celsius": mean_sst,
            "min_sst_celsius": round(min(temps), 4),
            "max_sst_celsius": round(max(temps), 4),
            "std_dev_celsius": round(math.sqrt(variance), 4),
            "flagged_count": len(flagged),
            "flagged_pct": round(len(flagged) / len(records) * 100, 2),
            "by_latitude_band": {
                "polar_gt60": {"count": len(polar), "mean_sst": _safe_mean(polar)},
                "temperate_30_60": {"count": len(temperate), "mean_sst": _safe_mean(temperate)},
                "tropical_0_30": {"count": len(tropical), "mean_sst": _safe_mean(tropical)},
            },
            "northern_hemisphere_mean": _safe_mean(north),
            "southern_hemisphere_mean": _safe_mean(south),
        }

    # ------------------------------------------------------------------
    # Currents
    # ------------------------------------------------------------------

    def analyze_currents(self, json_gz_path: Path) -> dict:
        """
        Analyse ocean current velocity output.

        Args:
            json_gz_path: Path to currents_global.json.gz.

        Returns:
            dict: Current speed statistics, high-energy fraction, and
                  compass-rose direction distribution.
        """
        records = _load_gz_json(Path(json_gz_path))
        if not records:
            return {"error": "no data", "total_points": 0}

        speeds = [r["speed_ms"] for r in records]
        high_energy = [s for s in speeds if s > 0.5]

        max_speed = max(speeds)
        max_record = next(r for r in records if r["speed_ms"] == max_speed)

        # Compass rose distribution
        buckets: dict = {d: 0 for d in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]}
        for r in records:
            buckets[_compass_bucket(r["direction_deg"])] += 1
        total = len(records)
        compass_pct = {k: round(v / total * 100, 2) for k, v in buckets.items()}

        return {
            "total_points": len(records),
            "mean_speed_ms": _safe_mean(speeds),
            "max_speed_ms": round(max_speed, 4),
            "min_speed_ms": round(min(speeds), 4),
            "max_speed_location": {"lat": max_record["lat"], "lon": max_record["lon"]},
            "high_energy_count": len(high_energy),
            "high_energy_pct": round(len(high_energy) / total * 100, 2),
            "compass_rose_pct": compass_pct,
        }

    # ------------------------------------------------------------------
    # Tides
    # ------------------------------------------------------------------

    def analyze_tides(self, json_gz_path: Path) -> dict:
        """
        Analyse coastal tide prediction output.

        Args:
            json_gz_path: Path to tides_coops.json.gz.

        Returns:
            dict: Tidal range statistics and station health counts.
        """
        records = _load_gz_json(Path(json_gz_path))
        if not records:
            return {"error": "no data", "total_stations": 0}

        valid = [r for r in records if r.get("next_high_time") not in ("N/A", "ERROR")]
        ranges = [r["next_high_m"] - r["next_low_m"] for r in valid]
        highs = [r["next_high_m"] for r in valid]
        lows = [r["next_low_m"] for r in valid]

        max_range = max(ranges) if ranges else 0
        max_station = next(
            (r for r in valid if (r["next_high_m"] - r["next_low_m"]) == max_range),
            None,
        )

        return {
            "total_stations": len(records),
            "valid_stations": len(valid),
            "error_stations": len(records) - len(valid),
            "mean_tidal_range_m": _safe_mean(ranges),
            "max_tidal_range_m": round(max_range, 4),
            "min_tidal_range_m": round(min(ranges), 4) if ranges else 0,
            "max_range_station": max_station["name"] if max_station else "N/A",
            "mean_high_tide_m": _safe_mean(highs),
            "mean_low_tide_m": _safe_mean(lows),
        }

    # ------------------------------------------------------------------
    # WW3
    # ------------------------------------------------------------------

    def analyze_ww3(self, json_gz_path: Path) -> dict:
        """
        Analyse WaveWatch III wave forecast output.

        Args:
            json_gz_path: Path to f006.json.gz.

        Returns:
            dict: Wave height statistics, category distribution, and
                  dominant direction.
        """
        records = _load_gz_json(Path(json_gz_path))
        if not records:
            return {"error": "no data", "total_points": 0}

        heights = [r["swh"] for r in records]
        directions = [r["mwd"] for r in records]

        categories = {
            "calm_lt1m": sum(1 for h in heights if h < 1),
            "moderate_1_3m": sum(1 for h in heights if 1 <= h < 3),
            "rough_3_6m": sum(1 for h in heights if 3 <= h < 6),
            "extreme_gt6m": sum(1 for h in heights if h >= 6),
        }

        # Dominant direction — bucket into 8 compass directions, pick largest
        dir_buckets: dict = {d: 0 for d in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]}
        for d in directions:
            dir_buckets[_compass_bucket(d)] += 1
        dominant_dir = max(dir_buckets, key=lambda k: dir_buckets[k])

        return {
            "total_points": len(records),
            "mean_swh_m": _safe_mean(heights),
            "max_swh_m": round(max(heights), 4),
            "min_swh_m": round(min(heights), 4),
            "wave_categories": categories,
            "dominant_direction": dominant_dir,
        }

    # ------------------------------------------------------------------
    # Quality report
    # ------------------------------------------------------------------

    def generate_quality_report(self, date_str: str) -> dict:
        """
        Run all four analyses for a given date and save combined JSON report.

        Reads from output/s3/<pipeline>/YYYY-MM-DD/ for each pipeline.
        Saves result to output/reports/YYYY-MM-DD/quality_report.json.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            dict: Combined quality report across all four pipelines.
        """
        s3_base = OUTPUT_DIR / "s3"
        report: dict = {
            "generated_at": datetime.utcnow().isoformat(),
            "date": date_str,
            "pipelines": {},
        }

        pipeline_files = {
            "sst": s3_base / "sst" / date_str / "sst_global.json.gz",
            "currents": s3_base / "currents" / date_str / "currents_global.json.gz",
            "tides": s3_base / "tides" / date_str / "tides_coops.json.gz",
            "ww3": s3_base / "ww3" / date_str / "f006.json.gz",
        }

        analyzers = {
            "sst": self.analyze_sst,
            "currents": self.analyze_currents,
            "tides": self.analyze_tides,
            "ww3": self.analyze_ww3,
        }

        for name, path in pipeline_files.items():
            logger.log_info(f"Analysing {name} from {path}")
            report["pipelines"][name] = analyzers[name](path)

        out_dir = REPORTS_DIR / date_str
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "quality_report.json"

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.log_info(f"Quality report saved to {out_path}")
        return report

    # ------------------------------------------------------------------
    # Console summary
    # ------------------------------------------------------------------

    def run_all_analysis(self, date_str: str) -> None:
        """
        Run all analyses and print a formatted summary to console.

        Args:
            date_str: Date string in YYYY-MM-DD format.
        """
        report = self.generate_quality_report(date_str)
        print("\n" + "=" * 70)
        print(f"  CUMULUS Data Quality Report — {date_str}")
        print("=" * 70)

        for pipeline, stats in report["pipelines"].items():
            print(f"\n[{pipeline.upper()}]")
            if "error" in stats:
                print(f"  No data available.")
                continue
            for key, val in stats.items():
                if isinstance(val, dict):
                    print(f"  {key}:")
                    for k2, v2 in val.items():
                        print(f"    {k2}: {v2}")
                else:
                    print(f"  {key}: {val}")

        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    today = datetime.utcnow().strftime("%Y-%m-%d")
    PipelineAnalyzer().run_all_analysis(today)
