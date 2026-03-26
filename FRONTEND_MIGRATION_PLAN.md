# Frontend Migration Plan: Streamlit → React + Shadnui/Tailwind

**Project**: ff-automation-captioning → ff-auto
**UI Framework**: Streamlit → React 18+ + Shadnui + Tailwind CSS
**Date**: March 25, 2026

---

## Table of Contents
1. [Current UI Analysis](#1-current-ui-analysis)
2. [Tech Stack & Justification](#2-tech-stack--justification)
3. [Design System & Component Mapping](#3-design-system--component-mapping)
4. [Page Architecture & Layout](#4-page-architecture--layout)
5. [Component Breakdown by Page](#5-component-breakdown-by-page)
6. [State Management Strategy](#6-state-management-strategy)
7. [Styling & Theming](#7-styling--theming)
8. [Form Handling & Validation](#8-form-handling--validation)
9. [Real-time Updates & WebSocket Integration](#9-real-time-updates--websocket-integration)
10. [Performance Optimizations](#10-performance-optimizations)
11. [Testing Strategy](#11-testing-strategy)
12. [Implementation Steps](#12-implementation-steps)
13. [Common Patterns & Utilities](#13-common-patterns--utilities)
14. [Migration Checklist](#14-migration-checklist)

---

## 1. Current UI Analysis

### 1.1 Streamlit App Structure

```
📱 Landing Page (app.py)
├─ Welcome message
├─ Navigation to sub-apps
└─ Setup instructions

📱 Workspace App (1_workspace_app.py) - 996 lines
├─ Sidebar: Configuration Panel
│  ├─ KOL Persona Selector
│  ├─ Vision Model Selector (ChatGPT, Grok, Gemini)
│  ├─ CLIP Model Type Selector (19 options)
│  ├─ Batch Limit (1-1000)
│  ├─ Variations per Image (1-5)
│  ├─ Model Strength (0.0-2.0)
│  ├─ LoRA Configuration (persona-specific)
│  ├─ Dimensions (Width × Height)
│  ├─ Seed Strategy (random/fixed)
│  └─ Debug Config Checkbox
├─ Main Panel: Workflow Management
│  ├─ Persona Configuration Expander
│  │  ├─ Select Persona
│  │  ├─ Edit Type
│  │  ├─ Edit Hair Color
│  │  └─ Edit Hairstyles (multi-line text)
│  ├─ Workflow Configuration Studio Expander
│  │  ├─ Select Persona Type
│  │  ├─ Create New Type Form
│  │  ├─ Edit Analyst Agent
│  │  ├─ Edit Turbo Agent
│  │  ├─ Test Workflow
│  │  └─ View Execution History
│  └─ Input Management Section
│     ├─ Image Upload Widget
│     ├─ Input Images Grid
│     ├─ Queue Status Widget
│     └─ Execution History Table
└─ Sticky Preset System (Auto-save to _last_used)

📱 Gallery App (2_gallery_app.py) - 670 lines
├─ Top Bar
│  ├─ Title "Results Gallery"
│  └─ Refresh Button
├─ Debug Info Expander (optional)
├─ Statistics Section
│  └─ Dataframe with Approval Rates
├─ Filters & Settings Expander
│  ├─ Persona Filter Dropdown (disabled for perf)
│  └─ Group By Radio (Date / Batch Reference / None)
├─ Tab 1: Wait for Approvals
│  ├─ Batch Actions
│  │  ├─ Approve Selected Button
│  │  └─ Disapprove Remaining (disabled)
│  ├─ Pagination (page_wait)
│  ├─ Image Grid (4 columns)
│  │  ├─ Thumbnail (512x512 lazy-loaded)
│  │  ├─ Approve Checkbox + Delete Button
│  │  ├─ Rename Input Field
│  │  ├─ Download Button
│  │  └─ Details Popover (metadata + execution info)
│  └─ Grouping (Date / Batch / None)
├─ Tab 2: Approved Images
│  ├─ Download by Date Expander (ZIP generation)
│  ├─ Pagination
│  ├─ Image Grid with Actions
│  │  ├─ Undo Button (move back to Wait)
│  │  ├─ Move to Disapproved Button
│  │  ├─ Download Button
│  │  └─ Details Popover
│  └─ Grouping Support
├─ Tab 3: Disapproved Images
│  ├─ Pagination
│  ├─ Image Grid with Actions
│  │  ├─ Recover Button (move to Wait)
│  │  ├─ Approve Button
│  │  ├─ Download Button
│  │  └─ Details Popover
│  └─ Grouping Support
└─ Daily Notes Section
   └─ Text Area + Save Button

📱 Video App (3_video_app.py) - Phase 3
```

### 1.2 Current UX Patterns

| Pattern | Current Implementation | Issues |
|---------|----------------------|--------|
| **State Persistence** | `st.session_state` per-session, not persistent across navigation | Lost state on page reload |
| **Configuration** | Sidebar selectboxes + text inputs | Poor mobile experience |
| **Image Grid** | 4-column grid with thumbnails | No lazy loading, full-page rerun on action |
| **Approval Workflow** | Checkbox → Approve button | No optimistic updates |
| **Download** | `st.download_button` → ZIP generation | Blocks UI during generation |
| **Metadata Display** | Popover with expanded JSON | No visual metadata cards |
| **Pagination** | Number input with manual page tracking | Non-standard UX |
| **Batch Operations** | Session state sets + buttons | No multi-select UI patterns |
| **Real-time Updates** | Manual refresh button | No live task progress |
| **Presets** | JSON file I/O, auto-save to `_last_used` | Good pattern, can be preserved |

---

## 2. Tech Stack & Justification

### 2.1 Core Framework Stack

| Technology | Purpose | Why Chosen |
|------------|---------|-----------|
| **React 18+** | UI Framework | Standard, hooks-based, excellent ecosystem |
| **Vite** | Build Tool | Fast dev server (HMR), optimized production builds |
| **TypeScript** | Type Safety | Catch errors at compile-time, better IDE support |
| **React Router v6** | Client-side Routing | Standard SPA routing, supports nested routes |
| **Tailwind CSS** | Styling | Utility-first, already in use via shadnui |
| **Shadnui** | Component Library | Accessible, customizable, built on Radix UI |
| **React Query** | Server State | Auto-refetching, caching, pagination helpers |
| **Zustand** | Client State | Lightweight, simple API, no boilerplate |
| **React Hook Form** | Form Handling | Minimal re-renders, composable validation |
| **Axios** | HTTP Client | Interceptors, auto-retry, request cancellation |
| **Zod** | Schema Validation | Type inference from schemas, runtime validation |

### 2.2 Additional Libraries

| Library | Purpose | Size Impact |
|---------|---------|------------|
| `lucide-react` | Icons | Already included in shadnui setup |
| `date-fns` | Date Manipulation | Parse/format timestamps |
| `clsx` | Class Merging | Conditional classes (alternative: tailwind-merge) |
| `react-photo-album` | Image Grid | Responsive, lazy-loading thumbnail grid |
| `react-hotkeys-hook` | Keyboard Shortcuts | Ctrl+A for select all, Del for batch delete |
| `recharts` | Charts | Gallery statistics dashboard |
| `react-helmet` | Document Head | SEO, page title management |
| `msw` | API Mocking | Testing without backend |

---

## 3. Design System & Component Mapping

### 3.1 Shadnui Component Mapping

| Streamlit Component | Shadnui Equivalent | Usage |
|-------------------|------------------|-------|
| `st.sidebar.selectbox` | `Select` | Persona, vision model, CLIP type dropdowns |
| `st.sidebar.number_input` | `Input[type="number"]` | Batch limit, variations, dimensions |
| `st.sidebar.slider` | `Slider` | Model strength, pagination |
| `st.text_input` | `Input` | Rename fields, persona config |
| `st.text_area` | `Textarea` | Hairstyles, agent backstories, daily notes |
| `st.tabs` | `Tabs` | Gallery status tabs, agent editor tabs |
| `st.expander` | `Collapsible` or custom `Card` | Config sections, filters |
| `st.columns` | CSS Grid / Flexbox | 2-col forms, 4-col image grids |
| `st.button` | `Button` | Approve, disapprove, download actions |
| `st.checkbox` | `Checkbox` | Image approval selection |
| `st.radio` | `RadioGroup` | Group by options |
| `st.dataframe` | `DataTable` or custom `Table` | Statistics, execution history |
| `st.multiselect` | `MultiSelect` or `Combobox` | Filter options (if re-enabled) |
| `st.download_button` | `Button` + fetch API | Download/ZIP generation |
| `st.progress` | `Progress` | Task progress bars |
| `st.metric` | Custom Card | Queue stats, system health |
| `st.image` | `<img>` or Picture | Thumbnail display |
| `st.popover` | `Popover` | Metadata details |
| `st.form` | `<form>` or Dialog | Persona creation, preset management |

### 3.2 Color & Theme Consistency

```typescript
// Tailwind Extends
export const theme = {
  colors: {
    // Primary: Action-oriented (blue/purple)
    primary: 'hsl(240 100% 50%)',

    // Success: Approval/Accept (green)
    success: 'hsl(142 71% 45%)',

    // Destructive: Disapprove/Delete (red)
    destructive: 'hsl(0 84% 60%)',

    // Warning: Processing (orange/yellow)
    warning: 'hsl(38 92% 50%)',

    // Muted: Secondary actions, disabled states
    muted: 'hsl(0 0% 64%)',

    // Background: Card, popover, modal
    bg: {
      primary: 'hsl(0 0% 100%)',   // Light mode
      secondary: 'hsl(210 40% 96%)',  // Light gray
      muted: 'hsl(210 10% 96%)',
    }
  },
  fonts: {
    sans: 'Inter, system-ui, -apple-system, sans-serif',
    mono: 'Fira Code, monospace',
  },
  spacing: {
    // Following Tailwind defaults (4px base unit)
    xs: '0.5rem',
    sm: '1rem',
    md: '1.5rem',
    lg: '2rem',
    xl: '3rem',
  },
  borders: {
    radius: {
      sm: '0.375rem',
      md: '0.5rem',
      lg: '0.75rem',
    }
  }
};
```

### 3.3 Icon Usage

Use `lucide-react` consistently:

```typescript
import {
  ChevronDown, Edit, Trash2, Download,
  Check, X, AlertCircle, Loader, Settings,
  Image, Grid, List, Zap, PlayCircle,
  Search, Filter, Copy, Heart, Eye,
} from 'lucide-react';

// Usage pattern:
<Button variant="outline" size="sm">
  <Edit className="w-4 h-4 mr-2" />
  Edit
</Button>
```

---

## 4. Page Architecture & Layout

### 4.1 App Shell & Routing

```
App.tsx
├─ Layout.tsx (Persistent)
│  ├─ Header
│  │  ├─ Logo + Title
│  │  ├─ Navigation Breadcrumbs
│  │  └─ Help + Settings Menu
│  ├─ Sidebar (Collapsible on mobile)
│  │  ├─ Logo
│  │  ├─ Nav Items (Workspace, Gallery, Video, Monitor)
│  │  ├─ Current Page Config Panel (dynamic)
│  │  └─ Footer Links
│  └─ Main Content (router outlet)
│     ├─ Workspace Page
│     ├─ Gallery Page
│     ├─ Video Page (Phase 3)
│     ├─ Monitor Page (Phase 3)
│     └─ Settings Page
└─ WebSocket Provider (global)
   └─ Toast Container
      └─ Dialog Container

```

### 4.2 Responsive Breakpoints

```typescript
// tailwind.config.js
{
  screens: {
    xs: '320px',    // Mobile-first
    sm: '640px',    // Tablets
    md: '768px',    // Small laptops
    lg: '1024px',   // Desktops
    xl: '1280px',   // Large desktops
    '2xl': '1536px' // Ultra-wide
  }
}

// Usage:
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
  {/* 1 col mobile, 2 cols tablet, 4 cols desktop */}
</div>
```

### 4.3 Navigation Flow

```
Landing (/)
├─ Workspace (/workspace)
│  ├─ Sidebar: Configuration
│  ├─ Main: Input Queue + Execution History
│  └─ Right Drawer: Persona Editor (optional)
├─ Gallery (/gallery)
│  ├─ Tabs: Pending | Approved | Disapproved
│  ├─ Filters Drawer: Status, Date Range, Persona
│  └─ Lightbox: Image Detail + Metadata
├─ Video (/video) - Phase 3
│  ├─ Storyboard Tab
│  ├─ Kling Tab
│  └─ Merge Tab
├─ Monitor (/monitor) - Phase 3
│  ├─ System Health Cards
│  ├─ Queue Charts
│  └─ Process List
└─ Settings (/settings)
   ├─ Theme Selector
   ├─ API Configuration
   └─ About
```

---

## 5. Component Breakdown by Page

### 5.1 Workspace Page (`/workspace`)

#### Main Components:

```typescript
// pages/WorkspacePage.tsx
<WorkspacePage>
  ├─ <WorkspaceLayout>
  │  ├─ <ConfigurationSidebar>
  │  │  ├─ <PersonaSelector />
  │  │  ├─ <VisionModelSelector />
  │  │  ├─ <CLIPModelSelector />
  │  │  ├─ <ParamAdjuster /> (limit, variations, strength)
  │  │  ├─ <LoRAConfigurator />
  │  │  ├─ <DimensionsInput />
  │  │  ├─ <SeedConfigurator />
  │  │  └─ <PresetManager /> (Load/Save/Delete)
  │  │
  │  ├─ <MainContent>
  │  │  ├─ <Tabs>
  │  │  │  ├─ <Tab "Configuration">
  │  │  │  │  ├─ <PersonaConfigEditor />
  │  │  │  │  │  ├─ <PersonaTypeSelector />
  │  │  │  │  │  ├─ <HairColorInput />
  │  │  │  │  │  └─ <HairstylesEditor />
  │  │  │  │  └─ <WorkflowConfigStudio />
  │  │  │  │     ├─ <AgentEditor /> (Analyst)
  │  │  │  │     ├─ <AgentEditor /> (Turbo)
  │  │  │  │     ├─ <PersonaTypeCreator />
  │  │  │  │     └─ <TestWorkflow /> (debug view)
  │  │  │  │
  │  │  │  ├─ <Tab "Input Queue">
  │  │  │  │  ├─ <ImageUploadArea />
  │  │  │  │  ├─ <InputImageGrid />
  │  │  │  │  │  ├─ <ImageItem /> (checkbox + details)
  │  │  │  │  │  └─ <BulkActions /> (Select All, Clear)
  │  │  │  │  └─ <ProcessButton /> (dispatch to queue)
  │  │  │  │
  │  │  │  ├─ <Tab "Execution History">
  │  │  │  │  ├─ <ExecutionFilter /> (status, date range)
  │  │  │  │  └─ <ExecutionTable />
  │  │  │  │     └─ <ExecutionRow /> (task details + status)
  │  │  │  │
  │  │  │  └─ <Tab "Queue Monitor">
  │  │  │     ├─ <ComfyUIQueueWidget />
  │  │  │     │  ├─ <QueueStats /> (running, pending)
  │  │  │     │  └─ <QueueList /> (live task list)
  │  │  │     └─ <RefreshControl />
  │  │  │
  │  │  └─ <TaskProgressOverlay />
  │  │     └─ <TaskProgressCard /> (WebSocket updates)
```

#### State Structure:

```typescript
// stores/workspaceStore.ts
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  // Configuration
  config: {
    persona: 'Jennie',
    visionModel: 'gpt-4o',
    clipModel: 'sd3',
    batchLimit: 10,
    variations: 1,
    strength: 0.8,
    lora: 'khiemle__xz-comfy__jennie_turbo_v4.safetensors',
    width: 1024,
    height: 1600,
    seedStrategy: 'random',
    baseSeed: 0,
  },
  setConfig: (update) => set(state => ({
    config: { ...state.config, ...update }
  })),

  // Selected images for processing
  selectedImages: new Set<string>(),
  toggleImageSelection: (filename) => { /* ... */ },

  // Task progress
  activeTask: null,
  tasks: [],
  setActiveTask: (task) => set({ activeTask: task }),

  // Presets
  presets: [],
  savePreset: async (name, config) => { /* API call */ },
  loadPreset: async (name) => { /* API call */ },
}));
```

### 5.2 Gallery Page (`/gallery`)

#### Main Components:

```typescript
// pages/GalleryPage.tsx
<GalleryPage>
  ├─ <GalleryLayout>
  │  ├─ <GalleryHeader>
  │  │  ├─ <Title> "Results Gallery"
  │  │  ├─ <FilterButton> (drawer toggle)
  │  │  ├─ <GroupBySelector />
  │  │  ├─ <ViewModeToggle /> (grid/list)
  │  │  ├─ <SearchBar />
  │  │  └─ <RefreshButton />
  │  │
  │  ├─ <FilterDrawer>
  │  │  ├─ <StatusFilter /> (tabs radio)
  │  │  ├─ <DateRangeFilter />
  │  │  ├─ <PersonaFilter /> (multi-select)
  │  │  ├─ <SortSelector /> (newest/oldest)
  │  │  ├─ <GroupBySelector /> (date/batch/none)
  │  │  ├─ <ResetFilters /> button
  │  │  └─ <ApplyFilters /> button
  │  │
  │  ├─ <StatsPanel>
  │  │  ├─ <StatsCard> (total count)
  │  │  ├─ <StatsCard> (approved count)
  │  │  ├─ <StatsCard> (disapproved count)
  │  │  └─ <ApprovalChart /> (recharts)
  │  │
  │  ├─ <Tabs>
  │  │  ├─ <Tab "Pending">
  │  │  │  ├─ <BulkActions>
  │  │  │  │  ├─ <SelectAllCheckbox />
  │  │  │  │  ├─ <Button> Approve Selected
  │  │  │  │  └─ <Button> Delete Selected
  │  │  │  ├─ <ImageGrid>
  │  │  │  │  ├─ <ImageCard /> (thumbnail + controls)
  │  │  │  │  │  ├─ <Checkbox /> (selection)
  │  │  │  │  │  ├─ <RenameInput />
  │  │  │  │  │  ├─ <DeleteButton />
  │  │  │  │  │  ├─ <DetailsButton /> (popover)
  │  │  │  │  │  └─ <DownloadButton />
  │  │  │  │  └─ <IntersectionObserver /> (lazy loading)
  │  │  │  └─ <Pagination />
  │  │  │
  │  │  ├─ <Tab "Approved">
  │  │  │  ├─ <DownloadByDateWidget />
  │  │  │  │  ├─ <DateButtons /> (ZIP per date)
  │  │  │  │  └─ <DownloadAll /> button
  │  │  │  ├─ <ImageGrid>
  │  │  │  │  ├─ <ImageCard /> (thumbnail + controls)
  │  │  │  │  │  ├─ <UndoButton /> (move to Pending)
  │  │  │  │  │  ├─ <RejectButton /> (move to Disapproved)
  │  │  │  │  │  ├─ <DetailsButton />
  │  │  │  │  │  └─ <DownloadButton />
  │  │  │  │  └─ <IntersectionObserver />
  │  │  │  └─ <Pagination />
  │  │  │
  │  │  └─ <Tab "Disapproved">
  │  │     ├─ <ImageGrid>
  │  │     │  ├─ <ImageCard />
  │  │     │  │  ├─ <RecoverButton /> (move to Pending)
  │  │     │  │  ├─ <ApproveButton /> (move to Approved)
  │  │     │  │  ├─ <DetailsButton />
  │  │     │  │  └─ <DownloadButton />
  │  │     │  └─ <IntersectionObserver />
  │  │     └─ <Pagination />
  │  │
  │  ├─ <ImageDetailLightbox>
  │  │  ├─ <LightboxImage />
  │  │  ├─ <MetadataPanel>
  │  │  │  ├─ <MetadataRow> (seed)
  │  │  │  ├─ <MetadataRow> (prompt)
  │  │  │  ├─ <MetadataRow> (persona)
  │  │  │  └─ <ReferenceImage />
  │  │  ├─ <ExecutionInfo>
  │  │  │  ├─ <InfoRow> (created at)
  │  │  │  ├─ <InfoRow> (status)
  │  │  │  └─ <FullMetadataExpander />
  │  │  └─ <ActionButtons>
  │  │     └─ Status-specific actions
  │  │
  │  └─ <DailyNotesCard>
  │     ├─ <NotesTextarea />
  │     └─ <SaveButton />
```

#### State Structure:

```typescript
// stores/galleryStore.ts
export const useGalleryStore = create<GalleryState>((set) => ({
  // Filters
  filters: {
    status: 'pending',
    dateRange: [null, null],
    personas: [],
    groupBy: 'date',
    sortBy: 'newest',
    searchQuery: '',
  },
  setFilter: (key, value) => { /* ... */ },

  // Pagination
  page: 1,
  perPage: 20,
  setPage: (page) => set({ page }),

  // Selection for bulk operations
  selectedImages: new Set<string>(),
  toggleImage: (filename) => { /* ... */ },
  selectAll: (filenames) => set(state => ({
    selectedImages: new Set(filenames)
  })),

  // Detail view
  detailImage: null,
  setDetailImage: (filename) => set({ detailImage: filename }),

  // Rename input
  renameMap: new Map<string, string>(),
  setRename: (filename, newName) => { /* ... */ },

  // UI state
  viewMode: 'grid', // or 'list'
  setViewMode: (mode) => set({ viewMode: mode }),
}));
```

### 5.3 Shared Components

#### Layout Components:

```typescript
// components/Layout.tsx
export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex h-screen bg-background">
    <Sidebar />
    <main className="flex-1 flex flex-col overflow-hidden">
      <Header />
      <div className="flex-1 overflow-auto">
        {children}
      </div>
    </main>
  </div>
)

// components/Sidebar.tsx
export const Sidebar: React.FC = () => (
  <aside className="w-64 bg-card border-r border-border">
    <nav className="flex flex-col h-full">
      <Logo />
      <NavItems />
      <ConfigPanel /> {/* Dynamic based on current page */}
      <SidebarFooter />
    </nav>
  </aside>
)

// components/Header.tsx
export const Header: React.FC = () => (
  <header className="h-16 bg-card border-b border-border flex items-center px-6">
    <Breadcrumbs />
    <Spacer />
    <SearchBar />
    <HelpMenu />
    <SettingsMenu />
  </header>
)
```

#### Common UI Components:

```typescript
// components/shared/
├─ Pagination.tsx        // Reusable pagination component
├─ LoadingSpinner.tsx    // Spinner overlay
├─ EmptyState.tsx        // Empty gallery placeholder
├─ StatusBadge.tsx       // Task status indicator
├─ ImageThumbnail.tsx    // Lazy-loaded image with fallback
├─ ConfirmDialog.tsx     // Delete/action confirmation
├─ Toast.tsx             // Toast notifications (built on Sonner)
├─ Breadcrumbs.tsx       // Navigation breadcrumbs
├─ FilterDrawer.tsx      // Reusable filter sidebar
├─ DataTable.tsx         // Generic table component
└─ ImageCard.tsx         // Reusable image card with actions
```

---

## 6. State Management Strategy

### 6.1 State Hierarchy

```typescript
// Two-tier state management:

// 1. SERVER STATE (React Query)
//    - Images (gallery)
//    - Tasks (celery)
//    - Config (personas, presets)
//    - Automatic: refetching, caching, pagination
useQuery({
  queryKey: ['gallery', { status, page }],
  queryFn: () => api.gallery.getImages({ status, page }),
  staleTime: 5 * 60 * 1000, // 5 min
})

// 2. CLIENT STATE (Zustand)
//    - UI preferences (sidebar open, view mode)
//    - Temporary selections (selected images)
//    - Form state (config being edited)
//    - Filters (not persisted immediately)
const { filters, setFilter } = useGalleryStore()
```

### 6.2 Zustand Stores

```typescript
// stores/index.ts
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  // ... workspace state
}))

export const useGalleryStore = create<GalleryState>((set) => ({
  // ... gallery state
}))

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set(state => ({ sidebarOpen: !state.sidebarOpen })),

  theme: 'light',
  setTheme: (theme) => set({ theme }),

  toasts: [],
  addToast: (message, type) => { /* ... */ },
  removeToast: (id) => { /* ... */ },
}))

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  login: async (credentials) => { /* ... */ },
  logout: () => { /* ... */ },
}))
```

### 6.3 React Query Setup

```typescript
// hooks/useGalleryImages.ts
export const useGalleryImages = (filters: GalleryFilters, page: number) => {
  return useQuery({
    queryKey: ['gallery', 'images', { ...filters, page }],
    queryFn: () => api.gallery.getImages({ ...filters, page, perPage: 20 }),
    keepPreviousData: true, // Smooth pagination
    staleTime: 1000 * 60 * 5, // 5 minutes
  })
}

// hooks/useTaskProgress.ts
export const useTaskProgress = (taskId: string) => {
  return useQuery({
    queryKey: ['tasks', taskId],
    queryFn: () => api.workspace.getTaskStatus(taskId),
    refetchInterval: 500, // Poll every 500ms OR use WebSocket
    enabled: !!taskId,
  })
}

// hooks/usePersonas.ts
export const usePersonas = () => {
  return useQuery({
    queryKey: ['config', 'personas'],
    queryFn: () => api.config.getPersonas(),
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}
```

### 6.4 WebSocket for Real-time Updates

```typescript
// hooks/useWebSocket.ts
export const useWebSocket = (url: string, handler: (data: any) => void) => {
  useEffect(() => {
    const ws = new WebSocket(url)

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handler(data)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    return () => ws.close()
  }, [url, handler])
}

// Usage in TaskProgress component:
const [progress, setProgress] = useState<TaskProgress | null>(null)
useWebSocket(`ws://${API_HOST}/ws/tasks`, (data) => {
  if (data.task_id === taskId) {
    setProgress(data)
    // Auto-invalidate query on completion
    if (data.state === 'SUCCESS') {
      queryClient.invalidateQueries({ queryKey: ['tasks', taskId] })
    }
  }
})
```

---

## 7. Styling & Theming

### 7.1 Tailwind + Shadnui Setup

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'
import defaultTheme from 'tailwindcss/defaultTheme'

const config: Config = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    './node_modules/@shadcn/ui/src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Shadnui defaults with custom overrides
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        success: 'hsl(142 71% 45%)',
        warning: 'hsl(38 92% 50%)',
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      spacing: {
        xs: '0.5rem',
        sm: '1rem',
        md: '1.5rem',
        lg: '2rem',
        xl: '3rem',
      },
      borderRadius: {
        xs: '0.25rem',
        sm: '0.375rem',
        md: '0.5rem',
        lg: '0.75rem',
        xl: '1rem',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

export default config
```

### 7.2 CSS Variables (Light/Dark Mode)

```css
/* src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Light Mode */
:root {
  --background: 0 0% 100%;
  --foreground: 0 0% 5%;
  --card: 0 0% 100%;
  --card-foreground: 0 0% 5%;
  --primary: 240 100% 50%;
  --primary-foreground: 0 0% 100%;
  --secondary: 210 40% 96%;
  --secondary-foreground: 240 100% 50%;
  --destructive: 0 84% 60%;
  --destructive-foreground: 0 0% 100%;
  --muted: 0 0% 90%;
  --muted-foreground: 0 0% 40%;
  --accent: 240 100% 50%;
  --accent-foreground: 0 0% 100%;
  --border: 0 0% 89%;
  --input: 0 0% 100%;
  --ring: 240 100% 50%;
}

/* Dark Mode */
@media (prefers-color-scheme: dark) {
  :root {
    --background: 0 0% 5%;
    --foreground: 0 0% 95%;
    --card: 0 0% 15%;
    --card-foreground: 0 0% 95%;
    --primary: 240 100% 60%;
    --primary-foreground: 0 0% 5%;
    --secondary: 210 20% 25%;
    --secondary-foreground: 0 0% 95%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 0 0% 5%;
    --muted: 0 0% 30%;
    --muted-foreground: 0 0% 70%;
    --accent: 240 100% 60%;
    --accent-foreground: 0 0% 5%;
    --border: 0 0% 20%;
    --input: 0 0% 15%;
    --ring: 240 100% 60%;
  }

  .dark {
    color-scheme: dark;
  }
}

/* Global Styles */
body {
  @apply bg-background text-foreground;
  font-family: system-ui, -apple-system, sans-serif;
}

/* Custom Utilities */
@layer components {
  .btn-primary {
    @apply px-md py-sm rounded-md bg-primary text-primary-foreground
           hover:bg-primary/90 transition-colors cursor-pointer;
  }

  .btn-outline {
    @apply px-md py-sm rounded-md border border-border
           hover:bg-muted transition-colors cursor-pointer;
  }

  .input-field {
    @apply w-full px-sm py-sm rounded-md border border-input
           focus:outline-none focus:ring-2 focus:ring-ring;
  }

  .card-base {
    @apply bg-card rounded-lg border border-border shadow-sm;
  }
}
```

### 7.3 Component Variants

```typescript
// components/Button.tsx (extending shadcn)
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  isLoading?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'default', size = 'default', isLoading, ...props }, ref) => {
    const variantClasses = {
      default: 'bg-primary text-primary-foreground hover:bg-primary/90',
      destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
      outline: 'border border-input hover:bg-accent',
      secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
      ghost: 'hover:bg-accent hover:text-accent-foreground',
      link: 'text-primary underline-offset-4 hover:underline',
    }

    const sizeClasses = {
      default: 'h-10 px-4 py-2',
      sm: 'h-9 rounded-md px-3',
      lg: 'h-11 rounded-md px-8',
      icon: 'h-10 w-10',
    }

    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-md font-medium',
          'transition-colors focus-visible:outline-none focus-visible:ring-2',
          'focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
          variantClasses[variant],
          sizeClasses[size],
          isLoading && 'pointer-events-none opacity-50',
          props.className
        )}
        disabled={isLoading || props.disabled}
        {...props}
      >
        {isLoading ? <Loader className="w-4 h-4 mr-2 animate-spin" /> : null}
        {props.children}
      </button>
    )
  }
)
```

---

## 8. Form Handling & Validation

### 8.1 React Hook Form Setup

```typescript
// hooks/useConfigForm.ts
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const configSchema = z.object({
  persona: z.string().min(1, 'Persona is required'),
  visionModel: z.enum(['gpt-4o', 'grok-4-1-fast-non-reasoning', 'gemini-3-flash-preview']),
  clipModel: z.string().min(1),
  batchLimit: z.number().min(1).max(1000),
  variations: z.number().min(1).max(5),
  strength: z.number().min(0).max(2),
  width: z.number().min(256).max(2048),
  height: z.number().min(256).max(2048),
  seedStrategy: z.enum(['random', 'fixed']),
  baseSeed: z.number().min(0).optional(),
})

export type ConfigFormData = z.infer<typeof configSchema>

export const useConfigForm = (defaultValues?: Partial<ConfigFormData>) => {
  return useForm<ConfigFormData>({
    resolver: zodResolver(configSchema),
    defaultValues: {
      persona: 'Jennie',
      visionModel: 'gpt-4o',
      clipModel: 'sd3',
      batchLimit: 10,
      variations: 1,
      strength: 0.8,
      width: 1024,
      height: 1600,
      seedStrategy: 'random',
      ...defaultValues,
    },
  })
}
```

### 8.2 Form Component Example

```typescript
// components/workspace/ProcessingConfig.tsx
export const ProcessingConfig: React.FC = () => {
  const form = useConfigForm()
  const { mutate: savePreset } = useMutation({
    mutationFn: (name: string) => api.config.savePreset(name, form.getValues()),
  })

  return (
    <form onSubmit={form.handleSubmit(async (data) => {
      // Process the config
      dispatch(data)
    })} className="space-y-4">
      {/* Persona Selector */}
      <Controller
        name="persona"
        control={form.control}
        render={({ field }) => (
          <div>
            <Label htmlFor="persona">KOL Persona</Label>
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger id="persona">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {personas.map(p => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.persona && (
              <p className="text-sm text-destructive mt-1">
                {form.formState.errors.persona.message}
              </p>
            )}
          </div>
        )}
      />

      {/* Batch Limit */}
      <Controller
        name="batchLimit"
        control={form.control}
        render={({ field }) => (
          <div>
            <Label htmlFor="limit">Batch Limit</Label>
            <Input
              id="limit"
              type="number"
              {...field}
              onChange={(e) => field.onChange(parseInt(e.target.value))}
              min={1}
              max={1000}
            />
          </div>
        )}
      />

      {/* Model Strength Slider */}
      <Controller
        name="strength"
        control={form.control}
        render={({ field }) => (
          <div className="space-y-2">
            <Label>Model Strength: {field.value.toFixed(1)}</Label>
            <Slider
              value={[field.value]}
              onValueChange={([v]) => field.onChange(v)}
              min={0}
              max={2}
              step={0.1}
            />
          </div>
        )}
      />

      {/* Submit & Actions */}
      <div className="flex gap-2 pt-4">
        <Button type="submit" className="flex-1">
          <Zap className="w-4 h-4 mr-2" />
          Process Images
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            const name = prompt('Preset name:')
            if (name) savePreset(name)
          }}
        >
          Save as Preset
        </Button>
      </div>
    </form>
  )
}
```

---

## 9. Real-time Updates & WebSocket Integration

### 9.1 WebSocket Provider

```typescript
// contexts/WebSocketProvider.tsx
import React, { createContext, useContext, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface WebSocketMessage {
  type: 'task_progress' | 'queue_update' | 'system_health'
  data: any
}

interface WebSocketContextType {
  isConnected: boolean
  send: (message: WebSocketMessage) => void
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = React.useState(false)
  const wsRef = React.useRef<WebSocket | null>(null)

  useEffect(() => {
    const ws = new WebSocket(
      `ws://${import.meta.env.VITE_API_HOST}/ws/tasks`
    )

    ws.onopen = () => setIsConnected(true)
    ws.onclose = () => setIsConnected(false)

    ws.onmessage = (event) => {
      const message: WebSocketMessage = JSON.parse(event.data)

      switch (message.type) {
        case 'task_progress':
          // Update task progress in React Query cache
          queryClient.setQueryData(
            ['tasks', message.data.task_id],
            message.data
          )
          break

        case 'queue_update':
          // Invalidate queue status
          queryClient.invalidateQueries({ queryKey: ['workspace', 'queue'] })
          break

        case 'system_health':
          // Update system health
          queryClient.setQueryData(['monitor', 'health'], message.data)
          break
      }
    }

    wsRef.current = ws

    return () => {
      ws.close()
    }
  }, [queryClient])

  const send = (message: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }

  return (
    <WebSocketContext.Provider value={{ isConnected, send }}>
      {children}
    </WebSocketContext.Provider>
  )
}

export const useWebSocket = () => {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocket must be used within WebSocketProvider')
  }
  return context
}
```

### 9.2 Task Progress Component

```typescript
// components/workspace/TaskProgress.tsx
export const TaskProgress: React.FC<{ taskId: string }> = ({ taskId }) => {
  const { data: task, isLoading } = useQuery({
    queryKey: ['tasks', taskId],
    queryFn: () => api.workspace.getTaskStatus(taskId),
    refetchInterval: 500,
  })

  if (!task) return null

  return (
    <div className="fixed bottom-4 right-4 w-96 bg-card border border-border rounded-lg shadow-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Processing...</h3>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => {/* close */}}
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span>{task.status_message}</span>
          <span className="font-mono">{Math.round(task.progress || 0)}%</span>
        </div>
        <Progress value={task.progress || 0} />
      </div>

      {task.state === 'FAILURE' && (
        <Alert variant="destructive">
          <AlertCircle className="w-4 h-4" />
          <AlertDescription>{task.error || 'Processing failed'}</AlertDescription>
        </Alert>
      )}

      {task.state === 'SUCCESS' && (
        <Alert>
          <Check className="w-4 h-4" />
          <AlertDescription>Processing complete!</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
```

---

## 10. Performance Optimizations

### 10.1 Code Splitting & Lazy Loading

```typescript
// router/routes.tsx
import { lazy, Suspense } from 'react'

const WorkspacePage = lazy(() => import('../pages/WorkspacePage'))
const GalleryPage = lazy(() => import('../pages/GalleryPage'))
const VideoPage = lazy(() => import('../pages/VideoPage'))
const MonitorPage = lazy(() => import('../pages/MonitorPage'))

export const routes = [
  {
    path: '/workspace',
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <WorkspacePage />
      </Suspense>
    ),
  },
  {
    path: '/gallery',
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <GalleryPage />
      </Suspense>
    ),
  },
  // ...
]
```

### 10.2 Image Optimization

```typescript
// components/shared/ImageThumbnail.tsx
export const ImageThumbnail: React.FC<{
  src: string
  alt: string
  width?: number
  height?: number
}> = ({ src, alt, width = 256, height = 256 }) => {
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState(false)

  return (
    <div className="aspect-square bg-muted rounded-md overflow-hidden">
      {isLoading && (
        <div className="w-full h-full flex items-center justify-center">
          <Loader className="w-6 h-6 animate-spin" />
        </div>
      )}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className={cn(
          'w-full h-full object-cover',
          isLoading && 'hidden',
          error && 'hidden'
        )}
        onLoad={() => setIsLoading(false)}
        onError={() => setError(true)}
      />
      {error && (
        <div className="w-full h-full flex items-center justify-center text-muted-foreground">
          <AlertCircle className="w-6 h-6" />
        </div>
      )}
    </div>
  )
}
```

### 10.3 Virtualized Lists

```typescript
// components/gallery/VirtualImageGrid.tsx
import { useVirtualizer } from '@tanstack/react-virtual'

export const VirtualImageGrid: React.FC<{ images: Image[] }> = ({ images }) => {
  const parentRef = React.useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: Math.ceil(images.length / 4), // 4 columns
    getScrollElement: () => parentRef.current,
    estimateSize: () => 350, // 256px image + padding
    overscan: 2, // Pre-render 2 rows
  })

  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => (
          <div
            key={virtualItem.key}
            style={{
              position: 'absolute',
              top: `${virtualItem.start}px`,
              left: 0,
              width: '100%',
            }}
          >
            {/* Render 4 images per row */}
          </div>
        ))}
      </div>
    </div>
  )
}
```

### 10.4 React Query Optimization

```typescript
// hooks/useGalleryImages.ts
export const useGalleryImages = (filters: GalleryFilters, page: number) => {
  return useQuery({
    queryKey: ['gallery', 'images', { ...filters, page }],
    queryFn: () => api.gallery.getImages({ ...filters, page, perPage: 20 }),

    // Optimizations
    keepPreviousData: true,        // Smooth pagination transitions
    staleTime: 5 * 60 * 1000,      // Cache for 5 minutes
    gcTime: 10 * 60 * 1000,        // Keep in memory for 10 minutes
    enabled: !!filters.status,     // Don't fetch until ready

    // Reduce re-renders
    structuralSharing: true,        // Only update changed properties
  })
}
```

---

## 11. Testing Strategy

### 11.1 Unit Tests (Vitest)

```typescript
// components/__tests__/ImageCard.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ImageCard } from '../ImageCard'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient()

describe('ImageCard', () => {
  const mockImage = {
    filename: 'test.png',
    path: '/path/to/test.png',
    created_at: new Date().toISOString(),
    metadata: { seed: '12345', prompt: 'test prompt' },
  }

  it('renders thumbnail and actions', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ImageCard image={mockImage} status="pending" />
      </QueryClientProvider>
    )

    expect(screen.getByRole('img')).toBeInTheDocument()
    expect(screen.getByText(/approve/i)).toBeInTheDocument()
  })

  it('calls onApprove when approve button is clicked', async () => {
    const onApprove = vi.fn()
    const user = userEvent.setup()

    render(
      <QueryClientProvider client={queryClient}>
        <ImageCard image={mockImage} status="pending" onApprove={onApprove} />
      </QueryClientProvider>
    )

    await user.click(screen.getByRole('button', { name: /approve/i }))
    expect(onApprove).toHaveBeenCalledWith(mockImage.filename)
  })

  it('shows metadata in popover', async () => {
    const user = userEvent.setup()

    render(
      <QueryClientProvider client={queryClient}>
        <ImageCard image={mockImage} status="pending" />
      </QueryClientProvider>
    )

    await user.click(screen.getByRole('button', { name: /details/i }))
    expect(screen.getByText(mockImage.metadata.seed)).toBeInTheDocument()
  })
})
```

### 11.2 Integration Tests (Playwright)

```typescript
// e2e/gallery.spec.ts
import { test, expect } from '@playwright/test'

test('approve image workflow', async ({ page }) => {
  await page.goto('http://localhost:5173/gallery')

  // Wait for images to load
  await page.waitForSelector('[data-testid="image-card"]')

  // Get first image
  const firstCard = page.locator('[data-testid="image-card"]').first()

  // Click approve checkbox
  await firstCard.locator('input[type="checkbox"]').check()

  // Click approve button
  await page.click('button:has-text("✅ Approve Selected")')

  // Verify success message
  await expect(page.locator('text=Moved 1 images to Approved')).toBeVisible()

  // Navigate to approved tab
  await page.click('[data-value="approved"]')

  // Verify image appears in approved tab
  await expect(
    page.locator('[data-testid="image-card"]:has-text("test.png")')
  ).toBeVisible()
})

test('bulk select images', async ({ page }) => {
  await page.goto('http://localhost:5173/gallery')

  // Select all
  await page.click('input[aria-label="Select all"]')

  // Verify checkboxes are checked
  const checkboxes = await page.locator('[data-testid="image-card"] input[type="checkbox"]').all()
  for (const checkbox of checkboxes) {
    await expect(checkbox).toBeChecked()
  }
})
```

---

## 12. Implementation Steps

### Phase 2A: Frontend Scaffold (1 day)

- [ ] Initialize Vite + React + TypeScript project
  - `npm create vite@latest ff-auto-frontend -- --template react-ts`
  - Install dependencies: React, React Router, Tailwind, shadnui

- [ ] Set up Tailwind + Shadnui
  - `npx shadcn-ui@latest init`
  - Configure `tailwind.config.ts`
  - Import global styles in `main.tsx`

- [ ] Create project structure
  ```
  src/
  ├── components/
  │  ├── layout/
  │  ├── workspace/
  │  ├── gallery/
  │  └── shared/
  ├── hooks/
  ├── stores/
  ├── api/
  ├── types/
  ├── pages/
  ├── styles/
  └── App.tsx
  ```

- [ ] Set up API client + React Query
  - Create `api/client.ts` with Axios instance
  - Create `hooks/useApi.ts` for common queries
  - Wrap App with `QueryClientProvider`

- [ ] Create Layout shell
  - Header, Sidebar, Main content area
  - Navigation routing with React Router
  - Mobile-responsive layout

### Phase 2B: Workspace Page (2-3 days)

- [ ] Create WorkspacePage component structure
- [ ] Build ConfigurationSidebar
  - PersonaSelector, VisionModelSelector, CLIPModelSelector
  - ParamAdjuster (limit, variations, strength)
  - LoRAConfigurator, DimensionsInput, SeedConfigurator
  - PresetManager (Load/Save/Delete)

- [ ] Build Persona Configuration section
  - PersonaTypeSelector, HairColorInput, HairstylesEditor
  - Save/Update functionality

- [ ] Build Workflow Configuration Studio
  - AgentEditor (Analyst & Turbo tabs)
  - PersonaTypeCreator form
  - Test workflow functionality

- [ ] Build Input Management
  - ImageUploadArea (drag-drop)
  - InputImageGrid (selection + details)
  - BulkActions (Select All, Clear)
  - ProcessButton (dispatch to queue)

- [ ] Build Execution History
  - ExecutionFilter, ExecutionTable
  - Task status indicators
  - Pagination support

- [ ] Build Queue Monitor
  - ComfyUI queue widget
  - Queue stats display
  - Live updates via WebSocket

- [ ] Add TaskProgressOverlay
  - Real-time progress tracking
  - Error display and handling

### Phase 2C: Gallery Page (2-3 days)

- [ ] Create GalleryPage component structure
- [ ] Build GalleryHeader
  - Title, Filters button, GroupBySelector
  - ViewModeToggle (grid/list), SearchBar, RefreshButton

- [ ] Build FilterDrawer
  - StatusFilter (radio buttons)
  - DateRangeFilter, PersonaFilter (multi-select)
  - SortSelector, GroupBySelector
  - ResetFilters, ApplyFilters buttons

- [ ] Build StatsPanel
  - Stat cards (total, approved, disapproved)
  - Approval rate chart (recharts)

- [ ] Build Gallery Tabs
  - **Pending Tab**:
    - BulkActions (Select All, Approve, Delete)
    - ImageGrid with virtualization
    - ImageCard with checkbox, rename, details, download
    - Pagination

  - **Approved Tab**:
    - DownloadByDateWidget (ZIP per date)
    - ImageGrid with undo/reject actions
    - Pagination

  - **Disapproved Tab**:
    - ImageGrid with recover/approve actions
    - Pagination

- [ ] Build ImageDetailLightbox
  - Full image display
  - MetadataPanel (seed, prompt, persona)
  - ExecutionInfo panel
  - Action buttons

- [ ] Build DailyNotesCard
  - NotesTextarea, SaveButton
  - Date-based persistence

- [ ] Implement Lazy Loading
  - IntersectionObserver for thumbnails
  - Virtualized list for large galleries

### Phase 2D: Shared Components (1-2 days)

- [ ] Create shared component library
  - Pagination component
  - LoadingSpinner
  - EmptyState
  - StatusBadge
  - ImageThumbnail
  - ConfirmDialog
  - Toast notification system
  - Breadcrumbs
  - FilterDrawer
  - DataTable
  - ImageCard

### Phase 2E: State Management & Hooks (1 day)

- [ ] Set up Zustand stores
  - `stores/workspaceStore.ts`
  - `stores/galleryStore.ts`
  - `stores/uiStore.ts`

- [ ] Create React Query hooks
  - `hooks/useGalleryImages.ts`
  - `hooks/useTaskProgress.ts`
  - `hooks/usePersonas.ts`
  - `hooks/usePresets.ts`

- [ ] Set up WebSocket integration
  - `contexts/WebSocketProvider.tsx`
  - `hooks/useWebSocket.ts`

- [ ] Create form hooks
  - `hooks/useConfigForm.ts`
  - `hooks/usePersonaForm.ts`

### Phase 2F: Styling & Theme (1 day)

- [ ] Configure Tailwind
  - Custom colors, spacing, breakpoints
  - Dark mode support
  - Custom utilities

- [ ] Create shadnui component overrides
  - Custom Button, Input, Select components
  - Consistent sizing and spacing

- [ ] Build component library documentation
  - Storybook setup (optional)
  - Component patterns guide

### Phase 2G: API Integration (1-2 days)

- [ ] Create API client
  - Base Axios instance with interceptors
  - Error handling and retry logic

- [ ] Create API service modules
  - `api/workspace.ts` (process, queue, tasks)
  - `api/gallery.ts` (images, approve, download)
  - `api/config.ts` (personas, presets)
  - `api/monitor.ts` (health, queues)

- [ ] Set up mock data (MSW)
  - Mock handlers for all endpoints
  - Test against backend API

### Phase 2H: Testing & QA (1-2 days)

- [ ] Write unit tests
  - Component tests (Vitest + React Testing Library)
  - Hook tests
  - Store tests

- [ ] Write integration tests
  - Page-level workflows (Playwright)
  - API integration tests

- [ ] Performance testing
  - Lighthouse audit
  - Bundle size analysis
  - Load testing with large image galleries

### Phase 2I: Docker & Deployment (1 day)

- [ ] Create Dockerfile.frontend
  - Node build stage → Nginx serve stage
  - Environment variable substitution

- [ ] Create docker-compose.yml service
  - Frontend service on port 3000
  - Nginx proxy to /api → backend

- [ ] Update CI/CD pipeline
  - Build and push frontend image
  - Deploy with backend

---

## 13. Common Patterns & Utilities

### 13.1 API Client Pattern

```typescript
// api/client.ts
import axios, { AxiosInstance } from 'axios'

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
})

