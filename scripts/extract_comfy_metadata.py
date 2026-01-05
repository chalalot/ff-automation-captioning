import os
import json
import glob
from PIL import Image

def extract_metadata():
    results_dir = 'results'
    output_file = os.path.join(results_dir, 'extracted_metadata.json')
    
    # Check if results dir exists
    if not os.path.exists(results_dir):
        print(f"Directory {results_dir} not found.")
        return

    png_files = glob.glob(os.path.join(results_dir, '*.png'))
    print(f"Found {len(png_files)} PNG files in {results_dir}")

    all_metadata = {}
    count = 0

    for file_path in png_files:
        try:
            with Image.open(file_path) as img:
                meta = img.info
                filename = os.path.basename(file_path)
                
                # Check for 'prompt' key (ComfyUI API metadata)
                if 'prompt' in meta:
                    try:
                        prompt_data = json.loads(meta['prompt'])
                        all_metadata[filename] = prompt_data
                        count += 1
                        # print(f"Extracted metadata from {filename}")
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON from 'prompt' in {filename}")
                
                # Also check for 'workflow' key (ComfyUI GUI metadata) just in case
                if 'workflow' in meta:
                    try:
                        workflow_data = json.loads(meta['workflow'])
                        # If we already have prompt data, we can merge or store separately.
                        # For now, let's just store prompt as primary, or add workflow as a separate key if prompt exists
                        if filename in all_metadata:
                            all_metadata[filename]['_workflow_extra'] = workflow_data
                        else:
                            all_metadata[filename] = {'workflow': workflow_data}
                            count += 1
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON from 'workflow' in {filename}")

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    # Save to JSON file
    if all_metadata:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_metadata, f, indent=2)
        print(f"\nSuccessfully extracted metadata from {count} images.")
        print(f"Metadata saved to: {output_file}")
    else:
        print("\nNo ComfyUI metadata found in the images.")

if __name__ == "__main__":
