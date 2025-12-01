#!/usr/bin/env python3
"""
GCS Image Viewer - Streamlit UI for browsing Google Cloud Storage images

This provides a web interface to view all images stored in the ComfyUI GCS bucket.
Supports filtering, search, and detailed image metadata display.

Usage:
  streamlit run gcs_image_viewer.py
"""

import streamlit as st
from datetime import datetime
from pathlib import Path
import re
from typing import List, Dict, Optional

# Import GCS client
from src.third_parties.gcs_client import list_all_comfy_ui_images, GCSClientError
from src.config import GlobalConfig

# Page configuration
st.set_page_config(
    page_title="GCS Image Viewer",
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .header-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .image-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 15px;
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .image-card:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        transition: box-shadow 0.3s ease;
    }
    .metadata-text {
        font-size: 0.85em;
        color: #666;
        margin: 5px 0;
    }
    .stats-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


def parse_image_metadata(image_name: str) -> Dict[str, str]:
    """Extract metadata from image name/path."""
    # Expected format: comfy_ui/run_{product}_{persona}_{timestamp}/image_{type}_{seq}_{unique}.png
    metadata = {
        "product": "Unknown",
        "persona": "Unknown",
        "timestamp": "Unknown",
        "image_type": "Unknown",
        "sequence": "Unknown",
        "run_folder": "Unknown"
    }

    # Extract run folder
    parts = image_name.split('/')
    if len(parts) >= 2:
        run_folder = parts[1]
        metadata["run_folder"] = run_folder

        # Parse run folder: run_{product}_{persona}_{timestamp}
        if run_folder.startswith("run_"):
            run_parts = run_folder[4:].split('_')
            if len(run_parts) >= 3:
                # Last 2 parts are timestamp (YYYYMMDD_HHMMSS)
                metadata["timestamp"] = f"{run_parts[-2]}_{run_parts[-1]}"
                # Everything before timestamp is product and persona
                remaining = run_parts[:-2]
                if len(remaining) >= 2:
                    # Assume last before timestamp is persona
                    metadata["persona"] = remaining[-1]
                    metadata["product"] = "_".join(remaining[:-1])
                elif len(remaining) == 1:
                    metadata["product"] = remaining[0]

    # Extract image filename info
    filename = Path(image_name).name
    # image_{type}_{seq}_{unique}.png
    if filename.startswith("image_"):
        file_parts = filename[6:].split('_')
        if len(file_parts) >= 2:
            metadata["image_type"] = file_parts[0]
            metadata["sequence"] = file_parts[1]

    return metadata


