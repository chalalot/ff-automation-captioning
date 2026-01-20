import json
import os
from typing import List, Dict, Any, Optional

class WorkflowConfigManager:
    """
    Manages loading and saving persona configuration and types using text files in prompts directory.
    """
    
    def __init__(self):
        # Determine paths relative to this file
        # src/workflows/config_manager.py -> ../../prompts
        self.PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'prompts'))
        self.PERSONAS_DIR = os.path.join(self.PROMPTS_DIR, 'personas')
        self.TYPES_FILE = os.path.join(self.PROMPTS_DIR, 'persona_types.txt')
        
        # Ensure directories exist
        os.makedirs(self.PERSONAS_DIR, exist_ok=True)
        if not os.path.exists(self.TYPES_FILE):
             # Default types if not exists
             with open(self.TYPES_FILE, 'w', encoding='utf-8') as f:
                 f.write("instagirl\ngymer\ndancer")

    def get_personas(self) -> List[str]:
        """Returns list of persona names based on directories."""
        if not os.path.exists(self.PERSONAS_DIR):
            return []
        
        personas = []
        for item in os.listdir(self.PERSONAS_DIR):
            if os.path.isdir(os.path.join(self.PERSONAS_DIR, item)):
                personas.append(item)
        return sorted(personas)
    
    def get_persona_types(self) -> List[str]:
        """Returns list of available persona types from text file."""
        if not os.path.exists(self.TYPES_FILE):
            return ["instagirl"] # Fallback
            
        try:
            with open(self.TYPES_FILE, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            print(f"Error loading persona types: {e}")
            return ["instagirl"]

    def get_persona_config(self, name: str) -> Dict[str, Any]:
        """Returns configuration for a specific persona by reading its text files."""
        persona_dir = os.path.join(self.PERSONAS_DIR, name)
        if not os.path.exists(persona_dir):
            return {}
            
        config = {}
        
        # Read Type
        try:
            with open(os.path.join(persona_dir, 'type.txt'), 'r', encoding='utf-8') as f:
                config['type'] = f.read().strip()
        except:
            config['type'] = 'instagirl' # Default
            
        # Read Hair Color
        try:
            with open(os.path.join(persona_dir, 'hair_color.txt'), 'r', encoding='utf-8') as f:
                config['hair_color'] = f.read().strip()
        except:
            config['hair_color'] = ''
            
        # Read Hairstyles
        try:
            with open(os.path.join(persona_dir, 'hairstyles.txt'), 'r', encoding='utf-8') as f:
                lines = f.readlines()
                config['hairstyles'] = [line.strip() for line in lines if line.strip()]
        except:
            config['hairstyles'] = []
            
        return config

    def update_persona_config(self, name: str, data: Dict[str, Any]):
        """Updates configuration for a specific persona by writing to text files."""
        persona_dir = os.path.join(self.PERSONAS_DIR, name)
        os.makedirs(persona_dir, exist_ok=True)
        
        # Update Type
        if 'type' in data:
            with open(os.path.join(persona_dir, 'type.txt'), 'w', encoding='utf-8') as f:
                f.write(str(data['type']))
                
        # Update Hair Color
        if 'hair_color' in data:
            with open(os.path.join(persona_dir, 'hair_color.txt'), 'w', encoding='utf-8') as f:
                f.write(str(data['hair_color']))
                
        # Update Hairstyles
        if 'hairstyles' in data:
            hairstyles = data['hairstyles']
            if isinstance(hairstyles, list):
                content = "\n".join(hairstyles)
                with open(os.path.join(persona_dir, 'hairstyles.txt'), 'w', encoding='utf-8') as f:
                    f.write(content)

    def add_persona_type(self, type_name: str):
        """Adds a new persona type if it doesn't exist."""
        current_types = self.get_persona_types()
            
        if type_name not in current_types:
            current_types.append(type_name)
            try:
                with open(self.TYPES_FILE, 'w', encoding='utf-8') as f:
                    f.write("\n".join(current_types))
            except Exception as e:
                print(f"Error saving persona types: {e}")

    def create_persona_template_structure(self, type_name: str) -> bool:
        """
        Creates directory structure and default files for a new persona type.
        Returns True if created, False if already exists or failed.
        """
        # 1. Add to types list
        self.add_persona_type(type_name)
        
        # 2. Create directory
        template_dir = os.path.join(self.PROMPTS_DIR, 'templates', type_name)
        
        # If directory already exists, we might still want to ensure files exist, 
        # but let's assume if it exists we don't overwrite.
        if not os.path.exists(template_dir):
            try:
                os.makedirs(template_dir, exist_ok=True)
                
                # 3. Create empty files
                files_to_create = [
                    'turbo_agent.txt',
                    'turbo_framework.txt',
                    'turbo_constraints.txt', 
                    'turbo_example.txt',
                    'turbo_prompt_template.txt',
                    'analyst_agent.txt',
                    'analyst_task.txt'
                ]
                
                for filename in files_to_create:
                    file_path = os.path.join(template_dir, filename)
                    if not os.path.exists(file_path):
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write("") # Create empty file
                        
                return True
            except Exception as e:
                print(f"Error creating persona template structure: {e}")
                return False
        return True
