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

    TURBO_PROMPT_TEMPLATE = """
Here is the systematic translation of your prompt framework and feedback summary.

---

## I. THE 11-POINT PROMPT FRAMEWORK
You must structure your analysis and final prompt generation following this exact logical flow:

[1] Technical anchor (LoRA / identity)
[2] Subject + age + context
[3] Camera framing & angle
[4] Body orientation & posture
[5] Primary gesture / action
[6] Expression & emotional state
[7] Outfit & fabric realism
[8] Hair & grooming realism
[9] Props / foreground objects
[10] Background & environment realism (anti-DOF)
[11] Lighting, color, capture feel

---

## II. DETAILED CONSTRAINTS & REQUIREMENTS

### 1. Subject & Identity (Strict)
- **Age**: You MUST describe the subject as **"a girl 22-23 years old"** (FIXED).
- **Identity**: DO NOT describe face features, skin tone, or specific personal identity.
- **Body**: Maintain body axis, S-curve, and hand placement. Emphasize small waist, deep waist curve, rounded hips, and straight/slender legs. Natural proportions only.

### 2. Hair & Styling
- **Color**: **{hair_color}** (MANDATORY).
- **Hairstyle**: Select ONE from this list:
{hairstyle_options}
- **Description**: Describe flow, texture, and state (neat vs natural) in detail.

### 3. Outfit & Fabric
- **Specificity**: Use exact garment types (e.g., "jeans" not "pants").
- **Realism**: Describe fabric texture (e.g., "soft cotton," "knit," "modern denim").
- **Fit**: Avoid unintended tightness or "fitted" descriptors unless evident.

### 4. Background & Environment
- **Constraint**: You MUST include the phrase: **"the background is rendered with ultra realistic detail"**.
- **Realism**: Avoid Depth of Field (DOF). The background should be "lived-in," showing texture, wear, and imperfections (e.g., "scuffs," "irregularities").

### 5. Lighting & Atmosphere
- **Vibe**: Daily realistic photography.
- **Quality**: Soft, uneven, textured lighting. Avoid "cinematic" or "studio" perfection.

---

## III. OUTPUT FORMAT
- **Structure**: A single, comprehensive paragraph following the 11-point framework.
- **Length**: As detailed as possible. No limit.
- **Style**: Descriptive, narrative, and "thick" with visual adjectives.

---

## IV. EXAMPLE OUTPUT
(Follow this level of detail and structure)

a young beautiful girl around 22–23 years old, sitting at a café table and captured in a medium shot from head to upper torso at eye-level. The camera is straight and stable, with no tilt or dramatic angle. Her body faces the camera almost directly, shoulders relaxed and posture upright, weight evenly balanced while seated.

She raises one hand holding a metal spoon, gently covering one eye in a playful and casual gesture. Her elbow is bent naturally, wrist relaxed. Her other arm rests comfortably out of frame. The pose feels spontaneous and unforced, expressing a light, cozy café moment rather than a posed shot. Her upper body appears slim and well-proportioned, with soft shoulders, visible collarbones, a narrow waistline, and a naturally full but relaxed chest without tension.

She wears a thin beige spaghetti-strap top made from soft cotton or knit fabric. Over it, she loosely drapes a light oatmeal-colored knitted cardigan, slipping off both shoulders slightly. The cardigan texture is clearly visible, not smooth or perfect, enhancing a warm and casual feel.

Her hair is styled in a loose messy updo with gentle volume at the crown. Several soft strands fall naturally around the face and neck. Hair color is blonde or honey-blonde, realistic and natural, without artificial shine or heavy styling.

Her expression is calm and content. Eyes are gently closed, lips forming a subtle, relaxed smile, conveying enjoyment and ease. She is not actively posing for the camera, but immersed in the moment.

In front of her on the table is a wooden tray holding a casual meal: a bowl of white rice, a fried egg, a small dish of meat and vegetables, and another small side dish. Two drinks sit nearby — one red-toned fruit drink and one green-toned beverage — placed naturally without careful styling.

The background is rendered with ultra realistic detail, showing a modern café interior that feels genuinely lived-in rather than styled. Light grey concrete walls display subtle surface irregularities and natural texture variation. Exposed ceiling elements and visible pipes show slight wear and tonal inconsistency instead of uniform finishes. Round hanging lights emit soft, uneven illumination typical of real indoor fixtures. Indoor plants in simple pots show natural variation in leaf shape and color, and the wooden furniture reveals fine grain patterns, minor scuffs, and everyday signs of use. The space feels authentic and naturally imperfect, with realistic spatial depth and environmental presence, avoiding any studio-like cleanliness or artificial refinement.

Lighting is soft and natural, coming primarily from a large window to the side, blended with gentle indoor ambient lighting. White balance is neutral with a slight warm tone. Colors are muted and harmonious, with beige, cream, grey, and soft green dominating. The image feels like a slightly imperfect, everyday snapshot taken with a high-end smartphone, realistic, cozy, and authentic, without cinematic effects or depth-of-field blur.
"""

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

            prompt_instruction = self.TURBO_PROMPT_TEMPLATE.format(hair_color=hair_color, hairstyle_options=hairstyle_options)
            
            generate_prompt_task = Task(
                description=prompt_instruction,
                expected_output="A detailed paragraph describing the image as detailed as possible",
                agent=self.engineer,
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
