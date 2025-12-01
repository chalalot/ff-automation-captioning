"""Database storage adapters for Google Cloud SQL."""

from .runs_posts_storage import RunsPostsStorage, get_runs_posts_storage

# Provide backward compatibility alias
get_storage = get_runs_posts_storage

__all__ = ["RunsPostsStorage", "get_runs_posts_storage", "get_storage"]
