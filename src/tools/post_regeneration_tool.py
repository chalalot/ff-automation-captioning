"""
Post Regeneration Tool

Re-generates visual plans and image prompts for existing posts using the same content seeds
but with fresh CrewAI agent execution to create variations.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Any
import traceback

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from scripts.crewai_trend_workflow import (
    create_visual_director_agent,
    create_image_prompter_agent,
    create_visual_planning_task,
    create_image_prompt_task
)
from crewai import Crew, Process
from src.personas.db_models import StructuredPersonaDatabase
from src.tools.generate_image_tool import generate_marketing_image_sync

logger = logging.getLogger(__name__)


def regenerate_post_content(
    post_id: str,
    content_seed: Dict[str, Any],
    metadata: Dict[str, Any],
    persona_name: str,
    workflow_name: Optional[str] = None,
    lora_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Regenerate visual plan and image prompt for a post using CrewAI workflow.
    
    Args:
        post_id: Post identifier
        content_seed: Original content seed data
        metadata: Post metadata including mood information
        persona_name: Persona name for regeneration
        workflow_name: Optional ComfyUI workflow name
        lora_name: Optional LoRA model name
        
    Returns:
        Dict with regenerated content including visual_plan, prompts, and image_url
    """
    try:
        logger.info(f"🔄 Starting regeneration for post {post_id}")
        logger.info(f"👤 Persona: {persona_name}")
        logger.info(f"🎭 Content seed: {content_seed}")
        
        # Extract content information
        micro_idea = content_seed.get('micro_idea', '')
        selected_mood = content_seed.get('selected_mood', '')
        
        if not micro_idea:
            raise ValueError("Content seed missing micro_idea")
        
        logger.info(f"💡 Micro idea: {micro_idea}")
        logger.info(f"🎨 Selected mood: {selected_mood}")
        
        # Get structured mood data from database
        assigned_mood_obj = None
        try:
            db = StructuredPersonaDatabase()
            persona_db = db.get_persona_by_name(persona_name.upper())
            
            if persona_db:
                # Try to find mood by name
                moods = db.get_all_moods_for_persona(persona_db.id)
                for mood in moods:
                    if mood.mood_name == selected_mood:
                        assigned_mood_obj = mood
                        break
                
                if assigned_mood_obj:
                    logger.info(f"✅ Found mood data: {assigned_mood_obj.mood_name}")
                else:
                    logger.warning(f"⚠️  Mood '{selected_mood}' not found, using first available mood")
                    if moods:
                        assigned_mood_obj = moods[0]
            else:
                logger.warning(f"⚠️  Persona '{persona_name}' not found in database")
                
        except Exception as e:
            logger.warning(f"⚠️  Could not load mood data: {e}")
        
        # Load persona text
        persona_text = ""
        try:
            if persona_db and persona_db.persona_text:
                persona_text = persona_db.persona_text
                logger.info("✅ Loaded persona text from database")
            else:
                # Fallback to file loading
                from src.personas.txt_loader import load_persona_with_fallback
                persona_data = load_persona_with_fallback(persona_name)
                if persona_data and 'text' in persona_data:
                    persona_text = persona_data['text']
                    logger.info("✅ Loaded persona text from file")
                else:
                    persona_text = f"Persona: {persona_name}\nContent creator with authentic style."
                    logger.warning("⚠️  Using fallback persona text")
                    
        except Exception as e:
            logger.warning(f"⚠️  Could not load persona text: {e}")
            persona_text = f"Persona: {persona_name}\nContent creator with authentic style."
        
        # ========== PHASE 1: REGENERATE VISUAL PLAN ==========
        logger.info("🎨 Phase 1: Regenerating visual plan...")
        
        # Create agents
        visual_planner = create_visual_director_agent(persona_name)
        
        # Create visual planning task with mood constraints
        visual_task = create_visual_planning_task(
            content_seed=micro_idea,
            seed_number=1,  # Dummy number for regeneration
            persona_text=persona_text,
            persona_name=persona_name,
            assigned_mood_obj=assigned_mood_obj
        )
        visual_task.agent = visual_planner
        
        # Run visual planning crew
        visual_crew = Crew(
            agents=[visual_planner],
            tasks=[visual_task],
            process=Process.sequential,
            verbose=False
        )
        
        visual_result = visual_crew.kickoff()
        new_visual_plan_raw = visual_result.raw
        
        logger.info(f"✅ Generated new visual plan: {new_visual_plan_raw[:100]}...")
        
        # Structure the visual plan data
        new_visual_plan = {
            "regenerated": True,
            "image_description": new_visual_plan_raw.strip(),
            "mood_name": assigned_mood_obj.mood_name if assigned_mood_obj else selected_mood,
            "mood_keywords": assigned_mood_obj.get_all_keywords() if assigned_mood_obj else [],
            "regeneration_timestamp": int(__import__('time').time())
        }
        
        # ========== PHASE 2: REGENERATE IMAGE PROMPT ==========
        logger.info("🖼️  Phase 2: Regenerating image prompt...")
        
        # Create image prompter agent
        image_prompter = create_image_prompter_agent(persona_name)
        
        # Create image prompt task
        prompt_task = create_image_prompt_task(
            image_description=new_visual_plan_raw,
            visual_plan=new_visual_plan_raw,
            seed_number=1,  # Dummy number for regeneration
            persona_text=persona_text,
            persona_name=persona_name,
            assigned_mood_obj=assigned_mood_obj
        )
        prompt_task.agent = image_prompter
        
        # Run image prompt crew
        prompt_crew = Crew(
            agents=[image_prompter],
            tasks=[prompt_task],
            process=Process.sequential,
            verbose=False
        )
        
        prompt_result = prompt_crew.kickoff()
        image_prompt_raw = prompt_result.raw
        
        logger.info(f"✅ Generated new image prompt: {image_prompt_raw[:100]}...")
        
        # ========== PHASE 3: PARSE AND CLEAN PROMPT ==========
        logger.info("🧹 Phase 3: Parsing and cleaning prompt...")
        
        # Parse positive and negative prompts
        import re
        
        positive_prompt_match = re.search(r"(.*)Negative prompt:", image_prompt_raw, re.IGNORECASE | re.DOTALL)
        negative_prompt_match = re.search(r"Negative prompt:(.*)", image_prompt_raw, re.IGNORECASE | re.DOTALL)
        
        positive_prompt_raw = positive_prompt_match.group(1).strip() if positive_prompt_match else image_prompt_raw
        negative_prompt_raw = negative_prompt_match.group(1).strip() if negative_prompt_match else "older woman, mature face, tired expression, anime, cartoon, harsh lighting, low quality"
        
        # Clean up prompts
        positive_prompt = re.sub(r'^Positive prompt:\s*', '', positive_prompt_raw, flags=re.IGNORECASE)
        positive_prompt = re.sub(r'^Hybrid prompt.*?:\s*', '', positive_prompt, flags=re.IGNORECASE)
        positive_prompt = positive_prompt.strip()
        
        # Ensure LoRA tag is at the beginning
        lora_tag = f"<lora:{persona_name.lower()}>"
        positive_prompt = re.sub(r'<lora:[^>]*>\s*,?\s*', '', positive_prompt)
        positive_prompt = positive_prompt.strip(' ,')
        positive_prompt = f"{lora_tag}, {positive_prompt}"
        
        # Add quality keywords
        positive_prompt += ", warm highlights and soft shadows, realistic color rendering, daily realistic photography"
        
        logger.info(f"✅ Cleaned prompt: {positive_prompt[:100]}...")
        
        # ========== PHASE 4: GENERATE NEW IMAGE ==========
        logger.info("🖼️  Phase 4: Generating new image...")
        
        # Generate new image
        image_result = generate_marketing_image_sync(
            prompt=positive_prompt,
            kol_persona=persona_name.lower(),
            product_name="regenerated_content",
            workflow_name=workflow_name,
            lora_name=lora_name,
            upload_to_gcs=False  # Use ComfyUI URLs directly
        )
        
        new_image_url = None
        if isinstance(image_result, dict) and 'url' in image_result:
            new_image_url = image_result['url']
            logger.info(f"✅ Generated new image: {new_image_url}")
        else:
            logger.error(f"❌ Image generation failed: {image_result}")
            raise ValueError(f"Image generation failed: {image_result}")
        
        # ========== RETURN RESULTS ==========
        result = {
            "visual_plan": new_visual_plan,
            "image_prompt": positive_prompt,
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt_raw,
            "image_url": new_image_url,
            "metadata": {
                "regenerated": True,
                "original_mood": selected_mood,
                "workflow_name": workflow_name,
                "lora_name": lora_name,
                "regeneration_method": "crewai_workflow"
            }
        }
        
        logger.info("🎉 Regeneration completed successfully!")
        return result
        
    except Exception as e:
        logger.error(f"❌ Regeneration failed for post {post_id}: {e}")
        traceback.print_exc()
        raise


