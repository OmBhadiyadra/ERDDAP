"""
Flask dashboard for CUMULUS Multi-Source Pipeline.
CIS 600 Master's Project — University of Massachusetts Dartmouth.

Provides:
  - Interactive visualization dashboard with Chart.js charts (GET /)
  - REST data endpoints for SST, currents, tides, WW3, analysis, history
  - GeoJSON passthrough endpoints for the Leaflet map viewer
  - Pipeline trigger endpoint (POST /api/run-all)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gzip
import json
import subprocess
import threading
from datetime import datetime

from flask import Flask, jsonify, render_template_string, send_file

from config import OUTPUT_DIR
from core.database import get_database
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)
app = Flask(__name__)

REPORTS_DIR = OUTPUT_DIR / "reports"


# ======================================================================
# Helpers
# ======================================================================

def _latest_file(pipeline: str, filename: str) -> Path | None:
    """
    Find the most-recent dated folder under output/s3/<pipeline>/ and
    return the path to <filename> inside it.

    Args:
        pipeline: Pipeline name (sst, currents, tides, ww3).
        filename: File name to look for (e.g. sst_global.json.gz).

    Returns:
        Path if found, None otherwise.
    """
    base = OUTPUT_DIR / "s3" / pipeline
    if not base.exists():
        return None
    dated_dirs = sorted(base.iterdir(), reverse=True)
    for d in dated_dirs:
        candidate = d / filename
        if candidate.exists():
            return candidate
    return None


def _load_gz_records(path: Path) -> list:
    """
    Decompress and parse a gzipped JSON file.

    Args:
        path: Path to .json.gz file.

    Returns:
        list: Parsed records, or empty list on failure.
    """
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.log_error(f"Failed to read {path}: {e}")
        return []


def _json_404(message: str):
    return jsonify({"error": message}), 404


# ======================================================================
# Dashboard HTML (Chart.js, dark sidebar, auto-refresh)
# ======================================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CUMULUS — Pipeline Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,sans-serif;display:flex;min-height:100vh;background:#eef2f7;color:#1e293b}

/* ---- Sidebar ---- */
#sidebar{
  width:232px;background:#0d1117;color:#8b949e;
  flex-shrink:0;display:flex;flex-direction:column;
  border-right:1px solid #21262d
}
.sidebar-brand{
  display:flex;align-items:center;gap:10px;
  padding:20px 18px 20px;border-bottom:1px solid #21262d
}
.sidebar-brand .logo{
  width:32px;height:32px;background:#1d4ed8;border-radius:4px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0
}
.sidebar-brand .logo svg{display:block}
.sidebar-brand .wordmark{display:flex;flex-direction:column}
.sidebar-brand .wordmark strong{font-size:13px;font-weight:700;color:#f0f6fc;letter-spacing:.5px}
.sidebar-brand .wordmark span{font-size:10px;color:#484f58;letter-spacing:.3px;margin-top:1px}
#sidebar nav{padding:12px 0;flex:1}
#sidebar nav a{
  display:flex;align-items:center;gap:10px;
  padding:9px 18px;color:#8b949e;text-decoration:none;
  font-size:13px;font-weight:500;transition:background .15s,color .15s;
  border-left:2px solid transparent
}
#sidebar nav a svg{opacity:.6;flex-shrink:0;transition:opacity .15s}
#sidebar nav a:hover{background:#161b22;color:#c9d1d9}
#sidebar nav a:hover svg{opacity:.9}
#sidebar nav a.active{
  background:#161b22;color:#58a6ff;
  border-left-color:#1d4ed8
}
#sidebar nav a.active svg{opacity:1}
.sidebar-footer{
  padding:14px 18px;border-top:1px solid #21262d;
  font-size:10px;color:#484f58;line-height:1.6
}

/* ---- Topbar ---- */
#topbar{
  height:48px;background:#fff;border-bottom:1px solid #e2e8f0;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 24px;flex-shrink:0
}
.topbar-title{font-size:13px;font-weight:600;color:#374151;letter-spacing:.2px}
.topbar-right{display:flex;align-items:center;gap:10px}
.topbar-clock{font-family:'JetBrains Mono',monospace;font-size:11px;color:#94a3b8}
.status-dot{width:7px;height:7px;border-radius:50%;background:#16a34a;box-shadow:0 0 0 2px #dcfce7}

/* ---- Main content ---- */
#content-wrap{flex:1;display:flex;flex-direction:column;overflow:hidden}
#main{flex:1;overflow-y:auto;padding:24px}
.page{display:none}.page.active{display:block}

/* Page header */
.page-header{margin-bottom:22px;display:flex;align-items:center;justify-content:space-between}
.page-header h1{font-size:18px;font-weight:700;color:#0f172a;letter-spacing:-.2px}
.page-header .page-sub{font-size:11px;color:#94a3b8;margin-top:2px;font-family:'JetBrains Mono',monospace}

/* ---- Metric cards ---- */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:22px}
.card{
  background:#fff;padding:18px 20px;
  border:1px solid #e2e8f0;border-left:3px solid #1d4ed8;
  position:relative;overflow:hidden
}
.card::after{
  content:'';position:absolute;top:0;right:0;
  width:48px;height:100%;background:linear-gradient(90deg,transparent,rgba(29,78,216,.04));
  pointer-events:none
}
.card-icon{position:absolute;top:16px;right:16px;opacity:.12}
.card-label{
  font-size:10px;font-weight:600;color:#64748b;
  text-transform:uppercase;letter-spacing:1px;margin-bottom:8px
}
.card-value{
  font-size:26px;font-weight:700;color:#0f172a;
  font-family:'JetBrains Mono',monospace;letter-spacing:-1px
}
.card-unit{font-size:12px;color:#94a3b8;margin-top:4px;font-family:'JetBrains Mono',monospace}

/* ---- Toolbar ---- */
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:22px}
.btn{
  display:inline-flex;align-items:center;gap:6px;
  background:#1d4ed8;color:#fff;border:none;
  padding:8px 16px;cursor:pointer;
  font-size:12px;font-weight:600;letter-spacing:.3px;
  font-family:'Inter',sans-serif;transition:background .15s
}
.btn:hover{background:#1e40af}
.btn:disabled{background:#94a3b8;cursor:not-allowed}
.btn svg{flex-shrink:0}
.btn-ghost{
  background:transparent;color:#475569;
  border:1px solid #cbd5e1;
  padding:8px 12px
}
.btn-ghost:hover{background:#f1f5f9;color:#1e293b}
.toolbar-sep{width:1px;height:24px;background:#e2e8f0;margin:0 4px}
.toolbar-hint{font-size:11px;color:#94a3b8;font-family:'JetBrains Mono',monospace}

/* ---- Notification bar ---- */
#msg{
  padding:10px 16px;margin-bottom:16px;font-size:12px;
  font-weight:500;display:none;border-left:3px solid;
  font-family:'JetBrains Mono',monospace
}
#msg.ok{background:#f0fdf4;color:#15803d;border-color:#16a34a;display:block}
#msg.err{background:#fef2f2;color:#b91c1c;border-color:#dc2626;display:block}

/* ---- Charts ---- */
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:22px}
.chart-box{background:#fff;border:1px solid #e2e8f0;padding:20px}
.chart-box-header{
  display:flex;align-items:center;gap:8px;margin-bottom:16px;
  padding-bottom:12px;border-bottom:1px solid #f1f5f9
}
.chart-box-header svg{color:#64748b;flex-shrink:0}
.chart-box-header h3{
  font-size:12px;font-weight:600;color:#374151;
  text-transform:uppercase;letter-spacing:.6px
}
.chart-box canvas{max-height:240px}

/* ---- Quality panel ---- */
.quality-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-bottom:22px}
.quality-card{background:#fff;border:1px solid #e2e8f0;padding:16px;border-top:2px solid #1d4ed8}
.quality-card h4{
  font-size:10px;font-weight:700;color:#1d4ed8;
  text-transform:uppercase;letter-spacing:1px;margin-bottom:12px
}
.quality-row{
  display:flex;justify-content:space-between;align-items:baseline;
  font-size:12px;color:#64748b;margin-bottom:6px;padding-bottom:6px;
  border-bottom:1px solid #f8fafc
}
.quality-row:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.quality-row span:last-child{
  font-family:'JetBrains Mono',monospace;font-size:12px;
  font-weight:600;color:#1e293b
}

/* ---- Tables ---- */
.table-wrap{background:#fff;border:1px solid #e2e8f0;overflow:hidden;margin-bottom:22px}
.table-toolbar{
  display:flex;align-items:center;justify-content:space-between;
  padding:12px 16px;border-bottom:1px solid #e2e8f0;background:#f8fafc
}
.table-toolbar-title{font-size:12px;font-weight:600;color:#374151;text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse}
thead{background:#f8fafc}
th{
  padding:9px 14px;text-align:left;
  font-size:10px;color:#64748b;font-weight:700;
  text-transform:uppercase;letter-spacing:.7px;
  cursor:pointer;user-select:none;border-bottom:1px solid #e2e8f0;
  white-space:nowrap
}
th:hover{background:#f1f5f9;color:#374151}
th svg{display:inline;vertical-align:middle;margin-left:4px;opacity:.5}
td{
  padding:9px 14px;border-bottom:1px solid #f1f5f9;
  font-size:12px;color:#374151
}
tr:last-child td{border-bottom:none}
tr:hover td{background:#fafbfc}
td.mono{font-family:'JetBrains Mono',monospace;font-size:12px}
.badge{
  display:inline-block;padding:1px 7px;
  font-size:10px;font-weight:700;letter-spacing:.5px;
  text-transform:uppercase;border-radius:2px
}
.badge-success{background:#dcfce7;color:#15803d}
.badge-failed{background:#fee2e2;color:#b91c1c}
.badge-pending{background:#fef9c3;color:#92400e}

/* ---- Spinner animation ---- */
@keyframes spin{to{transform:rotate(360deg)}}
.spin{animation:spin .8s linear infinite;display:inline-block}

@media(max-width:900px){
  .chart-grid{grid-template-columns:1fr}
  #sidebar{width:200px}
}
</style>
</head>
<body>

<!-- ===== SIDEBAR ===== -->
<div id="sidebar">
  <div class="sidebar-brand">
    <div class="logo">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="1" y="11" width="3" height="6" rx="1" fill="#60a5fa"/>
        <rect x="6" y="7"  width="3" height="10" rx="1" fill="#60a5fa"/>
        <rect x="11" y="3" width="3" height="14" rx="1" fill="#60a5fa"/>
        <rect x="16" y="5" width="1" height="2" rx=".5" fill="#93c5fd"/>
        <rect x="16" y="9" width="1" height="2" rx=".5" fill="#93c5fd"/>
        <rect x="16" y="13" width="1" height="2" rx=".5" fill="#93c5fd"/>
      </svg>
    </div>
    <div class="wordmark">
      <strong>CUMULUS</strong>
      <span>PIPELINE MONITOR</span>
    </div>
  </div>

  <nav>
    <a href="#" class="active" onclick="showPage('overview',this)">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        <rect x="1" y="1" width="6" height="6" rx="1"/>
        <rect x="9" y="1" width="6" height="6" rx="1"/>
        <rect x="1" y="9" width="6" height="6" rx="1"/>
        <rect x="9" y="9" width="6" height="6" rx="1"/>
      </svg>
      Overview
    </a>
    <a href="#" onclick="showPage('tides',this)">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <path d="M1 10c1.5-3 3.5-3 5 0s3.5 3 5 0"/>
        <path d="M1 13c1.5-3 3.5-3 5 0s3.5 3 5 0"/>
        <path d="M8 1v5M6 3l2-2 2 2"/>
      </svg>
      Tide Stations
    </a>
    <a href="#" onclick="showPage('history',this)">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="8" cy="8" r="6.5"/>
        <path d="M8 4.5V8l2.5 2"/>
      </svg>
      Run History
    </a>
    <a href="/map" target="_blank">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="1,3 6,1 10,3 15,1 15,13 10,15 6,13 1,15"/>
        <line x1="6" y1="1" x2="6" y2="13"/>
        <line x1="10" y1="3" x2="10" y2="15"/>
      </svg>
      Map Viewer
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="margin-left:auto;opacity:.4">
        <path d="M3 9L9 3M9 3H5M9 3v4"/>
      </svg>
    </a>
  </nav>

  <div class="sidebar-footer">
    CIS 600 · UMass Dartmouth<br>
    NOAA Multi-Source Pipeline
  </div>
</div>

<!-- ===== MAIN AREA ===== -->
<div id="content-wrap">
  <div id="topbar">
    <span class="topbar-title">NOAA Environmental Data Pipeline</span>
    <div class="topbar-right">
      <span class="status-dot"></span>
      <span class="topbar-clock" id="topClock"></span>
    </div>
  </div>

  <div id="main">
    <div id="msg"></div>

    <!-- ===== OVERVIEW PAGE ===== -->
    <div id="page-overview" class="page active">

      <div class="page-header">
        <div>
          <h1>Pipeline Overview</h1>
          <div class="page-sub">REAL-TIME NOAA DATA MONITOR</div>
        </div>
      </div>

      <div class="cards">
        <div class="card">
          <div class="card-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="#1d4ed8"><path d="M3 3h7v7H3zm0 11h7v7H3zM14 3h7v7h-7zm0 11h7v7h-7z"/></svg>
          </div>
          <div class="card-label">Total Pipeline Runs</div>
          <div class="card-value" id="cTotalRuns">—</div>
        </div>
        <div class="card">
          <div class="card-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="#1d4ed8"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"/></svg>
          </div>
          <div class="card-label">Total Data Points</div>
          <div class="card-value" id="cTotalPoints">—</div>
        </div>
        <div class="card" style="border-left-color:#0891b2">
          <div class="card-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="#0891b2"><path d="M12 2a10 10 0 100 20A10 10 0 0012 2zm0 18a8 8 0 110-16 8 8 0 010 16zm-1-5h2v2h-2zm0-8h2v6h-2z"/></svg>
          </div>
          <div class="card-label">Latest SST Mean</div>
          <div class="card-value" id="cSstMean">—</div>
          <div class="card-unit">DEGREES CELSIUS</div>
        </div>
        <div class="card" style="border-left-color:#059669">
          <div class="card-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="#059669"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg>
          </div>
          <div class="card-label">Latest Current Speed</div>
          <div class="card-value" id="cCurrentSpeed">—</div>
          <div class="card-unit">METRES / SECOND</div>
        </div>
      </div>

      <div class="toolbar">
        <button class="btn" id="runBtn" onclick="triggerRun()">
          <svg width="11" height="11" viewBox="0 0 12 12" fill="currentColor"><polygon points="2,1 11,6 2,11"/></svg>
          Execute All Pipelines
        </button>
        <button class="btn btn-ghost" onclick="loadAll()">
          <svg id="refreshIcon" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M13.5 8A5.5 5.5 0 1 1 10 3.07"/>
            <path d="M13.5 1v4h-4"/>
          </svg>
          Refresh
        </button>
        <div class="toolbar-sep"></div>
        <span class="toolbar-hint">AUTO-REFRESH · 60 s</span>
      </div>

      <div class="chart-grid">
        <div class="chart-box">
          <div class="chart-box-header">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#64748b" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="1,12 5,7 9,9 15,3"/>
            </svg>
            <h3>Points Processed Per Run</h3>
          </div>
          <canvas id="chartHistory"></canvas>
        </div>
        <div class="chart-box">
          <div class="chart-box-header">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#64748b" stroke-width="1.5" stroke-linecap="round">
              <rect x="1" y="1" width="4" height="14"/><rect x="6" y="4" width="4" height="11"/><rect x="11" y="7" width="4" height="8"/>
            </svg>
            <h3>SST by Latitude Band (°C)</h3>
          </div>
          <canvas id="chartSstBands"></canvas>
        </div>
        <div class="chart-box">
          <div class="chart-box-header">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#64748b" stroke-width="1.5" stroke-linecap="round">
              <circle cx="8" cy="8" r="6"/><line x1="8" y1="2" x2="8" y2="8"/><line x1="8" y1="8" x2="12" y2="5"/>
            </svg>
            <h3>Current Direction Distribution (%)</h3>
          </div>
          <canvas id="chartCompass"></canvas>
        </div>
        <div class="chart-box">
          <div class="chart-box-header">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#64748b" stroke-width="1.5" stroke-linecap="round">
              <path d="M1 11c2-5 5-5 7 0s5 5 7 0"/>
              <path d="M1 7c2-5 5-5 7 0s5 5 7 0"/>
            </svg>
            <h3>Wave Height Categories</h3>
          </div>
          <canvas id="chartWaves"></canvas>
        </div>
      </div>

      <div class="page-header" style="margin-top:4px">
        <div>
          <h1>Data Quality</h1>
          <div class="page-sub">PER-PIPELINE COMPLETENESS REPORT</div>
        </div>
      </div>
      <div class="quality-grid" id="qualityGrid">
        <div class="quality-card" style="color:#94a3b8;font-size:12px">Loading quality data…</div>
      </div>

    </div>

    <!-- ===== TIDES PAGE ===== -->
    <div id="page-tides" class="page">
      <div class="page-header">
        <div>
          <h1>Tide Stations</h1>
          <div class="page-sub">NOAA CO-OPS · HIGH / LOW PREDICTIONS</div>
        </div>
      </div>
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-toolbar-title">Station Data</span>
          <span class="toolbar-hint">CLICK HEADER TO SORT</span>
        </div>
        <table id="tidesTable">
          <thead>
            <tr>
              <th onclick="sortTable('tidesTable',0)">Station
                <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor"><path d="M4 1l3 3H1zm0 6L1 4h6z"/></svg>
              </th>
              <th onclick="sortTable('tidesTable',1)">Next High Time</th>
              <th onclick="sortTable('tidesTable',2)">High (m)</th>
              <th onclick="sortTable('tidesTable',3)">Next Low Time</th>
              <th onclick="sortTable('tidesTable',4)">Low (m)</th>
            </tr>
          </thead>
          <tbody id="tidesBody">
            <tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:24px">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ===== HISTORY PAGE ===== -->
    <div id="page-history" class="page">
      <div class="page-header">
        <div>
          <h1>Pipeline Run History</h1>
          <div class="page-sub">ALL EXECUTIONS · LAST 40 RUNS</div>
        </div>
      </div>
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-toolbar-title">Execution Log</span>
          <span class="toolbar-hint" id="historyCount"></span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Pipeline</th>
              <th>Timestamp</th>
              <th>Status</th>
              <th>Points</th>
              <th>Duration</th>
              <th>File Size</th>
            </tr>
          </thead>
          <tbody id="historyBody">
            <tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:24px">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</div>

<script>
// ---- Clock ----
function tickClock() {
  document.getElementById('topClock').textContent = new Date().toUTCString().slice(17,25) + ' UTC';
}
tickClock(); setInterval(tickClock, 1000);

// ---- Navigation ----
function showPage(name, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#sidebar nav a').forEach(a => a.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  el.classList.add('active');
  if (name === 'tides') loadTides();
  if (name === 'history') loadHistory();
}

// ---- Message ----
function showMsg(text, type) {
  const el = document.getElementById('msg');
  el.textContent = text;
  el.className = type === 'ok' ? 'ok' : 'err';
  setTimeout(() => { el.className = ''; el.style.display = 'none'; }, 6000);
}

// ---- Formatters ----
function fmtSize(b) {
  if (!b) return '—';
  if (b > 1048576) return (b/1048576).toFixed(2)+' MB';
  if (b > 1024) return (b/1024).toFixed(2)+' KB';
  return b+' B';
}
function fmtDate(s) { return s ? new Date(s).toLocaleString() : '—'; }
function fmtNum(n) { return n != null ? Number(n).toLocaleString() : '—'; }

// ---- Charts ----
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = '#64748b';

const charts = {};
function upsertChart(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}

const CHART_GRID = {
  color: '#f1f5f9',
  borderColor: '#e2e8f0',
  drawBorder: false,
};

// ---- Load overview ----
async function loadAll() {
  await Promise.all([loadSummary(), loadAnalysis(), loadHistoryChart()]);
}

async function loadSummary() {
  const r = await fetch('/api/dashboard').then(r=>r.json()).catch(()=>({}));
  if (!r.summary) return;
  document.getElementById('cTotalRuns').textContent   = fmtNum(r.summary.total_runs);
  document.getElementById('cTotalPoints').textContent = fmtNum(r.summary.total_points_processed);
}

async function loadAnalysis() {
  const r = await fetch('/api/analysis/latest').then(r=>r.json()).catch(()=>({}));
  const p = r.pipelines || {};

  const sstMean = p.sst?.mean_sst_celsius ?? '—';
  const curSpd  = p.currents?.mean_speed_ms ?? '—';
  document.getElementById('cSstMean').textContent      = sstMean !== '—' ? Number(sstMean).toFixed(2) : '—';
  document.getElementById('cCurrentSpeed').textContent = curSpd  !== '—' ? Number(curSpd).toFixed(3)  : '—';

  if (p.sst?.by_latitude_band) {
    const bands = p.sst.by_latitude_band;
    upsertChart('chartSstBands', {
      type: 'bar',
      data: {
        labels: ['Polar >60°', 'Temperate 30-60°', 'Tropical 0-30°'],
        datasets: [{
          label: 'Mean SST (°C)',
          data: [bands.polar_gt60?.mean_sst??0, bands.temperate_30_60?.mean_sst??0, bands.tropical_0_30?.mean_sst??0],
          backgroundColor: ['#93c5fd','#34d399','#fbbf24'],
          borderWidth: 0, borderRadius: 2,
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: false, grid: CHART_GRID },
          x: { grid: { display: false } }
        }
      }
    });
  }

  if (p.currents?.compass_rose_pct) {
    const cr = p.currents.compass_rose_pct;
    upsertChart('chartCompass', {
      type: 'radar',
      data: {
        labels: Object.keys(cr),
        datasets: [{
          label: '% of currents',
          data: Object.values(cr),
          backgroundColor: 'rgba(29,78,216,.12)',
          borderColor: '#1d4ed8',
          pointBackgroundColor: '#1d4ed8',
          pointRadius: 3,
        }]
      },
      options: {
        scales: {
          r: {
            beginAtZero: true,
            grid: { color: '#f1f5f9' },
            angleLines: { color: '#e2e8f0' },
            ticks: { display: false },
          }
        }
      }
    });
  }

  if (p.ww3?.wave_categories) {
    const wc = p.ww3.wave_categories;
    upsertChart('chartWaves', {
      type: 'doughnut',
      data: {
        labels: ['Calm <1 m','Moderate 1-3 m','Rough 3-6 m','Extreme >6 m'],
        datasets: [{
          data: [wc.calm_lt1m, wc.moderate_1_3m, wc.rough_3_6m, wc.extreme_gt6m],
          backgroundColor: ['#34d399','#fbbf24','#fb923c','#f43f5e'],
          borderWidth: 0,
        }]
      },
      options: {
        cutout: '62%',
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14 } } }
      }
    });
  }

  const grid = document.getElementById('qualityGrid');
  const pipelineNames = { sst:'SST', currents:'Currents', tides:'Tides', ww3:'WW3' };
  grid.innerHTML = Object.entries(pipelineNames).map(([key, label]) => {
    const s = p[key] || {};
    const pts  = s.total_points ?? s.total_stations ?? '—';
    const anom = s.flagged_count != null ? s.flagged_count : (s.error_stations ?? '—');
    const anomL = s.flagged_count != null ? 'Flagged Values' : 'Error Stations';
    return `
      <div class="quality-card">
        <h4>${label}</h4>
        <div class="quality-row"><span>Points / Stations</span><span>${fmtNum(pts)}</span></div>
        <div class="quality-row"><span>${anomL}</span><span>${anom}</span></div>
        <div class="quality-row"><span>Report Date</span><span>${r.date || '—'}</span></div>
      </div>`;
  }).join('');
}

async function loadHistoryChart() {
  const r = await fetch('/api/runs/history').then(r=>r.json()).catch(()=>({}));
  if (!r.pipelines) return;

  const colors = { ww3:'#6366f1', sst:'#06b6d4', currents:'#10b981', tides:'#f59e0b' };
  const datasets = Object.entries(r.pipelines).map(([name, info]) => ({
    label: name.toUpperCase(),
    data: info.runs.map(run => ({ x: run.run_timestamp?.slice(0,10), y: run.points_processed })),
    borderColor: colors[name] || '#94a3b8',
    backgroundColor: 'transparent',
    tension: 0.3, borderWidth: 1.5, pointRadius: 2,
  }));

  upsertChart('chartHistory', {
    type: 'line',
    data: { datasets },
    options: {
      scales: {
        x: { type: 'category', grid: { display: false }, ticks: { maxTicksLimit: 6 } },
        y: { title: { display: true, text: 'Points' }, grid: CHART_GRID }
      },
      plugins: {
        legend: { labels: { boxWidth: 10, padding: 16 } }
      }
    }
  });
}

// ---- Tides table ----
async function loadTides() {
  const r = await fetch('/api/tides/stations').then(r=>r.json()).catch(()=>[]);
  const rows = Array.isArray(r) ? r : (r.records || []);
  const tbody = document.getElementById('tidesBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:24px">No tide data. Run the pipeline first.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(s => `
    <tr>
      <td><span style="font-weight:600">${s.name}</span> <span style="color:#94a3b8;font-size:10px;font-family:\'JetBrains Mono\',monospace">${s.station_id}</span></td>
      <td class="mono">${s.next_high_time}</td>
      <td class="mono">${s.next_high_m}</td>
      <td class="mono">${s.next_low_time}</td>
      <td class="mono">${s.next_low_m}</td>
    </tr>`).join('');
}

// ---- Run history table ----
async function loadHistory() {
  const r = await fetch('/api/dashboard').then(r=>r.json()).catch(()=>({}));
  const runs = r.recent_runs || [];
  const tbody = document.getElementById('historyBody');
  const counter = document.getElementById('historyCount');
  if (counter) counter.textContent = runs.length + ' RECORDS';
  if (!runs.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:24px">No runs yet.</td></tr>';
    return;
  }
  tbody.innerHTML = runs.map(run => `
    <tr>
      <td style="font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.3px">${run.pipeline_name}</td>
      <td class="mono" style="color:#94a3b8;font-size:11px">${fmtDate(run.run_timestamp)}</td>
      <td><span class="badge badge-${run.status}">${run.status}</span></td>
      <td class="mono">${fmtNum(run.points_processed)}</td>
      <td class="mono">${run.duration_seconds?.toFixed(2)}s</td>
      <td class="mono">${fmtSize(run.file_size_bytes)}</td>
    </tr>`).join('');
}

// ---- Sort table ----
function sortTable(tableId, col) {
  const table = document.getElementById(tableId);
  const rows  = Array.from(table.querySelectorAll('tbody tr'));
  const dir   = table.dataset.sortDir === 'asc' ? 'desc' : 'asc';
  table.dataset.sortDir = dir;
  rows.sort((a, b) => {
    const va = a.cells[col]?.textContent.trim() || '';
    const vb = b.cells[col]?.textContent.trim() || '';
    const na = parseFloat(va), nb = parseFloat(vb);
    const cmp = !isNaN(na) && !isNaN(nb) ? na - nb : va.localeCompare(vb);
    return dir === 'asc' ? cmp : -cmp;
  });
  table.querySelector('tbody').append(...rows);
}

// ---- Trigger run ----
const IC_PLAY     = '<svg width="11" height="11" viewBox="0 0 12 12" fill="currentColor"><polygon points="2,1 11,6 2,11"/></svg>';
const IC_SPINNER  = '<svg class="spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4"/></svg>';

async function triggerRun() {
  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  btn.innerHTML = IC_SPINNER + ' Running…';
  const r = await fetch('/api/run-all', {method:'POST'}).then(r=>r.json()).catch(()=>({status:'error'}));
  btn.disabled = false;
  btn.innerHTML = IC_PLAY + ' Execute All Pipelines';
  if (r.status === 'started') {
    showMsg('Pipelines dispatched — data will refresh automatically in 8 s', 'ok');
    setTimeout(loadAll, 8000);
  } else {
    showMsg('Dispatch error: ' + (r.message || 'unknown'), 'err');
  }
}

// ---- Boot ----
loadAll();
setInterval(loadAll, 60000);
</script>
</body>
</html>"""


