# Migration Plan: Streamlit → FastAPI + React

**Project**: ff-automation-captioning → ff-auto
**Priority**: Workspace App + Gallery App (core image pipeline)
**Task Queue**: Keep Celery + Redis
**Date**: March 24, 2026

---

## 1. Architecture Overview

### Current (Streamlit Monolith)
```
┌─────────────────────────────────┐
│   Streamlit (UI + Logic + State)│
│  ┌───────────┐ ┌──────────────┐ │
│  │ Workspace  │ │   Gallery    │ │
│  │ Video App  │ │  Monitor App │ │
│  └─────┬──────┘ └──────┬───────┘ │
│        │               │          │
│  ┌─────▼───────────────▼───────┐ │
│  │  Direct function calls      │ │
│  │  (ComfyUI, Kling, CrewAI)  │ │
│  └─────────────┬───────────────┘ │
└────────────────┼─────────────────┘
                 │
        ┌────────▼────────┐
        │ Celery + Redis  │
        │ SQLite / PG     │
        └─────────────────┘
```

### Target (FastAPI + React)
```
┌──────────────────┐       ┌──────────────────────────┐
│   React SPA      │ HTTP  │   FastAPI Backend         │
│                  │◄─────►│                            │
│  Workspace Page  │  WS   │  /api/workspace/*          │
│  Gallery Page    │◄─────►│  /api/gallery/*            │
│  (Video Page)    │       │  /api/videos/*             │
│  (Monitor Page)  │       │  /api/monitor/*            │
└──────────────────┘       │                            │
                           │  Services Layer             │
                           │  ├─ ImageProcessingService  │
                           │  ├─ GalleryService          │
                           │  ├─ ComfyUIService          │
                           │  └─ ConfigService           │
                           │                             │
                           │  Celery + Redis (unchanged) │
                           │  Database (SQLite → PG)     │
                           └─────────────────────────────┘
```

---

## 2. What Stays the Same (Zero Changes)

These modules are already framework-agnostic and can be reused as-is:

| Module | Path | Notes |
|--------|------|-------|
| ComfyUI Client | `src/third_parties/comfyui_client.py` | Async httpx, no Streamlit deps |
| Kling Client | `src/third_parties/kling_client.py` | Pure Python + JWT |
| GCS Client | `src/third_parties/gcs_client.py` | google-cloud-storage only |
| CrewAI Workflows | `src/workflows/*.py` | Framework-agnostic |
| Vision/Audio Tools | `src/tools/*.py` | Pure API calls |
| Image Filters | `src/utils/image_filters.py` | Pillow only |
| Video Utils | `src/utils/video_utils.py` | moviepy only (remove StreamlitLogger) |
| Audio Utils | `src/utils/audio_utils.py` | pydub only |
| Constants | `utils/constants.py` | Pure data |
| Celery App | `celery_app.py` | Already standalone |
| Celery Tasks | `tasks.py` | Already standalone |
| Config Manager | `src/workflows/config_manager.py` | File-based, no UI deps |
| GlobalConfig | `src/config.py` | Remove Streamlit secrets fallback |

**Key insight**: ~70% of your backend logic is already decoupled. The migration is primarily about extracting the UI logic from the Streamlit apps into API endpoints + React components.

---

## 3. Phase 1 — Backend: FastAPI API Layer

### 3.1 Project Structure

