"""
Normalized Runs/Posts Storage Adapter
Implements a normalized two-table structure for storing campaign runs and posts
"""

import json
import time
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("⚠️  psycopg2 not installed. Run: pip install psycopg2-binary")


class RunsPostsStorage:
    """
    Normalized storage adapter using runs and posts tables.

    Schema:
    - runs: Stores high-level campaign/session data
    - posts: Stores individual post content with GCS image links
    """

    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize storage with normalized schema.

        Args:
            connection_string: PostgreSQL connection string (optional, will be built from env vars)
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2-binary is required for database storage")

        # Use centralized database connection utility
        from .db_utils import get_postgres_connection_string
        
        try:
            self.connection_string = get_postgres_connection_string(connection_string)
            print(f"[RunsPostsStorage] Using centralized connection: {get_postgres_connection_string(connection_string, mask_password=True)}")
        except ValueError as e:
            print(f"[RunsPostsStorage] Failed to get connection string: {e}")
            raise

    def _get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(self.connection_string)

    def create_tables(self):
        """Create runs and posts tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Create runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    persona_name TEXT NOT NULL,
                    trend_text TEXT NOT NULL,
                    num_posts INTEGER NOT NULL,
                    adapted_idea JSONB,
                    trend_profile JSONB,
                    metadata JSONB,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                )
            """)

            # Create posts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    post_index INTEGER NOT NULL,
                    caption TEXT,
                    hashtags TEXT[],
                    cta TEXT,
                    image_url TEXT,
                    image_prompt TEXT,
                    positive_prompt TEXT,
                    negative_prompt TEXT,
                    visual_plan JSONB,
                    content_seed JSONB,
                    metadata JSONB,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_run_id ON posts(run_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)")

            conn.commit()
            print("[OK] Database tables created successfully")

        finally:
            cursor.close()
            conn.close()

    def save_run(
        self,
        run_id: str,
        trend_text: str,
        persona_name: str,
        num_posts: int,
        metadata: Optional[Dict] = None,
        adapted_idea: Optional[Dict] = None,
        trend_profile: Optional[Dict] = None
    ) -> str:
        """
        Save a new run to the database.

        Args:
            run_id: Unique run identifier
            trend_text: The trend description/input
            persona_name: Name of the persona used
            num_posts: Number of posts generated
            metadata: Additional metadata (workflow settings, etc.)
            adapted_idea: The creative concept (JSONB) - optional
            trend_profile: Trend analysis (JSONB) - optional

        Returns:
            The run_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = int(time.time())

            query = """
                INSERT INTO runs (id, persona_name, trend_text, num_posts, adapted_idea, trend_profile, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    persona_name = EXCLUDED.persona_name,
                    trend_text = EXCLUDED.trend_text,
                    num_posts = EXCLUDED.num_posts,
                    adapted_idea = EXCLUDED.adapted_idea,
                    trend_profile = EXCLUDED.trend_profile,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """

            cursor.execute(query, (
                run_id,
                persona_name,
                trend_text,
                num_posts,
                Json(adapted_idea) if adapted_idea else None,
                Json(trend_profile) if trend_profile else None,
                Json(metadata) if metadata else None,
                now,
                now
            ))

            conn.commit()
            return run_id

        finally:
            cursor.close()
            conn.close()

    def save_post(
        self,
        post_id: str,
        run_id: str,
        post_index: int,
        caption: str,
        hashtags: List[str],
        image_url: Optional[str] = None,
        image_prompt: Optional[str] = None,
        cta: Optional[str] = None,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        visual_plan: Optional[Dict] = None,
        content_seed: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save a post to the database.

        Args:
            post_id: Unique post identifier
            run_id: ID of the parent run
            post_index: Index/position of post in the campaign
            caption: Post caption text
            hashtags: List of hashtags
            image_url: Public URL of the generated image (GCS or HTTP)
            image_prompt: The image generation prompt text
            cta: Call to action text
            positive_prompt: Positive image generation prompt (legacy)
            negative_prompt: Negative image generation prompt (legacy)
            visual_plan: Visual planning data (JSONB)
            content_seed: Content seed data (JSONB)
            metadata: Additional metadata (tier, category, etc.)

        Returns:
            The post_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = int(time.time())

            query = """
                INSERT INTO posts
                (id, run_id, post_index, caption, hashtags, cta, image_url, image_prompt,
                 positive_prompt, negative_prompt, visual_plan, content_seed, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    post_index = EXCLUDED.post_index,
                    caption = EXCLUDED.caption,
                    hashtags = EXCLUDED.hashtags,
                    cta = EXCLUDED.cta,
                    image_url = EXCLUDED.image_url,
                    image_prompt = EXCLUDED.image_prompt,
                    positive_prompt = EXCLUDED.positive_prompt,
                    negative_prompt = EXCLUDED.negative_prompt,
                    visual_plan = EXCLUDED.visual_plan,
                    content_seed = EXCLUDED.content_seed,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """

            cursor.execute(query, (
                post_id,
                run_id,
                post_index,
                caption,
                hashtags,
                cta,
                image_url,
                image_prompt,
                positive_prompt,
                negative_prompt,
                Json(visual_plan) if visual_plan else None,
                Json(content_seed) if content_seed else None,
                Json(metadata) if metadata else None,
                now,
                now
            ))

            conn.commit()
            return post_id

        finally:
            cursor.close()
            conn.close()

    def update_post_image_link(self, post_id: str, image_url: str):
        """
        Update the image URL for a specific post.

        Args:
            post_id: Post identifier
            image_url: Public image URL (GCS or HTTP)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = """
                UPDATE posts
                SET image_url = %s, updated_at = %s
                WHERE id = %s
            """
            cursor.execute(query, (image_url, int(time.time()), post_id))
            conn.commit()

        finally:
            cursor.close()
            conn.close()

    def save_post_version(
        self,
        post_id: str,
        visual_plan: Optional[Dict] = None,
        image_prompt: Optional[str] = None,
        positive_prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        image_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Save a new version of an existing post.

        Args:
            post_id: Post identifier
            visual_plan: Visual planning data (JSONB)
            image_prompt: The image generation prompt text
            positive_prompt: Positive image generation prompt
            negative_prompt: Negative image generation prompt
            image_url: Public URL of the generated image
            metadata: Additional metadata for this version

        Returns:
            Dict with version information
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = int(time.time())
            
            # First, get current versions to determine next version number
            cursor.execute("SELECT versions, current_version FROM posts WHERE id = %s", (post_id,))
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"Post {post_id} not found")
            
            current_versions = result[0] or []
            current_version_num = result[1] or 1
            
            # Determine next version number
            next_version = len(current_versions) + 1
            
            # Create new version object
            new_version = {
                "version": next_version,
                "created_at": now,
                "visual_plan": visual_plan,
                "image_prompt": image_prompt,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "image_url": image_url,
                "metadata": metadata or {},
                "is_current": True
            }
            
            # Mark all existing versions as not current
            for version in current_versions:
                version["is_current"] = False
            
            # Add new version to the list
            updated_versions = current_versions + [new_version]
            
            # Update the post with new versions array and current version
            query = """
                UPDATE posts 
                SET versions = %s, 
                    current_version = %s, 
                    image_url = %s,
                    visual_plan = %s,
                    image_prompt = %s,
                    positive_prompt = %s,
                    negative_prompt = %s,
                    updated_at = %s
                WHERE id = %s
            """
            
            cursor.execute(query, (
                Json(updated_versions),
                next_version,
                image_url,
                Json(visual_plan) if visual_plan else None,
                image_prompt,
                positive_prompt,
                negative_prompt,
                now,
                post_id
            ))
            
            conn.commit()
            
            return {
                "version": next_version,
                "created_at": now,
                "image_url": image_url,
                "is_current": True
            }

        finally:
            cursor.close()
            conn.close()

    def get_post_versions(self, post_id: str) -> List[Dict]:
        """
        Get all versions of a post.

        Args:
            post_id: Post identifier

        Returns:
            List of version dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query = "SELECT versions, current_version FROM posts WHERE id = %s"
            cursor.execute(query, (post_id,))
            row = cursor.fetchone()
            
            if not row:
                return []
            
            versions = row['versions'] or []
            current_version = row['current_version'] or 1
            
            # Ensure is_current flag is set correctly
            for version in versions:
                version['is_current'] = version.get('version') == current_version
                
            return sorted(versions, key=lambda x: x.get('version', 0))

        finally:
            cursor.close()
            conn.close()

    def set_current_version(self, post_id: str, version_number: int) -> bool:
        """
        Set which version is the current/active one.

        Args:
            post_id: Post identifier
            version_number: Version number to make current

        Returns:
            True if successful, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get current versions
            cursor.execute("SELECT versions FROM posts WHERE id = %s", (post_id,))
            result = cursor.fetchone()
            
            if not result:
                return False
            
            versions = result[0] or []
            
            # Find the target version and update current status
            target_version_data = None
            for version in versions:
                if version.get('version') == version_number:
                    version['is_current'] = True
                    target_version_data = version
                else:
                    version['is_current'] = False
            
            if not target_version_data:
                return False
            
            # Update the post with new current version data
            query = """
                UPDATE posts 
                SET versions = %s, 
                    current_version = %s,
                    image_url = %s,
                    visual_plan = %s,
                    image_prompt = %s,
                    positive_prompt = %s,
                    negative_prompt = %s,
                    updated_at = %s
                WHERE id = %s
            """
            
            cursor.execute(query, (
                Json(versions),
                version_number,
                target_version_data.get('image_url'),
                Json(target_version_data.get('visual_plan')),
                target_version_data.get('image_prompt'),
                target_version_data.get('positive_prompt'),
                target_version_data.get('negative_prompt'),
                int(time.time()),
                post_id
            ))
            
            conn.commit()
            return cursor.rowcount > 0

        finally:
            cursor.close()
            conn.close()

    def get_post_by_id(self, post_id: str) -> Optional[Dict]:
        """
        Get a post by its ID.

        Args:
            post_id: Post identifier

        Returns:
            Post data dict or None
        """
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query = "SELECT * FROM posts WHERE id = %s"
            cursor.execute(query, (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

        finally:
            cursor.close()
            conn.close()

    def get_run(self, run_id: str) -> Optional[Dict]:
        """
        Get a run by ID.

        Args:
            run_id: Run identifier

        Returns:
            Run data dict or None
        """
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query = "SELECT * FROM runs WHERE id = %s"
            cursor.execute(query, (run_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

        finally:
            cursor.close()
            conn.close()

    def get_posts_by_run(self, run_id: str) -> List[Dict]:
        """
        Get all posts for a specific run.

        Args:
            run_id: Run identifier

        Returns:
            List of post dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query = "SELECT * FROM posts WHERE run_id = %s ORDER BY created_at ASC"
            cursor.execute(query, (run_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        finally:
            cursor.close()
            conn.close()

    def get_run_with_posts(self, run_id: str) -> Optional[Dict]:
        """
        Get a run with all its posts.

        Args:
            run_id: Run identifier

        Returns:
            Dict with run data and posts list
        """
        run = self.get_run(run_id)
        if not run:
            return None

        posts = self.get_posts_by_run(run_id)
        run['posts'] = posts
        return run

    def list_runs(self, limit: int = 100) -> List[Dict]:
        """
        List all runs.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of run dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            query = """
                SELECT r.*, COUNT(p.id) as post_count
                FROM runs r
                LEFT JOIN posts p ON r.id = p.run_id
                GROUP BY r.id
                ORDER BY r.created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        finally:
            cursor.close()
            conn.close()

    def get_all_runs(self, limit: int = 100) -> List[Dict]:
        """
        Get all runs with their basic information.
        Alias for list_runs() for backward compatibility.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of run dicts with keys: run_id (alias for id), trend_text, persona_name, num_posts, created_at, metadata
        """
        runs = self.list_runs(limit)
        # Add run_id alias for backward compatibility
        for run in runs:
            if 'id' in run:
                run['run_id'] = run['id']
        return runs

    def delete_run(self, run_id: str):
        """Delete a run and all its posts (CASCADE)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = "DELETE FROM runs WHERE id = %s"
            cursor.execute(query, (run_id,))
            conn.commit()

        finally:
            cursor.close()
            conn.close()


# Singleton instance
_runs_posts_storage = None


def get_runs_posts_storage() -> RunsPostsStorage:
    """Get singleton instance of RunsPostsStorage."""
    global _runs_posts_storage

    if _runs_posts_storage is None:
        _runs_posts_storage = RunsPostsStorage()
        # Create tables if they don't exist
        try:
            _runs_posts_storage.create_tables()
        except Exception as e:
            print(f"[WARNING] Could not create tables: {e}")

    return _runs_posts_storage
