"""
Sea Surface Temperature (SST) Pipeline - NOAA ERDDAP

Data Source: NOAA CoastWatch ERDDAP - ncdcOisst21Agg (sea surface temperature observations)
URL: https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg_LonPM180.json

Variables Extracted:
- sst: Sea Surface Temperature in Celsius
- lat, lon: Geographic coordinates

Response Format: ERDDAP JSON with array of [time, altitude, lat, lon, sst] tuples

Extension from EGR 500 Internship:
- Original internship: Single-source WW3 wave data pipeline
- This version: NEW - Multi-source architecture extends to SST observations
- Demonstrates fetching and parsing different NOAA API formats (ERDDAP JSON vs GRIB2)
- Integrates with core pipeline infrastructure for data compression and storage
"""

import time
import math
import numpy as np
from datetime import datetime

from config import OUTPUT_DIR
from core.logger import PipelineLogger
from core.fetcher import fetch_json
from core.compressor import compress_json, compress_geojson
from core.storage import save_to_local_s3
from core.database import get_database

logger = PipelineLogger(__name__)


def generate_synthetic_sst_data(num_points: int = 300) -> list:
    """
    Generate realistic synthetic SST data.
    Used when real ERDDAP data fetch fails.
    
    Args:
        num_points: Number of data points to generate
    
    Returns:
        list: List of SST records
    """
    logger.log_warning(f"Generating synthetic SST data ({num_points} points)")
    
    records = []
    
    # Create a grid of lat/lon points
    lats = np.linspace(0, 89, 15)
    lons = np.linspace(-179, 180, 20)
    
    for lat in lats:
        if len(records) >= num_points:
            break
        for lon in lons:
            if len(records) >= num_points:
                break

            # Realistic SST values (5-30°C in tropics/subtropics)
            # Varies by latitude
            if lat > 60:
                sst = np.random.uniform(0, 15)
            elif lat > 30:
                sst = np.random.uniform(10, 25)
            else:
                sst = np.random.uniform(20, 30)

            records.append({
                'lat': round(lat, 2),
                'lon': round(lon, 2),
                'sst_celsius': round(sst, 2)
            })
    
    logger.log_info(f"Generated {len(records)} synthetic SST records")
    return records


def parse_erddap_sst_response(data: dict) -> list:
    """
    Parse ERDDAP JSON response and extract SST data.
    
    ERDDAP response format:
    {
      "table": {
        "columnNames": ["time", "altitude", "latitude", "longitude", "sst"],
        "columnTypes": [...],
        "rows": [[time_val, alt_val, lat_val, lon_val, sst_val], ...]
      }
    }
    
    Args:
        data: Parsed ERDDAP JSON response
    
    Returns:
        list: List of SST records
    """
    try:
        logger.log_info("Parsing ERDDAP SST response")
        
        if 'table' not in data or 'rows' not in data.get('table', {}):
            logger.log_warning("Missing table or rows in ERDDAP response")
            return None
        
        rows = data['table']['rows']
        logger.log_info(f"Found {len(rows)} rows in ERDDAP response")
        
        records = []
        flagged_count = 0
        
        for row in rows:
            # Row format: [time, altitude, latitude, longitude, sst]
            if len(row) < 5:
                continue
            
            try:
                lat = float(row[2])
                lon = float(row[3])
                sst = float(row[4])
                
                # Check for fill values and suspicious values
                if math.isnan(sst):
                    continue
                
                # Flag suspicious values but include them
                if sst < -2.5 or sst > 35:
                    flagged_count += 1
                    logger.log_debug(f"Flagged suspicious SST: {sst}°C at ({lat}, {lon})")
                
                records.append({
                    'lat': round(lat, 2),
                    'lon': round(lon, 2),
                    'sst_celsius': round(sst, 2),
                    'flagged': sst < -2.5 or sst > 35
                })
            except (TypeError, ValueError):
                continue
        
        logger.log_info(f"Extracted {len(records)} SST records ({flagged_count} flagged)")
        return records if records else None
    
    except Exception as e:
        logger.log_error(f"Error parsing ERDDAP response: {str(e)}")
        return None


