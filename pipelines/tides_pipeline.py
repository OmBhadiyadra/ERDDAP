"""
Coastal Tide Predictions Pipeline - NOAA CO-OPS

Data Source: NOAA CO-OPS (Center for Operational Oceanographic Products and Services)
Endpoints: 
- Stations: https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json
- Predictions: https://api.tidesandcurrents.noaa.gov/api/prod/datagetter

Variables Extracted:
- station_id, name: Station identification
- lat, lon: Geographic coordinates
- next_high_time: Next high tide time (HH:MM format)
- next_high_m: Next high tide height (meters)
- next_low_time: Next low tide time (HH:MM format)
- next_low_m: Next low tide height (meters)

Extension from EGR 500 Internship:
- Original internship: Single-source WW3 wave forecasts
- This version: NEW - Station-based point data demonstrates different data structure
- Integrates multi-station geographic sampling (50 stations)
- Example of real-time operational oceanographic data endpoints
"""

import time
from datetime import datetime

from config import OUTPUT_DIR
from core.logger import PipelineLogger
from core.fetcher import fetch_json
from core.compressor import compress_json, compress_geojson
from core.storage import save_to_local_s3
from core.database import get_database

logger = PipelineLogger(__name__)


def generate_synthetic_tide_data(num_stations: int = 50) -> list:
    """
    Generate realistic synthetic tide prediction data.
    Used when real CO-OPS data fetch fails.
    
    Args:
        num_stations: Number of stations to generate
    
    Returns:
        list: List of tide records
    """
    logger.log_warning(f"Generating synthetic tide data ({num_stations} stations)")
    
    records = []
    
    # Sample stations from around the US coast
    sample_stations = [
        {"id": "8454000", "name": "The Narrows, NY", "lat": 40.6433, "lon": -74.0167},
        {"id": "8467150", "name": "Ocean City Inlet, MD", "lat": 38.3328, "lon": -75.0841},
        {"id": "8454049", "name": "Battery Park, NY", "lat": 40.7033, "lon": -74.0165},
        {"id": "8419870", "name": "Boston, MA", "lat": 42.3593, "lon": -71.0527},
        {"id": "8468090", "name": "Cape May, NJ", "lat": 38.9658, "lon": -74.9608},
        {"id": "8454500", "name": "Graves Light, MA", "lat": 42.3833, "lon": -70.8833},
        {"id": "8443970", "name": "Portsmouth, NH", "lat": 43.0725, "lon": -70.7408},
        {"id": "8452644", "name": "Sandy Hook, NJ", "lat": 40.4693, "lon": -73.9895},
        {"id": "8423898", "name": "Providence, RI", "lat": 41.8067, "lon": -71.4138},
        {"id": "8454711", "name": "Coney Island, NY", "lat": 40.5733, "lon": -73.9833},
    ]
    
    for i, station in enumerate(sample_stations[:num_stations]):
        records.append({
            "station_id": station["id"],
            "name": station["name"],
            "lat": station["lat"],
            "lon": station["lon"],
            "next_high_time": f"{8 + (i % 8):02d}:{30 * (i % 2):02d}",
            "next_high_m": round(1.0 + i * 0.1, 2),
            "next_low_time": f"{14 + (i % 8):02d}:{30 * ((i + 1) % 2):02d}",
            "next_low_m": round(0.2 + i * 0.05, 2)
        })
    
    logger.log_info(f"Generated {len(records)} synthetic tide stations")
    return records


def fetch_tide_stations() -> list:
    """
    Fetch list of tide prediction stations from NOAA CO-OPS.
    
    Returns:
        list: List of station objects with id, name, lat, lon
    """
    try:
        logger.log_info("Fetching tide station list from CO-OPS")
        
        url = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions&units=metric"
        
        data = fetch_json(url)
        
        if not data or 'stations' not in data:
            logger.log_warning("No stations in CO-OPS response")
            return []
        
        stations = data['stations']
        logger.log_info(f"Found {len(stations)} tide prediction stations")
        
        # Limit to first 50 stations to keep runtime reasonable
        stations = stations[:50]
        
        return stations
    
    except Exception as e:
        logger.log_error(f"Error fetching tide stations: {str(e)}")
        return []


def fetch_tide_predictions(station_id: str, station_name: str, station_lat: float, 
                           station_lon: float) -> dict:
    """
    Fetch tide predictions for a specific station.
    
    Args:
        station_id: CO-OPS station ID
        station_name: Station name
        station_lat: Station latitude
        station_lon: Station longitude
    
    Returns:
        dict: Tide record with high/low predictions
    """
    try:
        today = datetime.utcnow().strftime("%Y%m%d")
        
        url = (f"https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
               f"station={station_id}"
               f"&product=predictions"
               f"&datum=MLLW"
               f"&time_zone=gmt"
               f"&interval=hilo"
               f"&units=metric"
               f"&application=cumulus_cis600"
               f"&format=json"
               f"&begin_date={today}"
               f"&end_date={today}")
        
        data = fetch_json(url)
        
        if not data or 'predictions' not in data or len(data['predictions']) < 2:
            # Return empty predictions if fetch fails
            return {
                "station_id": station_id,
                "name": station_name,
                "lat": station_lat,
                "lon": station_lon,
                "next_high_time": "N/A",
                "next_high_m": 0,
                "next_low_time": "N/A",
                "next_low_m": 0
            }
        
        predictions = data['predictions']
        
        # Extract first high and low tides
        high_times = [p for p in predictions if p.get('type') == 'H']
        low_times = [p for p in predictions if p.get('type') == 'L']
        
        next_high_time = high_times[0]['t'].split()[-1] if high_times else "N/A"
        next_low_time  = low_times[0]['t'].split()[-1]  if low_times  else "N/A"
        next_high_m    = float(high_times[0]['v'])       if high_times else 0.0
        next_low_m     = float(low_times[0]['v'])        if low_times  else 0.0
        
        return {
            "station_id": station_id,
            "name": station_name,
            "lat": round(float(station_lat), 4),
            "lon": round(float(station_lon), 4),
            "next_high_time": next_high_time,
            "next_high_m": round(next_high_m, 2),
            "next_low_time": next_low_time,
            "next_low_m": round(next_low_m, 2)
        }
    
    except Exception as e:
        logger.log_debug(f"Error fetching predictions for station {station_id}: {str(e)}")
        return {
            "station_id": station_id,
            "name": station_name,
            "lat": station_lat,
            "lon": station_lon,
            "next_high_time": "ERROR",
            "next_high_m": 0,
            "next_low_time": "ERROR",
            "next_low_m": 0
        }


