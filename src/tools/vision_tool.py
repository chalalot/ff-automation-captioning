import base64
import os
from typing import Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from openai import OpenAI

class VisionToolInput(BaseModel):
    """Input schema for VisionTool."""
    image_path: str = Field(..., description="The absolute local file path to the image to analyze. This argument is MANDATORY.")
    prompt: str = Field(..., description="The question or instruction for the vision model about the image.")

class VisionTool(BaseTool):
    name: str = "Vision Tool"
    description: str = (
        "A tool that uses GPT-4o to analyze images. "
        "It REQUIRE 'image_path' and 'prompt' as arguments. "
        "It takes a local image path and a prompt, and returns a text description."
    )
    args_schema: Type[BaseModel] = VisionToolInput

    def _run(self, image_path: str, prompt: str) -> str:
        print(f"\n[VisionTool] DEBUG: _run called with args: image_path={repr(image_path)}, prompt={repr(prompt)}")
        # Clean path of potential quotes from LLM
        image_path = image_path.strip().strip("'").strip('"')

        print(f"[VisionTool] DEBUG: Cleaned path={image_path}")
        client = OpenAI() # Assumes OPENAI_API_KEY is set in environment

        try:
            # Check if file exists
            if not os.path.exists(image_path):
                print(f"[VisionTool] DEBUG: File not found at {image_path}")
                return f"Error: Image file not found at {image_path}"

            # Encode image
            print("[VisionTool] DEBUG: Encoding image...")
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            print("[VisionTool] DEBUG: Sending request to OpenAI...")
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error processing image: {str(e)}"
