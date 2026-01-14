import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
from crewai import Agent, Task, Crew, Process

load_dotenv()

from src.tools.vision_tool import VisionTool
from utils.constants import DEFAULT_NEGATIVE_PROMPT
from src.workflows.config_manager import WorkflowConfigManager

class ImageToPromptWorkflow:
    """
    CrewAI Workflow to analyze an image and generate a specific prompt 
    for Instagirl WAN2.2, adapted for daily/casual style.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.config_manager = WorkflowConfigManager()

    def _create_analyst(self, template_dir: str) -> Agent:
        # Load backstory from file in specific template directory
        backstory_path = os.path.join(template_dir, 'analyst_agent.txt')
        try:
            with open(backstory_path, 'r', encoding='utf-8') as f:
                backstory_content = f.read()
        except Exception as e:
            # Fallback if file missing
            backstory_content = """You are an expert visual director with an eye for detail.
            You can analyze an image and breakdown the:
            - Outfit (colors, textures, cuts)
            - Pose and body language
            - Camera Angle and Head Direction
            - Background and setting details (briefly)
            - Lighting setup (shadows, source)
            
            You focus on OBJECTIVE reality. You do not fluff or over-dramatize.
            """
            if self.verbose:
                print(f"Warning: Could not load analyst_agent.txt from {backstory_path}, using fallback. Error: {e}")

        return Agent(
            role='Lead Visual Analyst',
            goal='Analyze reference images to extract objective visual details for reproduction.',
            backstory=backstory_content,
            tools=[VisionTool()],
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_engineer(self) -> Agent:
        # Engineer agent for WAN2.2 (Legacy) - potentially not used in Turbo workflow
        return Agent(
            role='Instagirl WAN2.2 Prompt Specialist',
            goal='Convert visual descriptions into strict Instagirl WAN2.2 keyword prompts.',
            backstory="""You are a specialist in prompting for the Instagirl WAN2.2 model.
            
            **YOUR STYLE GUIDE:**
            1. **Daily & Casual**: We are creating daily, casual images. DO NOT make them look "cinematic" or "professional studio".
            2. **Natural Realism**: 
               - AVOID "soft pores", "smooth skin", "glowy", "plastic".
               - Aim for natural skin texture.
            3. **High Detail**: You need to produce prompts around 700-800 characters. Describe the outfit, pose, textures, background, lighting, and atmosphere in great detail using keywords.
            4. **Formatting**:
               - Use comma-separated keywords ONLY.
               - No full sentences.
               - No bullet points.
            """,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_turbo_engineer(self, template_dir: str) -> Agent:
        # Load backstory from file in specific template directory
        backstory_path = os.path.join(template_dir, 'turbo_agent.txt')
        try:
            with open(backstory_path, 'r', encoding='utf-8') as f:
                backstory_content = f.read()
        except Exception as e:
            # Fallback
            backstory_content = """You are an expert visual storyteller and prompt engineer.
            
            **YOUR GOAL:**
            Translate visual analysis into rich, descriptive narrative prompts that follow a strict structure.
            
            **YOUR STYLE GUIDE:**
            1. **Descriptive Flow**: Write in fluid, natural sentences. Avoid broken keyword lists.
            2. **High Density**: Pack as much visual detail as possible into the narrative (textures, lighting, atmosphere).
            3. **Objective Realism**: Focus on physical reality (fabric weight, light direction), avoiding abstract metaphors.
            4. **Formatting**:
               - Use a single, cohesive paragraph.
               - Follow the structure requested in the task exactly.
            """
            if self.verbose:
                print(f"Warning: Could not load turbo_agent.txt from {backstory_path}, using fallback. Error: {e}")

        return Agent(
            role='Visual Narrative Prompt Expert',
            goal='Convert visual analysis into rich, descriptive narrative prompts.',
            backstory=backstory_content,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    async def process(self, image_path: str, persona_name: str = "Jennie", workflow_type: str = "turbo") -> Dict[str, str]:
        """
        Run the workflow for a single image.
        
        Args:
            image_path: Path to local image file.
            persona_name: Name of the persona (e.g. "Jennie").
            workflow_type: Type of workflow ("turbo" or "wan2.2").
            
        Returns:
            A dictionary containing the reference image path and the generated prompt.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at {image_path}")

        print(f"\n📸 Starting Workflow for: {image_path} (Persona: {persona_name}, Workflow: {workflow_type})")

        # Load Persona Config
        persona_config = self.config_manager.get_persona_config(persona_name)
        
        # Determine Persona Type and Template Directory
        persona_type = persona_config.get("type", "instagirl")
        
        # Get project root assuming structure src/workflows/this_file.py
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_base = os.path.join(project_root, 'prompts', 'templates')
        
        template_dir = os.path.join(prompts_base, persona_type)
        
        # Fallback to instagirl if type folder doesn't exist (though it should)
        if not os.path.exists(template_dir):
            if self.verbose:
                print(f"Warning: Template directory for type '{persona_type}' not found at {template_dir}. Falling back to 'instagirl'.")
            template_dir = os.path.join(prompts_base, 'instagirl')

        # Initialize Agents with specific templates
        analyst = self._create_analyst(template_dir)
        turbo_engineer = self._create_turbo_engineer(template_dir)
        engineer = self._create_engineer() # Legacy engineer (WAN2.2)

        # Get Hairstyle Config
        available_hairstyles = persona_config.get("hairstyles", [])
        if not available_hairstyles:
             # Fallback defaults if config is empty
             available_hairstyles = ["long loose hair"] 

        # Task 1: Analyze
        # Load task description from file
        analyst_task_path = os.path.join(template_dir, 'analyst_task.txt')
        try:
            with open(analyst_task_path, 'r', encoding='utf-8') as f:
                analyst_task_template = f.read()
        except Exception as e:
            # Fallback
            analyst_task_template = """
            Analyze the reference image at: {image_path}
            
            Using the Vision Tool, describe every detail of the poses, the clothes, and the body of the girl in the image.
            """
            if self.verbose:
                print(f"Warning: Could not load analyst_task.txt from {analyst_task_path}, using fallback. Error: {e}")
        
        # Format the task description with image path
        # Normalize path for LLM consumption (use forward slashes even on Windows)
        safe_image_path = Path(image_path).resolve().as_posix()
        analyst_task_desc = analyst_task_template.format(image_path=safe_image_path)

        analyze_task = Task(
            description=analyst_task_desc,
            expected_output="A detailed textual description of the image's visual elements, covering body, outfit, pose, and background.",
            agent=analyst
        )

        # Task 2: Generate Prompt
        generate_prompt_task = None
        
        if workflow_type.lower() == "turbo":
            # Determine hair color for Turbo
            hair_color = persona_config.get("hair_color", "Honey-blonde")
            
            # Determine hairstyle options
            header = "  - You MUST choose ONE from this list explicitly (Do not invent others):"
            
            hairstyle_list = "\n".join([f"  - {style}" for style in available_hairstyles])
            hairstyle_options = f"{header}\n{hairstyle_list}"

            # Load template from file
            template_path = os.path.join(template_dir, 'turbo_prompt_template.txt')
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    turbo_template = f.read()
            except Exception as e:
                raise FileNotFoundError(f"Could not load Turbo template from {template_path}: {e}")

            # Safe formatting to ignore keys not present in the template if necessary, 
            # but usually we expect the template to have these placeholders.
            # Using standard format.
            try:
                prompt_instruction = turbo_template.format(hair_color=hair_color, hairstyle_options=hairstyle_options)
            except KeyError as e:
                 # In case the template doesn't have the keys (e.g. user edited them out), try formatting gracefully or just pass as is?
                 # Better to assume they are there or just replace if they exist.
                 # Let's try simple string replacement if format fails, or just fail loud to let user know template is broken.
                 # For now, let's assume valid template.
                 prompt_instruction = turbo_template.format(hair_color=hair_color, hairstyle_options=hairstyle_options)
            
            generate_prompt_task = Task(
                description=prompt_instruction,
                expected_output="A detailed paragraph describing the image as detailed as possible",
                agent=turbo_engineer,
                context=[analyze_task]
            )
        else:
            # WAN2.2 (Legacy/Default) Logic - using hardcoded strings mostly, but updated with config data
            
            hairstyle_instruction = f"""
               - PRIORITY: Use the hairstyle exactly as described in the reference image analysis if it is clear and distinct.
               - FALLBACK: If the reference hair is unclear, choose ONE from this list:
               {available_hairstyles}
            """

            generate_prompt_task = Task(
                description=f"""
                Create a final Image Generation Prompt based on the analysis.
                 
                **MANDATORY RULES:**
                1. **Prefix**: Start with "<lora:{persona_name.lower()}>, Instagirl," (Adjust trigger word if needed for other personas).
                2. **Subject**: "the girl (22-23 years old)"
                3. **Hairstyle**: 
                   {hairstyle_instruction}
                4. **Camera & Orientation**: You MUST include the specific **Camera Angle** and **Head Direction** keywords from the analysis.
                5. **Outfit**: You MUST include specific keywords describing the outfit from the analysis.
                6. **Background**: You MUST include specific keywords describing the background and setting.
                7. **Length Constraint**: The final output MUST be between 700 and 800 characters long.
                
                **OUTPUT FORMAT**:
                Comma-separated keywords only.
                """,
                expected_output="A single text string of comma-separated keywords, approximately 700-800 characters in length.",
                agent=engineer,
                context=[analyze_task]
            )

        # Run Crew
        crew = Crew(
            agents=[analyst, turbo_engineer if workflow_type.lower() == "turbo" else engineer],
            tasks=[analyze_task, generate_prompt_task],
            process=Process.sequential,
            memory=False,
            verbose=self.verbose
        )

        result = crew.kickoff()
        final_prompt = str(result)
        
        # Capture the descriptive output
        descriptive_prompt = str(analyze_task.output)

        print(f"\n✅ Generated Prompt:\n{final_prompt}\n")

        return {
            "reference_image": image_path,
            "generated_prompt": final_prompt,
            "descriptive_prompt": descriptive_prompt
        }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Path to image")
    parser.add_argument("--persona", default="Jennie", help="Persona name")
    args = parser.parse_args()
    
    workflow = ImageToPromptWorkflow()
    asyncio.run(workflow.process(args.image, args.persona))
