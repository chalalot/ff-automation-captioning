#!/usr/bin/env python3
"""
CrewAI Mood Variations Workflow

This workflow generates a cohesive set of 5 images (variations) based on a SINGLE Mood.
It fetches ALL context (Activity, Outfit, Setting) directly from the 'persona_moods' database table.
User input is minimal: just the Persona ID and Mood Number.

It ensures:
1. Consistent Outfit (derived from Mood).
2. Consistent Setting (derived from Mood).
3. Consistent Activity (derived from Mood).
4. 5 Distinct Camera Angles/Poses (Wide, Medium, Close-up, etc.).

Usage:
  python scripts/crewai_mood_variations.py \
    --persona-id 1 \
    --mood-number 1

Requires OPENAI_API_KEY in environment.
"""

from __future__ import annotations
import re
import argparse
import hashlib
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import traceback
import random

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from crewai import Agent, Task, Crew, Process
from crewai.memory import ShortTermMemory, LongTermMemory

# Import DB Models
try:
    from src.personas.db_models import StructuredPersonaDatabase, StructuredMood
    from src.personas.validation_models import StrictMoodValidator
    from utils.constants import DEFAULT_NEGATIVE_PROMPT
except ImportError:
    # Fallback for standalone testing (should not happen in prod)
    DEFAULT_NEGATIVE_PROMPT = "low quality, ugly, deformed, anime, cartoon"
    print("⚠️  Warning: Local modules not found. Ensure you are running from the project root.")

# Place holder for customized keywords
CUSTOM_KEYWORDS = "sexy breast with cleavage, squeezed breasts, thin and willwy arms"

# ---------- Structured Output Models ----------

class MasterScene(BaseModel):
    activity_concept: str = Field(..., description="The specific activity/action derived from the Mood Description.")
    outfit_description: str = Field(..., description="The EXACT definition of the outfit (must be plain/structural). Used for consistency.")
    setting_description: str = Field(..., description="The EXACT definition of the background/setting. Used for consistency.")
    lighting_style: str = Field(..., description="The lighting setup to be used across all shots.")
    mood_keywords: List[str] = Field(default_factory=list, description="Core keywords from the mood database")

class ShotVariation(BaseModel):
    shot_number: int = Field(..., description="1 to 5")
    shot_type: str = Field(..., description="e.g., Wide Shot, Close-up, Side Profile")
    pose_description: str = Field(..., description="Specific pose for this angle")
    expression_description: str = Field(..., description="Facial expression")
    framing_keywords: str = Field(..., description="Technical camera keywords for this shot")
    visual_description: str = Field(..., description="Full visual description combining Master Scene + This Variation")

class CaptionContent(BaseModel):
    caption: str = Field(..., description="Instagram caption under 500 characters")
    hashtags: List[str] = Field(default_factory=list, description="6-12 relevant hashtags")
    cta: str = Field(..., description="Call to action")

class ImagePrompt(BaseModel):
    positive_prompt: str = Field(..., description="Final comma-separated keywords")
    technical_specs: str = Field(..., description="Technical specs")

class PostPackage(BaseModel):
    master_scene: MasterScene
    variations: List[ShotVariation]
    captions: List[CaptionContent]
    image_prompts: List[ImagePrompt]

# ---------- CrewAI Agent Definitions ----------

def create_visual_director_agent(persona_name: str = "Jennie") -> Agent:
    """The continuity expert who defines the Master Scene."""
    return Agent(
        role='Visual Continuity Director',
        goal=f"""Define a SINGLE, cohesive Master Scene for {persona_name} derived PURELY from the database mood.
        1. Deduce the Activity from the Mood Description & Props.
        2. Define ONE outfit based on the 'Clothes' keywords.
        3. Define ONE setting based on the 'Setting' keywords.""",
        backstory=f"""You are a high-end editorial director. 
        You analyze mood boards (database entries) and turn them into concrete production sets.
        You ensure that the activity, outfit, and setting are perfectly aligned with the provided mood data.""",
        verbose=True,
        allow_delegation=False,
    )

