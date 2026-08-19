from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from core.adaptive_regime import ADAPTIVE_ARTIFACT_ENV_VAR, ADAPTIVE_MODEL_ID
from core.lightgbm_runtime import configure_lightgbm_environment, validate_lightgbm_device
from model_test import WORKSPACE_ROOT
from model_test.adaptive_router import train_adaptive_router_artifacts
from model_test.config import (
    DEFAULT_SEARCH_SEED,
    build_main_window,
    build_request_params_snapshot,
    build_rolling_windows,
    build_stage_a_model_specs,
    build_stage_b_model_specs,
    load_research_config,
)
from model_test.control import PAUSED_EXIT_CODE, ResearchControl, ResearchPauseRequested
from model_test.execution import ExecutionPaused, execute_tasks
from model_test.models import ModelSpec, RunRecord, StockProfile, TaskSpec
from model_test.observability import (
    ensure_optional_dependencies,
    generate_quantstats_outputs,
    log_research_run_to_mlflow,
)
from model_test.reporting import (
    build_market_strategy_payload,
    build_report_payload,
    render_market_strategy_markdown,
    render_report_markdown,
)
from model_test.summarize import (
    MARKET_MATRIX_COLUMNS,
    build_market_strategy_matrix,
    build_market_strategy_recommendations,
    build_model_summary,
    build_robustness_summary,
    build_segment_summary,
    pick_stage_b_winners,
    profiles_to_dataframe,
)
from model_test.universe import build_stock_profiles


CHECKPOINT_RUNS_FILENAME = "_checkpoint_runs.csv"
CHECKPOINT_META_FILENAME = "_checkpoint_meta.json"
RUN_RECORD_COLUMNS = list(RunRecord.__dataclass_fields__.keys())


def _build_main_tasks(stock_profiles, model_specs, config, params_snapshot):
    tasks: list[TaskSpec] = []
    for profile in stock_profiles:
        main_window = build_main_window(config, profile.history_days)
        for model in model_specs:
            tasks.append(
                TaskSpec(
                    symbol=profile.symbol,
                    company_name=profile.company_name,
                    segment_key=profile.segment_key,
                    trend_bucket=profile.trend_bucket,
                    volatility_bucket=profile.volatility_bucket,
                    source_kind=profile.source_kind,
                    data_path=profile.data_path,
                    market=config.market,
                    adjust=config.adjust,
                    model=model,
                    window=main_window,
                    params_snapshot=params_snapshot,
                    skip_reason=model.skip_reason_for_market(config.market),
                    execution=config.execution,
                )
            )
    return tasks


def _empty_records_df() -> pd.DataFrame:
    return pd.DataFrame(columns=RUN_RECORD_COLUMNS)


def _task_key(task: TaskSpec) -> tuple[str, str, str]:
    return (
        str(task.symbol),
        str(task.window.window_id),
        str(task.model.model_id),
    )


def _row_key(row: dict[str, Any] | pd.Series) -> tuple[str, str, str]:
    return (
        str(row["symbol"]),
        str(row["window_id"]),
        str(row["model_id"]),
    )


def _filter_pending_tasks(tasks: Iterable[TaskSpec], completed_keys: set[tuple[str, str, str]]) -> list[TaskSpec]:
    return [task for task in tasks if _task_key(task) not in completed_keys]


def _task_keys(tasks: Iterable[TaskSpec]) -> set[tuple[str, str, str]]:
    return {_task_key(task) for task in tasks}


def _records_for_keys(records_df: pd.DataFrame, task_keys: set[tuple[str, str, str]]) -> pd.DataFrame:
    if records_df.empty or not task_keys:
        return _empty_records_df()
    mask = [
        (str(symbol), str(window_id), str(model_id)) in task_keys
        for symbol, window_id, model_id in records_df[["symbol", "window_id", "model_id"]].itertuples(index=False, name=None)
    ]
    return records_df.loc[mask].reset_index(drop=True).copy()


