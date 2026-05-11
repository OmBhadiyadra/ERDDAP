"""
Pipeline comparison report module for CUMULUS Multi-Source Pipeline.
CIS 600 Master's Project — University of Massachusetts Dartmouth.

Compares quality reports between two dates and generates a self-contained
HTML summary report showing analysis statistics, deltas, and pipeline health.
"""

import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUT_DIR
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)

REPORTS_DIR = OUTPUT_DIR / "reports"


def _load_report(date_str: str) -> dict:
    """
    Load a quality report JSON for a given date.

    Args:
        date_str: Date string in YYYY-MM-DD format.

    Returns:
        dict: Parsed report, or empty dict if not found.
    """
    path = REPORTS_DIR / date_str / "quality_report.json"
    if not path.exists():
        logger.log_warning(f"No quality report found for {date_str} at {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.log_error(f"Failed to load report for {date_str}: {e}")
        return {}


def _delta_label(a, b) -> dict:
    """
    Return a dict with numeric delta and direction label.

    Args:
        a: New value.
        b: Old value.

    Returns:
        dict: {"delta": float, "direction": "increased"|"decreased"|"unchanged"}
    """
    try:
        diff = round(float(a) - float(b), 4)
        direction = "increased" if diff > 0 else ("decreased" if diff < 0 else "unchanged")
        return {"delta": diff, "direction": direction}
    except (TypeError, ValueError):
        return {"delta": None, "direction": "unknown"}


class PipelineComparisonReport:
    """
    Generates comparison dicts and HTML reports between two pipeline run dates.

    Uses quality_report.json files produced by PipelineAnalyzer as input.
    HTML output is self-contained with inline CSS and no external dependencies.
    """

    def compare_runs(self, date1_str: str, date2_str: str) -> dict:
        """
        Compare quality reports for two dates and return labelled deltas.

        Args:
            date1_str: Newer date (YYYY-MM-DD).
            date2_str: Older baseline date (YYYY-MM-DD).

        Returns:
            dict: Per-pipeline deltas with direction labels, or empty dict
                  if either report is missing.
        """
        new_report = _load_report(date1_str)
        old_report = _load_report(date2_str)

        if not new_report or not old_report:
            return {}

        new_p = new_report.get("pipelines", {})
        old_p = old_report.get("pipelines", {})

        comparison = {
            "date_new": date1_str,
            "date_old": date2_str,
            "pipelines": {},
        }

        metric_map = {
            "sst": ("mean_sst_celsius", "SST mean temperature"),
            "currents": ("mean_speed_ms", "Mean current speed"),
            "tides": ("mean_tidal_range_m", "Mean tidal range"),
            "ww3": ("mean_swh_m", "Mean wave height"),
        }

        for pipeline, (metric, label) in metric_map.items():
            new_val = new_p.get(pipeline, {}).get(metric)
            old_val = old_p.get(pipeline, {}).get(metric)
            new_pts = new_p.get(pipeline, {}).get("total_points") or new_p.get(pipeline, {}).get("total_stations")
            old_pts = old_p.get(pipeline, {}).get("total_points") or old_p.get(pipeline, {}).get("total_stations")

            comparison["pipelines"][pipeline] = {
                "metric": label,
                "new_value": new_val,
                "old_value": old_val,
                "change": _delta_label(new_val, old_val),
                "points_change": _delta_label(new_pts, old_pts),
            }

        return comparison

    def generate_html_report(self, date_str: str) -> Path:
        """
        Generate a standalone HTML report for a given date.

        Includes analysis statistics, pipeline health, and a comparison
        section if a previous day's report exists.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            Path: Path to the saved HTML file, or None on failure.
        """
        report = _load_report(date_str)
        if not report:
            logger.log_warning(f"No report to render for {date_str}")
            return None

        pipelines = report.get("pipelines", {})

        # Try to find previous day's report
        from datetime import timedelta
        prev_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        comparison = self.compare_runs(date_str, prev_date)

        html = self._build_html(date_str, pipelines, comparison, report.get("generated_at", ""))

        out_dir = REPORTS_DIR / date_str
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "summary_report.html"

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.log_info(f"HTML report saved to {out_path}")
        return out_path

    # ------------------------------------------------------------------
    # HTML builder (inline CSS, no external deps)
    # ------------------------------------------------------------------

    def _build_html(self, date_str: str, pipelines: dict, comparison: dict, generated_at: str) -> str:
        """
        Build a complete self-contained HTML report string.

        Args:
            date_str: Report date.
            pipelines: Dict of per-pipeline analysis results.
            comparison: Comparison dict from compare_runs (may be empty).
            generated_at: ISO timestamp when the report was generated.

        Returns:
            str: Full HTML document.
        """
        pipeline_labels = {
            "sst": "Sea Surface Temperature",
            "currents": "Ocean Currents",
            "tides": "Coastal Tides",
            "ww3": "WaveWatch III",
        }

        def badge(status: str) -> str:
            color = "#10b981" if status == "ok" else "#ef4444"
            return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{status.upper()}</span>'

        def stat_row(label: str, value) -> str:
            return f'<tr><td style="color:#666;padding:4px 8px">{label}</td><td style="font-weight:600;padding:4px 8px">{value}</td></tr>'

        def delta_row(info: dict) -> str:
            if not info or info.get("change", {}).get("delta") is None:
                return ""
            d = info["change"]
            color = "#10b981" if d["direction"] == "increased" else ("#ef4444" if d["direction"] == "decreased" else "#666")
            arrow = "▲" if d["direction"] == "increased" else ("▼" if d["direction"] == "decreased" else "→")
            return (
                f'<tr><td style="color:#666;padding:4px 8px">{info["metric"]} vs {info["date_old"]}</td>'
                f'<td style="color:{color};font-weight:600;padding:4px 8px">{arrow} {abs(d["delta"])}</td></tr>'
            )

        # Build per-pipeline cards
        cards_html = ""
        for name, label in pipeline_labels.items():
            stats = pipelines.get(name, {})
            has_error = "error" in stats
            status_badge = badge("error" if has_error else "ok")

            rows = ""
            if not has_error:
                for k, v in stats.items():
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            rows += stat_row(f"{k} / {k2}", v2)
                    else:
                        rows += stat_row(k, v)

            comp_row = ""
            if comparison and name in comparison.get("pipelines", {}):
                comp_row = delta_row(comparison["pipelines"][name])

            cards_html += f"""
            <div style="background:#fff;border-radius:8px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.08);margin-bottom:20px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                    <h3 style="margin:0;color:#1e293b">{label}</h3>
                    {status_badge}
                </div>
                <table style="width:100%;border-collapse:collapse">
                    {rows}
                    {comp_row}
                </table>
            </div>
            """

        comparison_section = ""
        if comparison:
            comparison_section = f"""
            <h2 style="color:#1e293b;margin:30px 0 16px">Comparison vs {comparison.get('date_old','previous day')}</h2>
            <div style="background:#fff;border-radius:8px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
                <table style="width:100%;border-collapse:collapse">
                    {''.join(delta_row(v) for v in comparison.get('pipelines', {}).values())}
                </table>
            </div>
            """
        else:
            comparison_section = '<p style="color:#999;font-style:italic">No previous day report found — comparison not available.</p>'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CUMULUS Report — {date_str}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',sans-serif; background:#f1f5f9; color:#1e293b; padding:30px; }}
  h1 {{ font-size:24px; margin-bottom:4px; }}
  .sub {{ color:#64748b; font-size:13px; margin-bottom:30px; }}
  h2 {{ font-size:18px; }}
</style>
</head>
<body>
  <h1>CUMULUS Pipeline Report</h1>
  <p class="sub">Date: {date_str} &nbsp;|&nbsp; Generated: {generated_at} &nbsp;|&nbsp; University of Massachusetts Dartmouth — CIS 600</p>

  <h2 style="color:#1e293b;margin-bottom:16px">Pipeline Analysis Results</h2>
  {cards_html}

  {comparison_section}

  <p style="margin-top:30px;color:#94a3b8;font-size:12px">Generated by CUMULUS PipelineComparisonReport</p>
</body>
</html>"""


if __name__ == "__main__":
    today = datetime.utcnow().strftime("%Y-%m-%d")
    report = PipelineComparisonReport()
    path = report.generate_html_report(today)
    if path:
        print(f"Report written to {path}")
