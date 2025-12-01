from typing import Dict, List

# RecurPost CSV export configuration
RECURPOST_FIELD_ORDER: List[str] = [
    "Original Message",
    "Facebook Message",
    "Twitter Message",
    "Linkedin Message",
    "Instagram Message",
    "GoogleBusinessProfile Message/Offer Detail",
    "Pinterest Message",
    "YouTube Message",
    "Tiktok Message",
    "Thread Message",
    "Bluesky Message",
    "Post URL",
    "Facebook Post Type",
    "GBP CTA",
    "GBP CTA Link/GBP Offer Link",
    "Pinterest Title",
    "Pinterest Destination Link",
    "YouTube Title",
    "YouTube Category",
    "YouTube Privacy Status",
    "YouTube Tags",
    "YouTube Thumbnail",
    "Tiktok Privacy Status",
    "Original First Comment",
    "Facebook First Comment",
    "Linkedin First Comment",
    "Instagram First Comment",
    "Instagram Post Type",
    "GBP Offer Title",
    "GBP Offer Start Date",
    "GBP Offer End Date",
    "GBP Offer Coupon Code",
    "GBP Offer Terms",
    "Linkedin Document",
    "Linkedin Document Title",
    "Image URL 1",
    "Image URL 2",
    "Image URL 3",
    "Image URL 4",
    "Image URL 5",
    "Image URL 6",
    "Image URL 7",
    "Image URL 8",
    "Image URL 9",
    "Image URL 10",
    "Image URL 11",
    "Image URL 12",
    "Image URL 13",
    "Image URL 14",
    "Image URL 15",
    "Video Url",
]

PLATFORM_TO_RECURPOST_FIELD: Dict[str, str] = {
    "generic": "Original Message",
    "linkedin": "Linkedin Message",
    "linkedi": "Linkedin Message",  # defensive typo guard
    "facebook": "Facebook Message",
    "meta": "Facebook Message",
    "fb": "Facebook Message",
    "x": "Twitter Message",
    "twitter": "Twitter Message",
    "threads": "Thread Message",
    "thread": "Thread Message",
    "instagram": "Instagram Message",
    "ig": "Instagram Message",
    "google_business_profile": "GoogleBusinessProfile Message/Offer Detail",
    "google business profile": "GoogleBusinessProfile Message/Offer Detail",
    "gbp": "GoogleBusinessProfile Message/Offer Detail",
    "google-my-business": "GoogleBusinessProfile Message/Offer Detail",
    "pinterest": "Pinterest Message",
    "pin": "Pinterest Message",
    "youtube": "YouTube Message",
    "yt": "YouTube Message",
    "tiktok": "Tiktok Message",
    "tik_tok": "Tiktok Message",
    "bluesky": "Bluesky Message",
}

# Image Generation - Default Negative Prompt
DEFAULT_NEGATIVE_PROMPT = """ 色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走, censored, sunburnt skin, rashy skin, red cheeks, pouty face, duckbil face"""

# Realistic Lighting Keywords - Always included in prompts for natural-looking images
REALISTIC_LIGHTING_KEYWORDS = [
    "cinematic soft light", "realistic texture", "no plastic smoothness", 
    "fine film grain", "50mm lens", "natural daylight tone"
]

# Technical Quality Keywords - Ensures high-quality realistic output
TECHNICAL_QUALITY_KEYWORDS = [
    "high fidelity", "realistic fabric grain", "natural skin pores",
    "soft shadow falloff", "eye-level composition", "cinematic softness",
    "professional photography", "natural imperfections", "authentic moment",
    "organic textures", "subtle color grading", "natural depth of field"
]

# Camera and Shot Keywords
CAMERA_SHOT_KEYWORDS = {
    "medium_full": ["medium-full shot", "3/4 body shot", "waist up framing"],
    "medium": ["medium shot", "bust shot", "chest up framing"],
    "close_up": ["close-up shot", "head and shoulders", "portrait framing"],
    "full_body": ["full body shot", "complete figure", "head to toe framing"]
}
