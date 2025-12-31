import os
from typing import Dict, List, Any
from crewai import Agent, Task, Crew, Process
from src.tools.vision_tool import VisionTool

class VideoStoryboardWorkflow:
    """
    CrewAI Workflow to generate 3 distinct video concept variations
    based on a single starting image.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.concept_ideator = self._create_concept_ideator()
        self.prompt_generator = self._create_prompt_generator()
        # Visual Analyst to understand the starting frame
        self.analyst = self._create_analyst()

    def _create_analyst(self) -> Agent:
        return Agent(
            role='Lead Visual Analyst',
            goal='Analyze reference images to extract objective visual details.',
            backstory="""You are an expert visual director. You analyze images to understand 
            the character, outfit, setting, lighting, and mood. Your analysis serves as the 
            ground truth for the video continuation.""",
            tools=[VisionTool()],
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_concept_ideator(self) -> Agent:
        return Agent(
            role='Video Concept Ideator',
            goal='Create 3 simple, distinct video actions based on a single image.',
            backstory="""You are a creative director for social media content. 
            You specialize in taking a single static image and imagining 3 different simple video versions of it.
            You prioritize subtle, natural movements that fit the mood.
            You strictly avoid complex camera moves or scene changes.
            """,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_prompt_generator(self) -> Agent:
        return Agent(
            role='Video Prompt Generator',
            goal='Create precise image generation prompts for video variations.',
            backstory="""You are an expert in generative AI prompting (Stable Diffusion/Flux).
            Your goal is to translate simple action concepts into detailed visual prompts.
            You must ensure the character and background remain EXACTLY identical to the source image.
            You only describe changes in the upper body pose and facial expression.
            """,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def process(self, image_path: str, persona_name: str = "Jennie") -> Dict[str, Any]:
        """
        Run the workflow.
        
        Args:
            image_path: Path to the source image.
            persona_name: Name of the persona for LORA consistency.
            
        Returns:
            Dict containing the list of variations.
        """
        print(f"\n🎬 Starting Video Variations Workflow for: {image_path} (Persona: {persona_name})")

        # Task 1: Analyze Frame 0
        analyze_task = Task(
            description=f"""
            Analyze the source image at: {image_path}
            
            Describe in detail:
            1. The Character (Hair, Face, Body, Outfit - BE EXACT).
            2. The Setting/Background.
            3. The Lighting and Mood.
            4. The Current Action/Pose.
            
            This analysis will be the visual anchor for all variations.
            """,
            expected_output="Detailed visual description of the source image.",
            agent=self.analyst
        )

        # Task 2: Create Concepts
        concept_task = Task(
            description=f"""
            Based on the analysis of the source image, create 3 DISTINCT simple video concepts.
            
            **Requirements for each concept:**
            1. **Simple Action**: The character performs a simple, natural action (e.g., taking a sip, looking around, smiling, fixing hair, relaxing).
            2. **Upper Body Only**: The action should mostly involve the head, shoulders, and arms.
            3. **Fixed Camera**: The camera angle and distance MUST NOT change.
            4. **No Lighting Changes**: The lighting must remain exactly as in the source.
            5. **No Transitions**: Do not include cuts or scene changes.
            
            Example Concepts for a coffee shop image:
            - Concept 1: "Sip" - Character lifts cup and takes a gentle sip.
            - Concept 2: "Look Around" - Character looks out the window then back at camera.
            - Concept 3: "Relaxed" - Character smiles warmly and adjusts posture slightly.
            """,
            expected_output="A list of 3 distinct video concepts/actions.",
            agent=self.concept_ideator,
            context=[analyze_task]
        )

        # Task 3: Generate Prompts
        prompt_task = Task(
            description=f"""
            Based on the 3 Concepts and the Visual Analysis, generate 3 Image Generation Prompts (one for each concept).
            
            **CRITICAL RULES:**
            1. **Consistency**: You MUST use the EXACT outfit, hair, and appearance details from the Analysis.
            2. **Background Consistency**: You MUST use the EXACT background/setting description from the Analysis. Do NOT change the background.
            3. **Fixed View**: Do NOT include camera movements (like "zoom in", "pan"). Keep "static camera" or "fixed shot".
            4. **Prompt Style**: Instagirl WAN2.2 style (Daily, Casual, Realistic).
            5. **Content**: Describe the character performing the specific action from the Concept.
            
            **Output Format**:
            Provide the output STRICTLY as a Python list of dictionaries:
            [
                {{ "variation": 1, "concept_name": "...", "prompt": "..." }},
                {{ "variation": 2, "concept_name": "...", "prompt": "..." }},
                {{ "variation": 3, "concept_name": "...", "prompt": "..." }}
            ]
            """,
            expected_output="A Python list of 3 dictionaries containing variation index, concept name, and image prompt.",
            agent=self.prompt_generator,
            context=[analyze_task, concept_task]
        )

        crew = Crew(
            agents=[self.analyst, self.concept_ideator, self.prompt_generator],
            tasks=[analyze_task, concept_task, prompt_task],
            process=Process.sequential,
            memory=False,
            verbose=self.verbose
        )

        result = crew.kickoff()
        
        # Parse the result
        raw_output = str(result)
        
        import re
        import json
        import ast

        clean_output = raw_output.strip()
        if clean_output.startswith("```"):
            clean_output = re.sub(r'^```(json|python)?', '', clean_output)
            clean_output = re.sub(r'```$', '', clean_output)
        
        parsed_variations = []
        try:
            # Try JSON first
            parsed_variations = json.loads(clean_output)
        except:
            try:
                # Try AST literal eval
                parsed_variations = ast.literal_eval(clean_output)
            except Exception as e:
                print(f"Error parsing variations output: {e}")
                print(f"Raw output: {raw_output}")
                parsed_variations = [{"variation": i, "concept_name": "Error parsing", "prompt": raw_output} for i in range(1, 4)]

        return {
            "source_image": image_path,
            "persona": persona_name,
            "variations": parsed_variations,
            "concepts_text": str(concept_task.output)
        }
