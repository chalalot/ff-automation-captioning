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
import json

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.workflows.video_storyboard_workflow import VideoStoryboardWorkflow
from src.workflows.music_analysis_workflow import MusicAnalysisWorkflow
from src.utils.streamlit_utils import get_sorted_images, StreamlitLogger
from src.database.video_logs_storage import VideoLogsStorage
from src.third_parties.gcs_client import check_blob_exists, download_blob_to_file, upload_bytes_to_gcs
import src.utils.video_utils
import importlib
importlib.reload(src.utils.video_utils)
from src.utils.video_utils import merge_videos
from src.third_parties.kling_client import KlingClient
from streamlit_sortables import sort_items
from moviepy import VideoFileClip

# Initialize Storage
video_storage = VideoLogsStorage()

# Page Config
st.set_page_config(page_title="Video - CrewAI Image Workflow", layout="wide")

st.title("🎬 Video Storyboard & Generation")

# Constants
INPUT_DIR = GlobalConfig.INPUT_DIR
OUTPUT_DIR = GlobalConfig.OUTPUT_DIR
RAW_VIDEO_DIR = os.path.join(OUTPUT_DIR, "raw_video")

# Sidebar Configuration for Persona (Removed)
kol_persona = "Jennie"

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

def generate_thumbnail(video_path, output_dir):
    try:
        os.makedirs(output_dir, exist_ok=True)
        video_name = os.path.basename(video_path)
        # Handle cases where video name might not have extension or different one
        base_name = os.path.splitext(video_name)[0]
        thumb_name = f"{base_name}.jpg"
        thumb_path = os.path.join(output_dir, thumb_name)
        
        if not os.path.exists(thumb_path):
            # Generate thumbnail
            # Use context manager to ensure clip is closed
            with VideoFileClip(video_path) as clip:
                clip.save_frame(thumb_path, t=0.1)
        return thumb_path
    except Exception as e:
        # print(f"Thumbnail error for {video_path}: {e}")
        return None

