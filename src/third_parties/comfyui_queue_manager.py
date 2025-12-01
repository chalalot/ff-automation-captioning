"""
ComfyUI Queue Manager

Provides sequential request processing to ensure ComfyUI only handles one request at a time.
Uses asyncio.Semaphore to control access and prevent concurrent requests that would
overwhelm the ComfyUI server.

Features:
- Global request queue with semaphore-based access control
- Request prioritization and tracking
- Proper error handling and cleanup
- Logging for debugging queue operations
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Callable, Awaitable, List
from contextvars import ContextVar
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Global semaphore to ensure only one ComfyUI request at a time
_comfyui_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_lock = asyncio.Lock()

# Global queue state for frontend monitoring
_active_queue: List['QueuedRequest'] = []
_queue_state_lock = asyncio.Lock()

# Context variable to track request IDs for logging
_request_id_var: ContextVar[str] = ContextVar('request_id', default='unknown')


async def get_comfyui_semaphore() -> asyncio.Semaphore:
    """Get or create the global ComfyUI semaphore (max 1 concurrent request)."""
    global _comfyui_semaphore
    
    async with _semaphore_lock:
        if _comfyui_semaphore is None:
            _comfyui_semaphore = asyncio.Semaphore(1)  # Only 1 concurrent request
            logger.info("🔒 ComfyUI queue manager initialized (max 1 concurrent request)")
    
    return _comfyui_semaphore


@dataclass
class QueuedRequest:
    """Represents a queued ComfyUI request with metadata."""
    
    request_id: str
    description: str
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    celery_task_id: Optional[str] = None
    status: str = "queued"  # queued, running, completed, failed
    
    def __init__(self, request_id: str, description: str, celery_task_id: Optional[str] = None):
        self.request_id = request_id
        self.description = description
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
        self.celery_task_id = celery_task_id
        self.status = "queued"
        
    @property
    def wait_time(self) -> float:
        """Time spent waiting in queue."""
        start = self.started_at or time.time()
        return start - self.created_at
        
    @property
    def execution_time(self) -> Optional[float]:
        """Time spent executing (if completed)."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def total_time(self) -> float:
        """Total time from creation to completion (or current time)."""
        end = self.completed_at or time.time()
        return end - self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "description": self.description,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "celery_task_id": self.celery_task_id,
            "status": self.status,
            "wait_time": self.wait_time,
            "execution_time": self.execution_time,
            "total_time": self.total_time,
            "created_at_iso": datetime.fromtimestamp(self.created_at).isoformat(),
            "started_at_iso": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "completed_at_iso": datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
        }


async def _add_to_queue(request: QueuedRequest):
    """Add request to the active queue for monitoring."""
    async with _queue_state_lock:
        _active_queue.append(request)
        # Keep only last 50 requests to prevent memory bloat
        if len(_active_queue) > 50:
            _active_queue.pop(0)


async def _update_request_status(request_id: str, status: str, **kwargs):
    """Update request status in the active queue."""
    async with _queue_state_lock:
        for req in _active_queue:
            if req.request_id == request_id:
                req.status = status
                for key, value in kwargs.items():
                    if hasattr(req, key):
                        setattr(req, key, value)
                break


async def _remove_from_queue(request_id: str):
    """Remove request from active queue (after completion)."""
    async with _queue_state_lock:
        global _active_queue
        _active_queue = [req for req in _active_queue if req.request_id != request_id]


async def execute_with_queue(
    operation: Callable[[], Awaitable[Any]],
    description: str = "ComfyUI request",
    timeout: Optional[float] = None,
    celery_task_id: Optional[str] = None
) -> Any:
    """
    Execute a ComfyUI operation with queue management.
    
    Args:
        operation: Async function to execute
        description: Human-readable description for logging
        timeout: Optional timeout for the entire operation
        celery_task_id: Optional Celery task ID for cross-reference
        
    Returns:
        Result of the operation
        
    Raises:
        asyncio.TimeoutError: If operation times out
        Exception: Any exception raised by the operation
    """
    request_id = str(uuid.uuid4())[:8]
    _request_id_var.set(request_id)
    
    queued_request = QueuedRequest(request_id, description, celery_task_id)
    
    # Add to queue for monitoring
    await _add_to_queue(queued_request)
    
    logger.info(f"🔄 [Queue] Request {request_id} queued: {description}")
    
    # Get the semaphore (create if doesn't exist)
    semaphore = await get_comfyui_semaphore()
    
    try:
        # Wait for our turn with optional timeout
        if timeout:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        else:
            await semaphore.acquire()
            
        queued_request.started_at = time.time()
        wait_time = queued_request.wait_time
        
        # Update status to running
        await _update_request_status(request_id, "running", started_at=queued_request.started_at)
        
        logger.info(f"🚀 [Queue] Request {request_id} started (waited {wait_time:.1f}s): {description}")
        
        try:
            # Execute the actual operation
            if timeout:
                remaining_timeout = timeout - wait_time
                if remaining_timeout <= 0:
                    raise asyncio.TimeoutError(f"Request {request_id} timed out while waiting in queue")
                result = await asyncio.wait_for(operation(), timeout=remaining_timeout)
            else:
                result = await operation()
                
            queued_request.completed_at = time.time()
            execution_time = queued_request.execution_time
            
            # Update status to completed
            await _update_request_status(request_id, "completed", completed_at=queued_request.completed_at)
            
            # Record stats
            _queue_stats.record_request(queued_request, True)
            
            logger.info(f"✅ [Queue] Request {request_id} completed in {execution_time:.1f}s: {description}")
            return result
            
        except Exception as e:
            queued_request.completed_at = time.time()
            execution_time = queued_request.execution_time or 0
            
            # Update status to failed
            await _update_request_status(request_id, "failed", completed_at=queued_request.completed_at)
            
            # Record stats
            _queue_stats.record_request(queued_request, False)
            
            logger.error(f"❌ [Queue] Request {request_id} failed after {execution_time:.1f}s: {e}")
            raise
            
    except asyncio.TimeoutError:
        await _update_request_status(request_id, "timeout")
        _queue_stats.record_request(queued_request, False)
        logger.error(f"⏰ [Queue] Request {request_id} timed out: {description}")
        raise
    except Exception as e:
        await _update_request_status(request_id, "failed")
        _queue_stats.record_request(queued_request, False)
        logger.error(f"💥 [Queue] Request {request_id} failed to acquire semaphore: {e}")
        raise
    finally:
        # Always release the semaphore
        try:
            semaphore.release()
        except ValueError:
            # Semaphore was not acquired, ignore
            pass


