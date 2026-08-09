from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from model_test import REPO_ROOT, WORKSPACE_ROOT
from model_test.config import load_research_config
from model_test.control import (
    PAUSED_EXIT_CODE,
    PAUSE_REQUEST_FILENAME,
    PROGRESS_FILENAME,
    atomic_write_json,
    read_json_mapping,
    utc_now,
)
from model_test.preflight import inspect_research_config


CAMPAIGNS_ROOT = WORKSPACE_ROOT / "outputs" / "_campaigns"
CAMPAIGN_FILENAME = "campaign.json"
CAMPAIGN_LOG_FILENAME = "campaign.log"
ACTIVE_STATUSES = {"preflight", "running", "pause_requested", "resuming"}
RESUMABLE_STATUSES = {"paused", "failed"}
DEFAULT_CONFIG_PATHS = (
    REPO_ROOT / "model-test" / "configs" / "full_us_deans_60.json",
    REPO_ROOT / "model-test" / "configs" / "full_cn_a_deans_60.json",
    REPO_ROOT / "model-test" / "configs" / "full_cross_market_deans_60.json",
)


@dataclass(frozen=True)
class CampaignSnapshot:
    campaign: dict[str, Any]
    run: dict[str, Any] | None
    phase: str | None
    process: dict[str, Any]
    progress: dict[str, Any]
    pause: dict[str, Any]
    error: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign": self.campaign,
            "run": self.run,
            "phase": self.phase,
            "process": self.process,
            "progress": self.progress,
            "pause": self.pause,
            "error": self.error,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state() -> tuple[str, bool]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    changed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return revision, not bool(changed)


def _process_alive(pid: Any) -> bool:
    try:
        numeric_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if numeric_pid <= 0:
        return False
    try:
        import psutil

        return bool(psutil.pid_exists(numeric_pid) and psutil.Process(numeric_pid).is_running())
    except Exception:
        try:
            os.kill(numeric_pid, 0)
        except (OSError, ValueError):
            return False
        return True


def _campaign_dir(campaign_id: str) -> Path:
    if not campaign_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in campaign_id):
        raise ValueError("campaign_id may contain only letters, numbers, '-' and '_'.")
    return CAMPAIGNS_ROOT / campaign_id


def _state_path(campaign_id: str) -> Path:
    return _campaign_dir(campaign_id) / CAMPAIGN_FILENAME


def _load_state(campaign_id: str) -> dict[str, Any]:
    payload = read_json_mapping(_state_path(campaign_id))
    if payload is None:
        raise FileNotFoundError(f"Campaign state is missing or unreadable: {campaign_id}")
    return payload


def _write_state(campaign_id: str, state: dict[str, Any]) -> None:
    payload = dict(state)
    payload["updated_at"] = utc_now()
    atomic_write_json(_state_path(campaign_id), payload)


def _default_campaign_id() -> str:
    return f"window3b-full-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def list_campaign_ids() -> list[str]:
    try:
        entries = list(CAMPAIGNS_ROOT.iterdir())
    except OSError:
        return []
    rows: list[tuple[float, str]] = []
    for entry in entries:
        state_path = entry / CAMPAIGN_FILENAME
        if not entry.is_dir() or not state_path.is_file():
            continue
        try:
            rows.append((state_path.stat().st_mtime, entry.name))
        except OSError:
            continue
    return [name for _mtime, name in sorted(rows, reverse=True)]


