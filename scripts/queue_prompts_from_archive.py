import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.third_parties.comfyui_client import ComfyUIClient
from src.database.image_logs_storage import ImageLogsStorage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants from user request
NEGATIVE_PROMPT = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走, censored, sunburnt skin, rashy skin, red cheeks, pouty face, duckbil face"

async def main(kol_persona=None, workflow_type=None):
    parser = argparse.ArgumentParser(description="Queue prompts for generation (Step 2)")
    parser.add_argument("--persona", help="Persona name to filter prompts (e.g., Jennie, Sephera)")
    parser.add_argument("--workflow", default="turbo", help="Workflow type: 'turbo' or 'wan2.2'")
    
    # Only parse args if not provided directly
    target_persona = kol_persona
    target_workflow = workflow_type

    if target_persona is None or target_workflow is None:
        try:
            args, _ = parser.parse_known_args()
            if target_persona is None:
                target_persona = args.persona
            if target_workflow is None:
                target_workflow = args.workflow
        except Exception:
            pass
    
    if target_workflow is None:
        target_workflow = "turbo"

    effective_persona = target_persona if target_persona else "Jennie"

    ready_dir = Path("ready")
    crawl_dir = Path("crawl")
    
    if not ready_dir.exists():
        logger.error(f"Directory {ready_dir} not found.")
        return

    # Find valid prompt files: .txt files
    all_files = [
        f for f in ready_dir.glob("*.txt") 
        if not f.name.endswith("_description.txt") and f.name != "executions.json"
    ]
    
    # Filter by persona
    prompt_files = all_files
    if target_persona:
        filtered_files = [f for f in all_files if f.name.startswith(f"{target_persona}_")]
        if filtered_files:
            prompt_files = filtered_files
            logger.info(f"Filtering for persona '{target_persona}': Found {len(prompt_files)} matching files.")
        else:
            logger.warning(f"No files found with prefix '{target_persona}_'. Processing ALL {len(all_files)} files using persona '{effective_persona}'.")
    else:
        logger.info(f"No persona filter applied. Processing all {len(prompt_files)} files.")
    
    if not prompt_files:
        logger.warning(f"No prompt files found in {ready_dir}")
        return

    logger.info(f"Processing {len(prompt_files)} prompt files...")

    client = ComfyUIClient()
    storage = ImageLogsStorage() # Uses default image_logs.db
    
    queued_count = 0
    failed_count = 0
    
    for file_path in prompt_files:
        try:
            prompt_content = file_path.read_text(encoding='utf-8').strip()
            
            if not prompt_content:
                logger.warning(f"Skipping empty file: {file_path.name}")
                continue

            # Identify original image in crawl directory
            base_name = file_path.stem
            image_extensions = ['.png', '.jpg', '.jpeg', '.webp']
            original_image_path = None
            
            for ext in image_extensions:
                possible_path = crawl_dir / f"{base_name}{ext}"
                if possible_path.exists():
                    original_image_path = str(possible_path)
                    break
            
            if not original_image_path:
                logger.warning(f"⚠️ Original image not found for {file_path.name} in {crawl_dir}")
            
            logger.info(f"Queueing prompt from {file_path.name}...")
            
            execution_id = await client.generate_image(
                positive_prompt=prompt_content,
                negative_prompt=NEGATIVE_PROMPT,
                kol_persona=effective_persona,
                workflow_type=target_workflow
            )
            
            logger.info(f"✅ Queued {file_path.name} - Execution ID: {execution_id}")
            
            # Log to DB instead of JSON
            storage.log_execution(
                execution_id=execution_id,
                prompt=prompt_content,
                image_ref_path=original_image_path
            )
            
            queued_count += 1
            
        except Exception as e:
            logger.error(f"❌ Failed to queue {file_path.name}: {e}")
            failed_count += 1

    logger.info("=" * 40)
    logger.info(f"Processing Complete")
    logger.info(f"Queued: {queued_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())
