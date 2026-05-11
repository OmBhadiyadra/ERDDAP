"""
WW3 Wave Data Pipeline - NOAA GEFS WaveWatch III

Data Source: NOAA NOMADS GEFS WaveWatch III forecasts
URL Pattern: https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/gefs.{YYYYMMDD}/{HH}/wave/gridded/gefs.wave.t{HH}z.mean.global.0p25.f006.grib2

Variables Extracted:
- swh: Significant Wave Height (meters)
- mwd: Mean Wave Direction (degrees)
- u, v: Computed U/V vector components from swh and mwd

Output Format: JSON array and GeoJSON with records {lat, lon, swh, mwd, u, v}

Extension from EGR 500 Internship:
- Original internship: Fetched real GRIB2 data from NOAA, parsed with xarray/cfgrib
- This version: Re-implemented locally with fallback to synthetic data if endpoint unavailable
- Integrated with multi-source pipeline architecture for SST, Currents, and Tides
"""

import time
import math
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

from config import WW3_BASE_URL
from core.logger import PipelineLogger
from core.fetcher import download_file, fetch_json
from core.compressor import compress_json, compress_geojson
from core.storage import save_to_local_s3
from core.database import get_database

logger = PipelineLogger(__name__)


def generate_synthetic_ww3_data(num_points: int = 500) -> list:
    """
    Generate realistic synthetic WW3 wave data.
    Used when real data fetch fails.
    
    Args:
        num_points: Number of data points to generate
    
    Returns:
        list: List of wave data records
    """
    logger.log_warning(f"Generating synthetic WW3 data ({num_points} points)")
    
    records = []
    
    # Create a grid of lat/lon points
    lats = np.linspace(-89, 89, 20)
    lons = np.linspace(-180, 180, 25)
    
    for lat in lats:
        for lon in lons:
            if len(records) >= num_points:
                break
            
            # Realistic wave heights (0.5 - 8 meters)
            swh = np.random.uniform(0.5, 8.0)
            
            # Realistic wave directions (0-360 degrees)
            mwd = np.random.uniform(0, 360)
            
            # Compute U/V components
            mwd_rad = math.radians(mwd)
            u = swh * math.sin(mwd_rad)
            v = swh * math.cos(mwd_rad)
            
            records.append({
                'lat': round(lat, 2),
                'lon': round(lon, 2),
                'swh': round(swh, 2),
                'mwd': round(mwd, 1),
                'u': round(u, 3),
                'v': round(v, 3)
            })
    
    logger.log_info(f"Generated {len(records)} synthetic wave records")
    return records


def parse_grib2_data(grib_file_path: str) -> list:
    """
    Parse GRIB2 file and extract wave data.
    
    Args:
        grib_file_path: Path to GRIB2 file
    
    Returns:
        list: List of wave data records
    """
    try:
        import xarray as xr
        
        logger.log_info(f"Parsing GRIB2 file: {grib_file_path}")
        
        # Open GRIB2 with cfgrib engine
        ds = xr.open_dataset(grib_file_path, engine='cfgrib')
        
        # Extract variables
        if 'swh' not in ds.data_vars or 'mwd' not in ds.data_vars:
            logger.log_warning("Required variables (swh, mwd) not found in GRIB2 file")
            return None
        
        swh = ds['swh'].values
        mwd = ds['mwd'].values
        lat = ds['latitude'].values if 'latitude' in ds.coords else ds['lat'].values
        lon = ds['longitude'].values if 'longitude' in ds.coords else ds['lon'].values
        
        records = []
        
        # Flatten arrays and create records
        for i, lat_val in enumerate(lat):
            for j, lon_val in enumerate(lon):
                swh_val = float(swh[i, j])
                mwd_val = float(mwd[i, j])
                
                # Skip NaN values
                if np.isnan(swh_val) or np.isnan(mwd_val):
                    continue
                
                # Compute U/V components
                mwd_rad = math.radians(mwd_val)
                u = swh_val * math.sin(mwd_rad)
                v = swh_val * math.cos(mwd_rad)
                
                records.append({
                    'lat': round(float(lat_val), 2),
                    'lon': round(float(lon_val), 2),
                    'swh': round(swh_val, 2),
                    'mwd': round(mwd_val, 1),
                    'u': round(u, 3),
                    'v': round(v, 3)
                })
        
        logger.log_info(f"Extracted {len(records)} wave records from GRIB2")
        ds.close()
        return records
    
    except ImportError:
        logger.log_warning("cfgrib not installed, cannot parse GRIB2")
        return None
    except Exception as e:
        logger.log_error(f"Error parsing GRIB2: {str(e)}")
        return None


