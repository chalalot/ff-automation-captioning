import streamlit as st
import os
import shutil
import asyncio
import sys
import zipfile
import io
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

# Import Scripts for Buttons
try:
    from scripts.queue_prompts_from_archive import main as run_queue_script
    from scripts.populate_generated_images import main as run_populate_script
except ImportError:
    # Fallback if running from a different context where scripts module isn't resolvable directly
    sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
    from scripts.queue_prompts_from_archive import main as run_queue_script
    from scripts.populate_generated_images import main as run_populate_script

# Page Config
st.set_page_config(page_title="CrewAI Image Workflow", layout="wide")

# Title
st.title("🚀 CrewAI Image-to-Prompt Workflow")

# Sidebar Configuration
st.sidebar.header("Configuration")
kol_persona = st.sidebar.text_input("KOL Persona", value="Jennie")

# Constants
base_dir = os.path.abspath(os.path.dirname(__file__))
CRAWL_DIR = os.path.join(base_dir, "crawl")
READY_DIR = os.path.join(base_dir, "ready")
ARCHIVE_DIR = os.path.join(base_dir, "crawl_archive")

# Ensure directories exist
os.makedirs(CRAWL_DIR, exist_ok=True)
os.makedirs(READY_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

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

    # --- 2. Generation Flow Section ---
    st.header("2. Generation Flow")

    # Step 1: Captioning (Generate Prompts)
    st.subheader("Step 1: Generate Prompts")
    
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
                
                # --- New Logic: Save to Ready Folder ---
                base_name = os.path.splitext(filename)[0]

                # Save Prompt to Ready Folder
                text_filename = f"{base_name}.txt"
                text_path = os.path.join(READY_DIR, text_filename)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(generated_prompt)
                
                # We leave the original image in CRAWL_DIR for now, 
                # as the populate script expects it there (or in CRAWL_DIR) to move it later.
                
                result["reference_image"] = image_path
                results.append(result)
                
            except Exception as e:
                st.error(f"Error processing {filename}: {e}")
                
            progress_bar.progress((i + 1) / len(image_files))
            
        status_text.text("Captioning Complete! Prompts saved to 'ready' folder.")
        return results

    if st.button("Generate Prompts (Step 1)"):
        with st.spinner("Generating Prompts..."):
            st.session_state.results = asyncio.run(run_captioning())
            st.success("Prompts generated and saved to 'ready'.")

    # Step 2: Queue Generation
    st.subheader("Step 2: Queue Image Generation")
    st.markdown("Reads prompts from `ready` folder and queues them in ComfyUI.")
    
    if st.button("Queue Generation (Step 2)"):
        with st.spinner("Queueing prompts..."):
            try:
                # Use asyncio.run to execute the async main function of the script
                asyncio.run(run_queue_script())
                st.success("Generation queued! Check terminal for details.")
            except Exception as e:
                st.error(f"Failed to queue generation: {e}")

    # Step 3: Populate Results
    st.subheader("Step 3: Populate & Archive Results")
    st.markdown("Checks status of queued generations. Downloads completed images and moves everything to `archive`.")
    
    if st.button("Populate Results (Step 3)"):
        with st.spinner("Checking status and downloading..."):
            try:
                asyncio.run(run_populate_script())
                st.success("Completed results populated to Archive!")
                
                # Clear session results as files have been moved to archive
                st.session_state.results = []
                st.rerun() # Refresh to show new items in Archive tab
            except Exception as e:
                st.error(f"Failed to populate results: {e}")

    # Display Results (Current Session)
    if st.session_state.results:
        st.subheader("Session Results")
        for idx, item in enumerate(st.session_state.results):
            # Check if file still exists (it might have been moved/archived)
            if not os.path.exists(item["reference_image"]):
                continue

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

    # Toggle for Compact View
    compact_view = st.toggle("Compact View (Generated Images Only)", value=False)
        
    # List all images in archive
    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    if os.path.exists(ARCHIVE_DIR):
        all_files = os.listdir(ARCHIVE_DIR)
        
        # Filter for Reference Images (exclude _generated ones)
        ref_images = [
            f for f in all_files 
            if f.lower().endswith(valid_exts) and "_generated" not in f
        ]
        
        # Sort by modification time (newest first)
        ref_images.sort(key=lambda x: os.path.getmtime(os.path.join(ARCHIVE_DIR, x)), reverse=True)
        
        # --- Download Logic ---
        approved_files = []
        for filename in ref_images:
            base_name = os.path.splitext(filename)[0]
            if st.session_state.get(f"approve_{base_name}", False):
                # Find Generated Image
                for ext in valid_exts:
                    possible_gen = os.path.join(ARCHIVE_DIR, f"{base_name}_generated{ext}")
                    if os.path.exists(possible_gen):
                        approved_files.append(possible_gen)
                        break
        
        if approved_files:
            st.info(f"Selected {len(approved_files)} images for download.")
            
            if st.button("Prepare Download ZIP"):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file_path in approved_files:
                        zf.write(file_path, arcname=os.path.basename(file_path))
                st.session_state['zip_buffer'] = zip_buffer.getvalue()
                st.success("ZIP file ready!")
            
            if 'zip_buffer' in st.session_state and st.session_state.get('zip_buffer'):
                st.download_button(
                    label="Download Approved Images (.zip)",
                    data=st.session_state['zip_buffer'],
                    file_name="approved_variations.zip",
                    mime="application/zip"
                )
        # ----------------------

        if not ref_images:
            st.info("Archive is empty.")
        else:
            st.write(f"Found {len(ref_images)} archive entries.")
            
            if compact_view:
                # --- Grid View (5 images per row) ---
                grid_items = []
                for filename in ref_images:
                    base_name = os.path.splitext(filename)[0]
                    # Find Generated Image
                    gen_path = None
                    for ext in valid_exts:
                        possible_gen = os.path.join(ARCHIVE_DIR, f"{base_name}_generated{ext}")
                        if os.path.exists(possible_gen):
                            gen_path = possible_gen
                            break
                    
                    if gen_path:
                        grid_items.append((base_name, gen_path))
                
                if not grid_items:
                    st.info("No generated images found for grid view.")
                else:
                    cols_per_row = 5
                    for i in range(0, len(grid_items), cols_per_row):
                        row_items = grid_items[i:i+cols_per_row]
                        cols = st.columns(cols_per_row)
                        for idx, (b_name, g_path) in enumerate(row_items):
                            with cols[idx]:
                                st.image(g_path, caption=os.path.basename(g_path), use_container_width=True)
                                st.checkbox("Approve", key=f"approve_{b_name}")
                                st.divider()
            
            else:
                # --- List View ---
                for filename in ref_images:
                    base_name = os.path.splitext(filename)[0]
                    
                    # Paths
                    ref_image_path = os.path.join(ARCHIVE_DIR, filename)
                    text_path = os.path.join(ARCHIVE_DIR, f"{base_name}.txt")
                    desc_path = os.path.join(ARCHIVE_DIR, f"{base_name}_description.txt")
                    
                    # Find Generated Image (could be any valid extension)
                    gen_image_path = None
                    for ext in valid_exts:
                        possible_gen = os.path.join(ARCHIVE_DIR, f"{base_name}_generated{ext}")
                        if os.path.exists(possible_gen):
                            gen_image_path = possible_gen
                            break

                    # Layout: Ref Image | Prompt & Desc | Generated Image
                    col1, col2, col3 = st.columns([1, 1.5, 1])

                    # 1. Reference Image
                    with col1:
                        st.image(ref_image_path, caption=f"Ref: {filename}", width='content')
                    
                    # 2. Prompts
                    with col2:
                        # Keyword Prompt
                        prompt_text = "No prompt file found."
                        if os.path.exists(text_path):
                            with open(text_path, "r", encoding="utf-8") as f:
                                prompt_text = f.read()
                        st.text_area("Keyword Prompt", prompt_text, height=150, key=f"archive_prompt_{filename}")
                        
                        # Descriptive Prompt (if exists)
                        if os.path.exists(desc_path):
                            with open(desc_path, "r", encoding="utf-8") as f:
                                desc_text = f.read()
                            st.text_area("Descriptive Prompt", desc_text, height=100, key=f"archive_desc_{filename}")
                    
                    # 3. Generated Image
                    with col3:
                        if gen_image_path:
                            st.image(gen_image_path, caption=f"Generated: {os.path.basename(gen_image_path)}", width='content')
                            st.checkbox("Approve", key=f"approve_{base_name}")
                        else:
                            st.info("No generated image yet.")
                    
                    st.divider()
    else:
        st.error(f"Archive directory '{ARCHIVE_DIR}' does not exist.")
