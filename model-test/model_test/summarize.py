from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

from model_test.models import ModelAggregate, RunRecord, StockProfile


ROBUSTNESS_SCORE_WEIGHTS = {
    "median_excess_return": 30.0,
    "median_sharpe": 30.0,
    "drawdown_control": 15.0,
    "stability": 15.0,
    "reliability": 10.0,
}

SUMMARY_COLUMNS = [
    "model_id",
    "display_name",
    "family_group",
    "stage",
    "attempted_count",
    "valid_count",
    "success_rate",
    "degraded_rate",
    "beat_naive_rate",
    "median_annret",
    "median_excess_return",
    "median_sharpe",
    "median_maxdd",
    "annret_iqr",
    "sharpe_iqr",
    "median_train_test_gap",
    "reliability_raw",
    "beat_naive_score",
    "excess_return_score",
    "sharpe_score",
    "drawdown_score",
    "stability_score",
    "overfit_score",
    "reliability_score",
    "main_total_score",
    "robustness_attempted_count",
    "robustness_valid_count",
    "robustness_success_rate",
    "robustness_degraded_rate",
    "robustness_median_annret",
    "robustness_median_excess_return",
    "robustness_median_sharpe",
    "robustness_median_maxdd",
    "robustness_annret_iqr",
    "robustness_sharpe_iqr",
    "robustness_reliability_raw",
    "robustness_excess_return_score",
    "robustness_sharpe_score",
    "robustness_drawdown_score",
    "robustness_stability_score",
    "robustness_reliability_score",
    "robustness_total_score",
    "total_score",
    "rank",
]

SEGMENT_COLUMNS = [
    "segment_key",
    "trend_bucket",
    "volatility_bucket",
    "model_id",
    "display_name",
    "family_group",
    "stage",
    "attempted_count",
    "valid_count",
    "success_rate",
    "degraded_rate",
    "beat_naive_rate",
    "median_annret",
    "median_excess_return",
    "median_sharpe",
    "median_maxdd",
    "annret_iqr",
    "sharpe_iqr",
    "median_train_test_gap",
    "reliability_raw",
    "beat_naive_score",
    "excess_return_score",
    "sharpe_score",
    "drawdown_score",
    "stability_score",
    "overfit_score",
    "reliability_score",
    "total_score",
    "segment_rank",
    "suitability",
]

ROBUSTNESS_COLUMNS = [
    "model_id",
    "display_name",
    "family_group",
    "stage",
    "attempted_count",
    "valid_count",
    "success_rate",
    "degraded_rate",
    "median_annret",
    "median_excess_return",
    "median_sharpe",
    "median_maxdd",
    "annret_iqr",
    "sharpe_iqr",
    "reliability_raw",
    "robustness_excess_return_score",
    "robustness_sharpe_score",
    "robustness_drawdown_score",
    "robustness_stability_score",
    "robustness_reliability_score",
    "robustness_total_score",
]

ROBUSTNESS_MERGE_MAP = {
    "attempted_count": "robustness_attempted_count",
    "valid_count": "robustness_valid_count",
    "success_rate": "robustness_success_rate",
    "degraded_rate": "robustness_degraded_rate",
    "median_annret": "robustness_median_annret",
    "median_excess_return": "robustness_median_excess_return",
    "median_sharpe": "robustness_median_sharpe",
    "median_maxdd": "robustness_median_maxdd",
    "annret_iqr": "robustness_annret_iqr",
    "sharpe_iqr": "robustness_sharpe_iqr",
    "reliability_raw": "robustness_reliability_raw",
    "robustness_excess_return_score": "robustness_excess_return_score",
    "robustness_sharpe_score": "robustness_sharpe_score",
    "robustness_drawdown_score": "robustness_drawdown_score",
    "robustness_stability_score": "robustness_stability_score",
    "robustness_reliability_score": "robustness_reliability_score",
    "robustness_total_score": "robustness_total_score",
}


def records_to_dataframe(records: Iterable[RunRecord]) -> pd.DataFrame:
    rows = [record.to_row() for record in records]
    return pd.DataFrame(rows)


def profiles_to_dataframe(profiles: Iterable[StockProfile]) -> pd.DataFrame:
    rows = [profile.to_row() for profile in profiles]
    return pd.DataFrame(rows)


