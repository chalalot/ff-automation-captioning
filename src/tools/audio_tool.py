import os
import logging
import time
from typing import Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from src.config import GlobalConfig

# Configure logger
logger = logging.getLogger(__name__)

class AudioToolInput(BaseModel):
    """Input schema for AudioTool."""
    audio_path: str = Field(..., description="The absolute local file path to the audio file (mp3, wav) to analyze.")
    prompt: str = Field(..., description="The question or instruction for the model about the audio.")

class AudioTool(BaseTool):
    name: str = "Audio Analysis Tool"
    description: str = (
        "A tool that uses Gemini 1.5 Flash to analyze audio files. "
        "It takes an audio file path and a prompt, and returns a text description."
    )
    args_schema: Type[BaseModel] = AudioToolInput
    model_name: str = "gemini-3-flash-preview"

    def _run(self, audio_path: str, prompt: str) -> str:
        logger.info(f"[AudioTool] _run called. Path: {audio_path}, Prompt: {prompt}")
        
        # Clean path
        audio_path = audio_path.strip().strip("'").strip('"')
        
        if not os.path.exists(audio_path):
            return f"Error: Audio file not found at {audio_path}"

        api_key = GlobalConfig.GEMINI_API_KEY
        if not api_key:
            return "Error: GEMINI_API_KEY not found in environment variables."

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            
            logger.info(f"[AudioTool] Uploading file to Gemini...")
            # Upload the file
            audio_file = genai.upload_file(path=audio_path)
            
            # Wait for processing (usually fast for audio, but good practice)
            while audio_file.state.name == "PROCESSING":
                time.sleep(1)
                audio_file = genai.get_file(audio_file.name)
                
            if audio_file.state.name == "FAILED":
                return "Error: Gemini failed to process the audio file."

            logger.info(f"[AudioTool] File uploaded: {audio_file.uri}")
            
            model = genai.GenerativeModel(self.model_name)
            
            logger.info(f"[AudioTool] Generating content...")
            response = model.generate_content([prompt, audio_file])
            
            # Cleanup? Gemini files persist for 48h. We might want to delete if possible, 
            # but for now let's leave it or check if delete_file exists.
            # genai.delete_file(audio_file.name) 
            
            return response.text
            
        except ImportError:
            return "Error: google-generativeai library not installed."
        except Exception as e:
            logger.error(f"[AudioTool] Error: {e}")
            return f"Error processing audio with Gemini: {str(e)}"
