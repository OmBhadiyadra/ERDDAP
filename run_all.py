#!/usr/bin/env python3
"""
Orchestrator script that runs all four CUMULUS pipelines in sequence.
Collects results and prints a comprehensive summary.
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pipelines.ww3_pipeline import run_ww3_pipeline
from pipelines.sst_pipeline import run_sst_pipeline
from pipelines.currents_pipeline import run_currents_pipeline
from pipelines.tides_pipeline import run_tides_pipeline
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)


def print_header():
    """Print startup header."""
    print("\n" + "=" * 80)
    print(" " * 15 + "CUMULUS Multi-Source Pipeline Orchestrator")
    print(" " * 10 + "CIS 600 Master's Project Extension")
    print(" " * 5 + "University of Massachusetts Dartmouth")
    print("=" * 80)
    print(f"Start time: {datetime.utcnow().isoformat()}")
    print("=" * 80 + "\n")


def print_summary(results):
    """Print execution summary in a formatted table."""
    print("\n" + "=" * 80)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 80)
    
    # Table header
    print(f"{'Pipeline':<15} {'Status':<10} {'Points':<12} {'Duration':<12} {'File Size':<15}")
    print("-" * 80)
    
    all_success = True
    total_points = 0
    total_duration = 0
    
    for pipeline_name, result in results.items():
        status = result['status'].upper()
        points = result['points_processed']
        duration = result['duration']
        file_size = result['file_size']
        
        # Format file size
        if file_size > 1024 * 1024:
            file_size_str = f"{file_size / (1024 * 1024):.2f} MB"
        elif file_size > 1024:
            file_size_str = f"{file_size / 1024:.2f} KB"
        else:
            file_size_str = f"{file_size} B"
        
        # Track totals
        if status == 'SUCCESS':
            total_points += points
        else:
            all_success = False
        
        total_duration += duration
        
        # Print row
        points_str = f"{points:,}" if status == 'SUCCESS' else "0"
        print(f"{pipeline_name:<15} {status:<10} {points_str:<12} {duration:<12.2f}s {file_size_str:<15}")
    
    print("-" * 80)
    print(f"{'TOTAL':<15} {'':<10} {total_points:,.<12} {total_duration:<12.2f}s")
    print("=" * 80)
    
    return all_success, total_points, total_duration


def run_all_pipelines():
    """Run all pipelines in sequence."""
    print_header()
    
    start_time = time.time()
    results = {}
    
    # Run each pipeline
    pipelines = [
        ('ww3', 'WW3 Wave Data', run_ww3_pipeline),
        ('sst', 'Sea Surface Temperature', run_sst_pipeline),
        ('currents', 'Ocean Currents', run_currents_pipeline),
        ('tides', 'Tide Predictions', run_tides_pipeline),
    ]
    
    for pipeline_id, pipeline_name, pipeline_func in pipelines:
        logger.log_info(f"\n>>> Starting {pipeline_name} pipeline...")
        try:
            result = pipeline_func()
            results[pipeline_name] = {
                'status': result['status'],
                'points_processed': result.get('points_processed', 0),
                'duration': result.get('duration', 0),
                'file_size': result.get('file_size', 0),
                'output_key': result.get('output_s3_key', ''),
                'error': result.get('error', '')
            }
        except Exception as e:
            logger.log_error(f"Exception running {pipeline_name}: {str(e)}")
            results[pipeline_name] = {
                'status': 'failed',
                'points_processed': 0,
                'duration': 0,
                'file_size': 0,
                'output_key': '',
                'error': str(e)
            }
    
    # Print summary
    all_success, total_points, total_duration = print_summary(results)
    
    # Print footer
    total_runtime = time.time() - start_time
    print(f"\nTotal execution time: {total_runtime:.2f} seconds")
    print(f"End time: {datetime.utcnow().isoformat()}")
    
    if all_success:
        print("\n✓ All pipelines completed successfully!")
        exit_code = 0
    else:
        print("\n✗ Some pipelines failed. Check logs for details.")
        exit_code = 1
    
    print("=" * 80 + "\n")
    
    return exit_code


if __name__ == "__main__":
    exit_code = run_all_pipelines()
    sys.exit(exit_code)
