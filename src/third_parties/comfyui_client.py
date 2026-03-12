"""
ComfyUI API Client for Image Generation

Provides async image generation capabilities using ComfyUI API including:
- Image generation with custom prompts
- Status checking and polling
- Image download and S3 upload
- Robust error handling and retry logic
- Marketing-focused prompt templates

Features:
- Async support for non-blocking operations
- Configurable timeout and polling parameters
- Error handling with exponential backoff
- S3 integration for image storage
- Marketing campaign optimization
"""

import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import httpx
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "httpx package is required. Install with: pip install httpx"
    ) from exc

from src.config import GlobalConfig
from src.utils.image_filters import apply_stable_film_look
from utils.constants import DEFAULT_NEGATIVE_PROMPT
from .comfyui_queue_manager import execute_with_queue

# Set up logging
logger = logging.getLogger(__name__)

# Rate limiting configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 2.0  # Base delay in seconds
DEFAULT_MAX_DELAY = 60.0  # Maximum delay in seconds
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_JITTER_RANGE = 0.1  # ±10% jitter to prevent thundering herd

# ComfyUI configuration from GlobalConfig
CLOUD_COMFY_API_URL = GlobalConfig.CLOUD_COMFY_API_URL
COMFYUI_API_KEY = GlobalConfig.COMFYUI_API_KEY
COMFYUI_API_TIMEOUT = GlobalConfig.COMFYUI_API_TIMEOUT
COMFYUI_POLL_INTERVAL = GlobalConfig.COMFYUI_POLL_INTERVAL
COMFYUI_MAX_POLL_TIME = GlobalConfig.COMFYUI_MAX_POLL_TIME
COMFYUI_MAX_RETRIES = GlobalConfig.COMFYUI_MAX_RETRIES

# Persona mappings
PERSONA_LORA_MAPPING_TURBO = {
    "Jennie": "z-image-persona/jennie_turbo_v3.safetensors",
    "Sephera": "z-image-persona/sephera_turbo_v5.safetensors",
    "Nya": "z-image-persona/nya-z-image-turbo-v1.safetensors",
    "Emi": "z-image-persona/emi_turbo_v2.safetensors",
    "Roxie": "z-image-persona/roxie_v3.safetensors"
}


def _calculate_backoff_delay(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
    jitter_range: float = DEFAULT_JITTER_RANGE
) -> float:
    """Calculate exponential backoff delay with jitter."""
    delay = base_delay * (multiplier ** attempt)
    delay = min(delay, max_delay)

    # Add jitter to prevent thundering herd
    jitter = delay * jitter_range * (2 * random.random() - 1)
    delay += jitter

    return max(0, delay)


class ComfyUIError(Exception):
    """Base exception for ComfyUI API errors."""
    pass


class ComfyUITimeoutError(ComfyUIError):
    """Raised when image generation times out."""
    pass


class ComfyUIAPIError(ComfyUIError):
    """Raised when ComfyUI API returns an error."""
    pass


class ComfyUIConfigError(ComfyUIError):
    """Raised when ComfyUI configuration is invalid (e.g., bad URL)."""
    pass

