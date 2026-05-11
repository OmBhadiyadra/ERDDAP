
### Features to add — ranked by academic impact

**Tier 1 — Non-negotiable for master's level**

1. **Data analysis module** — after each pipeline run, compute statistics on the output: mean/min/max SST by latitude band, current speed distribution, tidal range comparison across stations. This is what separates "I fetched data" from "I analyzed data."

2. **Data quality report** — after every run, generate a quality report: how many points were valid vs filtered, what percentage was flagged, which stations had missing predictions, what the completeness rate was per pipeline. Save it as `output/reports/YYYY-MM-DD/quality_report.json`.

3. **Unit test suite** — at minimum 20 tests covering parsers, compressor, database, and analysis functions. Zero tests on a master's project is immediately noticeable.

4. **Cross-pipeline correlation** — compare SST and wave height at overlapping coordinates. Do higher SST regions show different wave patterns? This is actual scientific analysis, not just data collection.

**Tier 2 — Strong differentiators**

5. **Interactive data visualization dashboard** — replace the plain Flask table with actual charts: SST heatmap by latitude, current speed histogram, tide height comparison bar chart, pipeline throughput over time. Use Chart.js or Plotly — no external dependencies needed.

6. **Automated scheduler** — instead of running manually, add a Python scheduler using `schedule` or `APScheduler` that runs every 6 hours automatically, mimicking the production cron job from the internship but running locally.

7. **Data export API** — add Flask REST endpoints so someone can actually query your stored data: `GET /api/sst/latest`, `GET /api/tides/stations`, `GET /api/currents/summary`. This makes the project actually usable, not just a batch job.

8. **Pipeline comparison report** — a generated Markdown or HTML report after each run comparing this run to the previous run: did SST change, did current speeds change, how many new tide stations succeeded.

**Tier 3 — Makes it exceptional**

9. **Anomaly detection** — flag SST values that are statistically unusual compared to the previous 7 runs. Simple z-score is enough. This demonstrates you understand the data, not just the pipeline.

10. **GeoJSON map viewer** — a single HTML file that loads your GeoJSON output files and renders them on a Leaflet map. Shows SST as colored dots, current vectors as arrows, tide stations as clickable markers. This is the most visually impressive thing you can show Prof. Xu.

11. **Docker containerization** — a `Dockerfile` and `docker-compose.yml` that lets anyone run your entire project with one command. Shows production deployment awareness.

12. **GitHub Actions CI** — a `.github/workflows/test.yml` that runs your test suite automatically on every push. Shows software engineering maturity.

---

### The prompt to give Claude Code

---

**PROMPT — paste this into Claude Code exactly:**

---

I have a working Python multi-source environmental data pipeline project called CUMULUS. It is a CIS 600 Master's Project at University of Massachusetts Dartmouth that extends an internship WW3 wave data pipeline to also fetch Sea Surface Temperature, Ocean Current Velocity, and Coastal Tide Predictions from NOAA public APIs. The project already works — all 4 pipelines run, data is fetched, compressed to gzip JSON and GeoJSON, saved to a simulated local S3 filesystem under `output/s3/`, and logged to a SQLite database at `output/rds.db`. A basic Flask dashboard exists at `dashboard/app.py`.

I need you to extend this project with the following features to make it genuinely master's-level. Implement all of them completely with real working code.

**Project structure that already exists:**
```
cumulus-pipeline/
├── config.py
├── run_all.py
├── requirements.txt
├── pipelines/
│   ├── ww3_pipeline.py
│   ├── sst_pipeline.py
│   ├── currents_pipeline.py
│   └── tides_pipeline.py
├── core/
│   ├── fetcher.py
│   ├── compressor.py
│   ├── storage.py
│   ├── database.py
│   └── logger.py
├── dashboard/
│   └── app.py
└── output/
    ├── s3/
    │   ├── ww3/YYYY-MM-DD/
    │   ├── sst/YYYY-MM-DD/
    │   ├── currents/YYYY-MM-DD/
    │   └── tides/YYYY-MM-DD/
    └── rds.db
```

Each pipeline output JSON file contains records in these formats:
- WW3: `{lat, lon, swh, mwd, u, v}`
- SST: `{lat, lon, sst_celsius, flagged}`
- Currents: `{lat, lon, u, v, speed_ms, direction_deg}`
- Tides: `{station_id, name, lat, lon, next_high_time, next_high_m, next_low_time, next_low_m}`

The SQLite `pipeline_runs` table has columns: `id, pipeline_name, run_timestamp, status, points_processed, duration_seconds, output_s3_key, file_size_bytes, pipeline_version, error_message`.

---

**FEATURE 1 — Data Analysis Module**

Create `analysis/data_analyzer.py` with a class `PipelineAnalyzer` that has these methods:

`analyze_sst(json_gz_path)` — reads the gzipped SST JSON, computes: total points, global mean/min/max/std_dev SST, mean SST split by latitude band (polar >60°, temperate 30-60°, tropical 0-30°), count and percentage of flagged anomalies (values outside -2 to 35°C), northern vs southern hemisphere mean SST comparison.

