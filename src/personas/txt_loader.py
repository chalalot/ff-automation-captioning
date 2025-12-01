#!/usr/bin/env python3
"""
Text loader for personas - Database-only implementation.
Replaces the old file-based system with PostgreSQL database access.
"""

from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


def load_persona_from_database(persona_name: str) -> Optional[str]:
    """
    Load persona text from PostgreSQL database ONLY. No fallbacks.
    
    Args:
        persona_name: Name of the persona to load
        
    Returns:
        Persona text string or None if not found
    """
    try:
        from .db_models import PersonaDatabase
        
        # Initialize database connection - will fail if PostgreSQL not available
        db = PersonaDatabase()
        
        # Try exact match only
        persona = db.get_persona(persona_name)
        if persona:
            return persona.to_persona_text()
        
        # Persona not found - return None (no fallbacks)
        logger.warning(f"Persona '{persona_name}' not found in PostgreSQL database")
        return None
        
    except Exception as e:
        logger.error(f"Error connecting to PostgreSQL database for persona '{persona_name}': {e}")
        return None


def load_all_personas_from_database() -> Dict[str, str]:
    """
    Load all personas from database.
    
    Returns:
        Dictionary mapping persona names to their text descriptions
    """
    try:
        from .db_models import PersonaDatabase
        
        db = PersonaDatabase()
        all_personas = db.get_all_personas()
        
        result = {}
        for persona in all_personas:
            result[persona.persona_name] = persona.to_persona_text()
        
        return result
        
    except Exception as e:
        logger.error(f"Error loading all personas from database: {e}")
        return {}


def load_persona_from_txt(persona_name: str) -> Optional[str]:
    """
    Load persona from database (renamed for backward compatibility).
    This function name is kept for compatibility but now only uses database.
    
    Args:
        persona_name: Name of the persona to load
        
    Returns:
        Persona text string or None if not found
    """
    return load_persona_from_database(persona_name)


def load_all_personas_from_directory(directory_path: str) -> Dict[str, str]:
    """
    DEPRECATED: Directory-based loading no longer supported.
    Use database-only approach instead.
    
    Args:
        directory_path: Ignored
        
    Returns:
        Empty dict (use load_all_personas_from_database instead)
    """
    logger.warning("Directory-based persona loading is deprecated. Use database instead.")
    return {}


def get_available_persona_names() -> List[str]:
    """
    Get list of available persona names from database.
    
    Returns:
        List of persona names
    """
    try:
        from .db_models import PersonaDatabase
        
        db = PersonaDatabase()
        all_personas = db.get_all_personas()
        
        return [persona.persona_name for persona in all_personas]
        
    except Exception as e:
        logger.error(f"Error getting persona names from database: {e}")
        return []


# Backward compatibility aliases
get_all_personas = load_all_personas_from_database
get_persona = load_persona_from_database

# Deprecated function name - keeping for compatibility but points to strict version
load_persona_with_fallback = load_persona_from_database
