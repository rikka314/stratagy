from __future__ import annotations

import importlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from model_test import WORKSPACE_ROOT
from model_test.models import ResearchConfig, RunRecord, TaskSpec


_RUN_EXPORT_STATUSES = {"success", "degraded"}


def _optional_dependency_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _import_optional_dependency(module_name: str):
    return importlib.import_module(module_name)


def ensure_optional_dependencies(config: ResearchConfig) -> None:
    missing: list[str] = []
    if config.enable_mlflow and not _optional_dependency_available("mlflow"):
        missing.append("mlflow")
    if config.enable_quantstats and not _optional_dependency_available("quantstats"):
        missing.append("quantstats")
    if missing:
        raise RuntimeError(
            "Missing optional dependencies required by the selected research config: "
            + ", ".join(sorted(missing))
        )


def _date_strings(index_like: Any) -> list[str]:
    index = pd.Index(index_like)
    parsed = pd.to_datetime(index, errors="coerce")
    values: list[str] = []
    for raw_value, parsed_value in zip(index, parsed, strict=False):
        if pd.isna(parsed_value):
            values.append(str(raw_value))
        else:
            values.append(parsed_value.date().isoformat())
    return values


def _series_frame(series: pd.Series, value_column: str, *, fillna: float | None = None) -> pd.DataFrame:
    values = pd.to_numeric(series, errors="coerce")
    if fillna is not None:
        values = values.fillna(fillna)
    return pd.DataFrame(
        {
            "date": _date_strings(series.index),
            value_column: values.to_numpy(),
        }
    )


def _benchmark_returns_frame(test_sim_df: pd.DataFrame) -> pd.DataFrame:
    benchmark_equity = pd.to_numeric(test_sim_df["buy_hold_equity"], errors="coerce")
    benchmark_returns = benchmark_equity.pct_change().fillna(0.0)
    return pd.DataFrame(
        {
            "date": _date_strings(test_sim_df["date"] if "date" in test_sim_df.columns else test_sim_df.index),
            "benchmark_return": benchmark_returns.to_numpy(),
        }
    )


def export_run_artifact_bundle(
    *,
    task: TaskSpec,
    result: Any,
    record: RunRecord,
    artifacts_root: str | Path | None,
) -> None:
    if artifacts_root is None or record.status not in _RUN_EXPORT_STATUSES or result.artifact is None:
        return

    artifact = result.artifact
    artifact_dir = Path(artifacts_root) / task.symbol / task.window.window_id / task.model.model_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    returns_path = artifact_dir / "returns.csv"
    benchmark_returns_path = artifact_dir / "benchmark_returns.csv"
    equity_path = artifact_dir / "equity.csv"
    trades_path = artifact_dir / "trades.csv"
    metadata_path = artifact_dir / "metadata.json"

    returns_df = _series_frame(artifact.returns_series, "strategy_return", fillna=0.0)
    benchmark_returns_df = _benchmark_returns_frame(artifact.test_sim_df)
    equity_df = _series_frame(artifact.equity_series, "strategy_equity")

    returns_df.to_csv(returns_path, index=False)
    benchmark_returns_df.to_csv(benchmark_returns_path, index=False)
    equity_df.to_csv(equity_path, index=False)

    trades_exists = artifact.trades_df is not None and not artifact.trades_df.empty
    if trades_exists:
        artifact.trades_df.to_csv(trades_path, index=False)

    final_stage = artifact.pipeline_lineage[-1] if artifact.pipeline_lineage else None
    lineage = [
        {
            "stage_key": stage.stage_key,
            "display_label": stage.display_label,
            "short_label": stage.short_label,
        }
        for stage in artifact.pipeline_lineage
    ]
    metadata_payload = {
        "artifact_id": str(artifact.id),
        "symbol": task.symbol,
        "window_id": task.window.window_id,
        "model_id": task.model.model_id,
        "stage": task.model.stage,
        "final_stage_key": final_stage.stage_key if final_stage is not None else None,
        "status": record.status,
        "eval": artifact.eval or {},
        "ml_quality": artifact.ml_quality or {},
        "lineage": lineage,
    }
    metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    record.artifact_id = str(artifact.id)
    record.artifact_dir = str(artifact_dir)
    record.returns_path = str(returns_path)
    record.benchmark_returns_path = str(benchmark_returns_path)
    record.equity_path = str(equity_path)
    record.trades_path = str(trades_path) if trades_exists else None


