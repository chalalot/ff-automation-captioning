# Automation Guide for KOL Agent Workflow

This guide explains how to set up the automated daily workflow for processing images for Jennie and Sephera.

## 1. Prerequisites

Before running the automation, ensure:

1.  **Source Directories**:
    *   `Sorted/Indoor` exists and contains images for **Jennie**.
    *   `Sorted/Outdoor` exists and contains images for **Sephera**.
    *   (These should be in the root of the project, e.g., `d:/sem 2 2025/Athena/ff/variations_mood/Sorted/Indoor`)

2.  **Environment**:
    *   Your `.env` file is correctly configured with API keys (OPENAI_API_KEY) and ComfyUI URL.
    *   Python dependencies are installed (`pip install -r requirements.txt`).

## 2. Option A: Python Scheduler (Recommended)

The easiest way to run the automation is to use the provided `daily_scheduler.py` script. This script acts as a daemon, checking the time and triggering the workflows at the correct times.

### How to Run

Open your terminal or command prompt in the project root:

```bash
# Activate your virtual environment if you use one
python scripts/daily_scheduler.py
```

This will start the scheduler. You will see logs indicating it is waiting for the scheduled times:
*   **08:00**: Step 3 (Populate Results)
*   **18:00 (6 PM)**: Step 1 (Process images from Sorted folders)
*   **20:00 (8 PM)**: Step 2 (Queue prompts to ComfyUI)

### Running in Background (Linux/VM)

If you are on a Linux VM and want this to keep running after you disconnect:

**Using `nohup`:**
```bash
nohup python scripts/daily_scheduler.py > scheduler.log 2>&1 &
```

**Using `screen`:**
```bash
screen -S scheduler
python scripts/daily_scheduler.py
# Press Ctrl+A, then D to detach
```

## 3. Option B: System Cron (Linux)

If you prefer to use the system's `cron` daemon instead of the Python script, you can add the following entries to your crontab.

1.  Open crontab:
    ```bash
    crontab -e
    ```

2.  Add the following lines (adjust `/path/to/project` to your actual project path):

    ```cron
    # 6:00 PM: Run Step 1 for Jennie (Indoor) and Sephera (Outdoor)
    0 18 * * * cd /path/to/project && /usr/bin/python3 scripts/auto_process_images.py --source Sorted/Indoor --persona Jennie --limit 50 >> automation.log 2>&1
    0 18 * * * cd /path/to/project && /usr/bin/python3 scripts/auto_process_images.py --source Sorted/Outdoor --persona Sephera --limit 50 >> automation.log 2>&1

    # 8:00 PM: Run Step 2 (Queue Prompts)
    0 20 * * * cd /path/to/project && /usr/bin/python3 scripts/queue_prompts_from_archive.py --persona Jennie >> automation.log 2>&1
    0 20 * * * cd /path/to/project && /usr/bin/python3 scripts/queue_prompts_from_archive.py --persona Sephera >> automation.log 2>&1

    # 8:00 AM: Run Step 3 (Populate Results)
    0 8 * * * cd /path/to/project && /usr/bin/python3 scripts/populate_generated_images.py >> automation.log 2>&1
    ```

**Note**: Ensure `/usr/bin/python3` points to the python executable that has your dependencies installed (or use the full path to your virtualenv python, e.g., `/path/to/project/venv/bin/python`).

## 4. Troubleshooting

*   **Logs**: Check `automation.log` (created by the scripts) and `scheduler.log` (created by the scheduler) for details on success or failure.
*   **Missing Images**: If `Sorted/Indoor` runs out of images, the script will log "No images found".
*   **ComfyUI Connectivity**: Ensure your ComfyUI server is running and accessible at the URL in `.env`.
