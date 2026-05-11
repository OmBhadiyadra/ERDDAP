"""
Structured logging module with color-coded output and file logging.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from config import LOGS_DIR


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color-coded output based on log level."""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[92m',       # Green
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[95m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        return super().format(record)


class PipelineLogger:
    """Logger for pipeline modules with structured output."""
    
    def __init__(self, name: str):
        """
        Initialize logger for a specific pipeline or module.
        
        Args:
            name: Logger name (typically __name__)
        """
        self.name = name
        self.pipeline_name = name.split('.')[-1] if '.' in name else name
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Console handler with color
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredFormatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler (plain format)
        log_file = LOGS_DIR / f"{self.pipeline_name}.log"
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
    
    def log_info(self, message: str):
        """Log info level message."""
        self.logger.info(message)
    
    def log_warning(self, message: str):
        """Log warning level message."""
        self.logger.warning(message)
    
    def log_error(self, message: str):
        """Log error level message."""
        self.logger.error(message)
    
    def log_debug(self, message: str):
        """Log debug level message."""
        self.logger.debug(message)
    
    def log_critical(self, message: str):
        """Log critical level message."""
        self.logger.critical(message)