# ======================================================================
# Page routes
# ======================================================================

@app.route("/")
def dashboard():
    """Render the main interactive dashboard."""
    return render_template_string(DASHBOARD_HTML)


@app.route("/map")
def map_viewer():
    """Serve the Leaflet map viewer HTML file."""
    map_path = Path(__file__).parent / "map_viewer.html"
    if map_path.exists():
        return send_file(map_path)
    return "Map viewer not found. Run the pipeline first.", 404


# ======================================================================
# REST — existing dashboard data
# ======================================================================

@app.route("/api/dashboard")
def api_dashboard():
    """Return summary stats and recent run list for the dashboard."""
    try:
        db = get_database()
        summary = db.get_summary()
        recent_runs = db.get_runs(limit=40)

        pipeline_status = {}
        descriptions = {
            "ww3": "NOAA WaveWatch III",
            "sst": "NOAA Sea Surface Temp",
            "currents": "NOAA Ocean Currents",
            "tides": "NOAA Tide Predictions",
        }
        for name in ["ww3", "sst", "currents", "tides"]:
            runs = db.get_runs(pipeline_name=name, limit=1)
            if runs:
                lr = runs[0]
                pipeline_status[name] = {
                    "last_status": lr["status"],
                    "last_run_time": lr["run_timestamp"],
                    "last_file_size": lr["file_size_bytes"],
                    "description": descriptions[name],
                }
            else:
                pipeline_status[name] = {
                    "last_status": None,
                    "last_run_time": None,
                    "last_file_size": 0,
                    "description": descriptions[name],
                }

        return jsonify({"summary": summary, "recent_runs": recent_runs, "pipeline_status": pipeline_status})
    except Exception as e:
        logger.log_error(f"api_dashboard error: {e}")
        return jsonify({"error": str(e)}), 500


