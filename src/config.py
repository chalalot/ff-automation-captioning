import os
from dotenv import load_dotenv
import threading
import json
from pathlib import Path

load_dotenv()

# Try to import streamlit for secrets support
try:
    import streamlit as st
    _STREAMLIT_AVAILABLE = True
except ImportError:
    _STREAMLIT_AVAILABLE = False


class GlobalConfig:
    """Global configurations."""
    # DATABASE TYPE
    DB_TYPE = os.getenv("DB_TYPE", "postgres") # sqlite or postgres

    # PostgreSQL specific (if DB_TYPE is postgres)
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost") # For docker-compose, this will be service name e.g., 'postgres'
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "mkt_agent")

    # DATABASE URLs - constructed based on DB_TYPE
    if DB_TYPE == "postgres":
        DB_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        ASYNC_DB_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    else: # Default to SQLite
        DB_URL = os.getenv("DB_URL", "sqlite:///./database/content.db")
        ASYNC_DB_URL = DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

    IS_ECHO_QUERY = bool(os.getenv("IS_ECHO_QUERY", False))
    
    # SQLite specific settings (only relevant if DB_TYPE is sqlite) - These will not be used if DB_TYPE is postgres
    SQLITE_TIMEOUT = int(os.getenv("SQLITE_TIMEOUT", "30"))  # in seconds
    SQLITE_BUSY_TIMEOUT = int(os.getenv("SQLITE_BUSY_TIMEOUT", "120000"))  # 120 seconds in milliseconds
    
    # Thread local storage for connection reuse (might be less relevant for async/PostgreSQL)
    DB_CONNECTION_LOCAL = threading.local()

    # OPENAI 
    OPENAI_API_BASE = os.getenv("OPENAI_BASE_URL")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # GROK (xAI)
    GROK_API_KEY = os.getenv("GROK_API_KEY")

    # GEMINI (Google)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # API 
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))

    # API Base URL 
    API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")

    # DEBUGGING FLAG 
    # DEBUG = bool(os.getenv("DEBUG", 0))
    DEBUG = False  

    # RunwayML 
    RUNWAY_API_KEY = os.getenv("RUNWAYML_API_SECRET", None)

    # EMAIL SETTINGS (SendGrid)
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    MAIL_FROM = os.getenv("MAIL_FROM")

    # JinaAI API
    JINA_API_KEY = os.getenv("JINA_API_KEY")
    JINA_API_URL = os.getenv("JINA_API_URL", "https://s.jina.ai/")

    # Auto Image URL Parsing Feature
    IS_ENABLE_PARSE_IMAGE_URL = bool(os.getenv("ENABLE_AUTO_IMAGE_URL_PARSING", "1") == "1")

    # DeerFlow API Settings
    DEERFLOW_API_URL = os.getenv("DEERFLOW_API_URL")
    DEERFLOW_API_TIMEOUT = int(os.getenv("DEERFLOW_API_TIMEOUT", "300"))
    DEERFLOW_POLL_INTERVAL = int(os.getenv("DEERFLOW_POLL_INTERVAL", "5"))
    DEERFLOW_MAX_POLL_TIME = int(os.getenv("DEERFLOW_MAX_POLL_TIME", "1800"))
    DEERFLOW_MAX_RETRIES = int(os.getenv("DEERFLOW_MAX_RETRIES", "3"))

    # ComfyUI API Settings
    COMFYUI_API_URL = os.getenv("COMFYUI_API_URL", "https://comfy-api.ez-agi.com")
    COMFY_LOCAL_API_URL = os.getenv("COMFY_LOCAL_API_URL", "http://127.0.0.1:8188")
    CLOUD_COMFY_API_URL = os.getenv("CLOUD_COMFY_API_URL", "https://api.comfy.org/api/v1")
    COMFYUI_API_KEY = os.getenv("COMFYUI_API_KEY")
    COMFYUI_API_TIMEOUT = int(os.getenv("COMFYUI_API_TIMEOUT", "1000"))  # Request timeout (httpx client timeout)
    COMFYUI_POLL_INTERVAL = int(os.getenv("COMFYUI_POLL_INTERVAL", "5"))  # Check status every 5 seconds
    COMFYUI_MAX_POLL_TIME = int(os.getenv("COMFYUI_MAX_POLL_TIME", "3600"))  # Max time to wait for completion (1 hour)
    COMFYUI_MAX_RETRIES = int(os.getenv("COMFYUI_MAX_RETRIES", "3"))

    # Kling AI
    KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY")
    KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY")

    # Google Cloud Storage (Image Storage)
    # Try Streamlit secrets first, then fall back to env vars
    _use_streamlit_secrets = False
    if _STREAMLIT_AVAILABLE:
        try:
            # Try to access secrets - this will raise an error if secrets file doesn't exist
            # Only use Streamlit secrets if we're actually in a Streamlit context
            if hasattr(st, 'secrets') and hasattr(st, 'runtime') and hasattr(st.runtime, 'exists'):
                if st.runtime.exists() and 'GCS_BUCKET_NAME' in st.secrets:
                    _use_streamlit_secrets = True
        except Exception:
            # Secrets file doesn't exist or can't be parsed, fall back to env vars
            pass

    if _use_streamlit_secrets:
        GCS_BUCKET_NAME = st.secrets["GCS_BUCKET_NAME"]
        GCS_PUBLIC_BASE_URL = st.secrets.get("GCS_PUBLIC_BASE_URL", f"https://storage.googleapis.com/{st.secrets['GCS_BUCKET_NAME']}")
        # For Streamlit, credentials come from GCS_CREDENTIALS (JSON string) or gcp_service_account (dict)
        GCS_CREDENTIALS_PATH = None  # Will use st.secrets["GCS_CREDENTIALS"] or st.secrets["gcp_service_account"]
        GCS_CREDENTIALS_JSON = st.secrets.get("GCS_CREDENTIALS")  # JSON string from secrets
    else:
        # Fall back to environment variables
        GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "soulie-gcp-bucket")
        GCS_CREDENTIALS_PATH = os.getenv("GCS_CREDENTIALS_PATH", "vincent-464803-ed8aaf9f590f.json")
        GCS_PUBLIC_BASE_URL = os.getenv("GCS_PUBLIC_BASE_URL", "https://storage.googleapis.com/soulie-gcp-bucket")
        GCS_CREDENTIALS_JSON = os.getenv("GCS_CREDENTIALS")  # JSON string from env var

    #S3
    AWS_URL = os.getenv("AWS_URL")
    # NOTE: this will be use for reconstruct the url of all the assets  
    # AWS_PUBLIC_URL = os.getenv("AWS_PUBLIC_URL", "https://sociai-minio.dopikai.com")
    AWS_PUBLIC_URL = "http://100.124.29.25:9900"
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "ap-southeast-1")
    AWS_BUCKET = os.getenv("AWS_BUCKET", "mkt-agent-public")


    # Storage Directories (Mounted Volumes)
    INPUT_DIR = os.getenv("INPUT_DIR", "Sorted")
    PROCESSED_DIR = os.getenv("PROCESSED_DIR", "processed")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "results")

    @classmethod
    def get_sqlite_connect_args(cls):
        """Get the connect_args for SQLite connections"""
        if cls.DB_TYPE == 'sqlite': # Check DB_TYPE
            return {
                "check_same_thread": False,
                "timeout": cls.SQLITE_TIMEOUT # Use the class attribute
            }
        return {}
