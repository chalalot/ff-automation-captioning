import jwt
import time
import requests
import json
import sys
import os
from datetime import datetime

# Add the project root to sys.path to import src.config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import GlobalConfig

def get_token(access_key, secret_key):
    """Generate JWT token for authentication."""
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    
    # Payload structure as requested
    payload = {
        "iss": access_key,
        "exp": int(time.time()) + 1800, # current time + 1800s
        "nbf": int(time.time()) - 5     # current time - 5s
    }
    
    token = jwt.encode(payload, secret_key, algorithm="HS256", headers=headers)
    return token

def format_timestamp(ts):
    """Convert timestamp to readable date."""
    if not ts:
        return "N/A"
    try:
        # Assuming timestamp is in milliseconds if it's very large, otherwise seconds
        # Kling API typically uses milliseconds for some fields, but let's check
        # Standard Unix timestamp is ~1.7e9 (10 digits). Milliseconds is ~1.7e12 (13 digits).
        ts_float = float(ts)
        if ts_float > 1e11: 
            ts_float = ts_float / 1000.0
            
        dt = datetime.fromtimestamp(ts_float)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)

def get_kling_history():
    access_key = GlobalConfig.KLING_ACCESS_KEY
    secret_key = GlobalConfig.KLING_SECRET_KEY
    
    if not access_key or not secret_key:
        print("Error: KLING_ACCESS_KEY or KLING_SECRET_KEY not found in configuration.")
        return

    base_url = "https://api-singapore.klingai.com/v1/videos/image2video"
    page_num = 1
    page_size = 30
    total_tasks = 0
    
    print(f"Fetching Kling AI Image-to-Video History...")
    print(f"Endpoint: {base_url}")
    print("-" * 60)

    while True:
        token = get_token(access_key, secret_key)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        params = {
            "pageNum": page_num,
            "pageSize": page_size
        }
        
        try:
            response = requests.get(base_url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 0:
                print(f"Error: API returned code {result.get('code')}: {result.get('message')}")
                break
                
            data_field = result.get("data")
            if isinstance(data_field, list):
                data_list = data_field
            elif isinstance(data_field, dict):
                data_list = data_field.get("tasks", [])
            else:
                data_list = []
            
            if not data_list:
                print(f"No more data found at page {page_num}.")
                break
                
            print(f"Page {page_num}: Found {len(data_list)} tasks")
            
            for task in data_list:
                total_tasks += 1
                task_id = task.get("task_id", "N/A")
                task_status = task.get("task_status", "N/A")
                created_at = task.get("created_at")
                formatted_date = format_timestamp(created_at)
                # final_unit_deduction might be camelCase or snake_case depending on API
                # Checking both likely variations just in case, defaulting to requested snake_case
                cost = task.get("final_unit_deduction", "N/A")
                
                print(f"[{total_tasks}] ID: {task_id}")
                print(f"      Status: {task_status}")
                print(f"      Date:   {formatted_date}")
                print(f"      Cost:   {cost}")
                
                if task_status == "succeed":
                    # Check where video url is located. Usually task_result -> videos -> [0] -> url
                    task_result = task.get("task_result", {})
                    if isinstance(task_result, str):
                        # Sometimes result is a json string
                        try:
                            task_result = json.loads(task_result)
                        except:
                            task_result = {}
                            
                    videos = task_result.get("videos", [])
                    if videos and len(videos) > 0:
                        print(f"      Video:  {videos[0].get('url')}")
                    else:
                        print(f"      Video:  (No video URL found)")
                
                print("-" * 40)
            
            # Check if we reached the end based on total count if available
            # total_count = result.get("data", {}).get("total")
            # But the requirement says "fetch until data array is empty" which covers it.
            
            page_num += 1
            # Optional: Sleep to be nice to the API?
            # time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    get_kling_history()
