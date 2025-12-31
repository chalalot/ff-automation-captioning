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

    PERSONA_HAIRSTYLES = {
        "Jennie": [
            "long honey-blonde hair tied in a half-up bun with loose face-framing strands",
            "thick and very long honey blonde hair with hippie style",
            "thick and very long honey blonde hair with loose waves",
            "long blonde hair messy bun with loose front strands"
        ],
        "Sephera": [
            "dark brown long hair with loose waves",
            "long dark brown hair, wet and sunlit, sticking gently to skin",
            "long dark brown hair",
            "long dark brown hair, slightly damp, sunlit reflections",
            "long dark straight hair, slightly wet and sun-lit, strands clinging softly to her shoulder"
        ],
        "Mika": [
            "Korean see-through bangs over forehead, effortless chic messy bun hairstyle",
            "long black hair styled in an elegant updo, parted slightly off-center, some loose strands framing face, smooth and neat with natural shine"
        ],
        "Nya": [
            "long curly chestnut hair reaching her chest",
            "long dark brown hair, styled in loose curls, parted at center, voluminous waves framing face"
        ],
        "Emi": [
            "short platinum blonde bob with messy layered waves, volumized hair, layered hairstyle, dynamic hair flow, hair shine enhancement, side part hairstyle, deep side part, one side tucked behind ear, asymmetrical hairstyle"
        ],
        "Roxie": [
            "thick and strong, long wavy pastel pink hair parted at the center, styled with two space buns on top of the head, and soft straight bangs covering the forehead",
            "long straight pastel hair cascading down the back, glossy texture reflecting key light.",
            "long straight platinum white hair cascading down back, glossy texture reflecting light."
        ]
    }

    PERSONA_HAIR_COLORS = {
        "Jennie": "Honey-blonde",
        "Sephera": "Dark brown",
        "Mika": "Black",
        "Nya": "Chestnut",
        "Emi": "Platinum blonde",
        "Roxie": "Pastel pink"
    }

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        # Initialize agents
        self.analyst = self._create_analyst()
        self.engineer = self._create_engineer()
        self.turbo_engineer = self._create_turbo_engineer()

    def _create_analyst(self) -> Agent:
        return Agent(
            role='Lead Visual Analyst',
            goal='Analyze reference images to extract objective visual details for reproduction.',
            backstory="""You are an expert visual director with an eye for detail.
            You can analyze an image and breakdown the:
            - Outfit (colors, textures, cuts)
            - Pose and body language
            - Camera Angle and Head Direction
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

    def _create_turbo_engineer(self) -> Agent:
        return Agent(
            role='Visual Narrative Prompt Expert',
            goal='Convert visual analysis into rich, descriptive narrative prompts.',
            backstory="""You are an expert visual storyteller and prompt engineer.
            
            **YOUR GOAL:**
            Translate visual analysis into rich, descriptive narrative prompts that follow a strict structure.
            
            **YOUR STYLE GUIDE:**
            1. **Descriptive Flow**: Write in fluid, natural sentences. Avoid broken keyword lists.
            2. **High Density**: Pack as much visual detail as possible into the narrative (textures, lighting, atmosphere).
            3. **Objective Realism**: Focus on physical reality (fabric weight, light direction), avoiding abstract metaphors.
            4. **Formatting**:
               - Use a single, cohesive paragraph.
               - Follow the structure requested in the task exactly.
            """,
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

        # Determine hairstyles based on persona
        persona_key = next((k for k in self.PERSONA_HAIRSTYLES.keys() if k.lower() == persona_name.lower()), "Jennie")
        available_hairstyles = self.PERSONA_HAIRSTYLES[persona_key]
        
        # Task 1: Analyze
        analyze_task = Task(
            description=f"""
            Analyze the reference image at: {image_path}
            
            Using the Vision Tool, describe every detail of the poses, the clothes, and the body of the girl in the image.
            
            Specifically describe:
            1. **Body Details**: How the body looks like, shape, features.
            2. **Outfit**: Clothing items, colors, fit, textures.
            3. **Pose/Action**: Hand placement, body angle, specific gestures.
            4. **Camera Angle**: (e.g. High angle, low angle, eye level, dutch angle, close-up, full shot, etc.) - BE EXACT.
            5. **Head Direction**: (e.g. Facing forward, looking left, profile view, looking back over shoulder, etc.) - BE EXACT.
            6. **Background**: Detailed description of setting (indoor/outdoor, specific objects, colors, key elements).
            7. **Lighting**: Direction and mood.
            
            *Keep it objective and detailed.*
            """,
            expected_output="A detailed textual description of the image's visual elements, covering body, outfit, pose, and background.",
            agent=self.analyst
        )

        # Task 2: Generate Prompt
        if workflow_type.lower() == "turbo":
            # Determine hair color for Turbo
            hair_color = self.PERSONA_HAIR_COLORS.get(persona_key, "Honey-blonde")
            
            # Determine hairstyle options
            header = "  - You MUST choose ONE from this list explicitly (Do not invent others):"
            
            hairstyle_list = "\n".join([f"  - {style}" for style in available_hairstyles])
            hairstyle_options = f"{header}\n{hairstyle_list}"

            # Load template from file
            template_path = os.path.join(os.path.dirname(__file__), 'turbo_prompt_template.txt')
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    turbo_template = f.read()
            except Exception as e:
                raise FileNotFoundError(f"Could not load Turbo template from {template_path}: {e}")

            prompt_instruction = turbo_template.format(hair_color=hair_color, hairstyle_options=hairstyle_options)
            
            generate_prompt_task = Task(
                description=prompt_instruction,
                expected_output="A detailed paragraph describing the image as detailed as possible",
                agent=self.turbo_engineer,
                context=[analyze_task]
            )
        else:
            # WAN2.2 (Legacy/Default) Logic
            
            # Determine hairstyle instruction
            if persona_name.lower() == "sephera":
                 hairstyle_instruction = f"""
                   - You MUST choose ONE from this list explicitly (Do not invent others):
                   {available_hairstyles}
                 """
            else:
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
                4. **Camera & Orientation**: You MUST include the specific **Camera Angle** and **Head Direction** keywords from the analysis (e.g., "low angle", "looking back", "profile view").
                5. **Outfit**: You MUST include specific keywords describing the outfit from the analysis (colors, textures, fit, specific items).
                6. **Background**: You MUST include specific keywords describing the background and setting from the analysis (location, props, lighting).
                7. **Length Constraint**: The final output MUST be between 700 and 800 characters long. To achieve this, provide VERY detailed descriptions of the outfit, textures, background, lighting, and atmosphere, while maintaining the comma-separated keyword format.
                
                **STYLE INSTRUCTIONS:**
                - **Vibe**: Daily, casual, authentic. NOT cinematic.
                - **Skin**: Realistic, natural. AVOID "soft pores", "smooth", "glowy".
                - **Detail**: Comprehensive detail on outfit, pose, textures, background, and lighting to meet the length requirement.
                
                **OUTPUT FORMAT**:
                Comma-separated keywords only.
                
                **Example**:
                "<lora:{persona_name.lower()}>, Instagirl, low angle shot, looking back over shoulder, the girl (22-23 years old), [HAIRSTYLE_FROM_IMAGE], wearing white t-shirt, blue denim jeans, standing in a cafe, wooden table, coffee cup, natural lighting, realistic skin texture, daily photography, casual vibe..." (ensure length is 700-800 chars)
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
