import streamlit as st
import os
import sys
import asyncio
import contextlib
import pandas as pd
import requests
import uuid
import time
import shutil

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.workflows.video_storyboard_workflow import VideoStoryboardWorkflow
from src.utils.streamlit_utils import get_sorted_images, StreamlitLogger
from src.database.video_logs_storage import VideoLogsStorage
from src.third_parties.gcs_client import check_blob_exists, download_blob_to_file
from scripts.merge_videos_test import merge_videos
from src.third_parties.comfyui_client import ComfyUIClient

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

st.markdown("Select source images, configure variation counts, and queue for video generation.")

# --- Helper Functions ---
def get_sorted_videos(directory):
    if not os.path.exists(directory):
        return []
    valid_exts = ('.mp4', '.mov', '.avi')
    videos = [
        f for f in os.listdir(directory) 
        if f.lower().endswith(valid_exts)
    ]
    videos.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
    return videos

# --- Tabs ---
tab_create, tab_gallery = st.tabs(["Create Video", "Video Gallery"])

with tab_create:

    # --- Workflow Configuration Studio ---
    with st.expander("⚙️ Workflow Configuration Studio", expanded=False):
        st.info("Edit Agent Backstories and Task Descriptions for the video workflow.")
        
        # Paths
        base_workflow_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'workflows')
        
        # Files
        files = {
            "analyst_agent": "video_analyst_agent.txt",
            "analyst_task": "video_analyst_task.txt",
            "concept_agent": "video_concept_agent.txt",
            "concept_task": "video_concept_task.txt",
            "prompt_agent": "video_prompt_agent.txt",
            "prompt_task": "video_prompt_task.txt",
            "prompt_framework": "video_prompt_framework.txt",
            "prompt_constraints": "video_prompt_constraints.txt",
            "prompt_examples": "video_prompt_examples.txt"
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
                val_pa = st.text_area("Backstory", value=load_content(files["prompt_agent"]), height=400, key="v_pa")
            with c2:
                st.caption("Prompt Generation Task Template")
                sub_fw, sub_cs, sub_ex = st.tabs(["Framework", "Constraints", "Examples"])
                
                with sub_fw:
                    val_pf = st.text_area("Framework", value=load_content(files["prompt_framework"]), height=300, key="v_pf", label_visibility="collapsed")
                with sub_cs:
                    val_pc = st.text_area("Constraints", value=load_content(files["prompt_constraints"]), height=300, key="v_pc", label_visibility="collapsed")
                with sub_ex:
                    val_pe = st.text_area("Examples", value=load_content(files["prompt_examples"]), height=300, key="v_pe", label_visibility="collapsed")

        if st.button("Save Video Configuration"):
            try:
                # Ensure directory exists
                os.makedirs(base_workflow_dir, exist_ok=True)
                
                # Save all
                with open(os.path.join(base_workflow_dir, files["analyst_agent"]), 'w', encoding='utf-8') as f: f.write(val_aa)
                with open(os.path.join(base_workflow_dir, files["analyst_task"]), 'w', encoding='utf-8') as f: f.write(val_at)
                with open(os.path.join(base_workflow_dir, files["concept_agent"]), 'w', encoding='utf-8') as f: f.write(val_ca)
                with open(os.path.join(base_workflow_dir, files["concept_task"]), 'w', encoding='utf-8') as f: f.write(val_ct)
                with open(os.path.join(base_workflow_dir, files["prompt_agent"]), 'w', encoding='utf-8') as f: f.write(val_pa)
                
                # Save components
                with open(os.path.join(base_workflow_dir, files["prompt_framework"]), 'w', encoding='utf-8') as f: f.write(val_pf)
                with open(os.path.join(base_workflow_dir, files["prompt_constraints"]), 'w', encoding='utf-8') as f: f.write(val_pc)
                with open(os.path.join(base_workflow_dir, files["prompt_examples"]), 'w', encoding='utf-8') as f: f.write(val_pe)
                
                # Compile prompt task
                compiled_task = val_pf + "\n\n" + val_pc + "\n\n" + val_pe
                with open(os.path.join(base_workflow_dir, files["prompt_task"]), 'w', encoding='utf-8') as f: f.write(compiled_task)
                
                st.success("✅ Configuration saved!")
            except Exception as e:
                st.error(f"Failed to save: {e}")

    # --- Queue Status Section ---
    with st.expander("📊 Video Generation History", expanded=False):
        recent_executions = video_storage.get_recent_executions(limit=10)
        if recent_executions:
            df = pd.DataFrame(recent_executions)
            cols_to_show = ['id', 'execution_id', 'status', 'created_at', 'prompt']
            st.dataframe(df[cols_to_show], use_container_width=True)
            if st.button("Refresh History"):
                st.rerun()
        else:
            st.info("No video generation history found.")

    st.divider()

    # --- 1. Selection & Configuration ---
    st.subheader("1. Select Images & Configure")

    # Initialize Selection Queue
    if "selection_queue" not in st.session_state:
        st.session_state.selection_queue = [] # [{'path': '...', 'var_count': 3, 'id': '...'}]

    def add_to_queue(path):
        # Check if already in queue
        if not any(item['path'] == path for item in st.session_state.selection_queue):
            st.session_state.selection_queue.append({
                'path': path,
                'var_count': 3, # Default
                'id': str(uuid.uuid4())
            })
            st.toast(f"Added to queue: {os.path.basename(path)}")
        else:
            st.toast("Image already in queue.")

    # Input Method
    col_input, col_queue = st.columns([1, 1])
    
    with col_input:
        st.markdown("#### Add Images")
        input_method = st.radio("Source", ["Gallery", "Upload"], horizontal=True)
        
        if input_method == "Upload":
            uploaded_video_file = st.file_uploader("Upload Image", type=['png', 'jpg', 'jpeg', 'webp'])
            if uploaded_video_file:
                if st.button("Add Uploaded Image"):
                    temp_dir = os.path.join(INPUT_DIR, "temp_uploads")
                    os.makedirs(temp_dir, exist_ok=True)
                    file_path = os.path.join(temp_dir, uploaded_video_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_video_file.getbuffer())
                    add_to_queue(file_path)
        
        else:
            # Gallery Selection
            archive_images = get_sorted_images(OUTPUT_DIR)
            if not archive_images:
                st.warning("No images in Results Gallery.")
            else:
                # Simple list for selection to save space
                # Or a small grid
                ITEMS_PER_PAGE = 8
                if "vid_page" not in st.session_state: st.session_state.vid_page = 0
                
                total_pages = (len(archive_images) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                
                col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
                with col_nav1:
                    if st.button("◀", disabled=st.session_state.vid_page==0): st.session_state.vid_page -= 1
                with col_nav2:
                    st.caption(f"Page {st.session_state.vid_page+1}/{total_pages}")
                with col_nav3:
                    if st.button("▶", disabled=st.session_state.vid_page>=total_pages-1): st.session_state.vid_page += 1
                
                start = st.session_state.vid_page * ITEMS_PER_PAGE
                batch = archive_images[start:start+ITEMS_PER_PAGE]
                
                c_grid = st.columns(4)
                for i, img in enumerate(batch):
                    with c_grid[i % 4]:
                        p = os.path.join(OUTPUT_DIR, img)
                        st.image(p, use_container_width=True)
                        if st.button("Add", key=f"add_{img}"):
                            add_to_queue(p)

    with col_queue:
        st.markdown("#### Selection Queue")
        if not st.session_state.selection_queue:
            st.info("Queue is empty. Add images from left.")
        else:
            if st.button("Clear Queue"):
                st.session_state.selection_queue = []
                st.rerun()
            
            # Display items
            for idx, item in enumerate(st.session_state.selection_queue):
                with st.container():
                    c1, c2, c3 = st.columns([1, 2, 1])
                    with c1:
                        st.image(item['path'], width=60)
                    with c2:
                        st.caption(os.path.basename(item['path']))
                        # Variation Count Input
                        new_count = st.number_input(
                            f"Variations", 
                            min_value=1, max_value=5, value=item['var_count'], 
                            key=f"var_count_{item['id']}"
                        )
                        st.session_state.selection_queue[idx]['var_count'] = new_count
                    with c3:
                        if st.button("❌", key=f"rem_{item['id']}"):
                            st.session_state.selection_queue.pop(idx)
                            st.rerun()
                    st.divider()

    # --- 2. Process & Queue ---
    st.subheader("2. Process & Queue")
    
    # Configuration
    with st.expander("Kling/ComfyUI Settings", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            model_name = st.selectbox("Model", ["kling-v2-1", "kling-v2-master", "kling-v2-1-master", "kling-v2-5-turbo"])
        with c2:
            cfg_scale = st.number_input("CFG Scale", value=0.8, step=0.1)
        with c3:
            mode = st.selectbox("Mode", ["std", "pro"])
        with c4:
            aspect_ratio = st.selectbox("Aspect Ratio", ["9:16", "16:9", "1:1"])
        with c5:
            duration = st.selectbox("Duration", ["5", "10"], index=0)

    # Initialize Comfy Client
    try:
        comfy_client = ComfyUIClient()
        client_available = True
    except Exception as e:
        st.error(f"Failed to initialize ComfyUI Client: {e}")
        client_available = False

    # Initialize Batch State
    if "batch_task_ids" not in st.session_state:
        st.session_state.batch_task_ids = []
    if "batch_id" not in st.session_state:
        st.session_state.batch_id = None
    if "batch_status_map" not in st.session_state:
        st.session_state.batch_status_map = {} # {task_id: {'status':..., 'path':...}}

    if st.button("🚀 Process & Queue All Items", disabled=(not st.session_state.selection_queue or not client_available)):
        
        # New Batch
        batch_id = str(uuid.uuid4())
        st.session_state.batch_id = batch_id
        st.session_state.batch_task_ids = []
        st.session_state.batch_status_map = {}
        
        st.write(f"Starting Batch: `{batch_id}`")
        
        # Create Logger
        with st.expander("Processing Logs", expanded=True):
            log_placeholder = st.empty()
            logger = StreamlitLogger(log_placeholder)
            
            progress_bar = st.progress(0)
            
            with contextlib.redirect_stdout(logger):
                total_items = len(st.session_state.selection_queue)
                
                for img_idx, item in enumerate(st.session_state.selection_queue):
                    print(f"\nProcessing Image {img_idx+1}/{total_items}: {os.path.basename(item['path'])}")
                    
                    # 1. Run Storyboard Workflow
                    try:
                        workflow = VideoStoryboardWorkflow(verbose=True)
                        result = workflow.process(item['path'], kol_persona, var_count=item['var_count'])
                        
                        variations = result.get("variations", [])
                        print(f"Generated {len(variations)} prompts.")
                        
                        # 2. Queue Videos
                        for v_idx, var in enumerate(variations):
                            prompt = var.get("prompt")
                            try:
                                filename_id = str(uuid.uuid4())
                                print(f"Queueing Variation {v_idx+1}...")
                                task_id = asyncio.run(comfy_client.generate_video_kling(
                                    prompt=prompt,
                                    image_path=item['path'],
                                    model_name=model_name,
                                    cfg_scale=cfg_scale,
                                    mode=mode,
                                    aspect_ratio=aspect_ratio,
                                    duration=duration,
                                    filename_id=filename_id
                                ))
                                
                                # Log to DB
                                video_storage.log_execution(
                                    task_id, prompt, item['path'], 
                                    batch_id=batch_id, filename_id=filename_id
                                )
                                
                                st.session_state.batch_task_ids.append(task_id)
                                st.session_state.batch_status_map[task_id] = {'status': 'pending'}
                                print(f"Queued Task: {task_id}")
                                
                            except Exception as e:
                                print(f"Error queueing variation {v_idx+1}: {e}")
                                
                    except Exception as e:
                        print(f"Error processing image workflow: {e}")
                        
                    progress_bar.progress((img_idx + 1) / total_items)
                    
        st.success(f"Batch Queued! {len(st.session_state.batch_task_ids)} tasks submitted.")


    # --- 3. Status & Download ---
    st.subheader("3. Batch Status & Download")

    # Recover Batch logic
    with st.expander("🔄 Recover Incomplete Batch", expanded=not st.session_state.batch_task_ids):
        incomplete = video_storage.get_incomplete_batches()
        if incomplete:
            opts = {f"{b['created_at']} - {b['batch_id'][:8]}... ({b['count']} tasks)": b['batch_id'] for b in incomplete}
            sel = st.selectbox("Select Batch", list(opts.keys()))
            if st.button("Load Batch"):
                bid = opts[sel]
                execs = video_storage.get_batch_executions(bid)
                st.session_state.batch_id = bid
                st.session_state.batch_task_ids = [e['execution_id'] for e in execs]
                st.session_state.batch_status_map = {e['execution_id']: {'status': e['status'], 'path': e['video_output_path']} for e in execs}
                st.rerun()

    if st.session_state.batch_task_ids:
        st.info(f"Active Batch: `{st.session_state.batch_id}` | Tasks: {len(st.session_state.batch_task_ids)}")
        
        # Check Status Button
        if st.button("🔄 Check Status Now"):
            with st.spinner("Checking status..."):
                raw_video_dir = os.path.join(OUTPUT_DIR, "video-raw")
                os.makedirs(raw_video_dir, exist_ok=True)
                
                for task_id in st.session_state.batch_task_ids:
                    # Logic similar to original, but one-pass
                    
                    # 1. Get DB Record
                    db_rec = video_storage.get_execution(task_id)
                    local_path = db_rec.get('video_output_path')
                    status = db_rec.get('status')
                    filename_id = db_rec.get('filename_id')
                    
                    if status == 'completed' and local_path and os.path.exists(local_path):
                        st.session_state.batch_status_map[task_id] = {'status': 'completed', 'path': local_path}
                        continue
                    
                    # 2. Check Remote
                    try:
                        res = asyncio.run(comfy_client.check_status_local(task_id))
                        r_status = res.get("status")
                        
                        if r_status == "succeed":
                            # Download
                            if filename_id:
                                fname = f"ComfyUI-{filename_id}.mp4"
                            else:
                                fname = res.get("filename") or f"ComfyUI-{task_id}.mp4"
                            
                            gcs_name = f"outputs/{fname}"
                            l_path = os.path.join(raw_video_dir, fname)
                            
                            # Check GCS/Download
                            if check_blob_exists(gcs_name):
                                if not os.path.exists(l_path) or os.path.getsize(l_path) == 0:
                                    download_blob_to_file(gcs_name, l_path)
                                
                                if os.path.exists(l_path) and os.path.getsize(l_path) > 0:
                                    video_storage.update_result(task_id, l_path, 'completed')
                                    st.session_state.batch_status_map[task_id] = {'status': 'completed', 'path': l_path}
                                else:
                                    st.session_state.batch_status_map[task_id] = {'status': 'download_failed'}
                            else:
                                st.session_state.batch_status_map[task_id] = {'status': 'uploading_to_gcs'}
                                
                        elif r_status == "failed":
                             video_storage.update_result(task_id, status='failed')
                             st.session_state.batch_status_map[task_id] = {'status': 'failed'}
                        else:
                             st.session_state.batch_status_map[task_id] = {'status': 'running'}
                             
                    except Exception as e:
                        print(f"Error checking {task_id}: {e}")
                        st.session_state.batch_status_map[task_id] = {'status': 'error'}

        # Display Grid
        tasks = st.session_state.batch_task_ids
        cols = st.columns(4)
        completed_count = 0
        failed_count = 0
        
        for i, tid in enumerate(tasks):
            info = st.session_state.batch_status_map.get(tid, {'status': 'unknown'})
            s = info.get('status', 'unknown')
            
            with cols[i % 4]:
                st.caption(f"Task: {tid[-4:]}")
                if s == 'completed':
                    st.success("Completed")
                    completed_count += 1
                elif s == 'failed':
                    st.error("Failed")
                    failed_count += 1
                elif s == 'running':
                    st.warning("Running")
                else:
                    st.info(s)
        
        # Download All Button
        all_done = (completed_count + failed_count) == len(tasks) and len(tasks) > 0
        
        if all_done:
            if completed_count > 0:
                st.success("All tasks finished!")
                
                # Setup for Merge
                if "videos_to_merge" not in st.session_state:
                    st.session_state.videos_to_merge = []
                
                # Collect completed paths
                valid_paths = []
                for tid in tasks:
                    info = st.session_state.batch_status_map.get(tid)
                    if info and info.get('status') == 'completed' and info.get('path'):
                        valid_paths.append(info['path'])
                
                st.session_state.videos_to_merge = valid_paths
                
            else:
                st.error("All tasks failed.")
        else:
            st.info(f"Waiting for tasks... ({completed_count}/{len(tasks)} completed)")


    # --- 4. Merge ---
    st.subheader("4. Merge Videos")
    
    if "videos_to_merge" in st.session_state and st.session_state.videos_to_merge:
        st.write("Select videos to merge:")
        
        # Selection for merge
        selected_for_merge = []
        
        c_m = st.columns(3)
        for i, vp in enumerate(st.session_state.videos_to_merge):
            with c_m[i % 3]:
                is_sel = st.checkbox(f"Merge {i+1}", value=True, key=f"merge_sel_{i}")
                st.video(vp)
                if is_sel:
                    selected_for_merge.append(vp)
        
        if st.button("Merge Selected Videos", disabled=len(selected_for_merge) < 1):
            with st.spinner("Merging..."):
                merged_output_dir = "results"
                os.makedirs(merged_output_dir, exist_ok=True)
                batch_label = st.session_state.batch_id[-4:] if st.session_state.batch_id else "manual"
                merged_filename = f"merged_batch_{batch_label}.mp4"
                merged_path = os.path.join(merged_output_dir, merged_filename)
                
                try:
                    merge_videos(selected_for_merge, merged_path)
                    st.success("Merge Complete!")
                    st.video(merged_path)
                    st.markdown(f"**Saved:** `{merged_path}`")
                    
                    # Cleanup option
                    if st.button("Cleanup Raw Files"):
                         for vp in st.session_state.videos_to_merge:
                             try: os.remove(vp)
                             except: pass
                         st.success("Cleaned up raw files.")
                         
                except Exception as e:
                    st.error(f"Merge failed: {e}")

# --- Video Gallery Tab ---
with tab_gallery:
    st.subheader("🎥 Video Gallery")
    if st.button("🔄 Refresh Gallery"): st.rerun()
    videos = get_sorted_videos(OUTPUT_DIR)
    if not videos:
        st.info("No videos found.")
    else:
        cols_per_row = 3
        for i in range(0, len(videos), cols_per_row):
            cols = st.columns(cols_per_row)
            row_items = videos[i:i+cols_per_row]
            for idx, video_filename in enumerate(row_items):
                with cols[idx]:
                    video_path = os.path.join(OUTPUT_DIR, video_filename)
                    st.caption(video_filename)
                    st.video(video_path)
