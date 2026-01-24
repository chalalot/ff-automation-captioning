import streamlit as st
import os
import sys
import asyncio
import contextlib
import pandas as pd
import requests
import uuid
import time

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.workflows.video_storyboard_workflow import VideoStoryboardWorkflow
from src.utils.streamlit_utils import get_sorted_images, StreamlitLogger
from src.database.video_logs_storage import VideoLogsStorage
from src.third_parties.gcs_client import check_blob_exists, download_blob_to_file
from scripts.merge_videos_test import merge_videos

# Initialize Storage
video_storage = VideoLogsStorage()

# Page Config
st.set_page_config(page_title="Video - CrewAI Image Workflow", layout="wide")

st.title("🎬 Video Storyboard & Generation")

# Constants
INPUT_DIR = GlobalConfig.INPUT_DIR
OUTPUT_DIR = GlobalConfig.OUTPUT_DIR

# Sidebar Configuration for Persona
st.sidebar.header("Configuration")
kol_persona = st.sidebar.selectbox("KOL Persona", ["Jennie", "Sephera", "Mika", "Nya", "Emi", "Roxie"])

st.markdown("Select a source image from the Results Gallery to generate video.")

# --- Workflow Configuration Studio ---
with st.expander("⚙️ Workflow Configuration Studio", expanded=False):
    st.info("Edit Agent Backstories and Task Descriptions for the video workflow.")
    
    # Paths
    base_workflow_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'workflows')
    
    # Files
    files = {
        "analyst_agent": "video_analyst_agent.txt",
        "analyst_task": "video_analyst_task.txt",
        "concept_agent": "video_concept_agent.txt",
        "concept_task": "video_concept_task.txt",
        "prompt_agent": "video_prompt_agent.txt",
        "prompt_task": "video_prompt_task.txt"
    }
    
    def load_content(filename):
        path = os.path.join(base_workflow_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f: return f.read()
            except: return ""
        return ""

    # Tabs
    tab_analyst, tab_concept, tab_prompt = st.tabs(["Visual Analyst", "Concept Ideator", "Prompt Generator"])
    
    # Analyst
    with tab_analyst:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Analyst Agent Backstory")
            val_aa = st.text_area("Backstory", value=load_content(files["analyst_agent"]), height=300, key="v_aa")
        with c2:
            st.caption("Analysis Task Description (use `{image_path}`)")
            val_at = st.text_area("Task", value=load_content(files["analyst_task"]), height=300, key="v_at")
            
    # Concept
    with tab_concept:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Concept Agent Backstory")
            val_ca = st.text_area("Backstory", value=load_content(files["concept_agent"]), height=300, key="v_ca")
        with c2:
            st.caption("Concept Task Description")
            val_ct = st.text_area("Task", value=load_content(files["concept_task"]), height=300, key="v_ct")

    # Prompt
    with tab_prompt:
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Prompt Agent Backstory")
            val_pa = st.text_area("Backstory", value=load_content(files["prompt_agent"]), height=300, key="v_pa")
        with c2:
            st.caption("Prompt Generation Task Description")
            val_pt = st.text_area("Task", value=load_content(files["prompt_task"]), height=300, key="v_pt")

    if st.button("Save Video Configuration"):
        try:
            # Save all
            with open(os.path.join(base_workflow_dir, files["analyst_agent"]), 'w', encoding='utf-8') as f: f.write(val_aa)
            with open(os.path.join(base_workflow_dir, files["analyst_task"]), 'w', encoding='utf-8') as f: f.write(val_at)
            with open(os.path.join(base_workflow_dir, files["concept_agent"]), 'w', encoding='utf-8') as f: f.write(val_ca)
            with open(os.path.join(base_workflow_dir, files["concept_task"]), 'w', encoding='utf-8') as f: f.write(val_ct)
            with open(os.path.join(base_workflow_dir, files["prompt_agent"]), 'w', encoding='utf-8') as f: f.write(val_pa)
            with open(os.path.join(base_workflow_dir, files["prompt_task"]), 'w', encoding='utf-8') as f: f.write(val_pt)
            st.success("✅ Configuration saved!")
        except Exception as e:
            st.error(f"Failed to save: {e}")

# --- Queue Status Section ---
with st.expander("📊 Video Generation History", expanded=False):
    recent_executions = video_storage.get_recent_executions(limit=10)
    if recent_executions:
        # Convert to DataFrame
        df = pd.DataFrame(recent_executions)
        # Select columns
        cols_to_show = ['id', 'execution_id', 'status', 'created_at', 'prompt']
        
        st.dataframe(df[cols_to_show], use_container_width=True)
        
        if st.button("Refresh History"):
            st.rerun()
    else:
        st.info("No video generation history found.")

st.divider()

# --- 1. Select Source Image ---
st.subheader("1. Select Source Image (Frame 0)")

# Init session state for selection
if "selected_video_source" not in st.session_state:
    st.session_state.selected_video_source = None

def on_method_change():
    st.session_state.selected_video_source = None

# Input Method Toggle
input_method = st.radio(
    "Choose Input Method", 
    ["Select from Results Gallery", "Upload Custom Image"], 
    horizontal=True,
    on_change=on_method_change,
    key="video_input_method"
)

if input_method == "Upload Custom Image":
    uploaded_video_file = st.file_uploader("Upload Image", type=['png', 'jpg', 'jpeg', 'webp'])
    if uploaded_video_file:
        # Create temp directory
        temp_dir = os.path.join(INPUT_DIR, "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(temp_dir, uploaded_video_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_video_file.getbuffer())
        
        st.success(f"Uploaded: {uploaded_video_file.name}")
        st.image(file_path, width=300)
        
        # Auto-select
        st.session_state.selected_video_source = file_path
    else:
        if st.session_state.selected_video_source:
                st.info(f"Currently selected: {os.path.basename(st.session_state.selected_video_source)}")
        else:
                st.info("Please upload an image.")

else:
    # List output images
    archive_images = get_sorted_images(OUTPUT_DIR)
    
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
    st.write("🧠 Agents are brainstorming video concepts...")
    result = workflow.process(source_path, persona)
    
    concepts = result["concepts_text"]
    variations = result["variations"]
    
    st.success("✅ Video Prompts Generated!")
    
    return {
        "source": source_path,
        "concepts_text": concepts,
        "variations": variations
    }

if st.button("Draft Generate Video Prompts", disabled=(st.session_state.selected_video_source is None)):
    if st.session_state.selected_video_source:
        
        with st.expander("📝 Live Agent Logs", expanded=True):
            with st.container(height=300):
                log_placeholder = st.empty()
            logger = StreamlitLogger(log_placeholder)
        
        with st.spinner("Brainstorming Video Prompts... This may take a moment."):
            # Capture stdout for logging
            with contextlib.redirect_stdout(logger):
                video_results = asyncio.run(run_video_draft(st.session_state.selected_video_source, kol_persona))
            
            st.session_state.video_results = video_results
            st.success("Prompts Ready!")
    else:
        st.error("Please select an image first.")

# --- 3. Review ---
if "video_results" in st.session_state and st.session_state.video_results:
    st.subheader("3. Video Prompts")
    
    res = st.session_state.video_results
    
    col1, col2 = st.columns([1, 2])
    with col1:
            st.image(res["source"], caption="Source Image", width='stretch')
    
    with col2:
            with st.expander("📜 Concept Details", expanded=False):
                st.markdown(res["concepts_text"])

    st.divider()
    
    # Display Variations
    st.markdown("### 🎞️ Generated Prompts")
    variations = res["variations"]
    for item in variations:
        var_num = item.get("variation")
        concept = item.get("concept_name")
        prompt = item.get("prompt")
        
        st.markdown(f"#### Variation {var_num}: {concept}")
        st.code(prompt, language="text")
        st.divider()

# --- 4. Kling AI Generation (ComfyUI Partner Node) ---
st.subheader("4. Kling AI Video Generation (ComfyUI)")

from src.third_parties.comfyui_client import ComfyUIClient

# Initialize Client
try:
    comfy_client = ComfyUIClient()
    client_available = True
except Exception as e:
    st.error(f"Failed to initialize ComfyUI Client: {e}")
    client_available = False

if client_available:
    # Initialize session state for Batch
    if "batch_task_ids" not in st.session_state:
        st.session_state.batch_task_ids = []
    if "batch_id" not in st.session_state:
        st.session_state.batch_id = None
    if "batch_video_paths" not in st.session_state:
        st.session_state.batch_video_paths = []

    # Display Prompt Selection (Optional Single Queue) OR Batch Queue
    if "video_results" in st.session_state and st.session_state.video_results:
        variations = st.session_state.video_results["variations"]
        st.info(f"Available Variations: {len(variations)}")
        
        duration = st.selectbox("Duration", ["5", "10"], index=0)
        
        col_q1, col_q2 = st.columns(2)
        
        with col_q1:
            st.markdown("### Single Queue")
            # Selection for Prompt
            prompt_options = {f"Variation {v.get('variation', i+1)}: {v.get('concept_name', 'Unknown')}": v.get('prompt', '') for i, v in enumerate(variations)}
            selected_option = st.selectbox("Select Prompt", list(prompt_options.keys()) + ["Custom Prompt"])
            
            if selected_option == "Custom Prompt":
                final_prompt = st.text_area("Enter Custom Prompt", value="Cinematic shot, high quality, 4k")
            else:
                final_prompt = st.text_area("Selected Prompt", value=prompt_options[selected_option])

            if st.button("🚀 Queue Single Video"):
                if not st.session_state.selected_video_source:
                    st.error("No source image selected!")
                else:
                    with st.spinner("Queueing task..."):
                        try:
                            filename_id = str(uuid.uuid4())
                            task_id = asyncio.run(comfy_client.generate_video_kling(
                                prompt=final_prompt,
                                image_path=st.session_state.selected_video_source,
                                duration=duration,
                                filename_id=filename_id
                            ))
                            # Log to DB
                            video_storage.log_execution(task_id, final_prompt, st.session_state.selected_video_source, filename_id=filename_id)
                            st.success(f"Task Queued! ID: {task_id}")
                        except Exception as e:
                            st.error(f"Failed to queue task: {e}")

        with col_q2:
            st.markdown("### Batch Queue")
            st.write(f"Queue all {len(variations)} variations at once.")
            
            if st.button("🚀🚀 Queue All Variations"):
                if not st.session_state.selected_video_source:
                    st.error("No source image selected!")
                else:
                    st.session_state.batch_task_ids = [] # Reset batch
                    st.session_state.batch_video_paths = [] # Reset paths
                    
                    # Generate Batch ID
                    batch_id = str(uuid.uuid4())
                    st.session_state.batch_id = batch_id
                    
                    progress_bar = st.progress(0)
                    
                    with st.spinner(f"Queueing batch {batch_id[:8]}..."):
                        for idx, item in enumerate(variations):
                            prompt = item.get("prompt")
                            try:
                                filename_id = str(uuid.uuid4())
                                task_id = asyncio.run(comfy_client.generate_video_kling(
                                    prompt=prompt,
                                    image_path=st.session_state.selected_video_source,
                                    duration=duration,
                                    filename_id=filename_id
                                ))
                                # Log to DB with batch_id
                                video_storage.log_execution(task_id, prompt, st.session_state.selected_video_source, batch_id=batch_id, filename_id=filename_id)
                                st.session_state.batch_task_ids.append(task_id)
                                
                            except Exception as e:
                                st.error(f"Failed to queue variation {idx+1}: {e}")
                            
                            progress_bar.progress((idx + 1) / len(variations))
                            
                    st.success(f"Batch Queued! {len(st.session_state.batch_task_ids)} tasks started.")
                    st.write("Batch ID:", st.session_state.batch_id)
                    st.write("Task IDs:", st.session_state.batch_task_ids)

    # --- Batch Status & Download ---
    st.divider()
    st.markdown("### 📦 Batch Status, Download & Merge")
    
    # 1. Recover Pending Batches
    with st.expander("🔄 Recover Incomplete Batch", expanded=not st.session_state.batch_task_ids):
        incomplete_batches = video_storage.get_incomplete_batches()
        if incomplete_batches:
            st.write(f"Found {len(incomplete_batches)} incomplete batches in database.")
            
            # Create selection options
            batch_options = {f"{b['created_at']} (ID: {b['batch_id'][:8]}...) - {b['count']} tasks": b['batch_id'] for b in incomplete_batches}
            
            selected_batch_label = st.selectbox("Select Batch to Recover", list(batch_options.keys()))
            
            if st.button("Load Selected Batch"):
                selected_batch_id = batch_options[selected_batch_label]
                executions = video_storage.get_batch_executions(selected_batch_id)
                
                # Load into session state
                st.session_state.batch_id = selected_batch_id
                st.session_state.batch_task_ids = [e['execution_id'] for e in executions]
                st.session_state.batch_video_paths = [] # Reset paths
                
                st.success(f"Loaded batch {selected_batch_id} with {len(executions)} tasks.")
                st.rerun()
        else:
            st.info("No incomplete batches found in database.")

    # 2. Process Current Batch
    if st.session_state.batch_task_ids:
        st.write(f"Current Batch ID: `{st.session_state.batch_id}`")
        st.write(f"Tasks: {len(st.session_state.batch_task_ids)}")
        
        col_poll, col_stop = st.columns(2)
        with col_poll:
            if st.button("🔄 Start Auto-Poll & Merge"):
                st.session_state.polling_active = True
                st.rerun()
        
        with col_stop:
            if st.button("⏹️ Stop Polling"):
                st.session_state.polling_active = False
                st.rerun()

        if st.session_state.get("polling_active", False):
            st.info("🔄 Polling active... checking status...")
            completed_videos = [] # List of paths
            pending_count = 0
            failed_count = 0
            
            # Temporary directory for downloads (inside OUTPUT_DIR to ensure it persists in VM mounts)
            raw_video_dir = os.path.join(OUTPUT_DIR, "video-raw")
            os.makedirs(raw_video_dir, exist_ok=True)
            
            with st.spinner("Checking status for all tasks..."):
                # Use a limited number of columns for display to avoid layout issues
                num_cols = min(len(st.session_state.batch_task_ids), 4)
                if num_cols > 0:
                    status_cols = st.columns(num_cols)
                
                for idx, task_id in enumerate(st.session_state.batch_task_ids):
                    col = status_cols[idx % num_cols] if num_cols > 0 else st
                    
                    # 1. Check Local DB First
                    db_record = video_storage.get_execution(task_id)
                    local_status = db_record.get('status') if db_record else None
                    video_output_path = db_record.get('video_output_path') if db_record else None
                    filename_id = db_record.get('filename_id') if db_record else None
                    
                    is_completed_locally = False
                    if local_status == 'completed' and video_output_path and os.path.exists(video_output_path) and os.path.getsize(video_output_path) > 0:
                         is_completed_locally = True
                    
                    if is_completed_locally:
                        with col:
                            st.write(f"Task {task_id[-4:]}: **completed (cached)**")
                        completed_videos.append(video_output_path)
                        continue

                    # 2. Check ComfyUI Status & GCS
                    try:
                        # Ask ComfyUI for status and filename
                        status_res = asyncio.run(comfy_client.check_status_local(task_id))
                        status = status_res.get("status")
                        
                        if status == "succeed":
                            # 1. Determine Filename (Prioritize filename_id if available)
                            if filename_id:
                                filename = f"ComfyUI-{filename_id}.mp4"
                            else:
                                filename = status_res.get("filename")
                                if not filename:
                                    filename = f"ComfyUI-{task_id}.mp4"
                            
                            # Construct GCS Path
                            gcs_blob_name = f"outputs/{filename}"
                            local_path = os.path.join(raw_video_dir, filename)
                            
                            # Check if it exists on GCS
                            is_completed_remote = check_blob_exists(gcs_blob_name)
                            
                            if is_completed_remote:
                                with col:
                                    st.write(f"Task {task_id[-4:]}: **completed**")
                                
                                # Download if not exists or empty
                                if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                                    try:
                                        download_blob_to_file(gcs_blob_name, local_path)
                                        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                                            completed_videos.append(local_path)
                                            # Update DB
                                            video_storage.update_result(task_id, local_path, 'completed')
                                        else:
                                            st.warning(f"Video file missing after download for {task_id}")
                                            failed_count += 1
                                    except Exception as e:
                                        st.error(f"Download error for {task_id}: {e}")
                                        failed_count += 1
                                else:
                                    # Already downloaded
                                    completed_videos.append(local_path)
                                    # Update DB
                                    video_storage.update_result(task_id, local_path, 'completed')
                            else:
                                # Status says succeed but not found in GCS yet (maybe upload lag)
                                with col:
                                    st.write(f"Task {task_id[-4:]}: **uploading...**")
                                pending_count += 1

                        elif status == "failed":
                             with col:
                                 st.error(f"Task {task_id[-4:]}: **FAILED**")
                             failed_count += 1
                                
                        else:
                            # Not found in GCS yet, assume running
                            status = "running"
                            with col:
                                st.write(f"Task {task_id[-4:]}: **running**")
                            pending_count += 1
                            
                    except Exception as e:
                        st.error(f"Error checking {task_id}: {e}")
                        failed_count += 1
            
            # Display Completed Videos
            if completed_videos:
                st.markdown("#### Completed Videos")
                v_cols = st.columns(min(len(completed_videos), 3))
                for idx, v_path in enumerate(completed_videos):
                    with v_cols[idx % 3]:
                        st.video(v_path)
                        st.caption(os.path.basename(v_path))
            
            # Merge Logic or Wait
            if pending_count == 0:
                st.session_state.polling_active = False # Stop polling
                
                if len(completed_videos) > 0:
                    st.success(f"All tasks finished. {len(completed_videos)} successful, {failed_count} failed. Merging successful videos...")
                    
                    # Merge
                    merged_output_dir = "results"
                    os.makedirs(merged_output_dir, exist_ok=True)
                    # Use batch ID for filename if available, else first task ID
                    batch_label = st.session_state.batch_id[-4:] if st.session_state.batch_id else st.session_state.batch_task_ids[0][-4:]
                    merged_filename = f"merged_batch_{batch_label}.mp4"
                    merged_path = os.path.join(merged_output_dir, merged_filename)
                    
                    with st.spinner("Merging videos..."):
                        try:
                            merge_videos(completed_videos, merged_path)
                            st.success("Merge Complete!")
                            st.video(merged_path)
                            st.markdown(f"**Merged Video Saved:** `{merged_path}`")

                            # Cleanup raw videos
                            for v_path in completed_videos:
                                try:
                                    if os.path.exists(v_path):
                                        os.remove(v_path)
                                except Exception as cleanup_err:
                                    print(f"Failed to delete {v_path}: {cleanup_err}")
                            st.info("Temporary raw videos cleaned up.")
                            
                        except Exception as e:
                            st.error(f"Merge failed: {e}")
                else:
                    st.error("All tasks failed or no videos available to merge.")
            else:
                st.info(f"Waiting for {pending_count} tasks to complete before merging. ({len(completed_videos)} ready, {failed_count} failed)")
                time.sleep(10)
                st.rerun()
    else:
        st.info("No active batch in session. Queue variations to start a batch or recover one above.")
