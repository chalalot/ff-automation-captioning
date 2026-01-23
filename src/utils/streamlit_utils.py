import streamlit as st
import os
import re
import sys
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

class StreamlitLogger:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.log_buffer = ""
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        try:
            self.ctx = get_script_run_ctx()
        except Exception:
            self.ctx = None

    def write(self, message):
        # Avoid writing to UI from MainThread (Server Thread) as it causes warnings/issues
        if threading.current_thread() is threading.main_thread():
            sys.__stdout__.write(message)
            return

        # If we have a context, use it to update the UI
        if self.ctx:
            try:
                add_script_run_ctx(self.ctx)
                # Clean ANSI codes
                clean_message = self.ansi_escape.sub('', message)
                self.log_buffer += clean_message
                # Update placeholder
                self.placeholder.code(self.log_buffer, language="text")
            except Exception:
                # If updating UI fails, fall back to console
                sys.__stdout__.write(message)
        else:
            # If no context (e.g. in a separate process), just log to console
            # Use sys.__stdout__ to avoid infinite recursion if stdout is redirected
            sys.__stdout__.write(message)

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
