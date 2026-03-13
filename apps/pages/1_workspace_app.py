import streamlit as st
import os
import sys
import asyncio
import pandas as pd
import re
import contextlib
import json
import math
import logging
import threading
import time
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.config import GlobalConfig
from src.database.image_logs_storage import ImageLogsStorage
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow
from src.workflows.config_manager import WorkflowConfigManager
from src.utils.streamlit_utils import StreamlitLogger
from celery_app import celery_app

# Import Scripts for Buttons
try:
    from scripts.process_and_queue import main as run_process_script
    from scripts.populate_generated_images import main as run_populate_script
except ImportError:
    # Fallback if running from a different context where scripts module isn't resolvable directly
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from scripts.process_and_queue import main as run_process_script
    from scripts.populate_generated_images import main as run_populate_script

from src.third_parties.comfyui_client import ComfyUIClient, PERSONA_LORA_MAPPING_TURBO

# Title
st.title("🚀 Workspace: Input & Generation")

# Initialize Config Manager
config_manager = WorkflowConfigManager()

# --- Presets Configuration ---
PRESETS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'prompts', 'presets')
os.makedirs(PRESETS_DIR, exist_ok=True)

def get_available_presets():
    if not os.path.exists(PRESETS_DIR):
        return []
    # exclude the hidden sticky config
    files = [f for f in os.listdir(PRESETS_DIR) if f.endswith('.json') and not f.startswith('_')]
    return [os.path.splitext(f)[0] for f in files]

def save_preset(name, config_data):
    try:
        path = os.path.join(PRESETS_DIR, f"{name}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Failed to save preset: {e}")
        return False

def load_preset(name):
    try:
        path = os.path.join(PRESETS_DIR, f"{name}.json")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load preset: {e}")
    return None

st.sidebar.header("💾 Configuration Presets")
preset_col1, preset_col2 = st.sidebar.columns([2, 1])

# Initialize session state for preset triggers if not exists
if "preset_loaded" not in st.session_state:
    st.session_state.preset_loaded = False

# We ALWAYS load sticky defaults on a completely fresh session (when loaded_config is missing)
if "loaded_config" not in st.session_state:
    sticky_config = load_preset("_last_used")
    st.session_state.loaded_config = sticky_config if sticky_config else {}
    
    # Immediately push these values into session state keys so the UI picks them up
    # This happens only once per fresh browser reload
    for key, st_key, default in [
        ("kol_persona", "input_kol_persona", "Jennie"),
        ("vision_model_choice", "input_vision_model", "ChatGPT (gpt-4o)"),
        ("limit_choice", "input_limit", 10),
        ("variation_count", "input_variation", 1),
        ("strength_model", "input_strength", 0.8),
        ("width", "input_width", "1024"),
        ("height", "input_height", "1600"),
        ("seed_strategy", "input_seed_strategy", "random"),
        ("base_seed", "input_base_seed", 0),
    ]:
        st.session_state[st_key] = st.session_state.loaded_config.get(key, default)
        
    persona = st.session_state["input_kol_persona"]
    lora_key = f"lora_turbo_{persona}"
    st.session_state[lora_key] = st.session_state.loaded_config.get("lora_name_override", PERSONA_LORA_MAPPING_TURBO.get(persona, ""))

if "preset_load_success" not in st.session_state:
    st.session_state.preset_load_success = None
if "preset_save_success" not in st.session_state:
    st.session_state.preset_save_success = None
if "preset_save_error" not in st.session_state:
    st.session_state.preset_save_error = None

available_presets = get_available_presets()
selected_preset = st.sidebar.selectbox("Load Preset", ["Select..."] + available_presets, index=0)

