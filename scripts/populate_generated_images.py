import os
import sys
import asyncio
import logging
import json
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.third_parties.comfyui_client import ComfyUIClient, ComfyUIAPIError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    ready_dir = Path("ready")
    archive_dir = Path("crawl_archive")
    executions_file = ready_dir / "executions.json"
    
    if not executions_file.exists():
        logger.error(f"Executions file not found at {executions_file}")
        return

    try:
        executions_data = json.loads(executions_file.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        logger.error("Failed to decode executions.json")
        return

    if not executions_data:
        logger.info("No executions to process.")
        return

    logger.info(f"Checking {len(executions_data)} executions...")
    
    client = ComfyUIClient()
    
    # Track which indices to remove (completed ones)
    completed_indices = []
    
    # Ensure archive directory exists
    archive_dir.mkdir(exist_ok=True)

    for i, item in enumerate(executions_data):
        execution_id = item.get("execution_id")
        base_name = item.get("base_name")
        prompt_file = Path(item.get("prompt_file"))
        original_image = Path(item.get("original_image")) if item.get("original_image") else None
        
        if not execution_id:
            logger.warning(f"Skipping item {i} due to missing execution_id")
            continue
            
        logger.info(f"Checking status for {base_name} ({execution_id})...")
        
        try:
            status_data = await client.check_status(execution_id)
            status = status_data.get("status")
            
            if status == "completed":
                logger.info(f"✅ {base_name} is completed. Downloading...")
                
                # Get output image path
                output_images = status_data.get("output_images", [])
                image_path = None
                
                # Logic to extract path from output_images structure
                # Structure: [{"node_id": ["path1", "path2"]}] or similar
                if output_images and isinstance(output_images, list):
                    first_output = output_images[0]
                    if isinstance(first_output, dict):
                        for key, paths in first_output.items():
                            if paths and len(paths) > 0:
                                image_path = paths[0]
                                break
                
                if image_path:
                    # Download generated image
                    image_bytes = await client.download_image_by_path(image_path)
                    
                    # Define destination paths
                    # Use base_name for consistency
                    # 1. Original Image
                    if original_image and original_image.exists():
                        dest_original = archive_dir / original_image.name
                        shutil.move(str(original_image), str(dest_original))
                        logger.info(f"Moved original image to {dest_original}")
                    else:
                        logger.warning(f"Original image not found at {original_image}")

                    # 2. Prompt File
                    if prompt_file.exists():
                        dest_prompt = archive_dir / prompt_file.name
                        shutil.move(str(prompt_file), str(dest_prompt))
                        logger.info(f"Moved prompt file to {dest_prompt}")
                    else:
                        logger.warning(f"Prompt file not found at {prompt_file}")
                        
                    # 3. Generated Image
                    # Save as basename_generated.png (ComfyUI usually returns PNG)
                    # We can infer extension from image_path or just assume .png
                    ext = os.path.splitext(image_path)[1] or ".png"
                    generated_filename = f"{base_name}_generated{ext}"
                    dest_generated = archive_dir / generated_filename
                    
                    dest_generated.write_bytes(image_bytes)
                    logger.info(f"Saved generated image to {dest_generated}")
                    
                    completed_indices.append(i)
                    
                else:
                    logger.warning(f"No output image path found for completed execution {execution_id}")

            elif status == "failed":
                logger.error(f"❌ Execution {execution_id} failed.")
                # Optional: Handle failure (remove from list? keep for retry?)
                # For now, keep it in list but maybe mark as failed?
                # item['status'] = 'failed' 
                
            else:
                logger.info(f"⏳ Status: {status}")

        except Exception as e:
            logger.error(f"Error checking/processing {base_name}: {e}")

    # Remove completed items from the list (in reverse order to avoid index shifting)
    for i in sorted(completed_indices, reverse=True):
        executions_data.pop(i)
        
    # Save updated executions.json
    executions_file.write_text(json.dumps(executions_data, indent=2), encoding='utf-8')
    logger.info(f"Updated executions.json. Remaining pending: {len(executions_data)}")

if __name__ == "__main__":
    asyncio.run(main())
