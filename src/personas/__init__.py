# Import with graceful fallback for dependencies
try:
    from .models import Persona
except ImportError:
    Persona = None

try:
    from .loader import load_personas_csv
except ImportError:
    load_personas_csv = None

# Database-only imports
from .txt_loader import (
    load_persona_from_txt, 
    load_persona_from_database,
    load_all_personas_from_directory, 
    load_all_personas_from_database,
    get_available_persona_names
)

# db_models imports - using simplified SimplePersona and PersonaDatabase
try:
    from .db_models import SimplePersona, PersonaDatabase, PersonaCharacteristics
except ImportError:
    SimplePersona = None
    PersonaDatabase = None
    PersonaCharacteristics = None

__all__ = [
    "Persona",
    "load_personas_csv",
    "load_persona_from_txt",
    "load_persona_from_database", 
    "load_all_personas_from_directory",
    "load_all_personas_from_database",
    "get_available_persona_names",
    "SimplePersona",
    "PersonaCharacteristics", 
    "PersonaDatabase"
]
