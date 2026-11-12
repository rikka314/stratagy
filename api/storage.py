"""Bounded 24-hour persistence for API datasets and calculation jobs."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from core.config import DATA_DIR
from core.workspace_cache import WorkspaceSnapshotStore, new_workspace_id


class ApiStorage:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else Path(DATA_DIR) / "runtime-cache" / "api"
        self.datasets = WorkspaceSnapshotStore(base / "datasets", max_workspace_bytes=64 * 1024 * 1024, max_total_bytes=512 * 1024 * 1024)
        self.jobs = WorkspaceSnapshotStore(base / "jobs", max_workspace_bytes=160 * 1024 * 1024, max_total_bytes=1024 * 1024 * 1024)
        self._lock = RLock()

    @staticmethod
    def new_id() -> str:
        return new_workspace_id()

    def save_dataset(self, dataset_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self.datasets.save(dataset_id, payload)

    def load_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self.datasets.load(dataset_id)

    def save_job(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self.jobs.save(job_id, payload)

    def load_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self.jobs.load(job_id)


storage = ApiStorage()

