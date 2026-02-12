import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BatchCaptionGemini")

async def process_folder(folder_path: str, persona: str = "Jennie", vision_model: str = "gemini-3-flash-preview"):
    """
    Process all images in a folder and generate captions using Gemini (or specified model).
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        logger.error(f"Folder not found: {folder_path}")
        return

    logger.info(f"Processing folder: {folder_path} with model: {vision_model}")
    
    # Initialize Workflow
    workflow = ImageToPromptWorkflow(verbose=True)
    
    # Supported extensions
    extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    
    files = [f for f in folder.iterdir() if f.suffix.lower() in extensions]
    files.sort()
    
    if not files:
        logger.warning(f"No image files found in {folder_path}")
        return
        
    logger.info(f"Found {len(files)} images to process.")
    
    for image_file in files:
        try:
            logger.info(f"--- Processing {image_file.name} ---")
            
            # check if txt already exists
            txt_path = image_file.with_suffix('.txt')
            if txt_path.exists() and txt_path.stat().st_size > 10:
                logger.info(f"Caption file already exists for {image_file.name}, skipping.")
                continue

            # Run Workflow
            # Defaulting to "turbo" workflow
            result = await workflow.process(
                image_path=str(image_file),
                persona_name=persona,
                workflow_type="turbo", 
                vision_model=vision_model
            )
            
            caption = result.get("generated_prompt", "")
            
            if caption:
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(caption)
                logger.info(f"Saved caption to {txt_path}")
            else:
                logger.warning(f"No caption generated for {image_file.name}")
                
        except Exception as e:
            logger.error(f"Failed to process {image_file.name}: {e}")
            # Continue to next file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch generate captions for images in a folder using Gemini.")
    parser.add_argument("folder", help="Path to the folder containing images")
    parser.add_argument("--persona", default="Jennie", help="Persona name (default: Jennie)")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Vision model to use (default: gemini-3-flash-preview)")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(process_folder(args.folder, args.persona, args.model))
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
