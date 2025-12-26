import os
import sys
import asyncio
import logging
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.third_parties.comfyui_client import ComfyUIClient
from src.database.image_logs_storage import ImageLogsStorage
from src.third_parties.gcs_client import upload_image_to_gcs

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PopulateImages")

async def main():
    output_dir = Path(GlobalConfig.OUTPUT_DIR)
    
    # Create output dir if not exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    storage = ImageLogsStorage()
    client = ComfyUIClient()
    
    pending_items = storage.get_pending_executions()
    
    if not pending_items:
        logger.info("No pending executions found in database.")
        return

    logger.info(f"Checking {len(pending_items)} pending executions...")
    
    for item in pending_items:
        execution_id = item['execution_id']
        image_ref_path = item['image_ref_path']
        
        if not execution_id:
            continue
            
        try:
            # Check Status
            try:
                status_data = await client.check_status(execution_id)
                status = status_data.get("status")
            except Exception as e:
                logger.error(f"Failed to check status for {execution_id}: {e}")
                continue

            if status == "completed":
                logger.info(f"✅ Execution {execution_id} completed. Processing...")
                
                # Get output image path
                output_images = status_data.get("output_images", [])
                comfy_image_path = None
                
                if output_images and isinstance(output_images, list):
                    first_output = output_images[0]
                    if isinstance(first_output, dict):
                        for key, paths in first_output.items():
                            if paths and len(paths) > 0:
                                comfy_image_path = paths[0]
                                break
                
                if comfy_image_path:
                    # Download Generated Image
                    try:
                        image_bytes = await client.download_image_by_path(comfy_image_path)
                    except Exception as e:
                        logger.error(f"Failed to download image for {execution_id}: {e}")
                        continue
                    
                    # Determine Base Name from Ref Image
                    base_name = "unknown"
                    if image_ref_path:
                        base_name = Path(image_ref_path).stem
                        # If ref name starts with ref_, maybe keep it or strip it?
                        # User convention: ref_{timestamp}_{uuid}
                        # Result convention: result_{base_name}.png
                    else:
                        base_name = execution_id

                    # Save Result Image to OUTPUT_DIR
                    result_filename = f"result_{base_name}.png"
                    local_result_path = output_dir / result_filename
                    
                    local_result_path.write_bytes(image_bytes)
                    logger.info(f"Saved local result to {local_result_path}")
                    
                    # Upload to GCP (Optional - keeping for compatibility if configured)
                    # If GCP credentials are missing, this might fail or be skipped.
                    # We'll prioritize the local path for DB update as requested by volume architecture.
                    
                    # Update Database
                    # We store the local absolute path (or relative to container)
                    # Ensuring it points to the volume location.
                    storage.update_result_path(
                        execution_id=execution_id, 
                        result_image_path=str(local_result_path),
                        new_ref_path=None # We didn't move the ref image
                    )
                    logger.info(f"Database updated for {execution_id}")
                        
                else:
                    logger.warning(f"No output image path found for {execution_id}")

            elif status == "failed":
                logger.error(f"❌ Execution {execution_id} failed. Marking as failed in DB.")
                storage.mark_as_failed(execution_id)
                
            else:
                # Still running/queued
                pass
                
        except Exception as e:
            logger.error(f"Error processing {execution_id}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
