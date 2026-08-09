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

MARKET_MATRIX_COLUMNS = [
    "market", "strategy_id", "strategy_label", "evaluation_window", "symbol_count",
    "successful_symbol_count", "failed_symbol_count", "skipped_symbol_count", "coverage_rate",
    "total_return", "annualized_return", "sharpe", "max_drawdown", "total_turnover",
    "total_transaction_cost", "net_total_return", "naive_win_rate", "median_excess_return",
    "rolling_rank_median", "rolling_direction_consistency", "degraded_run_rate",
]


def _numeric_mean(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _numeric_median(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.median()) if not values.empty else None


def _value_or_fallback(primary: float | None, fallback: float | None) -> float | None:
    return fallback if primary is None else primary


def _naive_win_rate(valid: pd.DataFrame, naive_returns: pd.Series) -> float | None:
    if valid.empty or naive_returns.empty:
        return None
    key_index = pd.MultiIndex.from_frame(valid[["window_id", "symbol"]])
    comparisons = valid.assign(
        _naive_return=naive_returns.reindex(key_index).to_numpy(),
        _strategy_return=pd.to_numeric(valid["test_annret"], errors="coerce"),
    ).dropna(subset=["_naive_return", "_strategy_return"])
    return float((comparisons["_strategy_return"] > comparisons["_naive_return"]).mean()) if not comparisons.empty else None


def _apply_rolling_metrics(matrix: pd.DataFrame) -> pd.DataFrame:
    if matrix.empty:
        return matrix
    result = matrix.copy()
    rolling = result[result["evaluation_window"].str.startswith("rolling_", na=False)].copy()
    if rolling.empty:
        return result
    rolling["_rank"] = rolling.groupby(["market", "evaluation_window"])["median_excess_return"].rank(
        method="average", ascending=False
    )
    summary = rolling.groupby(["market", "strategy_id"], as_index=False).agg(
        rolling_rank_median=("_rank", "median"),
        rolling_direction_consistency=("median_excess_return", lambda values: float((values > 0).mean())),
    )
    main_mask = result["evaluation_window"] == "main"
    result = result.merge(summary, on=["market", "strategy_id"], how="left", suffixes=("", "_rolling"))
    result.loc[main_mask, "rolling_rank_median"] = result.loc[main_mask, "rolling_rank_median_rolling"]
    result.loc[main_mask, "rolling_direction_consistency"] = result.loc[main_mask, "rolling_direction_consistency_rolling"]
    return result.drop(columns=["rolling_rank_median_rolling", "rolling_direction_consistency_rolling"])


def build_market_strategy_matrix(records_df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Build frozen market x strategy x evaluation-window rows from run records."""
    if records_df.empty:
        return pd.DataFrame(columns=MARKET_MATRIX_COLUMNS)
    frame = records_df.copy()
    frame["market"] = str(market).strip().upper()
    valid_statuses = frame["status"].astype(str).str.lower().isin(["success", "degraded"])
    naive_returns = pd.to_numeric(
        frame.loc[valid_statuses & (frame["model_id"] == "naive")]
        .groupby(["window_id", "symbol"])["test_annret"].median(),
        errors="coerce",
    )
    rows: list[dict[str, object]] = []
    for (strategy_id, label, window), group in frame.groupby(
        ["model_id", "display_name", "window_id"], dropna=False, sort=False
    ):
        statuses = group["status"].astype(str).str.lower()
        successful = int(statuses.eq("success").sum())
        degraded = int(statuses.eq("degraded").sum())
        failed = int(statuses.eq("failed").sum())
        skipped = int(statuses.eq("skipped").sum())
        symbol_count = int(len(group))
        valid = group[statuses.isin(["success", "degraded"])]
        total_turnover = _value_or_fallback(
            _numeric_mean(valid, "total_turnover"), _numeric_mean(valid, "test_turnover")
        )
        net_total_return = _value_or_fallback(
            _numeric_median(valid, "net_total_return"), _numeric_median(valid, "test_cumret")
        )
        rows.append({
            "market": frame["market"].iloc[0],
            "strategy_id": str(strategy_id),
            "strategy_label": str(label),
            "evaluation_window": str(window),
            "symbol_count": symbol_count,
            "successful_symbol_count": successful,
            "failed_symbol_count": failed,
            "skipped_symbol_count": skipped,
            "coverage_rate": float((successful + degraded) / symbol_count) if symbol_count else 0.0,
            "total_return": _numeric_median(valid, "test_cumret"),
            "annualized_return": _numeric_median(valid, "test_annret"),
            "sharpe": _numeric_median(valid, "test_sharpe"),
            "max_drawdown": _numeric_median(valid, "test_maxdd"),
            "total_turnover": total_turnover,
            "total_transaction_cost": _numeric_mean(valid, "total_transaction_cost"),
            "net_total_return": net_total_return,
            "naive_win_rate": _naive_win_rate(valid, naive_returns) if strategy_id != "naive" else None,
            "median_excess_return": _numeric_median(valid, "test_excess_return"),
            "rolling_rank_median": None,
            "rolling_direction_consistency": None,
            "degraded_run_rate": float(degraded / symbol_count) if symbol_count else 0.0,
        })
    return _apply_rolling_metrics(pd.DataFrame(rows, columns=MARKET_MATRIX_COLUMNS))[MARKET_MATRIX_COLUMNS]


def build_market_strategy_recommendations(
    matrix_df: pd.DataFrame,
    *,
    source_limitations: dict[str, list[str]] | None = None,
    min_valid_symbols: int = 2,
    min_coverage_rate: float = 0.5,
    min_naive_win_rate: float = 0.5,
    min_rolling_direction_consistency: float = 0.5,
    max_degraded_run_rate: float = 0.5,
    require_rolling_evidence: bool = True,
    tie_score_margin: float = 0.02,
    eligible_strategy_ids: set[str] | None = None,
) -> dict[str, object]:
    """Apply the frozen multi-signal winner rule and always emit both markets."""
    recommendations: dict[str, object] = {}
    limitations_map = source_limitations or {}
    for market in ("US", "CN_A"):
        market_rows = (
            matrix_df[(matrix_df["market"] == market) & (matrix_df["evaluation_window"] == "main")].copy()
            if not matrix_df.empty
            else pd.DataFrame()
        )
        limitations = list(limitations_map.get(market, []))
        if not market_rows.empty:
            numeric_columns = [
                "symbol_count", "successful_symbol_count", "coverage_rate", "net_total_return",
                "naive_win_rate", "median_excess_return", "sharpe", "max_drawdown",
                "rolling_rank_median", "rolling_direction_consistency", "degraded_run_rate",
            ]
            for column in numeric_columns:
                market_rows[column] = pd.to_numeric(market_rows[column], errors="coerce")
            market_rows["valid_symbol_count"] = (
                market_rows["coverage_rate"] * market_rows["symbol_count"]
            ).round()

        valid = market_rows[market_rows["strategy_id"] != "naive"] if not market_rows.empty else market_rows
        if eligible_strategy_ids is not None and not valid.empty:
            valid = valid[valid["strategy_id"].isin(eligible_strategy_ids)]
        if not valid.empty:
            valid = valid[
                (valid["valid_symbol_count"] >= min_valid_symbols)
                & (valid["coverage_rate"] >= min_coverage_rate)
                & (valid["net_total_return"] > 0)
                & (valid["median_excess_return"] > 0)
                & (valid["naive_win_rate"] >= min_naive_win_rate)
                & (valid["degraded_run_rate"] <= max_degraded_run_rate)
            ]
        if require_rolling_evidence and not valid.empty:
            valid = valid[
                valid["rolling_rank_median"].notna()
                & (valid["rolling_direction_consistency"] >= min_rolling_direction_consistency)
            ]

        thresholds = {
            "min_valid_symbols": int(min_valid_symbols),
            "min_coverage_rate": float(min_coverage_rate),
            "min_naive_win_rate": float(min_naive_win_rate),
            "min_rolling_direction_consistency": float(min_rolling_direction_consistency),
            "max_degraded_run_rate": float(max_degraded_run_rate),
            "require_rolling_evidence": bool(require_rolling_evidence),
            "eligible_strategy_ids": sorted(eligible_strategy_ids) if eligible_strategy_ids is not None else None,
        }
        if valid.empty:
            limitations.append(
                "insufficient evidence: no non-naive candidate met the sample, coverage, "
                "post-cost return, naive-win, rolling-stability, and degradation thresholds"
            )
            recommendations[market] = {
                "recommendation": None,
                "confidence": "insufficient_evidence",
                "evidence": {"matrix_rows": [], "thresholds": thresholds},
                "limitations": list(dict.fromkeys(limitations)),
            }
            continue

        def _rank_or_neutral(values: pd.Series) -> pd.Series:
            return values.rank(pct=True).fillna(0.5)

        rank_inputs = {
            "excess": _rank_or_neutral(valid["median_excess_return"]),
            "sharpe": _rank_or_neutral(valid["sharpe"]),
            "drawdown": _rank_or_neutral(valid["max_drawdown"]),
            "naive_win": _rank_or_neutral(valid["naive_win_rate"]),
            "rolling": _rank_or_neutral(valid["rolling_direction_consistency"]),
            "coverage": _rank_or_neutral(valid["coverage_rate"]),
            "degradation": _rank_or_neutral(-valid["degraded_run_rate"]),
        }
        valid = valid.assign(
            selection_score=(
                0.30 * rank_inputs["excess"]
                + 0.20 * rank_inputs["sharpe"]
                + 0.10 * rank_inputs["drawdown"]
                + 0.15 * rank_inputs["naive_win"]
                + 0.15 * rank_inputs["rolling"]
                + 0.05 * rank_inputs["coverage"]
                + 0.05 * rank_inputs["degradation"]
            )
        )
        ranked = valid.sort_values(
            ["selection_score", "median_excess_return", "sharpe"], ascending=False
        ).reset_index(drop=True)
        winner = ranked.iloc[0]
        tied = (
            len(ranked) > 1
            and abs(float(winner["selection_score"]) - float(ranked.iloc[1]["selection_score"]))
            <= tie_score_margin
        )
        winner_valid_symbols = int(winner["valid_symbol_count"])
        if (
            winner_valid_symbols >= 6
            and float(winner["coverage_rate"]) >= 0.8
            and float(winner["naive_win_rate"]) >= 0.6
            and (
                not require_rolling_evidence
                or float(winner["rolling_direction_consistency"]) >= 2.0 / 3.0
            )
            and float(winner["degraded_run_rate"]) <= 0.1
        ):
            confidence = "high"
        elif winner_valid_symbols >= 4 and float(winner["coverage_rate"]) >= 0.7:
            confidence = "medium"
        else:
            confidence = "low"
        if tied:
            limitations.append(
                f"top candidates are within the {tie_score_margin:.3f} selection-score tie margin"
            )
            recommendations[market] = {
                "recommendation": None,
                "confidence": "insufficient_evidence",
                "evidence": {
                    "matrix_rows": [
                        {"market": market, "strategy_id": str(row["strategy_id"]), "evaluation_window": "main"}
                        for _, row in ranked.head(2).iterrows()
                    ],
                    "thresholds": thresholds,
                    "selection_scores": {
                        str(row["strategy_id"]): float(row["selection_score"])
                        for _, row in ranked.head(2).iterrows()
                    },
                },
                "limitations": list(dict.fromkeys(limitations)),
            }
        else:
            winner_id = str(winner["strategy_id"])
            rolling_rows = matrix_df[
                (matrix_df["market"] == market)
                & (matrix_df["strategy_id"] == winner_id)
                & (matrix_df["evaluation_window"].astype(str).str.startswith("rolling_"))
            ]
            row_refs = [
                {"market": market, "strategy_id": winner_id, "evaluation_window": "main"},
                *[
                    {"market": market, "strategy_id": winner_id, "evaluation_window": str(row["evaluation_window"])}
                    for _, row in rolling_rows.iterrows()
                ],
            ]
            recommendations[market] = {
                "recommendation": winner_id,
                "confidence": confidence,
                "evidence": {
                    "matrix_rows": row_refs,
                    "thresholds": thresholds,
                    "selection_score": float(winner["selection_score"]),
                    "metrics": {
                        "valid_symbol_count": winner_valid_symbols,
                        "coverage_rate": float(winner["coverage_rate"]),
                        "net_total_return": float(winner["net_total_return"]),
                        "median_excess_return": float(winner["median_excess_return"]),
                        "naive_win_rate": float(winner["naive_win_rate"]),
                        "rolling_rank_median": (
                            float(winner["rolling_rank_median"])
                            if pd.notna(winner["rolling_rank_median"])
                            else None
                        ),
                        "rolling_direction_consistency": (
                            float(winner["rolling_direction_consistency"])
                            if pd.notna(winner["rolling_direction_consistency"])
                            else None
                        ),
                        "degraded_run_rate": float(winner["degraded_run_rate"]),
                    },
                },
                "limitations": list(dict.fromkeys(limitations)),
            }
    return {"schema_version": "1.0", "markets": recommendations}


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
