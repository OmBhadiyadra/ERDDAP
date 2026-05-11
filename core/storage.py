"""
Storage module for saving files to simulated S3 (local filesystem).
"""

import shutil
from pathlib import Path
from config import S3_SIMULATED_DIR, STORAGE_MODE, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET
from core.logger import PipelineLogger
import boto3

logger = PipelineLogger(__name__)


def save_to_local_s3(local_path: str, s3_key: str) -> bool:
    """
    Save a file to simulated S3 (local filesystem) or real S3.
    
    Args:
        local_path: Local file path to upload
        s3_key: S3 key path (e.g., "ww3/2024-01-15/data.json.gz")
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        local_file = Path(local_path)
        if not local_file.exists():
            logger.log_error(f"Local file not found: {local_path}")
            return False
        
        if STORAGE_MODE == "local":
            return _save_to_local_s3_impl(local_path, s3_key)
        else:
            return _save_to_aws_s3(local_path, s3_key)
    
    except Exception as e:
        logger.log_error(f"Error saving to S3: {str(e)}")
        return False


def _save_to_local_s3_impl(local_path: str, s3_key: str) -> bool:
    """Save to local filesystem simulation."""
    try:
        dest_path = S3_SIMULATED_DIR / s3_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(local_path, dest_path)
        
        file_size = dest_path.stat().st_size
        logger.log_info(f"[SIMULATED S3 UPLOAD] s3://{S3_BUCKET}/{s3_key} ({file_size} bytes)")
        logger.log_debug(f"Local path: {dest_path}")
        
        return True
    except Exception as e:
        logger.log_error(f"Failed to save to local S3: {str(e)}")
        return False


def _save_to_aws_s3(local_path: str, s3_key: str) -> bool:
    """Save to real AWS S3 (requires credentials)."""
    try:
        if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
            logger.log_error("AWS credentials not configured for S3 upload")
            return False
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        
        s3_client.upload_file(local_path, S3_BUCKET, s3_key)
        
        file_size = Path(local_path).stat().st_size
        logger.log_info(f"[AWS S3 UPLOAD] s3://{S3_BUCKET}/{s3_key} ({file_size} bytes)")
        
        return True
    except Exception as e:
        logger.log_error(f"Failed to upload to AWS S3: {str(e)}")
        return False


def list_s3_objects(prefix: str) -> list:
    """
    List all files under a prefix in simulated S3.
    
    Args:
        prefix: S3 prefix path (e.g., "ww3/")
    
    Returns:
        list: List of file paths relative to simulated S3 root
    """
    try:
        prefix_path = S3_SIMULATED_DIR / prefix
        if not prefix_path.exists():
            logger.log_debug(f"Prefix path does not exist: {prefix_path}")
            return []
        
        files = []
        for file_path in prefix_path.rglob('*'):
            if file_path.is_file():
                rel_path = file_path.relative_to(S3_SIMULATED_DIR)
                files.append(str(rel_path))
        
        logger.log_info(f"Found {len(files)} objects under prefix '{prefix}'")
        return sorted(files)
    
    except Exception as e:
        logger.log_error(f"Error listing S3 objects: {str(e)}")
        return []
