#!/usr/bin/env python3
"""
Mood Parser for Persona Style Constraints

Parses mood-based persona descriptions into structured constraints
for strict agent enforcement.
"""

from __future__ import annotations
import re
import random
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class MoodProfile(BaseModel):
    """A single mood with its keyword constraints."""
    mood_name: str = Field(..., description="Full mood name like 'Mood 1: Sunlit Interior & Candid Home Life'")
    mood_number: int = Field(..., description="Mood number (1-4)")
    mood_description: str = Field(..., description="Description of the mood feeling")
    pose_keywords: List[str] = Field(default_factory=list, description="Allowed pose keywords")
    lighting_keywords: List[str] = Field(default_factory=list, description="Allowed lighting keywords")
    clothes_keywords: List[str] = Field(default_factory=list, description="Allowed clothing keywords")
    expression_keywords: List[str] = Field(default_factory=list, description="Allowed expression keywords")
    props_setting_keywords: List[str] = Field(default_factory=list, description="Allowed props and setting keywords")

    def get_all_keywords(self) -> List[str]:
        """Get all keywords from this mood combined."""
        return (
            self.pose_keywords +
            self.lighting_keywords +
            self.clothes_keywords +
            self.expression_keywords +
            self.props_setting_keywords
        )

    def to_constraint_string(self) -> str:
        """Convert mood to a constraint string for agent prompts."""
        return f"""
MOOD: {self.mood_name}
DESCRIPTION: {self.mood_description}

ALLOWED KEYWORDS ONLY:
- Poses: {', '.join(self.pose_keywords)}
- Lighting: {', '.join(self.lighting_keywords)}
- Clothes: {', '.join(self.clothes_keywords)}
- Expressions: {', '.join(self.expression_keywords)}
- Props/Settings: {', '.join(self.props_setting_keywords)}

YOU MUST ONLY USE THESE EXACT KEYWORDS. NO CREATIVE ADDITIONS.
"""


class PersonaMoodCollection(BaseModel):
    """Collection of all moods for a persona."""
    persona_name: str = Field(..., description="Name of the persona")
    moods: List[MoodProfile] = Field(default_factory=list, description="List of available moods")

    def get_mood_by_number(self, mood_number: int) -> Optional[MoodProfile]:
        """Get mood by number (1-4)."""
        for mood in self.moods:
            if mood.mood_number == mood_number:
                return mood
        return None

    def get_random_mood(self) -> Optional[MoodProfile]:
        """Get a random mood from available moods."""
        return random.choice(self.moods) if self.moods else None

    def get_all_keywords(self) -> Dict[str, List[str]]:
        """Get all keywords from all moods combined by category."""
        combined = {
            'poses': [],
            'lighting': [],
            'clothes': [],
            'expressions': [],
            'props_settings': []
        }
        
        for mood in self.moods:
            combined['poses'].extend(mood.pose_keywords)
            combined['lighting'].extend(mood.lighting_keywords)
            combined['clothes'].extend(mood.clothes_keywords)
            combined['expressions'].extend(mood.expression_keywords)
            combined['props_settings'].extend(mood.props_setting_keywords)
        
        # Remove duplicates while preserving order
        for key in combined:
            combined[key] = list(dict.fromkeys(combined[key]))
        
        return combined

    def to_json_string(self) -> str:
        """Convert to JSON string for agent prompts."""
        return self.model_dump_json(indent=2)


