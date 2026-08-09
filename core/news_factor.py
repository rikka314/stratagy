"""News sentiment validation, leakage-safe fusion, and ablation helpers.

The input CSV is a daily, symbol-level factor produced outside this repository.
``date`` always denotes the information date, not the trade date.  Fusion maps
each row to a later signal-row date using an explicit trading-day lag, so a
same-day news value can never affect a same-day position.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.indicators import rolling_percentile, rolling_zscore


DEFAULT_NEWS_FACTOR_PATH = os.environ.get(
    "STRATAGY_NEWS_FACTOR_PATH",
    r"D:\Learn\20_Projects\FinGPT-github\student_local\outputs\news_sentiment_daily.csv",
)
NEWS_FUSION_MODE = "residual_gate"
DEFAULT_NEWS_AVAILABLE_LAG_TRADING_DAYS = 1
REQUIRED_NEWS_COLUMNS = (
    "symbol",
    "date",
    "news_count",
    "sentiment_ewm_3",
    "confidence_mean",
)
TECHNICAL_PROXY_COLUMNS = ("mom_short_z", "mom_long_z", "macd_z", "rsi_z")
_CN_A_SYMBOL_PATTERN = re.compile(r"^(?:(?:SH|SZ|BJ))?(\d{6})(?:\.(?:SH|SZ|BJ))?$")
NEWS_ABLATION_COLUMNS = (
    "market",
    "base_strategy_id",
    "news_weight",
    "lookback_days",
    "symbol_count",
    "matched_row_count",
    "coverage_rate",
    "missing_rate",
    "future_leakage_violation_count",
    "duplicate_news_row_count",
    "fallback_position_match_rate",
    "total_return",
    "max_drawdown",
    "sharpe",
    "total_turnover",
    "total_transaction_cost",
    "net_total_return",
    "rolling_direction_consistency",
    "status",
    "skip_reason",
)


def normalize_news_market(market: str | None) -> str | None:
    """Return the canonical research market, accepting the frozen aliases."""
    if market is None or not str(market).strip():
        return None
    normalized = str(market).strip().upper()
    aliases = {"US": "US", "CN_A": "CN_A", "CN": "CN_A", "A": "CN_A"}
    if normalized not in aliases:
        raise ValueError(f"unsupported news market: {market!r}")
    return aliases[normalized]


def normalize_news_symbol(symbol: object, *, market: str | None = None) -> str:
    """Normalize US symbols and common A-share forms without dropping leading zeros."""
    if symbol is None or pd.isna(symbol):
        return ""
    raw = str(symbol).strip().upper()
    canonical_market = normalize_news_market(market)
    if canonical_market == "CN_A":
        # ``read_csv(dtype={"symbol": "string"})`` preserves canonical codes.
        # The numeric branches additionally make direct DataFrame callers safe.
        if re.fullmatch(r"\d+(?:\.0+)?", raw):
            return str(int(float(raw))).zfill(6)
        match = _CN_A_SYMBOL_PATTERN.fullmatch(raw)
        if match:
            return match.group(1)
    elif canonical_market is None:
        match = _CN_A_SYMBOL_PATTERN.fullmatch(raw)
        if match:
            return match.group(1)
    return raw


def _resolve_market(market: str | None, symbol: str | None, news: pd.DataFrame | None = None) -> str:
    canonical = normalize_news_market(market)
    if canonical:
        return canonical
    if news is not None and "market" in news.columns:
        values = [normalize_news_market(value) for value in news["market"].dropna().unique() if str(value).strip()]
        values = [value for value in values if value]
        if len(set(values)) == 1:
            return values[0]
        if len(set(values)) > 1:
            raise ValueError("news fusion requires one market per invocation")
    if news is not None and "symbol" in news.columns:
        inferred = {
            "CN_A"
            if len(normalize_news_symbol(value, market="CN_A")) == 6
            and normalize_news_symbol(value, market="CN_A").isdigit()
            else "US"
            for value in news["symbol"].dropna().unique()
        }
        if len(inferred) == 1:
            return inferred.pop()
        if len(inferred) > 1:
            raise ValueError("news fusion requires one market per invocation")
    candidate = str(symbol or "").strip().upper()
    normalized_candidate = normalize_news_symbol(candidate, market="CN_A")
    return "CN_A" if normalized_candidate.isdigit() and len(normalized_candidate) == 6 else "US"


def _canonicalize_market_column(out: pd.DataFrame, explicit_market: str | None) -> pd.Series:
    """Canonicalize row markets while allowing one CSV to contain both markets."""
    if "market" in out.columns:
        raw_market = out["market"].astype("string").fillna("").str.strip()
        unknown = sorted(
            {
                str(value)
                for value in raw_market.loc[raw_market != ""].unique()
                if str(value).strip().upper() not in {"US", "CN_A", "CN", "A"}
            }
        )
        if unknown:
            raise ValueError(f"unsupported news market values: {', '.join(unknown)}")
        canonical = raw_market.map(lambda value: normalize_news_market(value) if value else None)
    else:
        canonical = pd.Series(None, index=out.index, dtype="object")

    if explicit_market:
        canonical = canonical.fillna(explicit_market)
    unresolved = canonical.isna()
    if unresolved.any():
        canonical.loc[unresolved] = out.loc[unresolved, "symbol"].map(
            lambda value: "CN_A"
            if len(normalize_news_symbol(value, market="CN_A")) == 6
            and normalize_news_symbol(value, market="CN_A").isdigit()
            else "US"
        )
    return canonical.astype("string")


def validate_news_factor_frame(
    news: pd.DataFrame,
    *,
    market: str | None = None,
    as_of_date: object | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate and normalize a raw news frame without silently fabricating data.

    Duplicate daily factors are deterministically collapsed to the last CSV row.
    Diagnostics retain their count; callers can surface the data-quality issue.
    """
    missing = [column for column in REQUIRED_NEWS_COLUMNS if column not in news.columns]
    if missing:
        raise ValueError(f"news factor CSV missing columns: {', '.join(missing)}")

    out = news.copy()
    explicit_market = normalize_news_market(market)
    input_rows = len(out)
    out["market"] = _canonicalize_market_column(out, explicit_market)
    out["symbol"] = [
        normalize_news_symbol(symbol, market=row_market)
        for symbol, row_market in zip(out["symbol"], out["market"])
    ]
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    invalid_date_count = int(out["date"].isna().sum())
    empty_symbol_count = int((out["symbol"] == "").sum())
    out = out.dropna(subset=["date"])
    out = out.loc[out["symbol"] != ""].copy()

    # Quality diagnostics describe every valid input row, including rows later
    # collapsed as duplicates, so the source issue remains auditable.
    sentiment = pd.to_numeric(out["sentiment_ewm_3"], errors="coerce")
    confidence = pd.to_numeric(out["confidence_mean"], errors="coerce")
    news_count = pd.to_numeric(out["news_count"], errors="coerce")
    reference_date = (
        pd.Timestamp(as_of_date).tz_localize(None).normalize()
        if as_of_date is not None
        else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    )
    duplicate_mask = out.duplicated(subset=["market", "symbol", "date"], keep="last")
    duplicate_news_row_count = int(duplicate_mask.sum())
    diagnostics = {
        "news_rows_input": int(input_rows),
        "news_rows_valid": int(len(out)),
        "invalid_date_count": invalid_date_count,
        "empty_symbol_count": empty_symbol_count,
        "duplicate_news_row_count": duplicate_news_row_count,
        "missing_sentiment_count": int(sentiment.isna().sum()),
        "missing_confidence_count": int(confidence.isna().sum()),
        "missing_news_count_count": int(news_count.isna().sum()),
        "sentiment_outlier_count": int((sentiment.abs() > 1.0).sum()),
        "confidence_outlier_count": int(((confidence < 0.0) | (confidence > 1.0)).sum()),
        "negative_news_count_count": int((news_count < 0.0).sum()),
        "future_information_date_count": int((out["date"] > reference_date).sum()),
        "validation_as_of_date": reference_date.date().isoformat(),
        "markets": sorted(str(value) for value in out["market"].dropna().unique()),
    }
    out = out.loc[~duplicate_mask].copy()
    out["news_count"] = news_count.loc[out.index]
    out["sentiment_ewm_3"] = sentiment.loc[out.index]
    out["confidence_mean"] = confidence.loc[out.index]
    out["news_information_date"] = out["date"]
    diagnostics["news_rows_after_validation"] = int(len(out))
    diagnostics["market"] = diagnostics["markets"][0] if len(diagnostics["markets"]) == 1 else "MIXED"
    return out.reset_index(drop=True), diagnostics


