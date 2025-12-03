# KOL Agent Workflow Documentation

This document outlines the complete flow, hierarchy, and architecture of the KOL Agent system, specifically focusing on the image-to-prompt and image generation workflows.

## 1. System Overview

The system is designed to automate the process of generating high-quality, persona-consistent images for marketing campaigns. It leverages:
- **Streamlit** for the user interface.
- **CrewAI** for orchestrating AI agents (Visual Analysts, Prompt Engineers, Photographers).
- **ComfyUI** for the actual image generation using Stable Diffusion/Flux models.
- **OpenAI GPT-4o** for vision analysis and prompt engineering.

## 2. Directory Structure & Key Components

```
d:/sem 2 2025/Athena/ff/variations_mood/
├── app.py                          # MAIN ENTRY POINT: Streamlit UI
├── scripts/                        # Executable workflow scripts
│   ├── crewai_image_prompt_workflow.py # CLI for Image-to-Prompt (CrewAI)
│   ├── crewai_mood_variations.py       # CLI for Mood Variations (CrewAI)
│   ├── queue_prompts_from_archive.py   # Queues prompts from 'ready' to ComfyUI
│   └── populate_generated_images.py    # Downloads results to 'crawl_archive'
├── src/                            # Core source code
│   ├── workflows/                  # Workflow class definitions
│   │   └── image_to_prompt_workflow.py # Core logic for App's prompt gen
│   ├── tools/                      # Agent tools
│   │   ├── vision_tool.py          # Vision analysis (GPT-4o)
│   │   └── generate_image_tool.py  # Image generation wrapper
│   ├── third_parties/              # External API clients
│   │   └── comfyui_client.py       # ComfyUI API client
│   └── personas/                   # Persona data management
│       ├── loader.py               # CSV/DB loader
│       └── models.py               # Data models
└── crawl/, ready/, crawl_archive/  # Data directories
```

## 3. Workflow 1: Image-to-Prompt (Main UI Flow)

This is the primary workflow exposed in `app.py`. It takes reference images and converts them into optimized prompts for the "Instagirl WAN2.2" model.

### **Step-by-Step Flow:**

1.  **Ingestion (Streamlit UI)**
    *   User uploads images via the "Workspace" tab in `app.py`.
    *   Images are saved to the `crawl/` directory.

2.  **Analysis & Prompt Generation**
    *   **Trigger**: User clicks "Generate Prompts (Step 1)".
    *   **Logic**: `app.py` calls `src.workflows.image_to_prompt_workflow.ImageToPromptWorkflow`.
    *   **Agents Involved**:
        *   `Lead Visual Analyst`: Uses `VisionTool` (GPT-4o) to analyze the image (outfit, pose, setting, lighting) objectively.
        *   `Instagirl WAN2.2 Prompt Specialist`: Converts the analysis into a strict comma-separated keyword prompt, applying specific style guides (daily/casual vibe, 700-800 chars) and mandatory overrides (specific hairstyles, trigger words).
    *   **Output**: Generated text prompts are saved as `.txt` files in the `ready/` directory.

3.  **Queueing Generation**
    *   **Trigger**: User clicks "Queue Generation (Step 2)".
    *   **Logic**: Executes `scripts/queue_prompts_from_archive.py`.
    *   **Action**: Reads prompts from `ready/` and sends API requests to the ComfyUI server via `ComfyUIClient`.

4.  **Retrieval & Archiving**
    *   **Trigger**: User clicks "Populate Results (Step 3)".
    *   **Logic**: Executes `scripts/populate_generated_images.py`.
    *   **Action**: Checks ComfyUI for completed jobs, downloads generated images, and moves the original source image, prompt file, and result image to `crawl_archive/`.

## 4. Workflow 2: Mood Variations (CLI/Script)

This workflow (`scripts/crewai_mood_variations.py`) is designed to generate a cohesive set of 5 images based on a single "Mood" definition from the database.

### **Hierarchy & Agents:**

*   **Input**: Persona ID and Mood Number.
*   **Database**: Fetches structured mood data (keywords for clothes, setting, lighting, props).

1.  **Visual Continuity Director (Agent)**
    *   **Goal**: Define a single "Master Scene" (Activity, Outfit, Setting, Lighting) based *purely* on the database mood keywords.
    *   **Output**: A cohesive scene description.

2.  **Editorial Photographer (Agent)**
    *   **Goal**: Plan 5 distinct camera shots (angles, crops, gazes) for that specific Master Scene.
    *   **Output**: A list of 5 shot definitions (e.g., Establishing Shot, Close-up, Low angle).

3.  **Technical Keyword Prompt Specialist (Agent)**
    *   **Goal**: Convert each shot definition into a strict Stable Diffusion prompt.
    *   **Logic**: Combines Master Scene keywords + Shot specific keywords + Technical/Lighting keywords. Applies rigorous formatting (no sentences, only keywords).

4.  **Authentic Voice Caption Writer (Agent)**
    *   **Goal**: Write a natural social media caption for each shot.

### **Output:**
*   A structured JSON/Dictionary containing the Master Scene, 5 Shot Plans, 5 Final Prompts, and 5 Captions.

## 5. Key Dependencies & Integrations

*   **ComfyUI**: The backend engine for image generation. The system assumes a ComfyUI instance is running and accessible (URL configured in `.env`).
*   **OpenAI GPT-4o**: Used for all intelligent tasks: vision analysis, reasoning, prompt engineering, and captioning.
*   **CrewAI**: Framework for defining agents, tasks, and sequential processes.
*   **Google Cloud Storage (Optional)**: `generate_image_tool.py` supports uploading results to GCS if configured.

## 6. Data Flow Diagram (Conceptual)

```mermaid
graph TD
    User[User (Streamlit UI)] -->|Uploads Images| CrawlDir[crawl/ folder]
    
    subgraph "Phase 1: Analysis"
        CrawlDir --> ImageToPromptWF[ImageToPromptWorkflow]
        ImageToPromptWF --> Analyst[Agent: Visual Analyst]
        Analyst -->|Vision Analysis| Engineer[Agent: Prompt Engineer]
        Engineer -->|Generated Prompt| ReadyDir[ready/ folder]
    end
    
    subgraph "Phase 2: Generation"
        ReadyDir --> QueueScript[queue_prompts.py]
        QueueScript -->|API Request| ComfyUI[ComfyUI Server]
        ComfyUI -->|Generation| ComfyQueue[Generation Queue]
    end
    
    subgraph "Phase 3: Retrieval"
        PopulateScript[populate_images.py] -->|Poll Status| ComfyUI
        ComfyUI -->|Download Image| PopulateScript
        PopulateScript -->|Archive All| ArchiveDir[crawl_archive/ folder]
    end
    
    ArchiveDir -->|Display| User
