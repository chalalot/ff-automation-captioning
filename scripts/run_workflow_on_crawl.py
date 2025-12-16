import os
import sys
import asyncio
import argparse

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

async def main():
    parser = argparse.ArgumentParser(description="Run image-to-prompt workflow")
    parser.add_argument("--mode", choices=["self", "crawl"], help="Mode: 'self' for specific files, 'crawl' for folders")
    parser.add_argument("--file", help="File path for self input mode")
    parser.add_argument("--folder", choices=["indoor", "outdoor", "crawl"], help="Folder choice for crawl mode")
    parser.add_argument("--persona", default="Jennie", help="Persona name (e.g. Jennie, Sephera)")
    
    args = parser.parse_args()
    
    mode = args.mode
    files_to_process = []
    
    # 1. Determine Mode
    if not mode:
        print("\nSelect Workflow Mode:")
        print("1. Self Input (Specific File)")
        print("2. From Crawled Folders")
        choice = input("Enter choice (1/2): ").strip()
        if choice == "1":
            mode = "self"
        else:
            mode = "crawl"
    
    # 2. Collect Files based on Mode
    if mode == "self":
        file_path = args.file
        if not file_path:
            file_path = input("Enter image file path: ").strip()
        
        # Remove quotes if user added them
        file_path = file_path.strip('"').strip("'")
            
        if os.path.exists(file_path):
            files_to_process.append(file_path)
        else:
            print(f"❌ File not found: {file_path}")
            return
            
    else: # mode == "crawl"
        folder_choice = args.folder
        if not folder_choice:
            print("\nSelect Source Folder:")
            print("1. Indoor (/Sorted/Indoor)")
            print("2. Outdoor (/Sorted/Outdoor)")
            print("3. Local 'crawl' folder (Default)")
            f_choice = input("Enter choice (1/2/3): ").strip()
            
            if f_choice == "1":
                crawl_dir = "app/Sorted/Indoor"
            elif f_choice == "2":
                crawl_dir = "app/Sorted/Outdoor"
            else:
                crawl_dir = "crawl"
        else:
            if folder_choice == "indoor":
                crawl_dir = "app/Sorted/Indoor"
            elif folder_choice == "outdoor":
                crawl_dir = "app/Sorted/Outdoor"
            else:
                crawl_dir = "crawl"
                
        print(f"📂 Selected Source Directory: {crawl_dir}")
        
        if not os.path.exists(crawl_dir):
            print(f"❌ Directory {crawl_dir} not found.")
            return

        # Filter for image files
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
        found_files = [f for f in os.listdir(crawl_dir) if f.lower().endswith(valid_exts)]
        found_files.sort()

        if not found_files:
            print(f"No images found in {crawl_dir}/ directory.")
            return

        print(f"Found {len(found_files)} images in {crawl_dir}.")
        
        # Limit only applies to crawl mode unless we want otherwise. keeping existing logic.
        LIMIT = 20
        print(f"Processing first {LIMIT} images for demonstration...")
        
        for filename in found_files[:LIMIT]:
            files_to_process.append(os.path.join(crawl_dir, filename))

    if not files_to_process:
        print("No files to process.")
        return

    print(f"🚀 Starting processing for {len(files_to_process)} files...")

    # Initialize workflow
    workflow = ImageToPromptWorkflow(verbose=True)
    results = []
    
    # Ensure ready directory exists
    ready_dir = "ready"
    os.makedirs(ready_dir, exist_ok=True)
    
    for image_path in files_to_process:
        filename = os.path.basename(image_path)
        try:
            result = await workflow.process(
                image_path=image_path,
                persona_name=args.persona,
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