def load_news_factor_csv(
    path: str | Path,
    *,
    symbol: str | None = None,
    market: str | None = None,
    return_diagnostics: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, Any]]:
    """Load a schema-checked CSV; keep the DataFrame-only legacy return by default."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"news factor CSV not found: {csv_path}")
    raw_news = pd.read_csv(csv_path, dtype={"symbol": "string", "market": "string"})
    resolved_market = normalize_news_market(market)
    if resolved_market is None and symbol:
        resolved_market = _resolve_market(None, symbol)
    news, diagnostics = validate_news_factor_frame(raw_news, market=resolved_market)
    if resolved_market:
        news = news.loc[news["market"] == resolved_market].copy()
    diagnostics["news_rows_after_market_filter"] = int(len(news))
    if symbol:
        normalized_symbol = normalize_news_symbol(symbol, market=resolved_market)
        news = news.loc[news["symbol"] == normalized_symbol].copy()
    diagnostics["news_rows_after_symbol_filter"] = int(len(news))
    if return_diagnostics:
        return news, diagnostics
    return news


def _align_news_to_trading_dates(
    news: pd.DataFrame,
    trading_dates: pd.Series,
    *,
    available_lag_trading_days: int,
) -> tuple[pd.DataFrame, int]:
    if available_lag_trading_days < 1:
        raise ValueError("news_available_lag_trading_days must be at least 1 to prevent future leakage")
    dates = pd.to_datetime(trading_dates, errors="coerce").dropna().dt.normalize()
    unique_dates = pd.DatetimeIndex(dates.unique()).sort_values()
    if unique_dates.empty:
        raise ValueError("News Fusion requires at least one valid signal date")

    out = news.copy()
    out["_news_source_order"] = np.arange(len(out), dtype=int)
    information_dates = pd.to_datetime(out["news_information_date"], errors="coerce").dt.normalize()
    indices = unique_dates.searchsorted(information_dates.to_numpy(), side="left") + int(available_lag_trading_days)
    effective = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
    valid = indices < len(unique_dates)
    if valid.any():
        effective.loc[valid] = unique_dates.take(indices[valid]).to_numpy()
    out["news_effective_date"] = effective
    out = out.dropna(subset=["news_effective_date"]).copy()
    # Weekend/holiday information rows can share the same first eligible trade
    # date. Keep the latest source row so a left merge remains one-to-one and
    # cannot duplicate the signal frame.
    out = out.sort_values(
        ["market", "symbol", "news_effective_date", "news_information_date", "_news_source_order"],
        kind="stable",
    )
    effective_duplicate_mask = out.duplicated(
        subset=["market", "symbol", "news_effective_date"], keep="last"
    )
    effective_duplicate_count = int(effective_duplicate_mask.sum())
    return out.loc[~effective_duplicate_mask].drop(columns="_news_source_order").copy(), effective_duplicate_count


def _sigmoid(value: pd.Series) -> pd.Series:
    clipped = pd.to_numeric(value, errors="coerce").fillna(0.0).clip(lower=-30.0, upper=30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _score_position_from_percentile(
    factor_percentile: pd.Series,
    *,
    score_mid_pct: float,
    score_high_pct: float,
) -> np.ndarray:
    mid = float(score_mid_pct)
    high = float(score_high_pct)
    thresholds = [high, max(mid, high - 0.10), mid, max(0.0, mid - 0.10), max(0.0, mid - 0.20)]
    return np.select(
        [factor_percentile >= threshold for threshold in thresholds],
        [1.0, 0.8, 0.6, 0.4, 0.2],
        default=0.0,
    ).astype(float)


def _refresh_trade_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
    target_position = pd.to_numeric(df["target_position"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    if "symbol" in df.columns:
        symbol_keys = df["symbol"].astype("string").fillna("")
        previous_position = target_position.groupby(symbol_keys, sort=False).shift(1)
        previous_position = previous_position.fillna(target_position)
    else:
        previous_position = target_position.shift(1)
        if len(previous_position) > 0:
            previous_position.iloc[0] = target_position.iloc[0]
        previous_position = previous_position.fillna(0.0)
    out = df.copy()
    out["target_position"] = target_position
    out["buy_signal"] = (target_position > 0) & (previous_position <= 0)
    out["sell_signal"] = (target_position <= 0) & (previous_position > 0)
    return out


def _merge_news_to_signal_df(
    full_signal_df: pd.DataFrame,
    news: pd.DataFrame,
    *,
    symbol: str | None,
    market: str,
    available_lag_trading_days: int,
) -> tuple[pd.DataFrame, int, int, int]:
    out = full_signal_df.copy()
    if "date" not in out.columns:
        raise ValueError("News Fusion requires full_signal_df to contain a date column")
    out["_news_merge_date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    if out["_news_merge_date"].isna().any():
        raise ValueError("News Fusion received invalid signal dates")
    out["_news_row_order"] = np.arange(len(out), dtype=int)
    out["_news_upstream_position"] = pd.to_numeric(out["target_position"], errors="coerce").fillna(0.0)
    out["_news_upstream_percentile"] = pd.to_numeric(out["factor_percentile"], errors="coerce").fillna(0.0)
    effective_duplicate_count = 0
    if symbol:
        normalized_symbol = normalize_news_symbol(symbol, market=market)
        symbol_news = news.loc[news["symbol"] == normalized_symbol].copy()
        news_for_merge, effective_duplicate_count = _align_news_to_trading_dates(
            symbol_news,
            out["_news_merge_date"],
            available_lag_trading_days=available_lag_trading_days,
        )
        merge_keys_left, merge_keys_right = ["_news_merge_date"], ["news_effective_date"]
    elif "symbol" in out.columns:
        out["_news_merge_symbol"] = out["symbol"].map(lambda value: normalize_news_symbol(value, market=market))
        aligned_parts: list[pd.DataFrame] = []
        for normalized_symbol, signal_rows in out.groupby("_news_merge_symbol", sort=False):
            symbol_news = news.loc[news["symbol"] == normalized_symbol].copy()
            if symbol_news.empty:
                continue
            aligned_part, collision_count = _align_news_to_trading_dates(
                symbol_news,
                signal_rows["_news_merge_date"],
                available_lag_trading_days=available_lag_trading_days,
            )
            aligned_parts.append(aligned_part)
            effective_duplicate_count += collision_count
        if aligned_parts:
            news_for_merge = pd.concat(aligned_parts, ignore_index=True)
        else:
            news_for_merge = news.iloc[0:0].copy()
            news_for_merge["news_effective_date"] = pd.Series(dtype="datetime64[ns]")
        merge_keys_left = ["_news_merge_symbol", "_news_merge_date"]
        merge_keys_right = ["symbol", "news_effective_date"]
    elif news["symbol"].nunique(dropna=True) <= 1:
        news_for_merge, effective_duplicate_count = _align_news_to_trading_dates(
            news,
            out["_news_merge_date"],
            available_lag_trading_days=available_lag_trading_days,
        )
        merge_keys_left, merge_keys_right = ["_news_merge_date"], ["news_effective_date"]
    else:
        raise ValueError("News Fusion needs a symbol when news CSV contains multiple symbols")

    news_columns = [
        "symbol", "news_information_date", "news_effective_date", "news_count", "sentiment_ewm_3",
        "confidence_mean", "negative_tail_ratio", "sentiment_mean", "sentiment_sum",
    ]
    news_for_merge = news_for_merge[
        [column for column in news_columns if column in news_for_merge.columns]
    ].copy()
    merged = out.merge(
        news_for_merge,
        how="left",
        left_on=merge_keys_left,
        right_on=merge_keys_right,
        suffixes=("", "_news"),
    )
    merged = merged.sort_values("_news_row_order", kind="stable").reset_index(drop=True)
    matched_rows = int(merged["sentiment_ewm_3"].notna().sum())
    future_leakage_violation_count = int(
        (
            merged["news_information_date"].notna()
            & (merged["news_information_date"] >= merged["_news_merge_date"])
        ).sum()
    )
    if future_leakage_violation_count:
        raise RuntimeError("news alignment produced a future-leakage violation")
    return (
        merged.drop(
            columns=[
                column
                for column in ("_news_merge_date", "_news_merge_symbol", "_news_row_order")
                if column in merged.columns
            ]
        ),
        matched_rows,
        future_leakage_violation_count,
        effective_duplicate_count,
    )


def _estimate_proxy_beta(merged: pd.DataFrame, split_idx: int) -> dict[str, float]:
    train = merged.iloc[: max(0, int(split_idx))].copy()
    required = [*TECHNICAL_PROXY_COLUMNS, "news_sentiment_z"]
    # A custom upstream signal frame may omit the technical proxy diagnostics.
    # Treat that case as an unavailable residual model rather than failing the
    # no-news fallback path; canonical search signals still provide all columns.
    valid = train.reindex(columns=required).replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) < len(TECHNICAL_PROXY_COLUMNS) + 2:
        return {column: 0.0 for column in TECHNICAL_PROXY_COLUMNS}
    try:
        beta, *_ = np.linalg.lstsq(
            valid.loc[:, TECHNICAL_PROXY_COLUMNS].to_numpy(dtype=float),
            valid["news_sentiment_z"].to_numpy(dtype=float),
            rcond=None,
        )
    except np.linalg.LinAlgError:
        beta = np.zeros(len(TECHNICAL_PROXY_COLUMNS), dtype=float)
    return {column: float(value) for column, value in zip(TECHNICAL_PROXY_COLUMNS, beta)}


def _rolling_by_symbol(
    frame: pd.DataFrame,
    values: pd.Series,
    function: Callable[[pd.Series, int], pd.Series],
    window: int,
) -> pd.Series:
    """Apply a rolling transform without allowing one symbol to affect another."""
    if "symbol" not in frame.columns:
        return function(values, window)
    keys = frame["symbol"].astype("string").fillna("")
    return values.groupby(keys, sort=False, group_keys=False).transform(lambda group: function(group, window))


def apply_news_fusion(
    full_signal_df: pd.DataFrame,
    *,
    news_factor_path: str | Path,
    symbol: str | None = None,
    market: str | None = None,
    news_weight: float = 0.4,
    news_lookback: int = 20,
    news_available_lag_trading_days: int = DEFAULT_NEWS_AVAILABLE_LAG_TRADING_DAYS,
    split_idx: int | None = None,
    score_mid_pct: float = 0.60,
    score_high_pct: float = 0.80,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply a leakage-safe residual news adjustment to a search signal frame."""
    if NEWS_FUSION_MODE != "residual_gate":
        raise ValueError("Only residual_gate news fusion is supported in v1")
    required_signal_columns = ("date", "factor_score", "factor_percentile", "target_position")
    missing_signal_columns = [column for column in required_signal_columns if column not in full_signal_df.columns]
    if missing_signal_columns:
        raise ValueError(f"News Fusion missing signal columns: {', '.join(missing_signal_columns)}")
    if not np.isfinite(float(news_weight)) or float(news_weight) < 0.0:
        raise ValueError("news_weight must be a finite non-negative number")
    lookback = int(news_lookback)
    if lookback < 2:
        raise ValueError("news_lookback must be at least 2")
    lag = int(news_available_lag_trading_days)
    if lag < 1:
        raise ValueError("news_available_lag_trading_days must be at least 1 to prevent future leakage")
    split = len(full_signal_df) if split_idx is None else int(split_idx)
    if split < 0 or split > len(full_signal_df):
        raise ValueError("split_idx must be between 0 and the signal-frame length")

    resolved_market = _resolve_market(market, symbol, full_signal_df)
    news, diagnostics = load_news_factor_csv(
        news_factor_path, symbol=symbol, market=resolved_market, return_diagnostics=True
    )
    merged, matched_rows, leakage_count, effective_duplicate_count = _merge_news_to_signal_df(
        full_signal_df,
        news,
        symbol=symbol,
        market=resolved_market,
        available_lag_trading_days=lag,
    )
    merged["news_count"] = pd.to_numeric(merged.get("news_count"), errors="coerce").fillna(0.0)
    merged["confidence_mean"] = pd.to_numeric(merged.get("confidence_mean"), errors="coerce").fillna(0.0)
    merged["news_raw"] = pd.to_numeric(merged.get("sentiment_ewm_3"), errors="coerce")
    merged["news_sentiment_z"] = _rolling_by_symbol(merged, merged["news_raw"], rolling_zscore, lookback)
    merged["news_count_z"] = _rolling_by_symbol(merged, merged["news_count"], rolling_zscore, lookback)
    beta = _estimate_proxy_beta(merged, split)
    technical_proxy = pd.Series(0.0, index=merged.index, dtype=float)
    for column, value in beta.items():
        if column in merged.columns:
            technical_proxy += pd.to_numeric(merged[column], errors="coerce").fillna(0.0) * float(value)
    merged["news_technical_proxy"] = technical_proxy
    merged["news_residual"] = pd.to_numeric(merged["news_sentiment_z"], errors="coerce").fillna(0.0) - technical_proxy
    merged["news_gate"] = _sigmoid(
        0.8 * merged["news_residual"].abs()
        + 0.4 * pd.to_numeric(merged["news_count_z"], errors="coerce").fillna(0.0)
        + 0.4 * merged["confidence_mean"]
    )
    has_news = pd.to_numeric(merged.get("sentiment_ewm_3"), errors="coerce").notna()
    merged["news_delta"] = float(news_weight) * merged["news_gate"] * merged["news_residual"]
    merged.loc[~has_news, "news_delta"] = 0.0
    if float(news_weight) == 0.0:
        merged["news_delta"] = 0.0
    merged["fused_factor_score"] = (
        pd.to_numeric(merged["factor_score"], errors="coerce").fillna(0.0)
        + merged["news_delta"]
    )
    upstream_position = merged["_news_upstream_position"].to_numpy(dtype=float)
    if float(news_weight) == 0.0:
        merged["factor_percentile"] = merged["_news_upstream_percentile"].to_numpy(dtype=float)
        merged["target_position"] = upstream_position
    else:
        merged["factor_percentile"] = _rolling_by_symbol(
            merged, merged["fused_factor_score"], rolling_percentile, lookback
        ).fillna(
            merged["_news_upstream_percentile"]
        )
        merged["target_position"] = _score_position_from_percentile(
            merged["factor_percentile"], score_mid_pct=score_mid_pct, score_high_pct=score_high_pct
        )
        # The Gate-0 repair: no-news rows retain the upstream strategy position.
        merged.loc[~has_news, "target_position"] = upstream_position[~has_news.to_numpy()]
    fused = _refresh_trade_signal_columns(merged).drop(
        columns=["_news_upstream_position", "_news_upstream_percentile"]
    )
    information_dates = fused["news_information_date"].dropna()
    effective_dates = fused["news_effective_date"].dropna()
    metadata = {
        **diagnostics,
        "news_rows_loaded": int(len(news)),
        "news_rows_matched": int(matched_rows),
        "news_coverage_ratio": float(matched_rows / len(full_signal_df)) if len(full_signal_df) else 0.0,
        "news_missing_ratio": float(1.0 - matched_rows / len(full_signal_df)) if len(full_signal_df) else 0.0,
        "future_leakage_violation_count": int(leakage_count),
        "effective_date_collision_count": int(effective_duplicate_count),
        "duplicate_news_row_count": int(diagnostics["duplicate_news_row_count"] + effective_duplicate_count),
        "news_weight": float(news_weight),
        "news_lookback": int(lookback),
        "news_available_lag_trading_days": lag,
        "news_fusion_mode": NEWS_FUSION_MODE,
        "news_factor_path": str(news_factor_path),
        "news_symbol": normalize_news_symbol(symbol, market=resolved_market) if symbol else None,
        "news_market": resolved_market,
        "news_information_date_min": (
            information_dates.min().date().isoformat() if not information_dates.empty else None
        ),
        "news_information_date_max": (
            information_dates.max().date().isoformat() if not information_dates.empty else None
        ),
        "news_effective_date_min": effective_dates.min().date().isoformat() if not effective_dates.empty else None,
        "news_effective_date_max": effective_dates.max().date().isoformat() if not effective_dates.empty else None,
        "news_beta": beta,
    }
    return fused, metadata


