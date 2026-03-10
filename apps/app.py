import streamlit as st

st.set_page_config(
    page_title="Variations Mood Dashboard",
    page_icon="🎨",
    layout="wide",
)

st.title("Welcome to Variations Mood Dashboard")

st.markdown("""
This is your central hub for managing the image workflow. Use the sidebar to navigate through the different applications:

*   **Workspace**: Input, manage, and queue images for generation. Edit personas and workflows.
*   **Gallery**: View and manage processed and generated images.
*   **Video**: Manage and generate video content.
*   **Monitor**: (If applicable) Monitor system status.

### Getting Started
Select an application from the sidebar to begin.
""")
