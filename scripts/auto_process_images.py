import os
import sys
import argparse
import asyncio
import logging
import shutil
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("automation.log")
    ]
)
logger = logging.getLogger("AutoProcess")

async def main():
    parser = argparse.ArgumentParser(description="Automated Image-to-Prompt Processing (Step 1)")
    parser.add_argument("--source", required=True, help="Source directory containing images (e.g., Sorted/Indoor)")
    parser.add_argument("--persona", required=True, help="Persona name (e.g., Jennie, Sephera)")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of images to process")
    
    args = parser.parse_args()
    
    source_dir = Path(args.source)
    persona = args.persona
    limit = args.limit
    
    crawl_dir = Path("crawl")
    ready_dir = Path("ready")
    
    # Validation
    if not source_dir.exists():
        logger.error(f"Source directory {source_dir} does not exist.")
        return

    # Create directories if they don't exist
    crawl_dir.mkdir(exist_ok=True)
    ready_dir.mkdir(exist_ok=True)
    
    # Find images
    valid_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    images = [f for f in source_dir.iterdir() if f.suffix.lower() in valid_exts and f.is_file()]
    images.sort() # Deterministic order
    
    if not images:
        logger.info(f"No images found in {source_dir}.")
        return

    # Select batch
    batch = images[:limit]
    logger.info(f"Found {len(images)} images. Processing batch of {len(batch)} for persona '{persona}'.")
    
    # Initialize workflow
    workflow = ImageToPromptWorkflow(verbose=False) # Reduce noise in logs
    
    successful_count = 0
    
    for src_image_path in batch:
        try:
            # 1. Prepare filenames
            original_filename = src_image_path.name
            # Prefix with persona to track ownership
            new_filename = f"{persona}_{original_filename}"
            dest_image_path = crawl_dir / new_filename
            
            # 2. Move image to crawl directory
            # We move it so it's not processed again from source
            logger.info(f"Moving {src_image_path} -> {dest_image_path}")
            shutil.move(str(src_image_path), str(dest_image_path))
            
            # 3. Process with Workflow
            # Note: We pass the path in crawl dir
            logger.info(f"Processing {new_filename}...")
            result = await workflow.process(
                image_path=str(dest_image_path),
                persona_name=persona
            )
            
            # 4. Save Prompt
            # Filename should match the image filename stem for consistency
            base_name = dest_image_path.stem # e.g. Jennie_image1
            output_txt_path = ready_dir / f"{base_name}.txt"
            
            output_txt_path.write_text(result['generated_prompt'], encoding="utf-8")
            logger.info(f"✅ Prompt saved to {output_txt_path}")
            
            successful_count += 1
            
        except Exception as e:
            logger.error(f"❌ Error processing {src_image_path.name}: {e}")
            # If failed, maybe move back? For now, we leave it or manual intervention.
    
    logger.info(f"Batch complete. Successfully processed {successful_count}/{len(batch)} images.")

if __name__ == "__main__":
    asyncio.run(main())
