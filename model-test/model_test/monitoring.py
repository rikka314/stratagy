from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from model_test.config import load_research_config
from model_test.summarize import build_model_summary, build_robustness_summary


CHECKPOINT_FILENAME = "_checkpoint_runs.csv"
VALID_STATUSES = {"success", "degraded"}


def load_checkpoint_records(
    run_dir: str | Path,
    *,
    fallback: pd.DataFrame | None = None,
) -> pd.DataFrame:
    path = Path(run_dir) / CHECKPOINT_FILENAME
    if not path.is_file():
        return fallback.copy() if fallback is not None else pd.DataFrame()
    for _attempt in range(3):
        try:
            frame = pd.read_csv(path, dtype={"symbol": "string"})
            required = {"symbol", "window_id", "window_kind", "model_id", "stage", "status"}
            if required.issubset(frame.columns):
                return frame.drop_duplicates(
                    subset=["symbol", "window_id", "model_id"], keep="last"
                ).reset_index(drop=True)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
    return fallback.copy() if fallback is not None else pd.DataFrame()


def _coverage_by_model(frame: pd.DataFrame, denominator: int) -> dict[str, dict[str, Any]]:
    if frame.empty or denominator <= 0:
        return {}
    valid = frame[frame["status"].astype(str).str.lower().isin(VALID_STATUSES)].copy()
    results: dict[str, dict[str, Any]] = {}
    for model_id, group in frame.groupby("model_id", sort=False):
        valid_group = valid[valid["model_id"] == model_id]
        completed = int(len(group))
        valid_count = int(len(valid_group))
        results[str(model_id)] = {
            "completed_records": completed,
            "valid_records": valid_count,
            "coverage": min(1.0, completed / denominator),
        }
    return results


def _attach_coverage(
    summary: pd.DataFrame,
    source: pd.DataFrame,
    *,
    denominator: int,
) -> pd.DataFrame:
    if summary.empty:
        return summary.copy()
    coverage = _coverage_by_model(source, denominator)
    result = summary.copy()
    result["completed_records"] = result["model_id"].map(
        lambda value: coverage.get(str(value), {}).get("completed_records", 0)
    )
    result["coverage"] = result["model_id"].map(
        lambda value: coverage.get(str(value), {}).get("coverage", 0.0)
    )
    return result


def build_stage_leaderboards(
    records_df: pd.DataFrame,
    *,
    config_path: str | Path,
    final_summary_path: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    config = load_research_config(config_path)
    if records_df.empty:
        empty = pd.DataFrame()
        return {"stage_a": empty, "stage_b": empty, "rolling": empty, "final": empty}

    status = records_df["status"].astype(str).str.lower()
    records = records_df.copy()
    records["status"] = status
    main = records[records["window_kind"].astype(str).str.lower() == "main"].copy()
    stage_a_source = main[main["stage"].astype(str).str.upper() == "A"].copy()
    stage_a, _ = build_model_summary(stage_a_source, config.score_weights)
    stage_a = _attach_coverage(stage_a, stage_a_source, denominator=int(config.main_pool_size))

    stage_b_only = main[main["stage"].astype(str).str.upper() == "B"].copy()
    naive_rows = main[main["model_id"].astype(str) == "naive"].copy()
    stage_b_scoring = pd.concat([naive_rows, stage_b_only], ignore_index=True)
    stage_b, _ = build_model_summary(stage_b_scoring, config.score_weights)
    if not stage_b.empty:
        stage_b = stage_b[stage_b["stage"].astype(str).str.upper() == "B"].reset_index(drop=True)
        stage_b["rank"] = stage_b.index + 1
    stage_b = _attach_coverage(stage_b, stage_b_only, denominator=int(config.main_pool_size))

    rolling_source = records[records["window_kind"].astype(str).str.lower() == "rolling"].copy()
    rolling = build_robustness_summary(rolling_source)
    rolling_denominator = int(config.main_pool_size) * int(config.rolling_window_count)
    rolling = _attach_coverage(rolling, rolling_source, denominator=rolling_denominator)
    if not rolling.empty:
        rolling["rank"] = rolling.index + 1

    final = pd.DataFrame()
    if final_summary_path is not None:
        path = Path(final_summary_path)
        try:
            final = pd.read_csv(path) if path.is_file() else pd.DataFrame()
        except (OSError, ValueError, pd.errors.ParserError):
            final = pd.DataFrame()
    return {"stage_a": stage_a, "stage_b": stage_b, "rolling": rolling, "final": final}


def leaderboard_view(frame: pd.DataFrame, *, robustness: bool = False) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    score_column = "robustness_total_score" if robustness else "total_score"
    columns = [
        "rank",
        "model_id",
        "display_name",
        "coverage",
        "completed_records",
        "valid_count",
        "success_rate",
        score_column,
        "median_sharpe",
        "median_excess_return",
        "median_maxdd",
    ]
    selected = [column for column in columns if column in frame.columns]
    return frame[selected].copy()