# --- Tabs ---
tab_create, tab_constructor, tab_gallery, tab_song_producer = st.tabs(["Create Video", "Video Constructor", "Video Gallery", "Song Producer"])

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
            st.dataframe(df[cols_to_show], width="stretch")
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

    # --- 2. Process: Generate & Edit Prompts ---
    st.subheader("2. Generate & Edit Prompts")

    # Initialize Prompt State
    if "generated_prompts" not in st.session_state:
        st.session_state.generated_prompts = {} # { item_id: {path:..., result:...} }

    if st.button("✨ Generate Prompts", disabled=not st.session_state.selection_queue):
        st.session_state.generated_prompts = {}
        
        # Create Logger
        with st.expander("Generation Logs", expanded=True):
            with st.container(height=300):
                log_placeholder = st.empty()
                logger = StreamlitLogger(log_placeholder)
            
            progress_bar = st.progress(0)
            
            with contextlib.redirect_stdout(logger):
                total_items = len(st.session_state.selection_queue)
                
                for img_idx, item in enumerate(st.session_state.selection_queue):
                    print(f"\nProcessing Image {img_idx+1}/{total_items}: {os.path.basename(item['path'])}")
                    
                    try:
                        workflow = VideoStoryboardWorkflow(verbose=True)
                        result = workflow.process(item['path'], kol_persona, var_count=item['var_count'])
                        
                        # Store result keyed by item ID
                        st.session_state.generated_prompts[item['id']] = {
                            'path': item['path'],
                            'result': result,
                            'variations': result.get("variations", [])
                        }
                        print(f"Generated {len(result.get('variations', []))} prompts.")
                        
                    except Exception as e:
                        print(f"Error processing image workflow: {e}")
                    
                    progress_bar.progress((img_idx + 1) / total_items)
        st.success("Prompts Generated! Review them below.")

    # Display & Edit Prompts
    if st.session_state.generated_prompts:
        st.markdown("### Review Prompts")
        for item_id, data in st.session_state.generated_prompts.items():
            with st.expander(f"Prompts for: {os.path.basename(data['path'])}", expanded=True):
                c_img, c_vars = st.columns([1, 2])
                with c_img:
                    st.image(data['path'], caption="Source Image")
                
                with c_vars:
                    updated_vars = []
                    for i, var in enumerate(data['variations']):
                        st.markdown(f"**Variation {var.get('variation', i+1)}: {var.get('concept_name', '')}**")
                        new_prompt = st.text_area(
                            "Prompt", 
                            value=var.get("prompt", ""), 
                            key=f"p_{item_id}_{i}",
                            height=120
                        )
                        var['prompt'] = new_prompt
                        updated_vars.append(var)
                    
                    # Update state with edits
                    st.session_state.generated_prompts[item_id]['variations'] = updated_vars


    # --- 3. Configure, Queue & Poll ---
    st.subheader("3. Configure, Queue & Poll")
    
    # --- Presets Logic ---
    PRESETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'presets')
    PRESETS_FILE = os.path.join(PRESETS_DIR, 'kling_presets.json')
    
    def ensure_presets_dir():
        if not os.path.exists(PRESETS_DIR):
            os.makedirs(PRESETS_DIR, exist_ok=True)
            
    def load_presets():
        ensure_presets_dir()
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return {}
        return {}

    def save_preset(name, data):
        ensure_presets_dir()
        presets = load_presets()
        presets[name] = data
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2)

    # Initialize State Defaults
    defaults = {
        "k_model": "kling-v1",
        "k_mode": "std",
        "k_duration": "5",
        "k_aspect": "16:9",
        "k_cfg": 0.5,
        "k_negative": "blurry, low quality, distorted, static",
        "k_sound": False,
        "k_voice_input": ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Callback to apply preset
    def apply_preset():
        sel = st.session_state.preset_selector
        if sel and sel != "Custom":
            presets = load_presets()
            if sel in presets:
                data = presets[sel]
                # Update state
                st.session_state.k_model = data.get("model_name", "kling-v1")
                st.session_state.k_mode = data.get("mode", "std")
                st.session_state.k_duration = data.get("duration", "5")
                st.session_state.k_aspect = data.get("aspect_ratio", "16:9")
                st.session_state.k_cfg = data.get("cfg_scale", 0.5)
                st.session_state.k_negative = data.get("negative_prompt", "")
                st.session_state.k_sound = data.get("sound_enabled", False)
                st.session_state.k_voice_input = data.get("voice_input", "")


    # Configuration UI
    with st.expander("Kling AI Settings", expanded=True):
        
        # Load Presets
        all_presets = load_presets()
        preset_options = ["Custom"] + sorted(list(all_presets.keys()))
        
        c_p1, c_p2 = st.columns([3, 1])
        with c_p1:
            st.selectbox(
                "📁 Load Preset", 
                options=preset_options, 
                key="preset_selector", 
                on_change=apply_preset,
                help="Select a saved preset to auto-fill settings."
            )
        
        st.divider()
        st.caption("Configure generation parameters for Kling V2.6+")
        
        # Row 1: Model, Mode, Duration
        c1, c2, c3 = st.columns(3)
        with c1:
            model_name = st.selectbox("Model Name", ["kling-v1", "kling-v1-5", "kling-v1-6", "kling-v2-master", "kling-v2-1", "kling-v2-5-turbo", "kling-v2-6"], key="k_model")
        with c2:
            mode = st.selectbox("Generation Mode", ["std", "pro"], key="k_mode")
        with c3:
            duration = st.selectbox("Duration (s)", ["5", "10"], key="k_duration")

        # Row 2: Aspect Ratio, CFG Scale
        c4, c5 = st.columns(2)
        with c4:
            aspect_ratio = st.selectbox("Aspect Ratio", ["16:9", "9:16", "1:1"], key="k_aspect")
        with c5:
            cfg_scale = st.slider("CFG Scale", 0.0, 1.0, step=0.1, key="k_cfg", help="Guidance scale (default 0.5). V2.x often ignores this.")

        # Negative Prompt
        negative_prompt = st.text_input("Negative Prompt", key="k_negative")

        st.divider()
        
        # --- Audio & Voice (V2.6+) ---
        st.markdown("#### Audio Settings")
        # Check if model supports audio (V2.6+)
        is_v2_6 = "v2-6" in model_name or "v2.6" in model_name
        
        sound_enabled = st.toggle("Generate Sound", disabled=not is_v2_6, key="k_sound", help="Requires Kling V2.6+")
        voice_ids = []
        
        # Logic for voice input visibility
        if sound_enabled:
            v_input = st.text_input("Voice IDs (comma separated)", key="k_voice_input", help="Enter custom voice IDs (e.g. v_001). Use <<<voice_1>>> in prompt.")
            if v_input:
                voice_ids = [{"voice_id": v.strip()} for v in v_input.split(",") if v.strip()]

        st.divider()
        
        # Save Preset
        with st.popover("💾 Save Current Settings as Preset"):
            new_preset_name = st.text_input("Preset Name", placeholder="e.g., Vertical-Pro-Sound")
            if st.button("Save Preset"):
                if new_preset_name:
                    data_to_save = {
                        "model_name": model_name,
                        "mode": mode,
                        "duration": duration,
                        "aspect_ratio": aspect_ratio,
                        "cfg_scale": cfg_scale,
                        "negative_prompt": negative_prompt,
                        "sound_enabled": sound_enabled,
                        "voice_input": st.session_state.k_voice_input
                    }
                    save_preset(new_preset_name, data_to_save)
                    st.success(f"Saved: {new_preset_name}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Please enter a name.")


    # Initialize Kling Client
    try:
        kling_client = KlingClient()
        client_available = True
    except Exception as e:
        st.error(f"Failed to initialize Kling Client: {e}")
        client_available = False

    # Initialize Batch State
    if "batch_task_ids" not in st.session_state:
        st.session_state.batch_task_ids = []
    if "batch_id" not in st.session_state:
        st.session_state.batch_id = None
    if "batch_status_map" not in st.session_state:
        st.session_state.batch_status_map = {} # {task_id: {'status':..., 'path':...}}
    if "is_polling" not in st.session_state:
        st.session_state.is_polling = False

    # Queue Button
    if st.button("🚀 Queue to Generation", disabled=(not st.session_state.generated_prompts or not client_available)):
        
        # New Batch
        batch_id = str(uuid.uuid4())
        st.session_state.batch_id = batch_id
        st.session_state.batch_task_ids = []
        st.session_state.batch_status_map = {}
        
        st.write(f"Starting Batch: `{batch_id}`")
        
        # Queue Loop
        with st.status("Submitting tasks to Kling...", expanded=True) as status:
            for item_id, data in st.session_state.generated_prompts.items():
                image_path = data['path']
                variations = data['variations']
                
                for v_idx, var in enumerate(variations):
                    prompt = var.get("prompt")
                    try:
                        filename_id = str(uuid.uuid4())
                        status.write(f"Queueing: {os.path.basename(image_path)} - Var {v_idx+1}")
                        
                        # Call Kling API
                        task_id = kling_client.generate_video(
                            prompt=prompt,
                            image=image_path,
                            model_name=model_name,
                            cfg_scale=cfg_scale,
                            mode=mode,
                            aspect_ratio=aspect_ratio,
                            duration=duration,
                            negative_prompt=negative_prompt,
                            sound="on" if sound_enabled else "off",
                            voice_list=voice_ids if voice_ids else None
                        )
                        
                        # Log to DB
                        video_storage.log_execution(
                            task_id, prompt, image_path, 
                            batch_id=batch_id, filename_id=filename_id
                        )
                        
                        st.session_state.batch_task_ids.append(task_id)
                        st.session_state.batch_status_map[task_id] = {'status': 'pending'}
                        
                    except Exception as e:
                        status.write(f"❌ Error queueing variation {v_idx+1}: {e}")
            
            status.update(label="Batch Submitted!", state="complete", expanded=False)
            
        st.success(f"Batch Queued! {len(st.session_state.batch_task_ids)} tasks submitted.")
        st.session_state.is_polling = True
        st.rerun()

    
    # --- Polling & Status ---
    st.markdown("#### Batch Status")
    
    # Polling Controls
    col_p1, col_p2 = st.columns([1, 3])
    with col_p1:
        if st.session_state.is_polling:
            if st.button("⏹ Stop Polling"):
                st.session_state.is_polling = False
                st.rerun()
        else:
            if st.button("▶ Start Polling", disabled=not st.session_state.batch_task_ids):
                st.session_state.is_polling = True
                st.rerun()
    
    with col_p2:
         # Recover Batch logic
        with st.expander("🔄 Recover Incomplete Batch", expanded=False):
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
                    st.session_state.is_polling = False # Don't auto-start
                    st.rerun()

    # Display Status Grid
    if st.session_state.batch_task_ids:
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
                elif 'error' in s:
                    st.error(s)
                else:
                    st.info(s)
        
        # Check completion
        all_done = (completed_count + failed_count) == len(tasks) and len(tasks) > 0
        if all_done and st.session_state.is_polling:
             st.session_state.is_polling = False
             st.success("All tasks finished!")
             st.rerun()

        # Polling Logic
        if st.session_state.is_polling:
            with st.spinner(f"Polling status... ({completed_count}/{len(tasks)} done)"):
                time.sleep(5) # Poll interval
                
                raw_video_dir = RAW_VIDEO_DIR
                os.makedirs(raw_video_dir, exist_ok=True)
                
                for task_id in st.session_state.batch_task_ids:
                    # Skip if already final
                    curr_status = st.session_state.batch_status_map.get(task_id, {}).get('status')
                    if curr_status in ['completed', 'failed']:
                        continue

                    try:
                        # Get DB info first
                        db_rec = video_storage.get_execution(task_id)
                        filename_id = db_rec.get('filename_id')
                        
                        # Call Kling API
                        res = kling_client.get_video_status(task_id)
                        k_status = res.get("task_status")
                        
                        if k_status == "succeed":
                            video_url = res.get("video_url")
                            if video_url:
                                if filename_id: fname = f"Kling-{filename_id}.mp4"
                                else: fname = f"Kling-{task_id}.mp4"
                                
                                l_path = os.path.join(raw_video_dir, fname)
                                try:
                                    kling_client.download_video(video_url, l_path)
                                    if os.path.exists(l_path) and os.path.getsize(l_path) > 0:
                                        video_storage.update_result(task_id, l_path, 'completed')
                                        st.session_state.batch_status_map[task_id] = {'status': 'completed', 'path': l_path}
                                    else:
                                        st.session_state.batch_status_map[task_id] = {'status': 'download_failed'}
                                except Exception:
                                     st.session_state.batch_status_map[task_id] = {'status': 'download_error'}
                            else:
                                st.session_state.batch_status_map[task_id] = {'status': 'error_no_url'}
                                
                        elif k_status == "failed":
                             video_storage.update_result(task_id, status='failed')
                             st.session_state.batch_status_map[task_id] = {'status': 'failed'}
                        else:
                             st.session_state.batch_status_map[task_id] = {'status': 'running'}
                             
                    except Exception as e:
                        print(f"Polling error {task_id}: {e}")
                
                st.rerun()
                
        # Setup for Merge if done
        if all_done:
            # Collect completed paths
            valid_paths = []
            for tid in tasks:
                info = st.session_state.batch_status_map.get(tid)
                if info and info.get('status') == 'completed' and info.get('path'):
                    valid_paths.append(info['path'])
            st.session_state.videos_to_merge = valid_paths


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
                if os.path.exists(vp):
                    st.video(vp)
                else:
                    st.caption(f"Missing: {os.path.basename(vp)}")
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
                         st.session_state.videos_to_merge = []
                         st.success("Cleaned up raw files.")
                         st.rerun()
                         
                except Exception as e:
                    st.error(f"Merge failed: {e}")

# --- Video Constructor Tab ---
with tab_constructor:
    st.subheader("🛠️ Video Constructor")
    
    # Ensure directories
    os.makedirs(RAW_VIDEO_DIR, exist_ok=True)
    THUMB_DIR = os.path.join(OUTPUT_DIR, "thumbnails")
    
    # --- Top: Library ---
    st.markdown("### 📂 Library")
    
    # Upload & Controls
    with st.expander("Upload New Clip", expanded=False):
        uploaded_raw = st.file_uploader("Upload Clip", type=['mp4', 'mov', 'avi'], key="raw_uploader")
        if uploaded_raw:
             if st.button("Save to Library"):
                 save_path = os.path.join(RAW_VIDEO_DIR, uploaded_raw.name)
                 with open(save_path, "wb") as f:
                     f.write(uploaded_raw.getbuffer())
                 st.success("Saved!")
                 time.sleep(1)
                 st.rerun()

    # Fetch Videos
    valid_exts = ('.mp4', '.mov', '.avi')
    if os.path.exists(RAW_VIDEO_DIR):
        raw_videos = [f for f in os.listdir(RAW_VIDEO_DIR) if f.lower().endswith(valid_exts)]
        raw_videos.sort(key=lambda x: os.path.getmtime(os.path.join(RAW_VIDEO_DIR, x)), reverse=True)
    else:
        raw_videos = []
    
    # Pagination Logic
    ITEMS_PER_PAGE = 12
    if "const_lib_page" not in st.session_state: st.session_state.const_lib_page = 0
    
    total_videos = len(raw_videos)
    total_pages = max(1, (total_videos + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    
    # Navigation
    c_nav1, c_nav2, c_nav3 = st.columns([1, 6, 1])
    with c_nav1:
        if st.button("◀ Prev", key="lib_prev", disabled=st.session_state.const_lib_page == 0):
            st.session_state.const_lib_page -= 1
            st.rerun()
    with c_nav2:
        st.caption(f"Page {st.session_state.const_lib_page + 1} of {total_pages} ({total_videos} clips)")
    with c_nav3:
        if st.button("Next ▶", key="lib_next", disabled=st.session_state.const_lib_page >= total_pages - 1):
            st.session_state.const_lib_page += 1
            st.rerun()
    
    # Grid Display
    start_idx = st.session_state.const_lib_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_batch = raw_videos[start_idx:end_idx]
    
    if not current_batch:
        st.info("No videos found in library.")
    else:
        # Fixed 6-column grid for consistent card size
        cols = st.columns(6)
        for i, v_file in enumerate(current_batch):
            v_path = os.path.join(RAW_VIDEO_DIR, v_file)
            
            with cols[i % 6]:
                with st.container(border=True):
                    # Direct Video Preview
                    st.video(v_path)
                    
                    # Truncate filename if too long for card
                    display_name = (v_file[:15] + '..') if len(v_file) > 18 else v_file
                    st.caption(f"**{display_name}**")
                    
                    # Add Action
                    if st.button("➕ Add", key=f"add_{v_file}", use_container_width=True):
                         if "track_videos" not in st.session_state: st.session_state.track_videos = []
                         st.session_state.track_videos.append(v_file)
                         st.toast(f"Added {v_file}")

    st.divider()

    # --- Bottom: Timeline Track ---
    st.markdown("### 🎬 Timeline Track")
    
    if "track_videos" not in st.session_state: st.session_state.track_videos = []
    
    if not st.session_state.track_videos:
        st.info("Timeline is empty. Add clips from the Library above.")
    else:
        # Sortable List with Compact Labels
        st.caption("Drag items below to reorder sequence:")
        
        # Create mapping: Label -> (OriginalIndex, Filename) to handle duplicates and reconstruction
        # We assume uniqueness of items by index for sorting purposes if needed, but sort_items creates a new order
        # To handle duplicates (e.g. same video added twice), we need unique labels.
        # We append a hidden ID or just the original index to the label?
        # Label format: "{OriginalIndex}. ..{Last4Chars}"
        
        current_track = st.session_state.track_videos
        labels = []
        label_map = {} # label -> filename
        
        for idx, v_file in enumerate(current_track):
            name_no_ext = os.path.splitext(v_file)[0]
            short_suffix = name_no_ext[-4:] if len(name_no_ext) > 4 else name_no_ext
            # Use a unique prefix (idx) to ensure every list item is distinct for the sorter
            # This allows reordering "1. ..AB" and "2. ..AB" effectively.
            label = f"{idx+1}. ..{short_suffix}"
            labels.append(label)
            label_map[label] = v_file

        sorted_labels = sort_items(labels)
        
        # Reconstruct track from sorted labels
        new_track_order = [label_map[lbl] for lbl in sorted_labels]
        st.session_state.track_videos = new_track_order
        
        st.write("") # Spacer
        
        # Visual Filmstrip (Fixed Grid)
        st.caption("Sequence Preview & Edit:")
        # Use 8 columns for smaller filmstrip cards
        f_cols = st.columns(6)
        
        # We iterate over the NEW sorted track
        videos_to_remove_indices = []
        
        for i, v_file in enumerate(st.session_state.track_videos):
            v_path = os.path.join(RAW_VIDEO_DIR, v_file)
            thumb_path = generate_thumbnail(v_path, THUMB_DIR)
            
            # Calculate column index (wrapping)
            col_idx = i % 8
            # If wrapping to new row, create new columns
            if col_idx == 0 and i > 0:
                f_cols = st.columns(8)
            
            with f_cols[col_idx]:
                 with st.container(border=True):
                    st.caption(f"#{i+1}")
                    if thumb_path and os.path.exists(thumb_path):
                        st.image(thumb_path, use_container_width=True)
                    else:
                        st.caption("No Preview")
                    
                    # Remove Button
                    if st.button("🗑️", key=f"rem_track_{i}", help="Remove from track"):
                        videos_to_remove_indices.append(i)

        # Process removals
        if videos_to_remove_indices:
            # Remove in reverse order to avoid index shift issues
            for idx in sorted(videos_to_remove_indices, reverse=True):
                st.session_state.track_videos.pop(idx)
            st.rerun()
        
        st.divider()
        
        # Transition Configuration
        st.caption("Merge Configuration:")
        c_t1, c_t2 = st.columns(2)
        with c_t1:
            trans_type = st.selectbox("Transition Style", ["Crossfade", "Fade to Black", "Simple Cut"], index=0)
        with c_t2:
            trans_dur = st.slider("Transition Duration (s)", 0.1, 2.0, 0.5, step=0.1)
        
        st.divider()
        
        # Merge Actions
        ac1, ac2, ac3 = st.columns([1, 2, 1])
        with ac2:
            if st.button("🎥 Merge Sequence", type="primary", use_container_width=True):
                 prog_bar = st.progress(0)
                 status_text = st.empty()
                 
                 def update_prog(p, **kwargs):
                     prog_bar.progress(p)
                     status_text.caption(f"Processing... {int(p*100)}%")

                 with st.spinner("Merging clips..."):
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    merged_filename = f"constructed_video_{timestamp}.mp4"
                    merged_path = os.path.join(OUTPUT_DIR, merged_filename)
                    input_paths = [os.path.join(RAW_VIDEO_DIR, f) for f in st.session_state.track_videos]
                    
                    try:
                        merge_videos(input_paths, merged_path, transition_type=trans_type, duration=trans_dur, progress_callback=update_prog)
                        prog_bar.empty()
                        status_text.empty()
                        st.success("Merge Complete!")
                        st.video(merged_path)
                        st.markdown(f"**Saved to:** `{merged_path}`")
                    except Exception as e:
                        st.error(f"Merge Failed: {e}")
        with ac3:
             if st.button("Clear Track", use_container_width=True):
                st.session_state.track_videos = []
                st.rerun()

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

# --- Song Producer Tab ---
with tab_song_producer:
    st.subheader("🎵 Song Producer")
    st.info("Upload an MP3 song to extract its vibe and lyrics using AI agents.")

    # File Uploader
    uploaded_song = st.file_uploader("Upload Song (MP3)", type=['mp3'])
    
    if uploaded_song:
        # Save temp file
        temp_dir = os.path.join(INPUT_DIR, "temp_audio")
        os.makedirs(temp_dir, exist_ok=True)
        song_path = os.path.join(temp_dir, uploaded_song.name)
        
        # Save to disk
        with open(song_path, "wb") as f:
            f.write(uploaded_song.getbuffer())
            
        st.success(f"File uploaded: {uploaded_song.name}")
        st.audio(song_path)
        
        if st.button("🚀 Analyze & Produce"):
            with st.status("Processing Song...", expanded=True) as status:
                
                # 1. Upload to GCS
                status.write("Uploading to GCS...")
                try:
                    # Use the specific bucket for audio
                    audio_bucket = os.getenv("GCS_AUDIO_BUCKET_NAME", "ff-automation")
                    
                    with open(song_path, "rb") as f:
                        file_bytes = f.read()
                        
                    # Generate a unique path in the bucket
                    # e.g. scraped-audio-host/{timestamp}_{filename}
                    ts = int(time.time())
                    gcs_path = f"scraped-audio-host/{ts}_{uploaded_song.name}"
                    
                    public_url = upload_bytes_to_gcs(
                        payload=file_bytes,
                        gcs_path=gcs_path,
                        content_type="audio/mpeg",
                        bucket_name=audio_bucket
                    )
                    status.write(f"✅ Uploaded to GCS: {public_url}")
                    
                except Exception as e:
                    status.update(label="Upload Failed", state="error")
                    st.error(f"GCS Upload Error: {e}")
                    st.stop()
                
                # 2. Run CrewAI Analysis
                status.write("Running AI Agents (Vibe & Lyrics)...")
                try:
                    workflow = MusicAnalysisWorkflow(verbose=True)
                    result = workflow.process(song_path)
                    status.write("✅ Analysis Complete")
                    
                except Exception as e:
                    status.update(label="Analysis Failed", state="error")
                    st.error(f"CrewAI Error: {e}")
                    st.stop()
                
                status.update(label="Processing Complete!", state="complete", expanded=False)
            
            # --- Display Results ---
            st.divider()
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("### 🎹 Vibe & Style")
                st.markdown(result.get("vibe", "No vibe detected."))
                
                st.markdown("### 🔗 Cloud Link")
                st.code(public_url)
                
            with c2:
                st.markdown("### 📝 Full Lyrics")
                st.text_area("Lyrics", value=result.get("lyrics", "No lyrics detected."), height=600)
