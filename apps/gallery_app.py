import streamlit as st
import os
import sys
import asyncio
import json
import zipfile
import io
import pandas as pd
import math
from datetime import datetime
from PIL import Image

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.database.image_logs_storage import ImageLogsStorage
from src.third_parties.comfyui_client import ComfyUIClient
from src.utils.streamlit_utils import get_sorted_images, fetch_remote_metadata

# Page Config
st.set_page_config(page_title="Gallery - CrewAI Image Workflow", layout="wide")

st.title("🗂️ Results Gallery")

# Constants
OUTPUT_DIR = GlobalConfig.OUTPUT_DIR
storage = ImageLogsStorage()
client = ComfyUIClient()

# Session State Initialization
if "results" not in st.session_state:
    st.session_state.results = []

st.header(f"Results Gallery ({OUTPUT_DIR})")

# --- Helper Functions ---
@st.cache_data(ttl=30, show_spinner="Loading gallery data...")
def load_gallery_data(output_dir):
    """
    Fetch DB records and file list, then merge them.
    Cached to prevent lag on every interaction.
    """
    # 1. Fetch all completed executions for metadata lookup
    all_executions = storage.get_all_completed_executions()
    execution_map = {}
    for exc in all_executions:
        if exc['result_image_path']:
            # Normalize to filename
            fname = os.path.basename(exc['result_image_path'])
            execution_map[fname] = exc
    
    # 2. List files and build data list
    all_files = get_sorted_images(output_dir)
    
    items = []
    for f in all_files:
        full_path = os.path.join(output_dir, f)
        mtime = os.path.getmtime(full_path)
        dt = datetime.fromtimestamp(mtime)
        date_str = dt.strftime("%Y-%m-%d")
        
        # Get Metadata
        record = execution_map.get(f)
        persona = record['persona'] if record and 'persona' in record and record['persona'] else "Unknown"
        
        # Pre-calculate Reference Image Path (Heavy I/O)
        final_ref_path = None
        if record:
            ref_path = record.get('image_ref_path')
            if ref_path:
                if os.path.exists(ref_path):
                    final_ref_path = ref_path
                else:
                    # Fix Windows paths when running in Linux container
                    fixed_path = ref_path.replace('\\', '/')
                    if os.path.exists(fixed_path):
                        final_ref_path = fixed_path
                    else:
                        # Fallback: Check if file exists in PROCESSED_DIR by filename
                        filename = os.path.basename(fixed_path)
                        fallback = os.path.join(GlobalConfig.PROCESSED_DIR, filename)
                        if os.path.exists(fallback):
                            final_ref_path = fallback

        items.append({
            "filename": f,
            "path": full_path,
            "mtime": mtime,
            "date": date_str,
            "persona": persona,
            "record": record,
            "ref_path": final_ref_path
        })
    return items

@st.cache_data(show_spinner=False)
def extract_metadata_from_image(file_path, mtime=None):
    """
    Extracts seed and prompt from ComfyUI image metadata.
    Returns a dict with seed, prompt, and raw_metadata.
    """
    metadata = {
        "seed": None,
        "prompt": None,
        "raw_metadata": {}
    }
    
    try:
        with Image.open(file_path) as img:
            meta = img.info
            if 'prompt' in meta:
                prompt_data = json.loads(meta['prompt'])
                metadata["raw_metadata"] = prompt_data
                
                # Traverse nodes to find seed and prompt
                for node_id, node_data in prompt_data.items():
                    inputs = node_data.get('inputs', {})
                    class_type = node_data.get('class_type', '')
                    
                    # Look for Seed
                    if metadata["seed"] is None:
                        if 'seed' in inputs:
                            metadata["seed"] = inputs['seed']
                        elif 'noise_seed' in inputs:
                            metadata["seed"] = inputs['noise_seed']
                    
                    # Look for Prompt (Text)
                    # Prioritize CLIPTextEncode or similar
                    if 'text' in inputs and isinstance(inputs['text'], str):
                        # Simple heuristic: if it's a CLIPTextEncode node, it's likely the prompt
                        # If we haven't found one yet, take it. 
                        # Or if it's explicitly a CLIPTextEncode, overwrite whatever we found (maybe?)
                        # Let's just take the first CLIPTextEncode we find, or the first text if no CLIPTextEncode found yet.
                        if 'CLIPTextEncode' in class_type or metadata["prompt"] is None:
                            metadata["prompt"] = inputs['text']
                            
    except Exception as e:
        print(f"Error extracting metadata from {file_path}: {e}")
        
    return metadata

