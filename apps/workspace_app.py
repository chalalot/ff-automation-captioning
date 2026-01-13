import streamlit as st
import os
import sys
import asyncio
import pandas as pd
import re
import contextlib
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.database.image_logs_storage import ImageLogsStorage
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow
from src.workflows.config_manager import WorkflowConfigManager
from src.utils.streamlit_utils import StreamlitLogger

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

# Initialize Config Manager
config_manager = WorkflowConfigManager()

# Sidebar Configuration
st.sidebar.header("Configuration")

# Load personas from config
available_personas = config_manager.get_personas()
if not available_personas:
    available_personas = ["Jennie"] # Fallback

kol_persona = st.sidebar.selectbox("KOL Persona", available_personas)
workflow_choice = st.sidebar.selectbox("Workflow Type", ["Turbo", "WAN2.2"])
limit_choice = st.sidebar.number_input("Batch Limit", min_value=1, max_value=1000, value=10)
strength_model = st.sidebar.slider("Model Strength", min_value=0.0, max_value=2.0, value=0.8, step=0.1)

# Seed Configuration
seed_strategy = st.sidebar.selectbox("Seed Strategy", ["random", "fixed"], index=0)
base_seed = 0
if seed_strategy == "fixed":
    base_seed = st.sidebar.number_input("Base Seed", min_value=0, value=0, step=1)

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

# --- Persona Configuration ---
with st.expander("👤 Persona Configuration", expanded=False):
    st.info("Configure specific settings for each Persona.")
    
    col_p_select, col_p_edit = st.columns([1, 2])
    
    with col_p_select:
        selected_persona_config = st.selectbox("Select Persona to Edit", available_personas, key="persona_config_select")
        
        # Load current config
        current_p_config = config_manager.get_persona_config(selected_persona_config)
        current_type = current_p_config.get("type", "instagirl")
        available_types = config_manager.get_persona_types()
        
        new_type = st.selectbox("Persona Type", available_types, index=available_types.index(current_type) if current_type in available_types else 0)
        
        current_hair_color = current_p_config.get("hair_color", "")
        new_hair_color = st.text_input("Hair Color", value=current_hair_color)

    with col_p_edit:
        current_hairstyles = current_p_config.get("hairstyles", [])
        hairstyles_text = "\n".join(current_hairstyles)
        
        new_hairstyles_text = st.text_area("Hairstyle Keywords (One per line)", value=hairstyles_text, height=200)
        
        if st.button("Save Persona Configuration"):
            new_hairstyles_list = [line.strip() for line in new_hairstyles_text.split('\n') if line.strip()]
            
            update_data = {
                "type": new_type,
                "hair_color": new_hair_color,
                "hairstyles": new_hairstyles_list
            }
            config_manager.update_persona_config(selected_persona_config, update_data)
            st.success(f"✅ Configuration for {selected_persona_config} saved!")