# ======================================================================
# REST — data endpoints
# ======================================================================

@app.route("/api/sst/latest")
def api_sst_latest():
    """Return first 100 records from the most recent SST run."""
    path = _latest_file("sst", "sst_global.json.gz")
    if not path:
        return _json_404("No SST data available")
    records = _load_gz_records(path)
    return jsonify({"total": len(records), "records": records[:100]})


@app.route("/api/currents/latest")
def api_currents_latest():
    """Return first 100 records from the most recent currents run."""
    path = _latest_file("currents", "currents_global.json.gz")
    if not path:
        return _json_404("No currents data available")
    records = _load_gz_records(path)
    return jsonify({"total": len(records), "records": records[:100]})


@app.route("/api/tides/stations")
def api_tides_stations():
    """Return all tide station records from the latest run."""
    path = _latest_file("tides", "tides_coops.json.gz")
    if not path:
        return _json_404("No tide data available")
    records = _load_gz_records(path)
    return jsonify({"total": len(records), "records": records})


@app.route("/api/ww3/latest")
def api_ww3_latest():
    """Return first 100 WW3 records from the most recent run."""
    path = _latest_file("ww3", "f006.json.gz")
    if not path:
        return _json_404("No WW3 data available")
    records = _load_gz_records(path)
    return jsonify({"total": len(records), "records": records[:100]})


