import os
import sys
import base64
from openai import OpenAI

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

def test_grok_vision():
    api_key = GlobalConfig.GROK_API_KEY
    if not api_key:
        print("Error: GROK_API_KEY not found in environment variables.")
        return

    print(f"Testing Grok Vision API with key: {api_key[:5]}...")
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )

    image_path = "temp_test/ComfyUI_03370_.png"
    if not os.path.exists(image_path):
        print(f"Error: Test image not found at {image_path}")
        return

    base64_image = encode_image(image_path)

    try:
        response = client.chat.completions.create(
            model="grok-2-vision-1212",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "text",
                            "text": "What's in this image?",
                        },
                    ],
                },
            ],
        )
        print("Response from Grok:")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error calling Grok API: {e}")

if __name__ == "__main__":
    test_grok_vision()
