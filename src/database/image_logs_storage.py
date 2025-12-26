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
        self._init_db()

    def _get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize database: create table and migrate if needed."""
        self._create_table()
        self._migrate_table()

    def _create_table(self):
        """Create image_logs table if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Check if table exists to decide if we need to create it with new schema
            # or rely on migration. We'll just CREATE IF NOT EXISTS with the FULL schema 
            # for fresh installs.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    persona TEXT,
                    image_ref_path TEXT,
                    result_image_path TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise
        finally:
            conn.close()

    def _migrate_table(self):
        """Check for missing columns and add them (migration)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get existing columns
            cursor.execute("PRAGMA table_info(image_logs)")
            columns = [info[1] for info in cursor.fetchall()]
            
            if "status" not in columns:
                logger.info("Migrating database: Adding 'status' column to image_logs table.")
                cursor.execute("ALTER TABLE image_logs ADD COLUMN status TEXT DEFAULT 'pending'")
                conn.commit()

            if "persona" not in columns:
                logger.info("Migrating database: Adding 'persona' column to image_logs table.")
                cursor.execute("ALTER TABLE image_logs ADD COLUMN persona TEXT")
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to migrate table: {e}")
            # Don't raise here, as table creation might have succeeded or it's a critical error
            # but we don't want to crash init if possible, although schema mismatch is bad.
            raise
        finally:
            conn.close()

    def log_execution(self, execution_id: str, prompt: str, image_ref_path: str = None, persona: str = None) -> int:
        """
        Log a new execution.
        
        Returns:
            The inserted row ID.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO image_logs (execution_id, prompt, persona, image_ref_path, result_image_path, status)
                VALUES (?, ?, ?, ?, NULL, 'pending')
            """, (execution_id, prompt, persona, image_ref_path))
            
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
        Get all executions where status is 'pending'.
        Also includes legacy rows where result_image_path is NULL and status might be NULL (if defaulted badly or old data).
        The migration sets default 'pending' for new rows, but existing rows get the default value (pending) automatically when column is added?
        SQLite ADD COLUMN ... DEFAULT ... *does* populate existing rows with the default value.
        So checking status='pending' is sufficient.
        
        Returns:
            List of dictionaries representing rows.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM image_logs 
                WHERE status = 'pending'
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
        Update the result_image_path for a given execution_id and set status to 'completed'.
        Optionally update image_ref_path if it was moved/renamed.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if new_ref_path:
                cursor.execute("""
                    UPDATE image_logs 
                    SET result_image_path = ?, image_ref_path = ?, status = 'completed'
                    WHERE execution_id = ?
                """, (result_image_path, new_ref_path, execution_id))
            else:
                cursor.execute("""
                    UPDATE image_logs 
                    SET result_image_path = ?, status = 'completed'
                    WHERE execution_id = ?
                """, (result_image_path, execution_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to update result path for {execution_id}: {e}")
            raise
        finally:
            conn.close()

    def mark_as_failed(self, execution_id: str):
        """
        Mark an execution as failed.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE image_logs 
                SET status = 'failed'
                WHERE execution_id = ?
            """, (execution_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to mark execution {execution_id} as failed: {e}")
            raise
        finally:
            conn.close()

    def get_execution_by_result_path(self, result_image_path: str):
        """Get execution details by result image path."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM image_logs 
                WHERE result_image_path = ?
            """, (result_image_path,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to fetch execution by path: {e}")
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
                SELECT * FROM image_logs 
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

    def get_all_completed_executions(self):
        """Get all completed executions (where result_image_path is not null)."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM image_logs 
                WHERE result_image_path IS NOT NULL
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch all completed executions: {e}")
            return []
        finally:
            conn.close()
