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

    # Ensure ready directory exists
    ready_dir = "ready"
    os.makedirs(ready_dir, exist_ok=True)
    
    for filename in image_files[:LIMIT]:
        image_path = os.path.join(crawl_dir, filename)
        
        try:
            result = await workflow.process(
                image_path=image_path,
                persona_name="Jennie",
                trigger_generation=False # Explicitly False as requested
            )
            
            results.append(result)
            
            # Save to individual file in ready folder
            base_name = os.path.splitext(filename)[0]
            output_txt_path = os.path.join(ready_dir, f"{base_name}.txt")
            
            with open(output_txt_path, "w", encoding="utf-8") as f:
                f.write(result['generated_prompt'])
            
            print(f"✅ Processed {filename} -> {output_txt_path}")
            
        except Exception as e:
            error_msg = f"❌ Error processing {filename}: {e}\n"
            print(error_msg.strip())

    print(f"\nCompleted processing {len(results)} images. Results saved to {ready_dir}/")

if __name__ == "__main__":
    asyncio.run(main())
