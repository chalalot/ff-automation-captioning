import streamlit as st
import os
import sys
import asyncio
import json
import zipfile
import io
import pandas as pd
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
def extract_metadata_from_image(file_path):
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

# --- Persistence Logic ---
APPROVALS_FILE = os.path.join(OUTPUT_DIR, "approvals.json")

def save_approvals():
    # Save all currently True approval keys
    approvals = [k.replace("approve_", "") for k, v in st.session_state.items() if k.startswith("approve_") and v]
    with open(APPROVALS_FILE, "w") as f:
        json.dump(approvals, f)

# Load initial state on first run of session
if "approvals_loaded" not in st.session_state:
    if os.path.exists(APPROVALS_FILE):
        try:
            with open(APPROVALS_FILE, "r") as f:
                saved_approvals = json.load(f)
            for name in saved_approvals:
                st.session_state[f"approve_{name}"] = True
        except Exception as e:
            pass # approvals.json might not exist yet
    st.session_state.approvals_loaded = True
# -------------------------

if st.button("Refresh Gallery"):
    st.rerun()

if os.path.exists(OUTPUT_DIR):
    # 1. Fetch all completed executions for metadata lookup
    all_executions = storage.get_all_completed_executions()
    execution_map = {}
    for exc in all_executions:
        if exc['result_image_path']:
            # Normalize to filename
            fname = os.path.basename(exc['result_image_path'])
            execution_map[fname] = exc
    
    # 2. List files and build data list
    all_files = get_sorted_images(OUTPUT_DIR)
    
    gallery_items = []
    for f in all_files:
        full_path = os.path.join(OUTPUT_DIR, f)
        mtime = os.path.getmtime(full_path)
        dt = datetime.fromtimestamp(mtime)
        date_str = dt.strftime("%Y-%m-%d")
        
        # Get Metadata
        record = execution_map.get(f)
        persona = record['persona'] if record and 'persona' in record and record['persona'] else "Unknown"
        
        gallery_items.append({
            "filename": f,
            "path": full_path,
            "mtime": mtime,
            "date": date_str,
            "persona": persona,
            "record": record
        })
    
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

        # --- Filtering ---
        filtered_items = gallery_items
        if selected_personas:
            filtered_items = [item for item in filtered_items if item['persona'] in selected_personas]
        
        st.write(f"Showing {len(filtered_items)} images.")

        # --- Sorting ---
        reverse_sort = (sort_order == "Newest First")
        filtered_items.sort(key=lambda x: x['mtime'], reverse=reverse_sort)

        # --- Download Logic (Filtered Items) ---
        # We iterate over filtered items to check approvals
        approved_files = []
        for item in filtered_items:
            base_name = os.path.splitext(item['filename'])[0]
            if st.session_state.get(f"approve_{base_name}", False):
                approved_files.append(item['path'])
        
        if approved_files:
            st.info(f"Selected {len(approved_files)} images for download.")
            
            if st.button("Prepare Download ZIP"):
                with st.spinner("Fetching prompts and creating ZIP..."):
                    # Reuse async fetch function logic
                    async def fetch_all_prompts(files):
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

                        tasks = [fetch_single(fp) for fp in files]
                        fetched_prompts = await asyncio.gather(*tasks)
                        for fp, p_content in zip(files, fetched_prompts):
                            if p_content: results[fp] = p_content
                        return results

                    prompts_map = asyncio.run(fetch_all_prompts(approved_files))

                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for file_path in approved_files:
                            zf.write(file_path, arcname=os.path.basename(file_path))
                            if file_path in prompts_map:
                                base_name = os.path.splitext(os.path.basename(file_path))[0]
                                txt_filename = f"{base_name}.txt"
                                content = prompts_map[file_path]
                                txt_content = json.dumps(content, indent=2) if isinstance(content, (dict, list)) else str(content)
                                zf.writestr(txt_filename, txt_content)

                    st.session_state['zip_buffer'] = zip_buffer.getvalue()
                    st.success("ZIP file ready!")
            
            if 'zip_buffer' in st.session_state and st.session_state.get('zip_buffer'):
                st.download_button("Download Approved Images (.zip)", st.session_state['zip_buffer'], "approved_results.zip", "application/zip")

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
                        st.checkbox("Approve", key=f"approve_{base_name}", on_change=save_approvals)
                        
                        with st.popover("View Metadata"):
                            # Extract Image Metadata (Seed & Prompt)
                            img_meta = extract_metadata_from_image(item['path'])
                            
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
                                
                                ref_path = db_record.get('image_ref_path')
                                if ref_path:
                                    final_ref_path = None
                                    if os.path.exists(ref_path):
                                        final_ref_path = ref_path
                                    else:
                                        # Fix Windows paths when running in Linux container
                                        fixed_path = ref_path.replace('\\', '/')
                                        if os.path.exists(fixed_path):
                                            final_ref_path = fixed_path
                                        else:
                                            # Fallback: Check if file exists in PROCESSED_DIR by filename
                                            # This handles case where absolute path differs but file is in mounted processed dir
                                            filename = os.path.basename(fixed_path)
                                            fallback = os.path.join(GlobalConfig.PROCESSED_DIR, filename)
                                            if os.path.exists(fallback):
                                                final_ref_path = fallback
                                    
                                    if final_ref_path:
                                        st.image(final_ref_path, caption="Reference Image", width=200)
                                
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
            for item in filtered_items:
                d = item['date']
                if d not in grouped: grouped[d] = []
                grouped[d].append(item)
            
            # Render groups
            for date_key in grouped:
                st.subheader(f"📅 {date_key}")
                render_grid(grouped[date_key])
        else:
            render_grid(filtered_items)

else:
    st.error(f"Output directory '{OUTPUT_DIR}' does not exist.")
