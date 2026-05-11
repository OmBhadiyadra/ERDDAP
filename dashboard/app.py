"""
Flask dashboard for CUMULUS Pipeline monitoring.
Displays pipeline run history from SQLite and allows triggering pipeline runs.
"""

from flask import Flask, render_template_string, jsonify
from datetime import datetime, timedelta
import subprocess
import threading
import json
from pathlib import Path

from core.database import get_database
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)

app = Flask(__name__)

# HTML template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CUMULUS Pipeline Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #667eea;
            margin-bottom: 5px;
            font-size: 28px;
        }
        
        .subtitle {
            color: #666;
            font-size: 14px;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .summary-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }
        
        .summary-card.warning {
            border-left-color: #f59e0b;
        }
        
        .summary-card.success {
            border-left-color: #10b981;
        }
        
        .summary-label {
            font-size: 12px;
            color: #999;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }
        
        .summary-value {
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }
        
        .summary-detail {
            font-size: 12px;
            color: #999;
            margin-top: 8px;
        }
        
        .controls {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        
        button:hover {
            background: #5568d3;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        }
        
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        
        .refresh-info {
            font-size: 12px;
            color: #999;
            margin-left: auto;
        }
        
        .pipeline-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .pipeline-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .pipeline-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }
        
        .pipeline-name {
            font-size: 16px;
            font-weight: bold;
            color: #333;
        }
        
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-success {
            background: #d1fae5;
            color: #065f46;
        }
        
        .status-failed {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .status-pending {
            background: #fef3c7;
            color: #92400e;
        }
        
        .pipeline-info {
            font-size: 13px;
            color: #666;
            line-height: 1.6;
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        
        .info-label {
            font-weight: 500;
            color: #999;
        }
        
        .info-value {
            color: #333;
        }
        
        table {
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        thead {
            background: #f3f4f6;
            border-bottom: 2px solid #e5e7eb;
        }
        
        th {
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            color: #666;
            font-size: 13px;
            text-transform: uppercase;
        }
        
        td {
            padding: 12px 16px;
            border-bottom: 1px solid #e5e7eb;
            font-size: 13px;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        tr:hover {
            background: #f9fafb;
        }
        
        .table-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
            margin-bottom: 30px;
        }
        
        .status-cell {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-cell.success {
            background: #d1fae5;
            color: #065f46;
        }
        
        .status-cell.failed {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .timestamp {
            font-size: 12px;
            color: #999;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: #999;
        }
        
        footer {
            text-align: center;
            color: rgba(255,255,255,0.7);
            font-size: 12px;
            padding: 20px;
        }
        
        .message {
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: none;
        }
        
        .message.show {
            display: block;
        }
        
        .message.success {
            background: #d1fae5;
            color: #065f46;
            border-left: 4px solid #10b981;
        }
        
        .message.error {
            background: #fee2e2;
            color: #991b1b;
            border-left: 4px solid #ef4444;
        }
        
        @media (max-width: 768px) {
            .summary-grid {
                grid-template-columns: 1fr;
            }
            
            .pipeline-grid {
                grid-template-columns: 1fr;
            }
            
            .controls {
                flex-direction: column;
                align-items: stretch;
            }
            
            .refresh-info {
                margin-left: 0;
                text-align: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌊 CUMULUS Pipeline Dashboard</h1>
            <p class="subtitle">CIS 600 Multi-Source NOAA Environmental Data Pipeline</p>
        </header>
        
        <div id="message" class="message"></div>
        
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-label">Total Runs</div>
                <div class="summary-value" id="totalRuns">0</div>
            </div>
            <div class="summary-card success">
                <div class="summary-label">Successful Runs</div>
                <div class="summary-value" id="successfulRuns">0</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Total Points Processed</div>
                <div class="summary-value" id="totalPoints">0</div>
            </div>
            <div class="summary-card warning">
                <div class="summary-label">Pipelines with Data</div>
                <div class="summary-value" id="pipelinesCount">0</div>
                <div class="summary-detail" id="lastRunTime">Never run</div>
            </div>
        </div>
        
        <div class="controls">
            <button id="runAllBtn" onclick="runAllPipelines()">▶ Run All Pipelines</button>
            <button id="refreshBtn" onclick="refreshData()">🔄 Refresh Now</button>
            <div class="refresh-info">Auto-refreshing every 30 seconds</div>
        </div>
        
        <h2 style="color: white; margin-bottom: 20px; font-size: 18px;">Per-Pipeline Status</h2>
        <div class="pipeline-grid" id="pipelineGrid">
            <div class="loading">Loading pipeline data...</div>
        </div>
        
        <h2 style="color: white; margin-bottom: 20px; font-size: 18px;">Recent Pipeline Runs</h2>
        <div class="table-container">
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
                <tbody id="runsTable">
                    <tr>
                        <td colspan="6" style="text-align: center; color: #999;">Loading runs...</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    
    <footer>
        <p>CUMULUS Multi-Source Pipeline • University of Massachusetts Dartmouth • CIS 600</p>
    </footer>
    
    <script>
        function showMessage(text, type) {
            const msg = document.getElementById('message');
            msg.textContent = text;
            msg.className = `message show ${type}`;
            setTimeout(() => {
                msg.className = 'message';
            }, 5000);
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function formatDate(isoString) {
            if (!isoString) return 'N/A';
            const date = new Date(isoString);
            return date.toLocaleString();
        }
        
        async function refreshData() {
            try {
                const response = await fetch('/api/dashboard');
                const data = await response.json();
                
                // Update summary cards
                document.getElementById('totalRuns').textContent = data.summary.total_runs;
                document.getElementById('successfulRuns').textContent = data.summary.successful_runs;
                document.getElementById('totalPoints').textContent = data.summary.total_points_processed.toLocaleString();
                document.getElementById('pipelinesCount').textContent = data.summary.pipelines_with_data;
                
                if (data.summary.last_run_time) {
                    document.getElementById('lastRunTime').textContent = `Last run: ${formatDate(data.summary.last_run_time)}`;
                }
                
                // Update pipeline status cards
                const pipelineGrid = document.getElementById('pipelineGrid');
                pipelineGrid.innerHTML = '';
                
                for (const [name, info] of Object.entries(data.pipeline_status)) {
                    const card = document.createElement('div');
                    card.className = 'pipeline-card';
                    
                    const statusClass = info.last_status === 'success' ? 'status-success' : 
                                       info.last_status === 'failed' ? 'status-failed' : 'status-pending';
                    const statusText = info.last_status || 'PENDING';
                    
                    card.innerHTML = `
                        <div class="pipeline-header">
                            <div class="pipeline-name">${name}</div>
                            <div class="status-badge ${statusClass}">${statusText}</div>
                        </div>
                        <div class="pipeline-info">
                            <div class="info-row">
                                <span class="info-label">Last Run:</span>
                                <span class="info-value">${info.last_run_time ? formatDate(info.last_run_time) : 'Never'}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Last File Size:</span>
                                <span class="info-value">${formatFileSize(info.last_file_size || 0)}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Data Source:</span>
                                <span class="info-value">${info.description}</span>
                            </div>
                        </div>
                    `;
                    pipelineGrid.appendChild(card);
                }
                
                // Update runs table
                const runsTable = document.getElementById('runsTable');
                if (data.recent_runs.length === 0) {
                    runsTable.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #999;">No runs yet</td></tr>';
                } else {
                    runsTable.innerHTML = data.recent_runs.map(run => `
                        <tr>
                            <td><strong>${run.pipeline_name}</strong></td>
                            <td><span class="timestamp">${formatDate(run.run_timestamp)}</span></td>
                            <td><span class="status-cell ${run.status}">${run.status.toUpperCase()}</span></td>
                            <td>${run.points_processed.toLocaleString()}</td>
                            <td>${run.duration_seconds.toFixed(2)}s</td>
                            <td>${formatFileSize(run.file_size_bytes || 0)}</td>
                        </tr>
                    `).join('');
                }
            } catch (error) {
                console.error('Error refreshing data:', error);
                showMessage('Error loading dashboard data', 'error');
            }
        }
        
        async function runAllPipelines() {
            const btn = document.getElementById('runAllBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Running...';
            
            try {
                const response = await fetch('/api/run-all', {method: 'POST'});
                const data = await response.json();
                
                if (data.status === 'started') {
                    showMessage('Pipelines started! Refreshing in 5 seconds...', 'success');
                    setTimeout(() => {
                        refreshData();
                        setTimeout(() => {
                            refreshData();
                        }, 2000);
                    }, 5000);
                } else {
                    showMessage('Error: ' + data.message, 'error');
                }
            } catch (error) {
                console.error('Error running pipelines:', error);
                showMessage('Error running pipelines', 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '▶ Run All Pipelines';
            }
        }
        
        // Initial load and auto-refresh
        refreshData();
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
'''


@app.route('/')
def dashboard():
    """Render main dashboard page."""
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/dashboard')
def api_dashboard():
    """API endpoint returning dashboard data."""
    try:
        db = get_database()
        summary = db.get_summary()
        recent_runs = db.get_runs(limit=20)
        
        # Build pipeline status
        pipeline_status = {}
        for pipeline_name in ['ww3', 'sst', 'currents', 'tides']:
            runs = db.get_runs(pipeline_name=pipeline_name, limit=1)
            
            pipeline_config = {
                'ww3': 'NOAA WaveWatch III',
                'sst': 'NOAA Sea Surface Temp',
                'currents': 'NOAA Ocean Currents',
                'tides': 'NOAA Tide Predictions'
            }
            
            if runs:
                last_run = runs[0]
                pipeline_status[pipeline_name] = {
                    'last_status': last_run['status'],
                    'last_run_time': last_run['run_timestamp'],
                    'last_file_size': last_run['file_size_bytes'],
                    'description': pipeline_config.get(pipeline_name, 'Unknown')
                }
            else:
                pipeline_status[pipeline_name] = {
                    'last_status': None,
                    'last_run_time': None,
                    'last_file_size': 0,
                    'description': pipeline_config.get(pipeline_name, 'Unknown')
                }
        
        return jsonify({
            'summary': summary,
            'recent_runs': recent_runs,
            'pipeline_status': pipeline_status
        })
    
    except Exception as e:
        logger.log_error(f"Error in API dashboard: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-all', methods=['POST'])
def api_run_all():
    """API endpoint to trigger all pipelines."""
    try:
        # Run in background thread
        def run_pipelines():
            try:
                result = subprocess.run(
                    ['python', 'run_all.py'],
                    cwd=Path(__file__).parent.parent,
                    capture_output=True,
                    timeout=600
                )
                logger.log_info(f"Pipeline run completed with exit code {result.returncode}")
            except Exception as e:
                logger.log_error(f"Error running pipelines: {str(e)}")
        
        thread = threading.Thread(target=run_pipelines, daemon=True)
        thread.start()
        
        return jsonify({'status': 'started', 'message': 'Pipelines started'})
    
    except Exception as e:
        logger.log_error(f"Error starting pipeline run: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    logger.log_info("Starting CUMULUS Dashboard on http://localhost:5000")
    app.run(debug=False, host='0.0.0.0', port=5000)