def create_photographer_agent(persona_name: str = "Jennie") -> Agent:
    """The photographer who creates variations."""
    return Agent(
        role='Editorial Photographer',
        goal=f"""Plan 5 distinct camera angles for the defined Master Scene.
        Focus on SUBTLE but MEANINGFUL variations in:
        - Gaze (looking at camera vs. looking away)
        - Head tilt and facial angles
        - Hand placement and interaction with props
        - Camera distance (Close vs Far)
        Keep the mood 80% consistent but make each shot feel like a unique moment.""",
        backstory=f"""You are a photographer shooting a lookbook for {persona_name}.
        You are given a set (location) and a look (outfit).
        Your job is to move around the subject and capture 5 different perspectives.
        You use technical camera terminology.""",
        verbose=True,
        allow_delegation=False
    )

def create_captioner_agent(persona_name: str = "Jennie") -> Agent:
    return Agent(
        role='Authentic Voice Caption Writer',
        goal=f"""Write natural captions for {persona_name}. 
        Since these are variations of the same moment, the captions should feel like a 'photo dump' or related thoughts.""",
        backstory=f"""You write authentic captions for {persona_name}. You sound like a real person, not an ad.""",
        verbose=True
    )

def create_image_prompter_agent(persona_name: str = "Jennie") -> Agent:
    return Agent(
        role='Technical Keyword Prompt Specialist',
        goal=f"""Create strict keyword-only image prompts.
        CRITICAL: 
        - You MUST convert all narrative descriptions (e.g., "She is wearing a red dress") into comma-separated keywords (e.g., "red dress").
        - NEVER output full sentences.
        - NEVER use linking verbs (is, are, has).
        - NEVER use articles (a, an, the).""",
        backstory=f"""You are a prompt engineer specializing in Stable Diffusion. 
        You know that the AI gets confused by sentences. 
        You ruthlessly strip away grammar to leave only visual tokens. 
        "She is holding a cup" -> "holding cup". 
        "The background is a wall" -> "background wall".""",
        verbose=True
    )

# ---------- CrewAI Task Definitions ----------

def create_master_scene_task(
    mood_obj: StructuredMood,
    persona_name: str
) -> Task:
    """Task to define the static elements (Outfit, Setting, Activity) PURELY from Mood."""
    
    # Extract keywords explicitly from the StructuredMood object
    mood_context = f"""
    ASSIGNED MOOD: {mood_obj.mood_name} (ID: {mood_obj.mood_number})
    MOOD DESCRIPTION: {mood_obj.mood_description}
    
    DATABASE KEYWORDS (You MUST use these):
    - Pose: {', '.join(mood_obj.pose_keywords)}
    - Lighting: {', '.join(mood_obj.lighting_keywords)}
    - Clothes: {', '.join(mood_obj.clothes_keywords)}
    - Props/Setting: {', '.join(mood_obj.props_setting_keywords)}
    """

    return Task(
        description=f"""
        Define the MASTER SCENE for a 5-photo series based ONLY on the provided Mood Data.
        
        INPUT DATA:
        {mood_context}

        REQUIREMENTS:
        1. **Activity**: Read the 'MOOD DESCRIPTION' and 'Props/Setting' carefully. Deduce the most logical activity.
           - Example: If props are "coffee, book, window", the activity is "Reading coffee by the window".
           - Example: If props are "yoga mat, water bottle", the activity is "Doing Yoga".
        2. **Outfit (STRICT)**: 
           - Must align with 'Clothes' keywords above.
           - PLAIN, Solid Colors. No prints/patterns.
           - Focus on Cut and Structure.
        3. **Setting (STRICT)**:
           - Must align with 'Props/Setting' keywords above.
           - Define the specific furniture, lighting, and background elements.
           - Must be simple and not cluttered.

        OUTPUT FORMAT:
        Return a structured description defining:
        - Activity Concept
        - Exact Outfit Description
        - Exact Setting Description
        - Lighting Style
        """,
        expected_output="A detailed definition of the Outfit, Setting, and Activity derived from the Mood.",
        agent=create_visual_director_agent(persona_name)
    )

