"""Rebuild exact daily execution artifacts from frozen main-window parameters.

The historical US full run predates the narrow ``daily.csv`` export.  This
module replays only the W13 expert set with each symbol/model row's already
frozen parameter snapshot.  A replay is published back to the authoritative
artifact directory only after its source-net return path matches the frozen
``returns.csv`` date-for-date and value-for-value within numerical tolerance.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from core.adaptive_regime import ADAPTIVE_ARTIFACT_ENV_VAR
from model_test.config import (
    build_main_window,
    build_stage_a_model_specs,
    build_stage_b_model_specs,
    load_research_config,
)
from model_test.execution import execute_tasks
from model_test.models import ModelSpec, RunRecord, TaskSpec
from model_test.summarize import pick_stage_b_winners


DEFAULT_EXPERT_MODEL_IDS = (
    "naive",
    "drift",
    "sm",
    "fsm",
    "sm_bayesian",
    "sm_bayesian_ml_lgbm",
    "rsm_adaptive_v1",
)
READY_STATUSES = {"success", "degraded"}
MANIFEST_NAME = "exact_daily_backfill_manifest.json"


class ExactDailyReplayError(ValueError):
    """Raised when an exact daily replay cannot be proven equivalent."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExactDailyReplayError(f"Unreadable JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ExactDailyReplayError(f"Expected JSON object: {path}")
    return value


