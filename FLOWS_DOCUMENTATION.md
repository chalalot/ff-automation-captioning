# Application Flows Documentation

This document outlines the detailed steps and logic for the system architecture and key user flows for the `ff-automation-captioning` project. These descriptions serve as a blueprint for drawing corresponding flowchart diagrams. Emphasis has been placed on capturing recent code optimizations including **Sticky Configs**, **Lazy Loading**, **Thumbnails**, and **UI Logging/Polling**.

---

## 1. General Architecture Flow (For Developers)

**Purpose**: To illustrate the high-level system structure, demonstrating how frontend apps interact with background tasks and external APIs.

### Details & Justification:
*   **Frontend Layer (Streamlit App)**: The user interacts with multi-page Streamlit apps (`1_workspace_app.py`, `2_gallery_app.py`, etc.). The frontend collects user inputs, applies sticky configurations (recently added to retain context across sessions), and prepares task payloads.
*   **Task Queuing (Celery & Redis)**: Streamlit sends heavy execution jobs to a Celery worker (`celery_app.py` & `tasks.py`) via a message broker (like Redis). This decoupling ensures the Streamlit UI remains responsive during long-running generation tasks.
*   **Execution & External APIs**: The Celery workers interface with third-party APIs such as ComfyUI/ComfyCloud (`comfyui_client.py`) for image generation and Kling API (`kling_client.py`) for video processing. Recent updates integrated **UI Logging and Polling**, allowing the frontend to poll status directly from the client wrappers while Celery manages the job asynchronously.
*   **Data Storage**:
    *   **SQLite/Database**: Execution metadata, run status, prompt details, and user feedback (approvals/disapprovals) are stored via `db_utils.py` and dedicated storage wrappers (`runs_posts_storage.py`, `image_logs_storage.py`).
    *   **Google Cloud Storage (GCS)**: Generated images and media are uploaded to GCS (`gcs_client.py`). The gallery fetches URLs or objects directly from here, recently optimized with pre-generated thumbnails for faster loading.

---

## 2. Workspace User Flow 1: Configuration & Templating Setup

**Purpose**: Maps the user's journey of preparing the environment, adjusting agent prompts, and setting up the generation context before queuing tasks.

### Details & Justification:
1.  **Start Workspace Application**: User opens the "Workspace" tab in the Streamlit interface.
2.  **Load System Context**: The application checks for previously saved session states or defaults.
3.  **Apply Sticky Configs (Recent Optimization)**: The app automatically populates prompts, selected LoRAs, and resolution settings from the user's last session or page visit. This prevents repetitive manual entry.
4.  **Edit Agent Prompts & Parameters**: The user reviews the pre-filled "Sticky Configs" and manually tweaks the base agent prompts, negative prompts, or model parameters (e.g., selecting readable LoRA combinations).
5.  **Save/Confirm Configuration**: The user commits the template or settings for the current session. The system updates the Streamlit session state and persists the sticky config for future loads.

---

## 3. Workspace User Flow 2: Execution Queueing & Monitoring

**Purpose**: Maps how a user takes their configured workspace, provides reference images, queues multiple task variations, and tracks the progress.

### Details & Justification:
1.  **Reference Input**: User uploads or selects reference images from the UI to be used as base inputs for generation.
2.  **Define Variations**: User selects variations for the run (e.g., trying different LoRAs, aspect ratios, or prompt adjustments against the reference images).
3.  **Initiate Execution (Queueing)**: User clicks the "Queue Tasks" button.
4.  **Dispatch to Celery**: The Streamlit backend packages the configurations, references, and variations into distinct jobs and pushes them to the Celery task queue.
5.  **UI Logging & Polling (Recent Optimization)**: Instead of a silent wait, the UI now actively polls the execution status (`comfyui_client.py`). The user sees real-time log updates and progress bars in the Streamlit app showing exactly which variation is currently processing, queuing, or fetching output.
6.  **Task Completion**: Once the API finishes, the worker saves the output metadata to the SQLite Database and the generated image/video to Google Cloud Storage. The UI updates the final status to "Completed".

---

## 4. Gallery User Flow 1: Browsing & Lazy Loading Outputs

**Purpose**: Details how the Gallery application efficiently presents massive amounts of generated media to the user.

### Details & Justification:
1.  **Open Gallery App**: User navigates to the Gallery page (`2_gallery_app.py`) to review past executions.
2.  **Query Database**: The application queries the backend database for recent "Runs" and associated generated image records based on selected filters (date, status, run ID).
3.  **Trigger Lazy Loading (Recent Optimization)**: Rather than fetching full-resolution images for the entire query result, the app uses a lazy-loading mechanism.
4.  **Fetch Thumbnails (Recent Optimization)**: For the visible grid, the system requests lightweight thumbnails from GCS instead of the massive raw generation files, drastically cutting down initial page load time and memory usage.
5.  **Render UI**: The user views a responsive grid of thumbnails representing the tasks that were queued in the Workspace. As the user scrolls, more thumbnails are lazy-loaded.

---

## 5. Gallery User Flow 2: Curation & Feedback (Approve/Disapprove)

**Purpose**: Maps the user's interaction for curating the outputs, which directly impacts downstream workflows (like social media posting or retraining).

### Details & Justification:
1.  **Select Media**: The user clicks on a thumbnail from the lazy-loaded Gallery grid to view the full-resolution generated output and its associated generation parameters (prompt, LoRA, seed).
2.  **Evaluate Output**: The user evaluates the quality of the generated output against the initial prompt.
3.  **Action: Approve or Disapprove**:
    *   **Approve**: User clicks the "Approve" button. The Streamlit app sends an update to the Database, marking the specific `image_id` or `run_id` as approved.
    *   **Disapprove/Delete**: User clicks "Disapprove". The database record is marked as rejected (and optionally, the file is flagged for deletion in GCS).
4.  **UI State Update**: The UI refreshes to show the new state. Approved images might move to a "Curated" bucket or tab, while disapproved images are hidden from the main view.
5.  **End Flow**: The curated assets are now ready for the next stage (e.g., passing to the Video storyboard or automated social posting).