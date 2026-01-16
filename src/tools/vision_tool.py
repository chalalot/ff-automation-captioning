import base64
import os
from typing import Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from openai import OpenAI

class VisionToolInput(BaseModel):
    """Input schema for VisionTool when image_path is required."""
    image_path: str = Field(..., description="The absolute local file path to the image to analyze. This argument is MANDATORY.")
    prompt: str = Field(..., description="The question or instruction for the vision model about the image.")

class VisionToolFixedInput(BaseModel):
    """Input schema for VisionTool when image_path is fixed."""
    prompt: str = Field(..., description="The question or instruction for the vision model about the image.")

class VisionTool(BaseTool):
    name: str = "Vision Tool"
    description: str = (
        "A tool that uses GPT-4o to analyze images. "
        "It takes a prompt and returns a text description."
    )
    args_schema: Type[BaseModel] = VisionToolInput
    fixed_image_path: Optional[str] = None

    def __init__(self, fixed_image_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if fixed_image_path:
            self.fixed_image_path = fixed_image_path
            self.args_schema = VisionToolFixedInput
            self.description = "A tool that uses GPT-4o to analyze the SPECIFIC image currently being processed. It takes a prompt and returns a text description."

    def _run(self, prompt: str, image_path: Optional[str] = None) -> str:
        # Determine effective image path
        effective_path = self.fixed_image_path or image_path
        
        print(f"\n[VisionTool] DEBUG: _run called. Fixed path: {repr(self.fixed_image_path)}, Arg path: {repr(image_path)}, Prompt: {repr(prompt)}")
        
        if not effective_path:
            return "Error: No image path provided. The tool requires an image path."

        # Clean path of potential quotes from LLM
        image_path = effective_path.strip().strip("'").strip('"')

        print(f"[VisionTool] DEBUG: Using path={image_path}")
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