def regenerate_post_simple(
    original_prompt: str,
    persona_name: str,
    workflow_name: Optional[str] = None,
    lora_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Simple regeneration that just adds variation to existing prompt.
    Fallback for when full workflow regeneration is not possible.
    
    Args:
        original_prompt: Original positive prompt
        persona_name: Persona name
        workflow_name: Optional ComfyUI workflow name
        lora_name: Optional LoRA model name
        
    Returns:
        Dict with regenerated content
    """
    try:
        logger.info("🔄 Using simple regeneration (prompt variation)")
        
        # Add variation keywords to the original prompt
        variation_keywords = [
            "slight variation", "new angle", "different lighting",
            "alternative pose", "fresh perspective"
        ]
        
        import random
        selected_variations = random.sample(variation_keywords, 2)
        regenerated_prompt = f"{original_prompt}, {', '.join(selected_variations)}"
        
        # Generate new image
        image_result = generate_marketing_image_sync(
            prompt=regenerated_prompt,
            kol_persona=persona_name.lower(),
            product_name="regenerated_simple",
            workflow_name=workflow_name,
            lora_name=lora_name,
            upload_to_gcs=False
        )
        
        new_image_url = None
        if isinstance(image_result, dict) and 'url' in image_result:
            new_image_url = image_result['url']
            logger.info(f"✅ Simple regeneration complete: {new_image_url}")
        else:
            raise ValueError(f"Image generation failed: {image_result}")
        
        return {
            "visual_plan": {"regenerated": True, "method": "simple_variation"},
            "image_prompt": regenerated_prompt,
            "positive_prompt": regenerated_prompt,
            "negative_prompt": "older woman, mature face, tired expression, anime, cartoon, harsh lighting, low quality",
            "image_url": new_image_url,
            "metadata": {
                "regenerated": True,
                "regeneration_method": "simple_variation"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Simple regeneration failed: {e}")
        raise
