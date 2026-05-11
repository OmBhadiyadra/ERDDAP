# CUMULUS — Multi-Source NOAA Environmental Data Pipeline

![Tests](https://github.com/OmBhadiyadra/cumulus-pipeline/actions/workflows/test.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**CIS 600 Master's Project — University of Massachusetts Dartmouth**

---

## What is New Beyond the EGR 500 Internship

| EGR 500 Internship (baseline) | CIS 600 Extension (this project) |
|---|---|
| Single WW3 wave data source | 4 data sources: WW3, SST, Currents, Tides |
| Manual script execution | Automated 6-hour scheduler (`scheduler.py`) |
| No data analysis | Full statistical analysis module (`analysis/`) |
| No quality reporting | Per-run quality report (`quality_report.json`) |
| No tests | 25+ pytest tests across 4 test files |
| Basic print output | Interactive Chart.js dashboard with charts |
| No map visualization | Leaflet GeoJSON map viewer (`map_viewer.html`) |
| No REST API | 10 REST endpoints for data and GeoJSON |
| No pipeline comparison | HTML comparison report between run dates |
| No containerization | Docker + docker-compose support |
| No CI | GitHub Actions CI (pytest + flake8) |

---

## Architecture

```
cumulus-pipeline/
│
├── config.py                   # Central config (paths, env vars, API URLs)
├── run_all.py                  # Orchestrator — runs all 4 pipelines in sequence
├── scheduler.py                # Automated scheduler (every 6 hours)
│
├── pipelines/
│   ├── ww3_pipeline.py         # NOAA GEFS WaveWatch III (GRIB2 → JSON/GeoJSON)
│   ├── sst_pipeline.py         # NOAA ERDDAP Sea Surface Temperature
│   ├── currents_pipeline.py    # NOAA ERDDAP OSCAR Ocean Currents
│   └── tides_pipeline.py       # NOAA CO-OPS Tide Predictions (50 stations)
│
├── core/
│   ├── fetcher.py              # HTTP download + JSON fetch with retry/backoff
│   ├── compressor.py           # gzip JSON and GeoJSON output
│   ├── storage.py              # Local S3 simulation (or real AWS S3)
│   ├── database.py             # SQLite run history (simulated RDS)
│   └── logger.py               # Colored console + file logger
│
├── analysis/
│   ├── data_analyzer.py        # PipelineAnalyzer — statistics per pipeline
│   └── comparison_report.py    # PipelineComparisonReport — HTML diff report
│
├── dashboard/
│   ├── app.py                  # Flask dashboard + all REST API endpoints
│   └── map_viewer.html         # Leaflet GeoJSON map viewer
│
├── tests/
│   ├── test_compressor.py      # Compressor round-trip tests
│   ├── test_database.py        # Database log/retrieve/summary tests
│   ├── test_parsers.py         # ERDDAP SST + currents parser tests
│   └── test_analyzers.py       # Analyzer statistics + synthetic data tests
│
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── pytest.ini
└── requirements.txt
```

---

## Data Sources

| Pipeline | Source | Variables | Output | Records |
|---|---|---|---|---|
| WW3 | NOAA NOMADS GEFS | swh, mwd, u, v | JSON.gz + GeoJSON.gz | ~500 |
| SST | NOAA ERDDAP (OISST) | sst_celsius, flagged | JSON.gz + GeoJSON.gz | ~300 |
| Currents | NOAA ERDDAP (OSCAR) | u, v, speed_ms, direction_deg | JSON.gz + GeoJSON.gz | ~300 |
| Tides | NOAA CO-OPS | high/low time+height per station | JSON.gz + GeoJSON.gz | 50 stations |

All pipelines fall back to synthetic data if NOAA endpoints are unavailable.

---

## Quick Start

```bash
git clone https://github.com/OmBhadiyadra/cumulus-pipeline
cd cumulus-pipeline
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
copy .env.example .env
python run_all.py             # Run all pipelines once
python dashboard\app.py       # Start dashboard at http://localhost:5000
```

---

## Running the Scheduler

```bash
python scheduler.py
```

Runs all pipelines immediately, then every 6 hours. Logs to `output/logs/scheduler.log`. Stop with `Ctrl+C`.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/sst/latest` | First 100 SST records from latest run |
| GET | `/api/currents/latest` | First 100 current records |
| GET | `/api/tides/stations` | All 50 tide station records |
| GET | `/api/ww3/latest` | First 100 WW3 wave records |
| GET | `/api/analysis/latest` | Latest quality report JSON |
| GET | `/api/runs/history` | Run history grouped by pipeline |
| GET | `/api/geojson/sst` | SST GeoJSON FeatureCollection |
| GET | `/api/geojson/currents` | Currents GeoJSON FeatureCollection |
| GET | `/api/geojson/tides` | Tides GeoJSON FeatureCollection |
| GET | `/api/geojson/ww3` | WW3 GeoJSON FeatureCollection |
| POST | `/api/run-all` | Trigger all pipelines in background |

### Example curl commands

```bash
curl http://localhost:5000/api/sst/latest
curl http://localhost:5000/api/analysis/latest
curl -X POST http://localhost:5000/api/run-all
```

### Example JSON — `/api/analysis/latest`

```json
{
  "date": "2026-05-11",
  "pipelines": {
    "sst": {
      "total_points": 300,
      "mean_sst_celsius": 22.4,
      "flagged_count": 3,
      "by_latitude_band": {
        "polar_gt60":      {"count": 30,  "mean_sst": 4.1},
        "temperate_30_60": {"count": 90,  "mean_sst": 15.3},
        "tropical_0_30":   {"count": 180, "mean_sst": 26.8}
      }
    }
  }
}
```

---

## Map Viewer

With the dashboard running, open `http://localhost:5000/map`.

Toggle each data layer with the buttons at the top:
- **SST** — colored circles, blue (cold) → red (warm)
- **Currents** — directional arrows colored by speed
- **Tides** — clickable markers with high/low tide popup
- **WW3** — circles sized by wave height

---

## Screenshots

> Insert screenshot of dashboard Overview page here.

> Insert screenshot of Map Viewer with SST layer enabled here.

> Insert screenshot of Tide Stations table here.

---

## Running with Docker

```bash
docker-compose up --build
```

Dashboard available at `http://localhost:5000`. Pipeline output is persisted to `./output/` via volume mount.

---

## Output Structure

```
output/
├── s3/
│   ├── ww3/YYYY-MM-DD/f006.json.gz
│   ├── sst/YYYY-MM-DD/sst_global.json.gz
│   ├── currents/YYYY-MM-DD/currents_global.json.gz
│   └── tides/YYYY-MM-DD/tides_coops.json.gz
├── reports/
│   └── YYYY-MM-DD/
│       ├── quality_report.json
│       └── summary_report.html
├── logs/
│   ├── scheduler.log
│   └── *.log
└── rds.db
```
