import streamlit as st
import os
import sys
import asyncio
import json
import zipfile
import io
import pandas as pd
import math
import time
import shutil
from datetime import datetime
from PIL import Image

# Path setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.config import GlobalConfig
from src.database.image_logs_storage import ImageLogsStorage
from src.third_parties.comfyui_client import ComfyUIClient
from src.utils.streamlit_utils import get_sorted_images, fetch_remote_metadata

# Constants
OUTPUT_DIR = GlobalConfig.OUTPUT_DIR
APPROVED_DIR = os.path.join(OUTPUT_DIR, "approved")
DISAPPROVED_DIR = os.path.join(OUTPUT_DIR, "disapproved")

# Ensure directories exist
os.makedirs(APPROVED_DIR, exist_ok=True)
os.makedirs(DISAPPROVED_DIR, exist_ok=True)

storage = ImageLogsStorage()
client = ComfyUIClient()

# Session State Initialization
if "results" not in st.session_state:
    st.session_state.results = []
if "selected_files" not in st.session_state:
    st.session_state.selected_files = set()
if "files_to_approve" not in st.session_state:
    st.session_state.files_to_approve = set()

# --- Helper Functions ---

def move_image(filename, source_dir, dest_dir, new_name=None):
    """
    Moves an image from source to dest, optionally renaming it.
    Returns True if successful, False otherwise.
    """
    try:
        src_path = os.path.join(source_dir, filename)
        if not os.path.exists(src_path):
            return False
            
        final_name = new_name if new_name else filename
        if not final_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            # Append extension from original if missing
            ext = os.path.splitext(filename)[1]
            final_name += ext
            
        dest_path = os.path.join(dest_dir, final_name)
        
        # Avoid overwriting
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(final_name)
            timestamp = int(time.time())
            dest_path = os.path.join(dest_dir, f"{base}_{timestamp}{ext}")
            
        shutil.move(src_path, dest_path)
        
        # Also try to move corresponding text file if it exists
        txt_src = os.path.splitext(src_path)[0] + ".txt"
        if os.path.exists(txt_src):
            txt_dest = os.path.splitext(dest_path)[0] + ".txt"
            shutil.move(txt_src, txt_dest)
            
        return True
    except Exception as e:
        st.error(f"Error moving {filename}: {e}")
        return False

@st.cache_data(ttl=5, show_spinner="Loading gallery data...")
def load_gallery_data(directory):
    """
    Fetch DB records and file list from a specific directory.
    """
    if not os.path.exists(directory):
        return []

    # 1. Fetch all completed executions for metadata lookup
    all_executions = storage.get_all_completed_executions()
    execution_map = {}
    for exc in all_executions:
        if exc['result_image_path']:
            fname = os.path.basename(exc['result_image_path'])
            execution_map[fname] = exc
    
    # 2. List files
    all_files = get_sorted_images(directory)
    
    items = []
    for f in all_files:
        full_path = os.path.join(directory, f)
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            continue # File might have been moved
            
        dt = datetime.fromtimestamp(mtime)
        date_str = dt.strftime("%Y-%m-%d")
        
        # Get Metadata
        record = execution_map.get(f)
        persona = record['persona'] if record and 'persona' in record and record['persona'] else "Unknown"
        
        # Pre-calculate Reference Image Path
        final_ref_path = None
        if record:
            ref_path = record.get('image_ref_path')
            if ref_path:
                if os.path.exists(ref_path):
                    final_ref_path = ref_path
                else:
                    fixed_path = ref_path.replace('\\', '/')
                    if os.path.exists(fixed_path):
                        final_ref_path = fixed_path
                    else:
                        filename = os.path.basename(fixed_path)
                        fallback = os.path.join(GlobalConfig.PROCESSED_DIR, filename)
                        if os.path.exists(fallback):
                            final_ref_path = fallback

        items.append({
            "filename": f,
            "path": full_path,
            "mtime": mtime,
            "date": date_str,
            "persona": persona,
            "record": record,
            "ref_path": final_ref_path
        })
    return items

