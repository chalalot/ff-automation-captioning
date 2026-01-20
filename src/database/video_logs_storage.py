import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class VideoLogsStorage:
    """
    SQLite storage adapter for video generation logs.
    """

    def __init__(self, db_path: str = "video_logs.db"):
        """
        Initialize storage with SQLite database.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize database: create table and migrate if needed."""
        self._create_table()

    def _create_table(self):
        """Create video_logs table if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT,
                    execution_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    source_image_path TEXT,
                    video_output_path TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filename_id TEXT
                );
            """)
            
            # Migration: Add batch_id/filename_id column if it doesn't exist (for existing tables)
            cursor.execute("PRAGMA table_info(video_logs)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'batch_id' not in columns:
                logger.info("Migrating video_logs: Adding batch_id column")
                cursor.execute("ALTER TABLE video_logs ADD COLUMN batch_id TEXT")
            
            if 'filename_id' not in columns:
                logger.info("Migrating video_logs: Adding filename_id column")
                cursor.execute("ALTER TABLE video_logs ADD COLUMN filename_id TEXT")
            
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise
        finally:
            conn.close()

    def log_execution(self, execution_id: str, prompt: str, source_image_path: str = None, batch_id: str = None, filename_id: str = None) -> int:
        """
        Log a new execution.
        
        Returns:
            The inserted row ID.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO video_logs (execution_id, prompt, source_image_path, video_output_path, status, batch_id, filename_id)
                VALUES (?, ?, ?, NULL, 'pending', ?, ?)
            """, (execution_id, prompt, source_image_path, batch_id, filename_id))
            
            row_id = cursor.lastrowid
            conn.commit()
            return row_id
        except Exception as e:
            logger.error(f"Failed to log execution: {e}")
            raise
        finally:
            conn.close()

    def update_result(self, execution_id: str, video_output_path: str = None, status: str = 'completed'):
        """
        Update the result for a given execution_id.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if video_output_path:
                cursor.execute("""
                    UPDATE video_logs 
                    SET video_output_path = ?, status = ?
                    WHERE execution_id = ?
                """, (video_output_path, status, execution_id))
            else:
                cursor.execute("""
                    UPDATE video_logs 
                    SET status = ?
                    WHERE execution_id = ?
                """, (status, execution_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to update result for {execution_id}: {e}")
            raise
        finally:
            conn.close()

    def get_execution(self, execution_id: str):
        """Get execution details by execution ID."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM video_logs 
                WHERE execution_id = ?
            """, (execution_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to fetch execution: {e}")
            return None
        finally:
            conn.close()

    def get_recent_executions(self, limit: int = 50):
        """Get recent executions ordered by creation time descending."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM video_logs 
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch recent executions: {e}")
            return []
        finally:
            conn.close()

    def get_incomplete_batches(self):
        """
        Get list of batch_ids that have pending tasks.
        Returns distinct batch_ids and their timestamps.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Find batches that have at least one execution not 'completed' and not 'failed' (i.e. 'pending')
            # Actually, we want batches where we might want to resume monitoring.
            # If a batch has 'pending' items, it's incomplete.
            cursor.execute("""
                SELECT DISTINCT batch_id, created_at, count(*) as count
                FROM video_logs 
                WHERE batch_id IS NOT NULL 
                AND status NOT IN ('completed', 'failed')
                GROUP BY batch_id
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch incomplete batches: {e}")
            return []
        finally:
            conn.close()

    def get_batch_executions(self, batch_id: str):
        """
        Get all executions for a specific batch.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM video_logs 
                WHERE batch_id = ?
                ORDER BY id ASC
            """, (batch_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch batch executions: {e}")
            return []
        finally:
            conn.close()
