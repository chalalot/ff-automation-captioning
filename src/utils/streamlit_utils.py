import streamlit as st
import os

@st.cache_data(ttl=15, show_spinner=False)
def get_sorted_images(directory):
    if not os.path.exists(directory):
        return []
    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    images = [
        f for f in os.listdir(directory) 
        if f.lower().endswith(valid_exts) and "approvals.json" not in f
    ]
    images.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
    return images

async def fetch_remote_metadata(client, execution_id):
    return await client.get_execution_details(execution_id)
