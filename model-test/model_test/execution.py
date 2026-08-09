from __future__ import annotations

import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from core.data import ensure_date_column, standardize_columns
from core.evaluation import compute_performance_metrics
from core.market_rules import MarketExecutionConfig, using_execution_config
from ui.single_stock_workflow import build_strategy_context_key, run_strategy_pipeline

from model_test.config import build_search_budget_summary
from model_test.models import RunRecord, TaskSpec, json_text
from model_test.observability import export_run_artifact_bundle


_FRAME_CACHE: dict[str, pd.DataFrame] = {}


class ExecutionPaused(RuntimeError):
    """All submitted batches finished, and no additional batch was started."""


def _clear_streamlit_state() -> None:
    import streamlit as st

    try:
        st.session_state.clear()
    except Exception:
        pass


def _load_task_frame(data_path: str) -> pd.DataFrame:
    cache_key = str(data_path)
    cached = _FRAME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    frame = pd.read_csv(cache_key)
    frame = ensure_date_column(standardize_columns(frame))
    _FRAME_CACHE[cache_key] = frame
    return frame


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _extract_window_dates(df_window: pd.DataFrame) -> tuple[str | None, str | None]:
    if "date" not in df_window.columns or df_window.empty:
        return None, None
    dates = pd.to_datetime(df_window["date"], errors="coerce").dropna()
    if dates.empty:
        return None, None
    return dates.iloc[0].date().isoformat(), dates.iloc[-1].date().isoformat()


def _build_train_metrics(sim_df: pd.DataFrame) -> dict[str, float | None]:
    if sim_df is None or sim_df.empty:
        return {
            "train_cumret": None,
            "train_annret": None,
            "train_maxdd": None,
            "train_sharpe": None,
        }
    equity = pd.Series(pd.to_numeric(sim_df["strategy_equity"], errors="coerce").to_numpy())
    benchmark = pd.Series(pd.to_numeric(sim_df["buy_hold_equity"], errors="coerce").to_numpy())
    metrics = compute_performance_metrics(equity, benchmark)
    return {
        "train_cumret": _safe_float(metrics.get("cumret")),
        "train_annret": _safe_float(metrics.get("annret")),
        "train_maxdd": _safe_float(metrics.get("maxdd")),
        "train_sharpe": _safe_float(metrics.get("sharpe")),
    }


def _build_execution_metrics(sim_df: pd.DataFrame | None) -> dict[str, float | None]:
    """Aggregate the frozen execution-cost fields from a test simulation."""
    empty = {
        "total_turnover": None,
        "total_transaction_cost": None,
        "gross_total_return": None,
        "net_total_return": None,
    }
    if sim_df is None or sim_df.empty:
        return empty

    def _sum_column(column: str) -> float | None:
        if column not in sim_df.columns:
            return None
        values = pd.to_numeric(sim_df[column], errors="coerce").dropna()
        return float(values.sum()) if not values.empty else None

    def _compound_column(column: str) -> float | None:
        if column not in sim_df.columns:
            return None
        values = pd.to_numeric(sim_df[column], errors="coerce").dropna()
        return float((1.0 + values).prod() - 1.0) if not values.empty else None

    return {
        "total_turnover": _sum_column("turnover"),
        "total_transaction_cost": _sum_column("transaction_cost"),
        "gross_total_return": _compound_column("gross_strategy_return"),
        "net_total_return": _compound_column("strategy_return"),
    }


def _skipped_record(task: TaskSpec, reason: str | None = None) -> RunRecord:
    return RunRecord(
        symbol=task.symbol,
        company_name=task.company_name,
        segment_key=task.segment_key,
        trend_bucket=task.trend_bucket,
        volatility_bucket=task.volatility_bucket,
        source_kind=task.source_kind,
        data_path=task.data_path,
        window_id=task.window.window_id,
        window_kind=task.window.kind,
        window_start=None,
        window_end=None,
        window_days=None,
        stage=task.model.stage,
        model_id=task.model.model_id,
        display_name=task.model.display_name,
        family_group=task.model.family_group,
        status="SKIPPED",
        error_message=reason or task.skip_reason or task.window.reason,
        params_snapshot_json=json_text(task.params_snapshot),
    )


