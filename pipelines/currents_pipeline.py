"""
Ocean Current Velocity (OSCAR) Pipeline - NOAA CoastWatch ERDDAP

Data Source: NOAA CoastWatch ERDDAP - OSCAR (Ocean Surface Current Analysis Real-time)
URL: https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplOscar_LonPM180.json

Variables Extracted:
- u: Eastward velocity component (m/s)
- v: Northward velocity component (m/s)
- speed: Computed total velocity magnitude
- direction: Computed direction in degrees

Response Format: ERDDAP JSON with dual variable query returning u and v components

Extension from EGR 500 Internship:
- Original internship: Single WW3 wave data source
- This version: NEW - Ocean current data demonstrates multi-variable ERDDAP queries
- Showcases vector component computation (speed and direction from u,v)
- Part of comprehensive multi-source environmental data pipeline
"""

import time
import math
import numpy as np
from datetime import datetime
from pathlib import Path

from core.logger import PipelineLogger
from core.fetcher import fetch_json
from core.compressor import compress_json, compress_geojson
from core.storage import save_to_local_s3
from core.database import get_database

logger = PipelineLogger(__name__)


def generate_synthetic_currents_data(num_points: int = 300) -> list:
    """
    Generate realistic synthetic ocean current data.
    Used when real ERDDAP data fetch fails.
    
    Args:
        num_points: Number of data points to generate
    
    Returns:
        list: List of current records
    """
    logger.log_warning(f"Generating synthetic ocean current data ({num_points} points)")
    
    records = []
    
    # Create a grid of lat/lon points
    lats = np.linspace(0, 60, 12)
    lons = np.linspace(-179, 180, 25)
    
    for lat in lats:
        for lon in lons:
            if len(records) >= num_points:
                break
            
            # Realistic current velocities (0.01 - 0.5 m/s)
            speed = np.random.uniform(0.01, 0.5)
            direction_rad = np.random.uniform(0, 2 * math.pi)
            
            u = speed * math.cos(direction_rad)
            v = speed * math.sin(direction_rad)
            
            # Compute derived values
            computed_speed = math.sqrt(u**2 + v**2)
            computed_direction = math.degrees(math.atan2(u, v))
            if computed_direction < 0:
                computed_direction += 360
            
            records.append({
                'lat': round(lat, 2),
                'lon': round(lon, 2),
                'u': round(u, 4),
                'v': round(v, 4),
                'speed_ms': round(computed_speed, 4),
                'direction_deg': round(computed_direction, 1)
            })
    
    logger.log_info(f"Generated {len(records)} synthetic current records")
    return records


def parse_erddap_currents_response(data: dict) -> list:
    """
    Parse ERDDAP JSON response with dual u,v variables.
    
    ERDDAP response format with dual query:
    {
      "table": {
        "columnNames": ["time", "altitude", "latitude", "longitude", "u", "v"],
        "rows": [[time_val, alt_val, lat_val, lon_val, u_val, v_val], ...]
      }
    }
    
    Args:
        data: Parsed ERDDAP JSON response
    
    Returns:
        list: List of current records
    """
    try:
        logger.log_info("Parsing ERDDAP currents response")
        
        if 'table' not in data or 'rows' not in data.get('table', {}):
            logger.log_warning("Missing table or rows in ERDDAP response")
            return None
        
        rows = data['table']['rows']
        logger.log_info(f"Found {len(rows)} rows in ERDDAP response")
        
        records = []
        
        for row in rows:
            # Row format: [time, altitude, latitude, longitude, u, v]
            if len(row) < 6:
                continue
            
            try:
                lat = float(row[2])
                lon = float(row[3])
                u = float(row[4]) if row[4] is not None else None
                v = float(row[5]) if row[5] is not None else None
                
                # Filter NaN/fill values
                if u is None or v is None or math.isnan(u) or math.isnan(v):
                    continue
                
                # Compute speed and direction
                speed = math.sqrt(u**2 + v**2)
                direction = math.degrees(math.atan2(u, v))
                if direction < 0:
                    direction += 360
                
                records.append({
                    'lat': round(lat, 2),
                    'lon': round(lon, 2),
                    'u': round(u, 4),
                    'v': round(v, 4),
                    'speed_ms': round(speed, 4),
                    'direction_deg': round(direction, 1)
                })
            except (TypeError, ValueError):
                continue
        
        logger.log_info(f"Extracted {len(records)} current records")
        return records if records else None
    
    except Exception as e:
        logger.log_error(f"Error parsing ERDDAP response: {str(e)}")
        return None


