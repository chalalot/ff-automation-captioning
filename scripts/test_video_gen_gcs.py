import os
import sys
import time

# Add src to path
sys.path.append(os.getcwd())

from src.third_parties.kling_client import KlingClient

def main():
    print("Initializing Kling Client...")
    try:
        # Load env vars if needed (dotenv)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        
        client = KlingClient()
    except Exception as e:
        print(f"Failed to init client: {e}")
        return

    # Image path - try to find a real one or use dummy
    image_path = "results/test_image.png"
    if not os.path.exists(image_path):
        if os.path.exists("results"):
            files = [f for f in os.listdir("results") if f.endswith(".png")]
            if files:
                image_path = os.path.join("results", files[0])
                print(f"Using existing image: {image_path}")
            else:
                # Create dummy
                os.makedirs("results", exist_ok=True)
                # Create a simple colored square using PIL if possible, else just bytes
                try:
                    from PIL import Image
                    img = Image.new('RGB', (100, 100), color = 'red')
                    img.save(image_path)
                    print(f"Created dummy image at {image_path}")
                except:
                     with open(image_path, "wb") as f:
                         f.write(b"dummy content")
                     print(f"Created dummy image (bytes) at {image_path}")

    prompt = "A cinematic shot of a warrior standing in the rain"
    
    print(f"Queueing video generation for {image_path}...")
    try:
        task_id = client.generate_video(
            prompt=prompt,
            image=image_path,
            duration="5"
        )
        print(f"✅ Task queued successfully!")
        print(f"🆔 Task ID: {task_id}")
    except Exception as e:
        print(f"❌ Failed to queue task: {e}")
        return

    # Poll for completion
    print(f"Polling Kling for completion using Task ID {task_id}...")
    
    max_retries = 60 # 10 mins (assuming 10s sleep)
    for i in range(max_retries):
        try:
            status_res = client.get_video_status(task_id)
            status = status_res.get("task_status")
            
            if status == "succeed":
                print(f"✅ Task Completed!")
                video_url = status_res.get("video_url")
                print(f"🔗 Video URL: {video_url}")
                
                # Download
                output_path = f"results/kling_test_{task_id}.mp4"
                client.download_video(video_url, output_path)
                print(f"⬇️ Downloaded to: {output_path}")
                return
                
            elif status == "failed":
                print(f"❌ Task Failed: {status_res}")
                return
            
            else:
                print(f"⏳ Status: {status}... ({i+1}/{max_retries})")
                
        except Exception as e:
            print(f"Error checking status: {e}")
            
        time.sleep(10)

    print("Timeout waiting for video.")

if __name__ == "__main__":
    main()