```
ff-auto/
├── backend/
│   ├── main.py                      # FastAPI app entry
│   ├── config.py                    # GlobalConfig (cleaned, no Streamlit)
│   ├── celery_app.py                # ← copy as-is
│   ├── tasks.py                     # ← copy as-is
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                  # Dependency injection (DB, services)
│   │   ├── workspace.py             # POST /process, GET /queue, GET /presets
│   │   ├── gallery.py               # GET /images, POST /approve, POST /reject
│   │   ├── monitor.py               # GET /health, GET /queues
│   │   └── config.py                # GET/PUT /personas, GET /presets
│   │
│   ├── models/                      # Pydantic schemas
│   │   ├── workspace.py             # ProcessImageRequest, QueueStatusResponse
│   │   ├── gallery.py               # ImageItem, ApprovalRequest, GalleryResponse
│   │   ├── monitor.py               # SystemHealth, QueueStats
│   │   └── config.py                # PersonaConfig, PresetConfig
│   │
│   ├── services/                    # Business logic (extracted from Streamlit apps)
│   │   ├── image_processing.py      # Queue management, file moves, rename
│   │   ├── gallery.py               # List/filter/paginate, approve/reject, thumbnails
│   │   ├── monitor.py               # System metrics, queue polling
│   │   └── config.py                # Persona CRUD, preset management
│   │
│   ├── database/                    # ← copy from src/database/
│   │   ├── image_logs_storage.py
│   │   ├── video_logs_storage.py
│   │   └── db_utils.py
│   │
│   ├── third_parties/               # ← copy from src/third_parties/
│   │   ├── comfyui_client.py
│   │   ├── comfyui_queue_manager.py
│   │   ├── kling_client.py
│   │   └── gcs_client.py
│   │
│   ├── workflows/                   # ← copy from src/workflows/
│   │   ├── image_to_prompt_workflow.py
│   │   ├── video_storyboard_workflow.py
│   │   ├── music_analysis_workflow.py
│   │   └── config_manager.py
│   │
│   ├── tools/                       # ← copy from src/tools/
│   │   ├── vision_tool.py
│   │   └── audio_tool.py
│   │
│   └── utils/
│       ├── constants.py
│       ├── image_filters.py
│       ├── video_utils.py
│       └── audio_utils.py
│
├── frontend/                        # React app (see Phase 2)
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── .env
```

### 3.2 API Endpoints — Workspace

These replace the logic currently embedded in `1_workspace_app.py`:

```
GET    /api/workspace/input-images
       → List images in INPUT_DIR (Sorted/) with metadata
       → Returns: [{filename, path, size, modified_at, thumbnail_url}]

POST   /api/workspace/process
       → Trigger image processing (replaces Celery task dispatch in Streamlit)
       → Body: {image_path, persona, workflow_type, vision_model,
                variation_count, strength, seed_strategy, base_seed,
                width, height, lora_name, clip_model_type}
       → Returns: {task_id} (Celery task ID)

GET    /api/workspace/task/{task_id}/status
       → Poll Celery task state (replaces st.session_state polling)
       → Returns: {state, status_message, progress, result}

POST   /api/workspace/process-batch
       → Batch process multiple images
       → Body: {image_paths[], ...shared_config}
       → Returns: {task_ids[]}

GET    /api/workspace/comfyui-queue
       → Get ComfyUI queue status (running + pending jobs)
       → Returns: {running: [], pending: [], counts: {}}

GET    /api/workspace/executions
       → Recent execution history
       → Query: ?limit=50&status=pending
       → Returns: [{execution_id, prompt, persona, status, created_at}]
```

### 3.3 API Endpoints — Gallery

These replace the logic in `2_gallery_app.py`:

```
GET    /api/gallery/images
       → Paginated image listing with filtering
       → Query: ?status=pending|approved|disapproved
                &page=1&per_page=20
                &group_by=date|batch|none
                &sort=newest|oldest
       → Returns: {items: [{filename, path, thumbnail_url, created_at,
                            metadata: {seed, prompt, persona}}],
                   total, page, pages}

GET    /api/gallery/images/{filename}/thumbnail
       → Serve cached thumbnail (512x512 JPEG)
       → Returns: image/jpeg binary

GET    /api/gallery/images/{filename}/metadata
       → Extract ComfyUI metadata from PNG
       → Returns: {seed, prompt, workflow, persona, ref_image}

POST   /api/gallery/approve
       → Approve one or more images
       → Body: {filenames: [], rename_map: {old: new}}
       → Moves files from results/ → results/approved/

POST   /api/gallery/disapprove
       → Reject images
       → Body: {filenames: []}
       → Moves files to results/disapproved/

POST   /api/gallery/undo
       → Move approved/disapproved back to pending
       → Body: {filenames: [], from_status: "approved"|"disapproved"}

GET    /api/gallery/stats
       → Approval statistics by date
       → Returns: {daily: [{date, pending, approved, disapproved}], totals}

GET    /api/gallery/download/{filename}
       → Download original full-resolution image

POST   /api/gallery/download-zip
       → Batch download as ZIP
       → Body: {filenames: []} or {date: "2026-03-24"}
       → Returns: application/zip stream

GET    /api/gallery/notes
PUT    /api/gallery/notes
       → Read/write daily_notes.json
```

