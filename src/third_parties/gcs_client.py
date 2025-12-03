"""
Google Cloud Storage Client for KOL Agent Image Management

Provides structured image upload and organization for marketing campaigns using
the folder structure: /comfy_ui/run_{product_name}_{kol_persona}_{datetime}/

Features:
- Campaign run-based folder organization
- Product and persona metadata integration
- Public URL generation for immediate access
- Sanitized folder naming for filesystem safety
- Sequential image numbering within runs
"""

import os
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

try:
    from google.cloud import storage
except ImportError:
    raise ImportError(
        "google-cloud-storage package is required. Install with: pip install google-cloud-storage"
    )

from src.config import GlobalConfig

# Set up logging
logger = logging.getLogger(__name__)

# GCS configuration from GlobalConfig
GCS_BUCKET_NAME = GlobalConfig.GCS_BUCKET_NAME
GCS_CREDENTIALS_PATH = GlobalConfig.GCS_CREDENTIALS_PATH
GCS_PUBLIC_BASE_URL = GlobalConfig.GCS_PUBLIC_BASE_URL
GCS_CREDENTIALS_JSON = getattr(GlobalConfig, 'GCS_CREDENTIALS_JSON', None)


class GCSClientError(Exception):
    """Base exception for GCS client errors."""
    pass


class GCSUploadError(GCSClientError):
    """Raised when GCS upload fails."""
    pass


def _sanitize_name(name: str) -> str:
    """
    Sanitize names for safe use in GCS folder paths.

    Args:
        name: Raw name to sanitize

    Returns:
        Sanitized name safe for filesystem use
    """
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized or 'unknown'


def generate_run_id(
    product_name: str,
    kol_persona: str,
    timestamp: Optional[str] = None
) -> str:
    """
    Generate a structured run ID for campaign organization.

    Args:
        product_name: Name of the product being marketed
        kol_persona: KOL/persona type (e.g., 'tech_reviewer', 'beauty_influencer')
        timestamp: Optional timestamp (defaults to current time)

    Returns:
        Formatted run ID: run_{product}_{persona}_{timestamp}
    """
    timestamp = timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')

    safe_product = _sanitize_name(product_name)
    safe_persona = _sanitize_name(kol_persona)

    return f"run_{safe_product}_{safe_persona}_{timestamp}"


def generate_image_filename(image_type: str, sequence: int = 1) -> str:
    """
    Generate standardized image filename with unique identifier.

    Args:
        image_type: Type of image (e.g., 'product_showcase', 'social_media')
        sequence: Sequential number within the run (used for uniqueness)

    Returns:
        Formatted filename: {image_type}_{timestamp}_{sequence}.png
    """
    import time
    safe_type = _sanitize_name(image_type)
    # Use timestamp in milliseconds + sequence for guaranteed uniqueness
    timestamp_ms = int(time.time() * 1000)
    return f"{safe_type}_{timestamp_ms}_{sequence}.png"


def generate_gcs_path(
    run_id: str,
    image_type: str,
    sequence: int = 1
) -> str:
    """
    Generate complete GCS path for an image.

    Args:
        run_id: Campaign run ID
        image_type: Type of image being generated
        sequence: Sequential number within the run

    Returns:
        Complete GCS path: comfy_ui/{run_id}/{filename}
    """
    filename = generate_image_filename(image_type, sequence)
    return f"comfy_ui/{run_id}/{filename}"


def get_public_url(gcs_path: str, bucket_name: str = GCS_BUCKET_NAME) -> str:
    """
    Generate public URL for a GCS object.

    Args:
        gcs_path: Path to the object in GCS
        bucket_name: GCS bucket name

    Returns:
        Public URL for the object
    """
    return f"https://storage.googleapis.com/{bucket_name}/{gcs_path}"


def generate_signed_url(
    gcs_path: str,
    bucket_name: str = GCS_BUCKET_NAME,
    expiration_minutes: int = 60
) -> str:
    """
    Generate a signed URL for a GCS object.
    
    Args:
        gcs_path: Path to the object in GCS
        bucket_name: GCS bucket name
        expiration_minutes: URL expiration time in minutes
        
    Returns:
        Signed URL if successful, else Public URL
    """
    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET"
        )
    except Exception as e:
        logger.warning(f"Failed to generate signed URL for {gcs_path}, falling back to public URL: {e}")
        return get_public_url(gcs_path, bucket_name)


