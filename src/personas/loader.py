from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .models import Persona


def load_personas_csv(csv_path: str | Path) -> List[Persona]:
    path = Path(csv_path)
    if not path.exists():
        return []

    personas: List[Persona] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_persona = row.get("Persona") or ""
            if not raw_persona.strip():
                continue
            persona = Persona(
                raw_name=raw_persona,
                name=Persona.cleaned_name(raw_persona),
                **{k: v for k, v in row.items() if k != "Persona"}
            )
            personas.append(persona)
    return personas