def _read_metric_series(path_value: Any, value_column: str) -> pd.Series:
    path = Path(str(path_value))
    frame = pd.read_csv(path)
    if frame.empty or "date" not in frame.columns or value_column not in frame.columns:
        return pd.Series(dtype="float64")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    valid_mask = dates.notna() & values.notna()
    if not valid_mask.any():
        return pd.Series(dtype="float64")
    series = pd.Series(values.loc[valid_mask].to_numpy(), index=dates.loc[valid_mask], dtype="float64")
    if series.empty:
        return series
    return series.groupby(level=0).mean().sort_index()


def _aggregate_equal_weight(paths: list[Any], value_column: str) -> pd.Series:
    series_list = []
    for ordinal, path_value in enumerate(paths, start=1):
        series = _read_metric_series(path_value, value_column)
        if series.empty:
            continue
        series_list.append(series.rename(f"series_{ordinal}"))
    if not series_list:
        return pd.Series(dtype="float64")
    aligned = pd.concat(series_list, axis=1, join="outer").sort_index()
    aggregated = aligned.mean(axis=1, skipna=True).dropna()
    aggregated.name = value_column
    return aggregated


def _series_to_csv(series: pd.Series, value_column: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "date": _date_strings(series.index),
            value_column: pd.to_numeric(series, errors="coerce").to_numpy(),
        }
    ).to_csv(output_path, index=False)


