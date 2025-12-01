import streamlit as st
import os
import shutil
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

# Page Config
st.set_page_config(page_title="CrewAI Image Workflow", layout="wide")

# Title
st.title("🚀 CrewAI Image-to-Prompt Workflow")

# Sidebar Configuration
st.sidebar.header("Configuration")
kol_persona = st.sidebar.text_input("KOL Persona", value="Jennie")

# Constants
CRAWL_DIR = "crawl"
ARCHIVE_DIR = "crawl_archive"

# Ensure directories exist
os.makedirs(CRAWL_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Session State Initialization
if "results" not in st.session_state:
    st.session_state.results = []

# --- Tabs ---
tab1, tab2 = st.tabs(["Workspace", "Archive"])

with tab1:
    # --- 1. File Upload Section ---
    st.header("1. Upload Images")
    uploaded_files = st.file_uploader("Upload images to 'crawl' folder", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'])

    if uploaded_files:
        if st.button("Save to Crawl Folder"):
            # Clear existing crawl directory
            if os.path.exists(CRAWL_DIR):
                shutil.rmtree(CRAWL_DIR)
            os.makedirs(CRAWL_DIR)
            
            # Save new files
            for uploaded_file in uploaded_files:
                file_path = os.path.join(CRAWL_DIR, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            
            st.success(f"Saved {len(uploaded_files)} images to {CRAWL_DIR}/")

    # --- 2. Captioning Workflow Section ---
    st.header("2. Captioning Flow")

    async def run_captioning():
        workflow = ImageToPromptWorkflow(verbose=True)
        results = []
        
        # Get files from crawl dir
        if not os.path.exists(CRAWL_DIR):
            st.error("Crawl directory does not exist. Please upload images first.")
            return []

        valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
        image_files = [f for f in os.listdir(CRAWL_DIR) if f.lower().endswith(valid_exts)]
        image_files.sort()
        
        if not image_files:
            st.error("No images found in crawl directory.")
            return []

        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, filename in enumerate(image_files):
            status_text.text(f"Processing {filename} ({i+1}/{len(image_files)})...")
            image_path = os.path.join(CRAWL_DIR, filename)
            
            try:
                # Run workflow
                result = await workflow.process(
                    image_path=image_path,
                    persona_name=kol_persona
                )
                
                generated_prompt = result["generated_prompt"]
                descriptive_prompt = result.get("descriptive_prompt", "")
                
                # --- Archiving Logic ---
                base_name = os.path.splitext(filename)[0]

                # 1. Save Keyword Prompt to Text File
                text_filename = f"{base_name}.txt"
                text_path = os.path.join(ARCHIVE_DIR, text_filename)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(generated_prompt)
                
                # 2. Save Descriptive Prompt to Text File
                desc_filename = f"{base_name}_description.txt"
                desc_path = os.path.join(ARCHIVE_DIR, desc_filename)
                with open(desc_path, "w", encoding="utf-8") as f:
                    f.write(descriptive_prompt)

                # 3. Move Image to Archive
                archive_image_path = os.path.join(ARCHIVE_DIR, filename)
                # Handle duplicates if necessary (simple overwrite here as per usual crawl logic)
                shutil.move(image_path, archive_image_path)
                
                # Update result to point to new location for display in this session
                result["reference_image"] = archive_image_path
                results.append(result)
                
            except Exception as e:
                st.error(f"Error processing {filename}: {e}")
                
            progress_bar.progress((i + 1) / len(image_files))
            
        status_text.text("Captioning & Archiving Complete!")
        return results

    if st.button("Start Captioning"):
        with st.spinner("Running CrewAI Workflow..."):
            # Run async function in event loop
            st.session_state.results = asyncio.run(run_captioning())
            st.success("Captioning finished! Files moved to Archive.")

    # Display Results (Current Session)
    if st.session_state.results:
        st.subheader("Session Results")
        for idx, item in enumerate(st.session_state.results):
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(item["reference_image"], caption=os.path.basename(item["reference_image"]), width='content')
            with col2:
                st.text_area(f"Keyword Prompt {idx+1}", item["generated_prompt"], height=100)
                st.text_area(f"Descriptive Prompt {idx+1}", item.get("descriptive_prompt", ""), height=100)
        
        st.divider()

with tab2:
    st.header("🗂️ Archive Gallery")
    
    if st.button("Refresh Archive"):
        st.rerun()
        
    # List all images in archive
    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if os.path.exists(ARCHIVE_DIR):
        archive_files = [f for f in os.listdir(ARCHIVE_DIR) if f.lower().endswith(valid_exts)]
        archive_files.sort(key=lambda x: os.path.getmtime(os.path.join(ARCHIVE_DIR, x)), reverse=True) # Newest first
        
        if not archive_files:
            st.info("Archive is empty.")
        else:
            st.write(f"Found {len(archive_files)} archived images.")
            
            for filename in archive_files:
                col1, col2 = st.columns([1, 2])
                
                image_path = os.path.join(ARCHIVE_DIR, filename)
                base_name = os.path.splitext(filename)[0]
                text_path = os.path.join(ARCHIVE_DIR, f"{base_name}.txt")
                desc_path = os.path.join(ARCHIVE_DIR, f"{base_name}_description.txt")
                
                with col1:
                    st.image(image_path, caption=filename, width='content')
                
                with col2:
                    # Keyword Prompt
                    prompt_text = "No prompt file found."
                    if os.path.exists(text_path):
                        with open(text_path, "r", encoding="utf-8") as f:
                            prompt_text = f.read()
                    st.text_area("Keyword Prompt", prompt_text, height=100, key=f"archive_prompt_{filename}")
                    
                    # Descriptive Prompt
                    desc_text = "No description file found."
                    if os.path.exists(desc_path):
                        with open(desc_path, "r", encoding="utf-8") as f:
                            desc_text = f.read()
                    st.text_area("Descriptive Prompt", desc_text, height=100, key=f"archive_desc_{filename}")
                
                st.divider()
    else:
        st.error(f"Archive directory '{ARCHIVE_DIR}' does not exist.")
