# Workspace App Analysis & System Design

This document provides a comprehensive technical analysis of the Workspace App (`apps/workspace_app.py` / `app.py`), covering architecture, features, debt, and deployment.

---

## 📂 Phase 1: Architecture & Processing Flow

### Component Map
The application follows a **Streamlit-driven micro-service style architecture**, orchestrated via Python scripts and relying on external AI services.

1.  **Frontend / UI**: `app.py` (Main Entry) & `apps/workspace_app.py`
    *   **Role**: User interface for configuration, monitoring, and triggering workflows.
    *   **Tech**: Streamlit.
2.  **Logic Engine / Orchestrator**: `src/workflows/image_to_prompt_workflow.py`
    *   **Role**: Handles the "business logic" of analyzing images (Vision) and crafting prompts (CrewAI Agents).
    *   **Key Dependencies**: `src/tools/vision_tool.py` (Vision), `crewai` (Agents).
3.  **Execution Engine**: `src/third_parties/comfyui_client.py`
    *   **Role**: Interface for the image generation backend. Handles queuing, polling, and downloading.
    *   **External Service**: ComfyUI (Local or Cloud).
4.  **Database**: `src/database/image_logs_storage.py`
    *   **Role**: Persistent state tracking for executions.
    *   **Tech**: SQLite (`image_logs.db`).
5.  **Task Scripts**: `scripts/process_and_queue.py`, `scripts/populate_generated_images.py`
    *   **Role**: Bridges the UI and the backend logic, handling file operations and batch loops.

### Data Life Cycle: Single User Request
**Scenario**: User processes a batch of images for the "Jennie" persona.

1.  **Input**: User places images in `Sorted/` directory. UI reflects this count.
2.  **Trigger**: User clicks **"Start Processing & Queueing"** in `apps/workspace_app.py`.
3.  **Execution (`scripts/process_and_queue.py`)**:
    *   **File Move**: Image moved from `Sorted/` $\rightarrow$ `processed/` (renamed to `ref_{timestamp}_{uuid}.ext`).
    *   **Vision Analysis**: Calls `ImageToPromptWorkflow`. `VisionTool` sends image to **OpenAI/Grok/Gemini API**.
    *   **Prompt Gen**: CrewAI Agents (Analyst + Engineer) generate a text prompt based on vision analysis.
    *   **Queueing**: Calls `ComfyUIClient.generate_image`. Sends payload to **ComfyUI API** (`/prompt` or `/executions`).
    *   **Logging**: Records `execution_id`, `prompt`, and `pending` status to `image_logs.db`.
4.  **Retrieval**: User clicks **"Download Completed Results"**.
5.  **Completion (`scripts/populate_generated_images.py`)**:
    *   **Polling**: Queries `image_logs.db` for `pending` items.
    *   **Status Check**: Calls `ComfyUIClient.check_status`.
    *   **Download**: If status is `completed`, downloads image bytes from ComfyUI.
    *   **Save**: Writes file to `results/result_{base_name}.png`.
    *   **Update**: Updates DB status to `completed` and saves local path.

### Third-Party Touchpoints
| Service | Purpose | Handling Script/Module |
| :--- | :--- | :--- |
| **OpenAI / xAI / Google** | Vision Analysis (GPT-4o, Grok, Gemini) | `src/tools/vision_tool.py`, `src/config.py` |
| **ComfyUI** | Image Generation Engine | `src/third_parties/comfyui_client.py` |
| **CrewAI** | Agentic Prompt Engineering | `src/workflows/image_to_prompt_workflow.py` |
| **Google Cloud Storage** | (Optional) Image Backup/Hosting | `src/third_parties/gcs_client.py` |

### Error Handling
*   **Vision Failure**: If the Vision API fails or refuses content, `ImageToPromptWorkflow` raises a `ValueError`. The script catches this, logs the error (`❌ Error processing...`), and skips to the next image in the batch.
*   **ComfyUI Connection**: `ComfyUIClient` implements **exponential backoff** (retries) for network requests. If max retries are exceeded, it raises `ComfyUIError`.
*   **Generation Failure**: If ComfyUI reports a `failed` status during polling, the database record is updated to `failed` to prevent infinite checking.

---

## 🛠 Phase 2: Functions & Features

### Core Utility
**Automated Fashion/Lifestyle Image Reproduction**: The app takes reference photos (e.g., influencers, fashion shots), analyzes them using Vision AI to understand pose/outfit/setting, and automatically generates high-fidelity prompts to recreate them using specific "Personas" (LoRA models) in ComfyUI.