def _build_failed_record(
    task: TaskSpec,
    *,
    window_start: str | None,
    window_end: str | None,
    window_days: int,
    error_message: str,
) -> RunRecord:
    return RunRecord(
        symbol=task.symbol,
        company_name=task.company_name,
        segment_key=task.segment_key,
        trend_bucket=task.trend_bucket,
        volatility_bucket=task.volatility_bucket,
        source_kind=task.source_kind,
        data_path=task.data_path,
        window_id=task.window.window_id,
        window_kind=task.window.kind,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        stage=task.model.stage,
        model_id=task.model.model_id,
        display_name=task.model.display_name,
        family_group=task.model.family_group,
        status="failed",
        error_message=error_message,
        params_snapshot_json=json_text(task.params_snapshot),
    )


def _record_from_result(
    task: TaskSpec,
    *,
    window_start: str | None,
    window_end: str | None,
    window_days: int,
    result,
    artifacts_root: str | None = None,
) -> RunRecord:
    record = RunRecord(
        symbol=task.symbol,
        company_name=task.company_name,
        segment_key=task.segment_key,
        trend_bucket=task.trend_bucket,
        volatility_bucket=task.volatility_bucket,
        source_kind=task.source_kind,
        data_path=task.data_path,
        window_id=task.window.window_id,
        window_kind=task.window.kind,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        stage=task.model.stage,
        model_id=task.model.model_id,
        display_name=task.model.display_name,
        family_group=task.model.family_group,
        status=result.status,
        error_message=result.error_message,
        warning_count=len(result.warnings),
        warnings_json=json_text(result.warnings),
        info_messages_json=json_text(result.info_messages),
        params_snapshot_json=json_text(task.params_snapshot),
    )

    if result.artifact is None:
        return record

    final_stage = result.artifact.pipeline_lineage[-1]
    record.lineage_json = json_text(
        [
            {
                "stage_key": stage.stage_key,
                "display_label": stage.display_label,
                "short_label": stage.short_label,
            }
            for stage in result.artifact.pipeline_lineage
        ]
    )
    metadata = dict(final_stage.metadata or {})
    search_metadata = _build_search_metadata(task)
    if search_metadata:
        metadata["search_budget"] = search_metadata
    record.metadata_json = json_text(metadata)
    record.params_snapshot_json = json_text(result.artifact.params_snapshot)
    record.ml_quality_json = json_text(result.artifact.ml_quality or {})

    train_metrics = _build_train_metrics(final_stage.train_sim_df)
    record.train_cumret = train_metrics["train_cumret"]
    record.train_annret = train_metrics["train_annret"]
    record.train_maxdd = train_metrics["train_maxdd"]
    record.train_sharpe = train_metrics["train_sharpe"]

    eval_result = result.artifact.eval or {}
    record.test_cumret = _safe_float(eval_result.get("cumret"))
    record.test_annret = _safe_float(eval_result.get("annret"))
    record.test_maxdd = _safe_float(eval_result.get("maxdd"))
    record.test_sharpe = _safe_float(eval_result.get("sharpe"))
    record.test_winrate = _safe_float(eval_result.get("winrate"))
    record.test_pnl_ratio = _safe_float(eval_result.get("pnl_ratio"))
    record.test_turnover = _safe_float(eval_result.get("turnover"))
    record.test_excess_return = _safe_float(eval_result.get("excess_return"))
    execution_metrics = _build_execution_metrics(result.artifact.test_sim_df)
    record.total_turnover = _safe_float(eval_result.get("total_turnover"))
    if record.total_turnover is None:
        record.total_turnover = execution_metrics["total_turnover"]
    record.total_transaction_cost = _safe_float(eval_result.get("total_transaction_cost"))
    if record.total_transaction_cost is None:
        record.total_transaction_cost = execution_metrics["total_transaction_cost"]
    record.gross_total_return = _safe_float(eval_result.get("gross_total_return"))
    if record.gross_total_return is None:
        record.gross_total_return = execution_metrics["gross_total_return"]
    record.net_total_return = _safe_float(eval_result.get("net_total_return"))
    if record.net_total_return is None:
        record.net_total_return = execution_metrics["net_total_return"]
    if record.net_total_return is None:
        record.net_total_return = record.test_cumret

    ml_quality = result.artifact.ml_quality or {}
    record.ml_precision = _safe_float(ml_quality.get("precision"))
    record.ml_recall = _safe_float(ml_quality.get("recall"))
    record.ml_f1 = _safe_float(ml_quality.get("f1"))
    record.ml_pr_auc = _safe_float(ml_quality.get("pr_auc"))
    record.ml_signal_pass_rate = _safe_float(ml_quality.get("signal_pass_rate"))

    if record.train_annret is not None and record.test_annret is not None:
        record.train_test_gap = max(record.train_annret - record.test_annret, 0.0)
    export_run_artifact_bundle(
        task=task,
        result=result,
        record=record,
        artifacts_root=artifacts_root,
    )
    return record


