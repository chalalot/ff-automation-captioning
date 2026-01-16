# Workspace: Input & Generation

## Description
The **Workspace App** is the central command center for the project. It handles the core "Image-to-Prompt" workflow, where input images are analyzed by AI agents to generate high-quality prompts, which are then queued for image generation in ComfyUI. It also provides tools for configuring AI personas, managing input datasets, and monitoring system health.

## Architecture / Processing Flow

1.  **Configuration**:
    *   **Persona Config**: User defines/edits personas (e.g., hair color, style) via `WorkflowConfigManager`.
    *   **Workflow Config**: User edits the "Turbo" or "Analyst" agent templates (backstories, constraints).

2.  **Input Management**:
    *   Images are placed in the `Sorted/` directory (mapped to `INPUT_DIR`).
    *   The app displays these images in a grid, allowing users to review and delete them before processing.

3.  **Generation Loop (`scripts/process_and_queue.py`)**:
    *   **Trigger**: User clicks "Start Processing".
    *   **Workflow**: For each image in the batch:
        1.  **Analyst Agent**: Describes the input image.
        2.  **Turbo Agent**: Uses the description + Persona rules + Templates to generate a specific Stable Diffusion prompt.
    *   **Queue**: The generated prompt is sent to the ComfyUI API.
    *   **Move**: The source image is moved from `Sorted/` to `processed/`.
    *   **Log**: Execution details are saved to the SQLite database.

4.  **Result Retrieval**:
    *   User clicks "Download Completed Results".
    *   The app checks the status of pending jobs in ComfyUI.
    *   Completed images are downloaded to `results/`.

## Functions/Features

*   **Persona Editor**: Visual interface to modify persona attributes (hair color, specific keywords) without touching JSON files.
*   **Workflow Studio**: Advanced editor for the CrewAI agent prompts (Analyst & Turbo), with support for template variables.
*   **Live Tester**: Upload a single test image to run the full analysis-to-prompt loop and view the raw agent outputs (logs) in real-time.
*   **Input Manager**: file browser for the input directory with batch delete capabilities.
*   **System Status**: Real-time dashboard showing the ComfyUI queue size (Running/Pending) and recent database entries.
*   **Batch Processing**: Run the workflow on hundreds of images with a single click, with progress tracking.

## Backlog

*   **Job Cancellation**: Ability to cancel running ComfyUI jobs directly from the dashboard.
*   **Dynamic Workflows**: Support for selecting different ComfyUI workflows (json files) from the UI.
*   **Advanced Scheduling**: Schedule batches to run at specific times.
*   **Multi-Select Processing**: Select specific images to process instead of just "next N".

## Deployment Infrastructure

*   **Container**: Docker container based on `python:3.11-slim`.
*   **Service Name**: `workspace` (in `docker-compose.yml`).
*   **Port**: Exposed on port **8501** (mapped from container port 8501).
*   **Volumes**: Maps `Sorted/` (Input), `processed/` (Archive), and `results/` (Output).

## Secrets/Keys

*   `OPENAI_API_KEY`: Critical for the "Analyst" and "Turbo" agents.
*   `COMFYUI_API_URL`: Connection to the generation engine.
*   `COMFYUI_API_KEY`: Authentication for the generation engine.

## Development Environment

*   **Language**: Python 3.11
*   **Framework**: Streamlit
*   **Key Libraries**:
    *   `crewai`: Agent orchestration.
    *   `streamlit`: User interface.
    *   `pandas`: Status tables.
    *   `python-dotenv`: Environment configuration.
