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
        # Load backstory
        # Get project root assuming structure src/workflows/this_file.py
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, 'prompts', 'workflows')
        
        backstory_path = os.path.join(prompts_dir, 'video_analyst_agent.txt')
        try:
             with open(backstory_path, 'r', encoding='utf-8') as f:
                 backstory_content = f.read()
        except:
             backstory_content = "You are an expert visual director..." # Fallback

        return Agent(
            role='Lead Visual Analyst',
            goal='Analyze reference images to extract objective visual details.',
            backstory=backstory_content,
            tools=[VisionTool()],
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_concept_ideator(self) -> Agent:
        # Load backstory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, 'prompts', 'workflows')
        
        backstory_path = os.path.join(prompts_dir, 'video_concept_agent.txt')
        try:
             with open(backstory_path, 'r', encoding='utf-8') as f:
                 backstory_content = f.read()
        except:
             backstory_content = "You are a creative director for social media content..." # Fallback

        return Agent(
            role='Video Concept Ideator',
            goal='Create 3 simple, distinct video actions based on a single image.',
            backstory=backstory_content,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_prompt_generator(self) -> Agent:
        # Load backstory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, 'prompts', 'workflows')

        backstory_path = os.path.join(prompts_dir, 'video_prompt_agent.txt')
        try:
             with open(backstory_path, 'r', encoding='utf-8') as f:
                 backstory_content = f.read()
        except:
             backstory_content = "You are an expert in generative AI prompting..." # Fallback

        return Agent(
            role='Video Prompt Generator',
            goal='Create precise image generation prompts for video variations.',
            backstory=backstory_content,
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
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, 'prompts', 'workflows')
        
        analyst_task_path = os.path.join(prompts_dir, 'video_analyst_task.txt')
        try:
             with open(analyst_task_path, 'r', encoding='utf-8') as f:
                 analyst_task_template = f.read()
        except:
             analyst_task_template = "Analyze the source image at: {image_path}..." # Fallback

        analyst_task_desc = analyst_task_template.format(image_path=image_path)

        analyze_task = Task(
            description=analyst_task_desc,
            expected_output="Detailed visual description of the source image.",
            agent=self.analyst
        )

        # Task 2: Create Concepts
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, 'prompts', 'workflows')

        concept_task_path = os.path.join(prompts_dir, 'video_concept_task.txt')
        try:
             with open(concept_task_path, 'r', encoding='utf-8') as f:
                 concept_task_desc = f.read()
        except:
             concept_task_desc = "Based on the analysis of the source image, create 3 DISTINCT simple video concepts..." # Fallback

        concept_task = Task(
            description=concept_task_desc,
            expected_output="A list of 3 distinct video concepts/actions.",
            agent=self.concept_ideator,
            context=[analyze_task]
        )

        # Task 3: Generate Prompts
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, 'prompts', 'workflows')

        prompt_task_path = os.path.join(prompts_dir, 'video_prompt_task.txt')
        try:
             with open(prompt_task_path, 'r', encoding='utf-8') as f:
                 prompt_task_desc = f.read()
        except:
             prompt_task_desc = "Based on the 3 Concepts and the Visual Analysis..." # Fallback

        prompt_task = Task(
            description=prompt_task_desc,
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
