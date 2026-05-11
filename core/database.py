"""
Database module for SQLite logging (simulating RDS).
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from config import DATABASE_PATH, DB_MODE
from core.logger import PipelineLogger

logger = PipelineLogger(__name__)


class PipelineDatabase:
    """SQLite database for pipeline run logging."""
    
    def __init__(self):
        """Initialize database connection and create tables if needed."""
        self.db_path = DATABASE_PATH
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """Create database and tables if they don't exist."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create pipeline_runs table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pipeline_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pipeline_name TEXT NOT NULL,
                        run_timestamp DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        points_processed INTEGER NOT NULL,
                        duration_seconds REAL NOT NULL,
                        output_s3_key TEXT,
                        file_size_bytes INTEGER,
                        pipeline_version TEXT,
                        error_message TEXT
                    )
                ''')
                
                # Create index for faster queries
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_pipeline_name 
                    ON pipeline_runs(pipeline_name)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_run_timestamp 
                    ON pipeline_runs(run_timestamp DESC)
                ''')
                
                conn.commit()
            
            logger.log_info(f"Database initialized at {self.db_path}")
        
        except Exception as e:
            logger.log_error(f"Failed to initialize database: {str(e)}")
    
    def log_run(self, pipeline_name: str, status: str, points_processed: int, 
                duration_seconds: float, output_s3_key: str = None, 
                file_size_bytes: int = None, pipeline_version: str = None,
                error_message: str = None) -> bool:
        """
        Log a pipeline run to the database.
        
        Args:
            pipeline_name: Name of the pipeline
            status: Status (success, failed, partial)
            points_processed: Number of data points processed
            duration_seconds: Time taken to run
            output_s3_key: S3 key where output was saved
            file_size_bytes: Size of output file
            pipeline_version: Pipeline version identifier
            error_message: Error message if failed
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            run_timestamp = datetime.utcnow().isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO pipeline_runs 
                    (pipeline_name, run_timestamp, status, points_processed, 
                     duration_seconds, output_s3_key, file_size_bytes, 
                     pipeline_version, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pipeline_name, run_timestamp, status, points_processed,
                    duration_seconds, output_s3_key, file_size_bytes,
                    pipeline_version, error_message
                ))
                conn.commit()
            
            logger.log_info(f"Logged pipeline run: {pipeline_name} - {status} ({points_processed} points in {duration_seconds:.2f}s)")
            return True
        
        except Exception as e:
            logger.log_error(f"Failed to log pipeline run: {str(e)}")
            return False
    
    def get_runs(self, pipeline_name: str = None, limit: int = 100) -> list:
        """
        Get recent pipeline runs from database.
        
        Args:
            pipeline_name: Filter by pipeline name (None = all)
            limit: Maximum number of runs to return
        
        Returns:
            list: List of run records as dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if pipeline_name:
                    cursor.execute('''
                        SELECT * FROM pipeline_runs
                        WHERE pipeline_name = ?
                        ORDER BY run_timestamp DESC
                        LIMIT ?
                    ''', (pipeline_name, limit))
                else:
                    cursor.execute('''
                        SELECT * FROM pipeline_runs
                        ORDER BY run_timestamp DESC
                        LIMIT ?
                    ''', (limit,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        
        except Exception as e:
            logger.log_error(f"Failed to retrieve pipeline runs: {str(e)}")
            return []
    
    def is_already_processed(self, pipeline_name: str, date_str: str) -> bool:
        """
        Check if a pipeline already processed data for a given date.
        Used for duplicate prevention.
        
        Args:
            pipeline_name: Name of the pipeline
            date_str: Date string (YYYY-MM-DD format)
        
        Returns:
            bool: True if already processed, False otherwise
        """
        try:
            date_prefix = date_str  # e.g., "2024-01-15"
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM pipeline_runs
                    WHERE pipeline_name = ?
                    AND status = 'success'
                    AND output_s3_key LIKE ?
                ''', (pipeline_name, f"%{date_prefix}%"))
                
                count = cursor.fetchone()[0]
                return count > 0
        
        except Exception as e:
            logger.log_error(f"Failed to check if already processed: {str(e)}")
            return False
    
    def get_summary(self) -> dict:
        """
        Get summary statistics from the database.
        
        Returns:
            dict: Summary statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total runs
                cursor.execute("SELECT COUNT(*) FROM pipeline_runs")
                total_runs = cursor.fetchone()[0]
                
                # Successful runs
                cursor.execute("SELECT COUNT(*) FROM pipeline_runs WHERE status = 'success'")
                successful_runs = cursor.fetchone()[0]
                
                # Total points processed
                cursor.execute("SELECT SUM(points_processed) FROM pipeline_runs WHERE status = 'success'")
                total_points = cursor.fetchone()[0] or 0
                
                # Last run time
                cursor.execute("SELECT MAX(run_timestamp) FROM pipeline_runs")
                last_run = cursor.fetchone()[0]
                
                # Pipelines with data
                cursor.execute("SELECT COUNT(DISTINCT pipeline_name) FROM pipeline_runs WHERE status = 'success'")
                pipelines_with_data = cursor.fetchone()[0]
                
                return {
                    'total_runs': total_runs,
                    'successful_runs': successful_runs,
                    'total_points_processed': total_points,
                    'last_run_time': last_run,
                    'pipelines_with_data': pipelines_with_data
                }
        
        except Exception as e:
            logger.log_error(f"Failed to get database summary: {str(e)}")
            return {
                'total_runs': 0,
                'successful_runs': 0,
                'total_points_processed': 0,
                'last_run_time': None,
                'pipelines_with_data': 0
            }


# Global database instance
_db_instance = None


def get_database() -> PipelineDatabase:
    """Get or create the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PipelineDatabase()
    return _db_instance