# Convenience wrapper for ComfyUI client methods
async def queue_comfyui_request(
    client_method: Callable[[], Awaitable[Any]],
    operation_name: str,
    **kwargs
) -> Any:
    """
    Queue a ComfyUI client method call.
    
    Args:
        client_method: The client method to call
        operation_name: Name of the operation for logging
        **kwargs: Additional arguments for execute_with_queue
        
    Returns:
        Result of the client method
    """
    description = f"ComfyUI {operation_name}"
    
    return await execute_with_queue(
        operation=client_method,
        description=description,
        **kwargs
    )


# Stats tracking
class QueueStats:
    """Track queue statistics for monitoring."""
    
    def __init__(self):
        self.total_requests = 0
        self.completed_requests = 0
        self.failed_requests = 0
        self.total_wait_time = 0.0
        self.total_execution_time = 0.0
        
    def record_request(self, request: QueuedRequest, success: bool):
        """Record a completed request."""
        self.total_requests += 1
        
        if success:
            self.completed_requests += 1
        else:
            self.failed_requests += 1
            
        self.total_wait_time += request.wait_time
        if request.execution_time:
            self.total_execution_time += request.execution_time
    
    @property
    def average_wait_time(self) -> float:
        """Average time spent waiting in queue."""
        return self.total_wait_time / max(1, self.total_requests)
    
    @property
    def average_execution_time(self) -> float:
        """Average execution time."""
        return self.total_execution_time / max(1, self.completed_requests)
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        return (self.completed_requests / max(1, self.total_requests)) * 100

    def __str__(self) -> str:
        return (
            f"Queue Stats: {self.total_requests} total, "
            f"{self.completed_requests} completed ({self.success_rate:.1f}% success), "
            f"avg wait: {self.average_wait_time:.1f}s, "
            f"avg execution: {self.average_execution_time:.1f}s"
        )


# Global stats instance
_queue_stats = QueueStats()


def get_queue_stats() -> QueueStats:
    """Get the global queue statistics."""
    return _queue_stats


async def get_queue_status() -> Dict[str, Any]:
    """Get current queue status information."""
    semaphore = await get_comfyui_semaphore()
    
    return {
        "semaphore_value": semaphore._value,  # Number of available slots
        "max_concurrent": 1,
        "stats": {
            "total_requests": _queue_stats.total_requests,
            "completed_requests": _queue_stats.completed_requests,
            "failed_requests": _queue_stats.failed_requests,
            "success_rate": _queue_stats.success_rate,
            "average_wait_time": _queue_stats.average_wait_time,
            "average_execution_time": _queue_stats.average_execution_time
        }
    }


async def get_active_queue() -> List[Dict[str, Any]]:
    """Get the current active queue for frontend monitoring."""
    async with _queue_state_lock:
        return [req.to_dict() for req in _active_queue]


async def get_detailed_queue_status() -> Dict[str, Any]:
    """Get comprehensive queue status including active requests."""
    semaphore = await get_comfyui_semaphore()
    active_requests = await get_active_queue()
    
    # Categorize requests
    queued_requests = [req for req in active_requests if req["status"] == "queued"]
    running_requests = [req for req in active_requests if req["status"] == "running"]
    completed_requests = [req for req in active_requests if req["status"] in ["completed", "failed", "timeout"]]
    
    # Calculate current queue position for each queued request
    for i, req in enumerate(queued_requests):
        req["queue_position"] = i + 1
    
    return {
        "timestamp": datetime.now().isoformat(),
        "semaphore": {
            "available_slots": semaphore._value,
            "max_concurrent": 1,
            "is_running": semaphore._value == 0
        },
        "queue": {
            "total_active": len(active_requests),
            "queued_count": len(queued_requests),
            "running_count": len(running_requests),
            "completed_count": len(completed_requests),
            "queued_requests": queued_requests,
            "running_requests": running_requests,
            "recent_completed": completed_requests[-10:]  # Last 10 completed
        },
        "stats": {
            "total_requests": _queue_stats.total_requests,
            "completed_requests": _queue_stats.completed_requests,
            "failed_requests": _queue_stats.failed_requests,
            "success_rate": _queue_stats.success_rate,
            "average_wait_time": _queue_stats.average_wait_time,
            "average_execution_time": _queue_stats.average_execution_time
        }
    }


async def get_request_by_id(request_id: str) -> Optional[Dict[str, Any]]:
    """Get specific request details by ID."""
    async with _queue_state_lock:
        for req in _active_queue:
            if req.request_id == request_id:
                return req.to_dict()
        return None


async def get_requests_by_celery_task(celery_task_id: str) -> List[Dict[str, Any]]:
    """Get all requests associated with a Celery task."""
    async with _queue_state_lock:
        return [req.to_dict() for req in _active_queue if req.celery_task_id == celery_task_id]