### Edge-Case Features
*   **Persona Editor**: A dedicated UI in the sidebar/expander to edit specific persona traits (e.g., hair color) and modify the underlying prompt templates (`analyst_task.txt`, `turbo_agent.txt`) without touching code.
*   **Live "Laboratory"**: A "Live Tester" section allows users to upload a single test image and see the raw Vision analysis and generated prompt immediately, without queuing a job.
*   **Multi-Model Vision**: Dropdown support to switch Vision providers on the fly (GPT-4o, Grok-2, Gemini 1.5).
*   **Input Management**: Built-in file browser to view, select, and bulk-delete images from the input directory.

### Input/Output Specs
*   **Input**:
    *   **Format**: Image files (`.png`, `.jpg`, `.jpeg`, `.webp`).
    *   **Location**: Local directory `Sorted/`.
*   **Output**:
    *   **Format**: Generated Image (`.png`).
    *   **Location**: Local directory `results/`.
    *   **Metadata**: SQLite record linking the result to the reference image and prompt.

### Admin/Dev Features
*   **Queue Monitor**: Real-time display of ComfyUI's internal queue (Running/Pending jobs) directly in the Streamlit UI.
*   **Execution History**: Table view of recent database entries showing execution IDs and status.
*   **Live Logs**: When processing starts, a custom `StreamlitLogHandler` redirects Python logs to a UI widget for real-time feedback.

---

## 📝 Phase 3: Backlog & Known Issues

### The "TODO" Scan
**Status: Clean.**
A comprehensive scan of the codebase revealed **zero** explicit `TODO`, `FIXME`, or `PENDING` comments in the active source code. This suggests either a very clean codebase or, more likely, a lack of inline technical debt tracking.

### Logic Gaps & Refactor Needs
*   **Unused Dependencies**: `requirements.txt` includes `fastapi`, `uvicorn`, `psycopg2-binary`. The app currently runs purely on `streamlit` and `sqlite3`. These should be removed to slim down the image or implemented if an API layer is intended.
*   **Synchronous Polling**: The "Download" action (`populate_generated_images.py`) runs synchronously. If there are hundreds of pending images, the UI might hang or timeout while waiting for the script to finish checking all statuses.
    *   *Recommendation*: Move polling to a background daemon or use `st.status` with smaller batches.

### Scalability Warnings
*   **SQLite Locking**: The app uses a local SQLite database file. If multiple users or concurrent scripts try to write (e.g., rapid processing + downloading simultaneously), this will hit database locks.
*   **Local Filesystem Dependency**: The architecture assumes `Sorted/`, `processed/`, and `results/` are local folders. This breaks immediately if the app is scaled to multiple containers without a shared Network File System (NFS) or Volume.
*   **State Management**: `process_and_queue.py` relies on the Streamlit session staying alive or the script finishing. If the container restarts, in-progress logic (moving files, waiting for vision) is lost.

### Security Holes
*   **Hardcoded Workflow IDs**: `src/third_parties/comfyui_client.py` contains hardcoded UUIDs for ComfyUI workflows. If the ComfyUI server is reset or workflows are re-imported with new IDs, the app will break.
*   **Static Persona Mappings**: LoRA filenames are hardcoded in a dictionary in Python code. Adding a new persona requires a code deployment, not just a config change.

---

## 🚀 Phase 4: Deployment & Infrastructure

### Environment Requirements
*   **Language**: Python 3.11
*   **Runtime**: Docker (Debian-based slim image).
*   **Core Libraries**: `streamlit`, `crewai`, `openai`, `httpx`.

### Infrastructure Assumptions
*   **ComfyUI Availability**: The code assumes a ComfyUI instance is reachable at `http://127.0.0.1:8188` (default) or the URL defined in `COMFYUI_API_URL`.
*   **Volume Mounts**: The container **must** have persistent volumes mounted at:
    *   `/app/Sorted` (Input)
    *   `/app/processed` (Archived Inputs)
    *   `/app/results` (Outputs)
    *   `/app/database` (SQLite DB persistence)
    *   `/app/prompts` (Template persistence)

### Containerization
*   **Dockerfile**: Present. Exposes port `8501`.
*   **Compose**: `docker-compose.yml` is present (implied by context), likely orchestrating this app alongside ComfyUI or a database.
*   **Networking**: The app listens on `0.0.0.0`, making it accessible externally.

### Secrets Management
*   **Method**: Environment Variables loaded via `python-dotenv` (`.env` file).
*   **Key Secrets**:
    *   `OPENAI_API_KEY` / `GROK_API_KEY` (AI Vision)
    *   `COMFYUI_API_URL` (Backend connection)
    *   `POSTGRES_*` (Database credentials - optional/unused currently)