# --- Workflow Configuration Studio ---
with st.expander("⚙️ Workflow Configuration Studio", expanded=False):
    st.info("Edit Agent Backstories and Task Descriptions for the workflow. These are organized by 'Persona Type'.")
    
    # Select Persona Type to Edit
    available_types = config_manager.get_persona_types()
    selected_type_for_editor = st.selectbox("Select Persona Type Template to Edit", available_types, key="editor_type_select")
    
    col_edit, col_test = st.columns([1.5, 1])
    
    # Paths - Dynamic based on selected type
    base_workflow_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'workflows', 'templates', selected_type_for_editor)
    
    # Ensure directory exists (create if new type added manually but folder missing)
    if not os.path.exists(base_workflow_dir):
        st.warning(f"Template directory for '{selected_type_for_editor}' does not exist. Saving will create it.")
        os.makedirs(base_workflow_dir, exist_ok=True)

    # Turbo Paths
    path_turbo_agent = os.path.join(base_workflow_dir, 'turbo_agent.txt')
    path_framework = os.path.join(base_workflow_dir, 'turbo_framework.txt')
    path_constraints = os.path.join(base_workflow_dir, 'turbo_constraints.txt')
    path_example = os.path.join(base_workflow_dir, 'turbo_example.txt')
    path_compiled = os.path.join(base_workflow_dir, 'turbo_prompt_template.txt')
    
    # Analyst Paths
    path_analyst_agent = os.path.join(base_workflow_dir, 'analyst_agent.txt')
    path_analyst_task = os.path.join(base_workflow_dir, 'analyst_task.txt')
    
    # Helper
    def load_content(path):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                return ""
        return ""

    # -- Editor --
    with col_edit:
        st.subheader(f"📝 Editor ({selected_type_for_editor})")
        
        # Tabs for Agents
        agent_tab_analyst, agent_tab_turbo = st.tabs(["🕵️ Analyst Agent", "⚡ Turbo Agent"])
        
        # --- Analyst Agent Tab ---
        with agent_tab_analyst:
            st.markdown("### Analyst Configuration")
            
            tab_analyst_agent, tab_analyst_task = st.tabs(["Agent Backstory", "Task Description"])
            
            with tab_analyst_agent:
                st.caption("The 'Backstory' and personality of the Analyst Agent.")
                content_analyst_agent = st.text_area("Analyst Backstory", value=load_content(path_analyst_agent), height=400, key="editor_analyst_agent")
                
            with tab_analyst_task:
                st.caption("The exact instructions for the Image Analysis task. Use `{image_path}` as placeholder.")
                content_analyst_task = st.text_area("Analyst Task", value=load_content(path_analyst_task), height=400, key="editor_analyst_task")
            
            if st.button("Save Analyst Configuration", key="save_analyst"):
                try:
                    with open(path_analyst_agent, 'w', encoding='utf-8') as f: f.write(content_analyst_agent)
                    with open(path_analyst_task, 'w', encoding='utf-8') as f: f.write(content_analyst_task)
                    st.success(f"✅ Analyst configuration for '{selected_type_for_editor}' saved!")
                except Exception as e:
                    st.error(f"Failed to save: {e}")

        # --- Turbo Agent Tab ---
        with agent_tab_turbo:
            st.markdown("### Turbo Configuration")
            
            tab_turbo_agent, tab_turbo_task = st.tabs(["Agent Backstory", "Task Template"])
            
            with tab_turbo_agent:
                st.caption("The 'Backstory' and personality of the Turbo Engineer Agent.")
                content_turbo_agent = st.text_area("Turbo Agent Backstory", value=load_content(path_turbo_agent), height=400, key="editor_turbo_agent")
            
            with tab_turbo_task:
                st.caption("Construct the Prompt Generation Task Description (Template).")
                # Sub-tabs for the components
                sub_fw, sub_cs, sub_ex = st.tabs(["Framework", "Constraints", "Example"])
                
                with sub_fw:
                    content_fw = st.text_area("Framework", value=load_content(path_framework), height=300, key="editor_fw", label_visibility="collapsed")
                with sub_cs:
                    content_cs = st.text_area("Constraints", value=load_content(path_constraints), height=300, key="editor_cs", label_visibility="collapsed")
                with sub_ex:
                    content_ex = st.text_area("Example", value=load_content(path_example), height=300, key="editor_ex", label_visibility="collapsed")

            if st.button("Save Turbo Configuration", key="save_turbo"):
                try:
                    # Save Backstory
                    with open(path_turbo_agent, 'w', encoding='utf-8') as f: f.write(content_turbo_agent)
                    
                    # Save Task Template Components
                    with open(path_framework, 'w', encoding='utf-8') as f: f.write(content_fw)
                    with open(path_constraints, 'w', encoding='utf-8') as f: f.write(content_cs)
                    with open(path_example, 'w', encoding='utf-8') as f: f.write(content_ex)
                    
                    # Compile Task Template
                    compiled_content = content_fw + "\n" + content_cs + "\n" + content_ex
                    with open(path_compiled, 'w', encoding='utf-8') as f: f.write(compiled_content)
                    
                    st.success(f"✅ Turbo configuration for '{selected_type_for_editor}' saved & compiled!")
                except Exception as e:
                    st.error(f"Failed to save: {e}")

    # -- Tester --
    with col_test:
        st.subheader("🧪 Live Tester")
        st.markdown(f"**Persona:** {kol_persona}")
        
        # Display current persona type info
        p_conf = config_manager.get_persona_config(kol_persona)
        st.caption(f"Type: **{p_conf.get('type', 'Unknown')}** | Hair: {p_conf.get('hair_color', 'N/A')}")
        
        st.caption("Runs the full workflow (Analyst + Turbo) with current settings.")
        
        test_image = st.file_uploader("Upload a test image", type=['png', 'jpg', 'jpeg', 'webp'], key="test_uploader")
        
        # Log Placeholder
        with st.expander("📝 Live Agent Logs", expanded=True):
            log_placeholder = st.empty()
            log_placeholder.info("Logs will appear here during generation...")
        
        if test_image and st.button("Run Test Generation"):
            with st.spinner("Analyzing and Generating Prompt..."):
                try:
                    # Save temp file
                    temp_dir = os.path.join(os.path.dirname(__file__), '..', 'temp_test')
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, test_image.name)
                    
                    with open(temp_path, "wb") as f:
                        f.write(test_image.getbuffer())
                        
                    # Initialize Workflow with verbose=True
                    workflow = ImageToPromptWorkflow(verbose=True)
                    
                    # Setup Logger
                    logger = StreamlitLogger(log_placeholder)
                    
                    # Run Process with stdout capture
                    with contextlib.redirect_stdout(logger):
                        result = asyncio.run(workflow.process(
                            image_path=temp_path,
                            persona_name=kol_persona,
                            workflow_type="turbo" 
                        ))
                    
                    generated_prompt = result.get('generated_prompt', "No prompt generated.")
                    descriptive_prompt = result.get('descriptive_prompt', "No analysis available.")
                    
                    st.success("Generation Complete!")
                    
                    with st.expander("Show Analysis Output", expanded=False):
                        st.text_area("Analysis Output", value=descriptive_prompt, height=200)
                        
                    st.text_area("Generated Prompt", value=generated_prompt, height=400)
                    
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        
                except Exception as e:
                    st.error(f"Test Run Failed: {e}")
                    # Also print error to logs if possible
                    if 'logger' in locals():
                        logger.write(f"\nERROR: {e}")

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
                    progress_callback=on_progress,
                    strength_model=str(strength_model),
                    seed_strategy=seed_strategy,
                    base_seed=base_seed
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