@app.route("/api/analysis/latest")
def api_analysis_latest():
    """
    Return the most recent quality report.
    If none exists, run analysis on latest available data and return result.
    """
    if REPORTS_DIR.exists():
        dated = sorted(REPORTS_DIR.iterdir(), reverse=True)
        for d in dated:
            rp = d / "quality_report.json"
            if rp.exists():
                with open(rp, "r", encoding="utf-8") as f:
                    return jsonify(json.load(f))

    # No existing report — generate one on the fly
    try:
        from analysis.data_analyzer import PipelineAnalyzer
        today = datetime.utcnow().strftime("%Y-%m-%d")
        report = PipelineAnalyzer().generate_quality_report(today)
        return jsonify(report)
    except Exception as e:
        return _json_404(f"No analysis available: {e}")


@app.route("/api/runs/history")
def api_runs_history():
    """
    Return all pipeline runs grouped by pipeline name with aggregate stats.
    """
    try:
        db = get_database()
        result: dict = {"pipelines": {}}
        for name in ["ww3", "sst", "currents", "tides"]:
            runs = db.get_runs(pipeline_name=name, limit=200)
            successes = [r for r in runs if r["status"] == "success"]
            total_pts = sum(r["points_processed"] for r in successes)
            avg_dur = (
                sum(r["duration_seconds"] for r in runs) / len(runs) if runs else 0
            )
            result["pipelines"][name] = {
                "run_count": len(runs),
                "success_rate": round(len(successes) / len(runs) * 100, 1) if runs else 0,
                "avg_duration_s": round(avg_dur, 2),
                "total_points_processed": total_pts,
                "runs": runs[:50],
            }
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ======================================================================
# REST — GeoJSON passthrough for map viewer
# ======================================================================

