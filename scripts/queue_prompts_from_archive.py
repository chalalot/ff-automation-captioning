import os
import sys
import asyncio
import logging
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.third_parties.comfyui_client import ComfyUIClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants from user request
NEGATIVE_PROMPT = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走, censored, sunburnt skin, rashy skin, red cheeks, pouty face, duckbil face"

async def main(kol_persona="Jennie"):
    ready_dir = Path("ready")
    crawl_dir = Path("crawl")
    
    if not ready_dir.exists():
        logger.error(f"Directory {ready_dir} not found.")
        return

    # Find valid prompt files: .txt files
    # In ready folder we expect only the generated prompts, but we can keep the filter just in case
    prompt_files = [
        f for f in ready_dir.glob("*.txt") 
        if not f.name.endswith("_description.txt") and f.name != "executions.json"
    ]
    
    if not prompt_files:
        logger.warning(f"No prompt files found in {ready_dir}")
        return

    logger.info(f"Found {len(prompt_files)} prompt files in {ready_dir}")

    client = ComfyUIClient()
    
    # Process each file
    queued_count = 0
    failed_count = 0
    
    # Load existing executions if any
    executions_file = ready_dir / "executions.json"
    executions_data = []
    if executions_file.exists():
        try:
            executions_data = json.loads(executions_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            logger.warning("Could not decode existing executions.json, starting fresh.")

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
                # We proceed anyway, but note it
            
            logger.info(f"Queueing prompt from {file_path.name}...")
            
            execution_id = await client.generate_image(
                positive_prompt=prompt_content,
                negative_prompt=NEGATIVE_PROMPT,
                kol_persona=kol_persona
            )
            
            logger.info(f"✅ Queued {file_path.name} (Persona: {kol_persona}) - Execution ID: {execution_id}")
            
            # Record execution data
            executions_data.append({
                "base_name": base_name,
                "prompt_file": str(file_path),
                "original_image": original_image_path,
                "execution_id": execution_id,
                "status": "queued"
            })
            
            queued_count += 1
            
        except Exception as e:
            logger.error(f"❌ Failed to queue {file_path.name}: {e}")
            failed_count += 1

    # Save executions.json
    executions_file.write_text(json.dumps(executions_data, indent=2), encoding='utf-8')
    logger.info(f"Saved execution data to {executions_file}")

    logger.info("=" * 40)
    logger.info(f"Processing Complete")
    logger.info(f"Queued: {queued_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())
