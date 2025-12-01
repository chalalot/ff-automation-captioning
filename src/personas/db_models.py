#!/usr/bin/env python3
"""
Database models for persona characteristics.
This module defines the schema for storing persona characteristics in a structured database.
Supports both SQLite (local) and Supabase PostgreSQL (deployed).
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict
import json
import os
from pathlib import Path

# Try importing psycopg2 for Supabase support
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Try importing streamlit for secrets support
try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


@dataclass
class PersonaCharacteristics:
    """
    Unified database model for persona characteristics.
    All fields are optional to accommodate different personas with varying levels of detail.
    """
    # Core Info
    persona_name: str  # Unique identifier (e.g., "JENNIE")
    display_name: str  # Full display name (e.g., "JENNIE - Clean-Girl Tech Chic")

    # Physical Appearance
    ethnicity_skin: Optional[str] = None
    body_shape: Optional[str] = None
    height_frame: Optional[str] = None
    face: Optional[str] = None
    eyes: Optional[str] = None
    nose: Optional[str] = None
    lips: Optional[str] = None
    eyebrows: Optional[str] = None
    hair: Optional[str] = None
    makeup_style: Optional[str] = None
    makeup_free: Optional[str] = None

    # Basic Profile
    field: Optional[str] = None
    special_hobby: Optional[str] = None
    signature_gadget: Optional[str] = None
    reference: Optional[str] = None

    # Authenticity Anchors
    props_repeat: Optional[str] = None
    backgrounds_repeat: Optional[str] = None
    makeup_description: Optional[str] = None
    imperfections: Optional[str] = None

    # Mood Palette
    mood_common: Optional[str] = None
    mood_often: Optional[str] = None
    mood_sometimes: Optional[str] = None

    # Content Distribution
    everyday_content_60: Optional[str] = None
    lifestyle_variety_30: Optional[str] = None
    trending_themes_10: Optional[str] = None

    # Additional (for some personas)
    caption_voice_tone: Optional[str] = None
    caption_voice_length: Optional[str] = None
    caption_voice_emojis: Optional[str] = None
    caption_voice_hashtags: Optional[str] = None
    caption_voice_ctas: Optional[str] = None

    visual_aesthetic_vibe: Optional[str] = None
    visual_aesthetic_color_palette: Optional[str] = None
    visual_aesthetic_lighting: Optional[str] = None
    visual_aesthetic_composition: Optional[str] = None
    visual_aesthetic_filter_style: Optional[str] = None

    authenticity_philosophy: Optional[str] = None

    # Metadata
    id: Optional[int] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_persona_text(self) -> str:
        """
        Reconstruct the persona description text from database fields.
        This generates the same format as the original txt files.
        """
        lines = []

        # Header
        lines.append(self.display_name)
        lines.append("")

        # Physical Appearance (if any physical fields are present)
        if any([self.ethnicity_skin, self.body_shape, self.height_frame, self.face,
                self.eyes, self.nose, self.lips, self.eyebrows, self.hair, self.makeup_style]):
            lines.append("Physical Appearance")
            if self.ethnicity_skin:
                lines.append(f"Ethnicity/Skin: {self.ethnicity_skin}")
            if self.body_shape:
                lines.append(f"Body Shape: {self.body_shape}")
            if self.height_frame:
                lines.append(f"Height/Frame: {self.height_frame}")
            if self.face:
                lines.append(f"Face: {self.face}")
            if self.eyes:
                lines.append(f"Eyes: {self.eyes}")
            if self.nose:
                lines.append(f"Nose: {self.nose}")
            if self.lips:
                lines.append(f"Lips: {self.lips}")
            if self.eyebrows:
                lines.append(f"Eyebrows: {self.eyebrows}")
            if self.hair:
                lines.append(f"Hair: {self.hair}")
            if self.makeup_style:
                lines.append(f"Makeup: {self.makeup_style}")
            if self.makeup_free:
                lines.append(f"Makeup-Free: {self.makeup_free}")
            lines.append("")

        # Basic Profile
        lines.append("Basic Profile")
        if self.field:
            lines.append(f"Field: {self.field}")
        if self.reference:
            lines.append(f"Reference: {self.reference}")
        if self.special_hobby:
            lines.append(f"Special Hobby: {self.special_hobby}")
        if self.signature_gadget:
            lines.append(f"Signature Gadget: {self.signature_gadget}")
        lines.append("")

        # Authenticity Anchors
        lines.append("Authenticity Anchors")
        if self.props_repeat:
            lines.append(f"Props (repeat): {self.props_repeat}")
        if self.backgrounds_repeat:
            lines.append(f"Backgrounds (repeat): {self.backgrounds_repeat}")
        if self.makeup_description:
            lines.append(f"Makeup: {self.makeup_description}")
        if self.imperfections:
            lines.append(f"Imperfections: {self.imperfections}")
        lines.append("")

        # Mood Palette
        lines.append("Mood Palette")
        if self.mood_common:
            lines.append(f"Common: {self.mood_common}")
        if self.mood_often:
            lines.append(f"Often: {self.mood_often}")
        if self.mood_sometimes:
            lines.append(f"Sometimes: {self.mood_sometimes}")
        lines.append("")

        # Content Distribution
        if self.everyday_content_60:
            lines.append("60% Everyday Content")
            lines.append(self.everyday_content_60)
            lines.append("")

        if self.lifestyle_variety_30:
            lines.append("30% Lifestyle Variety")
            lines.append(self.lifestyle_variety_30)
            lines.append("")

        if self.trending_themes_10:
            lines.append("10% Trending Themes (Rare)")
            lines.append(self.trending_themes_10)
            lines.append("")

        # Caption Voice & Style (if present)
        if any([self.caption_voice_tone, self.caption_voice_length, self.caption_voice_emojis,
                self.caption_voice_hashtags, self.caption_voice_ctas]):
            lines.append("Caption Voice & Style")
            if self.caption_voice_tone:
                lines.append(f"Tone: {self.caption_voice_tone}")
            if self.caption_voice_length:
                lines.append(f"Length: {self.caption_voice_length}")
            if self.caption_voice_emojis:
                lines.append(f"Emojis: {self.caption_voice_emojis}")
            if self.caption_voice_hashtags:
                lines.append(f"Hashtags: {self.caption_voice_hashtags}")
            if self.caption_voice_ctas:
                lines.append(f"CTAs: {self.caption_voice_ctas}")
            lines.append("")

        # Visual Aesthetic (if present)
        if any([self.visual_aesthetic_vibe, self.visual_aesthetic_color_palette,
                self.visual_aesthetic_lighting, self.visual_aesthetic_composition,
                self.visual_aesthetic_filter_style]):
            lines.append("Visual Aesthetic")
            if self.visual_aesthetic_vibe:
                lines.append(f"Overall Vibe: {self.visual_aesthetic_vibe}")
            if self.visual_aesthetic_color_palette:
                lines.append(f"Color Palette: {self.visual_aesthetic_color_palette}")
            if self.visual_aesthetic_lighting:
                lines.append(f"Lighting: {self.visual_aesthetic_lighting}")
            if self.visual_aesthetic_composition:
                lines.append(f"Composition: {self.visual_aesthetic_composition}")
            if self.visual_aesthetic_filter_style:
                lines.append(f"Filter Style: {self.visual_aesthetic_filter_style}")
            lines.append("")

        # Authenticity Philosophy (if present)
        if self.authenticity_philosophy:
            lines.append("Authenticity Philosophy")
            lines.append(self.authenticity_philosophy)
            lines.append("")

        return "\n".join(lines)


@dataclass 
class SimplePersona:
    """
    Simple persona model that reads directly from 'prompt' column.
    """
    persona_name: str
    prompt: str

    def to_persona_text(self) -> str:
        """Return the prompt content directly."""
        return self.prompt


@dataclass
class StructuredMood:
    """
    Structured mood model for the persona_moods table.
    """
    id: int
    persona_id: int
    mood_name: str
    mood_number: int
    mood_description: str
    pose_keywords: List[str] = field(default_factory=list)
    lighting_keywords: List[str] = field(default_factory=list)
    clothes_keywords: List[str] = field(default_factory=list)
    hair_keywords: List[str] = field(default_factory=list)
    expression_keywords: List[str] = field(default_factory=list)
    props_setting_keywords: List[str] = field(default_factory=list)
    camera_quality_keywords: List[str] = field(default_factory=list)

    def get_all_keywords(self) -> List[str]:
        """Get all keywords from this mood combined."""
        all_keywords = []
        all_keywords.extend(self.pose_keywords)
        all_keywords.extend(self.lighting_keywords)
        all_keywords.extend(self.clothes_keywords)
        all_keywords.extend(self.hair_keywords)
        all_keywords.extend(self.expression_keywords)
        all_keywords.extend(self.props_setting_keywords)
        all_keywords.extend(self.camera_quality_keywords)
        return all_keywords

    def assemble_prompt(self) -> str:
        """Assemble all keywords into a comma-separated prompt string."""
        all_keywords = self.get_all_keywords()
        return ", ".join(all_keywords)


@dataclass
class StructuredPersona:
    """
    Structured persona model for the personas table.
    """
    id: int
    name: str
    created_at: Optional[str] = None


class StructuredPersonaDatabase:
    """
    Database handler for structured personas and moods.
    Works with the new personas and persona_moods tables.
    """

    def __init__(self, connection_string: Optional[str] = None):
        """Initialize StructuredPersonaDatabase."""
        print(f"[StructuredPersonaDatabase] Initializing with centralized connection utility")
        
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2-binary is required for PostgreSQL. Run: pip install psycopg2-binary")
        
        # Use centralized database connection utility
        from src.database.db_utils import get_postgres_connection_string
        
        try:
            self.connection_string = get_postgres_connection_string(connection_string)
            print(f"[StructuredPersonaDatabase] Using centralized connection: {get_postgres_connection_string(connection_string, mask_password=True)}")
        except ValueError as e:
            print(f"[StructuredPersonaDatabase] Failed to get connection string: {e}")
            raise

    def _get_connection(self):
        """Get PostgreSQL database connection."""
        return psycopg2.connect(self.connection_string)

    def get_persona_by_name(self, persona_name: str) -> Optional[StructuredPersona]:
        """Get a persona by name from the personas table."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id, name, created_at FROM personas WHERE UPPER(name) = UPPER(%s)", (persona_name,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return StructuredPersona(
                id=row['id'],
                name=row['name'],
                created_at=str(row['created_at']) if row['created_at'] else None
            )
        finally:
            cursor.close()
            conn.close()


    def get_mood_by_persona_and_number(self, persona_id: int, mood_number: int) -> Optional[StructuredMood]:
        """Get a specific mood by persona_id and mood_number."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, persona_id, mood_name, mood_number, mood_description,
                       pose_keywords, lighting_keywords, clothes_keywords, hair_keywords,
                       expression_keywords, props_setting_keywords, camera_quality_keywords
                FROM persona_moods 
                WHERE persona_id = %s AND mood_number = %s
            """, (persona_id, mood_number))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return StructuredMood(
                id=row['id'],
                persona_id=row['persona_id'],
                mood_name=row['mood_name'],
                mood_number=row['mood_number'],
                mood_description=row['mood_description'] or "",
                pose_keywords=row['pose_keywords'] or [],
                lighting_keywords=row['lighting_keywords'] or [],
                clothes_keywords=row['clothes_keywords'] or [],
                hair_keywords=row['hair_keywords'] or [],
                expression_keywords=row['expression_keywords'] or [],
                props_setting_keywords=row['props_setting_keywords'] or [],
                camera_quality_keywords=row['camera_quality_keywords'] or []
            )
        finally:
            cursor.close()
            conn.close()

    def get_all_moods_for_persona(self, persona_id: int) -> List[StructuredMood]:
        """Get all moods for a persona."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT id, persona_id, mood_name, mood_number, mood_description,
                       pose_keywords, lighting_keywords, clothes_keywords, hair_keywords,
                       expression_keywords, props_setting_keywords, camera_quality_keywords
                FROM persona_moods 
                WHERE persona_id = %s
                ORDER BY mood_number
            """, (persona_id,))
            rows = cursor.fetchall()
            
            moods = []
            for row in rows:
                mood = StructuredMood(
                    id=row['id'],
                    persona_id=row['persona_id'],
                    mood_name=row['mood_name'],
                    mood_number=row['mood_number'],
                    mood_description=row['mood_description'] or "",
                    pose_keywords=row['pose_keywords'] or [],
                    lighting_keywords=row['lighting_keywords'] or [],
                    clothes_keywords=row['clothes_keywords'] or [],
                    hair_keywords=row['hair_keywords'] or [],
                    expression_keywords=row['expression_keywords'] or [],
                    props_setting_keywords=row['props_setting_keywords'] or [],
                    camera_quality_keywords=row['camera_quality_keywords'] or []
                )
                moods.append(mood)
            
            return moods
        finally:
            cursor.close()
            conn.close()

    def get_mood_by_persona_name_and_number(self, persona_name: str, mood_number: int) -> Optional[StructuredMood]:
        """Get a mood by persona name and mood number (convenience method)."""
        persona = self.get_persona_by_name(persona_name)
        if not persona:
            return None
        return self.get_mood_by_persona_and_number(persona.id, mood_number)


