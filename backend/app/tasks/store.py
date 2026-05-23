from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from app.core.models import SearchGroup, SearchResponse

TaskStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class SearchTaskRecord:
    task_id: str
    status: TaskStatus = "pending"
    message: str | None = None
    result: SearchResponse | None = None
    error: str | None = None
    groups: list[SearchGroup] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)


class SearchTaskStore:
    """In-process task store for async search jobs (asyncio.create_task)."""

    def __init__(self, *, ttl_seconds: float = 3600) -> None:
        self._tasks: dict[str, SearchTaskRecord] = {}
        self._lock = asyncio.Lock()
        self._ttl_seconds = ttl_seconds

    async def create(self) -> str:
        task_id = str(uuid.uuid4())
        async with self._lock:
            self._purge_expired_locked()
            self._tasks[task_id] = SearchTaskRecord(task_id=task_id)
        return task_id

    async def get(self, task_id: str) -> SearchTaskRecord | None:
        async with self._lock:
            self._purge_expired_locked()
            return self._tasks.get(task_id)

    async def set_running(self, task_id: str, message: str | None = None) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "running"
            if message:
                task.message = message

    async def update_progress(
        self,
        task_id: str,
        *,
        message: str | None = None,
        groups: list[SearchGroup] | None = None,
    ) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if message:
                task.message = message
            if groups is not None:
                task.groups = groups

    async def complete(self, task_id: str, result: SearchResponse) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "completed"
            task.result = result
            task.groups = result.groups
            task.message = "Готово"
            task.error = None

    async def fail(self, task_id: str, error: str) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "failed"
            task.error = error
            task.message = error

    def _purge_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [
            tid
            for tid, task in self._tasks.items()
            if now - task.created_at > self._ttl_seconds
        ]
        for tid in expired:
            del self._tasks[tid]


search_task_store = SearchTaskStore()
