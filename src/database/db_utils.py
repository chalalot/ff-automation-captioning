"""
Database connection utilities.
Handles building connection strings from environment variables.
"""
import os
from typing import Optional


def get_postgres_connection_string(
    connection_string: Optional[str] = None,
    mask_password: bool = False
) -> str:
    """
    Get PostgreSQL connection string from environment variables.

    Priority:
    1. Explicit connection_string parameter
    2. DATABASE_URL environment variable
    3. Build from DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

    Args:
        connection_string: Optional explicit connection string
        mask_password: If True, return masked version for logging

    Returns:
        PostgreSQL connection string

    Raises:
        ValueError: If no valid database configuration found
    """
    # Priority 1: Explicit parameter
    if connection_string:
        if mask_password:
            return _mask_connection_string(connection_string)
        return connection_string

    # Priority 2: DATABASE_URL env var
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if mask_password:
            return _mask_connection_string(db_url)
        return db_url

    # Priority 3: Build from components
    print(f"[DEBUG] DB_HOST from env: '{os.getenv('DB_HOST')}'")
    print(f"[DEBUG] POSTGRES_HOST from env: '{os.getenv('POSTGRES_HOST')}'")
    print(f"[DEBUG] DATABASE_URL from env: '{os.getenv('DATABASE_URL')}'")
    
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    # Validate required components
    missing = []
    if not db_host:
        missing.append("DB_HOST")
    if not db_user:
        missing.append("DB_USER")
    if not db_password:
        missing.append("DB_PASSWORD")
    if not db_name:
        missing.append("DB_NAME")

    if missing:
        raise ValueError(
            f"Database configuration incomplete. Missing: {', '.join(missing)}\n"
            "Set either:\n"
            "  1. DATABASE_URL environment variable, OR\n"
            "  2. DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME environment variables"
        )

    # Determine SSL mode based on environment
    ssl_mode = os.getenv("DB_SSL_MODE")
    if not ssl_mode:
        # Auto-detect: disable SSL for localhost, require for remote
        if db_host in ("localhost", "127.0.0.1"):
            ssl_mode = "disable"
        else:
            ssl_mode = "require"

    # Build connection string
    if mask_password:
        return f"postgresql://{db_user}:***@{db_host}:{db_port}/{db_name}?sslmode={ssl_mode}"
    else:
        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?sslmode={ssl_mode}"


def _mask_connection_string(connection_string: str) -> str:
    """
    Mask password in connection string for safe logging.

    Args:
        connection_string: Full connection string with password

    Returns:
        Connection string with password replaced by ***
    """
    # Handle postgresql://user:password@host:port/db format
    if "://" in connection_string and "@" in connection_string:
        try:
            protocol_part, rest = connection_string.split("://", 1)
            if "@" in rest:
                creds_part, host_part = rest.split("@", 1)
                if ":" in creds_part:
                    user, _ = creds_part.split(":", 1)
                    return f"{protocol_part}://{user}:***@{host_part}"
        except Exception:
            # If parsing fails, return generic mask
            return "postgresql://***:***@***:***/***"

    return connection_string


def get_db_config() -> dict:
    """
    Get database configuration as a dictionary.
    Useful for debugging and logging.

    Returns:
        Dictionary with database configuration (password masked)
    """
    config = {
        "db_host": os.getenv("DB_HOST", "not set"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "not set"),
        "db_password": "***" if os.getenv("DB_PASSWORD") else "not set",
        "db_name": os.getenv("DB_NAME", "not set"),
        "database_url": "set" if os.getenv("DATABASE_URL") else "not set",
        "connection_string": get_postgres_connection_string(mask_password=True) if _has_db_config() else "not configured"
    }
    return config


def _has_db_config() -> bool:
    """Check if database configuration is available."""
    try:
        get_postgres_connection_string()
        return True
    except ValueError:
        return False


def validate_db_connection():
    """
    Validate database connection by attempting to connect.

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        import psycopg2
    except ImportError:
        return False, "psycopg2-binary is not installed. Run: pip install psycopg2-binary"

    try:
        connection_string = get_postgres_connection_string()
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return True, f"Connection successful! PostgreSQL version: {version}"
    except ValueError as e:
        return False, f"Configuration error: {e}"
    except Exception as e:
        return False, f"Connection failed: {e}"


if __name__ == "__main__":
    """Quick test of database connection utilities."""
    print("Database Configuration:")
    print("-" * 60)

    config = get_db_config()
    for key, value in config.items():
        print(f"  {key}: {value}")

    print("\nTesting connection...")
    print("-" * 60)
    success, message = validate_db_connection()

    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
