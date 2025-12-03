#!/usr/bin/env python3
"""
CrewAI Image-to-Prompt Workflow for Instagirl WAN2.2

This workflow analyzes a reference image and generates a highly specific
image generation prompt compatible with Instagirl WAN2.2 LoRA.

Features:
- Visual Analysis using GPT-4o (Vision)
- Strict adherence to prompt formatting rules (keywords, no bullets)
- Mandatory overrides (specific hairstyle)
- Long-term memory for preference learning

Usage:
  python scripts/crewai_image_prompt_workflow.py --image "path/to/reference.jpg"
"""

import argparse
import os
import sys
import asyncio
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai.memory.long_term.long_term_memory import LongTermMemory
from crewai.memory.short_term.short_term_memory import ShortTermMemory
from crewai.memory.entity.entity_memory import EntityMemory

# Add src to pythonpath
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.tools.vision_tool import VisionTool
from src.third_parties.comfyui_client import ComfyUIClient
from utils.constants import DEFAULT_NEGATIVE_PROMPT

# Load environment variables
load_dotenv()

def create_visual_analyst_agent() -> Agent:
    return Agent(
        role='Lead Visual Analyst',
        goal='Analyze reference images to extract precise visual details for reproduction.',
        backstory="""You are an expert photographer and visual director. 
        Your eyes miss nothing. You can analyze an image and breakdown the:
        - Exact outfit (colors, textures, cuts)
        - Pose and body language (hand placement, gaze, posture)
        - Lighting setup (shadows, source, tone)
        - Background and setting details
        - Mood and atmosphere
        You provide objective, detailed descriptions.""",
        tools=[VisionTool()],
        verbose=True,
        allow_delegation=False,
        memory=False,
        llm="gpt-4o"
    )

def create_prompt_engineer_agent() -> Agent:
    return Agent(
        role='Instagirl WAN2.2 Prompt Specialist',
        goal='Convert visual descriptions into strict Instagirl WAN2.2 keyword prompts.',
        backstory="""You are a specialist in prompting for the Instagirl WAN2.2 model.
        You know exactly how to format prompts for maximum realism:
        - You ALWAYS use the prefix: "<lora:jennie>, Instagirl, visible cleavage", do not remove the "<>" wrappers.
        - You writes CONCISE, comma-separated keywords.
        - You NEVER use full sentences, bullet points, or line breaks.
        - You always enforce specific client overrides (like hairstyle) regardless of the input image.
        - You focus on "professional photography-style", "realistic skin", and "high contrast".
        - You learn from past prompts to perfect the style over time.""",
        verbose=True,
        allow_delegation=False,
        memory=False, # Enable long-term memory to remember style preferences
        llm="gpt-4o"
    )

DEFAULT_WORKFLOW_ID = "82892890-19b4-4c3c-9ea9-5e004afd3343"

