"""
Configuration module for CUMULUS Multi-Source Pipeline.
Loads settings from environment variables and .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = OUTPUT_DIR / "logs"
S3_SIMULATED_DIR = OUTPUT_DIR / "s3"
DATABASE_PATH = OUTPUT_DIR / "rds.db"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
S3_SIMULATED_DIR.mkdir(parents=True, exist_ok=True)

# Database configuration
DB_MODE = os.getenv("DB_MODE", "local")  # local or prod
if DB_MODE == "local":
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "")

# Storage configuration
STORAGE_MODE = os.getenv("STORAGE_MODE", "local")  # local or prod
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "cumulus-wave-data")

# API configuration
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "2"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

# NOAA API endpoints
WW3_BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod"
ERDDAP_COASTWATCH_URL = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"
TIDES_API_URL = "https://api.tidesandcurrents.noaa.gov"

# Pipeline configuration
PIPELINES = {
    "ww3": {
        "name": "WW3 Wave Data",
        "description": "NOAA GEFS WaveWatch III wave forecasts",
        "enabled": True,
    },
    "sst": {
        "name": "Sea Surface Temperature",
        "description": "NOAA ERDDAP SST observations",
        "enabled": True,
    },
    "currents": {
        "name": "Ocean Currents",
        "description": "NOAA OSCAR ocean current velocities",
        "enabled": True,
    },
    "tides": {
        "name": "Coastal Tide Predictions",
        "description": "NOAA CO-OPS tide predictions",
        "enabled": True,
    },
}