### 3.4 API Endpoints — Config / Personas

```
GET    /api/config/personas
       → List all personas with their configs
       → Returns: [{name, type, hair_color, hairstyles, lora_name}]

GET    /api/config/personas/{name}
PUT    /api/config/personas/{name}
       → Read/update a single persona's config files

GET    /api/config/presets
POST   /api/config/presets
DELETE /api/config/presets/{name}
       → CRUD for prompt presets

GET    /api/config/presets/_last_used
PUT    /api/config/presets/_last_used
       → Sticky configuration (replaces st.session_state persistence)

GET    /api/config/workflow-types
       → List available workflow types (turbo, standard)

GET    /api/config/vision-models
       → List available vision models
```

### 3.5 API Endpoints — Monitor

```
GET    /api/monitor/health
       → System metrics: CPU, RAM, disk usage
       → Returns: {cpu_percent, ram: {total, used, percent}, disk: {...}}

GET    /api/monitor/queues
       → ComfyUI + Kling queue status combined
       → Returns: {comfyui: {running, pending}, kling: {pending, completed, failed}}

GET    /api/monitor/processes
       → Running Python processes
       → Returns: [{pid, name, cpu, memory}]

GET    /api/monitor/db-stats
       → Database row counts and status breakdown
       → Returns: {images: {total, pending, completed, failed},
                   videos: {total, pending, completed, failed}}

GET    /api/monitor/filesystem
       → File counts in input/processed/output directories
```

### 3.6 WebSocket Endpoint (Real-time Updates)

```
WS     /ws/tasks
       → Real-time Celery task progress updates
       → Replaces Streamlit's auto-rerun polling
       → Messages: {task_id, state, progress, status_message}

WS     /ws/queue
       → Live ComfyUI queue updates (push every 5s)
       → Replaces monitor_app.py auto-refresh
```

### 3.7 Service Layer Extraction

The key refactoring work is extracting business logic from Streamlit apps into service classes. Here's a mapping of what lives where:

**`services/image_processing.py`** — extracted from `1_workspace_app.py`:
- `scan_input_directory()` — list + sort images from INPUT_DIR
- `prepare_image(src_path)` — copy/rename to PROCESSED_DIR with `ref_{timestamp}_{uuid}`
- `dispatch_processing(config)` — call `process_image_task.delay(...)`, return task_id
- `dispatch_batch(image_paths, config)` — loop dispatch for multiple images
- `get_task_status(task_id)` — wrap `AsyncResult(task_id)` into a clean response

**`services/gallery.py`** — extracted from `2_gallery_app.py`:
- `list_images(status, page, per_page, group_by)` — scan directories, paginate
- `get_thumbnail(filename)` — generate/serve from `.thumbnails/` cache
- `extract_metadata(filename)` — parse PNG embedded ComfyUI JSON
- `approve_images(filenames, rename_map)` — `shutil.move` to approved/
- `disapprove_images(filenames)` — `shutil.move` to disapproved/
- `undo_action(filenames, from_status)` — move back
- `get_stats()` — aggregate counts by date
- `build_zip(filenames)` — create ZIP in-memory, stream response
- `lookup_execution(result_path)` — join with `image_logs` DB

**`services/config.py`** — extracted from config_manager.py + workspace_app:
- `list_personas()` — read `prompts/personas/*/` directory structure
- `get_persona(name)` — read type.txt, hair_color.txt, hairstyles.txt
- `update_persona(name, data)` — write config files
- `list_presets()` / `save_preset()` / `delete_preset()` — JSON CRUD in `prompts/presets/`
- `get_last_used()` / `save_last_used()` — sticky config