def format_file_size(bytes_size: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def format_timestamp(dt: datetime) -> str:
    """Format datetime for display."""
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return "Unknown"


@st.cache_data(ttl=60)
def load_images() -> List[Dict]:
    """Load images from GCS with caching (60 second TTL)."""
    try:
        return list_all_comfy_ui_images()
    except GCSClientError as e:
        st.error(f"Failed to load images from GCS: {e}")
        return []
    except Exception as e:
        st.error(f"Unexpected error loading images: {e}")
        return []


def filter_images(
    images: List[Dict],
    search_query: str = "",
    persona_filter: Optional[str] = None,
    product_filter: Optional[str] = None,
    run_folder_filter: Optional[str] = None
) -> List[Dict]:
    """Filter images based on search and filter criteria."""
    filtered = images

    # Search query
    if search_query:
        query = search_query.lower()
        filtered = [
            img for img in filtered
            if query in img["name"].lower()
        ]

    # Persona filter
    if persona_filter and persona_filter != "All":
        filtered = [
            img for img in filtered
            if parse_image_metadata(img["name"])["persona"] == persona_filter
        ]

    # Product filter
    if product_filter and product_filter != "All":
        filtered = [
            img for img in filtered
            if parse_image_metadata(img["name"])["product"] == product_filter
        ]

    # Run folder filter
    if run_folder_filter and run_folder_filter != "All":
        filtered = [
            img for img in filtered
            if parse_image_metadata(img["name"])["run_folder"] == run_folder_filter
        ]

    return filtered


def main():
    # Header
    st.markdown("""
    <div class="header-section">
        <h1>🖼️ GCS Image Viewer</h1>
        <p>Browse and manage images stored in Google Cloud Storage</p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar - Filters and Settings
    with st.sidebar:
        st.header("⚙️ Settings")

        # Bucket info
        st.info(f"**Bucket**: {GlobalConfig.GCS_BUCKET_NAME}")

        # Refresh button
        if st.button("🔄 Refresh Images", width='stretch'):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.header("🔍 Filters")

        # Search
        search_query = st.text_input(
            "Search",
            placeholder="Search by filename, path...",
            help="Search in image names and paths"
        )

        # Load images
        with st.spinner("Loading images from GCS..."):
            all_images = load_images()

        if not all_images:
            st.warning("No images found")
            return

        # Extract unique values for filters
        all_metadata = [parse_image_metadata(img["name"]) for img in all_images]
        unique_personas = sorted(set(m["persona"] for m in all_metadata))
        unique_products = sorted(set(m["product"] for m in all_metadata))
        unique_runs = sorted(set(m["run_folder"] for m in all_metadata), reverse=True)

        # Persona filter
        persona_filter = st.selectbox(
            "Persona",
            options=["All"] + unique_personas,
            help="Filter by persona/KOL"
        )

        # Product filter
        product_filter = st.selectbox(
            "Product",
            options=["All"] + unique_products,
            help="Filter by product name"
        )

        # Run folder filter
        run_folder_filter = st.selectbox(
            "Run Folder",
            options=["All"] + unique_runs,
            help="Filter by campaign run"
        )

        st.markdown("---")
        st.header("📊 Display Options")

        # Grid columns
        grid_columns = st.slider(
            "Grid Columns",
            min_value=1,
            max_value=6,
            value=3,
            help="Number of columns in the image grid"
        )

        # Sort order
        sort_by = st.selectbox(
            "Sort By",
            options=["Newest First", "Oldest First", "Name (A-Z)", "Name (Z-A)", "Size (Large→Small)", "Size (Small→Large)"],
            help="Sort order for images"
        )

    # Apply filters
    filtered_images = filter_images(
        all_images,
        search_query,
        persona_filter,
        product_filter,
        run_folder_filter
    )

    # Sort images
    if sort_by == "Newest First":
        filtered_images.sort(key=lambda x: x["updated"], reverse=True)
    elif sort_by == "Oldest First":
        filtered_images.sort(key=lambda x: x["updated"])
    elif sort_by == "Name (A-Z)":
        filtered_images.sort(key=lambda x: x["name"])
    elif sort_by == "Name (Z-A)":
        filtered_images.sort(key=lambda x: x["name"], reverse=True)
    elif sort_by == "Size (Large→Small)":
        filtered_images.sort(key=lambda x: x["size"], reverse=True)
    elif sort_by == "Size (Small→Large)":
        filtered_images.sort(key=lambda x: x["size"])

    # Statistics
    st.markdown("### 📊 Statistics")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="stats-card">
            <h3>{len(all_images)}</h3>
            <p>Total Images</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stats-card">
            <h3>{len(filtered_images)}</h3>
            <p>Filtered</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        total_size = sum(img["size"] for img in all_images)
        st.markdown(f"""
        <div class="stats-card">
            <h3>{format_file_size(total_size)}</h3>
            <p>Total Size</p>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="stats-card">
            <h3>{len(unique_runs)}</h3>
            <p>Campaign Runs</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Display images in grid
    if not filtered_images:
        st.info("No images match your filters")
        return

    st.markdown(f"### 🖼️ Images ({len(filtered_images)})")

    # Create grid
    cols_per_row = grid_columns
    for i in range(0, len(filtered_images), cols_per_row):
        cols = st.columns(cols_per_row)

        for col_idx, col in enumerate(cols):
            img_idx = i + col_idx
            if img_idx >= len(filtered_images):
                break

            img = filtered_images[img_idx]
            metadata = parse_image_metadata(img["name"])

            with col:
                with st.container():
                    # Display image
                    st.image(
                        img["public_url"],
                        width='stretch',
                        caption=f"{metadata['persona']} - {metadata['product']}"
                    )

                    # Metadata in expander
                    with st.expander("ℹ️ Details"):
                        st.markdown(f"""
                        **Persona**: {metadata['persona']}
                        **Product**: {metadata['product']}
                        **Run**: `{metadata['run_folder']}`
                        **Type**: {metadata['image_type']}
                        **Size**: {format_file_size(img['size'])}
                        **Updated**: {format_timestamp(img['updated'])}
                        **Path**: `{img['name']}`
                        """)

                        # Copy URL button
                        st.code(img["public_url"], language=None)
                        if st.button("📋 Copy URL", key=f"copy_{img_idx}"):
                            st.write("URL copied! (use browser extension for actual clipboard)")


if __name__ == "__main__":
    main()
