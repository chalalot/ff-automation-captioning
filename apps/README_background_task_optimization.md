# Image Fetching Optimization Comparison

This document illustrates the background task architecture before and after implementing the database-first "pending" check optimization.

## Before Optimization (Naive Approach)

In the naive approach, the background task would unconditionally hit the external API (ComfyUI) every minute to ask "are you done with any images?", or try to poll everything. This is highly inefficient when the system is idle.

```mermaid
graph TD
    A[Celery Beat Trigger Every 1 Min] --> B{Call ComfyUI API to get ALL tasks}
    B -->|API Response| C[Iterate through all returned tasks]
    C --> D{Is task completed?}
    D -->|Yes| E[Download Image]
    E --> F[Update Local Database]
    D -->|No| G[Do Nothing]
    F --> C
```

## After Optimization (Current Architecture)

In the optimized approach, the local database acts as the source of truth for what needs to be checked. The external API is only ever called if there is *known pending work*. When the system is idle, the task just performs a lightning-fast local DB query and sleeps.

```mermaid
graph TD
    A[Celery Beat Trigger Every 1 Min] --> B[Query Local DB for 'pending' Executions]
    B --> C{Are there pending records?}
    C -->|No| D[Log 'No pending tasks' & EXIT EARLY]
    
    C -->|Yes| E[Iterate only through pending IDs]
    E --> F{Call ComfyUI API for Status of ID}
    
    F -->|Completed| G[Download Image]
    G --> H[Update DB to 'completed']
    H --> E
    
    F -->|Failed| I[Update DB to 'failed']
    I --> E
    
    F -->|Still Running| J[Leave as 'pending' in DB]
    J --> E
```

### Key Differences:
1. **API Usage**: Before, the API was hit 1440 times a day minimum. Now, it's 0 times a day if the system is idle.
2. **Database Load**: Instead of scanning potentially thousands of completed tasks, it only looks for records explicitly marked as `pending`.
3. **Execution Time**: The early-exit `return` drops execution time from seconds down to milliseconds.