# CrewAI Workflows

This directory contains reusable CrewAI workflows for the application.

## Image To Prompt Workflow (`image_to_prompt_workflow.py`)

This workflow analyzes a reference image and generates a tailored prompt for "Instagirl WAN2.2" generation, focused on a daily, casual aesthetic.

### Features
- **Visual Analysis**: Uses GPT-4o Vision to analyze outfit, pose, and setting.
- **Prompt Engineering**: Creates strict, keyword-based prompts.
- **Style Rules**: Enforces "Casual/Daily" vibe, natural skin texture (no smooth/glowy), and specific hairstyle selection.
- **Dynamic Persona**: Supports different personas (default: "Jennie").
- **ComfyUI Integration**: (Optional) Can trigger generation via `ComfyUIClient`.

### Usage

#### 1. Import in your code
```python
import asyncio
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow

async def main():
    # Initialize workflow
    workflow = ImageToPromptWorkflow(verbose=True)
    
    # Process an image
    # Returns a dict: {"reference_image": str, "generated_prompt": str}
    result = await workflow.process(
        image_path="path/to/reference.jpg",
        persona_name="Jennie",   # Maps to specific LoRA settings in ComfyUIClient
        trigger_generation=False # Default is False (prompt only)
    )
    
    print(f"Generated Prompt: {result['generated_prompt']}")
    
    # If you want to trigger generation manually later:
    # await workflow._trigger_comfyui(result['generated_prompt'], "Jennie")

if __name__ == "__main__":
    asyncio.run(main())
```

#### 2. Run directly from CLI
You can also test the workflow module directly:
```bash
python -m src.workflows.image_to_prompt_workflow --image "path/to/image.jpg" --persona "Jennie"
```

### Configuration
- **Hairstyles**: The allowed hairstyles are defined in `ImageToPromptWorkflow.HAIRSTYLES`.
- **Style Instructions**: Modifications to the prompt style guidelines can be made in the `_create_engineer` method and the `generate_prompt_task` description.
