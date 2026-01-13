import shutil
import os

src_dir = "prompts/templates/instagirl"
dst_dir = "prompts/templates/dancer"

if not os.path.exists(dst_dir):
    os.makedirs(dst_dir)
    print(f"Created directory: {dst_dir}")

files_to_copy = [
    "analyst_agent.txt",
    "analyst_task.txt",
    "turbo_agent.txt",
    "turbo_constraints.txt",
    "turbo_example.txt",
    "turbo_framework.txt",
    "turbo_prompt_template.txt"
]

for file in files_to_copy:
    src = os.path.join(src_dir, file)
    dst = os.path.join(dst_dir, file)
    if os.path.exists(src):
        print(f"Copying {src} to {dst}")
        shutil.copy2(src, dst)
    else:
        print(f"Warning: {src} does not exist")