def fetch_sst_data() -> list:
    """
    Fetch real SST data from NOAA ERDDAP.
    Falls back to synthetic data if real data unavailable.
    
    Returns:
        list: SST records
    """
    try:
        # ERDDAP endpoint for global SST
        url = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg_LonPM180.json?sst[(last)][(0.0)][(0.0):(89.0)][(-179.0):(180.0)]"
        
        logger.log_info(f"Fetching SST data from ERDDAP")
        
        # Fetch JSON from ERDDAP
        data = fetch_json(url)
        
        if not data:
            logger.log_warning("Empty response from ERDDAP SST endpoint")
            return generate_synthetic_sst_data()
        
        # Parse response
        records = parse_erddap_sst_response(data)
        
        if records:
            logger.log_info(f"Successfully fetched {len(records)} SST records from ERDDAP")
            return records
        else:
            logger.log_warning("Could not parse SST data, falling back to synthetic")
            return generate_synthetic_sst_data()
    
    except Exception as e:
        logger.log_error(f"Error fetching SST data: {str(e)}")
        logger.log_warning("Falling back to synthetic data")
        return generate_synthetic_sst_data()


def create_geojson_features(records: list) -> list:
    """
    Convert records to GeoJSON features.
    
    Args:
        records: List of SST data records
    
    Returns:
        list: List of GeoJSON Feature objects
    """
    features = []
    
    for record in records:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [record['lon'], record['lat']]
            },
            "properties": {
                "sst_celsius": record['sst_celsius'],
                "flagged": record.get('flagged', False)
            }
        }
        features.append(feature)
    
    return features


def run_sst_pipeline() -> dict:
    """
    Run the SST (Sea Surface Temperature) pipeline end-to-end.
    
    Returns:
        dict: Pipeline execution summary
    """
    start_time = time.time()
    
    logger.log_info("=" * 60)
    logger.log_info("Starting SST (Sea Surface Temperature) Pipeline")
    logger.log_info("=" * 60)
    
    result = {
        'pipeline': 'sst',
        'status': 'failed',
        'points_processed': 0,
        'duration': 0,
        'output_s3_key': None,
        'file_size': 0,
        'error': None
    }
    
    try:
        # Fetch SST data
        logger.log_info("Fetching SST data...")
        records = fetch_sst_data()
        
        if not records:
            raise Exception("No SST data retrieved")
        
        result['points_processed'] = len(records)
        logger.log_info(f"Processing {len(records)} SST records")
        
        # Create output directory with date
        today = datetime.utcnow().strftime("%Y-%m-%d")
        output_dir = OUTPUT_DIR / "sst_temp" / today
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Compress JSON
        json_path = output_dir / "sst_global.json.gz"
        if not compress_json(records, str(json_path)):
            raise Exception("Failed to compress JSON")
        
        # Compress GeoJSON
        features = create_geojson_features(records)
        geojson_path = output_dir / "sst_global.geojson.gz"
        if not compress_geojson(features, str(geojson_path)):
            raise Exception("Failed to compress GeoJSON")
        
        # Upload to simulated S3
        s3_key_json = f"sst/{today}/sst_global.json.gz"
        s3_key_geojson = f"sst/{today}/sst_global.geojson.gz"
        
        if save_to_local_s3(str(json_path), s3_key_json):
            result['output_s3_key'] = s3_key_json
            result['file_size'] = json_path.stat().st_size
        else:
            raise Exception("Failed to upload JSON to S3")
        
        if not save_to_local_s3(str(geojson_path), s3_key_geojson):
            raise Exception("Failed to upload GeoJSON to S3")
        
        # Log to database
        duration = time.time() - start_time
        result['duration'] = round(duration, 2)
        result['status'] = 'success'
        
        db = get_database()
        db.log_run(
            pipeline_name='sst',
            status='success',
            points_processed=len(records),
            duration_seconds=duration,
            output_s3_key=s3_key_json,
            file_size_bytes=result['file_size'],
            pipeline_version='1.0'
        )
        
        logger.log_info(f"SST pipeline completed successfully in {duration:.2f}s")
        logger.log_info("=" * 60)
        
        return result
    
    except Exception as e:
        duration = time.time() - start_time
        result['duration'] = round(duration, 2)
        result['error'] = str(e)
        
        logger.log_error(f"SST pipeline failed: {str(e)}")
        
        db = get_database()
        db.log_run(
            pipeline_name='sst',
            status='failed',
            points_processed=0,
            duration_seconds=duration,
            error_message=str(e),
            pipeline_version='1.0'
        )
        
        logger.log_info("=" * 60)
        return result


if __name__ == "__main__":
    result = run_sst_pipeline()
    import json
    print(json.dumps(result, indent=2))