def load_campaign_snapshot(campaign_id: str) -> CampaignSnapshot:
    state = _load_state(campaign_id)
    control_dir = _campaign_dir(campaign_id)
    progress = read_json_mapping(control_dir / PROGRESS_FILENAME) or {}
    pause_requested = (control_dir / PAUSE_REQUEST_FILENAME).is_file()
    process = dict(state.get("process") or {})
    process["manager_alive"] = _process_alive(process.get("manager_pid"))
    process["runner_alive"] = _process_alive(process.get("runner_pid"))
    runs = list(state.get("runs") or [])
    active_index = state.get("active_run_index")
    active_run = None
    if isinstance(active_index, int) and 0 <= active_index < len(runs):
        active_run = dict(runs[active_index])
    status = str(state.get("status") or "unknown")
    if (
        status in ACTIVE_STATUSES
        and process.get("manager_pid")
        and not process["manager_alive"]
        and not process["runner_alive"]
    ):
        status = "failed"
        state["status"] = status
        state["phase"] = "stale_process"
        state["error"] = {
            "message": "Background manager is no longer running; checkpoint data was preserved.",
            "at": utc_now(),
        }
        _write_state(campaign_id, state)
    display_status = "pause_requested" if pause_requested and status == "running" else status
    campaign = {
        "schema_version": state.get("schema_version", "1.0"),
        "campaign_id": campaign_id,
        "status": display_status,
        "created_at": state.get("created_at"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "completed_at": state.get("completed_at"),
        "git_commit": state.get("git_commit"),
        "runs": runs,
    }
    return CampaignSnapshot(
        campaign=campaign,
        run=active_run,
        phase=progress.get("phase") or state.get("phase"),
        process=process,
        progress=progress,
        pause={
            "requested": pause_requested,
            "requested_at": (read_json_mapping(control_dir / PAUSE_REQUEST_FILENAME) or {}).get("requested_at"),
        },
        error=state.get("error") if isinstance(state.get("error"), dict) else None,
    )


def _assert_no_active_campaign() -> None:
    for campaign_id in list_campaign_ids():
        try:
            snapshot = load_campaign_snapshot(campaign_id)
        except Exception:
            continue
        status = snapshot.campaign.get("status")
        if status in ACTIVE_STATUSES and (
            snapshot.process.get("manager_alive") or snapshot.process.get("runner_alive")
        ):
            raise RuntimeError(f"Campaign {campaign_id!r} is already active.")


def _build_run_entries(config_paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_path in config_paths:
        path = Path(raw_path).resolve()
        config = load_research_config(path)
        entries.append(
            {
                "config_name": config.name,
                "market": "CROSS" if config.is_cross_market_aggregation else config.market,
                "config_path": str(path),
                "config_sha256": _sha256_file(path),
                "output_subdir": config.output_subdir,
                "status": "pending",
                "task_estimate": None,
            }
        )
    return entries


def _spawn_worker(campaign_id: str) -> int:
    control_dir = _campaign_dir(campaign_id)
    log_path = control_dir / CAMPAIGN_LOG_FILENAME
    command = [
        sys.executable,
        str(WORKSPACE_ROOT / "manage_campaign.py"),
        "worker",
        "--campaign-id",
        campaign_id,
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True
    with log_path.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            **popen_kwargs,
        )
    state = _load_state(campaign_id)
    state["process"] = {"manager_pid": process.pid, "runner_pid": None}
    _write_state(campaign_id, state)
    return int(process.pid)


def start_campaign(
    campaign_id: str | None = None,
    *,
    config_paths: Iterable[str | Path] = DEFAULT_CONFIG_PATHS,
) -> CampaignSnapshot:
    _assert_no_active_campaign()
    campaign_id = campaign_id or _default_campaign_id()
    control_dir = _campaign_dir(campaign_id)
    if control_dir.exists():
        raise FileExistsError(f"Campaign already exists; use resume instead: {campaign_id}")
    runs = _build_run_entries(config_paths)
    for run in runs:
        output_dir = WORKSPACE_ROOT / "outputs" / str(run["output_subdir"])
        if output_dir.exists():
            raise FileExistsError(f"Output already exists; refusing a new run: {output_dir}")
    revision, clean = _git_state()
    if not clean:
        raise RuntimeError("Official campaign requires a clean git worktree.")
    control_dir.mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": "1.0",
        "campaign_id": campaign_id,
        "status": "preflight",
        "phase": "preflight",
        "created_at": utc_now(),
        "started_at": None,
        "completed_at": None,
        "git_commit": revision,
        "active_run_index": None,
        "runs": runs,
        "process": {"manager_pid": None, "runner_pid": None},
        "error": None,
    }
    _write_state(campaign_id, state)
    _spawn_worker(campaign_id)
    return load_campaign_snapshot(campaign_id)


def request_pause(campaign_id: str) -> CampaignSnapshot:
    snapshot = load_campaign_snapshot(campaign_id)
    if snapshot.campaign.get("status") not in {"preflight", "running", "resuming"}:
        raise RuntimeError(f"Campaign is not running: {snapshot.campaign.get('status')}")
    atomic_write_json(
        _campaign_dir(campaign_id) / PAUSE_REQUEST_FILENAME,
        {"schema_version": "1.0", "campaign_id": campaign_id, "requested_at": utc_now()},
    )
    return load_campaign_snapshot(campaign_id)


def _validate_resume_state(state: dict[str, Any]) -> None:
    revision, clean = _git_state()
    if not clean:
        raise RuntimeError("Resume requires a clean git worktree.")
    if revision != state.get("git_commit"):
        raise RuntimeError("Git commit changed since campaign creation; refusing an incompatible resume.")
    for run in state.get("runs") or []:
        path = Path(str(run.get("config_path") or ""))
        if not path.is_file() or _sha256_file(path) != run.get("config_sha256"):
            raise RuntimeError(f"Config changed since campaign creation: {path}")


def resume_campaign(campaign_id: str) -> CampaignSnapshot:
    _assert_no_active_campaign()
    state = _load_state(campaign_id)
    if state.get("status") not in RESUMABLE_STATUSES:
        raise RuntimeError(f"Campaign cannot be resumed from status {state.get('status')!r}.")
    _validate_resume_state(state)
    pause_path = _campaign_dir(campaign_id) / PAUSE_REQUEST_FILENAME
    if pause_path.exists():
        pause_path.unlink()
    state["status"] = "resuming"
    state["phase"] = "resuming"
    state["error"] = None
    state["process"] = {"manager_pid": None, "runner_pid": None}
    _write_state(campaign_id, state)
    _spawn_worker(campaign_id)
    return load_campaign_snapshot(campaign_id)


def _mark_failed(campaign_id: str, message: str) -> None:
    state = _load_state(campaign_id)
    active_index = state.get("active_run_index")
    if isinstance(active_index, int) and 0 <= active_index < len(state.get("runs") or []):
        state["runs"][active_index]["status"] = "failed"
    state["status"] = "failed"
    state["phase"] = "failed"
    state["error"] = {"message": message, "at": utc_now()}
    state["process"] = {"manager_pid": os.getpid(), "runner_pid": None}
    _write_state(campaign_id, state)


def run_campaign_worker(campaign_id: str) -> int:
    try:
        state = _load_state(campaign_id)
        state["process"] = {"manager_pid": os.getpid(), "runner_pid": None}
        if state.get("status") == "preflight":
            reports: list[dict[str, Any]] = []
            for run in state.get("runs") or []:
                if run.get("market") == "CROSS":
                    continue
                report = inspect_research_config(str(run["config_path"]), allow_dirty=False)
                run["task_estimate"] = report.get("task_estimate")
                reports.append(report)
            if not reports or not all(report.get("ready") for report in reports):
                failed = [report.get("config_name") for report in reports if not report.get("ready")]
                raise RuntimeError(f"Formal preflight failed: {', '.join(str(item) for item in failed)}")
        else:
            _validate_resume_state(state)

        state["status"] = "running"
        state["phase"] = "campaign_start"
        state["started_at"] = state.get("started_at") or utc_now()
        state["error"] = None
        _write_state(campaign_id, state)

        control_dir = _campaign_dir(campaign_id)
        for run_index, run in enumerate(state.get("runs") or []):
            if run.get("status") == "completed":
                continue
            if (control_dir / PAUSE_REQUEST_FILENAME).is_file():
                state["status"] = "paused"
                state["phase"] = "between_runs"
                state["active_run_index"] = run_index
                state["process"] = {"manager_pid": os.getpid(), "runner_pid": None}
                _write_state(campaign_id, state)
                return PAUSED_EXIT_CODE

            state["active_run_index"] = run_index
            state["phase"] = "launching_run"
            state["runs"][run_index]["status"] = "running"
            _write_state(campaign_id, state)
            command = [
                sys.executable,
                str(WORKSPACE_ROOT / "run_research.py"),
                "--config",
                str(run["config_path"]),
                "--control-dir",
                str(control_dir),
            ]
            child = subprocess.Popen(command, cwd=REPO_ROOT)
            state = _load_state(campaign_id)
            state["process"] = {"manager_pid": os.getpid(), "runner_pid": child.pid}
            _write_state(campaign_id, state)
            exit_code = int(child.wait())
            state = _load_state(campaign_id)
            state["process"] = {"manager_pid": os.getpid(), "runner_pid": None}
            if exit_code == PAUSED_EXIT_CODE:
                state["status"] = "paused"
                state["phase"] = "paused"
                state["runs"][run_index]["status"] = "paused"
                _write_state(campaign_id, state)
                return exit_code
            if exit_code != 0:
                raise RuntimeError(f"Run {run['config_name']} exited with code {exit_code}.")
            state["runs"][run_index]["status"] = "completed"
            state["phase"] = "run_completed"
            _write_state(campaign_id, state)

        state = _load_state(campaign_id)
        state["status"] = "completed"
        state["phase"] = "completed"
        state["completed_at"] = utc_now()
        state["process"] = {"manager_pid": os.getpid(), "runner_pid": None}
        _write_state(campaign_id, state)
        return 0
    except Exception as exc:
        _mark_failed(campaign_id, str(exc))
        print(f"[campaign failed] {exc}", file=sys.stderr)
        return 1


def tail_campaign_log(campaign_id: str, *, line_count: int = 100) -> str:
    path = _campaign_dir(campaign_id) / CAMPAIGN_LOG_FILENAME
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max(1, int(line_count)):])
