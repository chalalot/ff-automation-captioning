import os
import sys
import asyncio

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

async def main():
    crawl_dir = "crawl"
    if not os.path.exists(crawl_dir):
        print(f"Directory {crawl_dir} not found.")
        return

    # Filter for image files
    valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
    image_files = [f for f in os.listdir(crawl_dir) if f.lower().endswith(valid_exts)]
    image_files.sort()

    if not image_files:
        print("No images found in crawl/ directory.")
        return

    print(f"Found {len(image_files)} images in {crawl_dir}. Starting processing...")

    # Initialize workflow
    workflow = ImageToPromptWorkflow(verbose=True)

    output_file = "generated_prompts.txt"
    results = []

    # Process each image
    # For demonstration, we'll limit to the first 5 images.
    LIMIT = 20
    print(f"Processing first {LIMIT} images for demonstration...")
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Generated Prompts for 'Instagirl WAN2.2' (Limit: {LIMIT})\n")
        f.write("="*80 + "\n\n")

        for filename in image_files[:LIMIT]:
            image_path = os.path.join(crawl_dir, filename)
            
            try:
                result = await workflow.process(
                    image_path=image_path,
                    persona_name="Jennie",
                    trigger_generation=False # Explicitly False as requested
                )
                
                results.append(result)
                
                # Format output for file
                output_block = (
                    f"📸 Image: {filename}\n"
                    f"📍 Path: {image_path}\n"
                    f"📝 Prompt:\n{result['generated_prompt']}\n"
                    f"{'-'*80}\n"
                )
                
                f.write(output_block)
                f.flush() # Ensure it's written immediately
                
                print(f"✅ Processed {filename}")
                
            except Exception as e:
                error_msg = f"❌ Error processing {filename}: {e}\n"
                print(error_msg.strip())
                f.write(error_msg + "-"*80 + "\n")

    print(f"\nCompleted processing {len(results)} images. Results saved to {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