class PersonaDatabase:
    """
    Simplified database handler for personas.
    NOTE: 'prompt' column has been removed. This class is largely deprecated in favor of StructuredPersonaDatabase.
    """

    def __init__(self, db_path: str = None, connection_string: Optional[str] = None):
        """
        Initialize PersonaDatabase.

        Args:
            db_path: DEPRECATED - Not used, kept for compatibility
            connection_string: PostgreSQL connection string (optional, auto-detected from env)
        """
        # db_path is deprecated but kept for compatibility
        self.db_path = db_path
        
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2-binary is required for PostgreSQL. Run: pip install psycopg2-binary")
        
        # Use centralized database connection utility
        from src.database.db_utils import get_postgres_connection_string
        
        try:
            self.connection_string = get_postgres_connection_string(connection_string)
            print(f"[PersonaDatabase] Using centralized connection: {get_postgres_connection_string(connection_string, mask_password=True)}")
        except ValueError as e:
            print(f"[PersonaDatabase] Failed to get connection string: {e}")
            raise
            
        self.use_postgres = True
        print(f"[PersonaDatabase] Using PostgreSQL Cloud SQL exclusively")

    def _get_connection(self):
        """Get PostgreSQL database connection."""
        return psycopg2.connect(self.connection_string)

    def get_persona(self, persona_name: str) -> Optional[SimplePersona]:
        """
        Get a persona by name.
        NOTE: General persona text is deprecated. This method returns None to avoid SQL errors.
        """
        print(f"[PersonaDatabase] get_persona('{persona_name}') is deprecated. Using mood-based generation instead.")
        return None

    def get_all_personas(self) -> List[SimplePersona]:
        """
        Get all personas from the 'personas' table.
        NOTE: 'prompt' column is missing. Returns basic info only or empty list if unsafe.
        """
        conn = self._get_connection()

        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Only select valid columns
            query = "SELECT name FROM personas ORDER BY name"
            print(f"[PersonaDatabase] Executing query: {query}")
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append(SimplePersona(
                    persona_name=row['name'], 
                    prompt="" # Prompt is unavailable
                ))
            
            print(f"[PersonaDatabase] Found {len(result)} personas (names only)")
            return result

        except Exception as e:
            print(f"[PersonaDatabase] Error in get_all_personas: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def save_persona(self, persona: SimplePersona) -> bool:
        """Save or update a persona in the 'personas' table."""
        print(f"[PersonaDatabase] save_persona is deprecated. 'prompt' column does not exist.")
        return False

    def delete_persona(self, persona_name: str) -> bool:
        """Delete a persona from the 'personas' table."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM personas WHERE UPPER(name) = UPPER(%s)",
                (persona_name,)
            )

            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

        finally:
            cursor.close()
            conn.close()
