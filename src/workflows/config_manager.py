import json
import os
from typing import List, Dict, Any, Optional

class WorkflowConfigManager:
    """
    Manages loading and saving persona configuration and types.
    """
    
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'persona_config.json')
    
    def __init__(self):
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Loads the persona configuration from JSON file."""
        if not os.path.exists(self.CONFIG_PATH):
            return {"personas": {}, "persona_types": []}
        
        try:
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {"personas": {}, "persona_types": []}

    def save_config(self):
        """Saves the current configuration to the JSON file."""
        try:
            with open(self.CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_personas(self) -> List[str]:
        """Returns list of persona names."""
        return list(self.config.get("personas", {}).keys())
    
    def get_persona_types(self) -> List[str]:
        """Returns list of available persona types."""
        return self.config.get("persona_types", ["instagirl"])

    def get_persona_config(self, name: str) -> Dict[str, Any]:
        """Returns configuration for a specific persona."""
        return self.config.get("personas", {}).get(name, {})

    def update_persona_config(self, name: str, data: Dict[str, Any]):
        """Updates configuration for a specific persona."""
        if "personas" not in self.config:
            self.config["personas"] = {}
        
        # Merge existing with new
        existing = self.config["personas"].get(name, {})
        existing.update(data)
        self.config["personas"][name] = existing
        self.save_config()

    def add_persona_type(self, type_name: str):
        """Adds a new persona type if it doesn't exist."""
        if "persona_types" not in self.config:
            self.config["persona_types"] = []
            
        if type_name not in self.config["persona_types"]:
            self.config["persona_types"].append(type_name)
            self.save_config()