async def trigger_image_generation(positive_prompt: str, source_image: str):
    """Triggers image generation using ComfyUIClient."""
    print(f"\n🚀 Triggering ComfyUI Image Generation for source: {os.path.basename(source_image)}")
    
    client = ComfyUIClient()
    negative_prompt = DEFAULT_NEGATIVE_PROMPT

    # Construct specific payload as requested
    payload = {
        "workflow_id": DEFAULT_WORKFLOW_ID,
        "input_overrides": {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "persona_low_lora_name": "persona/WAN2.2-JennieV3_LowNoise_KhiemLe.safetensors",
            "persona_high_lora_name": "persona/WAN2.2-JennieV3_HighNoise_KhiemLe.safetensors"
        },
        "prompt_count": 1,
        "seed_config": {
            "strategy": "random",
            "base_seed": 0,
            "step": 1
        }
    }

    try:
        # Use _make_request directly as per instruction to control the exact payload
        response = await client._make_request(
            "POST",
            "/executions",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        data = response.json()
        print(f"✅ Request Sent! Response: {data}")
        
        # Optional: wait for completion if you want
        execution_id = data.get("execution_id") or data.get("id")
        
        # Check nested data if not found at top level
        if not execution_id and "data" in data and isinstance(data["data"], dict):
            execution_id = data["data"].get("execution_id")

        if execution_id:
             print(f"🆔 Execution ID: {execution_id}")
        else:
             print("⚠️ No execution ID found in response.")

    except Exception as e:
        print(f"❌ Failed to trigger generation: {e}")

def process_single_image(image_path: str, analyst: Agent, engineer: Agent):
    """Run the workflow for a single image."""
    print(f"\n{'='*60}")
    print(f"📸 PROCESSING IMAGE: {image_path}")
    print(f"{'='*60}")

    # Task 1: Analyze the image
    analyze_task = Task(
        description=f"""
        Analyze the reference image at: {image_path}
        
        Using the Vision Tool, describe the following elements in detail:
        1. **Outfit:** Detailed breakdown of clothing items, colors, and fit.
        2. **Pose/Action:** Specific position of hands, feet, head tilt, and body angle.
        3. **Gaze/Expression:** Where is she looking? What is the expression?
        4. **Background/Setting:** What is the environment? Indoor/outdoor? Colors?
        5. **Lighting/Mood:** Shadows, light direction, atmosphere.
        
        *Note: Describe the hair you see, but note that it will be overridden in the next step.*
        """,
        expected_output="A detailed textual description of the image's visual elements.",
        agent=analyst
    )

    # Task 2: Generate the Prompt
    generate_prompt_task = Task(
        description="""
        Create a final Image Generation Prompt for Instagirl WAN2.2 based on the visual analysis.

        **MANDATORY HARDCODED ELEMENTS (Override Visual Analysis):**
        - **Hair:** "honey-blonde hair tied in a half-up bun, loose face-framing strands"
        - **Subject:** "the girl (22-23 years old)"
        
        **STYLE & FORMATTING RULES:**
        1. **Prefix:** Start with `<lora:jennie>, Instagirl, visible cleavage`
        2. **Format:** Comma-separated keywords ONLY. No sentences. No line breaks.
        3. **Tone:** Affirmative, concise, focused.
        4. **Technical Quality Keywords to Include:** 
           "realistic skin, creamy warm tone, deep shadows, high contrast, fine film grain, 35mm lens, dreamy vintage atmosphere, daily realistic photography"
        
        **CONTENT TO ADAPT FROM ANALYSIS:**
        - Incorporate the analyzed **Outfit**, **Pose**, **Background**, and **Expression**.
        - Ensure specific details like "hand holding a tomato" or "resting on bed" (from example) are adapted if present in the NEW reference image, otherwise use the actual details from the analyzed image.
        
        **Example of desired style:**
        "<lora:jennie>, Instagirl, visible cleavage, high-angle close-up, the girl (22-23 years old), reclining on beige bed, neutral pastel indoor, long honey-blonde hair tied in a half-up bun, loose face-framing strands, dreamy soft gaze, flushed soft expression, one hand holding a tomato close to lips, other hand resting on bed beside scattered cherry tomatoes, deep red outfit visible on shoulder, realistic skin, creamy warm tone, deep shadows, high contrast, fine film grain, 35mm lens, dreamy vintage atmosphere, daily realistic photography"
        """,
        expected_output="A single, continuous text string containing the comma-separated keywords for the prompt.",
        agent=engineer,
        context=[analyze_task]
    )

    # --- Crew ---
    crew = Crew(
        agents=[analyst, engineer],
        tasks=[analyze_task, generate_prompt_task],
        process=Process.sequential,
        memory=False,
        verbose=True
    )

    result = crew.kickoff()
    final_prompt = str(result)

    print("\n" + "="*50)
    print("✅ FINAL GENERATED PROMPT")
    print("="*50)
    print(final_prompt)
    print("="*50)

    # Trigger generation automatically
    asyncio.run(trigger_image_generation(final_prompt, image_path))


def main():
    parser = argparse.ArgumentParser(description='Generate Instagirl prompts from reference images.')
    parser.add_argument('--image', help='Path to the local reference image file')
    parser.add_argument('--batch-dir', help='Directory containing batch of images to process')
    parser.add_argument('--limit', type=int, default=0, help='Max number of images to process from batch')
    args = parser.parse_args()

    # --- Agents (Created once and reused to maintain any session state if enabled) ---
    analyst = create_visual_analyst_agent()
    engineer = create_prompt_engineer_agent()

    if args.batch_dir:
        print(f"DEBUG: Checking directory: {os.path.abspath(args.batch_dir)}")
        if not os.path.exists(args.batch_dir):
            print(f"Error: Batch directory not found at {args.batch_dir}")
            return
        
        # Get all image files
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
        all_files = [f for f in os.listdir(args.batch_dir) if f.lower().endswith(valid_exts)]
        all_files.sort() # Ensure deterministic order
        
        print(f"DEBUG: Found {len(all_files)} images in directory.")

        if not all_files:
            print(f"No image files found in {args.batch_dir}")
            return

        # Apply limit
        if args.limit > 0:
            files_to_process = all_files[:args.limit]
            print(f"Processing first {args.limit} images from {args.batch_dir}")
        else:
            files_to_process = all_files
            print(f"Processing all {len(all_files)} images from {args.batch_dir}")

        for idx, filename in enumerate(files_to_process, 1):
            print(f"\n\n🔶 Batch Progress: {idx}/{len(files_to_process)}")
            image_path = os.path.join(args.batch_dir, filename)
            process_single_image(image_path, analyst, engineer)

    elif args.image:
        if not os.path.exists(args.image):
            print(f"Error: Image file not found at {args.image}")
            return
        process_single_image(args.image, analyst, engineer)
    
    else:
        print("Error: Must provide either --image or --batch-dir")

if __name__ == "__main__":
    main()