---

## 4. Phase 2 — Frontend: React SPA

### 4.1 Tech Stack Recommendation

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Framework | React 18+ (Vite) | Fast dev, matches your existing ff-auto target |
| Routing | React Router v6 | Standard SPA routing |
| State | Zustand or React Query | React Query for server state (polling, caching), Zustand for UI state |
| HTTP | Axios or fetch + React Query | Auto-retry, cache invalidation, polling built-in |
| WebSocket | native WebSocket + Zustand | For real-time task progress |
| UI Library | Tailwind + shadcn/ui | Clean, customizable, no heavy deps |
| Image handling | react-photo-album or custom grid | Lazy-load thumbnails, lightbox |
| Forms | React Hook Form | Workspace config forms |

### 4.2 Page Structure

```
frontend/src/
├── App.tsx                    # Router setup
├── api/
│   ├── client.ts              # Axios instance, base URL, interceptors
│   ├── workspace.ts           # Workspace API calls
│   ├── gallery.ts             # Gallery API calls
│   ├── config.ts              # Config API calls
│   └── monitor.ts             # Monitor API calls
│
├── hooks/
│   ├── useTaskProgress.ts     # WebSocket hook for Celery task updates
│   ├── useGalleryImages.ts    # React Query hook with pagination
│   ├── useQueueStatus.ts      # Polling hook for ComfyUI queue
│   └── usePersonas.ts         # Persona config CRUD
│
├── pages/
│   ├── WorkspacePage.tsx       # Main workspace layout
│   ├── GalleryPage.tsx         # Image curation grid
│   ├── VideoPage.tsx           # (Phase 3)
│   └── MonitorPage.tsx         # (Phase 3)
│
├── components/
│   ├── workspace/
│   │   ├── ImageQueue.tsx        # Input image grid with selection
│   │   ├── ProcessingConfig.tsx  # Persona, model, params form
│   │   ├── PresetSelector.tsx    # Load/save preset configs
│   │   ├── TaskProgress.tsx      # Real-time processing status
│   │   ├── ExecutionHistory.tsx  # Recent executions table
│   │   └── QueueMonitor.tsx      # ComfyUI queue widget
│   │
│   ├── gallery/
│   │   ├── ImageGrid.tsx         # Thumbnail grid with lazy loading
│   │   ├── ImageCard.tsx         # Single image with actions
│   │   ├── StatusTabs.tsx        # Pending | Approved | Disapproved
│   │   ├── BulkActions.tsx       # Select all, approve/reject batch
│   │   ├── ImageDetail.tsx       # Lightbox with metadata + execution info
│   │   ├── StatsPanel.tsx        # Daily approval stats
│   │   └── DownloadPanel.tsx     # ZIP download by date
│   │
│   └── shared/
│       ├── Layout.tsx            # App shell, sidebar navigation
│       ├── Pagination.tsx        # Reusable pagination
│       └── LoadingSpinner.tsx
│
└── types/
    ├── workspace.ts             # TypeScript interfaces
    ├── gallery.ts
    └── config.ts
```

### 4.3 Mapping: Streamlit State → React State

| Streamlit (`st.session_state`) | React Equivalent |
|-------------------------------|------------------|
| `page_{tab_name}` | URL search params (`?page=2`) or Zustand |
| `selected_files` (set) | `useState<Set<string>>` in GalleryPage |
| `files_to_approve` (set) | `useState<Set<string>>` in BulkActions |
| `rename_{filename}` | local state in ImageCard component |
| `items_wait`, `items_approved` | React Query cache (auto-invalidated) |
| `campaign_result` | React Query mutation result |
| Last-used config | `GET /api/config/presets/_last_used` on mount |
| Auto-refresh toggle | `useQuery` with `refetchInterval: 5000` or `enabled: false` |

### 4.4 Key UX Improvements Over Streamlit

The migration naturally solves several Streamlit limitations:

