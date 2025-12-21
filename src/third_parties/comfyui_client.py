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
COMFYUI_API_URL = GlobalConfig.COMFYUI_API_URL
COMFYUI_API_TIMEOUT = GlobalConfig.COMFYUI_API_TIMEOUT
COMFYUI_POLL_INTERVAL = GlobalConfig.COMFYUI_POLL_INTERVAL
COMFYUI_MAX_POLL_TIME = GlobalConfig.COMFYUI_MAX_POLL_TIME
COMFYUI_MAX_RETRIES = GlobalConfig.COMFYUI_MAX_RETRIES

# Workflow configurations
WORKFLOW_IDS = {
    "turbo": "43ad0c5c-3394-433b-b434-8089eb43f3c9",
    "wan2.2": "82892890-19b4-4c3c-9ea9-5e004afd3343"
}

# Persona mappings
PERSONA_LORA_MAPPING_TURBO = {
    "Jennie": "z-image-persona/jennie_test_training_copy.safetensors",
    "Sephera": "z-image-persona/sephera-z-image-turbo-v1_copy.safetensors",
    "Nya": "z-image-persona/nya-z-image-turbo-v1.safetensors",
    "Emi": "z-image-persona/emi-z-image-turbo-v1_copy_copy_copy.safetensors"
}

