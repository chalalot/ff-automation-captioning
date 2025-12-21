import sqlite3
import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class ImageLogsStorage:
    """
    SQLite storage adapter for image generation logs.
    """

    def __init__(self, db_path: str = "image_logs.db"):
        """
        Initialize storage with SQLite database.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._create_table()

    def _get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        """Create image_logs table if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    image_ref_path TEXT,
                    result_image_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise
        finally:
            conn.close()

    def log_execution(self, execution_id: str, prompt: str, image_ref_path: str = None) -> int:
        """
        Log a new execution.
        
        Returns:
            The inserted row ID.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO image_logs (execution_id, prompt, image_ref_path, result_image_path)
                VALUES (?, ?, ?, NULL)
            """, (execution_id, prompt, image_ref_path))
            
            row_id = cursor.lastrowid
            conn.commit()
            return row_id
        except Exception as e:
            logger.error(f"Failed to log execution: {e}")
            raise
        finally:
            conn.close()

    def get_pending_executions(self):
        """
        Get all executions where result_image_path is NULL.
        
        Returns:
            List of dictionaries representing rows.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM image_logs 
                WHERE result_image_path IS NULL
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch pending executions: {e}")
            return []
        finally:
            conn.close()

    def update_result_path(self, execution_id: str, result_image_path: str, new_ref_path: str = None):
        """
        Update the result_image_path for a given execution_id.
        Optionally update image_ref_path if it was moved/renamed.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if new_ref_path:
                cursor.execute("""
                    UPDATE image_logs 
                    SET result_image_path = ?, image_ref_path = ?
                    WHERE execution_id = ?
                """, (result_image_path, new_ref_path, execution_id))
            else:
                cursor.execute("""
                    UPDATE image_logs 
                    SET result_image_path = ?
                    WHERE execution_id = ?
                """, (result_image_path, execution_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to update result path for {execution_id}: {e}")
            raise
        finally:
            conn.close()