@st.cache_data(ttl=10, show_spinner=False)
def get_all_stats():
    """
    Scans all folders to build aggregate statistics.
    Returns a DataFrame.
    """
    stats = {} # Date -> {'total': 0, 'approved': 0}
    
    def scan_dir(directory, is_approved=False):
        if not os.path.exists(directory): return
        files = get_sorted_images(directory)
        for f in files:
            full_path = os.path.join(directory, f)
            try:
                mtime = os.path.getmtime(full_path)
                dt = datetime.fromtimestamp(mtime)
                date_str = dt.strftime("%Y-%m-%d")
                
                if date_str not in stats:
                    stats[date_str] = {'total': 0, 'approved': 0}
                
                stats[date_str]['total'] += 1
                if is_approved:
                    stats[date_str]['approved'] += 1
            except OSError:
                continue

    scan_dir(OUTPUT_DIR, is_approved=False)
    scan_dir(APPROVED_DIR, is_approved=True)
    scan_dir(DISAPPROVED_DIR, is_approved=False)
    
    data = []
    for date_str, counts in stats.items():
        total = counts['total']
        approved = counts['approved']
        ratio = (approved / total * 100) if total > 0 else 0
        data.append({
            "Date": date_str,
            "Total Generated": total,
            "Approved": approved,
            "Approval Rate": f"{ratio:.1f}%"
        })
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values("Date", ascending=False)
    return df

@st.cache_data(show_spinner=False)
def extract_metadata_from_image(file_path, mtime=None):
    """
    Extracts seed and prompt from ComfyUI image metadata.
    """
    metadata = {
        "seed": None,
        "prompt": None,
        "raw_metadata": {}
    }
    
    try:
        with Image.open(file_path) as img:
            meta = img.info
            if 'prompt' in meta:
                prompt_data = json.loads(meta['prompt'])
                metadata["raw_metadata"] = prompt_data
                
                for node_id, node_data in prompt_data.items():
                    inputs = node_data.get('inputs', {})
                    class_type = node_data.get('class_type', '')
                    
                    if metadata["seed"] is None:
                        if 'seed' in inputs:
                            metadata["seed"] = inputs['seed']
                        elif 'noise_seed' in inputs:
                            metadata["seed"] = inputs['noise_seed']
                    
                    if 'text' in inputs and isinstance(inputs['text'], str):
                        if 'CLIPTextEncode' in class_type or metadata["prompt"] is None:
                            metadata["prompt"] = inputs['text']
                            
    except Exception as e:
        # print(f"Error extracting metadata from {file_path}: {e}")
        pass
        
    return metadata