def handle_load_preset():
    if selected_preset != "Select...":
        config_data = load_preset(selected_preset)
        if config_data:
            st.session_state.loaded_config = config_data
            st.session_state.preset_loaded = True
            
            # Explicitly map loaded values to widget keys so they update immediately
            if "kol_persona" in config_data:
                st.session_state.input_kol_persona = config_data["kol_persona"]
            if "vision_model_choice" in config_data:
                st.session_state.input_vision_model = config_data["vision_model_choice"]
            if "limit_choice" in config_data:
                st.session_state.input_limit = int(config_data["limit_choice"])
            if "variation_count" in config_data:
                st.session_state.input_variation = int(config_data["variation_count"])
            if "strength_model" in config_data:
                st.session_state.input_strength = float(config_data["strength_model"])
            if "width" in config_data:
                st.session_state.input_width = str(config_data["width"])
            if "height" in config_data:
                st.session_state.input_height = str(config_data["height"])
            if "seed_strategy" in config_data:
                st.session_state.input_seed_strategy = config_data["seed_strategy"]
            if "base_seed" in config_data:
                st.session_state.input_base_seed = int(config_data["base_seed"])
                
            persona = config_data.get("kol_persona", "")
            if "lora_name_override" in config_data and persona:
                st.session_state[f"lora_turbo_{persona}"] = config_data["lora_name_override"]

            st.session_state.preset_load_success = f"Loaded '{selected_preset}'"

st.sidebar.button("Load Selected Preset", on_click=handle_load_preset)

if st.session_state.preset_load_success:
    st.success(st.session_state.preset_load_success)
    st.session_state.preset_load_success = None

def handle_save_preset(name):
    if not name:
        st.session_state.preset_save_error = "Enter a name."
        return
    
    # Harvest directly from session_state for what we know has been changed
    persona_val = st.session_state.get("input_kol_persona", "Jennie")
    current_config = {
        "kol_persona": persona_val,
        "workflow_choice": "Turbo",
        "vision_model_choice": st.session_state.get("input_vision_model", "ChatGPT (gpt-4o)"),
        "limit_choice": st.session_state.get("input_limit", 10),
        "variation_count": st.session_state.get("input_variation", 1),
        "strength_model": st.session_state.get("input_strength", 0.8),
        "width": st.session_state.get("input_width", "1024"),
        "height": st.session_state.get("input_height", "1600"),
        "seed_strategy": st.session_state.get("input_seed_strategy", "random"),
        "base_seed": st.session_state.get("input_base_seed", 0),
        "lora_name_override": st.session_state.get(f"lora_turbo_{persona_val}", "")
    }
    
    if save_preset(name, current_config):
        st.session_state.preset_save_success = f"✅ Saved preset '{name}'"
    else:
        st.session_state.preset_save_error = "Failed to save preset."

with st.sidebar.expander("Save Current Preset"):
    new_preset_name = st.text_input("Preset Name", key="new_preset_name_input")
    st.button("Save Preset", on_click=handle_save_preset, args=(new_preset_name,))
    
    if st.session_state.preset_save_success:
        st.success(st.session_state.preset_save_success)
        st.session_state.preset_save_success = None
    if st.session_state.preset_save_error:
        st.error(st.session_state.preset_save_error)
        st.session_state.preset_save_error = None

# Sidebar Configuration
st.sidebar.markdown("---")
st.sidebar.header("Configuration")

# Load personas from config
available_personas = config_manager.get_personas()
if not available_personas:
    available_personas = ["Jennie"] # Fallback

# 1. Persona
kol_persona = st.sidebar.selectbox(
    "KOL Persona", 
    available_personas, 
    index=available_personas.index(st.session_state.get("input_kol_persona", "Jennie")) if st.session_state.get("input_kol_persona", "Jennie") in available_personas else 0,
    key="input_kol_persona"
)

# 2. Workflow
workflow_choice = "Turbo"

# 3. Vision Model
vm_options = [
    "ChatGPT (gpt-4o)", 
    "Grok (grok-4-1-fast-non-reasoning)",
    "Gemini 3 Flash (gemini-3-flash-preview)"
]
vision_model_choice = st.sidebar.selectbox(
    "Vision Model", 
    vm_options, 
    index=vm_options.index(st.session_state.get("input_vision_model", vm_options[0])) if st.session_state.get("input_vision_model", vm_options[0]) in vm_options else 0,
    key="input_vision_model"
)

vision_model = "gpt-4o"
if "Grok" in vision_model_choice:
    vision_model = "grok-4-1-fast-non-reasoning"
elif "gemini-3-flash" in vision_model_choice:
    vision_model = "gemini-3-flash-preview"