def _geojson_response(pipeline: str, filename: str):
    """
    Read a gzipped GeoJSON file and return decompressed raw GeoJSON.

    Args:
        pipeline: Pipeline folder name.
        filename: GeoJSON gz filename.

    Returns:
        Flask response with application/json content type.
    """
    path = _latest_file(pipeline, filename)
    if not path:
        return _json_404(f"No {pipeline} GeoJSON available")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/geojson/sst")
def api_geojson_sst():
    """Return latest SST GeoJSON FeatureCollection."""
    return _geojson_response("sst", "sst_global.geojson.gz")


@app.route("/api/geojson/currents")
def api_geojson_currents():
    """Return latest currents GeoJSON FeatureCollection."""
    return _geojson_response("currents", "currents_global.geojson.gz")


@app.route("/api/geojson/tides")
def api_geojson_tides():
    """Return latest tides GeoJSON FeatureCollection."""
    return _geojson_response("tides", "tides_coops.geojson.gz")


@app.route("/api/geojson/ww3")
def api_geojson_ww3():
    """Return latest WW3 GeoJSON FeatureCollection."""
    return _geojson_response("ww3", "f006.geojson.gz")


# ======================================================================
# REST — pipeline trigger
# ======================================================================

@app.route("/api/run-all", methods=["POST"])
def api_run_all():
    """Trigger all pipelines in a background thread."""
    def _run():
        try:
            result = subprocess.run(
                ["python", "run_all.py"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                timeout=600,
            )
            logger.log_info(f"Pipeline run exited with code {result.returncode}")
        except Exception as e:
            logger.log_error(f"Pipeline trigger error: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "All pipelines started in background"})


# ======================================================================
# Entry point
# ======================================================================

if __name__ == "__main__":
    logger.log_info("Starting CUMULUS Dashboard on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