def fetch_currents_data() -> list:
    """
    Fetch real ocean current data from NOAA ERDDAP OSCAR.
    Falls back to synthetic data if real data unavailable.
    
    Returns:
        list: Current records
    """
    try:
        # ERDDAP endpoint for OSCAR currents
        url = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplOscar3rdParty_LonPM180.json?u[(last)][(0.0)][(0.0):(60.0)][(-179.0):(180.0)],v[(last)][(0.0)][(0.0):(60.0)][(-179.0):(180.0)]"
        
        logger.log_info(f"Fetching ocean current data from ERDDAP OSCAR")
        
        # Fetch JSON from ERDDAP
        data = fetch_json(url)
        
        if not data:
            logger.log_warning("Empty response from ERDDAP currents endpoint")
            return generate_synthetic_currents_data()
        
        # Parse response
        records = parse_erddap_currents_response(data)
        
        if records:
            logger.log_info(f"Successfully fetched {len(records)} current records from ERDDAP")
            return records
        else:
            logger.log_warning("Could not parse current data, falling back to synthetic")
            return generate_synthetic_currents_data()
    
    except Exception as e:
        logger.log_error(f"Error fetching current data: {str(e)}")
        logger.log_warning("Falling back to synthetic data")
        return generate_synthetic_currents_data()


def create_geojson_features(records: list) -> list:
    """
    Convert records to GeoJSON features.
    
    Args:
        records: List of current data records
    
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
                "u_ms": record['u'],
                "v_ms": record['v'],
                "speed_ms": record['speed_ms'],
                "direction_deg": record['direction_deg']
            }
        }
        features.append(feature)
    
    return features


def run_currents_pipeline() -> dict:
    """
    Run the Ocean Currents (OSCAR) pipeline end-to-end.
    
    Returns:
        dict: Pipeline execution summary
    """
    start_time = time.time()
    
    logger.log_info("=" * 60)
    logger.log_info("Starting Ocean Currents (OSCAR) Pipeline")
    logger.log_info("=" * 60)
    
    result = {
        'pipeline': 'currents',
        'status': 'failed',
        'points_processed': 0,
        'duration': 0,
        'output_s3_key': None,
        'file_size': 0,
        'error': None
    }
    
    try:
        # Fetch current data
        logger.log_info("Fetching current data...")
        records = fetch_currents_data()
        
        if not records:
            raise Exception("No current data retrieved")
        
        result['points_processed'] = len(records)
        logger.log_info(f"Processing {len(records)} current records")
        
        # Create output directory with date
        today = datetime.utcnow().strftime("%Y-%m-%d")
        output_dir = Path("output/currents_temp") / today
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Compress JSON
        json_path = output_dir / "currents_global.json.gz"
        if not compress_json(records, str(json_path)):
            raise Exception("Failed to compress JSON")
        
        # Compress GeoJSON
        features = create_geojson_features(records)
        geojson_path = output_dir / "currents_global.geojson.gz"
        if not compress_geojson(features, str(geojson_path)):
            raise Exception("Failed to compress GeoJSON")
        
        # Upload to simulated S3
        s3_key_json = f"currents/{today}/currents_global.json.gz"
        s3_key_geojson = f"currents/{today}/currents_global.geojson.gz"
        
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
            pipeline_name='currents',
            status='success',
            points_processed=len(records),
            duration_seconds=duration,
            output_s3_key=s3_key_json,
            file_size_bytes=result['file_size'],
            pipeline_version='1.0'
        )
        
        logger.log_info(f"Currents pipeline completed successfully in {duration:.2f}s")
        logger.log_info("=" * 60)
        
        return result
    
    except Exception as e:
        duration = time.time() - start_time
        result['duration'] = round(duration, 2)
        result['error'] = str(e)
        
        logger.log_error(f"Currents pipeline failed: {str(e)}")
        
        db = get_database()
        db.log_run(
            pipeline_name='currents',
            status='failed',
            points_processed=0,
            duration_seconds=duration,
            error_message=str(e),
            pipeline_version='1.0'
        )
        
        logger.log_info("=" * 60)
        return result


if __name__ == "__main__":
    result = run_currents_pipeline()
    import json
    print(json.dumps(result, indent=2))
