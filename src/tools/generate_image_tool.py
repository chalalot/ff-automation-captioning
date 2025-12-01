"""
Image Generation Tool for Marketing Campaign Agents

Provides marketing-focused image generation capabilities using ComfyUI API.
Integrates with the agent toolkit system to provide specialized functions for:
- Product showcase images
- Social media visuals
- Lifestyle photography
- Brand hero images

Features:
- Marketing prompt templates
- Brand-aware generation
- Platform optimization
- Async support for agent workflows
"""

import logging
import asyncio
from typing import Optional, Dict, Any, Literal, Union

from src.third_parties.comfyui_client import ComfyUIClient, get_client, create_marketing_prompt, ComfyUIError
from utils.constants import DEFAULT_NEGATIVE_PROMPT

# Set up logging
logger = logging.getLogger(__name__)

# Platform-specific optimization settings
PLATFORM_SPECS = {
    "instagram": {
        "aspect_ratio": "square",
        "style_notes": "vibrant, high contrast, mobile-optimized",
        "dimensions": "1080x1080"
    },
    "facebook": {
        "aspect_ratio": "landscape",
        "style_notes": "engaging, shareable, social",
        "dimensions": "1200x630"
    },
    "linkedin": {
        "aspect_ratio": "landscape",
        "style_notes": "professional, business-focused, clean",
        "dimensions": "1200x627"
    },
    "twitter": {
        "aspect_ratio": "landscape",
        "style_notes": "attention-grabbing, concise visual message",
        "dimensions": "1200x675"
    },
    "pinterest": {
        "aspect_ratio": "vertical",
        "style_notes": "aspirational, lifestyle-focused, rich details",
        "dimensions": "1000x1500"
    }
}


async def generate_marketing_image(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    style: str = "professional",
    product_name: str = "general_product",
    kol_persona: str = "general_influencer",
    upload_to_gcs: bool = False,  # Use ComfyUI URLs directly instead of GCS
    run_id: Optional[str] = None,
    workflow_name: Optional[str] = None,
    lora_name: Optional[str] = None
) -> Union[Dict[str, Any], str]:
    """
    Generate a marketing image with custom prompt and campaign organization.

    Args:
        prompt: Image description
        negative_prompt: What to avoid in the image
        style: Visual style (professional, casual, artistic, etc.)
        product_name: Product being marketed (for GCS organization)
        kol_persona: KOL/persona type (for GCS organization)
        upload_to_gcs: Whether to upload to GCS storage (default False - uses ComfyUI URLs)
        run_id: Optional explicit run ID for campaign grouping
        workflow_name: Name of the ComfyUI workflow to use (optional)
        lora_name: LoRA model name to use (optional)

    Returns:
        Dict with 'url', 'bytes', 'gcs_uploaded' keys on success
        OR string starting with 'Error:' if generation failed
    """
    logger.info("=" * 80)
    logger.info("📸 MARKETING IMAGE GENERATION - START")
    logger.info("=" * 80)
    logger.info(f"📝 Prompt: {prompt[:150]}{'...' if len(prompt) > 150 else ''}")
    logger.info(f"🎨 Style: {style}")
    logger.info(f"📦 Product: {product_name}")
    logger.info(f"👤 KOL Persona: {kol_persona}")
    logger.info(f"📋 Workflow: {workflow_name if workflow_name else 'NOT SPECIFIED'}")
    logger.info(f"🎭 LoRA: {lora_name if lora_name else 'NOT SPECIFIED'}")
    logger.info(f"☁️  Upload to GCS: {upload_to_gcs}")
    logger.info(f"🔑 Run ID: {run_id if run_id else 'AUTO-GENERATE'}")
    logger.info("=" * 80)

    try:
        client = get_client()

        # Enhance prompt with marketing-specific elements
        enhanced_prompt = f"{prompt}, {style} style, high quality, marketing photography"

        generation_result = await client.generate_and_wait(
            positive_prompt=enhanced_prompt,
            negative_prompt=negative_prompt,
            product_name=product_name,
            kol_persona=kol_persona,
            image_type="marketing",
            upload_to_gcs=upload_to_gcs,
            run_id=run_id,
            workflow_name=workflow_name,
            lora_name=lora_name
        )

        public_url = generation_result.get("public_url", generation_result.get("execution_id", "unknown"))

        logger.info("=" * 80)
        logger.info("✅ MARKETING IMAGE GENERATION - SUCCESS")
        logger.info("=" * 80)
        logger.info(f"🔗 Public URL: {public_url}")
        logger.info(f"📦 Image Size: {len(generation_result.get('image_bytes', [])) if generation_result.get('image_bytes') else 0} bytes")
        logger.info(f"☁️  GCS Upload: {'YES' if generation_result.get('gcs_uploaded') else 'NO'}")
        if generation_result.get("gcs_uploaded"):
            logger.info(f"📂 GCS Path: {generation_result.get('gcs_path')}")
        logger.info("=" * 80)

        # Return dict with both URL and bytes to avoid re-downloading
        return {
            "url": public_url,
            "bytes": generation_result.get("image_bytes"),
            "gcs_uploaded": generation_result.get("gcs_uploaded", False)
        }

    except ComfyUIError as e:
        logger.error("=" * 80)
        logger.error(f"❌ MARKETING IMAGE GENERATION - COMFYUI ERROR")
        logger.error(f"Error: {e}")
        logger.error("=" * 80)
        return f"Error: {str(e)}"
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ MARKETING IMAGE GENERATION - UNEXPECTED ERROR")
        logger.error(f"Error: {e}")
        logger.error(f"Type: {type(e).__name__}")
        logger.error("=" * 80)
        return f"Error: Failed to generate image - {str(e)}"


