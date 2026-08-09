from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTROL_DIR_ENV = "STRATAGY_RESEARCH_CONTROL_DIR"
PROGRESS_FILENAME = "progress.json"
PAUSE_REQUEST_FILENAME = "pause.request.json"
PAUSED_EXIT_CODE = 75


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(5):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))


def read_json_mapping(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


class ResearchPauseRequested(RuntimeError):
    """Raised only after every currently running task batch is checkpointed."""


class ResearchControl:
    def __init__(self, control_dir: str | Path | None = None) -> None:
        raw = control_dir or os.getenv(CONTROL_DIR_ENV)
        self.control_dir = Path(raw).resolve() if raw else None

    @property
    def enabled(self) -> bool:
        return self.control_dir is not None

    @property
    def progress_path(self) -> Path | None:
        return self.control_dir / PROGRESS_FILENAME if self.control_dir else None

    @property
    def pause_request_path(self) -> Path | None:
        return self.control_dir / PAUSE_REQUEST_FILENAME if self.control_dir else None

    def pause_requested(self) -> bool:
        path = self.pause_request_path
        return bool(path and path.is_file())

    def update(self, **changes: Any) -> None:
        path = self.progress_path
        if path is None:
            return
        payload = read_json_mapping(path) or {"schema_version": "1.0"}
        payload.update(changes)
        payload["updated_at"] = utc_now()
        atomic_write_json(path, payload)

    def set_phase(
        self,
        phase: str,
        *,
        config_name: str | None = None,
        planned_records: int | None = None,
        completed_records: int | None = None,
        in_flight_batches: int | None = None,
        pending_batches: int | None = None,
    ) -> None:
        changes: dict[str, Any] = {"phase": phase}
        optional = {
            "config_name": config_name,
            "planned_records": planned_records,
            "completed_records": completed_records,
            "in_flight_batches": in_flight_batches,
            "pending_batches": pending_batches,
        }
        changes.update({key: value for key, value in optional.items() if value is not None})
        self.update(**changes)

    def checkpoint_record(
        self,
        *,
        phase: str,
        completed_records: int,
        planned_records: int,
        status_counts: dict[str, int],
        last_record_key: tuple[str, str, str],
        run_completed_records: int | None = None,
    ) -> None:
        changes: dict[str, Any] = dict(
            phase=phase,
            completed_records=int(completed_records),
            planned_records=int(planned_records),
            status_counts={str(key): int(value) for key, value in status_counts.items()},
            last_record_key=list(last_record_key),
        )
        if run_completed_records is not None:
            changes["run_completed_records"] = int(run_completed_records)
        self.update(**changes)

    def update_queue(self, *, in_flight_batches: int, pending_batches: int) -> None:
        self.update(
            in_flight_batches=int(in_flight_batches),
            pending_batches=int(pending_batches),
            pause_requested=self.pause_requested(),
        )

    def raise_if_pause_requested(self, safe_point: str) -> None:
        if not self.pause_requested():
            return
        self.update(phase=safe_point, pause_requested=True, in_flight_batches=0)
        raise ResearchPauseRequested(f"Pause requested at safe point: {safe_point}")
