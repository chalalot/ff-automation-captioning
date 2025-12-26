import streamlit as st
import os
import shutil
import asyncio
import sys
import zipfile
import io
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.config import GlobalConfig
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow
from src.workflows.video_storyboard_workflow import VideoStoryboardWorkflow
from src.third_parties.comfyui_client import ComfyUIClient
from src.database.image_logs_storage import ImageLogsStorage

# Import Scripts for Buttons
try:
    from scripts.process_and_queue import main as run_process_script
    from scripts.populate_generated_images import main as run_populate_script
except ImportError:
    # Fallback if running from a different context where scripts module isn't resolvable directly
    sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
    from scripts.process_and_queue import main as run_process_script
    from scripts.populate_generated_images import main as run_populate_script

# Page Config
st.set_page_config(page_title="CrewAI Image Workflow", layout="wide")

# Title
st.title("🚀 CrewAI Image-to-Prompt Workflow")

# Sidebar Configuration
st.sidebar.header("Configuration")
kol_persona = st.sidebar.selectbox("KOL Persona", ["Jennie", "Sephera", "Mika", "Nya", "Emi", "Roxie"])
workflow_choice = st.sidebar.selectbox("Workflow Type", ["Turbo", "WAN2.2"])
limit_choice = st.sidebar.number_input("Batch Limit", min_value=1, max_value=100, value=10)

# Constants from Config
INPUT_DIR = GlobalConfig.INPUT_DIR
OUTPUT_DIR = GlobalConfig.OUTPUT_DIR
PROCESSED_DIR = GlobalConfig.PROCESSED_DIR

# Ensure directories exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Initialize Components
storage = ImageLogsStorage()
client = ComfyUIClient()

# Session State Initialization
if "results" not in st.session_state:
    st.session_state.results = []

# --- Helper Functions ---
async def fetch_remote_metadata(execution_id):
    return await client.get_execution_details(execution_id)

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["Workspace", "Results Gallery", "🎬 Video Generation"])