# --- Persistence & State Logic ---
APPROVALS_FILE = os.path.join(OUTPUT_DIR, "approvals.json")

# Initialize Session State for Approvals and Selections
if "approved_files" not in st.session_state:
    st.session_state.approved_files = set()
    if os.path.exists(APPROVALS_FILE):
        try:
            with open(APPROVALS_FILE, "r") as f:
                saved = json.load(f)
                st.session_state.approved_files = set(saved)
        except Exception:
            pass

if "selected_files" not in st.session_state:
    st.session_state.selected_files = set()

def update_approvals_file():
    try:
        with open(APPROVALS_FILE, "w") as f:
            json.dump(list(st.session_state.approved_files), f)
    except Exception as e:
        st.error(f"Failed to save approvals: {e}")

def toggle_approval(base_name):
    if base_name in st.session_state.approved_files:
        st.session_state.approved_files.remove(base_name)
    else:
        st.session_state.approved_files.add(base_name)
    update_approvals_file()

def toggle_selection(filename):
    if filename in st.session_state.selected_files:
        st.session_state.selected_files.remove(filename)
    else:
        st.session_state.selected_files.add(filename)

# --- Fragment for Gallery View ---
@st.fragment
def view_gallery_fragment(filtered_items, group_by_date):
    """
    Renders the gallery grid, pagination, and batch actions in a fragment.
    Updates here will not cause a full page reload.
    """
    
    # --- Pagination ---
    total_items = len(filtered_items)
    paginated_items = []

    if total_items > 0:
        col_p1, col_p2, col_p3 = st.columns([1, 2, 2])
        with col_p1:
            items_per_page = st.selectbox("Images per page", [20, 50, 100, 200], index=1)
        
        total_pages = math.ceil(total_items / items_per_page)
        
        if "gallery_page" not in st.session_state:
            st.session_state.gallery_page = 1
            
        # Ensure valid page
        if st.session_state.gallery_page > total_pages:
            st.session_state.gallery_page = total_pages
        if st.session_state.gallery_page < 1:
            st.session_state.gallery_page = 1
            
        with col_p2:
            st.session_state.gallery_page = st.number_input(
                f"Page (Total: {total_pages})", 
                min_value=1, 
                max_value=total_pages, 
                value=st.session_state.gallery_page
            )
        
        with col_p3:
            st.caption(f"Total Images: {total_items}")

        start_idx = (st.session_state.gallery_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        paginated_items = filtered_items[start_idx:end_idx]
        
        st.caption(f"Showing images {start_idx + 1}-{min(end_idx, total_items)} of {total_items}")
    else:
        paginated_items = []
        st.info("No matching images found.")

    # --- Batch Actions ---
    selected_files = st.session_state.selected_files
    
    # Filter valid files from selection (in case files were deleted but still in session)
    valid_selected = [f for f in selected_files if os.path.exists(os.path.join(OUTPUT_DIR, f))]
    
    if valid_selected:
        st.info(f"Selected {len(valid_selected)} images.")
        
        with st.container():
            col_b1, col_b2, col_b3 = st.columns([2, 2, 4])
            
            with col_b1:
                include_txt = st.toggle("Include Metadata (.txt)", value=True)
                if st.button("Download Selected"):
                    with st.spinner("Preparing ZIP..."):
                        # Helper to fetch prompts
                        async def fetch_prompts_map(files):
                            results = {}
                            async def fetch_single(f_path):
                                try:
                                    record = storage.get_execution_by_result_path(str(f_path))
                                    if not record or not record.get('execution_id'): return None
                                    ex_id = record['execution_id']
                                    details = await client.get_execution_details(ex_id)
                                    prompt_content = details.get('prompt')
                                    if prompt_content is None:
                                        if 'input_overrides' in details and 'positive_prompt' in details['input_overrides']:
                                            prompt_content = details['input_overrides']['positive_prompt']
                                        elif 'prompt' in record:
                                            prompt_content = record['prompt']
                                    return prompt_content
                                except Exception:
                                    if record and 'prompt' in record: return record['prompt']
                                    return None

                            full_paths = [os.path.join(OUTPUT_DIR, f) for f in files]
                            tasks = [fetch_single(fp) for fp in full_paths]
                            fetched_prompts = await asyncio.gather(*tasks)
                            
                            for fname, p_content in zip(files, fetched_prompts):
                                if p_content: results[fname] = p_content
                            return results

                        prompts_map = {}
                        if include_txt:
                            prompts_map = asyncio.run(fetch_prompts_map(valid_selected))

                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                            for fname in valid_selected:
                                full_path = os.path.join(OUTPUT_DIR, fname)
                                zf.write(full_path, arcname=fname)
                                
                                if include_txt and fname in prompts_map:
                                    base_name = os.path.splitext(fname)[0]
                                    txt_filename = f"{base_name}.txt"
                                    content = prompts_map[fname]
                                    txt_content = json.dumps(content, indent=2) if isinstance(content, (dict, list)) else str(content)
                                    zf.writestr(txt_filename, txt_content)
                        
                        st.session_state['batch_zip_buffer'] = zip_buffer.getvalue()
                        st.success("Ready for download!")
                
                if 'batch_zip_buffer' in st.session_state and st.session_state.get('batch_zip_buffer'):
                    st.download_button("Download ZIP", st.session_state['batch_zip_buffer'], "selected_images.zip", "application/zip")

            with col_b2:
                if st.button("Delete Selected", type="primary"):
                    st.session_state.confirm_batch_delete = True
                
                if st.session_state.get("confirm_batch_delete", False):
                    st.warning(f"Delete {len(valid_selected)} files?")
                    col_conf1, col_conf2 = st.columns(2)
                    with col_conf1:
                        if st.button("Yes, Delete"):
                            deleted = 0
                            for fname in valid_selected:
                                try:
                                    os.remove(os.path.join(OUTPUT_DIR, fname))
                                    st.session_state.selected_files.remove(fname)
                                    deleted += 1
                                except Exception as e:
                                    st.error(f"Error deleting {fname}: {e}")
                            st.success(f"Deleted {deleted} files.")
                            st.session_state.confirm_batch_delete = False
                            # We need to trigger a full rerun to refresh the list of files from disk
                            st.rerun()
                    with col_conf2:
                        if st.button("Cancel Delete"):
                            st.session_state.confirm_batch_delete = False
                            st.rerun() # Re-render fragment to hide warning

    # --- Rendering Helper ---
    def render_grid(items):
        cols_per_row = 4
        for i in range(0, len(items), cols_per_row):
            row_items = items[i:i+cols_per_row]
            cols = st.columns(cols_per_row)
            for idx, item in enumerate(row_items):
                with cols[idx]:
                    st.image(item['path'], caption=item['filename'], width='stretch')
                    base_name = os.path.splitext(item['filename'])[0]
                    
                    # Controls
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        # Selection Checkbox
                        st.checkbox("Sel", 
                            key=f"select_{item['filename']}", 
                            value=item['filename'] in st.session_state.selected_files,
                            on_change=toggle_selection,
                            args=(item['filename'],)
                        )
                    with c2:
                        # Approve Checkbox
                        st.checkbox("Approve", 
                            key=f"approve_{base_name}", 
                            value=base_name in st.session_state.approved_files,
                            on_change=toggle_approval,
                            args=(base_name,)
                        )
                    
                    with st.popover("View Metadata"):
                        # Extract Image Metadata (Seed & Prompt)
                        img_meta = extract_metadata_from_image(item['path'], item['mtime'])
                        
                        if img_meta['seed'] is not None:
                            st.write(f"**Seed:** `{img_meta['seed']}`")
                        
                        if img_meta['prompt']:
                            st.caption("**Prompt:**")
                            st.text(img_meta['prompt'])
                        
                        st.divider()

                        db_record = item['record']
                        if db_record:
                            st.write(f"**Persona:** {item['persona']}")
                            st.write(f"**Execution ID:** `{db_record['execution_id']}`")
                            st.write(f"**Status:** {db_record['status']}")
                            
                            # Use pre-calculated ref_path
                            ref_path = item.get('ref_path')
                            if ref_path:
                                st.image(ref_path, caption="Reference Image", width=200)
                            
                            if st.button("Fetch Remote Details", key=f"fetch_{base_name}"):
                                with st.spinner("Fetching details..."):
                                    remote = asyncio.run(fetch_remote_metadata(client, db_record['execution_id']))
                                    if remote: st.json(remote)
                        else:
                            st.warning("No database record found.")
                        
                        if img_meta['raw_metadata']:
                            with st.expander("View Full Metadata"):
                                st.json(img_meta['raw_metadata'])

    # --- Grouping Logic ---
    if group_by_date:
        # Group by date string
        # Note: items are already sorted by time
        grouped = {}
        for item in paginated_items:
            d = item['date']
            if d not in grouped: grouped[d] = []
            grouped[d].append(item)
        
        # Render groups
        for date_key in grouped:
            st.subheader(f"📅 {date_key}")
            render_grid(grouped[date_key])
    else:
        render_grid(paginated_items)

# -------------------------

if st.button("Refresh Gallery"):
    load_gallery_data.clear()
    st.rerun()

if os.path.exists(OUTPUT_DIR):
    # Load data (cached)
    gallery_items = load_gallery_data(OUTPUT_DIR)
    
    if not gallery_items:
            st.info("No results found yet.")
    else:
        # --- Gallery Settings ---
        with st.expander("🛠️ Gallery Settings", expanded=False):
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                # Persona Filter
                all_personas = sorted(list(set(item['persona'] for item in gallery_items)))
                selected_personas = st.multiselect("Filter by Persona", all_personas, default=[])
            
            with col_f2:
                # Sort Order
                sort_order = st.selectbox("Sort By", ["Newest First", "Oldest First"])
            
            with col_f3:
                # Grouping
                group_by_date = st.toggle("Group by Date", value=True)

        # --- Maintenance ---
        with st.expander("🗑️ Maintenance", expanded=False):
            st.write("Manage unused (unapproved) images.")
            
            # Calculate unused
            all_bases = set(os.path.splitext(f)[0] for f in get_sorted_images(OUTPUT_DIR))
            approved_bases = st.session_state.approved_files
            unused_bases = all_bases - approved_bases
            
            col_m1, col_m2 = st.columns([1, 1])
            with col_m1:
                st.metric("Total Images", len(all_bases))
            with col_m2:
                st.metric("Unused Images", len(unused_bases))
                
            if unused_bases:
                if st.button("Delete All Unused Images", type="primary"):
                    st.session_state.confirm_delete_unused = True
                
                if st.session_state.get("confirm_delete_unused", False):
                    st.warning(f"Are you sure you want to delete {len(unused_bases)} images? This cannot be undone.")
                    col_confirm_1, col_confirm_2 = st.columns(2)
                    with col_confirm_1:
                        if st.button("Yes, Delete Everything"):
                            deleted_count = 0
                            for base in unused_bases:
                                # Find files starting with this base (to cover extensions)
                                for f in os.listdir(OUTPUT_DIR):
                                    if os.path.splitext(f)[0] == base:
                                        try:
                                            os.remove(os.path.join(OUTPUT_DIR, f))
                                            deleted_count += 1
                                        except Exception as e:
                                            st.error(f"Error deleting {f}: {e}")
                            
                            st.success(f"Deleted {deleted_count} files.")
                            st.session_state.confirm_delete_unused = False
                            load_gallery_data.clear()
                            st.rerun()
                    
                    with col_confirm_2:
                        if st.button("Cancel"):
                            st.session_state.confirm_delete_unused = False
                            st.rerun()

        # --- Filtering & Sorting ---
        filtered_items = gallery_items
        if selected_personas:
            filtered_items = [item for item in filtered_items if item['persona'] in selected_personas]
        
        # Sort
        reverse_sort = (sort_order == "Newest First")
        filtered_items.sort(key=lambda x: x['mtime'], reverse=reverse_sort)
        
        st.write(f"Showing {len(filtered_items)} images.")
        
        # --- RENDER FRAGMENT ---
        # Pass the prepared items to the fragment
        view_gallery_fragment(filtered_items, group_by_date)

else:
    st.error(f"Output directory '{OUTPUT_DIR}' does not exist.")