def _build_search_metadata(task: TaskSpec) -> dict[str, object] | None:
    payload = dict(task.model.request_payload or {})
    search_method = payload.get("search_method")
    if not search_method:
        return None
    budget = build_search_budget_summary(
        search_trials=int(payload.get("search_trials", 0) or 0),
        ga_population_size=int(payload.get("ga_population_size", 0) or 0),
        ga_generations=int(payload.get("ga_generations", 0) or 0),
    )
    budget.update(
        {
            "search_method": str(search_method),
            "use_search": bool(payload.get("use_search", False)),
            "reused_main_window_params": not bool(payload.get("use_search", False)),
        }
    )
    return budget


def _nested_worker_limit(outer_workers: int) -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, min(4, cpu_count // max(1, outer_workers)))


def _init_execution_worker(nested_workers: int) -> None:
    nested = max(1, int(nested_workers))
    os.environ["STRATAGY_OPTIMIZER_MAX_WORKERS"] = str(nested)
    os.environ["STRATAGY_ML_MAX_WORKERS"] = str(nested)


def _task_batch_key(task: TaskSpec) -> tuple[object, ...]:
    return (
        task.data_path,
        task.market,
        task.adjust,
        task.symbol,
        task.window.window_id,
        task.window.kind,
        task.window.start_idx,
        task.window.end_idx,
        round(float(task.window.train_ratio), 6),
    )


def _group_task_batches(task_list: list[TaskSpec]) -> list[list[TaskSpec]]:
    batches: dict[tuple[object, ...], list[TaskSpec]] = {}
    order: list[tuple[object, ...]] = []
    for task in task_list:
        key = _task_batch_key(task)
        if key not in batches:
            batches[key] = []
            order.append(key)
        batches[key].append(task)
    return [batches[key] for key in order]


def run_task_batch(task_batch: list[TaskSpec], artifacts_root: str | None = None) -> list[RunRecord]:
    if not task_batch:
        return []

    unsupported_records = [
        _skipped_record(task, task.skip_reason)
        for task in task_batch
        if task.skip_reason
    ]
    runnable_tasks = [task for task in task_batch if not task.skip_reason]
    if not runnable_tasks:
        return unsupported_records

    lead_task = runnable_tasks[0]
    _clear_streamlit_state()
    if not lead_task.window.available:
        return [*unsupported_records, *[_skipped_record(task) for task in runnable_tasks]]

    df_full = _load_task_frame(lead_task.data_path)
    df_window = df_full.iloc[lead_task.window.start_idx : lead_task.window.end_idx].copy()
    window_start, window_end = _extract_window_dates(df_window)

    if df_window.empty:
        return [
            _build_failed_record(
                task,
                window_start=window_start,
                window_end=window_end,
                window_days=0,
                error_message="window slice is empty",
            )
            for task in runnable_tasks
        ]

    split_idx = int(len(df_window) * lead_task.window.train_ratio)
    split_idx = max(1, min(split_idx, len(df_window) - 1))
    context_key = build_strategy_context_key(
        market=lead_task.market,
        symbol=lead_task.symbol,
        adjust=lead_task.adjust,
        df_raw=df_window,
        train_ratio=lead_task.window.train_ratio,
    )

    records: list[RunRecord] = list(unsupported_records)
    for task in runnable_tasks:
        execution_config = MarketExecutionConfig(**task.execution) if task.execution else None
        with using_execution_config(execution_config):
            result = run_strategy_pipeline(
                context_key=context_key,
                request=task.model.build_request(),
                request_params_snapshot=task.params_snapshot,
                df_raw=df_window,
                split_idx=split_idx,
            )
        records.append(
            _record_from_result(
                task,
                window_start=window_start,
                window_end=window_end,
                window_days=int(len(df_window)),
                result=result,
                artifacts_root=artifacts_root,
            )
        )
    return records


def execute_tasks(
    tasks: Iterable[TaskSpec],
    max_workers: int,
    *,
    on_record: Callable[[RunRecord], None] | None = None,
    artifacts_root: str | Path | None = None,
    should_pause: Callable[[], bool] | None = None,
    on_queue_change: Callable[[int, int], None] | None = None,
) -> list[RunRecord]:
    task_list = list(tasks)
    if not task_list:
        return []

    task_batches = _group_task_batches(task_list)
    batch_count = len(task_batches)
    requested_workers = max(1, int(max_workers))
    outer_workers = min(requested_workers, batch_count)
    nested_workers = _nested_worker_limit(outer_workers)
    artifacts_root_value = str(artifacts_root) if artifacts_root is not None else None

    results: list[RunRecord] = []
    completed_records = 0
    total_records = len(task_list)

    if outer_workers == 1:
        _init_execution_worker(nested_workers)
        for batch_index, batch in enumerate(task_batches):
            if should_pause is not None and should_pause():
                if on_queue_change is not None:
                    on_queue_change(0, batch_count - batch_index)
                raise ExecutionPaused("Pause requested before the next serial task batch.")
            if on_queue_change is not None:
                on_queue_change(1, batch_count - batch_index - 1)
            for record in run_task_batch(batch, artifacts_root_value):
                completed_records += 1
                results.append(record)
                if on_record is not None:
                    on_record(record)
                print(
                    f"[{completed_records}/{total_records}] "
                    f"{record.model_id} {record.symbol} {record.window_id} -> {record.status}"
                )
            if on_queue_change is not None:
                on_queue_change(0, batch_count - batch_index - 1)
            if should_pause is not None and should_pause():
                raise ExecutionPaused("Pause requested after a serial task batch.")
        return results

    executor_kwargs = {
        "max_workers": outer_workers,
        "initializer": _init_execution_worker,
        "initargs": (nested_workers,),
    }
    with ProcessPoolExecutor(**executor_kwargs) as executor:
        batch_iterator = iter(task_batches)
        future_to_batch: dict[Any, list[TaskSpec]] = {}
        submitted_batches = 0
        pause_seen = bool(should_pause is not None and should_pause())

        def _submit_until_full() -> None:
            nonlocal submitted_batches
            if pause_seen:
                return
            while len(future_to_batch) < outer_workers:
                try:
                    batch = next(batch_iterator)
                except StopIteration:
                    break
                future = executor.submit(run_task_batch, batch, artifacts_root_value)
                future_to_batch[future] = batch
                submitted_batches += 1

        _submit_until_full()
        if on_queue_change is not None:
            on_queue_change(len(future_to_batch), batch_count - submitted_batches)

        while future_to_batch:
            done, _not_done = wait(tuple(future_to_batch), return_when=FIRST_COMPLETED)
            for future in done:
                future_to_batch.pop(future, None)
                batch_records = future.result()
                for record in batch_records:
                    completed_records += 1
                    results.append(record)
                    if on_record is not None:
                        on_record(record)
                    print(
                        f"[{completed_records}/{total_records}] "
                        f"{record.model_id} {record.symbol} {record.window_id} -> {record.status}"
                    )

            if should_pause is not None and should_pause():
                pause_seen = True
            _submit_until_full()
            if on_queue_change is not None:
                on_queue_change(len(future_to_batch), batch_count - submitted_batches)

        if pause_seen:
            raise ExecutionPaused("Pause requested after all in-flight task batches checkpointed.")
    return results