def _get_gcs_client() -> storage.Client:
    """
    Initialize and return GCS client with credentials.

    Returns:
        Authenticated GCS client

    Raises:
        GCSClientError: If client initialization fails
    """
    try:
        logger.debug(f"[GCS] Initializing client...")
        logger.debug(f"[GCS] Bucket: {GCS_BUCKET_NAME}")

        # Priority 1: Check for GCS_CREDENTIALS_JSON (from Streamlit secrets or env var)
        if GCS_CREDENTIALS_JSON:
            logger.debug("[GCS] Using GCS_CREDENTIALS_JSON for authentication")
            try:
                import json
                from google.oauth2 import service_account

                # Parse JSON string to dict
                credentials_dict = json.loads(GCS_CREDENTIALS_JSON)
                credentials = service_account.Credentials.from_service_account_info(credentials_dict)
                client = storage.Client(credentials=credentials)
                logger.info(f"[GCS] Client initialized with GCS_CREDENTIALS_JSON for project: {client.project}")
                return client
            except json.JSONDecodeError as e:
                logger.error(f"[GCS] Failed to parse GCS_CREDENTIALS_JSON: {e}")
                # Continue to next authentication method

        # Priority 2: Check if running in Streamlit Cloud with gcp_service_account dict
        try:
            import streamlit as st
            if hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
                logger.debug("[GCS] Using Streamlit gcp_service_account secrets for authentication")
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"]
                )
                client = storage.Client(credentials=credentials)
                logger.info(f"[GCS] Client initialized with Streamlit gcp_service_account for project: {client.project}")
                return client
        except ImportError:
            pass  # Streamlit not available, continue with file-based auth
        except Exception as e:
            logger.debug(f"[GCS] Streamlit gcp_service_account not available: {e}")

        # Priority 3: Fall back to file-based credentials
        logger.debug(f"[GCS] Attempting file-based authentication")
        logger.debug(f"[GCS] Credentials path: {GCS_CREDENTIALS_PATH}")

        # Set credentials environment variable if not already set
        if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            if GCS_CREDENTIALS_PATH and Path(GCS_CREDENTIALS_PATH).exists():
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GCS_CREDENTIALS_PATH
                logger.debug(f"[GCS] Set GOOGLE_APPLICATION_CREDENTIALS={GCS_CREDENTIALS_PATH}")
            else:
                raise GCSClientError(f"Credentials file not found: {GCS_CREDENTIALS_PATH}")
        else:
            logger.debug(f"[GCS] Using existing GOOGLE_APPLICATION_CREDENTIALS={os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")

        client = storage.Client()
        logger.info(f"[GCS] Client initialized successfully for project: {client.project}")
        return client

    except Exception as e:
        logger.error(f"[GCS] Failed to initialize client: {type(e).__name__}: {e}")
        raise GCSClientError(f"Failed to initialize GCS client: {e}")


def upload_bytes_to_gcs(
    payload: bytes,
    gcs_path: str,
    *,
    content_type: str = "application/octet-stream",
    bucket_name: str = GCS_BUCKET_NAME,
) -> str:
    """Upload arbitrary bytes to GCS and return the public URL."""
    try:
        logger.info(f"[GCS] Starting upload...")
        logger.info(f"[GCS]   Path: {gcs_path}")
        logger.info(f"[GCS]   Bucket: {bucket_name}")
        logger.info(f"[GCS]   Size: {len(payload)} bytes")
        logger.info(f"[GCS]   Content-Type: {content_type}")

        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        logger.debug(f"[GCS] Bucket object created: {bucket.name}")

        blob = bucket.blob(gcs_path)
        logger.debug(f"[GCS] Blob object created: {blob.name}")

        logger.debug(f"[GCS] Uploading {len(payload)} bytes...")
        blob.upload_from_string(payload, content_type=content_type)
        logger.info(f"[GCS] ✓ Upload successful!")

        # Note: /comfy_ui folder has bucket-level public access configured
        # Individual blob ACL modification is not required
        logger.debug(f"[GCS] Using bucket-level public access (folder: comfy_ui)")

        public_url = get_public_url(gcs_path, bucket_name)

        logger.info(f"[GCS] ✓ Upload complete: {gcs_path}")
        logger.info(f"[GCS]   Public URL: {public_url}")

        return public_url

    except Exception as e:
        error_msg = f"Failed to upload image to GCS path '{gcs_path}': {type(e).__name__}: {e}"
        logger.error(f"[GCS] ✗ Upload failed: {error_msg}")
        raise GCSUploadError(error_msg)


