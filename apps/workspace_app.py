import streamlit as st
import os
import sys
import asyncio
import pandas as pd

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.database.image_logs_storage import ImageLogsStorage
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

# Import Scripts for Buttons
try:
    from scripts.process_and_queue import main as run_process_script
    from scripts.populate_generated_images import main as run_populate_script
except ImportError:
    # Fallback if running from a different context where scripts module isn't resolvable directly
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
    from scripts.process_and_queue import main as run_process_script
    from scripts.populate_generated_images import main as run_populate_script

# Page Config
st.set_page_config(page_title="Workspace - CrewAI Image Workflow", layout="wide")

# Title
st.title("🚀 Workspace: Input & Generation")

# Sidebar Configuration
st.sidebar.header("Configuration")
kol_persona = st.sidebar.selectbox("KOL Persona", ["Jennie", "Sephera", "Mika", "Nya", "Emi", "Roxie"])
workflow_choice = st.sidebar.selectbox("Workflow Type", ["Turbo", "WAN2.2"])
limit_choice = st.sidebar.number_input("Batch Limit", min_value=1, max_value=1000, value=10)

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

# --- Turbo Agent Studio ---
with st.expander("⚙️ Turbo Agent Studio", expanded=False):
    st.info("Edit the instructions for the Turbo Agent and test immediately without queuing.")
    
    col_edit, col_test = st.columns(2)
    
    # Paths
    base_workflow_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'workflows')
    path_framework = os.path.join(base_workflow_dir, 'turbo_framework.txt')
    path_constraints = os.path.join(base_workflow_dir, 'turbo_constraints.txt')
    path_example = os.path.join(base_workflow_dir, 'turbo_example.txt')
    path_compiled = os.path.join(base_workflow_dir, 'turbo_prompt_template.txt')
    
    # -- Editor --
    with col_edit:
        st.subheader("📝 Prompt Editor")
        
        def load_content(path):
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return f.read()
                except:
                    return ""
            return ""

        # Tabs for structural editing
        tab_fw, tab_cs, tab_ex = st.tabs(["Framework", "Constraints", "Example"])
        
        with tab_fw:
            st.caption("The core logical flow and 11-point framework.")
            content_fw = st.text_area("Framework", value=load_content(path_framework), height=500, key="editor_fw", label_visibility="collapsed")
        
        with tab_cs:
            st.caption("Detailed constraints, requirements, and output format.")
            content_cs = st.text_area("Constraints", value=load_content(path_constraints), height=500, key="editor_cs", label_visibility="collapsed")
            
        with tab_ex:
            st.caption("The full example output used for few-shot prompting.")
            content_ex = st.text_area("Example", value=load_content(path_example), height=500, key="editor_ex", label_visibility="collapsed")

        # Save Logic
        if st.button("Save Configuration"):
            try:
                # 1. Save individual parts
                with open(path_framework, 'w', encoding='utf-8') as f: f.write(content_fw)
                with open(path_constraints, 'w', encoding='utf-8') as f: f.write(content_cs)
                with open(path_example, 'w', encoding='utf-8') as f: f.write(content_ex)
                
                # 2. Compile into the single template file
                # Join with newlines to ensure separation between sections
                compiled_content = content_fw + "\n" + content_cs + "\n" + content_ex
                
                with open(path_compiled, 'w', encoding='utf-8') as f:
                    f.write(compiled_content)
                    
                st.success("✅ Saved & Compiled! 'turbo_prompt_template.txt' updated.")
            except Exception as e:
                st.error(f"Failed to save: {e}")

    # -- Tester --
    with col_test:
        st.subheader("🧪 Live Tester")
        st.markdown(f"**Persona:** {kol_persona}")
        st.caption("Using 'Turbo' workflow logic.")
        
        test_image = st.file_uploader("Upload a test image", type=['png', 'jpg', 'jpeg', 'webp'], key="test_uploader")
        
        if test_image and st.button("Run Test Generation"):
            with st.spinner("Analyzing and Generating Prompt..."):
                try:
                    # Save temp file
                    temp_dir = os.path.join(os.path.dirname(__file__), '..', 'temp_test')
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, test_image.name)
                    
                    with open(temp_path, "wb") as f:
                        f.write(test_image.getbuffer())
                        
                    # Initialize Workflow
                    workflow = ImageToPromptWorkflow(verbose=False)
                    
                    # Run Process
                    result = asyncio.run(workflow.process(
                        image_path=temp_path,
                        persona_name=kol_persona,
                        workflow_type="turbo" 
                    ))
                    
                    generated_prompt = result.get('generated_prompt', "No prompt generated.")
                    
                    st.success("Generation Complete!")
                    st.text_area("Generated Prompt", value=generated_prompt, height=400)
                    
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        
                except Exception as e:
                    st.error(f"Test Run Failed: {e}")

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
            except Exception as e:
                st.error(f"Failed to populate results: {e}")
