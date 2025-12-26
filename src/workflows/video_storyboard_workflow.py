import os
from typing import Dict, List, Any
from crewai import Agent, Task, Crew, Process
from src.tools.vision_tool import VisionTool

class VideoStoryboardWorkflow:
    """
    CrewAI Workflow to generate a 30-second video script and keyframe prompts
    based on a single starting image.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.script_writer = self._create_script_writer()
        self.storyboard_artist = self._create_storyboard_artist()
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

    def _create_script_writer(self) -> Agent:
        return Agent(
            role='Short-Form Video Script Writer',
            goal='Create engaging 30-second video scripts (Reels/TikTok style).',
            backstory="""You are a creative director for social media content. 
            You specialize in taking a single image and expanding it into a 30-second narrative.
            You understand pacing, mood, and visual storytelling.
            The video is divided into 6 segments of 5 seconds each.
            You prioritize atmospheric consistency over complex plots.
            """,
            verbose=self.verbose,
            allow_delegation=False,
            memory=False,
            llm="gpt-4o"
        )

    def _create_storyboard_artist(self) -> Agent:
        return Agent(
            role='AI Storyboard Artist & Prompt Engineer',
            goal='Create consistent visual prompts for video keyframes.',
            backstory="""You are an expert in generative AI prompting (Stable Diffusion/Flux).
            Your goal is to visualize the script segments into specific keyframes.
            Frame 0 is the provided source image.
            You must generate prompts for Frame 1, Frame 2, Frame 3, Frame 4, Frame 5, and Frame 6.
            Each frame must strictly adhere to the character's appearance (outfit, hair, face) from Frame 0.
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
            image_path: Path to the source image (Frame 0).
            persona_name: Name of the persona for LORA consistency.
            
        Returns:
            Dict containing the script and list of prompts.
        """
        print(f"\n🎬 Starting Video Storyboard Workflow for: {image_path} (Persona: {persona_name})")

        # Task 1: Analyze Frame 0
        analyze_task = Task(
            description=f"""
            Analyze the source image (Frame 0) at: {image_path}
            
            Describe in detail:
            1. The Character (Hair, Face, Body, Outfit - BE EXACT).
            2. The Setting/Background.
            3. The Lighting and Mood.
            4. The Current Action/Pose.
            
            This analysis will be the visual anchor for the entire video.
            """,
            expected_output="Detailed visual description of Frame 0.",
            agent=self.analyst
        )

        # Task 2: Create Script
        script_task = Task(
            description=f"""
            Based on the analysis of Frame 0, create a 30-second video script divided into 6 segments (5 seconds each).
            
            Structure:
            - **Segment 1** (0s-5s): Starts at Frame 0. Action evolves to Frame 1.
            - **Segment 2** (5s-10s): Starts at Frame 1. Action evolves to Frame 2.
            - **Segment 3** (10s-15s): Starts at Frame 2. Action evolves to Frame 3.
            - **Segment 4** (15s-20s): Starts at Frame 3. Action evolves to Frame 4.
            - **Segment 5** (20s-25s): Starts at Frame 4. Action evolves to Frame 5.
            - **Segment 6** (25s-30s): Starts at Frame 5. Action evolves to Frame 6 (End).
            
            **Narrative Goal**: Create a coherent, engaging micro-story or mood piece suitable for TikTok/Reels.
            
            **CRITICAL CONSTRAINTS (MUST FOLLOW):**
            1. **Single Activity**: Focus on ONE main activity (e.g., sitting and drinking coffee, walking, or just standing). Do NOT switch between different activities.
            2. **Minimal Action**: The character should primarily be looking around, smiling, shifting weight, or interacting gently with the immediate environment. NO complex acting.
            3. **Static Background**: The setting MUST remain EXACTLY the same throughout. Do NOT change locations or angles significantly.
            """,
            expected_output="A structured script with 6 segments, describing the action and atmosphere for each.",
            agent=self.script_writer,
            context=[analyze_task]
        )

        # Task 3: Generate Keyframe Prompts
        prompt_task = Task(
            description=f"""
            Based on the Script and the Visual Analysis of Frame 0, generate the Image Generation Prompts for **Frame 1, Frame 2, Frame 3, Frame 4, Frame 5, and Frame 6**.
            
            **CRITICAL RULES:**
            1. **Consistency**: You MUST use the EXACT outfit, hair, and appearance details from Frame 0 Analysis. The character cannot change clothes.
            2. **Background Consistency**: You MUST use the EXACT background/setting description from Frame 0 Analysis for ALL frames. Do NOT change the background. Only describe changes in the character's pose, gaze, or slight movement.
            3. **Format**: Return a JSON-like list of 6 strings.
            4. **Prompt Style**: Instagirl WAN2.2 style (Daily, Casual, Realistic).
            5. **Prefix**: Start every prompt with "<lora:{persona_name.lower()}>, Instagirl,".
            6. **Detail**: Each prompt should be 500-700 characters, describing the specific moment at the END of the corresponding segment.
            
            **Output Format**:
            Provide the output STRICTLY as a Python list of dictionaries:
            [
                {{ "frame": 1, "script_segment": "...", "prompt": "..." }},
                {{ "frame": 2, "script_segment": "...", "prompt": "..." }},
                ...
                {{ "frame": 6, "script_segment": "...", "prompt": "..." }}
            ]
            """,
            expected_output="A Python list of 6 dictionaries containing frame index, script segment, and image prompt.",
            agent=self.storyboard_artist,
            context=[analyze_task, script_task]
        )

        crew = Crew(
            agents=[self.analyst, self.script_writer, self.storyboard_artist],
            tasks=[analyze_task, script_task, prompt_task],
            process=Process.sequential,
            memory=False,
            verbose=self.verbose
        )

        result = crew.kickoff()
        
        # Parse the result (Task 3 output)
        # We expect a list of dicts. Since CrewAI returns string, we might need to eval or json load.
        # However, for robustness, we'll try to extract it safely or assume the agent follows instructions well.
        
        raw_output = str(result)
        
        # Simple cleaning to help parsing if it's wrapped in markdown code blocks
        import re
        import json
        import ast

        clean_output = raw_output.strip()
        if clean_output.startswith("```"):
            clean_output = re.sub(r'^```(json|python)?', '', clean_output)
            clean_output = re.sub(r'```$', '', clean_output)
        
        parsed_frames = []
        try:
            # Try JSON first
            parsed_frames = json.loads(clean_output)
        except:
            try:
                # Try AST literal eval (for Python list format)
                parsed_frames = ast.literal_eval(clean_output)
            except Exception as e:
                print(f"Error parsing storyboard output: {e}")
                print(f"Raw output: {raw_output}")
                # Fallback: Return raw text wrapped in a dummy structure
                parsed_frames = [{"frame": i, "script_segment": "Error parsing", "prompt": raw_output} for i in range(1, 7)]

        return {
            "source_image": image_path,
            "persona": persona_name,
            "frames": parsed_frames,
            "full_script": str(script_task.output)
        }