def upload_image_to_gcs(
    image_bytes: bytes,
    gcs_path: str,
    content_type: str = "image/png",
    bucket_name: str = GCS_BUCKET_NAME
) -> str:
    """Upload image bytes to GCS and return public URL."""
    return upload_bytes_to_gcs(
        image_bytes,
        gcs_path,
        content_type=content_type,
        bucket_name=bucket_name,
    )


def upload_campaign_image(
    image_bytes: bytes,
    product_name: str,
    kol_persona: str,
    image_type: str,
    sequence: int = 1,
    timestamp: Optional[str] = None,
    run_id: Optional[str] = None,
    content_type: str = "image/png",
    bucket_name: str = GCS_BUCKET_NAME
) -> Tuple[str, str, str]:
    """
    Upload campaign image with structured organization.

    Args:
        image_bytes: Image data as bytes
        product_name: Product being marketed
        kol_persona: KOL/persona type
        image_type: Type of image (product_showcase, social_media, etc.)
        sequence: Sequential number within the run
        timestamp: Optional timestamp for run ID
        run_id: Optional explicit run ID (overrides generation)
        content_type: MIME type of the image
        bucket_name: GCS bucket name

    Returns:
        Tuple of (public_url, gcs_path, run_id)

    Raises:
        GCSUploadError: If upload fails
    """
    try:
        # Generate or use provided run ID
        if not run_id:
            run_id = generate_run_id(product_name, kol_persona, timestamp)

        # Generate GCS path
        gcs_path = generate_gcs_path(run_id, image_type, sequence)

        # Upload image
        public_url = upload_image_to_gcs(
            image_bytes,
            gcs_path,
            content_type,
            bucket_name
        )

        logger.info(f"Campaign image uploaded successfully")
        logger.debug(f"Run ID: {run_id}")
        logger.debug(f"GCS Path: {gcs_path}")
        logger.debug(f"Public URL: {public_url}")

        return public_url, gcs_path, run_id

    except Exception as e:
        error_msg = f"Failed to upload campaign image: {e}"
        logger.error(error_msg)
        raise GCSUploadError(error_msg)


def list_gcs_images(
    prefix: str = "",
    bucket_name: str = GCS_BUCKET_NAME
) -> list:
    """
    List all images in a specific GCS folder prefix.

    Args:
        prefix: Folder prefix (e.g., 'comfy_ui/', 'Trung/')
        bucket_name: GCS bucket name

    Returns:
        List of dicts with blob metadata: {
            'name': str,           # Full path
            'public_url': str,     # Public URL
            'size': int,           # Size in bytes
            'updated': datetime,   # Last updated timestamp
            'content_type': str    # MIME type
        }

    Raises:
        GCSClientError: If listing fails
    """
    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)

        blobs = bucket.list_blobs(prefix=prefix)

        images = []
        for blob in blobs:
            # Skip directory markers
            if blob.name.endswith('/'):
                continue

            # Generate signed URL for each image
            try:
                signed_url = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(minutes=60),
                    method="GET"
                )
            except Exception as e:
                logger.warning(f"Failed to generate signed URL for {blob.name}: {e}")
                signed_url = get_public_url(blob.name, bucket_name)

            images.append({
                'name': blob.name,
                'public_url': get_public_url(blob.name, bucket_name),
                'signed_url': signed_url,
                'size': blob.size,
                'updated': blob.updated,
                'content_type': blob.content_type or 'unknown'
            })

        logger.debug(f"Found {len(images)} images in prefix '{prefix}'")
        return images

    except Exception as e:
        error_msg = f"Failed to list images with prefix '{prefix}': {e}"
        logger.error(error_msg)
        raise GCSClientError(error_msg)


