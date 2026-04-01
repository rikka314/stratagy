from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from core.adaptive_regime import ADAPTIVE_ARTIFACT_ENV_VAR, ADAPTIVE_MODEL_ID
from model_test import WORKSPACE_ROOT
from model_test.adaptive_router import train_adaptive_router_artifacts
from model_test.config import (
    build_main_window,
    build_request_params_snapshot,
    build_rolling_windows,
    build_stage_a_model_specs,
    build_stage_b_model_specs,
    load_research_config,
)
from model_test.execution import execute_tasks
from model_test.models import ModelSpec, RunRecord, TaskSpec
from model_test.observability import (
    ensure_optional_dependencies,
    generate_quantstats_outputs,
    log_research_run_to_mlflow,
)
from model_test.reporting import build_report_payload, render_report_markdown
from model_test.summarize import (
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
                    )
                )
    return tasks


def _load_checkpoint_records(output_dir: Path) -> pd.DataFrame:
    return _load_records_table(output_dir / CHECKPOINT_RUNS_FILENAME)


def _load_records_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty_records_df()
    records_df = pd.read_csv(path)
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


def _checkpoint_callback(state: dict[str, Any], *, config, phase: str, output_dir: Path):
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


def run_research(config_path: str | Path) -> dict[str, Path]:
    config = load_research_config(config_path)
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

    params_snapshot = build_request_params_snapshot(config)
    stock_profiles = build_stock_profiles(config)
    stocks_df = profiles_to_dataframe(stock_profiles)

    stage_a_specs = build_stage_a_model_specs(config)
    adaptive_stage_a_specs = [spec for spec in stage_a_specs if spec.model_id == ADAPTIVE_MODEL_ID]
    standard_stage_a_specs = [spec for spec in stage_a_specs if spec.model_id != ADAPTIVE_MODEL_ID]

    stage_a_tasks = _build_main_tasks(stock_profiles, standard_stage_a_specs, config, params_snapshot)
    pending_stage_a = _filter_pending_tasks(stage_a_tasks, state["completed_keys"])
    if pending_stage_a:
        execute_tasks(
            pending_stage_a,
            config.parallelism,
            on_record=_checkpoint_callback(state, config=config, phase="stage_a_main", output_dir=output_dir),
            artifacts_root=artifacts_root,
        )

    stage_a_keys = _task_keys(stage_a_tasks)
    stage_a_df = _records_for_keys(state["records_df"], stage_a_keys)
    stage_a_summary_df, _ = build_model_summary(stage_a_df, config.score_weights)

    stage_winners: dict[str, str] = {}
    adaptive_artifact_paths: dict[str, Path] = {}
    adaptive_router_summary: dict[str, Any] = {}
    if adaptive_stage_a_specs:
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
        pending_adaptive_stage_a = _filter_pending_tasks(adaptive_stage_a_tasks, state["completed_keys"])
        if pending_adaptive_stage_a:
            execute_tasks(
                pending_adaptive_stage_a,
                config.parallelism,
                on_record=_checkpoint_callback(state, config=config, phase="stage_a_adaptive_main", output_dir=output_dir),
                artifacts_root=artifacts_root,
            )
    else:
        adaptive_stage_a_tasks = []

    stage_b_specs: list[ModelSpec] = []
    if config.run_stage_b:
        stage_winners = pick_stage_b_winners(stage_a_summary_df)
        stage_b_specs = build_stage_b_model_specs(config, stage_winners)
        stage_b_tasks = _build_main_tasks(stock_profiles, stage_b_specs, config, params_snapshot)
        pending_stage_b = _filter_pending_tasks(stage_b_tasks, state["completed_keys"])
        if pending_stage_b:
            execute_tasks(
                pending_stage_b,
                config.parallelism,
                on_record=_checkpoint_callback(state, config=config, phase="stage_b_main", output_dir=output_dir),
                artifacts_root=artifacts_root,
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
            execute_tasks(
                pending_rolling,
                config.parallelism,
                on_record=_checkpoint_callback(state, config=config, phase="rolling_robustness", output_dir=output_dir),
                artifacts_root=artifacts_root,
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

    records_df.to_csv(runs_path, index=False)
    stocks_df.to_csv(stocks_path, index=False)
    model_summary_df.to_csv(model_summary_path, index=False)
    segment_summary_df.to_csv(segment_summary_path, index=False)
    robustness_df.to_csv(robustness_summary_path, index=False)
    report_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report_md_path.write_text(report_md, encoding="utf-8")

    output_paths = {
        "runs": runs_path,
        "stocks": stocks_path,
        "model_summary": model_summary_path,
        "segment_summary": segment_summary_path,
        "robustness_summary": robustness_summary_path,
        "report_json": report_json_path,
        "report_md": report_md_path,
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

    return output_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline single-stock research framework.")
    parser.add_argument("--config", required=True, help="Path to the research config JSON file.")
    args = parser.parse_args(argv)

    outputs = run_research(args.config)
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0
