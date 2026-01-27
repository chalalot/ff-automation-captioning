import os
import sys
from pathlib import Path

def check_file_content(path, search_str=None, description="File"):
    print(f"\n--- Checking {description}: {path} ---")
    if not os.path.exists(path):
        print(f"❌ File NOT FOUND at {path}")
        return False
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"✅ File exists. Size: {len(content)} bytes.")
            if search_str:
                if search_str in content:
                    print(f"✅ Found expected string: '{search_str}'")
                else:
                    print(f"❌ Expected string '{search_str}' NOT FOUND in content.")
                    print("First 200 chars:")
                    print(content[:200])
            else:
                print("First 200 chars:")
                print(content[:200])
            return content
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

def main():
    print("Starting Diagnosis...")
    cwd = os.getcwd()
    print(f"Current Working Directory: {cwd}")

    # 1. Check if Codebase is Updated
    workflow_path = os.path.join(cwd, 'src', 'workflows', 'video_storyboard_workflow.py')
    content = check_file_content(workflow_path, "DEBUG: Raw Template Content", "Workflow Code")
    
    if content and "DEBUG: Raw Template Content" not in content:
        print("\n⚠️ WARNING: The code in this environment DOES NOT contain the debug prints I added.")
        print("This means the Docker container is running OLD CODE.")
        print("Action: You likely need to rebuild the image ensuring the cache is busted, or verify volume mounts.")

    # 2. Check Prompt File
    prompt_path = os.path.join(cwd, 'prompts', 'workflows', 'video_analyst_task.txt')
    prompt_content = check_file_content(prompt_path, "{image_path}", "Analyst Prompt Template")

    if prompt_content:
        if "{image_path}" in prompt_content:
             print("\n✅ Prompt file uses correct placeholder '{image_path}'")
        elif "[image_path]" in prompt_content:
             print("\n❌ Prompt file uses INCORRECT placeholder '[image_path]'")
        else:
             print("\n❌ Prompt file uses UNKNOWN placeholder pattern.")

        # 3. Simulate Formatting
        print("\n--- Simulating Template Formatting ---")
        image_path = "/tmp/test_image.png"
        try:
            formatted = prompt_content.format(image_path=f'"{image_path}"')
            print("Formatting Result (Start):")
            print(formatted[:200])
            if f'"{image_path}"' in formatted:
                print("✅ Formatting SUCCESS: Path injected correctly.")
            else:
                print("❌ Formatting FAILED: Path NOT found in output.")
        except Exception as e:
            print(f"❌ Formatting threw exception: {e}")

if __name__ == "__main__":
    main()