`analyze_currents(json_gz_path)` — reads gzipped currents JSON, computes: total points, mean/max/min current speed, location of maximum current speed, percentage of high-energy currents (speed > 0.5 m/s), compass rose distribution of current directions split into 8 directions (N/NE/E/SE/S/SW/W/NW).

`analyze_tides(json_gz_path)` — reads gzipped tides JSON, computes: total stations, stations with valid data vs ERROR, mean/max/min tidal range (high minus low), station with largest tidal range, mean high tide height and mean low tide height across all stations.

`analyze_ww3(json_gz_path)` — reads gzipped WW3 JSON, computes: total points, mean/max/min significant wave height, wave height category distribution (calm <1m, moderate 1-3m, rough 3-6m, extreme >6m), dominant wave direction.

`generate_quality_report(date_str)` — reads all 4 pipeline output files for that date from `output/s3/`, runs all 4 analysis methods, combines into one dict, saves to `output/reports/YYYY-MM-DD/quality_report.json`, and returns the combined dict.

`run_all_analysis(date_str)` — orchestrates calling all analysis methods and printing a formatted summary to console.

---

**FEATURE 2 — Unit Test Suite**

Create `tests/test_compressor.py`, `tests/test_database.py`, `tests/test_analyzers.py`, `tests/test_parsers.py`.

Write at minimum 25 real pytest tests total covering:

Compressor: compress and decompress round-trip, file actually created, GeoJSON output has correct FeatureCollection structure, empty list handled gracefully.

Database: log a run and retrieve it, duplicate prevention check works, get_summary returns correct counts, get_runs with pipeline filter works.

SST parser: valid ERDDAP response parsed correctly, missing table key returns None, NaN values skipped, flagged values correctly identified.

Currents parser: valid u/v parsed and speed computed correctly, None values skipped, direction computed correctly from known u/v values.

Tides: synthetic data has all required fields, high tide always greater than low in synthetic data.

Analyzer: SST mean computed correctly on known data, latitude band assignment correct, tidal range computed correctly, wave height categories assigned correctly.

Use `tmp_path` pytest fixture for file system tests. Use mock ERDDAP response dicts for parser tests — no real network calls in tests.

Add `pytest.ini` at project root and add `pytest` to `requirements.txt`.

---

**FEATURE 3 — REST API endpoints on Flask dashboard**

Add these routes to `dashboard/app.py`:

`GET /api/sst/latest` — reads the most recent SST JSON gz file from `output/s3/sst/`, returns first 100 records as JSON response with total count in header.

`GET /api/currents/latest` — same for currents, returns first 100 records.

`GET /api/tides/stations` — returns all tide station records from latest run including name, lat, lon, next_high_m, next_low_m.

`GET /api/ww3/latest` — returns first 100 WW3 records.

`GET /api/analysis/latest` — reads the most recent quality report from `output/reports/` and returns it as JSON. If no report exists, runs analysis on latest available data and returns result.

`GET /api/runs/history` — returns all pipeline runs from SQLite grouped by pipeline name with run count, success rate, average duration, total points processed per pipeline.

All endpoints return proper JSON with correct Content-Type headers and handle missing files gracefully with a 404 JSON response.

---

**FEATURE 4 — Interactive visualization dashboard**

Completely replace the HTML template in `dashboard/app.py` with a new dashboard that includes:

A summary section at top with 4 metric cards: total pipeline runs, total data points processed across all pipelines, latest SST mean temperature, latest mean current speed.

A pipeline run history line chart using Chart.js showing points processed per run over time for all 4 pipelines on the same chart with different colors. Pull data from SQLite via the `/api/runs/history` endpoint.

An SST latitude analysis bar chart showing mean SST by latitude band (polar, temperate, tropical) from the latest quality report.

A current speed distribution bar chart showing the compass rose distribution (N/NE/E/SE/S/SW/W/NW percentages) from the latest quality report.

A tide stations table showing all 50 stations with name, next high tide time, next high tide height, next low tide time, next low tide height — sortable by clicking column headers.

A data quality panel showing for each pipeline: points processed, completeness rate, anomaly count if applicable, last run timestamp.

All charts must use Chart.js loaded from cdnjs. Dashboard must auto-refresh every 60 seconds. Must look professional — use a clean CSS layout with a dark sidebar navigation and white content area.

---

**FEATURE 5 — Automated local scheduler**

Create `scheduler.py` at project root. Use the `schedule` library (`pip install schedule`). 

Schedule all 4 pipelines to run every 6 hours, starting immediately on first launch. After each pipeline run, automatically trigger `PipelineAnalyzer().generate_quality_report(today)`. Log all scheduled run start/end times to `output/logs/scheduler.log`. Catch all exceptions per pipeline so one failure does not stop others. Print a startup banner showing next scheduled run times for all 4 pipelines. Running `python scheduler.py` should keep running until Ctrl+C.

Add `schedule` to `requirements.txt`.

---

