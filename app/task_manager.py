"""
task_manager.py -- Bounded Background Task Manager for Ciel Desktop Assistant
Executes long-running operations (image generation, research, model queries, scripts)
asynchronously in a bounded thread pool without blocking Flask requests.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
import inspect
import json
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

log = logging.getLogger("ciel.tasks")


class TaskStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str
    task_type: str
    status: str = TaskStatus.QUEUED
    progress: int = 0
    progress_message: str = "Task queued"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    max_duration: Optional[float] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    events_queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=100))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat() if self.created_at else None,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "completed_at": datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
            "duration_seconds": (
                round(self.completed_at - self.started_at, 2)
                if (self.completed_at and self.started_at)
                else None
            ),
            "result": self.result,
            "error": self.error,
        }

    def emit_event(self, event_type: str = "progress", data: Optional[Dict[str, Any]] = None):
        payload = {
            "event": event_type,
            "task_id": self.id,
            "status": self.status,
            "progress": self.progress,
            "message": self.progress_message,
            "timestamp": time.time(),
        }
        if data:
            payload.update(data)
        try:
            self.events_queue.put_nowait(payload)
        except queue.Full:
            pass

    def update_progress(self, percent: int, message: str = ""):
        self.progress = min(max(percent, 0), 100)
        if message:
            self.progress_message = message
        self.emit_event("progress")


class TaskManager:
    def __init__(self, max_workers: int = 4, max_history: int = 200):
        self.max_workers = max_workers
        self.max_history = max_history
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ciel_task")
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        task_type: str,
        target_fn: Callable[..., Any],
        *args,
        max_duration: Optional[float] = None,
        task_id: Optional[str] = None,
        **kwargs,
    ) -> Task:
        t_id = task_id or uuid.uuid4().hex[:12]
        task = Task(id=t_id, task_type=task_type, max_duration=max_duration)
        with self._lock:
            # Prune oldest completed tasks if exceeding max history
            if len(self._tasks) >= self.max_history:
                completed = [
                    t.id for t in self._tasks.values()
                    if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                ]
                for old_id in completed[: len(self._tasks) - self.max_history + 1]:
                    self._tasks.pop(old_id, None)
            self._tasks[t_id] = task

        task.emit_event("queued")
        self._executor.submit(self._run_task, task, target_fn, *args, **kwargs)
        return task

    def _run_task(self, task: Task, target_fn: Callable[..., Any], *args, **kwargs):
        if task.cancel_event.is_set():
            task.status = TaskStatus.CANCELLED
            task.progress_message = "Task cancelled before start."
            task.completed_at = time.time()
            task.emit_event("cancelled")
            return

        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        task.progress_message = "Task started"
        task.emit_event("started")

        try:
            # If target_fn accepts task context keyword argument, inject it
            sig = inspect.signature(target_fn)
            if "task_ctx" in sig.parameters:
                kwargs["task_ctx"] = task

            res = target_fn(*args, **kwargs)

            if task.cancel_event.is_set():
                task.status = TaskStatus.CANCELLED
                task.progress_message = "Task cancelled during execution."
                task.completed_at = time.time()
                task.emit_event("cancelled")
            else:
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.progress_message = "Completed successfully."
                task.result = res
                task.completed_at = time.time()
                task.emit_event("completed", {"result": res})

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.progress_message = f"Failed: {e}"
            task.completed_at = time.time()
            log.exception(f"[TaskManager] Task {task.id} failed: {e}")
            task.emit_event("failed", {"error": str(e)})

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            task.cancel_event.set()
            if task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.CANCELLED
                task.progress_message = "Task cancelled from queue."
                task.completed_at = time.time()
                task.emit_event("cancelled")
            return True

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks[:limit]]


task_manager = TaskManager()