def _default_ablation_metrics(signal_df: pd.DataFrame) -> dict[str, float]:
    if "close" not in signal_df.columns:
        raise ValueError("default news-ablation evaluation requires a close column")
    position = pd.to_numeric(signal_df["target_position"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    close = pd.to_numeric(signal_df["close"], errors="coerce")
    if "symbol" in signal_df.columns:
        keys = signal_df["symbol"].astype("string").fillna("")
        held_position = position.groupby(keys, sort=False).shift(1).fillna(0.0)
        asset_returns = close.groupby(keys, sort=False).pct_change().fillna(0.0)
        row_returns = held_position * asset_returns
        turnover_rows = position.groupby(keys, sort=False).diff().abs().fillna(position.abs())
        if "date" in signal_df.columns:
            dates = pd.to_datetime(signal_df["date"], errors="coerce").dt.normalize()
            daily_returns = row_returns.groupby(dates, sort=True).mean()
        else:
            daily_returns = row_returns
        turnover = float(turnover_rows.sum())
    else:
        daily_returns = position.shift(1).fillna(0.0) * close.pct_change().fillna(0.0)
        turnover = float(position.diff().abs().fillna(position.abs()).sum())
    equity = (1.0 + daily_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    std = float(daily_returns.std(ddof=0))
    sharpe = float(np.sqrt(252) * daily_returns.mean() / std) if std > 0 else 0.0
    return {
        "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "sharpe": sharpe,
        "total_turnover": turnover,
        "total_transaction_cost": 0.0,
        "net_total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "rolling_direction_consistency": np.nan,
    }


def run_news_ablation(
    full_signal_df: pd.DataFrame,
    *,
    news_factor_path: str | Path,
    output_path: str | Path,
    base_strategy_id: str,
    symbol: str | None = None,
    market: str = "US",
    weights: Sequence[float] = (0.0, 0.15, 0.30, 0.45),
    lookbacks: Sequence[int] = (3, 5),
    news_available_lag_trading_days: int = DEFAULT_NEWS_AVAILABLE_LAG_TRADING_DAYS,
    coverage_threshold: float = 0.0,
    split_idx: int | None = None,
    evaluate_fn: Callable[[pd.DataFrame], Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Run a same-input weight × lookback news ablation and write the frozen CSV."""
    if len(weights) == 0 or len(lookbacks) == 0:
        raise ValueError("news ablation requires at least one weight and one lookback")
    if not np.isfinite(float(coverage_threshold)) or not 0.0 <= float(coverage_threshold) <= 1.0:
        raise ValueError("coverage_threshold must be between 0 and 1")
    evaluator = evaluate_fn or _default_ablation_metrics
    rows: list[dict[str, Any]] = []
    symbol_count = (
        1
        if symbol
        else int(full_signal_df["symbol"].dropna().nunique())
        if "symbol" in full_signal_df.columns
        else 1
    )
    for weight in weights:
        for lookback in lookbacks:
            row: dict[str, Any] = {
                "market": _resolve_market(market, symbol), "base_strategy_id": base_strategy_id,
                "news_weight": float(weight), "lookback_days": int(lookback), "symbol_count": symbol_count,
                "status": "success", "skip_reason": "",
            }
            try:
                fused, metadata = apply_news_fusion(
                    full_signal_df.copy(), news_factor_path=news_factor_path, symbol=symbol, market=market,
                    news_weight=float(weight), news_lookback=int(lookback),
                    news_available_lag_trading_days=int(news_available_lag_trading_days), split_idx=split_idx,
                )
                no_news = fused["sentiment_ewm_3"].isna()
                upstream = pd.to_numeric(
                    full_signal_df["target_position"], errors="coerce"
                ).fillna(0.0).reset_index(drop=True)
                fallback_rate = (
                    float(np.isclose(
                        pd.to_numeric(fused.loc[no_news, "target_position"], errors="coerce").to_numpy(),
                        upstream.loc[no_news.to_numpy()].to_numpy(),
                    ).mean())
                    if no_news.any() else 1.0
                )
                row.update({
                    "matched_row_count": metadata["news_rows_matched"],
                    "coverage_rate": metadata["news_coverage_ratio"],
                    "missing_rate": metadata["news_missing_ratio"],
                    "future_leakage_violation_count": metadata["future_leakage_violation_count"],
                    "duplicate_news_row_count": metadata["duplicate_news_row_count"],
                    "fallback_position_match_rate": fallback_rate,
                })
                row.update(dict(evaluator(fused)))
                if metadata["news_rows_matched"] == 0:
                    row.update(status="skipped", skip_reason="no matched news rows")
                elif metadata["news_coverage_ratio"] < float(coverage_threshold):
                    row.update(
                        status="skipped",
                        skip_reason=(
                            f"coverage {metadata['news_coverage_ratio']:.6f} is below "
                            f"threshold {float(coverage_threshold):.6f}"
                        ),
                    )
            except (FileNotFoundError, ValueError, RuntimeError) as exc:
                row.update({
                    "matched_row_count": 0, "coverage_rate": 0.0, "missing_rate": 1.0,
                    "future_leakage_violation_count": 0, "duplicate_news_row_count": 0,
                    "fallback_position_match_rate": np.nan, "total_return": np.nan, "max_drawdown": np.nan,
                    "sharpe": np.nan, "total_turnover": np.nan, "total_transaction_cost": np.nan,
                    "net_total_return": np.nan, "rolling_direction_consistency": np.nan,
                    "status": "skipped", "skip_reason": str(exc),
                })
            rows.append(row)
    result = pd.DataFrame(rows).reindex(columns=NEWS_ABLATION_COLUMNS)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination, index=False, encoding="utf-8")
    return result


__all__ = [
    "DEFAULT_NEWS_AVAILABLE_LAG_TRADING_DAYS", "DEFAULT_NEWS_FACTOR_PATH", "NEWS_ABLATION_COLUMNS",
    "NEWS_FUSION_MODE", "apply_news_fusion", "load_news_factor_csv", "normalize_news_market",
    "normalize_news_symbol", "run_news_ablation", "validate_news_factor_frame",
]
