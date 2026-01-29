# Video Storyboard & Generation

## Description
The **Video Storyboard & Generation** app is an advanced workflow tool that transforms static images into video concepts. It uses a multi-agent system (CrewAI) to analyze an input image, brainstorm video ideas, and generate detailed prompts. These prompts are then sent to **Kling AI** (via a self-hosted ComfyUI instance) to generate high-quality videos. The app features a hybrid architecture that supports local file management and Google Cloud Storage (GCS) integration for scalable asset handling.

## Architecture / Processing Flow

1.  **Configuration**:
    *   **Workflow Studio**: User edits agent backstories (Analyst, Concept, Prompt) and prompt frameworks.
    *   **Kling Settings**: User configures model version (`kling-v2-1`, etc.), CFG scale, mode (std/pro), aspect ratio, and duration.

2.  **Input Selection**:
    *   **Sources**: User adds images from the "Results Gallery" or uploads new ones directly.
    *   **Queue**: Images are added to a "Selection Queue" where variation counts (videos per image) can be set individually.

3.  **Draft Generation (`VideoStoryboardWorkflow`)**:
    *   **Analyst Agent**: Analyzes the visual elements of the source image.
    *   **Concept Agent**: Brainstorms creative video motion concepts based on the analysis and persona.
    *   **Prompt Agent**: Converts concepts into technical video generation prompts compatible with Kling AI.

4.  **Video Generation (ComfyUI / Kling)**:
    *   The app sends prompts to the `ComfyUIClient`.
    *   **Task IDs** are logged to the `VideoLogsStorage` database.

5.  **Monitoring & Delivery (Hybrid Cloud/Local)**:
    *   The app polls the task status.
    *   **Status Check**: It checks both the local ComfyUI server and **Google Cloud Storage (GCS)** for completed video files.
    *   **Download**: If a video is found on GCS (uploaded by the worker), it is downloaded to the local machine for viewing.
    *   **Merge**: Users can select multiple completed videos to stitch them into a single compilation file.

## Functions/Features

*   **Workflow Configuration Studio**: A UI to directly edit the text prompts and backstories for the CrewAI agents.
*   **Kling AI Controls**: Fine-grained control over Kling parameters including Model Version, Duration (5s/10s), Aspect Ratio, and Mode.
*   **Hybrid Asset Management**: Automatically detects and downloads videos from Google Cloud Storage if the generation worker is remote.
*   **Batch Queueing**: Queue multiple source images with different variation counts in a single batch.
*   **Batch Recovery**: UI to detect and resume monitoring for incomplete batches (e.g., after a browser refresh).
*   **Video Merging**: Built-in tool to select completed videos and merge them into a single MP4 file.
*   **History Log**: Tracks all generation attempts, their status, prompts, and file paths.

## Backlog

*   **Custom Aspect Ratios**: Add controls for video aspect ratio (currently defaults to source).
*   **Retry Logic**: Auto-retry failed Kling AI tasks.
*   **Prompt Editing**: Allow manual editing of generated prompts before queueing.
*   **Video Preview**: Better integrated video player for batch reviews.

## Deployment Infrastructure

*   **Container**: Docker container based on `python:3.11-slim`.
*   **Service Name**: `video` (in `docker-compose.yml`).
*   **Port**: Exposed on port **8503** (mapped from container port 8501).
*   **Dependencies**: Requires a running ComfyUI instance with Kling AI nodes.
*   **Storage**: Mounts `results/` locally, but can sync with GCS.

## Secrets/Keys

*   `OPENAI_API_KEY`: Required for the CrewAI agents (GPT-4o) to generate concepts.
*   `KLING_ACCESS_KEY` & `KLING_SECRET_KEY`: Credentials for the Kling AI API.
*   `COMFYUI_API_URL`: Address of the ComfyUI server.
*   `GCS_BUCKET_NAME`: Name of the Google Cloud Storage bucket.
*   `GCS_CREDENTIALS` or `GCS_CREDENTIALS_PATH`: JSON credentials for authenticating with GCS.

## Development Environment

*   **Language**: Python 3.11
*   **Framework**: Streamlit
*   **Key Libraries**:
    *   `crewai`: Agent orchestration.
    *   `moviepy`: Merging video files.
    *   `google-cloud-storage`: Cloud asset management.
    *   `requests` / `aiohttp`: API communication.
