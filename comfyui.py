import uuid
import json
import httpx
import os
import logging
import time
from typing import Optional, Dict, Any, BinaryIO

# Configure logger for this module
logger = logging.getLogger(__name__)


def get_server_address() -> str:
    """Get ComfyUI server address from environment variable."""
    server_addr = os.getenv('COMFYUI_URL', '127.0.0.1:8188')
    logger.info(f"Using ComfyUI server address: {server_addr}")
    return server_addr


def get_server_url(host: str, port: int) -> str:
    """Get full server URL based on worker host and port."""
    if port == 443:
        protocol = "https"
        url = f"https://{host}"
    elif port == 80:
        protocol = "http"
        url = f"http://{host}"
    else:
        protocol = "http"
        url = f"http://{host}:{port}"

    logger.info(f"Using ComfyUI server URL: {url} (protocol: {protocol})")
    return url


def get_client_id() -> str:
    """Generate a unique client ID."""
    client_id = str(uuid.uuid4())
    logger.info(f"Generated client ID: {client_id}")
    return client_id


def get_completion_wait_time() -> float:
    """Get wait time after execution completion before fetching history."""
    wait_time = float(os.getenv('COMFYUI_COMPLETION_WAIT_TIME', '2.0'))
    logger.info(f"Using completion wait time: {wait_time}s")
    return wait_time


def get_history_retry_wait_time() -> float:
    """Get wait time before retrying history fetch if empty."""
    wait_time = float(os.getenv('COMFYUI_HISTORY_RETRY_WAIT_TIME', '2.0'))
    logger.info(f"Using history retry wait time: {wait_time}s")
    return wait_time