def parse_persona_moods(prompt_text: str, persona_name: str = "") -> PersonaMoodCollection:
    """
    Parse mood-based persona text into structured MoodProfile objects.
    
    Expected format:
    Mood 1: Title
    Description text...
    
    Pose Keywords: keyword1, keyword2, keyword3
    Lighting Keywords: keyword1, keyword2
    ...
    
    Args:
        prompt_text: The mood-based persona text
        persona_name: Name of the persona
        
    Returns:
        PersonaMoodCollection with parsed moods
    """
    moods = []
    current_mood_data = {}
    current_mood_number = None
    
    lines = prompt_text.strip().split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Start of new mood section
        mood_match = re.match(r'Mood (\d+):\s*(.*)', line)
        if mood_match:
            # Save previous mood if exists
            if current_mood_data and current_mood_number:
                mood = MoodProfile(
                    mood_name=current_mood_data.get('name', f'Mood {current_mood_number}'),
                    mood_number=current_mood_number,
                    mood_description=current_mood_data.get('description', ''),
                    pose_keywords=current_mood_data.get('pose_keywords', []),
                    lighting_keywords=current_mood_data.get('lighting_keywords', []),
                    clothes_keywords=current_mood_data.get('clothes_keywords', []),
                    expression_keywords=current_mood_data.get('expression_keywords', []),
                    props_setting_keywords=current_mood_data.get('props_setting_keywords', [])
                )
                moods.append(mood)
            
            # Start new mood
            current_mood_number = int(mood_match.group(1))
            current_mood_data = {
                'name': f"Mood {current_mood_number}: {mood_match.group(2)}",
                'description': '',
                'pose_keywords': [],
                'lighting_keywords': [],
                'clothes_keywords': [],
                'expression_keywords': [],
                'props_setting_keywords': []
            }
            
        # Mood description (paragraph after mood title)
        elif current_mood_data and not line.endswith('Keywords:') and ':' not in line and line:
            if current_mood_data['description']:
                current_mood_data['description'] += ' ' + line
            else:
                current_mood_data['description'] = line
                
        # Keyword lines
        elif ':' in line and current_mood_data:
            key_part, value_part = line.split(':', 1)
            key_clean = key_part.strip().lower().replace(' ', '_')
            
            # Parse comma-separated keywords
            keywords = [kw.strip() for kw in value_part.split(',') if kw.strip()]
            
            # Map to appropriate field
            if 'pose' in key_clean:
                current_mood_data['pose_keywords'] = keywords
            elif 'lighting' in key_clean:
                current_mood_data['lighting_keywords'] = keywords
            elif 'clothes' in key_clean or 'clothing' in key_clean:
                current_mood_data['clothes_keywords'] = keywords
            elif 'expression' in key_clean:
                current_mood_data['expression_keywords'] = keywords
            elif 'props' in key_clean or 'setting' in key_clean:
                current_mood_data['props_setting_keywords'] = keywords
        
        i += 1
    
    # Don't forget the last mood
    if current_mood_data and current_mood_number:
        mood = MoodProfile(
            mood_name=current_mood_data.get('name', f'Mood {current_mood_number}'),
            mood_number=current_mood_number,
            mood_description=current_mood_data.get('description', ''),
            pose_keywords=current_mood_data.get('pose_keywords', []),
            lighting_keywords=current_mood_data.get('lighting_keywords', []),
            clothes_keywords=current_mood_data.get('clothes_keywords', []),
            expression_keywords=current_mood_data.get('expression_keywords', []),
            props_setting_keywords=current_mood_data.get('props_setting_keywords', [])
        )
        moods.append(mood)
    
    return PersonaMoodCollection(persona_name=persona_name, moods=moods)


def select_mood_for_trend(trend_text: str, mood_collection: PersonaMoodCollection) -> Optional[MoodProfile]:
    """
    Select mood based on trend content with slight influence.
    Falls back to random selection if no trend match.
    
    Args:
        trend_text: The input trend text
        mood_collection: Available moods for the persona
        
    Returns:
        Selected MoodProfile or None if no moods available
    """
    if not mood_collection.moods:
        return None
    
    trend_lower = trend_text.lower()
    
    # Simple trend → mood preference mapping
    if any(word in trend_lower for word in ['travel', 'vacation', 'beach', 'adventure', 'rooftop', 'scenic']):
        # Prefer Mood 4 (Sun-Kissed Travel) if available
        mood_4 = mood_collection.get_mood_by_number(4)
        if mood_4:
            return mood_4
    
    elif any(word in trend_lower for word in ['nature', 'outdoor', 'garden', 'flowers', 'park', 'green']):
        # Prefer Mood 2 (Dreamy Nature) if available
        mood_2 = mood_collection.get_mood_by_number(2)
        if mood_2:
            return mood_2
    
    elif any(word in trend_lower for word in ['home', 'cozy', 'morning', 'relax', 'bedroom', 'indoor']):
        # Prefer Mood 1 (Sunlit Interior) if available
        mood_1 = mood_collection.get_mood_by_number(1)
        if mood_1:
            return mood_1
    
    elif any(word in trend_lower for word in ['minimal', 'simple', 'clean', 'confident', 'portrait']):
        # Prefer Mood 3 (Candid & Confident) if available
        mood_3 = mood_collection.get_mood_by_number(3)
        if mood_3:
            return mood_3
    
    # Default: Random mood selection
    return mood_collection.get_random_mood()