with tab1:
    # --- 1. Workflow Mode ---
    st.header("1. Input Configuration")
    
    st.info(f"Monitoring Input Directory: `{INPUT_DIR}`")

    # Live Count Display
    def count_files_in_input():
        if os.path.exists(INPUT_DIR):
            valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
            return len([f for f in os.listdir(INPUT_DIR) if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(INPUT_DIR, f))])
        return 0

    input_count_placeholder = st.empty()
    input_count_placeholder.metric("Images Remaining in Sorted Folder", count_files_in_input())
    
    # Optional Upload Logic
    with st.expander("Upload Images to Input Directory (Optional)"):
        uploaded_files = st.file_uploader("Upload images to process", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'])
        if uploaded_files:
            if st.button("Save to Input Directory"):
                for uploaded_file in uploaded_files:
                    file_path = os.path.join(INPUT_DIR, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                st.success(f"Saved {len(uploaded_files)} images to {INPUT_DIR}.")
                # Update count immediately after upload
                input_count_placeholder.metric("Images Remaining in Sorted Folder", count_files_in_input())

    # --- Queue Status Section ---
    with st.expander("📊 Queue Status (Recent Executions)", expanded=False):
        recent_executions = storage.get_recent_executions(limit=20)
        if recent_executions:
            # Convert to DataFrame for cleaner display
            df = pd.DataFrame(recent_executions)
            # Select relevant columns
            cols_to_show = ['id', 'execution_id', 'status', 'created_at']
            if 'image_ref_path' in df.columns:
                cols_to_show.append('image_ref_path')
            
            st.dataframe(df[cols_to_show], width='stretch')
            
            if st.button("Refresh Status"):
                st.rerun()
        else:
            st.info("No execution history found.")

    # --- 2. Generation Flow Section ---
    st.header("2. Generation Flow")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Step 1: Process & Queue")
        st.markdown(f"Consumes images from `{INPUT_DIR}`, generates prompts, and queues them.")
        
        if st.button("Start Processing & Queueing", type="primary"):
            with st.spinner(f"Processing batch of {limit_choice} images..."):
                try:
                    # Callback to update the metric live during processing
                    def on_progress():
                        input_count_placeholder.metric("Images Remaining in Sorted Folder", count_files_in_input())

                    asyncio.run(run_process_script(
                        persona=kol_persona, 
                        workflow_type=workflow_choice.lower(),
                        limit=limit_choice,
                        progress_callback=on_progress
                    ))
                    st.success("Batch processing complete! Check logs for details.")
                    st.rerun() # Refresh status
                except Exception as e:
                    st.error(f"Error during processing: {e}")

    with col2:
        st.subheader("Step 2: Download Results")
        st.markdown(f"Checks status of queued items and saves completed images to `{OUTPUT_DIR}`.")
        
        if st.button("Download Completed Results"):
            with st.spinner("Checking status and downloading..."):
                try:
                    asyncio.run(run_populate_script())
                    st.success("Results updated!")
                    st.rerun() # Refresh to update gallery
                except Exception as e:
                    st.error(f"Failed to populate results: {e}")

    st.divider()

with tab2:
    st.header(f"🗂️ Results Gallery ({OUTPUT_DIR})")

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
        all_files = os.listdir(OUTPUT_DIR)
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
        
        gallery_items = []
        for f in all_files:
            if f.lower().endswith(valid_exts) and "approvals.json" not in f:
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
                            st.image(item['path'], caption=item['filename'], use_container_width=True)
                            base_name = os.path.splitext(item['filename'])[0]
                            st.checkbox("Approve", key=f"approve_{base_name}", on_change=save_approvals)
                            
                            with st.popover("View Metadata"):
                                db_record = item['record']
                                if db_record:
                                    st.write(f"**Persona:** {item['persona']}")
                                    st.write(f"**Execution ID:** `{db_record['execution_id']}`")
                                    st.write(f"**Status:** {db_record['status']}")
                                    
                                    ref_path = db_record.get('image_ref_path')
                                    if ref_path and os.path.exists(ref_path):
                                        st.image(ref_path, caption="Reference Image", width=200)
                                    
                                    if st.button("Fetch Remote Details", key=f"fetch_{base_name}"):
                                        with st.spinner("Fetching details..."):
                                            remote = asyncio.run(fetch_remote_metadata(db_record['execution_id']))
                                            if remote: st.json(remote)
                                else:
                                    st.warning("No metadata found.")

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

with tab3:
    st.header("🎬 Video Storyboard & Generation")
    st.markdown("Select a source image from the Results Gallery to generate video.")

    # --- 1. Select Source Image ---
    st.subheader("1. Select Source Image (Frame 0)")
    
    # Init session state for selection
    if "selected_video_source" not in st.session_state:
        st.session_state.selected_video_source = None
    
    # List output images
    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    archive_images = []
    if os.path.exists(OUTPUT_DIR):
        archive_images = [
            f for f in os.listdir(OUTPUT_DIR) 
            if f.lower().endswith(valid_exts)
        ]
        archive_images.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
    
    # Display Grid for Selection
    if not archive_images:
        st.warning("No images in Results Gallery.")
    else:
        # --- Pagination Logic ---
        ITEMS_PER_PAGE = 10
        if "video_page_number" not in st.session_state:
            st.session_state.video_page_number = 0

        total_pages = (len(archive_images) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        # Ensure page number is valid
        if st.session_state.video_page_number >= total_pages:
            st.session_state.video_page_number = max(0, total_pages - 1)
            
        start_idx = st.session_state.video_page_number * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        
        current_batch = archive_images[start_idx:end_idx]
        
        st.write(f"Found {len(archive_images)} available images. Showing page {st.session_state.video_page_number + 1} of {total_pages}.")
        
        # Show currently selected
        if st.session_state.selected_video_source:
            st.info(f"Selected: {os.path.basename(st.session_state.selected_video_source)}")
            st.image(st.session_state.selected_video_source, width=300)
            if st.button("Clear Selection"):
                st.session_state.selected_video_source = None
                st.rerun()
        else:
            st.info("Please select an image below:")

        # Grid for current page
        cols_per_row = 4
        for i in range(0, len(current_batch), cols_per_row):
            cols = st.columns(cols_per_row)
            row_items = current_batch[i:i+cols_per_row]
            for idx, filename in enumerate(row_items):
                with cols[idx]:
                    img_path = os.path.join(OUTPUT_DIR, filename)
                    st.image(img_path, width='stretch')
                    if st.button("Select", key=f"sel_vid_{filename}"):
                        st.session_state.selected_video_source = img_path
                        st.rerun()
        
        # Pagination Buttons
        if total_pages > 1:
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("Previous", disabled=st.session_state.video_page_number == 0):
                    st.session_state.video_page_number -= 1
                    st.rerun()
            with col_next:
                if st.button("Next", disabled=st.session_state.video_page_number >= total_pages - 1):
                    st.session_state.video_page_number += 1
                    st.rerun()

    st.divider()

    # --- 2. Generate Draft ---
    st.subheader("2. Draft Video Script & Keyframes")
    
    async def run_video_draft(source_path, persona):
        workflow = VideoStoryboardWorkflow(verbose=True)
        
        # 1. Run CrewAI Workflow
        st.write("🧠 Agents are brainstorming script and keyframes...")
        result = workflow.process(source_path, persona)
        
        script = result["full_script"]
        frames = result["frames"]
        
        st.success("✅ Script and Prompts generated!")
        
        # 2. Generate Images via ComfyUI
        client = ComfyUIClient()
        generated_frames = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_frames = len(frames)
        for i, frame_data in enumerate(frames):
            frame_num = frame_data.get("frame")
            prompt = frame_data.get("prompt")
            segment = frame_data.get("script_segment")
            
            status_text.text(f"🎨 Generating Frame {frame_num}/6...")
            
            # Call ComfyUI
            # We use the 'turbo' workflow by default or user choice
            try:
                # Use Nano Banana workflow for video drafting as requested
                gen_result = await client.generate_and_wait(
                    positive_prompt=prompt,
                    negative_prompt="bad quality, blur, low resolution", # Simple negative
                    kol_persona=persona,
                    workflow_name="nano_banana", # Force Nano Banana for consistency
                    upload_to_gcs=False, # Keep local for draft
                    input_image_path=source_path # Pass the source image
                )
                
                # Check for image bytes
                if "image_bytes" in gen_result:
                    image_bytes = gen_result["image_bytes"]
                    generated_frames.append({
                        "frame": frame_num,
                        "image_bytes": image_bytes,
                        "script": segment,
                        "prompt": prompt
                    })
                else:
                     st.error(f"Failed to generate Frame {frame_num}")
            
            except Exception as e:
                 st.error(f"Error generating Frame {frame_num}: {e}")
            
            progress_bar.progress((i + 1) / total_frames)
            
        return {
            "source": source_path,
            "script": script,
            "generated_frames": generated_frames
        }

    if st.button("Draft Generate Video", disabled=(st.session_state.selected_video_source is None)):
        if st.session_state.selected_video_source:
            with st.spinner("Running Video Storyboard Workflow... This may take a few minutes."):
                video_results = asyncio.run(run_video_draft(st.session_state.selected_video_source, kol_persona))
                st.session_state.video_results = video_results
                st.success("Video Draft Completed!")
        else:
            st.error("Please select an image first.")

    # --- 3. Review ---
    if "video_results" in st.session_state and st.session_state.video_results:
        st.subheader("3. Review Storyboard")
        
        res = st.session_state.video_results
        
        # Display Script
        with st.expander("📜 Full Video Script", expanded=False):
            st.markdown(res["script"])
            
        # Display Storyboard
        st.markdown("### 🎞️ Visual Storyboard")
        
        # Frame 0 (Source)
        col0, col_rest = st.columns([1, 4])
        with col0:
            st.image(res["source"], caption="Frame 0 (Start)", width='stretch')
            st.caption("Start")
        
        # Generated Frames
        # Display in rows of 3
        gen_frames = res["generated_frames"]
        if gen_frames:
            cols = st.columns(3)
            for idx, frame in enumerate(gen_frames):
                col = cols[idx % 3]
                with col:
                    st.image(frame["image_bytes"], caption=f"Frame {frame['frame']}", width='stretch')
                    st.caption(f"**Segment {frame['frame']}**: {frame['script'][:100]}...")
                    with st.popover("Prompt"):
                        st.write(frame["prompt"])