def queue_prompt(
    prompt: Dict[str, Any],
    server_address: Optional[str] = None,
    client_id: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """Queue a prompt for execution with retry mechanism."""
    if client_id is None:
        client_id = get_client_id()

    # Determine server URL
    if host is not None and port is not None:
        # Use new worker-based approach
        base_url = get_server_url(host, port)
        logger.info(f"Queueing prompt to ComfyUI worker: {host}:{port}")
    elif server_address is not None:
        # Use legacy server_address format
        base_url = f"http://{server_address}"
        logger.info(f"Queueing prompt to ComfyUI server: {server_address}")
    else:
        # Fall back to environment variable
        server_address = get_server_address()
        base_url = f"http://{server_address}"
        logger.info(f"Queueing prompt to ComfyUI server (env): {server_address}")

    logger.info(f"Using client ID: {client_id}")

    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            payload = {"prompt": prompt, "client_id": client_id}
            url = f"{base_url}/prompt"

            logger.info(f"Sending POST request to: {url} (attempt {attempt}/{max_retries})")
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()
                logger.info(f"Prompt queued successfully on attempt {attempt}, response: {result}")
                return result

        except httpx.TimeoutException as e:
            last_exception = e
            logger.warning(f"Timeout on attempt {attempt}/{max_retries}: {str(e)}")
            if attempt < max_retries:
                wait_time = attempt * 2  # Progressive backoff: 2s, 4s, 6s
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            continue

        except httpx.HTTPStatusError as e:
            last_exception = e
            # Extract detailed error message for 400 responses
            error_detail = None
            if e.response.status_code == 400:
                try:
                    error_json = e.response.json()
                    # Extract error details from the response
                    if "error" in error_json:
                        error_info = error_json["error"]
                        error_type = error_info.get("type", "unknown")
                        error_message = error_info.get("message", "Unknown error")
                        error_details = error_info.get("details", "")

                        error_detail = f"Type: {error_type}, Message: {error_message}"
                        if error_details:
                            error_detail += f", Details: {error_details}"

                        # Add node errors if present
                        if "node_errors" in error_json:
                            node_errors = []
                            for node_id, node_info in error_json["node_errors"].items():
                                class_type = node_info.get("class_type", "Unknown")
                                errors = node_info.get("errors", [])
                                for err in errors:
                                    err_type = err.get("type", "unknown")
                                    err_details = err.get("details", "")
                                    node_errors.append(f"Node {node_id} ({class_type}): {err_type} - {err_details}")

                            if node_errors:
                                error_detail += f"\nNode Errors:\n" + "\n".join(node_errors)
                    else:
                        error_detail = e.response.text
                except:
                    error_detail = e.response.text

                logger.error(f"HTTP 400 error on attempt {attempt}/{max_retries}:\n{error_detail}")
                # Don't retry on 400 errors - these are validation errors that won't resolve with retry
                raise Exception(f"ComfyUI validation error (400): {error_detail}")
            else:
                logger.warning(f"HTTP {e.response.status_code} error on attempt {attempt}/{max_retries}: {e.response.text}")
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                continue

        except httpx.RequestError as e:
            last_exception = e
            logger.warning(f"Connection error on attempt {attempt}/{max_retries}: {str(e)}")
            if attempt < max_retries:
                wait_time = attempt * 2
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            continue

        except json.JSONDecodeError as e:
            last_exception = e
            logger.error(f"Invalid JSON response from ComfyUI on attempt {attempt}/{max_retries}: {str(e)}")
            if attempt < max_retries:
                wait_time = attempt * 2
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            continue

        except Exception as e:
            last_exception = e
            logger.error(f"Unexpected error on attempt {attempt}/{max_retries}: {str(e)}")
            if attempt < max_retries:
                wait_time = attempt * 2
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            continue

    # All retries exhausted
    if isinstance(last_exception, httpx.TimeoutException):
        logger.error(f"All {max_retries} attempts failed with timeout")
        raise Exception(f"ComfyUI request timeout after {max_retries} attempts: {str(last_exception)}")
    elif isinstance(last_exception, httpx.HTTPStatusError):
        logger.error(f"All {max_retries} attempts failed with HTTP error {last_exception.response.status_code}")
        raise Exception(f"ComfyUI HTTP error {last_exception.response.status_code} after {max_retries} attempts")
    elif isinstance(last_exception, httpx.RequestError):
        logger.error(f"All {max_retries} attempts failed with connection error")
        raise Exception(f"ComfyUI connection error after {max_retries} attempts: {str(last_exception)}")
    else:
        logger.error(f"All {max_retries} attempts failed")
        raise Exception(f"ComfyUI error after {max_retries} attempts: {str(last_exception)}")


def get_image(
    filename: str,
    subfolder: str,
    folder_type: str,
    server_address: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None
) -> bytes:
    """Download an image from ComfyUI."""
    # Determine server URL
    if host is not None and port is not None:
        base_url = get_server_url(host, port)
        logger.info(f"Downloading from ComfyUI worker: {host}:{port}")
    elif server_address is not None:
        base_url = f"http://{server_address}"
        logger.info(f"Downloading from ComfyUI server: {server_address}")
    else:
        server_address = get_server_address()
        base_url = f"http://{server_address}"
        logger.info(f"Downloading from ComfyUI server (env): {server_address}")

    logger.info(f"Downloading image: {filename} from subfolder: {subfolder}, type: {folder_type}")

    try:
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url = f"{base_url}/view"
        headers = {"Host": "LLMAgent"}

        logger.info(f"Sending GET request to: {url} with params: {params}")
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()

            image_data = response.content
            logger.info(f"Successfully downloaded image: {filename}, size: {len(image_data)} bytes")
            return image_data

    except httpx.TimeoutException as e:
        logger.error(f"Timeout while downloading image {filename}: {str(e)}")
        raise Exception(f"Image download timeout: {str(e)}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while downloading image {filename}: {e.response.status_code}")
        raise Exception(f"Image download HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error while downloading image {filename}: {str(e)}")
        raise Exception(f"Image download connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error while downloading image {filename}: {str(e)}")
        raise


def get_queue(
    server_address: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None
) -> Dict[str, Any]:
    """Get current queue status."""
    # Determine server URL
    if host is not None and port is not None:
        base_url = get_server_url(host, port)
        logger.info(f"Getting queue status from ComfyUI worker: {host}:{port}")
    elif server_address is not None:
        base_url = f"http://{server_address}"
        logger.info(f"Getting queue status from ComfyUI server: {server_address}")
    else:
        server_address = get_server_address()
        base_url = f"http://{server_address}"
        logger.info(f"Getting queue status from ComfyUI server (env): {server_address}")

    try:
        url = f"{base_url}/queue"

        logger.info(f"Sending GET request to: {url}")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()

            queue_data = response.json()
            logger.info(f"Successfully retrieved queue status")
            return queue_data

    except httpx.TimeoutException as e:
        logger.error(f"Timeout while getting queue status: {str(e)}")
        raise Exception(f"Queue request timeout: {str(e)}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while getting queue status: {e.response.status_code}")
        raise Exception(f"Queue HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error while getting queue status: {str(e)}")
        raise Exception(f"Queue connection error: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from queue: {str(e)}")
        raise Exception(f"Invalid queue response: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error while getting queue status: {str(e)}")
        raise


def get_history(
    prompt_id: str,
    server_address: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None
) -> Dict[str, Any]:
    """Get execution history for a prompt."""
    # Determine server URL
    if host is not None and port is not None:
        base_url = get_server_url(host, port)
        logger.info(f"Getting history from ComfyUI worker: {host}:{port}")
    elif server_address is not None:
        base_url = f"http://{server_address}"
        logger.info(f"Getting history from ComfyUI server: {server_address}")
    else:
        server_address = get_server_address()
        base_url = f"http://{server_address}"
        logger.info(f"Getting history from ComfyUI server (env): {server_address}")

    logger.info(f"Getting execution history for prompt: {prompt_id}")

    try:
        url = f"{base_url}/history/{prompt_id}"

        logger.info(f"Sending GET request to: {url}")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()

            history = response.json()
            logger.info(f"Successfully retrieved history for prompt: {prompt_id}")
            logger.info(f"History contains {len(history)} entries")
            return history

    except httpx.TimeoutException as e:
        logger.error(f"Timeout while getting history for {prompt_id}: {str(e)}")
        raise Exception(f"History request timeout: {str(e)}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while getting history for {prompt_id}: {e.response.status_code}")
        raise Exception(f"History HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error while getting history for {prompt_id}: {str(e)}")
        raise Exception(f"History connection error: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from history for {prompt_id}: {str(e)}")
        raise Exception(f"Invalid history response: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error while getting history for {prompt_id}: {str(e)}")
        raise


def upload_file(file: BinaryIO, subfolder: str = "", overwrite: bool = False, server_address: Optional[str] = None, filename: Optional[str] = None) -> Optional[str]:
    """Upload a file to ComfyUI and return the path."""
    if server_address is None:
        server_address = get_server_address()

    # Use provided filename or get from file object
    file_name = filename or getattr(file, 'name', f'upload_{uuid.uuid4().hex[:8]}.png')
    logger.info(f"Uploading file: {file_name} to ComfyUI server: {server_address}")

    try:
        files = {"image": (file_name, file, 'image/png')}
        data = {}

        if overwrite:
            data["overwrite"] = "true"
            logger.info("Upload set to overwrite existing files")

        if subfolder:
            data["subfolder"] = subfolder
            logger.info(f"Upload to subfolder: {subfolder}")

        url = f"http://{server_address}/upload/image"
        logger.info(f"Sending upload request to: {url}")

        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, files=files, data=data)
            response.raise_for_status()

            response_data = response.json()
            logger.info(f"Upload response: {response_data}")

            path = response_data["name"]
            if "subfolder" in response_data and response_data["subfolder"]:
                path = response_data["subfolder"] + "/" + path

            logger.info(f"File uploaded successfully to path: {path}")
            return path

    except httpx.TimeoutException as e:
        logger.error(f"Timeout while uploading file {file_name}: {str(e)}")
        raise Exception(f"File upload timeout: {str(e)}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while uploading file {file_name}: {e.response.status_code} - {e.response.text}")
        raise Exception(f"File upload HTTP error: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error while uploading file {file_name}: {str(e)}")
        raise Exception(f"File upload connection error: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response while uploading file {file_name}: {str(e)}")
        raise Exception(f"Invalid upload response: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error while uploading file {file_name}: {str(e)}")
        raise