PERSONA_LORA_MAPPING_WAN = {
    "Jennie": {
        "low": "persona/WAN2.2-JennieV3_LowNoise_KhiemLe.safetensors",
        "high": "persona/WAN2.2-JennieV3_HighNoise_KhiemLe.safetensors"
    },
    "Sephera": {
        "low": "persona/WAN2.2-LowNoise_Sephera_KhiemLe.safetensors",
        "high": "persona/WAN2.2-HighNoise_Sephera_KhiemLe.safetensors"
    },
    "Mika": {
        "low": "persona/WAN2.2-MikaV2_LowNoise_KhiemLe.safetensors",
        "high": "persona/WAN2.2-MikaV2_HighNoise_KhiemLe.safetensors"
    },
    "Nya": {
        "low": "persona/WAN2.2-LowNoise_Nya_KhiemLe.safetensors",
        "high": "persona/WAN2.2-HighNoise_Nya_KhiemLe.safetensors"
    },
    "Emi": {
        "low": "persona/WAN2.2-LowNoise_Nya_KhiemLe.safetensors",
        "high": "persona/WAN2.2-HighNoise_Nya_KhiemLe.safetensors"
    },
    "Roxie": {
        "low": "persona/WAN2.2-LowNoise_Nya_KhiemLe.safetensors",
        "high": "persona/WAN2.2-HighNoise_Nya_KhiemLe.safetensors"
    }
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
    Async client for ComfyUI image generation API.

    Handles the complete workflow:
    1. Submit generation request
    2. Poll for completion status
    3. Download generated image
    4. Upload to S3 (optional)
    """

    def __init__(
        self,
        api_url: str = COMFYUI_API_URL,
        timeout: int = COMFYUI_API_TIMEOUT,
        poll_interval: int = COMFYUI_POLL_INTERVAL,
        max_poll_time: int = COMFYUI_MAX_POLL_TIME,
        max_retries: int = COMFYUI_MAX_RETRIES
    ):
        import traceback
        # Validate API URL early to avoid opaque httpx errors
        if not api_url or not str(api_url).strip():
            raise ComfyUIConfigError(
                "COMFYUI_API_URL is not set. Provide a full URL, e.g., http://localhost:8188"
            )
        if not (str(api_url).startswith("http://") or str(api_url).startswith("https://")):
            raise ComfyUIConfigError(
                f"Invalid COMFYUI_API_URL: '{api_url}'. It must start with http:// or https://"
            )

        self.api_url = api_url.rstrip('/')
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_time = max_poll_time
        self.max_retries = max_retries

        # No S3 integration; direct URLs are returned by the API

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        url = f"{self.api_url}{endpoint}"

        # Log request details
        request_body = kwargs.get('json', {})
        logger.info(f"🔵 ComfyUI Request: {method} {url}")
        if request_body:
            logger.info(f"   Request body: {json.dumps(request_body, indent=2)}")

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    response = await client.request(method, url, **kwargs)

                    # Log response for debugging
                    logger.info(f"   Response status: {response.status_code}")

                    if response.status_code == 429:  # Rate limited
                        if attempt == self.max_retries:
                            raise ComfyUIAPIError("Rate limited after all retries")

                        delay = _calculate_backoff_delay(attempt)
                        logger.warning(f"Rate limited, retrying in {delay:.2f}s (attempt {attempt + 1})")
                        await asyncio.sleep(delay)
                        continue

                    response.raise_for_status()
                    return response

            except httpx.TimeoutException:
                if attempt == self.max_retries:
                    raise ComfyUITimeoutError(f"Request timed out after {self.max_retries + 1} attempts")

                delay = _calculate_backoff_delay(attempt)
                logger.warning(f"Request timeout, retrying in {delay:.2f}s (attempt {attempt + 1})")
                await asyncio.sleep(delay)

            except httpx.HTTPStatusError as e:
                # Get response body for detailed error info
                try:
                    error_body = e.response.text
                    error_json = e.response.json()
                    logger.error(f"❌ Server returned {e.response.status_code}")
                    logger.error(f"   Response body: {json.dumps(error_json, indent=2)}")
                except:
                    error_body = e.response.text
                    logger.error(f"❌ Server returned {e.response.status_code}")
                    logger.error(f"   Response body (raw): {error_body[:500]}")

                if e.response.status_code >= 500:  # Server errors
                    if attempt == self.max_retries:
                        raise ComfyUIAPIError(f"Server error {e.response.status_code}: {error_body}")

                    delay = _calculate_backoff_delay(attempt)
                    logger.warning(f"Server error {e.response.status_code}, retrying in {delay:.2f}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Client errors (4xx) - don't retry
                    raise ComfyUIAPIError(f"Client error {e.response.status_code}: {error_body}")

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()

                if attempt == self.max_retries:
                    logger.error(f"ComfyUI connection failed after {self.max_retries} retries. Full traceback:\n{error_details}")
                    raise ComfyUIError(f"Unexpected error after {self.max_retries} retries: {str(e)}\n\nFull traceback:\n{error_details}")

                delay = _calculate_backoff_delay(attempt)
                logger.warning(f"Unexpected error, retrying in {delay:.2f}s: {e}\nTraceback:\n{error_details}")
                await asyncio.sleep(delay)

        raise ComfyUIError("Max retries exceeded")

    async def generate_image(
        self,
        positive_prompt: str,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        workflow_type: str = "turbo",
        workflow_name: Optional[str] = None,
        lora_name: Optional[str] = None,
        kol_persona: Optional[str] = None
    ) -> str:
        """
        Start image generation using the new executions endpoint with workflow ID.

        Args:
            positive_prompt: Description of desired image
            negative_prompt: Description of what to avoid
            workflow_type: Type of workflow to use ("turbo" or "wan2.2")
            workflow_name: Name of the ComfyUI workflow to use (deprecated, uses default workflow)
            lora_name: LoRA model name to use (deprecated, uses persona mapping)
            kol_persona: KOL persona name for automatic lora mapping

        Returns:
            execution_id: ID to track generation progress
        """
        workflow_id = WORKFLOW_IDS.get(workflow_type.lower(), WORKFLOW_IDS["turbo"])
        is_turbo = workflow_type.lower() == "turbo"

        logger.info("=" * 80)
        logger.info(f"🎨 COMFYUI IMAGE GENERATION REQUEST ({workflow_type.upper()})")
        logger.info("=" * 80)

        # Base payload
        payload = {
            "workflow_id": workflow_id,
            "prompt_count": 1,
            "seed_config": {
                "strategy": "random",
                "base_seed": 0,
                "step": 1
            }
        }

        if is_turbo:
            # TURBO WORKFLOW LOGIC
            cleaned_prompt = re.sub(r'<lora:[^>]+>,\s*Instagirl,?\s*', '', positive_prompt, flags=re.IGNORECASE)
            
            logger.info(f"📝 Original Prompt: {positive_prompt[:100]}...")
            logger.info(f"📝 Cleaned Prompt: {cleaned_prompt[:200]}{'...' if len(cleaned_prompt) > 200 else ''}")
            
            payload["overwritable_inputs"] = {
                "positive_prompt": {
                    "field": "45.inputs.text",
                    "dtype": "str"
                },
                "persona_lora_name": {
                    "field": "53.inputs.lora_name",
                    "dtype": "str"
                }
            }
            payload["input_overrides"] = {
                "positive_prompt": cleaned_prompt,
                "persona_lora_name": ""
            }

            if kol_persona:
                persona_lora = None
                for persona_key in PERSONA_LORA_MAPPING_TURBO.keys():
                    if persona_key.lower() == kol_persona.lower():
                        persona_lora = PERSONA_LORA_MAPPING_TURBO[persona_key]
                        break
                
                if persona_lora:
                    payload["input_overrides"]["persona_lora_name"] = persona_lora
                    logger.info(f"🎭 Turbo LoRA Applied: {persona_lora}")
                else:
                    logger.warning(f"⚠️  Unknown/Pending Persona for Turbo: {kol_persona}")
        
        else:
            # WAN2.2 WORKFLOW LOGIC (Old logic)
            logger.info(f"📝 Positive Prompt: {positive_prompt[:200]}...")
            logger.info(f"🚫 Negative Prompt: {negative_prompt[:100]}...")

            payload["input_overrides"] = {
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
                "persona_low_lora_name": "",
                "persona_high_lora_name": ""
            }

            if kol_persona:
                persona_config = None
                for persona_key in PERSONA_LORA_MAPPING_WAN.keys():
                    if persona_key.lower() == kol_persona.lower():
                        persona_config = PERSONA_LORA_MAPPING_WAN[persona_key]
                        break
                
                if persona_config:
                    payload["input_overrides"]["persona_low_lora_name"] = persona_config["low"]
                    payload["input_overrides"]["persona_high_lora_name"] = persona_config["high"]
                    logger.info(f"🎭 WAN LoRA Applied: Low={persona_config['low']}, High={persona_config['high']}")
                else:
                    logger.warning(f"⚠️  Unknown Persona for WAN: {kol_persona}")

        logger.info(f"📋 Workflow ID: {workflow_id}")
        logger.info(f"🌐 API URL: {self.api_url}")
        logger.info(f"⏱️  Timeout: {self.timeout}s, Max Poll Time: {self.max_poll_time}s")
        logger.debug(f"📦 Full Payload: {json.dumps(payload, indent=2)}")
        logger.info("=" * 80)

        try:
            response = await self._make_request(
                "POST",
                "/executions",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            data = response.json()
            
            # Add debug logging for API response format
            logger.info(f"📋 API Response structure: {json.dumps(data, indent=2)}")
            
            execution_id = data.get("execution_id")

            if not execution_id:
                # Try alternative response formats
                if isinstance(data, dict):
                    # Check nested data structure first (common format)
                    nested_data = data.get("data", {})
                    if isinstance(nested_data, dict):
                        execution_id = nested_data.get("execution_id")
                        if execution_id:
                            logger.info(f"🔍 Found execution_id in nested data: {execution_id}")
                    
                    # If still not found, check other common alternative keys
                    if not execution_id:
                        execution_id = (data.get("id") or 
                                      data.get("execution") or 
                                      data.get("task_id") or 
                                      data.get("job_id"))
                        
                        if execution_id:
                            logger.info(f"🔍 Found execution_id under alternative key: {execution_id}")
                    
                    if not execution_id:
                        logger.error(f"❌ No execution_id found in response keys: {list(data.keys())}")
                        if "data" in data:
                            logger.error(f"   Nested data keys: {list(data['data'].keys()) if isinstance(data['data'], dict) else 'Not a dict'}")
                        raise ComfyUIAPIError(f"No execution_id in response. Available keys: {list(data.keys())}")
                else:
                    raise ComfyUIAPIError(f"Invalid response format: {type(data)}")

            logger.info(f"✅ Image generation started successfully")
            logger.info(f"🔑 Execution ID: {execution_id}")
            logger.info(f"🕐 Request timestamp: {datetime.now().isoformat()}")
            logger.info("=" * 80)
            return execution_id

        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"❌ Failed to start image generation: {e}")
            logger.error(f"🔍 Error type: {type(e).__name__}")
            logger.error("=" * 80)
            raise

    async def check_status(self, execution_id: str) -> Dict[str, Any]:
        """
        Check the status of image generation.

        Args:
            execution_id: ID from generate_image()

        Returns:
            Status information including completion status and output images
        """
        async def _status_request():
            """Internal status request that goes through queue."""
            response = await self._make_request(
                "GET",
                f"/image/generate/{execution_id}/status"
            )

            data = response.json()

            if "data" not in data:
                raise ComfyUIAPIError("Invalid status response format")

            return data["data"]

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

    async def download_image(self, execution_id: str) -> bytes:
        """
        Download the generated image.

        Args:
            execution_id: ID from generate_image()

        Returns:
            Image data as bytes
        """
        try:
            logger.info(f"🔽 Starting download for execution_id: {execution_id}")
            response = await self._make_request(
                "GET",
                f"/image/generate/{execution_id}/download"
            )

            if not response.content:
                raise ComfyUIAPIError(f"Download returned empty content for {execution_id}")

            logger.info(f"✅ Successfully downloaded {len(response.content)} bytes")
            return response.content

        except ComfyUIAPIError:
            # Re-raise ComfyUI errors
            raise
        except Exception as e:
            logger.error(f"❌ Failed to download image for {execution_id}: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            raise

    async def download_image_by_path(self, image_path: str) -> bytes:
        """
        Download the generated image using its file path.

        Args:
            image_path: Path to the image (e.g., /outputs/xxx/xxx.png)

        Returns:
            Image data as bytes
        """
        try:
            logger.info(f"🔽 Starting download for path: {image_path}")

            # Try direct path endpoint
            response = await self._make_request(
                "GET",
                image_path
            )

            if not response.content:
                raise ComfyUIAPIError(f"Download returned empty content for path {image_path}")

            logger.info(f"✅ Successfully downloaded {len(response.content)} bytes from path")
            return response.content

        except ComfyUIAPIError:
            # Re-raise ComfyUI errors
            raise
        except Exception as e:
            logger.error(f"❌ Failed to download image from path {image_path}: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
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
        workflow_name: Optional[str] = None,
        lora_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete image generation workflow: generate, wait, download, and optionally upload to GCS.
        
        This method uses queue management to ensure sequential processing and prevent
        overwhelming ComfyUI with concurrent requests.

        Args:
            positive_prompt: Description of desired image
            negative_prompt: Description of what to avoid
            product_name: Product being marketed (for GCS organization)
            kol_persona: KOL/persona type (for GCS organization)
            image_type: Type of image (marketing, product_showcase, etc.)
            upload_to_gcs: Whether to upload to GCS with structured folders
            run_id: Optional explicit run ID (overrides generation)
            workflow_name: Name of the ComfyUI workflow to use (optional)
            lora_name: LoRA model name to use (optional)

        Returns:
            Dict containing execution metadata, URLs, and campaign info
        """
        
        async def _execute_generation():
            """Internal function to execute the entire generation workflow."""
            # Start generation
            execution_id = await self.generate_image(
                positive_prompt,
                negative_prompt,
                workflow_name=workflow_name,
                lora_name=lora_name,
                kol_persona=kol_persona
            )

            # Wait for completion
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

            # Debug logging - show full status response when output_images is missing
            if not output_images:
                logger.error(f"❌ No output_images in status response for {execution_id}")
                logger.error(f"📋 Full status data: {json.dumps(status_data, indent=2)}")

                # Try fallback: use direct download endpoint
                logger.info(f"🔄 Attempting fallback: direct download for {execution_id}")
                try:
                    image_data = await self.download_image(execution_id)
                    
                    # Apply stable film look filter
                    image_data = apply_stable_film_look(image_data)
                    
                    remote_url = f"{self.api_url}/image/generate/{execution_id}/download"

                    result = {
                        "execution_id": execution_id,
                        "remote_url": remote_url,
                        "image_bytes": image_data,
                        "timestamp": datetime.now().isoformat(),
                        "image_type": image_type,
                        "upload_to_gcs": upload_to_gcs,
                        "fallback_method": "direct_download"
                    }

                    logger.info(f"✅ Fallback successful! Downloaded {len(image_data)} bytes via direct endpoint")

                    # Continue with GCS upload if needed
                    if upload_to_gcs and product_name and kol_persona:
                        try:
                            from .gcs_client import upload_campaign_image, get_next_sequence_number, generate_run_id

                            if not run_id:
                                run_id = generate_run_id(product_name, kol_persona)

                            sequence = get_next_sequence_number(run_id, image_type)

                            public_url, gcs_path, final_run_id = upload_campaign_image(
                                image_bytes=image_data,
                                product_name=product_name,
                                kol_persona=kol_persona,
                                image_type=image_type,
                                sequence=sequence,
                                run_id=run_id,
                                content_type="image/png"
                            )

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
                                "public_url": remote_url,
                                "product_name": product_name,
                                "kol_persona": kol_persona
                            })

                    return result

                except Exception as fallback_error:
                    logger.error(f"❌ Fallback download also failed: {fallback_error}")
                    raise ComfyUIAPIError(
                        f"No output_images in status data and direct download failed for {execution_id}. "
                        f"Status: {status_data.get('status', 'unknown')}, "
                        f"Error message: {status_data.get('error_message', 'none')}"
                    )

            # Get first image path (output_images is a list of dicts)
            first_output = output_images[0]
            image_path = None
            for key, paths in first_output.items():
                if paths and len(paths) > 0:
                    image_path = paths[0]
                    break

            if not image_path:
                raise ComfyUIAPIError(f"No image path found in output_images for {execution_id}")

            logger.info(f"📁 Found image path: {image_path}")

            # Download image bytes using the path
            logger.info(f"📥 Attempting to download image for {execution_id}...")
            image_data = await self.download_image_by_path(image_path)
            logger.info(f"✅ Downloaded {len(image_data)} bytes")

            # Apply stable film look filter
            image_data = apply_stable_film_look(image_data)

            # Construct ComfyUI download URL using the working path
            remote_url = f"{self.api_url}{image_path}"

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
