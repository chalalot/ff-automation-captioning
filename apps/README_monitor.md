# 📈 Monitor App

The **Monitor App** is a centralized dashboard designed to track system health, active processes, and workflow queues for the automation pipeline. It helps identify resource bottlenecks and provides a real-time view of your background tasks.

## 🛠️ Tech Stack

*   **Streamlit**: The core framework for the interactive web dashboard.
*   **Psutil**: A cross-platform library for retrieving information on running processes and system utilization (CPU, memory, disks).
*   **Pandas**: Used for structuring and displaying process lists in a readable table.
*   **Asyncio**: Handles asynchronous calls to external APIs (ComfyUI).

## 📊 What It Tracks

### 1. System Health
*   **CPU Usage**: Real-time percentage of CPU load.
*   **RAM Usage**: Percentage and absolute memory usage (Used / Total GB).
*   **Disk Space**: Monitors the partition containing the `OUTPUT_DIR` to prevent storage full errors.

### 2. Process Monitoring
*   **Python Apps**: Automatically detects running Python processes related to the workspace (e.g., `gallery_app.py`, `video_app.py`).
*   **Memory Footprint**: Shows how much RAM (in MB) each application is consuming, helping you spot memory leaks.

### 3. Workflow Queues
*   **ComfyUI Queue**: Connects to the ComfyUI API to show:
    *   **Running Jobs**: Tasks currently being processed by the GPU.
    *   **Pending Jobs**: Tasks waiting in the queue.
*   **Kling AI Queue**: Connects to the local database to show:
    *   **Active Tasks**: Video generation tasks that are `pending` or `running`.
    *   **Completed Tasks**: Recently finished video generations.

### 4. Data & Storage
*   **Database Stats**: Tracks the file size of `image_logs.db` and the total number of logged executions.
*   **File Backlog**: Counts files in key directories to help you spot bottlenecks:
    *   **Input Queue**: Images waiting to be processed.
    *   **Processed**: Images that have been handled.
    *   **Output/Gallery**: Final generated results.

## 🚀 How to Run

1.  **Install Dependencies**:
    Ensure `psutil` is installed (it is included in `requirements.txt`).
    ```bash
    pip install psutil
    ```

2.  **Launch the App**:
    ```bash
    streamlit run apps/monitor_app.py
    ```

3.  **Auto-Refresh**:
    Toggle the **"Auto-Refresh (5s)"** checkbox in the sidebar to keep the dashboard updated in real-time without manual reloading.