def fetch_ww3_data() -> list:
    """
    Fetch real WW3 wave data from NOAA NOMADS.
    Falls back to synthetic data if real data unavailable.
    
    Returns:
        list: Wave data records
    """
    try:
        # Get latest available forecast
        now = datetime.utcnow()
        
        # Try a few recent times (NOMADS updates at 00, 06, 12, 18 UTC)
        for hours_back in [0, 6, 12, 18, 24]:
            forecast_time = now - timedelta(hours=hours_back)
            date_str = forecast_time.strftime("%Y%m%d")
            hour_str = forecast_time.strftime("%H")
            
            # Round hour to nearest 6-hour interval
            hour_int = int(hour_str) // 6 * 6
            hour_str = f"{hour_int:02d}"
            
            url = f"{WW3_BASE_URL}/gefs.{date_str}/{hour_str}/wave/gridded/gefs.wave.t{hour_str}z.mean.global.0p25.f006.grib2"
            
            logger.log_info(f"Attempting to fetch WW3 data from {url}")
            
            # Download to temp file
            with NamedTemporaryFile(suffix='.grib2', delete=False) as tmp:
                tmp_path = tmp.name
            
            if download_file(url, tmp_path):
                # Try to parse GRIB2
                data = parse_grib2_data(tmp_path)
                
                Path(tmp_path).unlink(missing_ok=True)
                
                if data:
                    logger.log_info(f"Successfully fetched WW3 data from {date_str}/{hour_str}")
                    return data
        
        logger.log_warning("Could not fetch real WW3 data, falling back to synthetic data")
        return generate_synthetic_ww3_data()
    
    except Exception as e:
        logger.log_error(f"Error fetching WW3 data: {str(e)}")
        logger.log_warning("Falling back to synthetic data")
        return generate_synthetic_ww3_data()


def create_geojson_features(records: list) -> list:
    """
    Convert records to GeoJSON features.
    
    Args:
        records: List of wave data records
    
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
                "swh_m": record['swh'],
                "mwd_deg": record['mwd'],
                "u_component": record['u'],
                "v_component": record['v'],
                "speed_ms": math.sqrt(record['u']**2 + record['v']**2)
            }
        }
        features.append(feature)
    
    return features


def run_ww3_pipeline() -> dict:
    """
    Run the WW3 wave data pipeline end-to-end.
    
    Returns:
        dict: Pipeline execution summary
    """
    start_time = time.time()
    
    logger.log_info("=" * 60)
    logger.log_info("Starting WW3 Wave Data Pipeline")
    logger.log_info("=" * 60)
    
    result = {
        'pipeline': 'ww3',
        'status': 'failed',
        'points_processed': 0,
        'duration': 0,
        'output_s3_key': None,
        'file_size': 0,
        'error': None
    }
    
    try:
        # Fetch wave data
        logger.log_info("Fetching WW3 wave data...")
        records = fetch_ww3_data()
        
        if not records:
            raise Exception("No wave data retrieved")
        
        result['points_processed'] = len(records)
        logger.log_info(f"Processing {len(records)} wave records")
        
        # Create output directory with date
        today = datetime.utcnow().strftime("%Y-%m-%d")
        output_dir = Path("output/ww3_temp") / today
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Compress JSON
        json_path = output_dir / "f006.json.gz"
        if not compress_json(records, str(json_path)):
            raise Exception("Failed to compress JSON")
        
        # Compress GeoJSON
        features = create_geojson_features(records)
        geojson_path = output_dir / "f006.geojson.gz"
        if not compress_geojson(features, str(geojson_path)):
            raise Exception("Failed to compress GeoJSON")
        
        # Upload to simulated S3
        s3_key_json = f"ww3/{today}/f006.json.gz"
        s3_key_geojson = f"ww3/{today}/f006.geojson.gz"
        
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
            pipeline_name='ww3',
            status='success',
            points_processed=len(records),
            duration_seconds=duration,
            output_s3_key=s3_key_json,
            file_size_bytes=result['file_size'],
            pipeline_version='1.0'
        )
        
        logger.log_info(f"WW3 pipeline completed successfully in {duration:.2f}s")
        logger.log_info("=" * 60)
        
        return result
    
    except Exception as e:
        duration = time.time() - start_time
        result['duration'] = round(duration, 2)
        result['error'] = str(e)
        
        logger.log_error(f"WW3 pipeline failed: {str(e)}")
        
        db = get_database()
        db.log_run(
            pipeline_name='ww3',
            status='failed',
            points_processed=0,
            duration_seconds=duration,
            error_message=str(e),
            pipeline_version='1.0'
        )
        
        logger.log_info("=" * 60)
        return result


if __name__ == "__main__":
    result = run_ww3_pipeline()
    import json
    print(json.dumps(result, indent=2))
