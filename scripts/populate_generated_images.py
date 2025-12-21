import os
import sys
import asyncio
import logging
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.third_parties.comfyui_client import ComfyUIClient
from src.database.image_logs_storage import ImageLogsStorage
from src.third_parties.gcs_client import upload_image_to_gcs

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    archive_dir = Path("crawl_archive")
    archive_dir.mkdir(exist_ok=True)
    
    ready_dir = Path("ready")
    
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
            status_data = await client.check_status(execution_id)
            status = status_data.get("status")
            
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
                    image_bytes = await client.download_image_by_path(comfy_image_path)
                    
                    # Determine Base Name
                    base_name = "unknown"
                    if image_ref_path:
                        base_name = Path(image_ref_path).stem
                    else:
                        base_name = execution_id

                    # 1. Rename & Archive Ref Image
                    new_ref_path = None
                    if image_ref_path and os.path.exists(image_ref_path):
                        original_ext = Path(image_ref_path).suffix
                        # Rename logic: [basename]_ref.[ext]
                        ref_filename = f"{base_name}_ref{original_ext}"
                        dest_ref = archive_dir / ref_filename
                        
                        shutil.move(image_ref_path, str(dest_ref))
                        new_ref_path = str(dest_ref)
                        logger.info(f"Moved ref image to {dest_ref}")
                    elif image_ref_path:
                        # If file doesn't exist (already moved?), keep old path or check archive?
                        # Assume it might be missing or already moved.
                        logger.warning(f"Ref image not found at {image_ref_path}")
                        new_ref_path = image_ref_path # Keep original string if move failed
                    
                    # 2. Rename & Archive Prompt File
                    # Infer prompt file from base_name in ready/ directory
                    prompt_file = ready_dir / f"{base_name}.txt"
                    if prompt_file.exists():
                        dest_prompt = archive_dir / f"{base_name}_prompt.txt"
                        shutil.move(str(prompt_file), str(dest_prompt))
                        logger.info(f"Moved prompt file to {dest_prompt}")
                    
                    # 3. Rename & Upload Result Image
                    # Naming: [basename]_result.png
                    result_filename = f"{base_name}_result.png"
                    
                    # Optional: Save locally to archive for backup
                    local_result_path = archive_dir / result_filename
                    local_result_path.write_bytes(image_bytes)
                    logger.info(f"Saved local result to {local_result_path}")
                    
                    # Upload to GCP
                    gcs_path = f"generated/{result_filename}"
                    logger.info(f"Uploading result to GCP: {gcs_path}")
                    
                    try:
                        public_url = upload_image_to_gcs(
                            image_bytes=image_bytes,
                            gcs_path=gcs_path,
                            content_type="image/png"
                        )
                        logger.info(f"Uploaded to GCP: {public_url}")
                        
                        # 4. Update Database
                        storage.update_result_path(
                            execution_id=execution_id, 
                            result_image_path=public_url,
                            new_ref_path=new_ref_path
                        )
                        logger.info(f"Database updated for {execution_id}")
                        
                    except Exception as upload_err:
                        logger.error(f"Failed to upload to GCP: {upload_err}")
                        # Update DB with local path if GCP fails? Or leave NULL?
                        # Leaving NULL might cause retry loop which is good for transient errors.
                        # But if files are moved, retry might fail on ref image move.
                        # Ref image move is already done.
                        # If GCP fails, we should probably NOT leave it NULL if we can't retry cleanly.
                        # But "stuck" usually implies we WANT retry.
                        # If retry happens: ref image move will fail (file not found). logic handles check `if os.path.exists`.
                        # So retry is safe.
                        pass
                        
                else:
                    logger.warning(f"No output image path found for {execution_id}")

            elif status == "failed":
                logger.error(f"❌ Execution {execution_id} failed.")
                # Optional: Mark as failed in DB?
                # storage.update_result_path(execution_id, "FAILED")
                
            else:
                # Still running/queued
                pass
                
        except Exception as e:
            logger.error(f"Error processing {execution_id}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