async def generate_product_showcase(
    product_name: str,
    product_description: str,
    style: str = "professional",
    background: str = "clean white",
    additional_details: str = "",
    kol_persona: str = "product_specialist",
    upload_to_gcs: bool = False,  # Use ComfyUI URLs directly instead of GCS
    run_id: Optional[str] = None
) -> str:
    """
    Generate product showcase image optimized for e-commerce and marketing.

    Args:
        product_name: Name of the product
        product_description: Detailed description of the product
        style: Photography style (professional, lifestyle, artistic)
        background: Background setting
        additional_details: Extra details for the prompt
        kol_persona: KOL/persona type (for GCS organization)
        upload_to_gcs: Whether to upload to GCS storage (default False - uses ComfyUI URLs)
        run_id: Optional explicit run ID for campaign grouping

    Returns:
        Public URL of generated image or error message
    """
    try:
        client = get_client()

        # Create marketing prompt using template
        prompt = create_marketing_prompt(
            "product_showcase",
            product=f"{product_name} - {product_description}",
            style=style,
            additional_details=f"{background} background, {additional_details}"
        )

        negative_prompt = DEFAULT_NEGATIVE_PROMPT

        generation_result = await client.generate_and_wait(
            positive_prompt=prompt,
            negative_prompt=negative_prompt,
            product_name=product_name,
            kol_persona=kol_persona,
            image_type="product_showcase",
            upload_to_gcs=upload_to_gcs,
            run_id=run_id
        )

        public_url = generation_result.get("public_url", generation_result.get("execution_id", "unknown"))

        if generation_result.get("gcs_uploaded"):
            logger.info(f"Product showcase uploaded to GCS: {generation_result.get('gcs_path')}")
        else:
            logger.info(f"Product showcase generated (no GCS upload): {public_url}")

        return public_url

    except Exception as e:
        logger.error(f"Error generating product showcase for {product_name}: {e}")
        return f"Error: Failed to generate product showcase - {str(e)}"


async def generate_social_media_visual(
    subject: str,
    platform: Literal["instagram", "facebook", "linkedin", "twitter", "pinterest"] = "instagram",
    mood: str = "energetic",
    brand_colors: str = "",
    additional_details: str = "",
) -> str:
    """
    Generate social media visual optimized for specific platform.

    Args:
        subject: Main subject/content of the image
        platform: Target social media platform
        mood: Desired mood/feeling (energetic, calm, professional, fun)
        brand_colors: Brand color palette to incorporate
        additional_details: Extra details for the prompt
    Returns:
        Remote URL of generated image or execution_id fallback
    """
    try:
        client = get_client()

        # Get platform-specific optimizations
        platform_spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["instagram"])

        # Create optimized prompt
        style_details = f"{platform_spec['style_notes']}, {platform_spec['aspect_ratio']} composition"
        if brand_colors:
            style_details += f", {brand_colors} color palette"
        if additional_details:
            style_details += f", {additional_details}"

        prompt = create_marketing_prompt(
            "social_media",
            subject=subject,
            platform=platform,
            mood=mood,
            additional_details=style_details
        )

        negative_prompt = DEFAULT_NEGATIVE_PROMPT

        generation_result = await client.generate_and_wait(
            positive_prompt=prompt,
            negative_prompt=negative_prompt,
        )

        result_url = (
            generation_result.get("remote_url")
            or generation_result.get("execution_id")
        )
        logger.info(f"Social media visual generated for {platform}: {result_url}")

        return result_url

    except Exception as e:
        logger.error(f"Error generating social media visual for {platform}: {e}")
        return f"Error: Failed to generate social media visual - {str(e)}"


async def generate_lifestyle_image(
    product_or_service: str,
    setting: str,
    demographic: str = "young professionals",
    activity: str = "",
    additional_details: str = "",
) -> str:
    """
    Generate lifestyle image showing product/service in real-world context.

    Args:
        product_or_service: Product or service being showcased
        setting: Environment/location (home, office, outdoors, etc.)
        demographic: Target demographic description
        activity: What people are doing in the scene
        additional_details: Extra details for the prompt
    Returns:
        Remote URL of generated image or execution_id fallback
    """
    try:
        client = get_client()

        # Build lifestyle prompt details
        lifestyle_details = f"in {setting}"
        if activity:
            lifestyle_details += f", {activity}"
        if additional_details:
            lifestyle_details += f", {additional_details}"

        prompt = create_marketing_prompt(
            "lifestyle",
            product=product_or_service,
            demographic=demographic,
            additional_details=lifestyle_details
        )

        negative_prompt = DEFAULT_NEGATIVE_PROMPT

        generation_result = await client.generate_and_wait(
            positive_prompt=prompt,
            negative_prompt=negative_prompt,
        )

        result_url = (
            generation_result.get("remote_url")
            or generation_result.get("execution_id")
        )
        logger.info(f"Lifestyle image generated for {product_or_service}: {result_url}")

        return result_url

    except Exception as e:
        logger.error(f"Error generating lifestyle image: {e}")
        return f"Error: Failed to generate lifestyle image - {str(e)}"