def create_variation_task(
    master_scene_raw: str,
    persona_name: str
) -> Task:
    """Task to generate 5 specific shots based on the Master Scene."""
    return Task(
        description=f"""
        Based on this MASTER SCENE, plan 5 distinct camera shots.
        
        MASTER SCENE:
        {master_scene_raw}
        
        REQUIREMENTS:
        Generate 5 variations following this structure. Ensure **DISTINCT** differences in angle and expression:
        1. **Establishing Shot**: Wide/Full body. Context focus. Looking AT camera.
        2. **Candid Activity**: Medium shot. Engaging with the activity (e.g., reading/drinking). Eyes DOWN or AWAY.
        3. **Detail/Emotion**: Close-up on face/shoulder. Soft expression. Looking SIDEWAYS or closed eyes.
        4. **Dynamic Angle**: Low angle or High angle (selfie style or artistic). Different hand placement.
        5. **Atmospheric**: Silhouette or profile view. Focus on lighting and mood. 
        
        CONSTRAINT:
        - KEEP OUTFIT AND SETTING EXACTLY THE SAME.
        - VARY the Gaze (Camera, Away, Down, Closed).
        - VARY the Smile (Soft smile, Laughing, Serious, Pout).
        
        OUTPUT FORMAT:
        Provide a numbered list (1-5) where each item describes:
        - Shot Type
        - Specific Pose
        - Expression & Gaze
        - Visual Description (combining scene + shot)
        """,
        expected_output="A list of 5 distinct shot plans, maintaining consistency of the master scene.",
        agent=create_photographer_agent(persona_name)
    )

def create_prompt_task(
    shot_description: str,
    master_scene_raw: str,
    shot_number: int,
    persona_name: str,
    mood_obj: StructuredMood
) -> Task:
    """Task to generate the prompt for a specific shot."""
    
    # Extract technical keywords from mood object - CLEAN LISTS ONLY
    technical_keywords = f"""
    LIGHTING KEYWORDS: {', '.join(mood_obj.lighting_keywords)}
    QUALITY KEYWORDS: {', '.join(mood_obj.camera_quality_keywords)}
    EXPRESSION KEYWORDS: {', '.join(mood_obj.expression_keywords)}
    HAIR KEYWORDS: {', '.join(mood_obj.hair_keywords)}
    """

    return Task(
        description=f"""
        Create the Stable Diffusion prompt for Shot #{shot_number}.
        
        SHOT DESCRIPTION: {shot_description}
        MASTER SCENE CONTEXT: {master_scene_raw}
        DATABASE REFERENCE: 
        {technical_keywords}
        
        CUSTOM BODY KEYWORDS: {CUSTOM_KEYWORDS}

        INSTRUCTIONS:
        1. **Consistency Layer (CONVERT TO KEYWORDS)**: 
           - Extract visual details (Outfit, Setting) from the Master Scene.
           - CONVERT them into comma-separated keywords.
           - BAD: "She is wearing a white shirt."
           - GOOD: "white shirt, loose fit, cotton fabric"
        2. **Hair Layer**: You MUST include the keywords from 'HAIR KEYWORDS'.
        3. **Variation Layer**: Add the specific Pose, Camera, and Angle keywords for this shot.
        4. **Technical Layer**: Add 'LIGHTING' and 'QUALITY' keywords from the database reference.
        
        CRITICAL FORMATTING RULES:
        - **ABSOLUTELY NO SENTENCES**.
        - **ABSOLUTELY NO "She wears...", "The scene is..."**.
        - OUTPUT ONLY A COMMA-SEPARATED LIST OF KEYWORDS.
        - DO NOT include labels like "Mood Lighting:", "Quality:", "Hair:", etc.
        - Structure: <lora:{persona_name.lower()}>, Instagirl, [Scene/Outfit Keywords], [Hair Keywords], [Custom Body Keywords], [Pose/Angle Keywords], [Lighting/Quality Keywords]
        
        NO NEGATIVE PROMPT IS NEEDED.
        """,
        expected_output="Final comma-separated Positive Prompt keywords ONLY.",
        agent=create_image_prompter_agent(persona_name)
    )