def list_campaign_images(
    run_id: str,
    bucket_name: str = GCS_BUCKET_NAME
) -> list:
    """
    List all images in a campaign run folder.

    Args:
        run_id: Campaign run ID
        bucket_name: GCS bucket name

    Returns:
        List of blob names in the run folder

    Raises:
        GCSClientError: If listing fails
    """
    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)

        prefix = f"comfy_ui/{run_id}/"
        blobs = list(bucket.list_blobs(prefix=prefix))

        image_paths = [blob.name for blob in blobs if blob.name != prefix]

        logger.debug(f"Found {len(image_paths)} images in run {run_id}")
        return image_paths

    except Exception as e:
        error_msg = f"Failed to list campaign images for run '{run_id}': {e}"
        logger.error(error_msg)
        raise GCSClientError(error_msg)


def list_all_comfy_ui_images(bucket_name: str = GCS_BUCKET_NAME) -> list:
    """
    List all publicly published images in the /comfy_ui folder.

    Args:
        bucket_name: GCS bucket name

    Returns:
        List of dicts with blob metadata: {
            'name': str,           # Full path
            'public_url': str,     # Public URL
            'size': int,           # Size in bytes
            'updated': datetime,   # Last updated timestamp
            'content_type': str    # MIME type
        }

    Raises:
        GCSClientError: If listing fails
    """
    try:
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)

        prefix = "comfy_ui/"
        blobs = bucket.list_blobs(prefix=prefix)

        images = []
        for blob in blobs:
            # Skip directory markers
            if blob.name.endswith('/'):
                continue

            images.append({
                'name': blob.name,
                'public_url': get_public_url(blob.name, bucket_name),
                'size': blob.size,
                'updated': blob.updated,
                'content_type': blob.content_type or 'unknown'
            })

        logger.debug(f"Found {len(images)} images in comfy_ui folder")
        return images

    except Exception as e:
        error_msg = f"Failed to list all comfy_ui images: {e}"
        logger.error(error_msg)
        raise GCSClientError(error_msg)


def get_next_sequence_number(
    run_id: str,
    image_type: str,
    bucket_name: str = GCS_BUCKET_NAME
) -> int:
    """
    Get the next sequence number for an image type within a run.

    Args:
        run_id: Campaign run ID
        image_type: Type of image
        bucket_name: GCS bucket name

    Returns:
        Next available sequence number
    """
    try:
        existing_images = list_campaign_images(run_id, bucket_name)
        safe_type = _sanitize_name(image_type)

        # Find existing images of the same type
        type_pattern = f"comfy_ui/{run_id}/{safe_type}_"
        matching_images = [
            img for img in existing_images
            if img.startswith(type_pattern)
        ]

        if not matching_images:
            return 1

        # Extract sequence numbers and find the maximum
        max_sequence = 0
        for img_path in matching_images:
            try:
                # Extract sequence from filename like "product_showcase_{timestamp}_{seq}.png"
                filename = Path(img_path).name
                seq_part = filename.split('_')[-1].split('.')[0]  # Get sequence number from end
                sequence = int(seq_part)
                max_sequence = max(max_sequence, sequence)
            except (ValueError, IndexError):
                # Skip files that don't match expected pattern
                continue

        return max_sequence + 1

    except Exception as e:
        logger.warning(f"Failed to get next sequence number, defaulting to 1: {e}")
        return 1


# Convenience function for testing
def test_gcs_connection() -> bool:
    """
    Test GCS connection and bucket access.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        client = _get_gcs_client()
        bucket = client.bucket(GCS_BUCKET_NAME)

        # Try to list a few objects (minimal test)
        list(bucket.list_blobs(max_results=1))

        logger.info("GCS connection test successful")
        return True

    except Exception as e:
        logger.error(f"GCS connection test failed: {e}")
        return False