# 4. Limits & Strength
limit_choice = st.sidebar.number_input("Batch Limit", min_value=1, max_value=1000, value=int(st.session_state.get("input_limit", 10)), key="input_limit")
variation_count = st.sidebar.number_input("Variations per Image", min_value=1, max_value=5, value=int(st.session_state.get("input_variation", 1)), help="Number of different prompts to generate from each image analysis.", key="input_variation")
strength_model = st.sidebar.slider("Model Strength", min_value=0.0, max_value=2.0, value=float(st.session_state.get("input_strength", 0.8)), step=0.1, key="input_strength")

# LoRA Configuration
st.sidebar.subheader("LoRA Configuration")

LORA_OPTIONS = [
    "khiemle__xz-comfy__jennie_turbo_v4.safetensors",
    "khiemle__xz-comfy__jennie_turbo_outdoor_v1.safetensors",
    "khiemle__xz-comfy__jennie_turbo_indoor_v1.safetensors",
    "khiemle__xz-comfy__jennie_turbo_selfie_v2.safetensors",
    "khiemle__xz-comfy__sephera_turbo_v6.safetensors",
    "khiemle__xz-comfy__sephera_turbo_v2_gymer.safetensors",
    "khiemle__xz-comfy__emi_turbo_v2.safetensors",
    "khiemle__xz-comfy__roxie_v3.safetensors"
]

# Ensure the dynamically expected LoRA key exists when changing Persona
current_lora_key = f"lora_turbo_{kol_persona}"
current_lora_val = st.session_state.get(current_lora_key)
if not current_lora_val:
    mapped_default = PERSONA_LORA_MAPPING_TURBO.get(kol_persona, LORA_OPTIONS[0])
    st.session_state[current_lora_key] = mapped_default
    current_lora_val = mapped_default

if current_lora_val not in LORA_OPTIONS:
    LORA_OPTIONS.insert(0, current_lora_val)

def format_lora_name(name):
    return name.split("__")[-1] if "__" in name else name

# Display selectbox tied directly to its dynamically generated key
lora_name_override = st.sidebar.selectbox(
    "LoRA Name", 
    options=LORA_OPTIONS,
    format_func=format_lora_name,
    index=LORA_OPTIONS.index(current_lora_val) if current_lora_val in LORA_OPTIONS else 0,
    key=current_lora_key
)

# Dimensions Configuration
width = st.sidebar.text_input("Width", value=str(st.session_state.get("input_width", "1024")), key="input_width")
height = st.sidebar.text_input("Height", value=str(st.session_state.get("input_height", "1600")), key="input_height")

# Seed Configuration
seed_opts = ["random", "fixed"]
seed_strategy = st.sidebar.selectbox(
    "Seed Strategy", 
    seed_opts, 
    index=seed_opts.index(st.session_state.get("input_seed_strategy", "random")) if st.session_state.get("input_seed_strategy", "random") in seed_opts else 0,
    key="input_seed_strategy"
)

base_seed = 0
if seed_strategy == "fixed":
    base_seed = st.sidebar.number_input("Base Seed", min_value=0, value=int(st.session_state.get("input_base_seed", 0)), step=1, key="input_base_seed")

# --- Save Sticky Defaults at end of config block ---
# Always update the sticky default preset so values persist across reruns/reloads
sticky_persona = st.session_state.get("input_kol_persona", kol_persona)
sticky_config = {
    "kol_persona": sticky_persona,
    "workflow_choice": "Turbo",
    "vision_model_choice": st.session_state.get("input_vision_model", vision_model_choice),
    "limit_choice": st.session_state.get("input_limit", limit_choice),
    "variation_count": st.session_state.get("input_variation", variation_count),
    "strength_model": st.session_state.get("input_strength", strength_model),
    "width": st.session_state.get("input_width", width),
    "height": st.session_state.get("input_height", height),
    "seed_strategy": st.session_state.get("input_seed_strategy", seed_strategy),
    "base_seed": st.session_state.get("input_base_seed", base_seed),
    "lora_name_override": st.session_state.get(f"lora_turbo_{sticky_persona}", lora_name_override)
}
save_preset("_last_used", sticky_config)
# Reset preset loaded flag so manual widget interactions become the new default
st.session_state.preset_loaded = False 

