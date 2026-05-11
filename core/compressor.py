"""
Compression module for gzipping JSON and GeoJSON output.
"""

import gzip
import json
from pathlib import Path
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)


def compress_json(data: list, output_path: str) -> bool:
    """
    Serialize data to JSON and compress with gzip.
    
    Args:
        data: List of dictionaries to serialize
        output_path: Path to save gzipped JSON file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        # Serialize to JSON
        json_str = json.dumps(data, indent=2)
        json_bytes = json_str.encode('utf-8')
        
        # Compress with gzip
        with gzip.open(output, 'wb') as f:
            f.write(json_bytes)
        
        file_size = output.stat().st_size
        logger.log_info(f"Compressed {len(data)} records to {output_path} ({file_size} bytes)")
        return True
        
    except Exception as e:
        logger.log_error(f"Failed to compress JSON: {str(e)}")
        return False


def compress_geojson(features: list, output_path: str) -> bool:
    """
    Build GeoJSON FeatureCollection and compress with gzip.
    
    Args:
        features: List of GeoJSON Feature objects
        output_path: Path to save gzipped GeoJSON file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        # Build GeoJSON FeatureCollection
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        # Serialize to JSON
        json_str = json.dumps(geojson, indent=2)
        json_bytes = json_str.encode('utf-8')
        
        # Compress with gzip
        with gzip.open(output, 'wb') as f:
            f.write(json_bytes)
        
        file_size = output.stat().st_size
        logger.log_info(f"Compressed {len(features)} features to GeoJSON {output_path} ({file_size} bytes)")
        return True
        
    except Exception as e:
        logger.log_error(f"Failed to compress GeoJSON: {str(e)}")
        return False
