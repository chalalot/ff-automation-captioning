import os
import sys
import uuid
import time

# Add src to path
sys.path.append(os.getcwd())

from src.third_parties.kling_client import KlingClient

def main():
    print("🚀 Initializing Kling Verification Test...")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        client = KlingClient()
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
    
    if not os.path.exists(image_path):
        # Create dummy
        os.makedirs("results", exist_ok=True)
        with open(image_path, "wb") as f:
            f.write(b"dummy")
            
    print(f"📸 Using image: {image_path}")

    # Params
    prompt = "A cinematic test video of a cat running, 4k"
    filename_id = str(uuid.uuid4())
    expected_filename = f"Kling-{filename_id}.mp4"
    
    print(f"🆔 Generated Filename ID: {filename_id}")
    print(f"📄 Expected Output Filename: {expected_filename}")
    
    # 1. Queue Task
    print("-" * 50)
    print("1️⃣  Queueing Task...")
    try:
        task_id = client.generate_video(
            prompt=prompt,
            image=image_path,
            duration="5"
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
            status_res = client.get_video_status(task_id)
            status = status_res.get("task_status")
            
            if status == "succeed":
                print(f"✅ Kling reports SUCCEED!")
                video_url = status_res.get("video_url")
                print(f"   URL: {video_url}")
                
                # 3. Download
                print("-" * 50)
                print("3️⃣  Testing Download...")
                local_out = f"results/{expected_filename}"
                os.makedirs("results", exist_ok=True)
                
                try:
                    client.download_video(video_url, local_out)
                    if os.path.exists(local_out) and os.path.getsize(local_out) > 0:
                        print(f"✅ Download Successful: {local_out}")
                        print(f"   Size: {os.path.getsize(local_out)} bytes")
                        print("\n🎉 VERIFICATION PASSED: File retrieved.")
                    else:
                        print("❌ Download failed (file missing or empty).")
                except Exception as e:
                    print(f"❌ Download Exception: {e}")
                
                break
                
            elif status == "failed":
                print(f"❌ Task Failed: {status_res}")
                return
            
            else:
                print(f"⏳ {status}... ({i+1}/{max_retries})")
                
        except Exception as e:
            print(f"⚠️  Error checking status: {e}")
            
        time.sleep(10)
    else:
        print("❌ Timeout waiting for Kling.")
        return

if __name__ == "__main__":
    main()