# Debug View
if st.sidebar.checkbox("Show Debug Config"):
    st.sidebar.write("Loaded Config Data:", st.session_state.get("loaded_config", {}))
    # Filter session state for input keys
    debug_state = {k: v for k, v in st.session_state.items() if k.startswith("input_") or k.startswith("lora_")}
    st.sidebar.write("Current Session State:", debug_state)

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


class StreamlitLogHandler(logging.Handler):
    def __init__(self, streamlit_logger):
        super().__init__()
        self.streamlit_logger = streamlit_logger

    def emit(self, record):
        try:
            msg = self.format(record)
            self.streamlit_logger.write(msg + "\n")
        except Exception:
            self.handleError(record)

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
    
    # Header with Add Button
    col_header_1, col_header_2 = st.columns([3, 1])
    with col_header_1:
         # Select Persona Type to Edit
        available_types = config_manager.get_persona_types()
        selected_type_for_editor = st.selectbox("Select Persona Type Template to Edit", available_types, key="editor_type_select")
    
    with col_header_2:
        st.write("") # Vertical spacer
        st.write("") 
        # Toggle creation form
        if "show_create_type" not in st.session_state:
            st.session_state.show_create_type = False
            
        if st.button("➕ New Type"):
            st.session_state.show_create_type = not st.session_state.show_create_type

    # Creation Form
    if st.session_state.show_create_type:
        with st.form("create_type_form"):
            st.write("#### Create New Persona Type")
            st.caption("This will create a new folder in `prompts/templates/` with default empty text files.")
            new_type_name = st.text_input("New Type Name (e.g. 'tech_guru')")
            
            if st.form_submit_button("Create & Initialize"):
                if new_type_name and new_type_name.strip():
                    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', new_type_name.strip())
                    if safe_name:
                        if config_manager.create_persona_template_structure(safe_name):
                            st.success(f"✅ Created type '{safe_name}'! Refreshing...")
                            st.session_state.show_create_type = False
                            st.rerun()
                        else:
                            st.error(f"Failed to create '{safe_name}'. Directory might already exist.")
                    else:
                        st.error("Invalid name. Use alphanumeric characters, underscores, or hyphens.")
                else:
                    st.warning("Please enter a name.")

    col_edit, col_test = st.columns([1.5, 1])
    
    # Paths - Dynamic based on selected type
    base_workflow_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'prompts', 'templates', selected_type_for_editor)
    
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
                content_analyst_agent = st.text_area("Analyst Backstory", value=load_content(path_analyst_agent), height=400, key=f"editor_analyst_agent_{selected_type_for_editor}")
                
            with tab_analyst_task:
                st.caption("The exact instructions for the Image Analysis task. Use `{image_path}` as placeholder.")
                content_analyst_task = st.text_area("Analyst Task", value=load_content(path_analyst_task), height=400, key=f"editor_analyst_task_{selected_type_for_editor}")
            
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
                content_turbo_agent = st.text_area("Turbo Agent Backstory", value=load_content(path_turbo_agent), height=400, key=f"editor_turbo_agent_{selected_type_for_editor}")
            
            with tab_turbo_task:
                st.caption("Construct the Prompt Generation Task Description (Template).")
                # Sub-tabs for the components
                sub_fw, sub_cs, sub_ex = st.tabs(["Framework", "Constraints", "Example"])
                
                with sub_fw:
                    content_fw = st.text_area("Framework", value=load_content(path_framework), height=300, key=f"editor_fw_{selected_type_for_editor}", label_visibility="collapsed")
                with sub_cs:
                    content_cs = st.text_area("Constraints", value=load_content(path_constraints), height=300, key=f"editor_cs_{selected_type_for_editor}", label_visibility="collapsed")
                with sub_ex:
                    content_ex = st.text_area("Example", value=load_content(path_example), height=300, key=f"editor_ex_{selected_type_for_editor}", label_visibility="collapsed")

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
                    temp_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'temp_test')
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
                            workflow_type="turbo",
                            vision_model=vision_model
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

# --- 1. Input Configuration (Sorted Images) ---
st.header("1. Input Configuration & Management")
st.info(f"Monitoring Input Directory: `{INPUT_DIR}`")

