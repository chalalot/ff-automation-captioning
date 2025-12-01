#!/usr/bin/env python3
"""
Validation Models for Mood-Constrained Content

Provides strict validation against mood-based keyword constraints.
"""

from __future__ import annotations
import re
from typing import List, Optional, Set
from pydantic import BaseModel, Field

from .mood_parser import MoodProfile, PersonaMoodCollection


class ValidationResult(BaseModel):
    """Result of mood constraint validation."""
    is_compliant: bool = Field(..., description="True if content strictly follows mood constraints")
    violation_reason: str = Field(default="", description="Specific reason for rejection if not compliant")
    violations_found: List[str] = Field(default_factory=list, description="List of specific violations")
    compliant_content: Optional[str] = Field(default=None, description="Original content if compliant")


class StrictMoodValidator:
    """
    Validates content against mood keyword constraints with zero tolerance.
    """
    
    def __init__(self):
        # Common words that are allowed but not part of mood keywords
        self.allowed_generic_words = {
            # Articles, pronouns, basic connectors
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'from', 'as', 'is', 'was', 'are', 'were', 'be', 'being', 'been', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
            'her', 'his', 'she', 'he', 'it', 'they', 'them', 'their', 'this', 'that', 'these', 'those',
            'very', 'quite', 'really', 'some', 'any', 'all', 'both', 'each', 'every', 'either', 'neither',
            'while', 'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over',
            'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how',
            'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
            'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'just', 'now',
            
            # ADDED: Common action/connector words needed for natural sentences
            'using', 'wearing', 'with', 'holding', 'near', 'next', 'beside', 'against', 'through',
            'around', 'across', 'into', 'onto', 'within', 'without', 'upon', 'beneath', 'between',
            'among', 'along', 'toward', 'towards', 'underneath', 'inside', 'outside', 'behind',
            'beside', 'beyond', 'throughout', 'during', 'amid', 'amidst', 'via', 'per', 'plus',
            'minus', 'including', 'excluding', 'regarding', 'concerning', 'despite', 'except',
            
            # Common descriptive connectors
            'looking', 'showing', 'having', 'getting', 'making', 'taking', 'giving', 'coming',
            'going', 'being', 'feeling', 'seeming', 'appearing', 'becoming', 'remaining', 'staying'
        }
    
    def extract_meaningful_words(self, text: str) -> Set[str]:
        """
        Extract meaningful words from text, filtering out common words.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Set of meaningful words in lowercase
        """
        # Remove punctuation and convert to lowercase
        cleaned_text = re.sub(r'[^\w\s-]', ' ', text.lower())
        
        # Split into words and filter
        words = cleaned_text.split()
        meaningful_words = set()
        
        for word in words:
            word = word.strip('-').strip()
            # Include words that are longer than 2 chars and not in generic words
            if len(word) > 2 and word not in self.allowed_generic_words:
                meaningful_words.add(word)
        
        return meaningful_words
    
    def normalize_keyword_for_matching(self, keyword: str) -> Set[str]:
        """
        Normalize a keyword phrase for flexible matching.
        
        Args:
            keyword: Original keyword (e.g., "lounging on bed")
            
        Returns:
            Set of normalized forms for matching
        """
        forms = set()
        
        # Original form
        forms.add(keyword.lower())
        
        # Without parentheses
        no_parens = re.sub(r'\([^)]*\)', '', keyword).strip()
        if no_parens:
            forms.add(no_parens.lower())
        
        # Individual words (for partial matching)
        words = self.extract_meaningful_words(keyword)
        forms.update(words)
        
        # Handle compound keywords
        if ' ' in keyword:
            # Add hyphenated version
            forms.add(keyword.replace(' ', '-').lower())
            
            # Add key parts (e.g., "sitting on a balcony" -> ["sitting", "balcony"])
            key_words = [w for w in words if w not in self.allowed_generic_words]
            forms.update(key_words)
        
        return forms
    
    def validate_against_mood(self, content: str, mood: MoodProfile) -> ValidationResult:
        """
        Validate content against a specific mood's constraints.
        
        Args:
            content: Text content to validate
            mood: MoodProfile containing allowed keywords
            
        Returns:
            ValidationResult with compliance status
        """
        if not content or not mood:
            return ValidationResult(
                is_compliant=False,
                violation_reason="Empty content or missing mood",
                violations_found=["Missing content or mood data"]
            )
        
        # Get all allowed keywords from the mood
        all_allowed_keywords = mood.get_all_keywords()
        
        # Create normalized forms of allowed keywords
        allowed_forms = set()
        for keyword in all_allowed_keywords:
            forms = self.normalize_keyword_for_matching(keyword)
            allowed_forms.update(forms)
        
        # Extract meaningful words from content
        content_words = self.extract_meaningful_words(content)
        
        # Find violations (meaningful words not in allowed forms)
        violations = []
        for word in content_words:
            # Check if this word appears in any allowed keyword form
            word_found = False
            for allowed_form in allowed_forms:
                if word in allowed_form or allowed_form in word:
                    word_found = True
                    break
            
            if not word_found:
                violations.append(f"'{word}' not found in mood keywords")
        
        # Determine compliance
        is_compliant = len(violations) == 0
        
        return ValidationResult(
            is_compliant=is_compliant,
            violation_reason=f"Found {len(violations)} unauthorized words" if violations else "",
            violations_found=violations[:10],  # Limit to first 10 violations for readability
            compliant_content=content if is_compliant else None
        )
    
    def validate_against_mood_collection(self, content: str, mood_collection: PersonaMoodCollection, target_mood_name: str = None) -> ValidationResult:
        """
        Validate content against a specific mood from a collection.
        
        Args:
            content: Text content to validate
            mood_collection: PersonaMoodCollection containing all moods
            target_mood_name: Name of specific mood to validate against (optional)
            
        Returns:
            ValidationResult with compliance status
        """
        if not mood_collection.moods:
            return ValidationResult(
                is_compliant=False,
                violation_reason="No moods available in collection",
                violations_found=["Empty mood collection"]
            )
        
        # If specific mood requested, find it
        if target_mood_name:
            target_mood = None
            for mood in mood_collection.moods:
                if mood.mood_name == target_mood_name or f"Mood {mood.mood_number}" in target_mood_name:
                    target_mood = mood
                    break
            
            if target_mood:
                return self.validate_against_mood(content, target_mood)
            else:
                return ValidationResult(
                    is_compliant=False,
                    violation_reason=f"Target mood '{target_mood_name}' not found",
                    violations_found=[f"Mood '{target_mood_name}' does not exist"]
                )
        
        # If no specific mood, try to validate against any mood (pick best match)
        best_result = None
        fewest_violations = float('inf')
        
        for mood in mood_collection.moods:
            result = self.validate_against_mood(content, mood)
            if result.is_compliant:
                return result  # Found compliant mood
            elif len(result.violations_found) < fewest_violations:
                best_result = result
                fewest_violations = len(result.violations_found)
        
        # Return best result if none were compliant
        return best_result or ValidationResult(
            is_compliant=False,
            violation_reason="Content does not match any available mood",
            violations_found=["No mood match found"]
        )


