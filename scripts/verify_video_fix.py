import asyncio
import os
import sys
import uuid
import time

# Add src to path
sys.path.append(os.getcwd())

from src.third_parties.comfyui_client import ComfyUIClient
from src.third_parties.gcs_client import check_blob_exists, download_blob_to_file

async def main():
    print("🚀 Initializing Test...")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        client = ComfyUIClient()
    except Exception as e:
        print(f"Failed to init client: {e}")
        return

    # Image setup
    image_path = "results/result_ref_1766634154_d875e649.png"
    if not os.path.exists(image_path):
        # Pick any if specific one missing
        if os.path.exists("results"):
            files = [f for f in os.listdir("results") if f.endswith(".png")]
            if files:
                image_path = os.path.join("results", files[0])
    
    print(f"📸 Using image: {image_path}")

    # Params
    prompt = "A cinematic test video of a cat running, 4k"
    filename_id = str(uuid.uuid4())
    expected_filename = f"ComfyUI-{filename_id}.mp4"
    gcs_blob_name = f"outputs/{expected_filename}"
    
    print(f"🆔 Generated Filename ID: {filename_id}")
    print(f"📄 Expected Filename: {expected_filename}")
    print(f"☁️  Expected GCS Path: {gcs_blob_name}")
    
    # 1. Queue Task
    print("-" * 50)
    print("1️⃣  Queueing Task...")
    try:
        task_id = await client.generate_video_kling(
            prompt=prompt,
            image_path=image_path,
            duration="5",
            filename_id=filename_id
        )
        print(f"✅ Queued! Task ID: {task_id}")
    except Exception as e:
        print(f"❌ Queue failed: {e}")
        return

    # 2. Wait for Completion
    print("-" * 50)
    print("2️⃣  Polling Status...")
    
    # Poll for up to 15 minutes
    max_retries = 90 
    for i in range(max_retries):
        try:
            status_res = await client.check_status_local(task_id)
            status = status_res.get("status")
            
            if status == "succeed":
                print(f"✅ ComfyUI reports SUCCEED!")
                # Log what ComfyUI returned
                print(f"   Returned Filename: {status_res.get('filename')}")
                print(f"   Returned URL: {status_res.get('video_url')}")
                break
                
            elif status == "failed":
                print(f"❌ Task Failed: {status_res.get('message')}")
                return
            
            else:
                print(f"⏳ {status}... ({i+1}/{max_retries})")
                
        except Exception as e:
            print(f"⚠️  Error checking status: {e}")
            
        await asyncio.sleep(10)
    else:
        print("❌ Timeout waiting for ComfyUI.")
        return

    # 3. Verify GCS
    print("-" * 50)
    print("3️⃣  Verifying GCS Upload...")
    
    # Wait loop for GCS (upload might lag slightly)
    found = False
    for i in range(12): # 2 minutes wait
        if check_blob_exists(gcs_blob_name):
            print(f"✅ FOUND in GCS: {gcs_blob_name}")
            found = True
            break
        print(f"   Waiting for GCS appearance... ({i+1}/12)")
        time.sleep(10)
        
    if not found:
        print(f"❌ FILE NOT FOUND in GCS after wait: {gcs_blob_name}")
        return

    # 4. Download
    print("-" * 50)
    print("4️⃣  Testing Download...")
    local_out = f"video-raw/{expected_filename}"
    os.makedirs("video-raw", exist_ok=True)
    
    try:
        download_blob_to_file(gcs_blob_name, local_out)
        if os.path.exists(local_out) and os.path.getsize(local_out) > 0:
            print(f"✅ Download Successful: {local_out}")
            print(f"   Size: {os.path.getsize(local_out)} bytes")
            print("\n🎉 VERIFICATION PASSED: Correct ID used and file retrieved.")
        else:
            print("❌ Download failed (file missing or empty).")
    except Exception as e:
        print(f"❌ Download Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
