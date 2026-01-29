import streamlit as st
import os
import pandas as pd
import time

st.set_page_config(page_title="Debug Crash", layout="wide")

st.title("Debug Streamlit Crash & Warnings")

# 1. Trigger Deprecation Warning
st.subheader("1. Deprecation Warning Check")
df = pd.DataFrame({"Col A": [1, 2], "Col B": [3, 4]})
try:
    st.dataframe(df, use_container_width=True)
    st.caption("Dataframe rendered with `use_container_width=True`. Check console for warnings.")
except Exception as e:
    st.error(f"Error rendering dataframe: {e}")

# 2. Trigger MediaFileHandler Error
st.subheader("2. MediaFileHandler Missing File Check")

# Initialize State
if "debug_videos" not in st.session_state:
    # Create a dummy file
    dummy_file = "debug_video.mp4"
    with open(dummy_file, "w") as f:
        f.write("dummy video content")
    
    st.session_state.debug_videos = [dummy_file]
    st.session_state.file_created = True

st.write(f"Current Video List: `{st.session_state.debug_videos}`")

# Button to delete file but NOT clear state (mimicking the bug)
if st.button("🔴 Simulate Cleanup (Delete File Only)"):
    for v in st.session_state.debug_videos:
        if os.path.exists(v):
            os.remove(v)
            st.toast(f"Deleted {v}")
    
    # We purposefully do NOT clear st.session_state.debug_videos
    # Then we trigger a rerun to force Streamlit to try rendering the missing file
    time.sleep(1)
    st.rerun()

# Attempt to render videos
for i, v in enumerate(st.session_state.debug_videos):
    st.write(f"Rendering Video {i}: `{v}`")
    st.video(v)