def generate_quantstats_outputs(
    *,
    config: ResearchConfig,
    output_dir: Path,
    model_summary_df: pd.DataFrame,
    records_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]], Path]:
    quantstats_root = output_dir / "quantstats"
    summary = model_summary_df.copy()
    if "quantstats_html_path" not in summary.columns:
        summary["quantstats_html_path"] = None
    if not config.enable_quantstats or summary.empty or int(config.quantstats_top_n) <= 0:
        return summary, [], quantstats_root

    quantstats = _import_optional_dependency("quantstats")
    entries: list[dict[str, Any]] = []
    eligible = records_df[
        (records_df["window_kind"] == "main")
        & (records_df["status"].isin(sorted(_RUN_EXPORT_STATUSES)))
        & (records_df["returns_path"].notna())
        & (records_df["benchmark_returns_path"].notna())
    ].copy()
    if eligible.empty:
        return summary, entries, quantstats_root

    quantstats_root.mkdir(parents=True, exist_ok=True)
    top_rows = summary.sort_values("rank", ascending=True).head(int(config.quantstats_top_n))
    for row in top_rows.to_dict("records"):
        model_id = str(row["model_id"])
        selected = eligible[eligible["model_id"] == model_id].copy()
        if selected.empty:
            continue

        returns_series = _aggregate_equal_weight(selected["returns_path"].tolist(), "strategy_return")
        benchmark_series = _aggregate_equal_weight(selected["benchmark_returns_path"].tolist(), "benchmark_return")
        if returns_series.empty:
            raise ValueError(f"QuantStats aggregation produced no returns for model {model_id}.")
        benchmark_series = benchmark_series.reindex(returns_series.index).fillna(0.0)

        model_dir = quantstats_root / f"{int(row['rank'])}_{model_id}"
        model_dir.mkdir(parents=True, exist_ok=True)
        tearsheet_path = model_dir / "tearsheet.html"
        returns_path = model_dir / "returns.csv"
        benchmark_returns_path = model_dir / "benchmark_returns.csv"
        manifest_path = model_dir / "manifest.json"

        _series_to_csv(returns_series, "strategy_return", returns_path)
        _series_to_csv(benchmark_series, "benchmark_return", benchmark_returns_path)

        title = f"{row['display_name']} main-window equal-weight pooled tear sheet"
        quantstats.reports.html(
            returns_series,
            benchmark=benchmark_series,
            output=str(tearsheet_path),
            title=title,
        )

        manifest = {
            "model_id": model_id,
            "display_name": row["display_name"],
            "rank": int(row["rank"]),
            "selected_record_count": int(len(selected)),
            "aggregation_method": "main-window equal-weight pooled tear sheet",
            "total_score": float(row["total_score"]),
            "main_total_score": float(row["main_total_score"]) if pd.notna(row.get("main_total_score")) else None,
            "robustness_total_score": (
                float(row["robustness_total_score"]) if pd.notna(row.get("robustness_total_score")) else None
            ),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        summary.loc[summary["model_id"] == model_id, "quantstats_html_path"] = str(tearsheet_path)
        entries.append(
            {
                **manifest,
                "quantstats_html_path": str(tearsheet_path),
                "returns_path": str(returns_path),
                "benchmark_returns_path": str(benchmark_returns_path),
                "manifest_path": str(manifest_path),
            }
        )

    return summary, entries, quantstats_root


def _resolved_tracking_uri(config: ResearchConfig) -> str:
    if config.mlflow_tracking_uri:
        return str(config.mlflow_tracking_uri)
    tracking_dir = WORKSPACE_ROOT / "mlruns"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    return tracking_dir.resolve().as_uri()


def _scalar_params(config: ResearchConfig) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in config.to_dict().items():
        if isinstance(value, (str, int, float, bool)):
            params[key] = value
    return params


def _numeric_metric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if pd.isna(numeric):
        return None
    return numeric


def log_research_run_to_mlflow(
    *,
    config: ResearchConfig,
    output_dir: Path,
    records_df: pd.DataFrame,
    model_summary_df: pd.DataFrame,
    artifacts: dict[str, Path],
    quantstats_dir: Path,
) -> Path:
    mlflow = _import_optional_dependency("mlflow")
    tracking_uri = _resolved_tracking_uri(config)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(config.mlflow_experiment_name)
    run_name = f"{config.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    mlflow_run_path = output_dir / "mlflow_run.json"

    with mlflow.start_run(run_name=run_name) as active_run:
        for key, value in _scalar_params(config).items():
            mlflow.log_param(key, value)
        mlflow.set_tags(
            {
                "config_name": config.name,
                "output_subdir": config.output_subdir,
                "market": config.market,
                "run_stage_b": str(bool(config.run_stage_b)).lower(),
                "run_robustness": str(bool(config.run_robustness)).lower(),
            }
        )

        top_row = model_summary_df.iloc[0] if not model_summary_df.empty else None
        status_counts = records_df["status"].value_counts(dropna=False).to_dict() if not records_df.empty else {}
        metrics = {
            "stock_count": float(records_df["symbol"].nunique()) if not records_df.empty else 0.0,
            "record_count": float(len(records_df)),
            "model_count": float(len(model_summary_df)),
            "top_total_score": _numeric_metric(top_row["total_score"]) if top_row is not None else None,
            "top_main_total_score": _numeric_metric(top_row.get("main_total_score")) if top_row is not None else None,
            "top_robustness_total_score": (
                _numeric_metric(top_row.get("robustness_total_score")) if top_row is not None else None
            ),
            "success_count": float(status_counts.get("success", 0)),
            "degraded_count": float(status_counts.get("degraded", 0)),
            "failed_count": float(status_counts.get("failed", 0)),
            "skipped_count": float(status_counts.get("SKIPPED", 0)),
        }
        for key, value in metrics.items():
            if value is not None:
                mlflow.log_metric(key, value)

        for artifact_path in artifacts.values():
            if artifact_path.exists() and artifact_path.is_file():
                mlflow.log_artifact(str(artifact_path))
        if quantstats_dir.exists() and any(quantstats_dir.iterdir()):
            mlflow.log_artifacts(str(quantstats_dir), artifact_path="quantstats")

        run_info = active_run.info
        mlflow_run_payload = {
            "tracking_uri": tracking_uri,
            "experiment_name": config.mlflow_experiment_name,
            "run_id": run_info.run_id,
            "artifact_uri": run_info.artifact_uri,
        }
        mlflow_run_path.write_text(
            json.dumps(mlflow_run_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        mlflow.log_artifact(str(mlflow_run_path))

    return mlflow_run_path