// Request interceptor
apiClient.interceptors.request.use((config) => {
  // Add auth token if available
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

### 13.2 Mutation Pattern with Optimistic Updates

```typescript
// Example: Approve images mutation
const useApproveImages = () => {
  const queryClient = useQueryClient()
  const { addToast } = useUIStore()

  return useMutation({
    mutationFn: async (filenames: string[]) => {
      return await api.gallery.approve({ filenames })
    },

    // Optimistically update UI
    onMutate: async (filenames) => {
      // Cancel pending queries
      await queryClient.cancelQueries({ queryKey: ['gallery'] })

      // Update cache optimistically
      queryClient.setQueryData(['gallery', 'images'], (old: any) => {
        return old.filter((img: any) => !filenames.includes(img.filename))
      })
    },

    // Revert if error
    onError: (error, filenames, context) => {
      queryClient.invalidateQueries({ queryKey: ['gallery'] })
      addToast(`Failed to approve: ${error.message}`, 'error')
    },

    // Confirm on success
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gallery'] })
      addToast('Images approved!', 'success')
    },
  })
}
```

### 13.3 Conditional Rendering Utility

```typescript
// utils/cn.ts
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Usage:
<div className={cn(
  'p-4 rounded-md',
  status === 'pending' && 'bg-yellow-100',
  status === 'approved' && 'bg-green-100',
  status === 'disapproved' && 'bg-red-100',
)}>
```

---

## 14. Migration Checklist

### Frontend Preparation
- [ ] Review Streamlit UI/UX thoroughly
- [ ] Identify all forms, inputs, workflows
- [ ] Document state dependencies
- [ ] Create component hierarchy diagram
- [ ] Plan color scheme and visual design

### Development Setup
- [ ] Create Vite project structure
- [ ] Configure Tailwind + Shadnui
- [ ] Set up TypeScript configuration
- [ ] Initialize Git repository
- [ ] Set up development environment

### Component Development
- [ ] Build Layout shell
- [ ] Create reusable component library
- [ ] Build Workspace page
- [ ] Build Gallery page
- [ ] Implement shared utilities

### State & API
- [ ] Set up Zustand stores
- [ ] Create React Query hooks
- [ ] Implement API client
- [ ] Set up WebSocket provider
- [ ] Create mock data (MSW)

### Testing
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Test against real backend
- [ ] Performance testing
- [ ] Accessibility testing (a11y)

### Styling & Polish
- [ ] Finalize colors and typography
- [ ] Add animations and transitions
- [ ] Responsive design testing
- [ ] Dark mode testing
- [ ] Mobile testing

### Deployment
- [ ] Create Dockerfiles
- [ ] Update docker-compose
- [ ] Set up environment variables
- [ ] Test in Docker locally
- [ ] Deploy to staging
- [ ] Cutover from Streamlit

---

## Next Steps

1. **Immediate**: Finalize this plan with team feedback
2. **Week 1**: Begin Phase 2A (Scaffold) + Phase 2B (Workspace) in parallel
3. **Week 2**: Complete Phase 2C (Gallery) + Phase 2D-F (Polish)
4. **Week 3**: Phase 2G-I (Testing & Deployment)
5. **Week 4**: Phase 3 (Video & Monitor apps) if needed

---

## Appendix: File Size Estimates

| Component | Estimated Lines | Estimated Size |
|-----------|-----------------|--------|
| WorkspacePage.tsx | 400 | 12 KB |
| GalleryPage.tsx | 500 | 15 KB |
| ProcessingConfig.tsx | 200 | 6 KB |
| ImageGrid.tsx | 250 | 8 KB |
| ImageCard.tsx | 150 | 5 KB |
| API client | 150 | 4 KB |
| Zustand stores | 200 | 6 KB |
| React Query hooks | 250 | 8 KB |
| Shared components | 800 | 24 KB |
| Styles (Tailwind) | 300 | 9 KB |
| Tests | 1000+ | 30+ KB |
| **Total** | **~4500** | **~140 KB** (gzipped: ~40 KB) |

---

**End of Frontend Migration Plan**
