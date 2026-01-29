# Workspace: Input & Generation

## Description
The **Workspace App** is the central command center for the project. It handles the core "Image-to-Prompt" workflow, where input images are analyzed by AI agents to generate high-quality prompts. It supports multiple state-of-the-art vision models (GPT-4o, Grok, Gemini) and workflow types (Turbo, WAN2.2). It also provides advanced tools for configuring AI personas, managing input datasets, and monitoring system health.

## Architecture / Processing Flow

1.  **Configuration**:
    *   **Persona Config**: User defines/edits personas (e.g., hair color, style) via the Persona Editor.
    *   **Workflow Studio**: User edits the "Turbo" or "Analyst" agent templates (backstories, constraints) and can create new Persona Types.
    *   **Settings**: User selects Vision Model, Model Strength, Dimensions, and Seed Strategy.

2.  **Input Management**:
    *   Images are placed in the `Sorted/` directory (mapped to `INPUT_DIR`).
    *   The app displays these images in a grid, allowing users to review and delete them before processing.
    *   **Upload**: Users can upload new images directly via the UI.

3.  **Generation Loop (`scripts/process_and_queue.py`)**:
    *   **Trigger**: User clicks "Start Processing".
    *   **Workflow**: For each image in the batch:
        1.  **Analyst Agent**: Describes the input image using the selected Vision Model.
        2.  **Turbo Agent**: Uses the description + Persona rules + Templates to generate a specific Stable Diffusion prompt.
    *   **Queue**: The generated prompt is sent to the ComfyUI API.
    *   **Move**: The source image is moved from `Sorted/` to `processed/`.
    *   **Log**: Execution details are saved to the SQLite database.

4.  **Result Retrieval**:
    *   User clicks "Download Completed Results".
    *   The app checks the status of pending jobs in ComfyUI.
    *   Completed images are downloaded to `results/`.

## Functions/Features

*   **Multi-Model Vision**: Choose between **ChatGPT (gpt-4o)**, **Grok (xAI)**, or **Gemini 1.5** for image analysis.
*   **Workflow Types**: Support for different generation strategies (e.g., "Turbo", "WAN2.2").
*   **Persona Editor**: Visual interface to create new Persona Types and modify attributes (hair color, keywords) without touching JSON files.
*   **Workflow Configuration Studio**: Advanced editor for the CrewAI agent prompts, supporting "Analyst" and "Turbo" agent customization.
*   **Live Tester**: Upload a single test image to run the full analysis-to-prompt loop and view raw agent outputs in real-time.
*   **Input Manager**: File browser for the input directory with batch delete and upload capabilities.
*   **System Status**: Real-time dashboard showing the ComfyUI queue size (Running/Pending) and recent database entries.
*   **Batch Processing**: Run the workflow on massive datasets with custom limits, strength settings, and seed strategies.

## Backlog

*   **Job Cancellation**: Ability to cancel running ComfyUI jobs directly from the dashboard.
*   **Advanced Scheduling**: Schedule batches to run at specific times.
*   **Multi-Select Processing**: Select specific images to process instead of just "next N".
*   **Visual Diff**: Compare different model outputs side-by-side.

## Deployment Infrastructure

*   **Container**: Docker container based on `python:3.11-slim`.
*   **Service Name**: `workspace` (in `docker-compose.yml`).
*   **Port**: Exposed on port **8501** (mapped from container port 8501).
*   **Volumes**: Maps `Sorted/` (Input), `processed/` (Archive), `results/` (Output), `prompts/` (Config), and databases.

## Secrets/Keys

*   `OPENAI_API_KEY`: Required for GPT-4o vision and agent reasoning.
*   `GROK_API_KEY`: Required if using Grok vision models.
*   `GEMINI_API_KEY`: Required if using Google Gemini models.
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
