import jwt
import time
import requests
import logging
import base64
import os
from typing import Optional, Dict, Any
from src.config import GlobalConfig

logger = logging.getLogger(__name__)

class KlingClient:
    """Client for Kling AI Video Generation API."""
    
    BASE_URL = "https://api.klingai.com/v1"

    def __init__(self):
        self.access_key = GlobalConfig.KLING_ACCESS_KEY
        self.secret_key = GlobalConfig.KLING_SECRET_KEY
        
        if not self.access_key or not self.secret_key:
            logger.warning("Kling AI credentials not set in GlobalConfig.")

    def _get_token(self) -> str:
        """Generate JWT token for authentication."""
        if not self.access_key or not self.secret_key:
            raise ValueError("Kling AI Access Key and Secret Key are required.")

        headers = {
            "alg": "HS256",
            "typ": "JWT"
        }
        
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800, # 30 mins validity
            "nbf": int(time.time()) - 5
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm="HS256", headers=headers)
        return token

    def _get_headers(self) -> Dict[str, str]:
        token = self._get_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with retry logic for rate limits."""
        max_retries = 5
        backoff_factor = 2
        
        # Merge headers if provided in kwargs, otherwise use default
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
            del kwargs["headers"]

        for attempt in range(max_retries + 1):
            try:
                response = requests.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                     # Kling specific error codes
                     raise Exception(f"Kling API Error: {data.get('message')}")
                
                return data

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries:
                        sleep_time = (backoff_factor ** attempt) + 1 # Start with at least 2s
                        logger.warning(f"Rate limited (429). Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue
                logger.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
                raise e
            except Exception as e:
                if attempt < max_retries:
                     # Retry on other connection errors? Maybe not unless we're sure.
                     # But for 429 it's handled above.
                     pass
                raise e

    def generate_video(self, prompt: str, image: str, model_name: str = "kling-v1", duration: str = "5") -> str:
        """
        Queue a video generation task.
        
        Args:
            prompt: Text prompt.
            image: Image URL or Base64 string.
            model_name: "kling-v1", "kling-v1-5", "kling-v1-6".
            duration: "5" or "10".
            
        Returns:
            task_id: The ID of the queued task.
        """
        url = f"{self.BASE_URL}/videos/image2video"
        
        # If image is a local path, convert to base64
        if os.path.exists(image):
            with open(image, "rb") as f:
                encoded_string = base64.b64encode(f.read()).decode('utf-8')
                image = encoded_string # Kling accepts base64 string directly
        
        payload = {
            "model_name": model_name,
            "image": image,
            "prompt": prompt,
            "duration": duration
        }
        
        try:
            data = self._make_request("POST", url, json=payload)
            
            task_id = data.get("data", {}).get("task_id")
            if not task_id:
                raise Exception("No task_id in response")
                
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to queue Kling video: {e}")
            raise

    def get_video_status(self, task_id: str) -> Dict[str, Any]:
        """
        Check status of video generation task.
        
        Returns:
            Dict with status and result url (if succeed).
            {
                "task_status": "succeed" | "processing" | "submitted" | "failed",
                "video_url": "..." (if succeed)
            }
        """
        url = f"{self.BASE_URL}/videos/image2video/{task_id}"
        
        try:
            data = self._make_request("GET", url)
            
            task_data = data.get("data", {})
            status = task_data.get("task_status")
            result = {"task_status": status}
            
            if status == "succeed":
                videos = task_data.get("task_result", {}).get("videos", [])
                if videos:
                    result["video_url"] = videos[0].get("url")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get Kling status: {e}")
            raise
            
    def download_video(self, url: str, output_path: str):
        """Download video from URL to path."""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded video to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to download video: {e}")
            raise