def create_mood_validator_agent():
    """
    Create a CrewAI agent for mood validation.
    This agent acts as a quality gate for content compliance.
    """
    from crewai import Agent
    
    return Agent(
        role='Mood Compliance Validator',
        goal='''
            Validate that content strictly follows the assigned mood's keyword constraints.
            Reject any content that uses words outside the allowed keyword lists.
            You are the quality gate - be extremely strict.
        ''',
        backstory='''
            You are a meticulous quality control agent for mood-based content creation.
            Your only job is to check if generated content uses ONLY the exact keywords
            from the assigned mood profile. You have zero tolerance for creative deviations
            or words that aren't in the approved lists. You are not creative - you are
            a rule enforcer.
        ''',
        verbose=True,
        allow_delegation=False
    )


# Test function
def test_validator():
    """Test the validator with sample data."""
    from .mood_parser import parse_persona_moods
    
    sample_mood_text = """
Mood 1: Sunlit Interior & Candid Home Life
This mood captures the persona in relaxed, intimate, and unposed moments indoors or on a private balcony.

Pose Keywords: lounging on bed, sitting on a balcony, leaning against a wall
Lighting Keywords: soft window light, direct sunlight beam
Clothes Keywords: simple cotton tank top, loungewear
Expression Keywords: calm, serene, content
Props & Setting Keywords: white bed linens, phone, headphones
"""
    
    mood_collection = parse_persona_moods(sample_mood_text, "Test")
    validator = StrictMoodValidator()
    
    # Test compliant content
    compliant_content = "lounging on bed wearing simple cotton tank top with soft window light"
    result1 = validator.validate_against_mood_collection(compliant_content, mood_collection)
    print(f"Compliant test: {result1.is_compliant}")
    
    # Test non-compliant content
    non_compliant_content = "standing in the kitchen wearing a formal dress with harsh neon lighting"
    result2 = validator.validate_against_mood_collection(non_compliant_content, mood_collection)
    print(f"Non-compliant test: {result2.is_compliant}")
    print(f"Violations: {result2.violations_found}")


if __name__ == "__main__":
    test_validator()
