import asyncio
import subprocess
import datetime
import time
import logging
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SCHEDULER - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scheduler.log")
    ]
)
logger = logging.getLogger("Scheduler")

# Define Tasks
# Format: {"time": "HH:MM", "command": ["cmd", "arg1", ...], "name": "Task Name"}
TASKS = [
    {
        "time": "08:00",
        "command": [sys.executable, "scripts/populate_generated_images.py"],
        "name": "Step 3: Populate Results (All)"
    },
    {
        "time": "18:00",
        "command": [sys.executable, "scripts/auto_process_images.py", "--source", "Sorted/Indoor", "--persona", "Jennie", "--limit", "50"],
        "name": "Step 1: Jennie (Indoor)"
    },
    {
        "time": "18:00",
        "command": [sys.executable, "scripts/auto_process_images.py", "--source", "Sorted/Outdoor", "--persona", "Sephera", "--limit", "50"],
        "name": "Step 1: Sephera (Outdoor)"
    },
    {
        "time": "20:00",
        "command": [sys.executable, "scripts/queue_prompts_from_archive.py", "--persona", "Jennie"],
        "name": "Step 2: Queue Jennie Prompts"
    },
    {
        "time": "20:00",
        "command": [sys.executable, "scripts/queue_prompts_from_archive.py", "--persona", "Sephera"],
        "name": "Step 2: Queue Sephera Prompts"
    }
]

def run_command(command, name):
    logger.info(f"🚀 Starting Task: {name}")
    try:
        # Run command and wait for completion
        result = subprocess.run(
            command,
            check=False, # Don't raise exception on non-zero exit, we just log it
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"✅ Task Completed: {name}")
            logger.info(f"Output:\n{result.stdout}")
        else:
            logger.error(f"❌ Task Failed: {name} (Exit Code: {result.returncode})")
            logger.error(f"Error Output:\n{result.stderr}")
            
    except Exception as e:
        logger.error(f"❌ Exception running task {name}: {e}")

def main():
    logger.info("🕒 Daily Scheduler Started. Waiting for tasks...")
    logger.info(f"Scheduled Tasks: {[t['name'] + ' at ' + t['time'] for t in TASKS]}")
    
    # Track last run time for each task to avoid duplicate runs within the same minute
    # Key: "HH:MM", Value: last_run_date_string
    last_runs = {} 
    
    while True:
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")
        current_date_str = now.strftime("%Y-%m-%d")
        
        for task in TASKS:
            task_time = task["time"]
            task_name = task["name"]
            
            # Check if it matches current time
            if current_time_str == task_time:
                # Check if we already ran this task today
                last_run_key = f"{task_name}_{task_time}"
                if last_runs.get(last_run_key) != current_date_str:
                    # Execute
                    run_command(task["command"], task_name)
                    # Mark as run
                    last_runs[last_run_key] = current_date_str
        
        # Sleep for a bit (e.g., 30 seconds) to avoid high CPU but ensure we catch the minute
        time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped by user.")
