from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class Persona(BaseModel):
    name: str = Field(..., description="Display name (trimmed, without Ref)")
    raw_name: str = Field(..., description="Original persona field from CSV, may include Ref line")
    ethnicity_style: Optional[str] = Field(None, alias="Ethnicity/Style")
    field: Optional[str] = Field(None, description="Primary domain like Tech/Lifestyle")
    typical_content: Optional[str] = Field(None, alias="Typical Content")
    mood_palette: Optional[str] = Field(None, alias="Mood Palette (Common → Often → Sometimes)")
    body_type: Optional[str] = Field(None, alias="Body Type")
    visual_aesthetic: Optional[str] = Field(None, alias="Visual Aesthetic")
    hook_strategy: Optional[str] = Field(None, alias="Man Hook Strategy")
    notes: Optional[str] = Field(None, description="Misc fields or trailing columns")

    # Extended authenticity fields
    special_hobby: Optional[str] = Field(None, alias="Special Hobby")
    signature_gadget: Optional[str] = Field(None, alias="Signature Gadget")
    authenticity_props: Optional[str] = Field(None, alias="Authenticity Props")
    authenticity_backgrounds: Optional[str] = Field(None, alias="Authenticity Backgrounds")
    makeup_style: Optional[str] = Field(None, alias="Makeup Style")
    imperfections: Optional[str] = Field(None, alias="Imperfections")
    everyday_content_60: Optional[str] = Field(None, alias="60% Everyday Content")
    lifestyle_variety_30: Optional[str] = Field(None, alias="30% Lifestyle Variety")
    trending_themes_10: Optional[str] = Field(None, alias="10% Trending Themes")

    @staticmethod
    def cleaned_name(raw: str) -> str:
        # Take portion before 'Ref:' and strip whitespace/newlines
        head = raw.split("Ref:", 1)[0].strip()
        # Collapse multi-line into single line
        return " ".join(head.split())

