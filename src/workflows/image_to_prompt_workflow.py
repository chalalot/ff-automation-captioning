import os
import asyncio
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
from crewai import Agent, Task, Crew, Process

load_dotenv()

from src.tools.vision_tool import VisionTool
from utils.constants import DEFAULT_NEGATIVE_PROMPT

class ImageToPromptWorkflow:
    """
    CrewAI Workflow to analyze an image and generate a specific prompt 
    for Instagirl WAN2.2, adapted for daily/casual style.
    """

    HAIRSTYLES = [
        "long honey-blonde hair tied in a half-up bun with loose face-framing strands",
        "thick and very long honey blonde hair with hippie style",
        "thick and very long honey blonde hair with loose waves",
        "long blonde hair messy bun with loose front strands"
    ]

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        # Initialize agents
        self.analyst = self._create_analyst()
        self.engineer = self._create_engineer()

    def _create_analyst(self) -> Agent:
        return Agent(
            role='Lead Visual Analyst',
            goal='Analyze reference images to extract objective visual details for reproduction.',
            backstory="""You are an expert visual director with an eye for detail.
            You can analyze an image and breakdown the:
            - Outfit (colors, textures, cuts)
            - Pose and body language
            - Background and setting details (briefly)
            - Lighting setup (shadows, source)
            
            You focus on OBJECTIVE reality. You do not fluff or over-dramatize.
            """,
            tools=[VisionTool()],
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_engineer(self) -> Agent:
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

    async def process(self, image_path: str, persona_name: str = "Jennie") -> Dict[str, str]:
        """
        Run the workflow for a single image.
        
        Args:
            image_path: Path to local image file.
            persona_name: Name of the persona (e.g. "Jennie").
            
        Returns:
            A dictionary containing the reference image path and the generated prompt.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at {image_path}")

        print(f"\n📸 Starting Workflow for: {image_path} (Persona: {persona_name})")

        # Task 1: Analyze
        analyze_task = Task(
            description=f"""
            Analyze the reference image at: {image_path}
            
            Using the Vision Tool, describe every detail of the poses, the clothes, and the body of the girl in the image.
            
            Specifically describe:
            1. **Body Details**: How the body looks like, shape, features.
            2. **Outfit**: Clothing items, colors, fit, textures.
            3. **Pose/Action**: Hand placement, body angle, specific gestures.
            4. **Background**: Simple description of setting (indoor/outdoor, key elements).
            5. **Lighting**: Direction and mood.
            
            *Keep it objective and detailed.*
            """,
            expected_output="A detailed textual description of the image's visual elements, covering body, outfit, and pose.",
            agent=self.analyst
        )

        # Task 2: Generate Prompt
        generate_prompt_task = Task(
            description=f"""
            Create a final Image Generation Prompt based on the analysis.
             
            **MANDATORY RULES:**
            1. **Prefix**: Start with "<lora:{persona_name.lower()}>, Instagirl," (Adjust trigger word if needed for other personas).
            2. **Subject**: "the girl (22-23 years old), visible cleavage"
            3. **Hairstyle**: CHOOSE EXACTLY ONE from this list (do not modify):
               {self.HAIRSTYLES}
            4. **Length Constraint**: The final output MUST be between 700 and 800 characters long. To achieve this, provide VERY detailed descriptions of the outfit, textures, background, lighting, and atmosphere, while maintaining the comma-separated keyword format.
            
            **STYLE INSTRUCTIONS:**
            - **Vibe**: Daily, casual, authentic. NOT cinematic.
            - **Skin**: Realistic, natural. AVOID "soft pores", "smooth", "glowy".
            - **Detail**: Comprehensive detail on outfit, pose, textures, background, and lighting to meet the length requirement.
            
            **OUTPUT FORMAT**:
            Comma-separated keywords only.
            
            **Example**:
            "<lora:{persona_name.lower()}>, Instagirl, the girl (22-23 years old), [SELECTED_HAIRSTYLE], wearing white t-shirt, blue denim jeans, standing in a cafe, wooden table, coffee cup, natural lighting, realistic skin texture, daily photography, casual vibe..." (ensure length is 700-800 chars)
            """,
            expected_output="A single text string of comma-separated keywords, approximately 700-800 characters in length.",
            agent=self.engineer,
            context=[analyze_task]
        )

        # Run Crew
        crew = Crew(
            agents=[self.analyst, self.engineer],
            tasks=[analyze_task, generate_prompt_task],
            process=Process.sequential,
            memory=False,
            verbose=self.verbose
        )

        result = crew.kickoff()
        final_prompt = str(result)
        
        # Capture the descriptive output from the analysis task
        # Note: Depending on CrewAI version, accessing task output might vary, 
        # but usually task objects are updated in place.
        descriptive_prompt = str(analyze_task.output)

        print(f"\n✅ Generated Prompt:\n{final_prompt}\n")

        return {
            "reference_image": image_path,
            "generated_prompt": final_prompt,
            "descriptive_prompt": descriptive_prompt
        }

# Example usage block (for testing the module directly)
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Path to image")
    parser.add_argument("--persona", default="Jennie", help="Persona name")
    args = parser.parse_args()
    
    workflow = ImageToPromptWorkflow()
    asyncio.run(workflow.process(args.image, args.persona))
