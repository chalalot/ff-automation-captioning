# Video Storyboard & Generation

## Description
The **Video Storyboard & Generation** app is an advanced workflow tool that transforms static images into video concepts. It uses a multi-agent system (CrewAI) to analyze an input image, brainstorm video ideas, and generate detailed prompts. These prompts are then sent to **Kling AI** (via a self-hosted ComfyUI instance) to generate high-quality videos. The app also handles batch processing and video merging.

## Architecture / Processing Flow

1.  **Configuration**:
    *   User selects a "KOL Persona" and edits the backstories/tasks for the AI Agents (Analyst, Concept, Prompt) in the **Workflow Configuration Studio**.

2.  **Input Selection**:
    *   User selects a source image (Frame 0) either from the "Results Gallery" (previous outputs) or by uploading a custom file.

3.  **Draft Generation (`VideoStoryboardWorkflow`)**:
    *   **Analyst Agent**: Analyzes the visual elements of the source image.
    *   **Concept Agent**: Brainstorms creative video motion concepts based on the analysis and persona.
    *   **Prompt Agent**: Converts concepts into technical video generation prompts compatible with Kling AI.
    *   *Result*: A list of variations (Prompt + Concept Name).

4.  **Video Generation (ComfyUI / Kling)**:
    *   User queues a single variation or a full batch.
    *   The app sends requests to the `ComfyUIClient`, which interfaces with the Kling AI node.
    *   **Task IDs** are returned and logged to the `VideoLogsStorage` database.

5.  **Monitoring & Delivery**:
    *   The app polls the status of queued tasks.
    *   Upon completion, it downloads the video files from the ComfyUI server to the local machine.
    *   **Merge**: Optionally merges all successful videos from a batch into a single compilation file using `moviepy`.

## Functions/Features

*   **Workflow Configuration Studio**: A UI to directly edit the text prompts and backstories for the CrewAI agents, allowing for rapid prompt engineering.
*   **AI Storyboarder**: Automatically generates multiple video concepts from a single image.
*   **Kling AI Integration**: Seamless connection to Kling AI via ComfyUI for state-of-the-art video generation.
*   **Batch Queueing**: One-click execution to generate videos for all drafted variations simultaneously.
*   **Batch Recovery**: Detects incomplete batches in the database and allows resuming monitoring/downloading.
*   **Auto-Merge**: Automatically stitches together all generated videos in a batch for easy previewing.
*   **History Log**: Tracks all generation attempts, their status, and prompts in a local SQLite database.

## Backlog

*   **Custom Aspect Ratios**: Add controls for video aspect ratio (currently defaults to source).
*   **Retry Logic**: Auto-retry failed Kling AI tasks.
*   **Prompt Editing**: Allow manual editing of generated prompts before queueing.
*   **Video Preview**: Better integrated video player for batch reviews.

## Deployment Infrastructure

*   **Container**: Docker container based on `python:3.11-slim`.
*   **Service Name**: `video` (in `docker-compose.yml`).
*   **Port**: Exposed on port **8503** (mapped from container port 8501).
*   **Dependencies**: Requires a running ComfyUI instance with Kling AI nodes installed and accessible via network.

## Secrets/Keys

*   `OPENAI_API_KEY`: Required for the CrewAI agents (GPT-4o) to generate concepts.
*   `KLING_ACCESS_KEY` & `KLING_SECRET_KEY`: Credentials for the Kling AI API.
*   `COMFYUI_API_URL`: Address of the ComfyUI server.
*   `COMFYUI_API_KEY`: Authentication for the ComfyUI server (if secured).

## Development Environment

*   **Language**: Python 3.11
*   **Framework**: Streamlit
*   **Key Libraries**:
    *   `crewai`: Orchestrating the AI agents.
    *   `moviepy`: Merging video files.
    *   `requests` / `aiohttp`: API communication with ComfyUI.
    *   `pandas`: displaying history tables.
