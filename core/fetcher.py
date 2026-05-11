"""
HTTP fetcher module with retry logic and exponential backoff.
Handles downloading files and fetching JSON from NOAA APIs.
"""

import requests
import time
import json
from pathlib import Path
from config import MAX_RETRIES, RETRY_DELAY, REQUEST_TIMEOUT
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)


def download_file(url: str, dest_path: str) -> bool:
    """
    Download a file from URL with exponential backoff retry logic.
    
    Args:
        url: URL to download from
        dest_path: Local file path to save to
    
    Returns:
        bool: True if successful, False otherwise
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    retry_count = 0
    delay = RETRY_DELAY
    
    while retry_count < MAX_RETRIES:
        try:
            logger.log_info(f"Downloading from {url}")
            response = requests.get(url, timeout=REQUEST_TIMEOUT, stream=True)
            response.raise_for_status()
            
            # Write to file in chunks
            with open(dest, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = dest.stat().st_size
            logger.log_info(f"Downloaded {file_size} bytes to {dest_path}")
            return True
            
        except requests.exceptions.RequestException as e:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                logger.log_warning(f"Download failed (attempt {retry_count}/{MAX_RETRIES}): {str(e)}")
                logger.log_info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                logger.log_error(f"Download failed after {MAX_RETRIES} attempts: {str(e)}")
                return False
        except Exception as e:
            logger.log_error(f"Unexpected error downloading file: {str(e)}")
            return False
    
    return False


def fetch_json(url: str) -> dict:
    """
    Fetch JSON data from a URL with retry logic.
    
    Args:
        url: URL to fetch from
    
    Returns:
        dict: Parsed JSON response, or empty dict on failure
    """
    retry_count = 0
    delay = RETRY_DELAY
    
    while retry_count < MAX_RETRIES:
        try:
            logger.log_info(f"Fetching JSON from {url}")
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            logger.log_info(f"Successfully fetched JSON ({len(str(data))} bytes)")
            return data
            
        except requests.exceptions.RequestException as e:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                logger.log_warning(f"API request failed (attempt {retry_count}/{MAX_RETRIES}): {str(e)}")
                logger.log_info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                logger.log_error(f"API request failed after {MAX_RETRIES} attempts: {str(e)}")
                return {}
        except json.JSONDecodeError as e:
            logger.log_error(f"Failed to parse JSON response: {str(e)}")
            return {}
        except Exception as e:
            logger.log_error(f"Unexpected error fetching JSON: {str(e)}")
            return {}
    
    return {}
