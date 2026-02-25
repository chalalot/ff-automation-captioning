import streamlit as st
import time
import os
import sys
import pandas as pd
import asyncio
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import psutil
except ImportError:
    st.error("`psutil` is not installed. Please install it using `pip install psutil` to monitor system resources.")
    psutil = None

from src.config import GlobalConfig
from src.third_parties.comfyui_client import ComfyUIClient
from src.third_parties.kling_client import KlingClient
from src.database.image_logs_storage import ImageLogsStorage
from src.database.video_logs_storage import VideoLogsStorage

# Page Config
st.set_page_config(page_title="Monitor - System Health & Queues", layout="wide", page_icon="📈")

st.title("📈 System Monitor")

# --- Auto Refresh Logic ---
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

auto_refresh = st.sidebar.checkbox("Auto-Refresh (5s)", value=True)

if auto_refresh:
    time.sleep(5)
    st.rerun()

if st.button("Refresh Now"):
    st.rerun()

st.caption(f"Last updated: {time.strftime('%H:%M:%S')}")

# --- 1. System Resources ---
st.header("1. System Health")

if psutil:
    c1, c2, c3 = st.columns(3)
    
    # CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    c1.metric("CPU Usage", f"{cpu_percent}%", delta_color="inverse")
    
    # RAM
    ram = psutil.virtual_memory()
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)
    c2.metric("RAM Usage", f"{ram.percent}%", f"{ram_used_gb:.1f} / {ram_total_gb:.1f} GB", delta_color="inverse")
    
    # Disk (Output Dir)
    output_dir = GlobalConfig.OUTPUT_DIR
    if os.path.exists(output_dir):
        disk = psutil.disk_usage(output_dir)
        disk_free_gb = disk.free / (1024 ** 3)
        c3.metric("Disk Free (Output)", f"{disk_free_gb:.1f} GB", f"{disk.percent}% Used", delta_color="normal")
    else:
        c3.warning("Output directory not found.")
        
    # Process Monitoring (Simple)
    with st.expander("Running Python Processes (Workspace)", expanded=False):
        process_list = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
            try:
                if 'python' in proc.info['name'].lower():
                    cmdline = proc.info['cmdline']
                    if cmdline and any('streamlit' in arg for arg in cmdline):
                         # Identify App
                         app_name = "Unknown Streamlit"
                         for arg in cmdline:
                             if arg.endswith('.py'):
                                 app_name = os.path.basename(arg)
                                 break
                         
                         mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
                         process_list.append({
                             "PID": proc.info['pid'],
                             "App": app_name,
                             "Memory (MB)": f"{mem_mb:.1f}",
                             "Status": proc.status()
                         })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if process_list:
            st.dataframe(pd.DataFrame(process_list), hide_index=True)
        else:
            st.info("No other Streamlit apps detected.")

else:
    st.warning("Install `psutil` to see system metrics.")

st.divider()

# --- 2. Workflow Queues ---
st.header("2. Workflow Queues")

q1, q2 = st.columns(2)

# ComfyUI Queue
with q1:
    st.subheader("ComfyUI")
    try:
        client = ComfyUIClient()
        queue_data = asyncio.run(client.get_queue())
        
        running = queue_data.get("queue_running", [])
        pending = queue_data.get("queue_pending", [])
        
        c_running, c_pending = st.columns(2)
        c_running.metric("Running Jobs", len(running))
        c_pending.metric("Pending Jobs", len(pending))
        
        if running:
            st.caption("🏃 Running:")
            for job in running:
                st.code(f"ID: {job[0]}")
        
        if pending:
             with st.expander(f"⏳ Pending ({len(pending)})"):
                 for job in pending:
                     st.text(f"ID: {job[0]}")

    except Exception as e:
        st.error(f"ComfyUI Connection Error: {e}")

# Kling AI Queue (Video)
with q2:
    st.subheader("Kling AI (Video)")
    try:
        video_storage = VideoLogsStorage()
        
        # Get pending/running from DB
        # Note: VideoLogsStorage needs a method for this, or we filter 'recent'
        # Let's inspect recent executions to infer status
        recent = video_storage.get_recent_executions(limit=50)
        
        pending_videos = [r for r in recent if r['status'] in ['pending', 'running']]
        completed_videos = [r for r in recent if r['status'] == 'completed']
        failed_videos = [r for r in recent if r['status'] == 'failed']
        
        k_pend, k_comp = st.columns(2)
        k_pend.metric("Active Tasks", len(pending_videos))
        k_comp.metric("Completed (Recent)", len(completed_videos))
        
        if pending_videos:
             with st.expander(f"Active Tasks ({len(pending_videos)})"):
                 for v in pending_videos:
                     st.text(f"Task: {v['execution_id'][-8:]}.. | Status: {v['status']}")
                     
    except Exception as e:
        st.error(f"Video Storage Error: {e}")

st.divider()

# --- 3. Data & Files ---
st.header("3. Data & Storage")

d1, d2 = st.columns(2)

with d1:
    st.subheader("Database Stats")
    db_path = "image_logs.db" # Default path from storage class
    if os.path.exists(db_path):
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        st.metric("DB Size", f"{size_mb:.2f} MB")
        
        # Row counts
        img_storage = ImageLogsStorage()
        # We might need to add count methods to storage class, for now we can select count
        try:
            conn = img_storage._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM image_logs")
            count = cursor.fetchone()[0]
            conn.close()
            st.metric("Total Image Logs", count)
        except:
            st.caption("Could not fetch row count.")
            
    else:
        st.warning("Database file not found.")

with d2:
    st.subheader("File System")
    
    def count_files(directory):
        if os.path.exists(directory):
            return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])
        return 0

    input_count = count_files(GlobalConfig.INPUT_DIR)
    processed_count = count_files(GlobalConfig.PROCESSED_DIR)
    output_count = count_files(GlobalConfig.OUTPUT_DIR)
    
    c_in, c_proc, c_out = st.columns(3)
    c_in.metric("Input Queue", input_count, help="Files waiting in Sorted folder")
    c_proc.metric("Processed", processed_count, help="Files moved to Processed folder")
    c_out.metric("Output/Gallery", output_count, help="Generated results")