class ComfyUIClient:
    """
    Async client for ComfyUI image generation API via Comfy Cloud.

    Handles the complete workflow:
    1. Submit generation request using local workflow.json
    2. Poll for completion status
    3. Download generated image
    4. Upload to GCS
    """

    def __init__(
        self,
        cloud_api_url: str = CLOUD_COMFY_API_URL,
        api_key: Optional[str] = COMFYUI_API_KEY,
        timeout: int = COMFYUI_API_TIMEOUT,
        poll_interval: int = COMFYUI_POLL_INTERVAL,
        max_poll_time: int = COMFYUI_MAX_POLL_TIME,
        max_retries: int = COMFYUI_MAX_RETRIES
    ):
        if not cloud_api_url or not str(cloud_api_url).strip():
            raise ComfyUIConfigError(
                "CLOUD_COMFY_API_URL is not set."
            )

        self.cloud_api_url = cloud_api_url.rstrip('/')
        self.api_key = api_key.strip() if api_key else None
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_time = max_poll_time
        self.max_retries = max_retries

    async def get_queue(self) -> Dict[str, Any]:
        """
        Fetch the current queue status from ComfyUI API.
        Returns the queue running and pending lists.
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")
            
        url = f"{self.cloud_api_url}/queue"
        
        logger.info(f"🔵 ComfyUI Cloud Request: GET {url}")
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Get queue HTTP Error ({e.response.status_code}): {e.response.text}")
            raise ComfyUIAPIError(f"Get queue failed ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Failed to get queue: {e}")
            raise ComfyUIAPIError(f"Get queue failed: {e}")

    async def queue_prompt(self, prompt_workflow: Dict[str, Any]) -> str:
        """
        Queue a prompt to the Cloud ComfyUI API (Standard /prompt endpoint).
        """
        if not self.cloud_api_url:
            raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")
            
        url = f"{self.cloud_api_url}/prompt"
        
        # Comfy Cloud format
        payload = {
            "prompt": prompt_workflow
        }
        
        logger.info(f"🔵 ComfyUI Cloud Request: POST {url}")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            # Comfy Cloud uses X-API-Key or Authorization
            headers["X-API-Key"] = self.api_key
            
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                logger.info(f"✅ Prompt queued: {data}")
                return data.get("prompt_id")
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Queue prompt HTTP Error ({e.response.status_code}): {e.response.text}")
            raise ComfyUIAPIError(f"Queue prompt failed ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Failed to queue prompt: {e}")
            raise ComfyUIAPIError(f"Queue prompt failed: {e}")

    async def generate_image(
        self,
        positive_prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        workflow_type: str = "turbo",
        lora_name: Optional[str] = None,
        kol_persona: Optional[str] = None,
        strength_model: Optional[str] = None,
        seed_strategy: str = "random",
        base_seed: int = 0,
        width: str = "1024",
        height: str = "1600",
        **kwargs
    ) -> str:
        """
        Start image generation via Comfy Cloud API using workflow.json.
        """
        logger.info("=" * 80)
        logger.info(f"🎨 COMFYUI IMAGE GENERATION REQUEST (CLOUD API)")
        logger.info("=" * 80)

        cleaned_prompt = re.sub(r'<lora:[^>]+>,\s*Instagirl,?\s*', '', positive_prompt, flags=re.IGNORECASE)
        
        logger.info(f"📝 Original Prompt: {positive_prompt[:100]}...")
        logger.info(f"📝 Cleaned Prompt: {cleaned_prompt[:200]}{'...' if len(cleaned_prompt) > 200 else ''}")
        
        # Determine Turbo LoRA
        final_lora = "z-image-persona/emi_turbo_v2.safetensors" # default
        
        if lora_name:
            final_lora = lora_name
            logger.info(f"🎭 LoRA Override: {final_lora}")
        elif kol_persona:
            for persona_key in PERSONA_LORA_MAPPING_TURBO.keys():
                if persona_key.lower() == kol_persona.lower():
                    final_lora = PERSONA_LORA_MAPPING_TURBO[persona_key]
                    logger.info(f"🎭 LoRA Mapped: {final_lora}")
                    break
        
        # Load the workflow.json file
        workflow_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workflow.json")
        try:
            with open(workflow_path, 'r') as f:
                workflow_data = json.load(f)
        except Exception as e:
            logger.error(f"❌ Failed to load workflow.json from {workflow_path}: {e}")
            raise ComfyUIAPIError(f"Failed to load workflow.json: {e}")
            
        # Inject overrides into workflow
        if "45" in workflow_data and "inputs" in workflow_data["45"]:
            workflow_data["45"]["inputs"]["text"] = cleaned_prompt
        if "53" in workflow_data and "inputs" in workflow_data["53"]:
            workflow_data["53"]["inputs"]["lora_name"] = final_lora
            workflow_data["53"]["inputs"]["strength_model"] = float(strength_model) if strength_model is not None else 1.0
        if "41" in workflow_data and "inputs" in workflow_data["41"]:
            workflow_data["41"]["inputs"]["width"] = int(width)
            workflow_data["41"]["inputs"]["height"] = int(height)
        if "44" in workflow_data and "inputs" in workflow_data["44"]:
            if seed_strategy == "random":
                workflow_data["44"]["inputs"]["seed"] = random.randint(1, 1000000000000000)
            else:
                workflow_data["44"]["inputs"]["seed"] = int(base_seed)
                
        return await self.queue_prompt(workflow_data)

    async def check_status(self, execution_id: str) -> Dict[str, Any]:
        """
        Check the status of image generation.
        """
        async def _status_request():
            if not self.cloud_api_url:
                raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")
            
            # Cloud API first uses /job/{prompt_id}/status to check if complete
            status_url = f"{self.cloud_api_url}/job/{execution_id}/status"
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    # 1. Check job status
                    status_response = await client.get(status_url, headers=headers)
                    status_response.raise_for_status()
                    job_status = status_response.json().get("status", "").lower()
                    
                    if job_status in ["success", "completed"]:
                        # 2. If completed, get history to find output filename
                        history_url = f"{self.cloud_api_url}/history_v2/{execution_id}"
                        history_response = await client.get(history_url, headers=headers)
                        history_response.raise_for_status()
                        history_data = history_response.json()
                        
                        outputs = history_data.get("outputs", {})
                        output_images = []
                        
                        # Flatten outputs
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                paths = []
                                for img in node_output["images"]:
                                    fname = img.get("filename")
                                    sub = img.get("subfolder", "")
                                    ftype = img.get("type", "output")
                                    # Construct path that we can download later
                                    paths.append(f"{sub}/{fname}?type={ftype}" if sub else f"{fname}?type={ftype}")
                                
                                output_images.append({node_id: paths})
                        
                        return {
                            "status": "completed",
                            "output_images": output_images,
                            "raw_history": history_data
                        }
                    
                    elif job_status in ["failed", "error"]:
                        return {
                            "status": "failed",
                            "error_message": status_response.text
                        }
                        
                    else:
                        # pending, running, etc.
                        return {"status": "running"}
                        
                except httpx.HTTPStatusError as e:
                    logger.error(f"Status check failed ({e.response.status_code}): {e.response.text}")
                    # In some APIs, if job hasn't started yet, it might 404. We'll assume running if 404 for now.
                    if e.response.status_code == 404:
                        return {"status": "running"}
                    raise

        try:
            # Queue status requests to prevent concurrent polling
            return await execute_with_queue(
                operation=_status_request,
                description=f"Status check for {execution_id}",
                timeout=30  # Shorter timeout for status checks
            )

        except Exception as e:
            logger.error(f"Failed to check status for {execution_id}: {e}")
            raise

    async def wait_for_completion(
        self,
        execution_id: str,
        poll_interval: Optional[int] = None,
        max_poll_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Poll for completion of image generation.

        Args:
            execution_id: ID from generate_image()
            poll_interval: Seconds between status checks
            max_poll_time: Maximum time to wait in seconds
            is_cloud: Whether to check status on Cloud API

        Returns:
            Final status data when completed
        """
        poll_interval = poll_interval or self.poll_interval
        max_poll_time = max_poll_time or self.max_poll_time

        start_time = time.time()

        while True:
            elapsed = time.time() - start_time

            if elapsed > max_poll_time:
                raise ComfyUITimeoutError(f"Generation timed out after {max_poll_time}s")

            try:
                status_data = await self.check_status(execution_id)
                status = status_data.get("status")

                logger.info(f"⏳ Status check [{elapsed:.0f}s elapsed]: {status}")

                if status == "completed":
                    logger.info("=" * 80)
                    logger.info(f"✅ IMAGE GENERATION COMPLETED")
                    logger.info("=" * 80)
                    logger.info(f"🔑 Execution ID: {execution_id}")
                    logger.info(f"⏱️  Total time elapsed: {elapsed:.1f}s")
                    logger.info(f"📊 Status Data: {json.dumps(status_data, indent=2)}")
                    logger.info("=" * 80)
                    return status_data
                elif status == "failed":
                    error_msg = status_data.get("error_message", "Unknown error")
                    raise ComfyUIAPIError(f"Generation failed: {error_msg}")
                elif status in ["queued", "running"]:
                    # Still in progress
                    logger.info(f"   Waiting... (status: {status}, {elapsed:.0f}s/{max_poll_time}s)")
                    await asyncio.sleep(poll_interval)
                    continue
                else:
                    logger.warning(f"Unknown status '{status}' for {execution_id}")
                    await asyncio.sleep(poll_interval)

            except ComfyUIError:
                raise
            except Exception as e:
                logger.error(f"Error while polling status: {e}")
                await asyncio.sleep(poll_interval)

    async def generate_and_wait(
        self,
        positive_prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        product_name: Optional[str] = None,
        kol_persona: Optional[str] = None,
        image_type: str = "marketing",
        upload_to_gcs: bool = True,
        run_id: Optional[str] = None,
        lora_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Complete image generation workflow: generate, wait, download, and optionally upload to GCS.
        """
        async def _execute_generation():
            execution_id = await self.generate_image(
                positive_prompt,
                negative_prompt,
                lora_name=lora_name,
                kol_persona=kol_persona,
                **kwargs
            )
            status_data = await self.wait_for_completion(execution_id)
            return execution_id, status_data

        # Use queue manager to ensure sequential processing
        description = f"Image generation for {kol_persona or 'unknown'} - {product_name or 'unknown'}"
        
        # Try to get current Celery task ID if available
        celery_task_id = None
        try:
            from celery import current_task
            if current_task and current_task.request.id:
                celery_task_id = current_task.request.id
        except ImportError:
            pass
        except AttributeError:
            pass
        except Exception:
            pass
        
        execution_id, status_data = await execute_with_queue(
            operation=_execute_generation,
            description=description,
            timeout=self.max_poll_time + 120,  # Add buffer time for queue waiting
            celery_task_id=celery_task_id
        )
        
        try:
            # Extract image path from output_images
            output_images = status_data.get("output_images", [])

            if not output_images:
                logger.error(f"❌ No output_images in status response for {execution_id}")
                raise ComfyUIAPIError(f"No output images available for execution {execution_id}")

            # Get first image path
            first_output = output_images[0]
            image_path = None
            for key, paths in first_output.items():
                if paths and len(paths) > 0:
                    image_path = paths[0]
                    break

            if not image_path:
                raise ComfyUIAPIError(f"No image path found in output_images for {execution_id}")

            logger.info(f"📁 Found image path: {image_path}")

            logger.info(f"📥 Attempting to download image for {execution_id}...")
            
            # Cloud API download via /view endpoint
            if not self.cloud_api_url:
                 raise ComfyUIConfigError("CLOUD_COMFY_API_URL is not set.")
            
            filename_part = image_path.split('?')[0]
            query_part = image_path.split('?')[1] if '?' in image_path else "type=output"
            
            view_url = f"{self.cloud_api_url}/view?filename={os.path.basename(filename_part)}&{query_part}"
            if '/' in filename_part:
                sub = os.path.dirname(filename_part)
                view_url += f"&subfolder={sub}"
            
            logger.info(f"📥 Downloading from Cloud: {view_url}")
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(view_url, headers=headers)
                resp.raise_for_status()
                image_data = resp.content
            
            remote_url = view_url

            logger.info(f"✅ Downloaded {len(image_data)} bytes")

            # Apply stable film look filter
            image_data = apply_stable_film_look(image_data)

            result = {
                "execution_id": execution_id,
                "remote_url": remote_url,
                "image_bytes": image_data,
                "timestamp": datetime.now().isoformat(),
                "image_type": image_type,
                "upload_to_gcs": upload_to_gcs
            }

            # Upload to GCS if requested and metadata provided
            if upload_to_gcs and product_name and kol_persona:
                try:
                    from .gcs_client import upload_campaign_image, get_next_sequence_number

                    # Get next sequence number for this image type
                    if not run_id:
                        from .gcs_client import generate_run_id
                        run_id = generate_run_id(product_name, kol_persona)

                    sequence = get_next_sequence_number(run_id, image_type)

                    # Upload to GCS with structured organization
                    public_url, gcs_path, final_run_id = upload_campaign_image(
                        image_bytes=image_data,
                        product_name=product_name,
                        kol_persona=kol_persona,
                        image_type=image_type,
                        sequence=sequence,
                        run_id=run_id,
                        content_type="image/png"
                    )

                    # Add GCS info to result
                    result.update({
                        "gcs_uploaded": True,
                        "public_url": public_url,
                        "gcs_path": gcs_path,
                        "run_id": final_run_id,
                        "product_name": product_name,
                        "kol_persona": kol_persona,
                        "sequence": sequence
                    })

                    logger.info(f"Image uploaded to GCS: {gcs_path}")

                except Exception as gcs_error:
                    logger.error(f"GCS upload failed: {gcs_error}")
                    result.update({
                        "gcs_uploaded": False,
                        "gcs_error": str(gcs_error),
                        "public_url": remote_url,  # Fallback to ComfyUI URL
                        "product_name": product_name,
                        "kol_persona": kol_persona
                    })

            elif upload_to_gcs and (not product_name or not kol_persona):
                # Raise exception with detailed traceback instead of silent logging
                import traceback
                stack_info = ''.join(traceback.format_stack())
                error_msg = f"GCS upload requested but missing required campaign metadata:\n"
                error_msg += f"  - product_name: {'✓' if product_name else '✗ MISSING'} ({product_name})\n"
                error_msg += f"  - kol_persona: {'✓' if kol_persona else '✗ MISSING'} ({kol_persona})\n"
                error_msg += f"  - upload_to_gcs: {upload_to_gcs}\n\n"
                error_msg += f"Call stack:\n{stack_info}"

                logger.error(error_msg)
                raise ValueError(f"Missing required campaign metadata for GCS upload: product_name={product_name}, kol_persona={kol_persona}")
            else:
                # No GCS upload requested
                result.update({
                    "gcs_uploaded": False,
                    "public_url": remote_url
                })

            logger.info(f"Image generation workflow completed for {execution_id}")
            return result

        except Exception as e:
            logger.error(f"Image generation workflow failed: {e}")
            raise

    async def generate_and_upload(
        self,
        positive_prompt: str,
        negative_prompt: str,
        product_name: str,
        kol_persona: str,
        image_type: str = "marketing",
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convenience method for generate + GCS upload workflow.

        Args:
            positive_prompt: Description of desired image
            negative_prompt: Description of what to avoid
            product_name: Product being marketed
            kol_persona: KOL/persona type
            image_type: Type of image
            run_id: Optional explicit run ID

        Returns:
            Dict containing execution metadata and GCS info
        """
        return await self.generate_and_wait(
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            product_name=product_name,
            kol_persona=kol_persona,
            image_type=image_type,
            upload_to_gcs=True,
            run_id=run_id
        ) 


# Marketing prompt templates
MARKETING_PROMPTS = {
    "product_showcase": """
    Professional product photography of {product}, {style} style,
    clean background, perfect lighting, high resolution, commercial quality,
    {additional_details}
    """,

    "social_media": """
    Eye-catching social media post featuring {subject}, vibrant colors,
    modern aesthetic, {platform} optimized, engaging composition,
    {mood} mood, {additional_details}
    """,

    "lifestyle": """
    Lifestyle photography showing {product} in use, natural setting,
    authentic moments, aspirational but relatable, warm lighting,
    {demographic} demographic, {additional_details}
    """,

    "brand_hero": """
    Hero image for {brand}, premium quality, brand colors,
    minimalist design, professional photography, {industry} industry,
    {additional_details}
    """
}


def create_marketing_prompt(
    template_type: str,
    **kwargs
) -> str:
    """
    Create marketing-optimized prompts using templates.

    Args:
        template_type: Type of marketing content ('product_showcase', 'social_media', etc.)
        **kwargs: Template variables

    Returns:
        Formatted prompt string
    """
    if template_type not in MARKETING_PROMPTS:
        raise ValueError(f"Unknown template type: {template_type}")

    template = MARKETING_PROMPTS[template_type]

    try:
        return template.format(**kwargs).strip()
    except KeyError as e:
        raise ValueError(f"Missing required template variable: {e}")


# Global client instance
_client_instance = None

def get_client() -> ComfyUIClient:
    """Get singleton ComfyUI client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = ComfyUIClient()
    return _client_instance
