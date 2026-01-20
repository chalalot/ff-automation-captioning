import asyncio
import os
import sys
import time

# Add src to path
sys.path.append(os.getcwd())

from src.third_parties.comfyui_client import ComfyUIClient
from src.third_parties.gcs_client import check_blob_exists, download_blob_to_file

async def main():
    print("Initializing ComfyUI Client...")
    try:
        client = ComfyUIClient()
    except Exception as e:
        print(f"Failed to init client: {e}")
        return

    # Image path
    image_path = "results/result_ref_1766634154_d875e649.png"
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return

    prompt = "A test video generation prompt"
    
    print(f"Queueing video generation for {image_path}...")
    try:
        task_id = await client.generate_video_kling(
            prompt=prompt,
            image_path=image_path,
            duration="5"
        )
        print(f"Task queued. ID: {task_id}")
    except Exception as e:
        print(f"Failed to queue task: {e}")
        return

    # Poll for completion via GCS
    print("Polling GCS for completion...")
    gcs_blob_name = f"outputs/ComfyUI-{task_id}.mp4"
    
    max_retries = 60 # 60 * 10s = 10 mins (video gen takes time)
    for i in range(max_retries):
        exists = check_blob_exists(gcs_blob_name)
        if exists:
            print(f"Video found in GCS: {gcs_blob_name}")
            
            # Download
            local_path = f"video-raw/test_{task_id}.mp4"
            os.makedirs("video-raw", exist_ok=True)
            
            print(f"Downloading to {local_path}...")
            download_blob_to_file(gcs_blob_name, local_path)
            
            if os.path.exists(local_path):
                print(f"Download successful! Size: {os.path.getsize(local_path)} bytes")
            else:
                print("Download failed (file missing locally).")
            return
        
        print(f"Waiting... ({i+1}/{max_retries})")
        time.sleep(10) # check every 10 seconds

    print("Timeout waiting for video.")

if __name__ == "__main__":
    asyncio.run(main())