def _parse_params_snapshot(raw_value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return dict(fallback)


def _build_frozen_rolling_model_spec(model: ModelSpec) -> ModelSpec:
    request_payload = dict(model.request_payload or {})
    if request_payload.get("family") != "search":
        return model

    request_payload["use_search"] = False
    return ModelSpec(
        model_id=model.model_id,
        display_name=model.display_name,
        stage=model.stage,
        family_group=model.family_group,
        request_payload=request_payload,
        notes=model.notes,
    )


def _build_main_record_lookup(records_df: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    if records_df.empty:
        return {}
    eligible = records_df[
        (records_df["window_kind"] == "main")
        & (records_df["status"].isin(["success", "degraded"]))
        & (records_df["params_snapshot_json"].notna())
    ].copy()
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in eligible.to_dict("records"):
        lookup[(str(row["symbol"]), str(row["model_id"]))] = row
    return lookup


def _build_rolling_tasks(
    stock_profiles,
    model_specs,
    config,
    fallback_params_snapshot,
    main_record_lookup: dict[tuple[str, str], dict[str, Any]],
):
    tasks: list[TaskSpec] = []
    for profile in stock_profiles:
        rolling_windows = build_rolling_windows(config, profile.history_days)
        for model in model_specs:
            main_row = main_record_lookup.get((profile.symbol, model.model_id))
            if main_row is None:
                continue
            frozen_params_snapshot = _parse_params_snapshot(main_row.get("params_snapshot_json"), fallback_params_snapshot)
            frozen_model = _build_frozen_rolling_model_spec(model)
            for window in rolling_windows:
                tasks.append(
                    TaskSpec(
                        symbol=profile.symbol,
                        company_name=profile.company_name,
                        segment_key=profile.segment_key,
                        trend_bucket=profile.trend_bucket,
                        volatility_bucket=profile.volatility_bucket,
                        source_kind=profile.source_kind,
                        data_path=profile.data_path,
                        market=config.market,
                        adjust=config.adjust,
                        model=frozen_model,
                        window=window,
                        params_snapshot=frozen_params_snapshot,
                        skip_reason=frozen_model.skip_reason_for_market(config.market),
                        execution=config.execution,
                    )
                )
    return tasks


def _load_checkpoint_records(output_dir: Path) -> pd.DataFrame:
    return _load_records_table(output_dir / CHECKPOINT_RUNS_FILENAME)


def _load_records_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty_records_df()
    # A-share symbols such as 000001 must retain leading zeros when a run is
    # resumed from its checkpoint or existing output.
    records_df = pd.read_csv(path, dtype={"symbol": "string"})
    if records_df.empty:
        return _empty_records_df()
    missing_columns = [column for column in RUN_RECORD_COLUMNS if column not in records_df.columns]
    for column in missing_columns:
        records_df[column] = None
    records_df = records_df[RUN_RECORD_COLUMNS]
    records_df = records_df.drop_duplicates(subset=["symbol", "window_id", "model_id"], keep="last").reset_index(drop=True)
    return records_df


def _load_initial_records(output_dir: Path, *, merge_into_existing_output: bool) -> pd.DataFrame:
    checkpoint_df = _load_checkpoint_records(output_dir)
    if not checkpoint_df.empty:
        return checkpoint_df
    if not merge_into_existing_output:
        return checkpoint_df
    return _load_records_table(output_dir / "runs.csv")


def _append_checkpoint_record(checkpoint_runs_path: Path, record: RunRecord) -> None:
    pd.DataFrame([record.to_row()]).to_csv(
        checkpoint_runs_path,
        mode="a",
        header=not checkpoint_runs_path.exists(),
        index=False,
    )


def _write_checkpoint_meta(
    checkpoint_meta_path: Path,
    *,
    config,
    records_df: pd.DataFrame,
    phase: str,
    last_record_key: tuple[str, str, str] | None = None,
) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "config_name": config.name,
        "output_subdir": config.output_subdir,
        "phase": phase,
        "completed_record_count": int(len(records_df)),
        "status_counts": records_df["status"].value_counts(dropna=False).to_dict() if not records_df.empty else {},
        "last_record_key": list(last_record_key) if last_record_key is not None else None,
    }
    checkpoint_meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _checkpoint_callback(
    state: dict[str, Any],
    *,
    config,
    phase: str,
    output_dir: Path,
    control: ResearchControl | None = None,
    planned_records: int = 0,
    phase_task_keys: set[tuple[str, str, str]] | None = None,
):
    checkpoint_runs_path = output_dir / CHECKPOINT_RUNS_FILENAME
    checkpoint_meta_path = output_dir / CHECKPOINT_META_FILENAME

    def _handle(record: RunRecord) -> None:
        record_key = _record_key(record)
        if record_key in state["completed_keys"]:
            return
        record_df = pd.DataFrame([record.to_row()])
        _append_checkpoint_record(checkpoint_runs_path, record)
        if state["records_df"].empty:
            state["records_df"] = record_df
        else:
            state["records_df"] = pd.concat([state["records_df"], record_df], ignore_index=True)
        state["completed_keys"].add(record_key)
        _write_checkpoint_meta(
            checkpoint_meta_path,
            config=config,
            records_df=state["records_df"],
            phase=phase,
            last_record_key=record_key,
        )
        if control is not None:
            phase_completed = (
                sum(key in state["completed_keys"] for key in phase_task_keys)
                if phase_task_keys is not None
                else len(state["records_df"])
            )
            control.checkpoint_record(
                phase=phase,
                completed_records=phase_completed,
                planned_records=planned_records,
                status_counts=state["records_df"]["status"].value_counts(dropna=False).to_dict(),
                last_record_key=record_key,
                run_completed_records=len(state["records_df"]),
            )

    return _handle


def _record_key(record: RunRecord) -> tuple[str, str, str]:
    return (
        str(record.symbol),
        str(record.window_id),
        str(record.model_id),
    )


def _resolve_rolling_specs(config, model_summary_df: pd.DataFrame, final_specs: list[ModelSpec]) -> list[ModelSpec]:
    eligible_specs = [spec for spec in final_specs if spec.model_id != ADAPTIVE_MODEL_ID]
    if config.robustness_weight > 0:
        return list(eligible_specs)
    top_model_ids = set(model_summary_df.head(config.robustness_top_n)["model_id"].tolist())
    return [spec for spec in eligible_specs if spec.model_id in top_model_ids]


def _code_version() -> str:
    """Return a reproducible revision marker without requiring a clean tree."""
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=WORKSPACE_ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=WORKSPACE_ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return f"{revision}-dirty" if dirty else revision
    except Exception:
        return "unknown"


def _ensure_research_runtime(config) -> dict[str, Any]:
    code_version = _code_version()
    if config.require_clean_worktree and (code_version == "unknown" or code_version.endswith("-dirty")):
        raise RuntimeError(
            "Full research config requires a clean git worktree; commit or intentionally stash "
            "all changes before starting the run."
        )
    configure_lightgbm_environment(
        device_type=config.lightgbm_device_type,
        gpu_platform_id=config.lightgbm_gpu_platform_id,
        gpu_device_id=config.lightgbm_gpu_device_id,
        gpu_use_dp=config.lightgbm_gpu_use_dp,
    )
    if config.lightgbm_device_type == "cpu":
        return {"available": True, "device_type": "cpu", "validation": "deferred_to_model_use"}
    validation = validate_lightgbm_device(config.lightgbm_device_type)
    if not validation.get("available"):
        raise RuntimeError(
            f"LightGBM device preflight failed for {config.lightgbm_device_type!r}: "
            f"{validation.get('error', 'unknown error')}"
        )
    return validation


def _freeze_stock_profile_data(stock_profiles, output_dir: Path, *, control: ResearchControl | None = None):
    snapshot_dir = output_dir / "data_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    frozen_profiles = []
    for profile in stock_profiles:
        if control is not None:
            control.raise_if_pause_requested("data_snapshot")
        source = Path(profile.data_path)
        if not source.is_file():
            raise FileNotFoundError(f"Cannot freeze missing research data: {source}")
        destination = snapshot_dir / f"{profile.symbol}_daily.csv"
        if not destination.exists():
            shutil.copy2(source, destination)
        frozen_profiles.append(
            replace(profile, source_kind="frozen_csv", data_path=str(destination.resolve()))
        )
    return frozen_profiles


def load_replay_stock_profiles(config) -> list[StockProfile]:
    """Load an immutable research universe directly from a prior frozen snapshot."""

    if not config.replay_source_subdir:
        raise ValueError("replay_source_subdir is required for frozen replay profiles.")
    source_dir = (WORKSPACE_ROOT / "outputs" / config.replay_source_subdir).resolve()
    stocks_path = source_dir / "stocks.csv"
    manifest_path = source_dir / "data_manifest.json"
    snapshot_dir = source_dir / "data_snapshot"
    if not stocks_path.is_file() or not manifest_path.is_file() or not snapshot_dir.is_dir():
        raise FileNotFoundError(f"Frozen replay source is incomplete: {source_dir}")
    try:
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Frozen replay manifest is unreadable: {manifest_path}") from exc
    if source_manifest.get("market") != config.market:
        raise ValueError(
            f"Frozen replay market is {source_manifest.get('market')!r}, expected {config.market!r}."
        )
    if not (source_manifest.get("data") or {}).get("snapshot_sha256"):
        raise ValueError("Frozen replay source has no data.snapshot_sha256.")
    stocks = pd.read_csv(stocks_path, dtype={"symbol": "string"})
    required = {
        "symbol", "company_name", "history_days", "recent_days", "total_return_1y", "annualized_vol_1y",
        "max_drawdown_1y", "avg_dollar_volume_1y", "trend_bucket", "volatility_bucket", "segment_key",
    }
    missing = sorted(required - set(stocks.columns))
    if missing:
        raise ValueError(f"Frozen replay stocks.csv is missing columns: {missing}")
    profiles: list[StockProfile] = []
    for row in stocks.to_dict("records"):
        symbol = str(row["symbol"]).strip().zfill(6) if config.market == "CN_A" else str(row["symbol"]).strip()
        data_path = snapshot_dir / f"{symbol.lower()}_daily.csv"
        if not data_path.is_file():
            raise FileNotFoundError(f"Frozen replay snapshot is missing {data_path.name}")
        profiles.append(
            StockProfile(
                symbol=symbol,
                company_name=str(row["company_name"]),
                source_kind="frozen_replay",
                data_path=str(data_path.resolve()),
                history_days=int(row["history_days"]),
                recent_days=int(row["recent_days"]),
                total_return_1y=row.get("total_return_1y"),
                annualized_vol_1y=row.get("annualized_vol_1y"),
                max_drawdown_1y=row.get("max_drawdown_1y"),
                avg_dollar_volume_1y=row.get("avg_dollar_volume_1y"),
                trend_bucket=str(row["trend_bucket"]),
                volatility_bucket=str(row["volatility_bucket"]),
                segment_key=str(row["segment_key"]),
            )
        )
    if not profiles:
        raise ValueError("Frozen replay stocks.csv contains no profiles.")
    return profiles


def _data_snapshot_manifest(stocks_df: pd.DataFrame) -> tuple[str | None, list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    for row in stocks_df.to_dict("records"):
        path = Path(str(row.get("data_path") or ""))
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        entries.append(
            {
                "symbol": str(row.get("symbol") or ""),
                "path": str(path.resolve()),
                "sha256": digest.hexdigest(),
                "size_bytes": int(path.stat().st_size),
            }
        )
    if not entries:
        return None, []
    portable_entries = [
        {key: entry[key] for key in ("symbol", "sha256", "size_bytes")}
        for entry in entries
    ]
    aggregate = hashlib.sha256(
        json.dumps(portable_entries, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return aggregate, entries


def _build_data_manifest(config, records_df: pd.DataFrame, stocks_df: pd.DataFrame) -> dict[str, Any]:
    starts = pd.to_datetime(records_df.get("window_start"), errors="coerce")
    ends = pd.to_datetime(records_df.get("window_end"), errors="coerce")
    symbols = [str(symbol) for symbol in stocks_df.get("symbol", pd.Series(dtype="object")).tolist()]
    sources = sorted({str(source) for source in stocks_df.get("source_kind", pd.Series(dtype="object")).dropna()})
    train_end, test_start = _representative_split_dates(records_df, config.train_ratio)
    snapshot_sha256, snapshot_files = _data_snapshot_manifest(stocks_df)
    return {
        "schema_version": "1.0",
        "market": config.market,
        "run_id": f"{config.output_subdir}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "code_version": _code_version(),
        "random_seed": DEFAULT_SEARCH_SEED,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "source": ",".join(sources) or "unavailable",
            "adjustment": config.adjust,
            "start": starts.min().date().isoformat() if starts.notna().any() else None,
            "end": ends.max().date().isoformat() if ends.notna().any() else None,
            "minimum_required_end_date": config.minimum_data_end_date,
            "snapshot_sha256": snapshot_sha256,
        },
        "universe": {
            "symbols": symbols,
            "selection_rationale": (
                "configured smoke symbols"
                if config.smoke_mode
                else f"{config.candidate_selection_mode} catalog candidates -> trend/volatility buckets -> liquidity-ranked pool"
            ),
            "files": snapshot_files,
        },
        "evaluation": {
            "train_end": train_end,
            "test_start": test_start,
            "rolling_windows": [{
                "window_days": config.rolling_window_days,
                "step_days": config.rolling_step_days,
                "count": config.rolling_window_count,
                "enabled": config.run_robustness,
            }],
        },
        "execution": dict(config.execution),
        "search": {"budget": config.search_trials, "seed": DEFAULT_SEARCH_SEED},
        "news": {"available_lag_trading_days": 1, "coverage_threshold": 0.0},
    }


def _representative_split_dates(records_df: pd.DataFrame, train_ratio: float) -> tuple[str | None, str | None]:
    """Read one successful main-window source to make the split reproducible."""
    if records_df.empty:
        return None, None
    eligible = records_df.loc[
        (records_df["window_kind"] == "main")
        & (records_df["status"].isin(["success", "degraded"]))
    ]
    if eligible.empty:
        return None, None
    row = eligible.iloc[0]
    try:
        frame = pd.read_csv(str(row["data_path"]), usecols=["date"])
        dates = pd.to_datetime(frame["date"], errors="coerce").dropna().sort_values().reset_index(drop=True)
        window_start = pd.to_datetime(row["window_start"], errors="coerce")
        window_end = pd.to_datetime(row["window_end"], errors="coerce")
        if pd.notna(window_start) and pd.notna(window_end):
            dates = dates.loc[(dates >= window_start) & (dates <= window_end)].reset_index(drop=True)
        split_idx = max(1, min(int(len(dates) * train_ratio), len(dates) - 1))
        return dates.iloc[split_idx - 1].date().isoformat(), dates.iloc[split_idx].date().isoformat()
    except Exception:
        return None, None


def _valid_source_manifest(manifest: dict[str, Any], market: str) -> bool:
    required = {"schema_version", "run_id", "code_version", "data", "universe", "evaluation", "execution", "search", "news"}
    execution = manifest.get("execution")
    return (
        manifest.get("market") == market
        and required.issubset(manifest)
        and isinstance(execution, dict)
        and all(isinstance(execution.get(key), (int, float)) for key in ("commission_bps", "slippage_bps"))
        and bool(str(manifest.get("run_id") or "").strip())
    )


def _run_cross_market_aggregation(config) -> dict[str, Path]:
    output_dir = WORKSPACE_ROOT / "outputs" / config.output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_frames: list[pd.DataFrame] = []
    source_manifests: dict[str, dict[str, Any]] = {}
    source_limitations: dict[str, list[str]] = {}

    for market in ("US", "CN_A"):
        source_subdir = config.cross_market_source_subdirs[market]
        source_dir = WORKSPACE_ROOT / "outputs" / source_subdir
        manifest_path = source_dir / "data_manifest.json"
        runs_path = source_dir / "runs.csv"
        limitations: list[str] = []
        manifest: dict[str, Any] = {}
        if not manifest_path.is_file():
            limitations.append(f"source manifest is missing: {manifest_path}")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                limitations.append(f"source manifest is unreadable: {manifest_path}")
        if manifest.get("market") != market:
            limitations.append(f"source manifest market is {manifest.get('market')!r}, expected {market!r}")
        if manifest and not _valid_source_manifest(manifest, market):
            limitations.append("source manifest is incomplete or has invalid execution metadata")
        source_manifests[market] = {
            "path": str(manifest_path.relative_to(output_dir.parent)) if manifest_path.exists() else str(manifest_path),
            "run_id": manifest.get("run_id"),
            "code_version": manifest.get("code_version"),
            "data": manifest.get("data"),
            "universe": manifest.get("universe"),
            "evaluation": manifest.get("evaluation"),
            "search": manifest.get("search"),
            "news": manifest.get("news"),
            "commission_bps": manifest.get("execution", {}).get("commission_bps"),
            "slippage_bps": manifest.get("execution", {}).get("slippage_bps"),
        }
        if limitations:
            source_limitations[market] = limitations
            continue
        if not runs_path.is_file():
            limitations.append(f"source runs are missing: {runs_path}")
        else:
            try:
                records_df = _load_records_table(runs_path)
                if records_df.empty:
                    limitations.append("source runs contain no records")
                else:
                    matrix_frames.append(build_market_strategy_matrix(records_df, market))
                    skipped = records_df[records_df["status"].astype(str).str.upper() == "SKIPPED"]
                    for reason in skipped.get("error_message", pd.Series(dtype="object")).dropna().astype(str).unique():
                        limitations.append(f"skipped: {reason}")
            except (OSError, pd.errors.ParserError):
                limitations.append(f"source runs are unreadable: {runs_path}")
        source_limitations[market] = limitations

    matrix_df = (
        pd.concat(
            [frame.dropna(axis=1, how="all") for frame in matrix_frames],
            ignore_index=True,
        ).reindex(columns=MARKET_MATRIX_COLUMNS)
        if matrix_frames
        else pd.DataFrame(columns=MARKET_MATRIX_COLUMNS)
    )
    common_strategy_ids: set[str] = set()
    shared_limitations = {market: list(items) for market, items in source_limitations.items()}
    if not matrix_df.empty:
        supported_main = matrix_df[
            (matrix_df["evaluation_window"] == "main")
            & (pd.to_numeric(matrix_df["coverage_rate"], errors="coerce") > 0)
        ]
        strategy_sets = [
            set(supported_main.loc[supported_main["market"] == market, "strategy_id"].astype(str))
            for market in ("US", "CN_A")
        ]
        common_strategy_ids = set.intersection(*strategy_sets) if all(strategy_sets) else set()
        for market in ("US", "CN_A"):
            market_ids = set(
                supported_main.loc[supported_main["market"] == market, "strategy_id"].astype(str)
            )
            excluded = sorted(market_ids - common_strategy_ids)
            if excluded:
                shared_limitations.setdefault(market, []).append(
                    "market-specific strategies excluded from fair cross-market recommendation: "
                    + ", ".join(excluded)
                )
    recommendations = build_market_strategy_recommendations(
        matrix_df,
        source_limitations=source_limitations,
    )
    shared_recommendations = build_market_strategy_recommendations(
        matrix_df,
        source_limitations=shared_limitations,
        eligible_strategy_ids=common_strategy_ids,
    )
    recommendations["decision_scope"] = "market_specific"
    recommendations["shared_benchmark"] = {
        "decision_scope": "common_candidates_only",
        "eligible_strategy_ids": sorted(common_strategy_ids),
        "markets": shared_recommendations["markets"],
    }
    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{config.output_subdir}-{generated_at}"
    recommendations["generated_at"] = datetime.now(timezone.utc).isoformat()
    comparison_payload = build_market_strategy_payload(
        config=config,
        run_id=run_id,
        matrix_df=matrix_df,
        recommendations=recommendations,
        source_manifests=source_manifests,
    )

    matrix_path = output_dir / "market_strategy_matrix.csv"
    recommendations_path = output_dir / "market_strategy_recommendations.json"
    strategy_report_path = output_dir / "market_strategy_report.md"
    report_json_path = output_dir / "report.json"
    report_md_path = output_dir / "report.md"
    config_snapshot_path = output_dir / "config_snapshot.json"
    data_manifest_path = output_dir / "data_manifest.json"
    matrix_df.to_csv(matrix_path, index=False)
    recommendations_path.write_text(json.dumps(recommendations, ensure_ascii=False, indent=2), encoding="utf-8")
    strategy_report_path.write_text(render_market_strategy_markdown(comparison_payload), encoding="utf-8")
    report_json_path.write_text(json.dumps(comparison_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report_md_path.write_text(render_market_strategy_markdown(comparison_payload), encoding="utf-8")
    config_snapshot_path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    data_manifest = {
        "schema_version": "1.0",
        "market": config.market,
        "run_id": run_id,
        "code_version": _code_version(),
        "random_seed": DEFAULT_SEARCH_SEED,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {"source": "aggregated completed market runs", "adjustment": None, "start": None, "end": None},
        "universe": {"symbols": [], "selection_rationale": "cross-market aggregation of source run universes"},
        "evaluation": {"train_end": None, "test_start": None, "rolling_windows": []},
        "execution": {
            "commission_bps": float(source_manifests.get("US", {}).get("commission_bps", 0.0) or 0.0),
            "slippage_bps": float(source_manifests.get("US", {}).get("slippage_bps", 0.0) or 0.0),
        },
        "search": {"budget": None},
        "news": {"available_lag_trading_days": 1, "coverage_threshold": 0.0},
        "compute": dict(config.compute),
        "aggregation_scope": {
            "markets": ["US", "CN_A"],
            "common_strategy_ids": sorted(common_strategy_ids),
        },
        "sources": source_manifests,
    }
    data_manifest_path.write_text(json.dumps(data_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "market_strategy_matrix": matrix_path,
        "market_strategy_recommendations": recommendations_path,
        "market_strategy_report": strategy_report_path,
        "report_json": report_json_path,
        "report_md": report_md_path,
        "config_snapshot": config_snapshot_path,
        "data_manifest": data_manifest_path,
    }


def _execute_phase_tasks(
    tasks: list[TaskSpec],
    *,
    config,
    phase: str,
    output_dir: Path,
    artifacts_root: Path,
    state: dict[str, Any],
    control: ResearchControl,
) -> None:
    pending = _filter_pending_tasks(tasks, state["completed_keys"])
    phase_task_keys = _task_keys(tasks)
    control.set_phase(
        phase,
        config_name=config.name,
        planned_records=len(tasks),
        completed_records=len(tasks) - len(pending),
        in_flight_batches=0,
    )
    control.raise_if_pause_requested(phase)
    if not pending:
        return
    try:
        execute_tasks(
            pending,
            config.parallelism,
            on_record=_checkpoint_callback(
                state,
                config=config,
                phase=phase,
                output_dir=output_dir,
                control=control,
                planned_records=len(tasks),
                phase_task_keys=phase_task_keys,
            ),
            artifacts_root=artifacts_root,
            should_pause=control.pause_requested,
            on_queue_change=lambda in_flight, pending_batches: control.update_queue(
                in_flight_batches=in_flight,
                pending_batches=pending_batches,
            ),
        )
    except ExecutionPaused as exc:
        control.update(phase=phase, pause_requested=True, in_flight_batches=0)
        raise ResearchPauseRequested(str(exc)) from exc


def run_research(
    config_path: str | Path,
    *,
    control_dir: str | Path | None = None,
) -> dict[str, Path]:
    config = load_research_config(config_path)
    control = ResearchControl(control_dir)
    control.update(
        config_name=config.name,
        phase="runtime_preflight",
        pause_requested=False,
        planned_records=0,
        completed_records=0,
        run_completed_records=0,
        in_flight_batches=0,
        pending_batches=0,
        status_counts={},
        last_record_key=None,
    )
    control.raise_if_pause_requested("runtime_preflight")
    if config.is_cross_market_aggregation:
        control.set_phase(
            "cross_market_aggregation",
            config_name=config.name,
            planned_records=0,
            completed_records=0,
            in_flight_batches=0,
            pending_batches=0,
        )
        outputs = _run_cross_market_aggregation(config)
        control.set_phase("completed", config_name=config.name, in_flight_batches=0)
        return outputs
    _ensure_research_runtime(config)
    output_dir = WORKSPACE_ROOT / "outputs" / config.output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_optional_dependencies(config)
    artifacts_root = output_dir / "artifacts"

    checkpoint_df = _load_initial_records(output_dir, merge_into_existing_output=config.merge_into_existing_output)
    state = {
        "records_df": checkpoint_df,
        "completed_keys": {_row_key(row) for row in checkpoint_df.to_dict("records")},
    }
    _write_checkpoint_meta(
        output_dir / CHECKPOINT_META_FILENAME,
        config=config,
        records_df=state["records_df"],
        phase="resume_loaded",
    )

    control.set_phase(
        "data_preparation",
        config_name=config.name,
        completed_records=len(state["records_df"]),
        in_flight_batches=0,
    )
    control.raise_if_pause_requested("data_preparation")
    params_snapshot = build_request_params_snapshot(config)
    stock_profiles = (
        load_replay_stock_profiles(config)
        if config.replay_source_subdir
        else build_stock_profiles(config)
    )
    control.raise_if_pause_requested("data_preparation")
    if config.freeze_data_snapshot:
        stock_profiles = _freeze_stock_profile_data(stock_profiles, output_dir, control=control)
    stocks_df = profiles_to_dataframe(stock_profiles)

    stage_a_specs = build_stage_a_model_specs(config)
    adaptive_stage_a_specs = [spec for spec in stage_a_specs if spec.model_id == ADAPTIVE_MODEL_ID]
    supported_adaptive_stage_a_specs = [
        spec for spec in adaptive_stage_a_specs if spec.skip_reason_for_market(config.market) is None
    ]
    standard_stage_a_specs = [spec for spec in stage_a_specs if spec.model_id != ADAPTIVE_MODEL_ID]

    stage_a_tasks = _build_main_tasks(stock_profiles, standard_stage_a_specs, config, params_snapshot)
    _execute_phase_tasks(
        stage_a_tasks,
        config=config,
        phase="stage_a_main",
        output_dir=output_dir,
        artifacts_root=artifacts_root,
        state=state,
        control=control,
    )

    stage_a_keys = _task_keys(stage_a_tasks)
    stage_a_df = _records_for_keys(state["records_df"], stage_a_keys)
    stage_a_summary_df, _ = build_model_summary(stage_a_df, config.score_weights)

    stage_winners: dict[str, str] = {}
    adaptive_artifact_paths: dict[str, Path] = {}
    adaptive_router_summary: dict[str, Any] = {}
    if adaptive_stage_a_specs:
        if supported_adaptive_stage_a_specs:
            control.set_phase("adaptive_training", config_name=config.name, in_flight_batches=0)
            control.raise_if_pause_requested("adaptive_training")
            try:
                stage_winners = pick_stage_b_winners(stage_a_summary_df)
                adaptive_result = train_adaptive_router_artifacts(
                    config=config,
                    output_dir=output_dir,
                    stock_profiles=stock_profiles,
                    params_snapshot=params_snapshot,
                    search_winners=stage_winners,
                )
                adaptive_artifact_paths = adaptive_result["artifact_paths"]
                adaptive_router_summary = adaptive_result["routing_policy_summary"]
                os.environ[ADAPTIVE_ARTIFACT_ENV_VAR] = str(adaptive_artifact_paths["artifact_dir"])
            except Exception as exc:
                print(f"[adaptive-router] artifact training failed: {exc}")

        adaptive_stage_a_tasks = _build_main_tasks(stock_profiles, adaptive_stage_a_specs, config, params_snapshot)
        _execute_phase_tasks(
            adaptive_stage_a_tasks,
            config=config,
            phase="stage_a_adaptive_main",
            output_dir=output_dir,
            artifacts_root=artifacts_root,
            state=state,
            control=control,
        )
    else:
        adaptive_stage_a_tasks = []

    stage_b_specs: list[ModelSpec] = []
    if config.run_stage_b:
        stage_winners = pick_stage_b_winners(stage_a_summary_df)
        stage_b_specs = build_stage_b_model_specs(config, stage_winners)
        stage_b_tasks = _build_main_tasks(stock_profiles, stage_b_specs, config, params_snapshot)
        _execute_phase_tasks(
            stage_b_tasks,
            config=config,
            phase="stage_b_main",
            output_dir=output_dir,
            artifacts_root=artifacts_root,
            state=state,
            control=control,
        )
    else:
        stage_b_tasks = []

    main_task_keys = stage_a_keys | _task_keys(adaptive_stage_a_tasks) | _task_keys(stage_b_tasks)
    records_df = (
        state["records_df"].reset_index(drop=True).copy()
        if config.merge_into_existing_output
        else _records_for_keys(state["records_df"], main_task_keys)
    )
    robustness_df = build_robustness_summary(records_df)
    model_summary_df, _aggregates = build_model_summary(
        records_df,
        config.score_weights,
        robustness_df=robustness_df,
        robustness_weight=config.robustness_weight,
    )
    segment_summary_df = build_segment_summary(records_df, config.score_weights)

    if config.run_robustness and not model_summary_df.empty:
        final_specs = [*stage_a_specs, *stage_b_specs]
        rolling_specs = _resolve_rolling_specs(config, model_summary_df, final_specs)
        main_record_lookup = _build_main_record_lookup(records_df)
        rolling_tasks = _build_rolling_tasks(
            stock_profiles,
            rolling_specs,
            config,
            params_snapshot,
            main_record_lookup,
        )
        pending_rolling = _filter_pending_tasks(rolling_tasks, state["completed_keys"])
        if pending_rolling:
            _execute_phase_tasks(
                rolling_tasks,
                config=config,
                phase="rolling_robustness",
                output_dir=output_dir,
                artifacts_root=artifacts_root,
                state=state,
                control=control,
            )
        all_task_keys = main_task_keys | _task_keys(rolling_tasks)
        records_df = (
            state["records_df"].reset_index(drop=True).copy()
            if config.merge_into_existing_output
            else _records_for_keys(state["records_df"], all_task_keys)
        )
        robustness_df = build_robustness_summary(records_df)
        model_summary_df, _aggregates = build_model_summary(
            records_df,
            config.score_weights,
            robustness_df=robustness_df,
            robustness_weight=config.robustness_weight,
        )
        segment_summary_df = build_segment_summary(records_df, config.score_weights)

    control.set_phase("reporting", config_name=config.name, in_flight_batches=0)
    control.raise_if_pause_requested("reporting")
    model_summary_df, quantstats_entries, quantstats_dir = generate_quantstats_outputs(
        config=config,
        output_dir=output_dir,
        model_summary_df=model_summary_df,
        records_df=records_df,
    )

    payload = build_report_payload(
        config=config,
        stocks_df=stocks_df,
        model_summary_df=model_summary_df,
        segment_summary_df=segment_summary_df,
        robustness_df=robustness_df,
        records_df=records_df,
        stage_winners=stage_winners,
        quantstats_entries=quantstats_entries,
        adaptive_router_summary=adaptive_router_summary,
    )
    report_md = render_report_markdown(payload)

    runs_path = output_dir / "runs.csv"
    stocks_path = output_dir / "stocks.csv"
    model_summary_path = output_dir / "model_summary.csv"
    segment_summary_path = output_dir / "segment_summary.csv"
    robustness_summary_path = output_dir / "robustness_summary.csv"
    report_json_path = output_dir / "report.json"
    report_md_path = output_dir / "report.md"
    config_snapshot_path = output_dir / "config_snapshot.json"
    data_manifest_path = output_dir / "data_manifest.json"

    records_df.to_csv(runs_path, index=False)
    stocks_df.to_csv(stocks_path, index=False)
    model_summary_df.to_csv(model_summary_path, index=False)
    segment_summary_df.to_csv(segment_summary_path, index=False)
    robustness_df.to_csv(robustness_summary_path, index=False)
    report_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report_md_path.write_text(report_md, encoding="utf-8")
    config_snapshot_path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    data_manifest_path.write_text(
        json.dumps(_build_data_manifest(config, records_df, stocks_df), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    output_paths = {
        "runs": runs_path,
        "stocks": stocks_path,
        "model_summary": model_summary_path,
        "segment_summary": segment_summary_path,
        "robustness_summary": robustness_summary_path,
        "report_json": report_json_path,
        "report_md": report_md_path,
        "config_snapshot": config_snapshot_path,
        "data_manifest": data_manifest_path,
    }
    if adaptive_artifact_paths:
        output_paths["regime_artifacts"] = adaptive_artifact_paths["artifact_dir"]
    if quantstats_dir.exists() and any(quantstats_dir.iterdir()):
        output_paths["quantstats"] = quantstats_dir
    if config.enable_mlflow:
        output_paths["mlflow_run"] = log_research_run_to_mlflow(
            config=config,
            output_dir=output_dir,
            records_df=records_df,
            model_summary_df=model_summary_df,
            artifacts=output_paths,
            quantstats_dir=quantstats_dir,
        )

    _write_checkpoint_meta(
        output_dir / CHECKPOINT_META_FILENAME,
        config=config,
        records_df=state["records_df"],
        phase="completed",
    )
    control.set_phase(
        "completed",
        config_name=config.name,
        completed_records=len(state["records_df"]),
        in_flight_batches=0,
        pending_batches=0,
    )

    return output_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline single-stock research framework.")
    parser.add_argument("--config", required=True, help="Path to the research config JSON file.")
    parser.add_argument("--control-dir", help="Optional campaign control directory for progress and safe pause.")
    args = parser.parse_args(argv)

    try:
        outputs = run_research(args.config, control_dir=args.control_dir)
    except ResearchPauseRequested as exc:
        print(f"[paused] {exc}")
        return PAUSED_EXIT_CODE
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0