async def generate_brand_hero_image(
    brand_name: str,
    industry: str,
    brand_values: str = "",
    visual_style: str = "modern minimalist",
    additional_details: str = "",
) -> str:
    """
    Generate hero image for brand marketing and website headers.

    Args:
        brand_name: Name of the brand
        industry: Industry/sector the brand operates in
        brand_values: Key brand values and personality
        visual_style: Desired visual aesthetic
        additional_details: Extra details for the prompt
    Returns:
        Remote URL of generated image or execution_id fallback
    """
    try:
        client = get_client()

        # Build brand-focused prompt details
        brand_details = f"{visual_style} aesthetic"
        if brand_values:
            brand_details += f", reflecting {brand_values}"
        if additional_details:
            brand_details += f", {additional_details}"

        prompt = create_marketing_prompt(
            "brand_hero",
            brand=brand_name,
            industry=industry,
            additional_details=brand_details
        )

        negative_prompt = DEFAULT_NEGATIVE_PROMPT

        generation_result = await client.generate_and_wait(
            positive_prompt=prompt,
            negative_prompt=negative_prompt,
        )

        result_url = (
            generation_result.get("remote_url")
            or generation_result.get("execution_id")
        )
        logger.info(f"Brand hero image generated for {brand_name}: {result_url}")

        return result_url

    except Exception as e:
        logger.error(f"Error generating brand hero image: {e}")
        return f"Error: Failed to generate brand hero image - {str(e)}"


# Synchronous wrappers for agent compatibility
def generate_marketing_image_sync(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    style: str = "professional",
    product_name: str = "general_product",
    kol_persona: str = "general_influencer",
    upload_to_gcs: bool = False,  # Use ComfyUI URLs directly instead of GCS
    run_id: Optional[str] = None,
    workflow_name: Optional[str] = None,
    lora_name: Optional[str] = None
) -> Union[Dict[str, Any], str]:
    """
    Synchronous wrapper for generate_marketing_image.

    Returns:
        Dict with keys: 'url', 'bytes', 'gcs_uploaded' on success
        OR string starting with 'Error:' if generation failed
    """
    logger.info("🔧 GENERATE_MARKETING_IMAGE_SYNC DEBUG:")
    logger.info(f"   prompt: {prompt[:50]}...")
    logger.info(f"   kol_persona: '{kol_persona}'")
    logger.info(f"   product_name: '{product_name}'")
    logger.info(f"   upload_to_gcs: {upload_to_gcs}")
    logger.info("=" * 50)
    
    return asyncio.run(generate_marketing_image(
        prompt, negative_prompt, style, product_name, kol_persona, upload_to_gcs, run_id,
        workflow_name, lora_name
    ))


def generate_product_showcase_sync(
    product_name: str,
    product_description: str,
    style: str = "professional",
    background: str = "clean white",
    additional_details: str = "",
    kol_persona: str = "product_specialist",
    upload_to_gcs: bool = False,  # Use ComfyUI URLs directly instead of GCS
    run_id: Optional[str] = None
) -> str:
    """Synchronous wrapper for generate_product_showcase."""
    return asyncio.run(generate_product_showcase(
        product_name, product_description, style, background, additional_details, kol_persona, upload_to_gcs, run_id
    ))


def generate_social_media_visual_sync(
    subject: str,
    platform: Literal["instagram", "facebook", "linkedin", "twitter", "pinterest"] = "instagram",
    mood: str = "energetic",
    brand_colors: str = "",
    additional_details: str = "",
) -> str:
    """Synchronous wrapper for generate_social_media_visual."""
    return asyncio.run(generate_social_media_visual(
        subject, platform, mood, brand_colors, additional_details
    ))


def generate_lifestyle_image_sync(
    product_or_service: str,
    setting: str,
    demographic: str = "young professionals",
    activity: str = "",
    additional_details: str = "",
) -> str:
    """Synchronous wrapper for generate_lifestyle_image."""
    return asyncio.run(generate_lifestyle_image(
        product_or_service, setting, demographic, activity, additional_details
    ))


def generate_brand_hero_image_sync(
    brand_name: str,
    industry: str,
    brand_values: str = "",
    visual_style: str = "modern minimalist",
    additional_details: str = "",
) -> str:
    """Synchronous wrapper for generate_brand_hero_image."""
    return asyncio.run(generate_brand_hero_image(
        brand_name, industry, brand_values, visual_style, additional_details
    ))
