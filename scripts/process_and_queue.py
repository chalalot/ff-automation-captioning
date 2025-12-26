import os
import sys
import asyncio
import logging
import shutil
import uuid
import time
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import GlobalConfig
from src.third_parties.comfyui_client import ComfyUIClient
from src.database.image_logs_storage import ImageLogsStorage
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow
from utils.constants import DEFAULT_NEGATIVE_PROMPT

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ProcessAndQueue")

async def main(persona="Jennie", workflow_type="turbo", limit=10, progress_callback=None):
    """
    Main processing loop:
    1. Scans INPUT_DIR for images.
    2. Moves them to PROCESSED_DIR and renames them.
    3. Generates prompts using CrewAI.
    4. Queues generation in ComfyUI.
    5. Logs to DB.
    """
    
    input_dir = Path(GlobalConfig.INPUT_DIR)
    processed_dir = Path(GlobalConfig.PROCESSED_DIR)
    
    # Validation
    if not input_dir.exists():
        logger.error(f"Input directory {input_dir} does not exist. Please check your config.")
        return

    # Create processed dir if not exists
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Find images
    valid_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    try:
        images = [f for f in input_dir.iterdir() if f.suffix.lower() in valid_exts and f.is_file()]
        images.sort() # Deterministic order
    except Exception as e:
        logger.error(f"Failed to list images in {input_dir}: {e}")
        return
    
    if not images:
        logger.info(f"No images found in {input_dir}.")
        return

    # Select batch
    batch = images[:limit]
    logger.info(f"Found {len(images)} images. Processing batch of {len(batch)} for persona '{persona}'.")
    
    # Initialize components
    # verbose=False to reduce clutter in logs, since we log main steps here
    workflow = ImageToPromptWorkflow(verbose=False)
    client = ComfyUIClient()
    storage = ImageLogsStorage()
    
    successful_count = 0
    
    for src_image_path in batch:
        try:
            # 1. Rename & Move to Processed Dir
            original_filename = src_image_path.name
            timestamp = int(time.time())
            unique_id = str(uuid.uuid4())[:8]
            ext = src_image_path.suffix
            
            # Naming convention: ref_{timestamp}_{uuid}.ext
            new_filename = f"ref_{timestamp}_{unique_id}{ext}"
            dest_image_path = processed_dir / new_filename
            
            logger.info(f"Moving {src_image_path.name} -> {dest_image_path}")
            
            # Move file (consumes from input)
            shutil.move(str(src_image_path), str(dest_image_path))
            
            # Notify progress if callback provided
            if progress_callback:
                try:
                    progress_callback()
                except Exception as cb_err:
                    logger.warning(f"Progress callback failed: {cb_err}")

            # 2. Generate Prompt
            logger.info(f"Generating prompt for {new_filename}...")
            result = await workflow.process(
                image_path=str(dest_image_path),
                persona_name=persona,
                workflow_type=workflow_type
            )
            prompt_content = result['generated_prompt']
            
            # 3. Queue to ComfyUI
            logger.info(f"Queueing execution for {new_filename}...")
            execution_id = await client.generate_image(
                positive_prompt=prompt_content,
                negative_prompt=DEFAULT_NEGATIVE_PROMPT,
                kol_persona=persona,
                workflow_type=workflow_type
            )
            
            if execution_id:
                logger.info(f"✅ Queued - Execution ID: {execution_id}")
                
                # 4. Log to DB
                # Note: We use the path in PROCESSED_DIR as the reference
                storage.log_execution(
                    execution_id=execution_id,
                    prompt=prompt_content,
                    image_ref_path=str(dest_image_path),
                    persona=persona
                )
                successful_count += 1
            else:
                logger.error("Failed to get execution ID from ComfyUI.")
                # We could potentially move the image back to an 'error' folder or 'input' if we want to retry.
                # But for now, it's safer to leave it in 'processed' to avoid loops.
            
        except Exception as e:
            logger.error(f"❌ Error processing {src_image_path.name}: {e}")
            # Similar to above, leave in processed (or potentially an error folder).
            # If the move failed (e.g. permission error), the file might still be in input, which is fine (retry later).
    
    logger.info("=" * 40)
    logger.info(f"Batch Complete. Processed & Queued: {successful_count}/{len(batch)}")
    logger.info("=" * 40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process images from INPUT_DIR, generate prompts, and queue to ComfyUI.")
    parser.add_argument("--persona", default="Jennie", help="Persona name")
    parser.add_argument("--workflow", default="turbo", help="Workflow type (turbo/wan2.2)")
    parser.add_argument("--limit", type=int, default=10, help="Max images to process in one run")
    args = parser.parse_args()
    
    asyncio.run(main(persona=args.persona, workflow_type=args.workflow, limit=args.limit))