def _read_return_frame(path: Path, *, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise ExactDailyReplayError(f"{label} is missing: {path}")
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise ExactDailyReplayError(f"{label} is unreadable: {path}") from exc
    required = {"date", "strategy_return"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ExactDailyReplayError(f"{label} lacks columns: {missing}")
    frame = frame[["date", "strategy_return"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["strategy_return"] = pd.to_numeric(frame["strategy_return"], errors="coerce")
    if frame["date"].isna().any() or not np.isfinite(
        frame["strategy_return"].to_numpy(dtype=float)
    ).all():
        raise ExactDailyReplayError(f"{label} contains invalid date/return rows")
    if frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
        raise ExactDailyReplayError(f"{label} dates must be unique and chronological")
    return frame.reset_index(drop=True)


def validate_daily_replay(
    *,
    source_returns_path: str | Path,
    replay_returns_path: str | Path,
    replay_daily_path: str | Path,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    """Prove that a replay preserves source-net returns and exact execution rows."""

    source_path = Path(source_returns_path)
    replay_path = Path(replay_returns_path)
    daily_path = Path(replay_daily_path)
    source = _read_return_frame(source_path, label="frozen returns.csv")
    replay = _read_return_frame(replay_path, label="replay returns.csv")
    if not source["date"].equals(replay["date"]):
        raise ExactDailyReplayError("source-net replay dates differ from frozen returns.csv")
    return_diff = np.abs(
        source["strategy_return"].to_numpy(dtype=float)
        - replay["strategy_return"].to_numpy(dtype=float)
    )
    max_diff = float(return_diff.max(initial=0.0))
    if max_diff > float(tolerance):
        raise ExactDailyReplayError(
            f"source-net returns drifted during exact daily replay (max_abs_diff={max_diff:.3g})"
        )

    if not daily_path.is_file():
        raise ExactDailyReplayError(f"replay daily.csv is missing: {daily_path}")
    try:
        daily = pd.read_csv(daily_path)
    except (OSError, pd.errors.ParserError) as exc:
        raise ExactDailyReplayError(f"replay daily.csv is unreadable: {daily_path}") from exc
    if "date" not in daily.columns or "strategy_return" not in daily.columns:
        raise ExactDailyReplayError("replay daily.csv requires date and strategy_return")
    position_column = next(
        (column for column in ("target_position", "position") if column in daily.columns),
        None,
    )
    if position_column is None:
        raise ExactDailyReplayError("replay daily.csv requires target_position/position")
    if "turnover" not in daily.columns:
        raise ExactDailyReplayError("replay daily.csv requires turnover")
    daily_dates = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
    daily_returns = pd.to_numeric(daily["strategy_return"], errors="coerce")
    positions = pd.to_numeric(daily[position_column], errors="coerce")
    turnover = pd.to_numeric(daily["turnover"], errors="coerce")
    if not source["date"].equals(daily_dates.reset_index(drop=True)):
        raise ExactDailyReplayError("daily.csv dates differ from frozen returns.csv")
    if not all(
        np.isfinite(values.to_numpy(dtype=float)).all()
        for values in (daily_returns, positions, turnover)
    ):
        raise ExactDailyReplayError("daily.csv contains missing return/position/turnover values")
    daily_diff = np.abs(
        source["strategy_return"].to_numpy(dtype=float) - daily_returns.to_numpy(dtype=float)
    )
    daily_max_diff = float(daily_diff.max(initial=0.0))
    if daily_max_diff > float(tolerance):
        raise ExactDailyReplayError(
            f"daily strategy_return differs from frozen returns.csv (max_abs_diff={daily_max_diff:.3g})"
        )
    if (turnover < -float(tolerance)).any():
        raise ExactDailyReplayError("daily.csv turnover cannot be negative")
    execution_position_column = "position" if "position" in daily.columns else position_column
    execution_position = pd.to_numeric(daily[execution_position_column], errors="coerce")
    if not np.isfinite(execution_position.to_numpy(dtype=float)).all():
        raise ExactDailyReplayError("daily.csv execution position must be finite")
    expected_turnover = execution_position.diff().abs()
    expected_turnover.iloc[0] = abs(float(execution_position.iloc[0]))
    turnover_diff = np.abs(
        turnover.to_numpy(dtype=float) - expected_turnover.to_numpy(dtype=float)
    )
    turnover_max_diff = float(turnover_diff.max(initial=0.0))
    if turnover_max_diff > float(tolerance):
        raise ExactDailyReplayError(
            f"daily turnover differs from execution position changes (max_abs_diff={turnover_max_diff:.3g})"
        )
    return {
        "row_count": int(len(source)),
        "date_start": source["date"].iloc[0].date().isoformat(),
        "date_end": source["date"].iloc[-1].date().isoformat(),
        "position_column": position_column,
        "return_max_abs_diff": max(max_diff, daily_max_diff),
        "turnover_validation": "exact_execution_position_delta",
        "turnover_max_abs_diff": turnover_max_diff,
        "source_returns_sha256": _sha256_file(source_path),
        "replay_returns_sha256": _sha256_file(replay_path),
        "daily_sha256": _sha256_file(daily_path),
    }


def _frozen_replay_spec(spec: ModelSpec) -> ModelSpec:
    payload = dict(spec.request_payload or {})
    if payload.get("family") == "search":
        payload["use_search"] = False
    return replace(spec, request_payload=payload)


def _safe_path_component(value: Any, *, field: str) -> str:
    if pd.isna(value):
        raise ExactDailyReplayError(f"{field} must be a non-empty path component")
    text = str(value)
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or Path(text).name != text
    ):
        raise ExactDailyReplayError(f"{field} must be a single safe path component: {text!r}")
    return text


def _load_source_records(source_dir: Path, model_ids: tuple[str, ...]) -> pd.DataFrame:
    path = source_dir / "runs.csv"
    if not path.is_file():
        raise ExactDailyReplayError(f"Frozen source runs.csv is missing: {path}")
    records = pd.read_csv(path, dtype={"symbol": "string"})
    required = {
        "symbol",
        "company_name",
        "segment_key",
        "trend_bucket",
        "volatility_bucket",
        "window_id",
        "window_kind",
        "model_id",
        "status",
        "params_snapshot_json",
        "returns_path",
    }
    missing = sorted(required - set(records.columns))
    if missing:
        raise ExactDailyReplayError(f"Frozen source runs.csv lacks fields: {missing}")
    selected = records.loc[
        records["model_id"].astype(str).isin(model_ids)
        & records["window_kind"].astype(str).eq("main")
        & records["status"].astype(str).isin(READY_STATUSES)
    ].copy()
    duplicates = selected.duplicated(["symbol", "model_id"], keep=False)
    if duplicates.any():
        raise ExactDailyReplayError("Frozen source has duplicate symbol/model main rows")
    present = set(selected["model_id"].astype(str))
    missing_models = sorted(set(model_ids) - present)
    if missing_models:
        raise ExactDailyReplayError(f"Frozen source lacks required expert rows: {missing_models}")
    counts = selected.groupby("model_id")["symbol"].nunique()
    if counts.nunique() != 1:
        raise ExactDailyReplayError(f"Required expert symbol coverage differs: {counts.to_dict()}")
    for value in selected["symbol"]:
        _safe_path_component(value, field="symbol")
    for value in selected["model_id"]:
        _safe_path_component(value, field="model_id")
    return selected.sort_values(["symbol", "model_id"]).reset_index(drop=True)


def _model_spec_registry(config: Any, source_dir: Path) -> dict[str, ModelSpec]:
    stage_a_specs = build_stage_a_model_specs(config)
    summary_path = source_dir / "model_summary.csv"
    if not summary_path.is_file():
        raise ExactDailyReplayError(f"Frozen model_summary.csv is missing: {summary_path}")
    summary = pd.read_csv(summary_path)
    stage_a_summary = summary.loc[summary["stage"].astype(str).eq("A")].copy()
    winners = pick_stage_b_winners(stage_a_summary)
    stage_b_specs = build_stage_b_model_specs(config, winners)
    return {
        spec.model_id: _frozen_replay_spec(spec)
        for spec in [*stage_a_specs, *stage_b_specs]
    }


def _parse_params(raw: Any, *, symbol: str, model_id: str) -> dict[str, Any]:
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ExactDailyReplayError(
            f"Invalid frozen params_snapshot_json for {symbol}/{model_id}"
        ) from exc
    if not isinstance(value, dict) or not value:
        raise ExactDailyReplayError(f"Missing frozen params for {symbol}/{model_id}")
    return value


def build_replay_tasks(
    *,
    config_path: str | Path,
    source_dir: str | Path,
    model_ids: Iterable[str] = DEFAULT_EXPERT_MODEL_IDS,
) -> tuple[list[TaskSpec], pd.DataFrame]:
    config = load_research_config(config_path)
    source = Path(source_dir).resolve()
    selected_ids = tuple(dict.fromkeys(str(value) for value in model_ids))
    records = _load_source_records(source, selected_ids)
    registry = _model_spec_registry(config, source)
    missing_specs = sorted(set(selected_ids) - set(registry))
    if missing_specs:
        raise ExactDailyReplayError(f"No model spec for replay experts: {missing_specs}")

    tasks: list[TaskSpec] = []
    for row in records.to_dict("records"):
        symbol = str(row["symbol"])
        model_id = str(row["model_id"])
        data_path = source / "data_snapshot" / f"{symbol}_daily.csv"
        if not data_path.is_file():
            raise ExactDailyReplayError(f"Frozen snapshot is missing: {data_path}")
        try:
            history_days = int(pd.read_csv(data_path, usecols=["date"]).shape[0])
        except (OSError, ValueError) as exc:
            raise ExactDailyReplayError(f"Frozen snapshot is unreadable: {data_path}") from exc
        window = build_main_window(config, history_days)
        if not window.available:
            raise ExactDailyReplayError(f"Frozen main window is unavailable for {symbol}")
        tasks.append(
            TaskSpec(
                symbol=symbol,
                company_name=str(row["company_name"]),
                segment_key=str(row["segment_key"]),
                trend_bucket=str(row["trend_bucket"]),
                volatility_bucket=str(row["volatility_bucket"]),
                source_kind="frozen_exact_daily_replay",
                data_path=str(data_path),
                market=config.market,
                adjust=config.adjust,
                model=registry[model_id],
                window=window,
                params_snapshot=_parse_params(
                    row["params_snapshot_json"], symbol=symbol, model_id=model_id
                ),
                execution=config.execution,
            )
        )
    return tasks, records


def _artifact_dir(root: Path, symbol: str, model_id: str) -> Path:
    return root / "artifacts" / symbol / "main" / model_id


def _publish_daily(source_path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(".csv.pending")
    shutil.copy2(source_path, staging)
    os.replace(staging, destination)


def backfill_exact_daily_artifacts(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    source_output_dir: str | Path,
    scratch_output_dir: str | Path,
    max_workers: int = 1,
    model_ids: Iterable[str] = DEFAULT_EXPERT_MODEL_IDS,
) -> tuple[dict[str, Any], Path]:
    """Replay and publish exact daily artifacts without replacing frozen returns."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    source = Path(source_output_dir).resolve()
    scratch = Path(scratch_output_dir).resolve()
    try:
        config_relative = config_file.relative_to(root)
        source_relative = source.relative_to(root)
        scratch.relative_to(root)
    except ValueError as exc:
        raise ExactDailyReplayError("config, source, and scratch paths must stay inside repo_root") from exc
    if source == scratch or scratch.is_relative_to(source) or source.is_relative_to(scratch):
        raise ExactDailyReplayError("scratch_output_dir must be separate from source_output_dir")
    scratch.mkdir(parents=True, exist_ok=True)
    config = load_research_config(config_file)
    if config.market != "US":
        raise ExactDailyReplayError("The historical exact-daily backfill is scoped to US")
    tasks, records = build_replay_tasks(
        config_path=config_file,
        source_dir=source,
        model_ids=model_ids,
    )
    record_lookup = {
        (str(row["symbol"]), str(row["model_id"])): row for row in records.to_dict("records")
    }
    proofs: dict[tuple[str, str], dict[str, Any]] = {}
    pending: list[TaskSpec] = []
    for task in tasks:
        key = (task.symbol, task.model.model_id)
        source_artifact = _artifact_dir(source, *key)
        daily_path = source_artifact / "daily.csv"
        if daily_path.is_file():
            try:
                proofs[key] = validate_daily_replay(
                    source_returns_path=source_artifact / "returns.csv",
                    replay_returns_path=source_artifact / "returns.csv",
                    replay_daily_path=daily_path,
                )
                continue
            except ExactDailyReplayError:
                pass
        replay_artifact = _artifact_dir(scratch, *key)
        if (replay_artifact / "daily.csv").is_file():
            try:
                proof = validate_daily_replay(
                    source_returns_path=source_artifact / "returns.csv",
                    replay_returns_path=replay_artifact / "returns.csv",
                    replay_daily_path=replay_artifact / "daily.csv",
                )
                _publish_daily(replay_artifact / "daily.csv", daily_path)
                proof["published_daily_sha256"] = _sha256_file(daily_path)
                frozen = record_lookup[key]
                proof["frozen_params_sha256"] = hashlib.sha256(
                    str(frozen["params_snapshot_json"]).encode("utf-8")
                ).hexdigest()
                proofs[key] = proof
                continue
            except ExactDailyReplayError:
                pass
        pending.append(task)

    adaptive_dir = source / "regime_artifacts"
    if any(task.model.model_id == "rsm_adaptive_v1" for task in pending):
        if not adaptive_dir.is_dir():
            raise ExactDailyReplayError(f"Adaptive artifact directory is missing: {adaptive_dir}")
        os.environ[ADAPTIVE_ARTIFACT_ENV_VAR] = str(adaptive_dir)

    def publish(record: RunRecord) -> None:
        key = (str(record.symbol), str(record.model_id))
        if record.status not in READY_STATUSES:
            raise ExactDailyReplayError(
                f"Replay failed for {record.symbol}/{record.model_id}: {record.error_message}"
            )
        frozen = record_lookup.get(key)
        if frozen is None:
            raise ExactDailyReplayError(f"Unexpected replay record: {key}")
        replay_artifact = _artifact_dir(scratch, *key)
        source_artifact = _artifact_dir(source, *key)
        proof = validate_daily_replay(
            source_returns_path=source_artifact / "returns.csv",
            replay_returns_path=replay_artifact / "returns.csv",
            replay_daily_path=replay_artifact / "daily.csv",
        )
        _publish_daily(replay_artifact / "daily.csv", source_artifact / "daily.csv")
        proof["published_daily_sha256"] = _sha256_file(source_artifact / "daily.csv")
        proof["frozen_params_sha256"] = hashlib.sha256(
            str(frozen["params_snapshot_json"]).encode("utf-8")
        ).hexdigest()
        proofs[key] = proof

    if pending:
        execute_tasks(
            pending,
            max(1, int(max_workers)),
            on_record=publish,
            artifacts_root=scratch / "artifacts",
        )
    missing = sorted(set(record_lookup) - set(proofs))
    if missing:
        raise ExactDailyReplayError(f"Exact daily replay is incomplete: {missing[:5]}")

    entries = [
        {"symbol": symbol, "model_id": model_id, **proofs[(symbol, model_id)]}
        for symbol, model_id in sorted(proofs)
    ]
    manifest = {
        "schema_version": "1.0",
        "phase": "W13_exact_daily_source_backfill",
        "status": "ready",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "market": config.market,
        "config_path": config_relative.as_posix(),
        "config_sha256": _sha256_file(config_file),
        "source_output_dir": source_relative.as_posix(),
        "source_data_manifest_sha256": _sha256_file(source / "data_manifest.json"),
        "source_model_summary_sha256": _sha256_file(source / "model_summary.csv"),
        "expert_model_ids": list(dict.fromkeys(str(value) for value in model_ids)),
        "artifact_count": len(entries),
        "symbol_count": int(records["symbol"].nunique()),
        "return_tolerance": 1e-12,
        "artifacts": entries,
    }
    manifest_path = source / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return manifest, manifest_path


__all__ = [
    "DEFAULT_EXPERT_MODEL_IDS",
    "ExactDailyReplayError",
    "MANIFEST_NAME",
    "backfill_exact_daily_artifacts",
    "build_replay_tasks",
    "validate_daily_replay",
]
