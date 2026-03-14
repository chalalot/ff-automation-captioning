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
from tasks import process_image_task

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ProcessAndQueue")

async def main(persona="Jennie", workflow_type="turbo", limit=10, progress_callback=None, strength_model=None, seed_strategy="random", base_seed=0, width="1024", height="1600", vision_model="gpt-4o", lora_name=None, variation_count=1, clip_model_type="sd3"):
    """
    Main processing loop:
    1. Scans INPUT_DIR for images.
    2. Moves them to PROCESSED_DIR and renames them.
    3. Generates prompts using CrewAI (supports multiple variations).
    4. Queues generation in ComfyUI for each variation.
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
    
    queued_task_ids = []
    
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
                    # Pass the current filename to the callback
                    progress_callback(src_image_path.name)
                except TypeError:
                    # Fallback for callbacks that don't accept arguments
                    progress_callback()
                except Exception as cb_err:
                    logger.warning(f"Progress callback failed: {cb_err}")

            # 2. Queue Celery Task
            task = process_image_task.delay(
                dest_image_path=str(dest_image_path),
                persona=persona,
                workflow_type=workflow_type,
                vision_model=vision_model,
                variation_count=variation_count,
                strength_model=strength_model,
                seed_strategy=seed_strategy,
                base_seed=base_seed,
                width=width,
                height=height,
                lora_name=lora_name,
                clip_model_type=clip_model_type
            )
            
            logger.info(f"Queued Celery Task ID: {task.id} for {new_filename}")
            queued_task_ids.append(task.id)
            
        except Exception as e:
            logger.error(f"❌ Error processing {src_image_path.name}: {e}")
            
    logger.info("=" * 40)
    logger.info(f"Batch Queued. Dispatched {len(queued_task_ids)} tasks to Celery.")
    logger.info("=" * 40)
    
    return queued_task_ids

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process images from INPUT_DIR, generate prompts, and queue to ComfyUI.")
    parser.add_argument("--persona", default="Jennie", help="Persona name")
    parser.add_argument("--workflow", default="turbo", help="Workflow type (turbo)")
    parser.add_argument("--limit", type=int, default=10, help="Max images to process in one run")
    parser.add_argument("--strength_model", default=None, help="Strength of the LoRA model")
    parser.add_argument("--seed_strategy", default="random", help="Seed strategy (random/fixed)")
    parser.add_argument("--base_seed", type=int, default=0, help="Base seed for fixed strategy")
    parser.add_argument("--width", default="1024", help="Image width")
    parser.add_argument("--height", default="1600", help="Image height")
    parser.add_argument("--vision_model", default="gpt-4o", help="Vision model (gpt-4o/grok-4-1-fast-non-reasoning)")
    parser.add_argument("--lora_name", default=None, help="LoRA name override for Turbo")
    parser.add_argument("--variation_count", type=int, default=1, help="Number of prompt variations per image")
    parser.add_argument("--clip_model_type", type=str, default="sd3", help="Type of CLIP model to use")
    args = parser.parse_args()
    
    asyncio.run(main(persona=args.persona, workflow_type=args.workflow, limit=args.limit, strength_model=args.strength_model, seed_strategy=args.seed_strategy, base_seed=args.base_seed, width=args.width, height=args.height, vision_model=args.vision_model, lora_name=args.lora_name, variation_count=args.variation_count, clip_model_type=args.clip_model_type))