def get_images(
    prompt: Dict[str, Any],
    server_address: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    poll_interval: float = 1.0
) -> Dict[str, list]:
    """Execute a prompt and get the resulting images using API polling."""
    # Determine which parameters to use
    if host is not None and port is not None:
        logger.info(f"Starting image generation process with worker: {host}:{port}")
    elif server_address is not None:
        logger.info(f"Starting image generation process with server: {server_address}")
    else:
        server_address = get_server_address()
        logger.info(f"Starting image generation process with server (env): {server_address}")

    try:
        # Queue the prompt for execution
        prompt_response = queue_prompt(prompt, server_address, host=host, port=port)
        prompt_id = prompt_response['prompt_id']
        logger.info(f"Prompt queued with ID: {prompt_id}")

        output_images = {}

        # Poll queue status until prompt is complete
        logger.info(f"Polling queue status for prompt completion...")
        prompt_in_queue = True
        polling_start_time = time.time()
        max_polling_time = 600  # 10 minutes max polling time
        last_status_log_time = time.time()

        while prompt_in_queue:
            time.sleep(poll_interval)

            # Check for polling timeout
            elapsed_time = time.time() - polling_start_time
            if elapsed_time > max_polling_time:
                logger.error(f"Polling timeout after {elapsed_time:.1f} seconds for prompt {prompt_id}")
                raise Exception(f"Polling timeout: No completion detected after {max_polling_time} seconds")

            try:
                queue_status = get_queue(server_address, host=host, port=port)

                # Check if prompt is in pending queue
                prompt_in_pending = any(
                    item[1] == prompt_id for item in queue_status.get('queue_pending', [])
                )

                # Check if prompt is in running queue
                prompt_in_running = any(
                    item[1] == prompt_id for item in queue_status.get('queue_running', [])
                )

                # Log status periodically (every 30 seconds) to avoid spam
                current_time = time.time()
                should_log = (current_time - last_status_log_time) >= 30

                if prompt_in_pending:
                    if should_log:
                        logger.info(f"Prompt {prompt_id} is in pending queue (elapsed: {elapsed_time:.1f}s)")
                        last_status_log_time = current_time
                elif prompt_in_running:
                    if should_log:
                        logger.info(f"Prompt {prompt_id} is currently running (elapsed: {elapsed_time:.1f}s)")
                        last_status_log_time = current_time
                else:
                    # Prompt is no longer in queue, either completed or errored
                    logger.info(f"Prompt {prompt_id} is no longer in queue (elapsed: {elapsed_time:.1f}s)")
                    prompt_in_queue = False

            except Exception as e:
                logger.error(f"Error checking queue status: {str(e)}")
                time.sleep(poll_interval * 2)  # Wait longer on error
                continue

        # Wait for completion before fetching history (configurable)
        completion_wait_time = get_completion_wait_time()
        logger.info(f"Waiting {completion_wait_time}s for completion before fetching history")
        time.sleep(completion_wait_time)

        # Get execution history and download results
        logger.info(f"Getting execution history for prompt: {prompt_id}")
        history = get_history(prompt_id, server_address, host=host, port=port)

        if prompt_id not in history:
            # there is a delay while update the result, so retry
            retry_wait_time = get_history_retry_wait_time()
            logger.info(f"History empty, waiting {retry_wait_time}s before retry")
            time.sleep(retry_wait_time)
            history = get_history(prompt_id, server_address, host=host, port=port)

            # if still empty, error
            if prompt_id not in history:
                logger.error(f"History still empty after retry for prompt: {prompt_id}")
                raise Exception(f"No execution history found for prompt: {prompt_id}")

        prompt_history = history[prompt_id]

        # Check if execution was successful
        if prompt_history.get('status', {}).get('status_str') == 'error':
            error_details = prompt_history.get('status', {}).get('messages', [])
            logger.error(f"Prompt execution failed: {error_details}")
            raise Exception(f"Prompt execution failed: {error_details}")

        logger.info(f"History retrieved with {len(prompt_history.get('outputs', {}))} output nodes")

        # Process output images
        for node_id in prompt_history['outputs']:
            node_output = prompt_history['outputs'][node_id]
            if 'images' in node_output:
                logger.info(f"Processing {len(node_output['images'])} images from node {node_id}")
                images_output = []

                for idx, image in enumerate(node_output['images']):
                    try:
                        logger.info(f"Downloading image {idx + 1}/{len(node_output['images'])}: {image['filename']}")
                        image_data = get_image(image['filename'], image['subfolder'], image['type'], server_address, host=host, port=port)
                        images_output.append(image_data)
                        logger.info(f"Successfully downloaded image: {image['filename']}")
                    except Exception as e:
                        logger.error(f"Failed to download image {image['filename']}: {str(e)}")
                        continue

                output_images[node_id] = images_output
                logger.info(f"Node {node_id}: {len(images_output)} images processed")

        logger.info(f"Image generation completed. Total nodes with images: {len(output_images)}")
        return output_images

    except Exception as e:
        logger.error(f"Error in get_images: {str(e)}")
        raise


