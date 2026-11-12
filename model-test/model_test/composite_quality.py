"""Quality gates and audit helpers for Composite Phase 0/1."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_PRICE_COLUMNS = ("date", "open", "high", "low", "close", "volume")


def validate_price_frame(frame: pd.DataFrame) -> dict[str, object]:
    """Return a serialisable price-quality report; raise on hard failures."""
    missing = sorted(set(REQUIRED_PRICE_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"price frame missing columns: {missing}")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]].apply(
        pd.to_numeric, errors="coerce"
    )
    failures: list[str] = []
    warnings: list[str] = []
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        failures.append("invalid_or_duplicate_dates")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        failures.append("non_finite_ohlcv")
    if (numeric.loc[:, ["open", "high", "low", "close"]] <= 0).any().any():
        failures.append("non_positive_price")
    if (numeric.loc[:, ["open", "close"]].sub(numeric["high"], axis=0) > 0).any().any():
        warnings.append("high_below_open_or_close")
    if (numeric["low"].sub(numeric.loc[:, ["open", "close"]].min(axis=1)) > 0).any():
        warnings.append("low_above_open_or_close")
    if (numeric["high"] < numeric["low"]).any():
        failures.append("high_below_low")
    returns = numeric["close"].pct_change()
    abnormal = int((returns.abs() > 0.50).sum())
    if abnormal:
        warnings.append("abnormal_close_return_gt_50pct")
    report = {
        "rows": int(len(frame)),
        "start": str(dates.min().date()) if dates.notna().any() else None,
        "end": str(dates.max().date()) if dates.notna().any() else None,
        "duplicate_dates": int(dates.duplicated().sum()),
        "abnormal_close_return_count_gt_50pct": abnormal,
        "failures": failures,
        "warnings": warnings,
        "status": "failed" if failures else "passed",
    }
    if failures:
        raise ValueError(f"price quality gate failed: {failures}")
    return report


def audit_factor_directions(
    frame: pd.DataFrame,
    factors: Iterable[str],
    *,
    horizon: int = 20,
) -> pd.DataFrame:
    """Compute pooled diagnostics for raw, inverse and lagged factor views."""
    result = frame.copy()
    future_return = result["close"].shift(-horizon) / result["close"] - 1.0
    rows: list[dict[str, object]] = []
    for factor in factors:
        values = pd.to_numeric(result[factor], errors="coerce")
        for view, signal in (
            ("raw", values),
            ("inverse", -values),
            ("lagged_1", values.shift(1)),
        ):
            valid = pd.concat([signal.rename("signal"), future_return.rename("target")], axis=1).dropna()
            if len(valid) < 3 or valid["signal"].nunique() < 2:
                rows.append({"factor": factor, "view": view, "observations": int(len(valid)), "ic": np.nan, "rank_ic": np.nan, "sign_hit_rate": np.nan})
                continue
            rows.append({
                "factor": factor,
                "view": view,
                "observations": int(len(valid)),
                "ic": float(valid["signal"].corr(valid["target"])),
                "rank_ic": float(valid["signal"].rank().corr(valid["target"].rank())),
                "sign_hit_rate": float((np.sign(valid["signal"]) == np.sign(valid["target"])).mean()),
            })
    return pd.DataFrame(rows)


def redundancy_matrix(frame: pd.DataFrame, factors: Iterable[str]) -> pd.DataFrame:
    """Return Pearson and Spearman redundancy matrices in a long format."""
    values = frame.loc[:, list(factors)].apply(pd.to_numeric, errors="coerce")
    rows = []
    for left_index, left in enumerate(values.columns):
        left_values = values.iloc[:, left_index]
        for right_index, right in enumerate(values.columns):
            right_values = values.iloc[:, right_index]
            pair = pd.concat([left_values, right_values], axis=1).dropna()
            rows.append({
                "factor_left": str(left),
                "factor_right": str(right),
                "observations": int(len(pair)),
                "pearson": float(pair.iloc[:, 0].corr(pair.iloc[:, 1])) if len(pair) > 2 else np.nan,
                "spearman": float(pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())) if len(pair) > 2 else np.nan,
            })
    return pd.DataFrame(rows)


__all__ = ["audit_factor_directions", "redundancy_matrix", "validate_price_frame"]