# ---------- Workflow Manager ----------

class CrewAIMoodVariationsWorkflow:
    def __init__(self, persona_name: str = "JENNIE"):
        self.persona_name = persona_name.upper()
        # Initialize DB connection
        try:
            self.db = StructuredPersonaDatabase()
            print("✅ Database connection initialized.")
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            self.db = None

    def _get_mood_from_db(self, persona_id: int, mood_number: int) -> Optional[StructuredMood]:
        """Fetch specific mood from database."""
        if not self.db:
            return None
        
        try:
            mood = self.db.get_mood_by_persona_and_number(persona_id, mood_number)
            return mood
        except Exception as e:
            print(f"❌ DB Query Error: {e}")
            return None

    def _clean_prompt(self, text: str) -> str:
        """
        Aggressively cleans prompt text to remove sentence structures and labels.
        """
        # 1. Remove common labels
        labels = [
            "Mood Lighting:", "Quality Keywords:", "HAIR KEYWORDS:", "Pose:", "Outfit:", "Setting:",
            "Scene:", "Visual Plan:", "Positive Prompt:", "Keywords:", "Technical Layer:", "Consistency Layer:"
        ]
        cleaned = text
        for label in labels:
            cleaned = cleaned.replace(label, "")
        
        # 2. Remove sentence starters and connectors (case insensitive)
        patterns = [
            r'\bShe is\b', r'\bHe is\b', r'\bIt is\b', r'\bThere is\b',
            r'\bShe wears\b', r'\bHe wears\b', r'\bShe has\b', 
            r'\bThe scene is\b', r'\bThe background is\b',
            r'\bfeaturing a\b', r'\bconsisting of\b', r'\bcomposed of\b',
            r'\bshows a\b', r'\bdepicts a\b', r'\bcaptures a\b',
            r'\bcreates a\b', r'\bprovides a\b', r'\benhancing the\b',
            r'\bmaintaining a\b', r'\badding a\b', r'\blooking out\b'
        ]
        
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # 3. Remove articles and simple prepositions if they are standalone
        # Be careful not to break meaningful phrases, but for prompts, removing 'a', 'an', 'the' is usually safe.
        cleaned = re.sub(r'\b(a|an|the)\b', '', cleaned, flags=re.IGNORECASE)

        # 4. Clean up punctuation
        cleaned = cleaned.replace('.', ',')
        cleaned = cleaned.replace(';', ',')
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Multiple spaces -> single space
        cleaned = re.sub(r',\s*,+', ',', cleaned)  # Double commas -> single comma
        cleaned = re.sub(r'^\s*,\s*', '', cleaned) # Leading comma
        cleaned = re.sub(r'\s*,\s*$', '', cleaned) # Trailing comma
        
        return cleaned.strip()

    def run(self, persona_id: int, mood_number: int):
        print(f"\n🎬 Starting Mood Variations Workflow")
        print(f"   Persona ID: {persona_id} ({self.persona_name})")
        print(f"   Mood Number: {mood_number}")

        # 1. Fetch Mood
        selected_mood = self._get_mood_from_db(persona_id, mood_number)
        if not selected_mood:
            print(f"❌ Mood #{mood_number} for Persona ID {persona_id} not found in database.")
            return
        
        print(f"✅ Found Mood: {selected_mood.mood_name}")
        print(f"   Description: {selected_mood.mood_description[:100]}...")

        # 2. Define Agents
        director = create_visual_director_agent(self.persona_name)
        photographer = create_photographer_agent(self.persona_name)
        captioner = create_captioner_agent(self.persona_name)
        prompter = create_image_prompter_agent(self.persona_name)

        # 3. Step 1: Master Scene Definition
        print("\n🏗️  Phase 1: Defining Master Scene from Database Data...")
        task_master = create_master_scene_task(selected_mood, self.persona_name)
        crew_master = Crew(agents=[director], tasks=[task_master], verbose=True)
        master_scene_result = crew_master.kickoff().raw
        print(f"\n✅ Master Scene Defined:\n{master_scene_result[:200]}...")

        # 4. Step 2: Plan Variations
        print("\n📸 Phase 2: Planning 5 Variations...")
        task_variations = create_variation_task(master_scene_result, self.persona_name)
        crew_variations = Crew(agents=[photographer], tasks=[task_variations], verbose=True)
        variations_result = crew_variations.kickoff().raw
        
        # Parse the variations
        variations_list = []
        raw_splits = re.split(r'\n\d+\.\s+\*\*', variations_result) 
        if len(raw_splits) < 2:
             raw_splits = re.split(r'\n\d+\.\s+', variations_result)
        
        shots = [s.strip() for s in raw_splits if len(s.strip()) > 20][:5]
        
        if len(shots) < 5:
            print("⚠️  Complex parsing fallback triggered")
            shots = [variations_result] * 5 

        # 5. Step 3: Generate Prompts & Captions for each
        print("\n🎨 Phase 3: Generating Content for Variations...")
        
        final_prompts = []
        final_captions = []

        for i, shot_desc in enumerate(shots):
            shot_num = i + 1
            print(f"\n   ... Processing Shot {shot_num}")

            # Prompt Task
            task_p = create_prompt_task(shot_desc, master_scene_result, shot_num, self.persona_name, selected_mood)
            crew_p = Crew(agents=[prompter], tasks=[task_p], verbose=False)
            prompt_res = crew_p.kickoff().raw
            
            # AGGRESSIVE CLEANING
            cleaned_prompt = self._clean_prompt(prompt_res)
            final_prompts.append(cleaned_prompt)

            # Caption Task
            task_c = Task(
                description=f"Write a short caption for Shot {shot_num}: {shot_desc}. Keep it consistent with the generated activity.",
                expected_output="Caption text",
                agent=captioner
            )
            crew_c = Crew(agents=[captioner], tasks=[task_c], verbose=False)
            caption_res = crew_c.kickoff().raw
            final_captions.append(caption_res)

        # 6. Output Results
        print("\n" + "="*80)
        print("🎉 WORKFLOW COMPLETE - FULL SUMMARY")
        print("="*80)
        
        print(f"\n📝 MASTER SCENE CONCEPT:\n{master_scene_result}\n")
        print("-" * 80)

        for i in range(len(final_prompts)):
            print(f"\n📸 POST {i+1} / 5")
            print(f"{'='*20}")
            print(f"👀 VISUAL PLAN:\n{shots[i]}")
            print(f"\n🖍️  POSITIVE PROMPT:\n{final_prompts[i]}")
            print(f"\n💬 CAPTION:\n{final_captions[i]}")
            print("-" * 80)

        return {
            "master_scene": master_scene_result,
            "variations": shots,
            "prompts": final_prompts,
            "captions": final_captions
        }

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona-id", type=int, default=1, help="Persona ID in DB (default: 1)")
    parser.add_argument("--mood-number", type=int, required=True, help="Mood Number to fetch (e.g. 1)")
    parser.add_argument("--persona", default="Jennie", help="Persona Name (for LoRA)")
    args = parser.parse_args()

    workflow = CrewAIMoodVariationsWorkflow(args.persona)
    workflow.run(args.persona_id, args.mood_number)

if __name__ == "__main__":
    main()