# --- Daily Notes Logic ---
NOTES_FILE = os.path.join(OUTPUT_DIR, "daily_notes.json")
def load_notes():
    if os.path.exists(NOTES_FILE):
        try:
            with open(NOTES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_note(date_str, note_text):
    notes = load_notes()
    notes[date_str] = note_text
    try:
        with open(NOTES_FILE, "w") as f:
            json.dump(notes, f, indent=2)
        return True
    except Exception as e:
        st.error(f"Failed to save note: {e}")
        return False

def toggle_selection(filename):
    if filename in st.session_state.selected_files:
        st.session_state.selected_files.remove(filename)
    else:
        st.session_state.selected_files.add(filename)

def toggle_approve_status(filename):
    if filename in st.session_state.files_to_approve:
        st.session_state.files_to_approve.remove(filename)
    else:
        st.session_state.files_to_approve.add(filename)

# --- Fragment for Gallery View ---
@st.fragment
def view_gallery_fragment(items, current_tab, context_dir, grouping_mode):
    """
    Renders the gallery grid for a specific tab.
    current_tab: 'wait', 'approved', 'disapproved'
    """
    if not items:
        st.info("No images match current filters.")
        return

    # --- Batch Actions for Wait Tab ---
    if current_tab == 'wait':
        col_actions, _ = st.columns([2, 1])
        with col_actions:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Approve Selected", type="primary", width='stretch'):
                    count = 0
                    for item in items:
                        fname = item['filename']
                        # Check if marked for approval
                        if fname in st.session_state.files_to_approve:
                            # Get rename value if any
                            new_name = st.session_state.get(f"rename_{fname}", "").strip()
                            if not new_name: new_name = None
                            
                            if move_image(fname, context_dir, APPROVED_DIR, new_name):
                                count += 1
                                # Cleanup state
                                if fname in st.session_state.files_to_approve:
                                    st.session_state.files_to_approve.remove(fname)
                    
                    if count > 0:
                        st.success(f"Moved {count} images to Approved.")
                        load_gallery_data.clear()
                        get_all_stats.clear() # Clear stats cache too
                        st.rerun()
                    else:
                        st.warning("No images selected for approval.")

            with c2:
                if st.button("🗑️ Disapprove Remaining", type="secondary", width='stretch'):
                     # Disapprove everything NOT marked for approval
                    count = 0
                    for item in items:
                        fname = item['filename']
                        if fname not in st.session_state.files_to_approve:
                            if move_image(fname, context_dir, DISAPPROVED_DIR):
                                count += 1
                    
                    if count > 0:
                        st.success(f"Moved {count} remaining images to Disapproved.")
                        load_gallery_data.clear()
                        get_all_stats.clear()
                        st.rerun()

    # --- Bulk Download for Approved Tab ---
    if current_tab == 'approved' and items:
        with st.expander("📥 Download All Approved Images (By Date)", expanded=False):
            # Group items by date
            date_groups = {}
            for item in items:
                d = item['date']
                if d not in date_groups: date_groups[d] = []
                date_groups[d].append(item)
            
            # Show download buttons for each date
            cols = st.columns(3)
            for i, (date_str, group_items) in enumerate(sorted(date_groups.items(), reverse=True)):
                with cols[i % 3]:
                    # Create ZIP in memory
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for item in group_items:
                            f_path = item['path']
                            if os.path.exists(f_path):
                                zf.write(f_path, arcname=item['filename'])
                                # Also include txt if exists
                                txt_path = os.path.splitext(f_path)[0] + ".txt"
                                if os.path.exists(txt_path):
                                    zf.write(txt_path, arcname=os.path.basename(txt_path))
                    
                    st.download_button(
                        label=f"📥 Download {date_str} ({len(group_items)})",
                        data=zip_buffer.getvalue(),
                        file_name=f"approved_{date_str}.zip",
                        mime="application/zip",
                        key=f"dl_zip_{date_str}"
                    )

    # --- Pagination ---
    items_per_page = 20
    total_items = len(items)
    total_pages = math.ceil(total_items / items_per_page)
    
    # Simple pagination key based on tab
    page_key = f"page_{current_tab}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1
        
    col_p1, col_p2 = st.columns([1, 4])
    with col_p1:
        if total_pages > 1:
            st.session_state[page_key] = st.number_input(
                f"Page ({total_pages})", 
                min_value=1, max_value=total_pages, 
                value=st.session_state[page_key],
                key=f"num_{page_key}"
            )
    
    start_idx = (st.session_state[page_key] - 1) * items_per_page
    end_idx = start_idx + items_per_page
    paginated_items = items[start_idx:end_idx]

    # --- Grid Render Helper ---
    def render_grid(grid_items):
        cols_per_row = 4
        for i in range(0, len(grid_items), cols_per_row):
            row_items = grid_items[i:i+cols_per_row]
            cols = st.columns(cols_per_row)
            for idx, item in enumerate(row_items):
                with cols[idx]:
                    try:
                        st.image(item['path'], width='stretch')
                    except Exception:
                        st.error("Error loading image")
                        continue
                    
                    fname = item['filename']
                    base_name = os.path.splitext(fname)[0]

                    # Tab Specific Controls
                    if current_tab == 'wait':
                        # Checkbox for Approval & Delete Button
                        c_chk, c_del = st.columns([4, 1])
                        with c_chk:
                            is_approved = fname in st.session_state.files_to_approve
                            st.checkbox("Approve", value=is_approved, key=f"chk_{fname}", on_change=toggle_approve_status, args=(fname,))
                        with c_del:
                            if st.button("🗑️", key=f"del_{fname}", help="Delete Permanently"):
                                try:
                                    os.remove(item['path'])
                                    txt_path = os.path.splitext(item['path'])[0] + ".txt"
                                    if os.path.exists(txt_path):
                                        os.remove(txt_path)
                                    st.toast(f"Deleted {fname}")
                                    load_gallery_data.clear()
                                    get_all_stats.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error deleting: {e}")

                        # Rename Input
                        st.text_input("Rename:", value=base_name, key=f"rename_{fname}", label_visibility="collapsed", placeholder="Rename...")
                    
                    elif current_tab == 'approved':
                        if st.button("Undo (Move to Wait)", key=f"undo_{fname}"):
                            move_image(fname, context_dir, OUTPUT_DIR)
                            load_gallery_data.clear()
                            get_all_stats.clear()
                            st.rerun()
                        if st.button("Move to Disapproved", key=f"reject_{fname}"):
                            move_image(fname, context_dir, DISAPPROVED_DIR)
                            load_gallery_data.clear()
                            get_all_stats.clear()
                            st.rerun()

                    elif current_tab == 'disapproved':
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("Recover", key=f"rec_{fname}"):
                                move_image(fname, context_dir, OUTPUT_DIR)
                                load_gallery_data.clear()
                                get_all_stats.clear()
                                st.rerun()
                        with c2:
                            if st.button("Approve", key=f"app_from_dis_{fname}"):
                                move_image(fname, context_dir, APPROVED_DIR)
                                load_gallery_data.clear()
                                get_all_stats.clear()
                                st.rerun()

                    # Download Button (All Tabs)
                    try:
                        with open(item['path'], "rb") as file:
                            st.download_button(
                                label="📥 Download",
                                data=file,
                                file_name=fname,
                                mime="image/png",
                                key=f"dl_{current_tab}_{fname}"
                            )
                    except Exception:
                        pass

                    # Metadata Popover
                    with st.popover("Details"):
                        st.caption(fname)
                        img_meta = extract_metadata_from_image(item['path'], item['mtime'])
                        
                        if img_meta['seed'] is not None:
                            st.write(f"**Seed:** `{img_meta['seed']}`")
                        if img_meta['prompt']:
                            st.caption("**Prompt:**")
                            st.text(img_meta['prompt'])
                        
                        st.divider()
                        
                        if item['record']:
                            st.write(f"**Persona:** {item['persona']}")
                            if item.get('ref_path'):
                                st.image(item['ref_path'], caption="Reference", width=150)
                        
                        if img_meta['raw_metadata']:
                            with st.expander("Full Metadata"):
                                st.json(img_meta['raw_metadata'])

    # --- Grouping Logic ---
    if grouping_mode == "Date":
        grouped = {}
        for item in paginated_items:
            d = item['date']
            if d not in grouped: grouped[d] = []
            grouped[d].append(item)
        
        for date_key in grouped:
            st.subheader(f"📅 {date_key}")
            render_grid(grouped[date_key])
            
    elif grouping_mode == "Batch (Reference)":
        grouped = {}
        for item in paginated_items:
            ref_path = item.get('ref_path')
            key = ref_path if ref_path else "Unknown Reference"
            if key not in grouped: grouped[key] = []
            grouped[key].append(item)
            
        group_list = []
        for key, g_items in grouped.items():
            max_mtime = max(i['mtime'] for i in g_items)
            group_list.append((key, g_items, max_mtime))
        group_list.sort(key=lambda x: x[2], reverse=True)
        
        for key, g_items, _ in group_list:
            st.markdown(f"#### Batch: {os.path.basename(key) if key != 'Unknown Reference' else 'Unknown'}")
            if key != "Unknown Reference" and os.path.exists(key):
                st.image(key, width=100)
            render_grid(g_items)
            st.divider()

    else:
        render_grid(paginated_items)


# --- Main App Layout ---

col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.title("🗂️ Results Gallery")
with col_refresh:
    if st.button("🔄 Refresh All", type="primary", width='stretch'):
        load_gallery_data.clear()
        get_all_stats.clear()
        st.rerun()

# 1. Statistics Table
st.markdown("### 📊 Generation Statistics")
df_stats = get_all_stats()
if not df_stats.empty:
    st.dataframe(
        df_stats, 
        hide_index=True, 
        width='stretch',
        column_config={
            "Approval Rate": st.column_config.ProgressColumn(
                "Approval Rate",
                help="Percentage of generated images that were approved",
                format="%f",
                min_value=0,
                max_value=100,
            ),
        }
    )
else:
    st.info("No statistics available yet.")

st.divider()

# 2. Global Controls (Filters & Grouping)
with st.expander("🛠️ Filters & Settings", expanded=True):
    col_f1, col_f2 = st.columns(2)
    
    # We need all unique personas from ALL loaded data ideally, but loading just current view is faster.
    # To be safe and fast, let's load all potential personas from the DB logs or just current view.
    # Let's use the current view approach for simplicity + cache, or just load all executed logs.
    # Loading from storage is fast.
    all_completed = storage.get_all_completed_executions()
    all_personas = sorted(list(set(e['persona'] for e in all_completed if e.get('persona'))))
    
    with col_f1:
        selected_personas = st.multiselect("Filter by Persona", all_personas, default=[])
    
    with col_f2:
        grouping_mode = st.radio("Group By", ["Date", "Batch (Reference)", "None"], index=0, horizontal=True)

# 3. Tab Layout
tab1, tab2, tab3 = st.tabs(["⏳ Wait for Approvals", "✅ Approved Images", "🗑️ Disapproved"])

# Filter Logic Helper
def apply_filters(items, personas):
    if not personas:
        return items
    return [item for item in items if item['persona'] in personas]

# 1. Wait Tab
with tab1:
    st.subheader("Wait for Approvals")
    wait_items = load_gallery_data(OUTPUT_DIR)
    filtered_wait = apply_filters(wait_items, selected_personas)
    view_gallery_fragment(filtered_wait, 'wait', OUTPUT_DIR, grouping_mode)

# 2. Approved Tab
with tab2:
    st.subheader("Approved Images")
    approved_items = load_gallery_data(APPROVED_DIR)
    filtered_approved = apply_filters(approved_items, selected_personas)
    view_gallery_fragment(filtered_approved, 'approved', APPROVED_DIR, grouping_mode)

# 3. Disapproved Tab
with tab3:
    st.subheader("Disapproved Images")
    disapproved_items = load_gallery_data(DISAPPROVED_DIR)
    filtered_disapproved = apply_filters(disapproved_items, selected_personas)
    view_gallery_fragment(filtered_disapproved, 'disapproved', DISAPPROVED_DIR, grouping_mode)

# --- Common Footer ---
st.divider()
with st.expander("📝 Daily Notes", expanded=False):
    today_str = datetime.now().strftime("%Y-%m-%d")
    all_notes = load_notes()
    current_note = all_notes.get(today_str, "")
    new_note = st.text_area(f"Notes for {today_str}", value=current_note, height=100)
    if st.button("Save Note"):
        save_note(today_str, new_note)
        st.success("Saved.")