1. **No full-page reruns** — React only re-renders what changed. Approving an image doesn't reload the entire gallery.
2. **Real URL routing** — `/gallery?status=approved&page=3` is shareable and bookmarkable.
3. **Optimistic updates** — Approve an image, immediately move it in the UI, confirm on server in background.
4. **Persistent selection** — Selecting images survives tab switches (Streamlit loses `session_state` on page navigation).
5. **Concurrent operations** — Process images while browsing gallery (Streamlit blocks on one action).
6. **Native drag-and-drop** — For image upload and reordering (replaces `streamlit-sortables`).

---

## 5. Phase 3 — Video App & Monitor (Future)

Deferred to after Workspace + Gallery are stable. The pattern will be identical:

**Video App** → `api/videos.py` + `services/video.py` + `VideoPage.tsx`
- Storyboard workflow → POST /api/videos/storyboard
- Kling generation → POST /api/videos/generate
- Video merge → POST /api/videos/merge
- GCS upload → handled server-side

**Monitor App** → `api/monitor.py` + `services/monitor.py` + `MonitorPage.tsx`
- System health → GET /api/monitor/health (polled every 5s via React Query)
- Queue dashboard → WebSocket /ws/queue

---

## 6. Migration Steps (Execution Order)

### Step 1: Scaffold the FastAPI backend (1-2 days)
- [ ] Create project structure under `ff-auto/backend/`
- [ ] Copy all framework-agnostic modules (third_parties, workflows, tools, database, utils)
- [ ] Clean `config.py` — remove Streamlit secrets fallback, keep env-only
- [ ] Set up FastAPI `main.py` with CORS, static file serving, router registration
- [ ] Set up dependency injection (`deps.py`) for DB connections and service singletons
- [ ] Copy `celery_app.py` and `tasks.py` unchanged

### Step 2: Build the Config API (0.5 day)
- [ ] Implement `services/config.py` (persona CRUD, presets)
- [ ] Create `api/config.py` routes
- [ ] Test with curl/httpie — this is the simplest API and validates the pattern

### Step 3: Build the Workspace API (1-2 days)
- [ ] Implement `services/image_processing.py`
  - Extract `scan_input_directory()` from workspace_app lines that glob INPUT_DIR
  - Extract `prepare_image()` from the rename + move logic
  - Wrap `process_image_task.delay()` in `dispatch_processing()`
  - Wrap `AsyncResult` polling in `get_task_status()`
- [ ] Create `api/workspace.py` routes
- [ ] Add WebSocket endpoint for task progress (subscribe to Celery events)
- [ ] Test full flow: upload → process → poll → verify in DB

### Step 4: Build the Gallery API (1-2 days)
- [ ] Implement `services/gallery.py`
  - Extract directory scanning + pagination from gallery_app
  - Extract thumbnail generation (PIL resize to 512x512)
  - Extract PNG metadata parsing
  - Extract approve/disapprove file move logic
  - Extract stats aggregation
  - Add ZIP streaming
- [ ] Create `api/gallery.py` routes
- [ ] Serve thumbnails via FastAPI `FileResponse`
- [ ] Test approve/reject flow end-to-end

### Step 5: Build the Monitor API (0.5 day)
- [ ] Implement `services/monitor.py` (extract psutil calls from monitor_app.py)
- [ ] Create `api/monitor.py` routes

### Step 6: Scaffold the React frontend (1 day)
- [ ] Initialize Vite + React + TypeScript project
- [ ] Set up Tailwind + shadcn/ui
- [ ] Create Layout component with sidebar navigation
- [ ] Set up React Router with page stubs
- [ ] Set up Axios client + React Query provider
- [ ] Create TypeScript types matching Pydantic models

### Step 7: Build the Workspace Page (2-3 days)
- [ ] ImageQueue component — fetch + display input images
- [ ] ProcessingConfig form — persona, model, params (React Hook Form)
- [ ] PresetSelector — load/save presets via API
- [ ] TaskProgress — WebSocket connection for real-time updates
- [ ] ExecutionHistory — table with recent executions
- [ ] QueueMonitor widget — poll ComfyUI queue status