def fetch_tides_data() -> list:
    """
    Fetch tide predictions for multiple stations from NOAA CO-OPS.
    Falls back to synthetic data if real data unavailable.
    
    Returns:
        list: List of tide records
    """
    try:
        # Fetch station list
        stations = fetch_tide_stations()
        
        if not stations:
            logger.log_warning("No stations retrieved, falling back to synthetic data")
            return generate_synthetic_tide_data()
        
        records = []
        
        for i, station in enumerate(stations):
            logger.log_debug(f"Fetching tide predictions for station {i+1}/{len(stations)}: {station.get('name', 'Unknown')}")
            
            tide_record = fetch_tide_predictions(
                station_id=station.get('id', ''),
                station_name=station.get('name', ''),
                station_lat=station.get('lat', 0),
                station_lon=station.get('lon', 0)
            )
            
            records.append(tide_record)
            
            # Add small delay to avoid overwhelming API
            if i < len(stations) - 1:
                time.sleep(0.2)
        
        logger.log_info(f"Fetched tide predictions for {len(records)} stations")
        return records if records else generate_synthetic_tide_data()
    
    except Exception as e:
        logger.log_error(f"Error fetching tide data: {str(e)}")
        logger.log_warning("Falling back to synthetic data")
        return generate_synthetic_tide_data()


def create_geojson_features(records: list) -> list:
    """
    Convert records to GeoJSON station features.
    
    Args:
        records: List of tide station records
    
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
                "station_id": record['station_id'],
                "name": record['name'],
                "next_high_time": record['next_high_time'],
                "next_high_m": record['next_high_m'],
                "next_low_time": record['next_low_time'],
                "next_low_m": record['next_low_m']
            }
        }
        features.append(feature)
    
    return features


def run_tides_pipeline() -> dict:
    """
    Run the Tides (CO-OPS) pipeline end-to-end.
    
    Returns:
        dict: Pipeline execution summary
    """
    start_time = time.time()
    
    logger.log_info("=" * 60)
    logger.log_info("Starting Coastal Tide Predictions (CO-OPS) Pipeline")
    logger.log_info("=" * 60)
    
    result = {
        'pipeline': 'tides',
        'status': 'failed',
        'points_processed': 0,
        'duration': 0,
        'output_s3_key': None,
        'file_size': 0,
        'error': None
    }
    
    try:
        # Fetch tide data
        logger.log_info("Fetching tide predictions...")
        records = fetch_tides_data()
        
        if not records:
            raise Exception("No tide data retrieved")
        
        result['points_processed'] = len(records)
        logger.log_info(f"Processing {len(records)} tide station records")
        
        # Create output directory with date
        today = datetime.utcnow().strftime("%Y-%m-%d")
        output_dir = OUTPUT_DIR / "tides_temp" / today
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Compress JSON
        json_path = output_dir / "tides_coops.json.gz"
        if not compress_json(records, str(json_path)):
            raise Exception("Failed to compress JSON")
        
        # Compress GeoJSON
        features = create_geojson_features(records)
        geojson_path = output_dir / "tides_coops.geojson.gz"
        if not compress_geojson(features, str(geojson_path)):
            raise Exception("Failed to compress GeoJSON")
        
        # Upload to simulated S3
        s3_key_json = f"tides/{today}/tides_coops.json.gz"
        s3_key_geojson = f"tides/{today}/tides_coops.geojson.gz"
        
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
            pipeline_name='tides',
            status='success',
            points_processed=len(records),
            duration_seconds=duration,
            output_s3_key=s3_key_json,
            file_size_bytes=result['file_size'],
            pipeline_version='1.0'
        )
        
        logger.log_info(f"Tides pipeline completed successfully in {duration:.2f}s")
        logger.log_info("=" * 60)
        
        return result
    
    except Exception as e:
        duration = time.time() - start_time
        result['duration'] = round(duration, 2)
        result['error'] = str(e)
        
        logger.log_error(f"Tides pipeline failed: {str(e)}")
        
        db = get_database()
        db.log_run(
            pipeline_name='tides',
            status='failed',
            points_processed=0,
            duration_seconds=duration,
            error_message=str(e),
            pipeline_version='1.0'
        )
        
        logger.log_info("=" * 60)
        return result


if __name__ == "__main__":
    result = run_tides_pipeline()
    import json
    print(json.dumps(result, indent=2))