# Helper to count files
def count_files_in_input():
    if os.path.exists(INPUT_DIR):
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
        return len([f for f in os.listdir(INPUT_DIR) if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(INPUT_DIR, f))])
    return 0

# Metric
input_count_placeholder = st.empty()
input_count_placeholder.metric("Images Remaining in Sorted Folder", count_files_in_input())

# -- Sorted Images Panel --
valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
all_files = []
if os.path.exists(INPUT_DIR):
    all_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(INPUT_DIR, f))]
    all_files.sort()

with st.expander("📂 Manage Sorted Images", expanded=True):
    if not all_files:
        st.write("No images in Sorted folder.")
    else:
        # Pagination
        items_per_page = 12
        total_pages = math.ceil(len(all_files) / items_per_page)
        
        if "sorted_page" not in st.session_state:
            st.session_state.sorted_page = 1
            
        col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])
        with col_pag1:
            if st.button("Previous", disabled=st.session_state.sorted_page <= 1):
                st.session_state.sorted_page -= 1
                st.rerun()
        with col_pag2:
            st.markdown(f"**Page {st.session_state.sorted_page} of {total_pages}** ({len(all_files)} images)")
        with col_pag3:
            if st.button("Next", disabled=st.session_state.sorted_page >= total_pages):
                st.session_state.sorted_page += 1
                st.rerun()
                
        # Slice files
        start_idx = (st.session_state.sorted_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_batch = all_files[start_idx:end_idx]
        
        # Grid Display with Selection
        # We use a form to handle selection
        with st.form("sorted_images_form"):
            # Create a 4-column grid
            cols = st.columns(4)
            selected_images = []
            
            # Since st.image loads the image, for large folders this is okay because we paginate
            for i, filename in enumerate(current_batch):
                col = cols[i % 4]
                file_path = os.path.join(INPUT_DIR, filename)
                with col:
                    st.image(file_path, width='stretch')
                    if st.checkbox(f"Select {filename}", key=f"sel_{filename}"):
                        selected_images.append(filename)
            
            st.markdown("---")
            if st.form_submit_button("🗑️ Delete Selected"):
                if selected_images:
                    count = 0
                    for img_name in selected_images:
                        try:
                            os.remove(os.path.join(INPUT_DIR, img_name))
                            count += 1
                        except Exception as e:
                            st.error(f"Failed to delete {img_name}: {e}")
                    st.success(f"Deleted {count} images.")
                    st.rerun()
                else:
                    st.warning("No images selected.")

# Optional Upload Logic
with st.expander("Upload Images to Input Directory (Optional)"):
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    uploaded_files = st.file_uploader("Upload images to process", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'], key=f"uploader_{st.session_state.uploader_key}")
    if uploaded_files:
        col_up_save, col_up_clear = st.columns([1, 1])
        with col_up_save:
            if st.button("Save to Input Directory"):
                for uploaded_file in uploaded_files:
                    file_path = os.path.join(INPUT_DIR, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                st.success(f"Saved {len(uploaded_files)} images to {INPUT_DIR}.")
                # Update count immediately after upload
                input_count_placeholder.metric("Images Remaining in Sorted Folder", count_files_in_input())
                
                # Increment key to clear uploader
                st.session_state.uploader_key += 1
                st.rerun()

        with col_up_clear:
            if st.button("Clear Uploads"):
                st.session_state.uploader_key += 1
                st.rerun()

# --- Queue & Status Section ---
st.header("📊 System Status")

col_q1, col_q2 = st.columns(2)

with col_q1:
    st.subheader("ComfyUI Queue")
    # Fetch queue
    try:
        client = ComfyUIClient() # Initialize client
        queue_data = asyncio.run(client.get_queue())
        
        running = queue_data.get("queue_running", [])
        pending = queue_data.get("queue_pending", [])
        
        st.metric("Running Jobs", len(running))
        st.metric("Pending Jobs", len(pending))
        
        if running:
            st.markdown("#### 🏃 Running")
            for job in running:
                # job usually is [prompt_id, prompt_dict, extra_info_dict]
                job_id = job[0] if isinstance(job, list) and len(job)>0 else "Unknown"
                st.code(f"Job ID: {job_id}")
                
        if pending:
            st.markdown("#### ⏳ Pending (Next 5)")
            for i, job in enumerate(pending[:5]):
                job_id = job[0] if isinstance(job, list) and len(job)>0 else "Unknown"
                st.text(f"{i+1}. Job ID: {job_id}")
            if len(pending) > 5:
                st.caption(f"... and {len(pending)-5} more")
                
    except Exception as e:
        st.error(f"Failed to fetch ComfyUI queue: {e}")

with col_q2:
    st.subheader("Recent Executions (DB)")
    recent_executions = storage.get_recent_executions(limit=10)
    if recent_executions:
        # Convert to DataFrame for cleaner display
        df = pd.DataFrame(recent_executions)
        # Select relevant columns
        cols_to_show = ['id', 'execution_id', 'status', 'created_at']
        if 'image_ref_path' in df.columns:
            cols_to_show.append('image_ref_path')
        
        st.dataframe(df[cols_to_show], width='stretch', height=300)
        
        if st.button("Refresh Status", key="refresh_status_gen"):
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
        with st.spinner("Preparing tasks..."):
            try:
                def on_progress(filename=None):
                    count = count_files_in_input()
                    input_count_placeholder.metric("Images Remaining in Sorted Folder", count)
                
                queued_task_ids = asyncio.run(run_process_script(
                    persona=kol_persona, 
                    workflow_type=workflow_choice.lower(),
                    limit=limit_choice,
                    progress_callback=on_progress,
                    strength_model=str(strength_model),
                    seed_strategy=seed_strategy,
                    base_seed=base_seed,
                    width=width,
                    height=height,
                    vision_model=vision_model,
                    lora_name=lora_name_override,
                    variation_count=variation_count
                ))
                
                if not queued_task_ids:
                    st.warning("No images found to process. Check your Input Directory.")
                else:
                    # Initialize or append to session state
                    if "active_batch" not in st.session_state:
                        st.session_state.active_batch = {
                            "tasks": [],
                            "config": {}
                        }
                    st.session_state.active_batch["tasks"].extend(queued_task_ids)
                    
                    # Store current config to show in the UI banner
                    st.session_state.active_batch["config"] = {
                        "persona": kol_persona,
                        "workflow": workflow_choice,
                        "vision": vision_model_choice,
                        "limit": limit_choice,
                        "variations": variation_count,
                        "queued_count": len(queued_task_ids)
                    }
                    st.success(f"Successfully queued {len(queued_task_ids)} images for processing!")
            except Exception as e:
                st.error(f"Error during queueing: {e}")

    # Helper: Auto-refresh manually (if active tasks exist)
    if st.session_state.get("active_batch", {}).get("tasks"):
        st.button("🔄 Refresh Task Status", width='stretch')

    # UI Banner: Current Batch Details
    batch_state = st.session_state.get("active_batch", {})
    all_tasks = batch_state.get("tasks", [])
    
    if all_tasks:
        config = batch_state.get("config", {})
        
        st.markdown("### 📋 Current Batch Details")
        st.info(f"**Persona:** {config.get('persona')} | **Workflow:** {config.get('workflow')} | **Vision:** {config.get('vision')}\n\n"
                f"**Images Queued:** {config.get('queued_count')} | **Variations per Image:** {config.get('variations')}")
        
        st.markdown("[🔍 View Full Celery Dashboard (Flower)](http://localhost:5555)")
        st.markdown("---")
        
        # Calculate Overarching Progress
        completed_count = 0
        active_tasks = []
        
        task_results_to_render = []
        
        # Gather states
        for task_id in all_tasks:
            result = celery_app.AsyncResult(task_id)
            if result.ready():
                completed_count += 1
            else:
                active_tasks.append(task_id)
            
            task_results_to_render.append((task_id, result))
            
        # Display General Progress Bar
        total_tasks = len(all_tasks)
        general_progress = completed_count / total_tasks if total_tasks > 0 else 1.0
        
        st.markdown(f"**Overall Progress:** {completed_count} / {total_tasks} Images Done")
        st.progress(general_progress)
        
        st.markdown("---")
        st.markdown("### 🚦 Detailed Task Status")
        
        # Status Blocks Render
        for idx, (task_id, result) in enumerate(task_results_to_render):
            st.markdown(f"**Task {idx + 1}:** `{task_id[:8]}...`")
            
            # Extract state details
            state = result.state
            info = result.info if isinstance(result.info, dict) else {}
            
            # Helper logic to determine what block is lit
            # We map states to 4 blocks: STARTING (1), GENERATING_PROMPT (2), QUEUEING_COMFY (3), SUCCESS (4)
            # If state is FAILURE, all blocks red or something similar
            
            block1_style = "⚪"
            block2_style = "⚪"
            block3_style = "⚪"
            block4_style = "⚪"
            
            error_msg = None
            
            if state == "SUCCESS":
                block1_style = "🟢"
                block2_style = "🟢"
                block3_style = "🟢"
                block4_style = "✅"
            elif state == "FAILURE":
                block1_style = "🔴"
                block2_style = "🔴"
                block3_style = "🔴"
                block4_style = "❌"
                error_msg = str(result.result)
            elif state == "QUEUEING_COMFY":
                block1_style = "🟢"
                block2_style = "🟢"
                block3_style = "🔵"
            elif state == "GENERATING_PROMPT":
                block1_style = "🟢"
                block2_style = "🔵"
            elif state == "STARTING" or state == "PROCESSING":
                block1_style = "🔵"
            elif state == "PENDING":
                # Waiting in Redis Queue before worker picks it up
                block1_style = "🟡"
            
            # Render Blocks using columns
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                st.markdown(f"{block1_style} **1. Queued & Init**")
            with c2:
                st.markdown(f"{block2_style} **2. AI Prompting**")
            with c3:
                st.markdown(f"{block3_style} **3. ComfyUI Render**")
            with c4:
                st.markdown(f"{block4_style} **4. Complete**")
                
            if error_msg:
                st.error(f"Error: {error_msg}")
            elif not result.ready() and state != "PENDING":
                status_text = info.get('status', 'Processing...')
                st.caption(f"_{status_text}_")
            
            st.divider()

        if st.button("Clear Completed from List"):
            st.session_state.active_batch["tasks"] = active_tasks
            if not active_tasks:
                st.session_state.active_batch = {}
            st.rerun()

with col2:
    st.subheader("Step 2: Auto-Download Results")
    st.markdown(f"Checks status of queued items and saves completed images to `{OUTPUT_DIR}`.")
    
    st.info("🔄 **Auto-check is active.**\n\nThe system automatically checks for completed images every 1 minute in the background. You don't need to do anything.")
    
    with st.expander("🛠️ Manual Check & Logs", expanded=False):
        log_populate_placeholder = st.empty()
        log_populate_placeholder.info("Logs for manual populating will appear here...")
        
        if st.button("Force Check Now", type="secondary"):
            with st.spinner("Checking ComfyUI Cloud for completed images..."):
                try:
                    logger_pop = StreamlitLogger(log_populate_placeholder)
                    with contextlib.redirect_stdout(logger_pop), contextlib.redirect_stderr(logger_pop):
                        # Use our own logger to capture
                        import logging
                        pop_logger = logging.getLogger("PopulateImages")
                        
                        # Add Streamlit handler
                        sl_handler = StreamlitLogHandler(logger_pop)
                        sl_handler.setFormatter(logging.Formatter('%(message)s'))
                        pop_logger.addHandler(sl_handler)
                        
                        try:
                            asyncio.run(run_populate_script())
                        finally:
                            pop_logger.removeHandler(sl_handler)
                            
                    st.success("Manual check complete!")
                except Exception as e:
                    st.error(f"Error checking for downloads: {e}")

    st.markdown("### 📥 Recently Downloaded")
    # Fetch recent completed and downloaded from DB
    completed_executions = [exc for exc in storage.get_all_completed_executions() if exc.get('result_image_path')]
    # Sort by updated_at or created_at
    completed_executions.sort(key=lambda x: x.get('updated_at', x.get('created_at', '')), reverse=True)
    recent_downloads = completed_executions[:5]
    
    if recent_downloads:
        for exc in recent_downloads:
            fname = os.path.basename(exc['result_image_path'])
            st.markdown(f"✅ `{fname}` *(Execution: {exc['execution_id'][:8]}...)*")
    else:
        st.info("No recently downloaded images found.")