### Step 8: Build the Gallery Page (2-3 days)
- [ ] StatusTabs — Pending / Approved / Disapproved
- [ ] ImageGrid — lazy-loaded thumbnail grid with intersection observer
- [ ] ImageCard — hover actions (approve, reject, view detail)
- [ ] BulkActions — select multiple, batch approve/reject
- [ ] ImageDetail lightbox — full image + metadata + execution record
- [ ] StatsPanel — daily approval chart
- [ ] DownloadPanel — ZIP download

### Step 9: Docker & Deployment (1 day)
- [ ] Create `Dockerfile.backend` (Python 3.11 + ffmpeg)
- [ ] Create `Dockerfile.frontend` (Node build → nginx)
- [ ] Update `docker-compose.yml` with 4 services:
  - `backend` (FastAPI on :8000)
  - `frontend` (nginx on :3000, proxy /api → backend)
  - `worker` (Celery worker + Beat)
  - Uses existing `global-redis` on ff-shared-net
- [ ] Migrate volume mounts

### Step 10: Data Migration & Cutover (0.5 day)
- [ ] SQLite databases (`image_logs.db`, `video_logs.db`) — copy to new location
- [ ] Verify `prompts/` directory structure is mounted correctly
- [ ] Verify `Sorted/`, `processed/`, `results/` volume mounts work
- [ ] Test full pipeline end-to-end in Docker
- [ ] Shut down old Streamlit containers, start new stack

---

## 7. Docker Compose (Target)

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: uvicorn backend.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    volumes:
      - ../Sorted:/app/Sorted
      - ../processed:/app/processed
      - ../results:/app/results
      - ../prompts:/app/prompts
      - ../image_logs.db:/app/image_logs.db
      - ../video_logs.db:/app/video_logs.db
    env_file:
      - .env
    environment:
      - CELERY_BROKER_URL=redis://global-redis:6379/1
      - CELERY_RESULT_BACKEND=redis://global-redis:6379/2
    networks:
      - ff-shared-net
    deploy:
      resources:
        limits:
          cpus: '0.6'

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
    networks:
      - ff-shared-net

  worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: celery -A celery_app worker -B --loglevel=info
    volumes:
      - ../Sorted:/app/Sorted
      - ../processed:/app/processed
      - ../results:/app/results
      - ../prompts:/app/prompts
      - ../image_logs.db:/app/image_logs.db
    env_file:
      - .env
    environment:
      - CELERY_BROKER_URL=redis://global-redis:6379/1
      - CELERY_RESULT_BACKEND=redis://global-redis:6379/2
    networks:
      - ff-shared-net
    deploy:
      resources:
        limits:
          cpus: '0.8'

networks:
  ff-shared-net:
    external: true
```

---

## 8. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Losing working pipeline during migration | Run both stacks in parallel. Streamlit on :8501, FastAPI on :8000. Share same volumes + DB. |
| Celery task compatibility | Tasks are already standalone — no changes needed. Both apps can dispatch to the same Celery workers. |
| SQLite concurrency under FastAPI | FastAPI serves multiple requests concurrently. Use connection pooling or migrate to PostgreSQL (already configured in GlobalConfig). |
| File path differences | Keep volume mounts identical. Use `GlobalConfig.INPUT_DIR` etc. consistently. |
| Thumbnail cache invalidation | Gallery service generates thumbnails on-demand with mtime check. Same logic, just moved to a service. |

---

## 9. Estimated Timeline

| Phase | Effort | Cumulative |
|-------|--------|------------|
| Phase 1: FastAPI Backend (Steps 1-5) | 5-7 days | Week 1 |
| Phase 2: React Frontend (Steps 6-8) | 5-7 days | Week 2 |
| Phase 3: Docker + Cutover (Steps 9-10) | 1-2 days | Week 2-3 |
| **Total for Workspace + Gallery** | **~2-3 weeks** | |
| Phase 4: Video App (future) | 3-4 days | +1 week |
| Phase 5: Monitor App (future) | 1-2 days | +0.5 week |
