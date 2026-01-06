import streamlit as st
import os
import re

class StreamlitLogger:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.log_buffer = ""
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def write(self, message):
        # Clean ANSI codes
        clean_message = self.ansi_escape.sub('', message)
        self.log_buffer += clean_message
        # Update placeholder
        self.placeholder.code(self.log_buffer, language="text")

    def flush(self):
        pass

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