def _main_attempted_df(records_df: pd.DataFrame) -> pd.DataFrame:
    if records_df.empty:
        return records_df.copy()
    df = records_df[records_df["window_kind"] == "main"].copy()
    if df.empty:
        return df
    return df[df["status"] != "SKIPPED"].copy()


def _valid_with_naive(records_df: pd.DataFrame) -> pd.DataFrame:
    attempted = _main_attempted_df(records_df)
    if attempted.empty:
        return attempted
    valid = attempted[attempted["status"].isin(["success", "degraded"])].copy()
    valid = valid[valid["test_annret"].notna()].copy()
    naive = valid[valid["model_id"] == "naive"][["symbol", "window_id", "test_annret"]].rename(
        columns={"test_annret": "naive_annret"}
    )
    valid = valid.merge(naive, on=["symbol", "window_id"], how="left")
    valid["beat_naive"] = (
        (valid["test_annret"] > valid["naive_annret"]).where(valid["naive_annret"].notna())
    ).astype("float64")
    return valid


def _aggregate_rows(
    attempted_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    if attempted_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    valid_groups = {key: group for key, group in valid_df.groupby(group_columns)} if not valid_df.empty else {}

    for group_key, attempted_group in attempted_df.groupby(group_columns):
        key_tuple = group_key if isinstance(group_key, tuple) else (group_key,)
        row = dict(zip(group_columns, key_tuple, strict=False))
        valid_group = valid_groups.get(group_key)
        attempted_count = len(attempted_group)
        valid_count = 0 if valid_group is None else len(valid_group)
        success_rate = float((attempted_group["status"] == "success").mean()) if attempted_count else 0.0
        degraded_rate = float((attempted_group["status"] == "degraded").mean()) if attempted_count else 0.0
        reliability_raw = success_rate - 0.5 * degraded_rate

        row.update(
            {
                "attempted_count": int(attempted_count),
                "valid_count": int(valid_count),
                "success_rate": success_rate,
                "degraded_rate": degraded_rate,
                "reliability_raw": reliability_raw,
                "beat_naive_rate": None,
                "median_annret": None,
                "median_excess_return": None,
                "median_sharpe": None,
                "median_maxdd": None,
                "annret_iqr": None,
                "sharpe_iqr": None,
                "median_train_test_gap": None,
            }
        )
        if valid_group is not None and not valid_group.empty:
            annret_series = pd.to_numeric(valid_group["test_annret"], errors="coerce")
            sharpe_series = pd.to_numeric(valid_group["test_sharpe"], errors="coerce")
            row.update(
                {
                    "beat_naive_rate": float(valid_group["beat_naive"].dropna().mean())
                    if "beat_naive" in valid_group.columns and valid_group["beat_naive"].dropna().size
                    else None,
                    "median_annret": float(annret_series.median()) if annret_series.notna().any() else None,
                    "median_excess_return": float(pd.to_numeric(valid_group["test_excess_return"], errors="coerce").median()),
                    "median_sharpe": float(sharpe_series.median()) if sharpe_series.notna().any() else None,
                    "median_maxdd": float(pd.to_numeric(valid_group["test_maxdd"], errors="coerce").median()),
                    "annret_iqr": float(annret_series.quantile(0.75) - annret_series.quantile(0.25))
                    if annret_series.notna().any()
                    else None,
                    "sharpe_iqr": float(sharpe_series.quantile(0.75) - sharpe_series.quantile(0.25))
                    if sharpe_series.notna().any()
                    else None,
                    "median_train_test_gap": float(pd.to_numeric(valid_group["train_test_gap"], errors="coerce").median()),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _percentile(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    output = pd.Series(0.0, index=series.index, dtype="float64")
    if valid.empty:
        return output
    ranked = valid.rank(method="average", pct=True, ascending=True) * 100.0
    output.loc[ranked.index] = ranked
    return output


def _score_partition(partition: pd.DataFrame, score_weights: dict[str, float]) -> pd.DataFrame:
    scored = partition.copy()

    drawdown_raw = -pd.to_numeric(scored["median_maxdd"], errors="coerce").abs()
    stability_raw = -(
        pd.to_numeric(scored["annret_iqr"], errors="coerce").fillna(float("inf"))
        + pd.to_numeric(scored["sharpe_iqr"], errors="coerce").fillna(float("inf"))
    )
    overfit_raw = -pd.to_numeric(scored["median_train_test_gap"], errors="coerce")

    scored["beat_naive_score"] = _percentile(pd.to_numeric(scored["beat_naive_rate"], errors="coerce"))
    scored["excess_return_score"] = _percentile(pd.to_numeric(scored["median_excess_return"], errors="coerce"))
    scored["sharpe_score"] = _percentile(pd.to_numeric(scored["median_sharpe"], errors="coerce"))
    scored["drawdown_score"] = _percentile(drawdown_raw)
    scored["stability_score"] = _percentile(stability_raw.replace(-float("inf"), pd.NA))
    scored["overfit_score"] = _percentile(overfit_raw)
    scored["reliability_score"] = _percentile(pd.to_numeric(scored["reliability_raw"], errors="coerce"))

    scored["total_score"] = (
        score_weights["beat_naive_rate"] * scored["beat_naive_score"]
        + score_weights["median_excess_return"] * scored["excess_return_score"]
        + score_weights["median_sharpe"] * scored["sharpe_score"]
        + score_weights["drawdown_control"] * scored["drawdown_score"]
        + score_weights["stability"] * scored["stability_score"]
        + score_weights["overfit_discipline"] * scored["overfit_score"]
        + score_weights["reliability"] * scored["reliability_score"]
    ) / 100.0
    return scored


def _score_robustness_partition(partition: pd.DataFrame) -> pd.DataFrame:
    scored = partition.copy()
    drawdown_raw = -pd.to_numeric(scored["median_maxdd"], errors="coerce").abs()
    stability_raw = -(
        pd.to_numeric(scored["annret_iqr"], errors="coerce").fillna(float("inf"))
        + pd.to_numeric(scored["sharpe_iqr"], errors="coerce").fillna(float("inf"))
    )

    scored["robustness_excess_return_score"] = _percentile(
        pd.to_numeric(scored["median_excess_return"], errors="coerce")
    )
    scored["robustness_sharpe_score"] = _percentile(pd.to_numeric(scored["median_sharpe"], errors="coerce"))
    scored["robustness_drawdown_score"] = _percentile(drawdown_raw)
    scored["robustness_stability_score"] = _percentile(stability_raw.replace(-float("inf"), pd.NA))
    scored["robustness_reliability_score"] = _percentile(pd.to_numeric(scored["reliability_raw"], errors="coerce"))
    scored["robustness_total_score"] = (
        ROBUSTNESS_SCORE_WEIGHTS["median_excess_return"] * scored["robustness_excess_return_score"]
        + ROBUSTNESS_SCORE_WEIGHTS["median_sharpe"] * scored["robustness_sharpe_score"]
        + ROBUSTNESS_SCORE_WEIGHTS["drawdown_control"] * scored["robustness_drawdown_score"]
        + ROBUSTNESS_SCORE_WEIGHTS["stability"] * scored["robustness_stability_score"]
        + ROBUSTNESS_SCORE_WEIGHTS["reliability"] * scored["robustness_reliability_score"]
    ) / 100.0
    return scored


def _merge_robustness_scores(
    summary_df: pd.DataFrame,
    robustness_df: pd.DataFrame | None,
    robustness_weight: float,
) -> pd.DataFrame:
    merged = summary_df.copy()
    merged["main_total_score"] = merged["total_score"]

    weight = min(max(float(robustness_weight), 0.0), 1.0)
    if robustness_df is None or robustness_df.empty or weight <= 0.0:
        for target_column in ROBUSTNESS_MERGE_MAP.values():
            merged[target_column] = None
        merged["total_score"] = merged["main_total_score"]
        return merged

    robustness_subset = robustness_df[["model_id", *ROBUSTNESS_MERGE_MAP.keys()]].rename(columns=ROBUSTNESS_MERGE_MAP)
    merged = merged.merge(robustness_subset, on="model_id", how="left")
    for target_column in ROBUSTNESS_MERGE_MAP.values():
        if target_column not in merged.columns:
            merged[target_column] = None
    merged["total_score"] = merged["main_total_score"]

    robustness_mask = merged["robustness_total_score"].notna()
    merged.loc[robustness_mask, "total_score"] = (
        (1.0 - weight) * pd.to_numeric(merged.loc[robustness_mask, "main_total_score"], errors="coerce")
        + weight * pd.to_numeric(merged.loc[robustness_mask, "robustness_total_score"], errors="coerce")
    )
    return merged


def build_model_summary(
    records_df: pd.DataFrame,
    score_weights: dict[str, float],
    *,
    robustness_df: pd.DataFrame | None = None,
    robustness_weight: float = 0.0,
) -> tuple[pd.DataFrame, list[ModelAggregate]]:
    attempted = _main_attempted_df(records_df)
    valid = _valid_with_naive(records_df)
    summary = _aggregate_rows(attempted, valid, ["model_id", "display_name", "family_group", "stage"])
    if summary.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS), []
    summary = _score_partition(summary, score_weights)
    summary = _merge_robustness_scores(summary, robustness_df, robustness_weight)
    summary = summary.sort_values(
        [
            "total_score",
            "robustness_total_score",
            "main_total_score",
            "beat_naive_rate",
            "median_excess_return",
            "median_sharpe",
        ],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)
    summary["rank"] = summary.index + 1
    summary = summary[SUMMARY_COLUMNS]
    aggregates = [ModelAggregate(**row) for row in summary.to_dict("records")]
    return summary, aggregates


def build_segment_summary(records_df: pd.DataFrame, score_weights: dict[str, float]) -> pd.DataFrame:
    attempted = _main_attempted_df(records_df)
    if attempted.empty or "segment_key" not in attempted.columns:
        return pd.DataFrame(columns=SEGMENT_COLUMNS)
    valid = _valid_with_naive(records_df)
    summary = _aggregate_rows(
        attempted,
        valid,
        ["segment_key", "trend_bucket", "volatility_bucket", "model_id", "display_name", "family_group", "stage"],
    )
    if summary.empty:
        return pd.DataFrame(columns=SEGMENT_COLUMNS)

    partitions: list[pd.DataFrame] = []
    for _segment_key, segment_frame in summary.groupby("segment_key", sort=False):
        scored = _score_partition(segment_frame, score_weights)
        scored = scored.sort_values(
            ["total_score", "beat_naive_rate", "median_excess_return", "median_sharpe"],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)
        scored["segment_rank"] = scored.index + 1
        total_models = len(scored)
        bottom_count = max(1, math.ceil(total_models * 0.3))
        suitability: list[str] = []
        for row in scored.itertuples(index=False):
            if row.valid_count < 5:
                suitability.append("insufficient_sample")
            elif row.segment_rank <= 2 and (row.beat_naive_rate or 0.0) >= 0.60:
                suitability.append("suitable")
            elif row.segment_rank > total_models - bottom_count and (row.beat_naive_rate or 0.0) < 0.40:
                suitability.append("not_suitable")
            else:
                suitability.append("neutral")
        scored["suitability"] = suitability
        partitions.append(scored)

    result = pd.concat(partitions, ignore_index=True)
    return result[SEGMENT_COLUMNS]


def build_robustness_summary(records_df: pd.DataFrame) -> pd.DataFrame:
    if records_df.empty:
        return pd.DataFrame(columns=ROBUSTNESS_COLUMNS)
    rolling = records_df[(records_df["window_kind"] == "rolling") & (records_df["status"] != "SKIPPED")].copy()
    if rolling.empty:
        return pd.DataFrame(columns=ROBUSTNESS_COLUMNS)
    valid = rolling[rolling["status"].isin(["success", "degraded"])].copy()
    summary = _aggregate_rows(rolling, valid, ["model_id", "display_name", "family_group", "stage"])
    if summary.empty:
        return pd.DataFrame(columns=ROBUSTNESS_COLUMNS)
    summary = _score_robustness_partition(summary)
    summary = summary.sort_values(
        ["robustness_total_score", "median_sharpe", "median_excess_return"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return summary[ROBUSTNESS_COLUMNS]


def pick_stage_b_winners(model_summary_df: pd.DataFrame) -> dict[str, str]:
    winners: dict[str, str] = {}
    if model_summary_df.empty:
        return winners
    score_column = "main_total_score" if "main_total_score" in model_summary_df.columns else "total_score"
    for family_group in ("sm", "fsm"):
        family = model_summary_df[
            (model_summary_df["family_group"] == family_group)
            & model_summary_df["model_id"].str.contains("_", regex=False)
        ].copy()
        if family.empty:
            continue
        winners[family_group] = str(family.sort_values(score_column, ascending=False).iloc[0]["model_id"])
    return winners