**FEATURE 6 — GeoJSON map viewer**

Create `dashboard/map_viewer.html` — a single standalone HTML file that requires no server, just open in browser.

It loads Leaflet.js from CDN. It has 4 toggle buttons at top: WW3, SST, Currents, Tides. Each button loads the corresponding latest GeoJSON gz file from the local output directory — since gzip files cannot be loaded directly in browser, include a Flask endpoint `GET /api/geojson/sst`, `GET /api/geojson/currents`, `GET /api/geojson/tides`, `GET /api/geojson/ww3` that reads the gzipped file, decompresses it, and returns raw GeoJSON. The map viewer fetches from these endpoints.

SST points render as colored circles where color maps from blue (cold, <5°C) to red (warm, >30°C) using a 5-step color scale. Circle radius 4px.

Current vectors render as small directional arrows using Leaflet rotated markers, colored by speed (light = slow, dark = fast).

Tide stations render as clickable markers that show a popup with station name, next high tide time and height, next low tide time and height.

WW3 points render as circles sized by wave height (swh) — larger circle = bigger waves — colored blue.

Add a legend for each layer. Add a layer control so user can toggle each dataset on/off.

---

**FEATURE 7 — Pipeline comparison report**

Create `analysis/comparison_report.py` with class `PipelineComparisonReport`.

Method `compare_runs(date1_str, date2_str)` — reads quality reports for both dates from `output/reports/`, computes differences: SST mean change, current speed change, tidal range change, wave height change, points processed change per pipeline. Returns a dict with all deltas labeled as "increased", "decreased", or "unchanged" with the numeric delta.

Method `generate_html_report(date_str)` — generates a complete standalone HTML report file saved to `output/reports/YYYY-MM-DD/summary_report.html`. The report includes: run date and time, table of all 4 pipeline results with points, duration, file size, analysis summary for each pipeline with the computed statistics, data quality section showing completeness rates, and if a previous day's report exists, a comparison section showing what changed. The HTML must be self-contained with inline CSS — no external dependencies.

---

**FEATURE 8 — Docker support**

Create `Dockerfile`:
- Base image: `python:3.11-slim`
- Copy project files
- Install requirements
- Expose port 5000
- Default CMD runs `python run_all.py && python dashboard/app.py`

Create `docker-compose.yml` with one service `cumulus` using the Dockerfile, mounting `./output` as a volume so data persists between container runs, exposing port 5000.

Create `.dockerignore` excluding `output/`, `__pycache__/`, `.env`, `*.pyc`.

Add instructions to README for Docker usage: `docker-compose up --build`

---

**FEATURE 9 — GitHub Actions CI**

Create `.github/workflows/test.yml`:

Trigger on push and pull_request to main branch.

Job: runs on `ubuntu-latest`, Python 3.11. Steps: checkout, install dependencies from requirements.txt, run `pytest tests/ -v --tb=short`. 

Also add a second job `lint` that runs `flake8 pipelines/ core/ analysis/ --max-line-length=120 --ignore=E501` to check code style.

Add `flake8` to requirements.txt.

---

**FEATURE 10 — Improve README for GitHub**

Rewrite `README.md` completely with these sections:

Title and badges at top: a green passing badge for GitHub Actions tests, a Python version badge, a license badge.

A clear "What is new beyond EGR 500 internship" section right at the top — a table with two columns "EGR 500 Internship (baseline)" and "CIS 600 Extension (this project)" listing every new feature.

Architecture diagram in ASCII art.

Quick start section: clone, pip install, python run_all.py, python dashboard/app.py.

API documentation section listing all REST endpoints with example curl commands and example JSON responses.

Data pipeline table with source URL, variables, output format, record count for each of the 4 pipelines.

Screenshots section — placeholder text saying where to insert screenshots.

Running tests section: `pytest tests/ -v`.

Running with Docker section.

Project structure tree showing every file.

---

**IMPLEMENTATION RULES:**

1. Every new file must have a module docstring explaining what it does and how it relates to the CIS 600 project extension.

2. Every new function must have a docstring with Args and Returns.

3. All file paths must use `pathlib.Path` — never string concatenation.

4. All new dependencies must be added to `requirements.txt`.

5. Nothing should crash if an output file does not exist yet — handle missing files gracefully with clear log messages.

6. The Flask dashboard must remain runnable with just `python dashboard/app.py` — no separate build step.

7. Tests must be runnable with just `pytest tests/ -v` from project root.

8. Docker must work with just `docker-compose up --build`.

9. The map viewer must work when the Flask dashboard is running — it fetches data from the Flask API endpoints.

10. The comparison report must handle the case where only one day of data exists — skip the comparison section gracefully.

Build every file completely. Do not truncate any file. Start with `requirements.txt`, then `analysis/data_analyzer.py`, then `analysis/comparison_report.py`, then all test files, then updated `dashboard/app.py`, then `dashboard/map_viewer.html`, then `scheduler.py`, then `Dockerfile`, then `docker-compose.yml`, then `.github/workflows/test.yml`, then updated `README.md`.

---
