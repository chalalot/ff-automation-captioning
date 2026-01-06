import streamlit as st
import os
import sys
import asyncio
import contextlib

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.workflows.video_storyboard_workflow import VideoStoryboardWorkflow
from src.utils.streamlit_utils import get_sorted_images, StreamlitLogger

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

# --- 4. Kling AI Generation ---
st.subheader("4. Kling AI Video Generation")

from src.third_parties.kling_client import KlingClient

# Initialize Client
try:
    kling_client = KlingClient()
    client_available = True
except Exception as e:
    st.error(f"Failed to initialize Kling Client: {e}")
    client_available = False

if client_available:
    # Initialize session state for Kling
    if "kling_task_id" not in st.session_state:
        st.session_state.kling_task_id = None

    if "video_results" in st.session_state and st.session_state.video_results:
        variations = st.session_state.video_results["variations"]
        
        # Selection for Prompt
        prompt_options = {f"Variation {v['variation']}: {v['concept_name']}": v['prompt'] for v in variations}
        selected_option = st.selectbox("Select Prompt for Video Generation", list(prompt_options.keys()) + ["Custom Prompt"])
        
        if selected_option == "Custom Prompt":
            final_prompt = st.text_area("Enter Custom Prompt", value="Cinematic shot, high quality, 4k")
        else:
            final_prompt = st.text_area("Selected Prompt", value=prompt_options[selected_option])
            
        duration = st.selectbox("Duration", ["5", "10"], index=0)
        
        # 1. Queue Button
        if st.button("🚀 Queue Video Generation"):
            if not st.session_state.selected_video_source:
                st.error("No source image selected!")
            else:
                with st.spinner("Queueing task to Kling AI..."):
                    try:
                        task_id = kling_client.generate_video(
                            prompt=final_prompt,
                            image=st.session_state.selected_video_source,
                            duration=duration
                        )
                        st.session_state.kling_task_id = task_id
                        st.success(f"Task Queued! ID: {task_id}")
                    except Exception as e:
                        st.error(f"Failed to queue task: {e}")

    # Check Status Section (Always visible)
    st.markdown("### Status & Download")

    # Input for Task ID (allow manual entry or use session)
    task_id_input = st.text_input("Task ID", value=st.session_state.kling_task_id if st.session_state.kling_task_id else "")

    if st.button("🔄 Check Status & Download"):
        if not task_id_input:
            st.error("Please enter a Task ID.")
        else:
            with st.spinner(f"Checking status for {task_id_input}..."):
                try:
                    status_data = kling_client.get_video_status(task_id_input)
                    status = status_data.get("task_status")
                    
                    st.info(f"Status: **{status}**")
                    
                    if status == "succeed":
                        video_url = status_data.get("video_url")
                        if video_url:
                            st.success("Video Generated Successfully!")
                            st.video(video_url)
                            
                            # Download to video-raw
                            os.makedirs("video-raw", exist_ok=True)
                            filename = f"kling_{task_id_input}.mp4"
                            output_path = os.path.join("video-raw", filename)
                            
                            kling_client.download_video(video_url, output_path)
                            st.success(f"Downloaded to: `{output_path}`")
                            
                        else:
                            st.warning("Status is succeed but no video URL found.")
                    elif status == "failed":
                        st.error(f"Video generation failed. Message: {status_data.get('message', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error checking status: {e}")
