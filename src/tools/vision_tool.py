import base64
import os
import logging
from typing import Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from openai import OpenAI
import PIL.Image
from src.config import GlobalConfig

# Configure logger
logger = logging.getLogger(__name__)

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
    model_name: str = "gpt-4o"

    def __init__(self, fixed_image_path: Optional[str] = None, model_name: str = "gpt-4o", **kwargs):
        super().__init__(**kwargs)
        self.model_name = model_name
        if fixed_image_path:
            self.fixed_image_path = fixed_image_path
            self.args_schema = VisionToolFixedInput
            self.description = f"A tool that uses {self.model_name} to analyze the SPECIFIC image currently being processed. It takes a prompt and returns a text description."

    def _run(self, prompt: str, image_path: Optional[str] = None) -> str:
        # Debug Print for User
        print(f"DEBUG: VisionTool called with image_path='{image_path}', fixed='{self.fixed_image_path}'")

        # Determine effective image path
        effective_path = self.fixed_image_path or image_path
        
        logger.info(f"[VisionTool] _run called. Fixed path: {repr(self.fixed_image_path)}, Arg path: {repr(image_path)}, Model: {self.model_name}")
        
        if not effective_path:
            return "Error: No image path provided. The tool requires an image path."

        # Clean path of potential quotes from LLM
        image_path = effective_path.strip().strip("'").strip('"')

        logger.info(f"[VisionTool] Using path={image_path}")
        
        # GEMINI
        if self.model_name.lower().startswith("gemini"):
            api_key = GlobalConfig.GEMINI_API_KEY
            if not api_key:
                return "Error: GEMINI_API_KEY not found in environment variables."
            
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                
                logger.info(f"[VisionTool] Using Gemini API with model {self.model_name}")
                
                # Check file
                if not os.path.exists(image_path):
                     logger.error(f"[VisionTool] File not found at {image_path}")
                     return f"Error: Image file not found at {image_path}"
                
                logger.info("[VisionTool] Loading image for Gemini...")
                img = PIL.Image.open(image_path)
                model = genai.GenerativeModel(self.model_name)
                
                logger.info(f"[VisionTool] Sending request to Gemini ({self.model_name})...")
                response = model.generate_content([prompt, img])
                return response.text
            except ImportError:
                 return "Error: google-generativeai library not installed."
            except Exception as e:
                 return f"Error processing image with Gemini: {str(e)}"

        # Configure Client based on model (OpenAI / Grok)
        if self.model_name.lower().startswith("grok"):
            api_key = GlobalConfig.GROK_API_KEY
            if not api_key:
                return "Error: GROK_API_KEY not found in environment variables."
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )
            logger.info(f"[VisionTool] Using Grok API with model {self.model_name}")
        else:
            client = OpenAI() # Assumes OPENAI_API_KEY is set in environment
            logger.info(f"[VisionTool] Using OpenAI API with model {self.model_name}")

        try:
            # Check if file exists
            if not os.path.exists(image_path):
                logger.error(f"[VisionTool] File not found at {image_path}")
                return f"Error: Image file not found at {image_path}"

            # Encode image
            logger.info("[VisionTool] Encoding image...")
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            logger.info(f"[VisionTool] Sending request to LLM ({self.model_name})...")
            response = client.chat.completions.create(
                model=self.model_name,
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
