import asyncio
import os
import sys
import time

# Add src to path
sys.path.append(os.getcwd())

from src.third_parties.comfyui_client import ComfyUIClient

# Try importing GCS client, but don't fail if missing
try:
    from src.third_parties.gcs_client import check_blob_exists, download_blob_to_file
    GCS_AVAILABLE = True
except ImportError:
    print("Warning: GCS Client not available (missing google-cloud-storage?). Skipping GCS check.")
    GCS_AVAILABLE = False

async def main():
    print("Initializing ComfyUI Client...")
    try:
        # Load env vars if needed (dotenv)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        
        client = ComfyUIClient()
    except Exception as e:
        print(f"Failed to init client: {e}")
        return

    # Image path - try to find a real one or use dummy
    image_path = "results/result_ref_1766634154_d875e649.png"
    if not os.path.exists(image_path):
        if os.path.exists("results"):
            files = [f for f in os.listdir("results") if f.endswith(".png")]
            if files:
                image_path = os.path.join("results", files[0])
                print(f"Using existing image: {image_path}")
            else:
                # Create dummy
                os.makedirs("results", exist_ok=True)
                with open(image_path, "wb") as f:
                    f.write(b"dummy content")
                print(f"Created dummy image at {image_path}")
        else:
             os.makedirs("results", exist_ok=True)
             with open(image_path, "wb") as f:
                 f.write(b"dummy content")
             print(f"Created dummy image at {image_path}")

    prompt = "A test video generation prompt"
    
    print(f"Queueing video generation for {image_path}...")
    try:
        task_id = await client.generate_video_kling(
            prompt=prompt,
            image_path=image_path,
            duration="5"
        )
        print(f"✅ Task queued successfully!")
        print(f"🆔 Prompt ID: {task_id}")
    except Exception as e:
        print(f"❌ Failed to queue task: {e}")
        return

    # Poll for completion using PROMPT ID
    print(f"Polling ComfyUI for completion using Prompt ID {task_id}...")
    
    max_retries = 60 # 10 mins
    for i in range(max_retries):
        try:
            status_res = await client.check_status_local(task_id)
            status = status_res.get("status")
            
            if status == "succeed":
                print(f"✅ Task Completed!")
                filename = status_res.get("filename")
                print(f"📄 Filename reported by ComfyUI: {filename}")
                
                if GCS_AVAILABLE:
                    gcs_blob_name = f"outputs/{filename}"
                    print(f"🔍 Checking GCS for: {gcs_blob_name}")
                    if check_blob_exists(gcs_blob_name):
                        print("✅ File found on GCS!")
                    else:
                        print("⚠️ File NOT found on GCS (yet?).")
                return
                
            elif status == "failed":
                print(f"❌ Task Failed: {status_res.get('message')}")
                return
            
            else:
                print(f"⏳ Status: {status}... ({i+1}/{max_retries})")
                
        except Exception as e:
            print(f"Error checking status: {e}")
            
        await asyncio.sleep(10)

    print("Timeout waiting for video.")

if __name__ == "__main__":
    asyncio.run(main())