def assemble_keywords_from_structured_mood(structured_mood) -> str:
    """
    Assemble all keywords from a StructuredMood object into a comma-separated prompt string.
    Uses EXACT keywords from database with no modifications.
    
    Args:
        structured_mood: StructuredMood object from database
        
    Returns:
        Comma-separated string of all keywords
    """
    if not structured_mood:
        return ""
    
    # Use the built-in assemble_prompt method from StructuredMood
    return structured_mood.assemble_prompt()


def get_structured_mood_by_persona_and_number(persona_name: str, mood_number: int):
    """
    Get a StructuredMood from database by persona name and mood number.
    
    Args:
        persona_name: Name of the persona
        mood_number: Number of the mood (1-8)
        
    Returns:
        StructuredMood object or None if not found
    """
    try:
        from .db_models import StructuredPersonaDatabase
        
        db = StructuredPersonaDatabase()
        structured_mood = db.get_mood_by_persona_name_and_number(persona_name, mood_number)
        return structured_mood
        
    except Exception as e:
        print(f"Error getting structured mood: {e}")
        return None


def assemble_keywords_for_persona_mood(persona_name: str, mood_number: int) -> str:
    """
    Convenience function to get keywords for a specific persona mood.
    
    Args:
        persona_name: Name of the persona  
        mood_number: Number of the mood (1-8)
        
    Returns:
        Comma-separated string of all keywords from that mood
    """
    structured_mood = get_structured_mood_by_persona_and_number(persona_name, mood_number)
    return assemble_keywords_from_structured_mood(structured_mood)


# Test function for development
def test_mood_parser():
    """Test the mood parser with sample data."""
    sample_text = """
Mood 1: Sunlit Interior & Candid Home Life
This mood captures the persona in relaxed, intimate, and unposed moments indoors or on a private balcony. The feeling is calm, comfortable, and authentic, like a quiet morning or a lazy afternoon.

Pose Keywords: lounging on bed, sitting on a balcony, leaning against a wall, looking off-camera, candidly focused (on phone), sitting on the floor, legs crossed, relaxed posture

Lighting Keywords: soft window light, direct sunlight beam, warm indoor lamp, golden hour (indoors), soft shadows

Clothes Keywords: simple cotton tank top, loungewear, white t-shirt, simple white blouse, underwear and tank top, pajama shorts, spaghetti strap top

Expression Keywords: calm, serene, content, peaceful, relaxed, focused, thoughtful

Props & Setting Keywords: white bed linens, phone, headphones, simple bedroom, uncluttered room, balcony, breakfast tray, orange juice, coffee mug

Mood 2: Dreamy Nature & Lush Greenery
This mood is ethereal, playful, and deeply connected to nature. The persona is seen in lush, sun-drenched outdoor environments, interacting with natural elements. The feeling is innocent, free, and joyful.

Pose Keywords: lying in flowers, sitting on a bench, sitting in grass, reading a book, playing with bubbles, eating fruit (cherries), holding flowers, laughing, looking up at the sky

Lighting Keywords: bright diffused sunlight, dappled light (through trees), sun-drenched, golden hour, soft focus, ethereal glow

Clothes Keywords: simple summer dress, linen top, white lace dress, floral print dress, off-shoulder top, simple light-colored fabrics

Expression Keywords: serene, dreamy, playful, laughing, joyful, innocent, eyes closed

Props & Setting Keywords: book, fresh fruit (cherries), bubbles, wildflowers, lush green grass, park, garden, fruit basket
"""
    
    collection = parse_persona_moods(sample_text, "Test Persona")
    print(f"Parsed {len(collection.moods)} moods")
    for mood in collection.moods:
        print(f"\n{mood.mood_name}")
        print(f"Poses: {len(mood.pose_keywords)}")
        print(f"Lighting: {len(mood.lighting_keywords)}")
        print(f"Props: {len(mood.props_setting_keywords)}")


if __name__ == "__main__":
    test_mood_parser()
