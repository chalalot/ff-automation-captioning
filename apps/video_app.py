import streamlit as st
import os
import sys
import asyncio

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.workflows.video_storyboard_workflow import VideoStoryboardWorkflow
from src.utils.streamlit_utils import get_sorted_images

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
        with st.spinner("Brainstorming Video Prompts... This may take a moment."):
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
