"""
News sentiment fusion for the single-stock search path.

The module consumes the cross-project CSV produced by FinGPT-github and applies
an optional residual-gated news adjustment on top of the existing technical
factor score. It keeps the original ``factor_score`` column intact and writes
the adjusted value to ``fused_factor_score``.
"""

from __future__ import annotations

import os
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
REQUIRED_NEWS_COLUMNS = (
    "symbol",
    "date",
    "news_count",
    "sentiment_ewm_3",
    "confidence_mean",
)
TECHNICAL_PROXY_COLUMNS = ("mom_short_z", "mom_long_z", "macd_z", "rsi_z")


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
    thresholds = [
        high,
        max(mid, high - 0.10),
        mid,
        max(0.0, mid - 0.10),
        max(0.0, mid - 0.20),
    ]
    return np.select(
        [
            factor_percentile >= thresholds[0],
            factor_percentile >= thresholds[1],
            factor_percentile >= thresholds[2],
            factor_percentile >= thresholds[3],
            factor_percentile >= thresholds[4],
        ],
        [1.0, 0.8, 0.6, 0.4, 0.2],
        default=0.0,
    ).astype(float)


def _refresh_trade_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
    target_position = pd.to_numeric(df["target_position"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    previous_position = target_position.shift(1)
    if len(previous_position) > 0:
        previous_position.iloc[0] = target_position.iloc[0]
    previous_position = previous_position.fillna(0.0)
    out = df.copy()
    out["target_position"] = target_position
    out["buy_signal"] = (target_position > 0) & (previous_position <= 0)
    out["sell_signal"] = (target_position <= 0) & (previous_position > 0)
    return out


def load_news_factor_csv(path: str | Path, *, symbol: str | None = None) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"news factor CSV not found: {csv_path}")

    news = pd.read_csv(csv_path)
    missing = [column for column in REQUIRED_NEWS_COLUMNS if column not in news.columns]
    if missing:
        raise ValueError(f"news factor CSV missing columns: {', '.join(missing)}")

    news = news.copy()
    news["symbol"] = news["symbol"].astype(str).str.strip().str.upper()
    news["date"] = pd.to_datetime(news["date"], errors="coerce").dt.normalize()
    news = news.dropna(subset=["date"])
    if symbol:
        news = news.loc[news["symbol"] == str(symbol).strip().upper()].copy()
    return news


def _merge_news_to_signal_df(
    full_signal_df: pd.DataFrame,
    news: pd.DataFrame,
    *,
    symbol: str | None,
) -> tuple[pd.DataFrame, int]:
    out = full_signal_df.copy()
    if "date" not in out.columns:
        raise ValueError("News Fusion requires full_signal_df to contain a date column")
    out["_news_merge_date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()

    if symbol:
        news_for_merge = news.loc[news["symbol"] == str(symbol).strip().upper()].copy()
        merge_keys_left = ["_news_merge_date"]
        merge_keys_right = ["date"]
    elif "symbol" in out.columns:
        out["_news_merge_symbol"] = out["symbol"].astype(str).str.strip().str.upper()
        news_for_merge = news.copy()
        merge_keys_left = ["_news_merge_symbol", "_news_merge_date"]
        merge_keys_right = ["symbol", "date"]
    elif news["symbol"].nunique(dropna=True) <= 1:
        news_for_merge = news.copy()
        merge_keys_left = ["_news_merge_date"]
        merge_keys_right = ["date"]
    else:
        raise ValueError("News Fusion needs a symbol when news CSV contains multiple symbols")

    news_columns = [
        "symbol",
        "date",
        "news_count",
        "sentiment_ewm_3",
        "confidence_mean",
        "negative_tail_ratio",
        "sentiment_mean",
        "sentiment_sum",
    ]
    news_for_merge = news_for_merge[[column for column in news_columns if column in news_for_merge.columns]].copy()
    merged = out.merge(
        news_for_merge,
        how="left",
        left_on=merge_keys_left,
        right_on=merge_keys_right,
        suffixes=("", "_news"),
    )
    matched_rows = int(merged["sentiment_ewm_3"].notna().sum())
    return merged.drop(columns=[column for column in ("_news_merge_date", "_news_merge_symbol") if column in merged.columns]), matched_rows


def _estimate_proxy_beta(merged: pd.DataFrame, split_idx: int) -> dict[str, float]:
    train = merged.iloc[: max(0, int(split_idx))].copy()
    required = [*TECHNICAL_PROXY_COLUMNS, "news_sentiment_z"]
    valid = train[required].replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) < len(TECHNICAL_PROXY_COLUMNS) + 2:
        return {column: 0.0 for column in TECHNICAL_PROXY_COLUMNS}

    x = valid.loc[:, TECHNICAL_PROXY_COLUMNS].to_numpy(dtype=float)
    y = valid["news_sentiment_z"].to_numpy(dtype=float)
    try:
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    except np.linalg.LinAlgError:
        beta = np.zeros(len(TECHNICAL_PROXY_COLUMNS), dtype=float)
    return {column: float(value) for column, value in zip(TECHNICAL_PROXY_COLUMNS, beta)}


def apply_news_fusion(
    full_signal_df: pd.DataFrame,
    *,
    news_factor_path: str | Path,
    symbol: str | None = None,
    news_weight: float = 0.4,
    news_lookback: int = 20,
    split_idx: int | None = None,
    score_mid_pct: float = 0.60,
    score_high_pct: float = 0.80,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if NEWS_FUSION_MODE != "residual_gate":
        raise ValueError("Only residual_gate news fusion is supported in v1")
    if "factor_score" not in full_signal_df.columns:
        raise ValueError("News Fusion requires factor_score in full_signal_df")

    news = load_news_factor_csv(news_factor_path, symbol=symbol)
    merged, matched_rows = _merge_news_to_signal_df(full_signal_df, news, symbol=symbol)
    lookback = max(2, int(news_lookback))
    split = len(merged) if split_idx is None else int(split_idx)

    merged["news_count"] = pd.to_numeric(merged.get("news_count"), errors="coerce").fillna(0.0)
    merged["confidence_mean"] = pd.to_numeric(merged.get("confidence_mean"), errors="coerce").fillna(0.0)
    merged["news_raw"] = pd.to_numeric(merged.get("sentiment_ewm_3"), errors="coerce")
    merged["news_sentiment_z"] = rolling_zscore(merged["news_raw"], lookback)
    merged["news_count_z"] = rolling_zscore(merged["news_count"], lookback)

    beta = _estimate_proxy_beta(merged, split)
    technical_proxy = pd.Series(0.0, index=merged.index, dtype=float)
    for column, value in beta.items():
        technical_proxy += pd.to_numeric(merged.get(column), errors="coerce").fillna(0.0) * float(value)
    merged["news_technical_proxy"] = technical_proxy
    merged["news_residual"] = pd.to_numeric(merged["news_sentiment_z"], errors="coerce").fillna(0.0) - technical_proxy
    gate_input = (
        0.8 * merged["news_residual"].abs()
        + 0.4 * pd.to_numeric(merged["news_count_z"], errors="coerce").fillna(0.0)
        + 0.4 * merged["confidence_mean"]
    )
    merged["news_gate"] = _sigmoid(gate_input)

    has_news = pd.to_numeric(merged.get("sentiment_ewm_3"), errors="coerce").notna()
    merged["news_delta"] = float(news_weight) * merged["news_gate"] * merged["news_residual"]
    merged.loc[~has_news, "news_delta"] = 0.0
    if float(news_weight) == 0.0:
        merged["news_delta"] = 0.0

    merged["fused_factor_score"] = pd.to_numeric(merged["factor_score"], errors="coerce").fillna(0.0) + merged["news_delta"]
    if float(news_weight) == 0.0:
        merged["factor_percentile"] = pd.to_numeric(full_signal_df.get("factor_percentile"), errors="coerce").fillna(0.0).to_numpy()
        merged["target_position"] = pd.to_numeric(full_signal_df.get("target_position"), errors="coerce").fillna(0.0).to_numpy()
    else:
        merged["factor_percentile"] = rolling_percentile(merged["fused_factor_score"], lookback).fillna(
            pd.to_numeric(merged.get("factor_percentile"), errors="coerce").fillna(0.0)
        )
        merged["target_position"] = _score_position_from_percentile(
            merged["factor_percentile"],
            score_mid_pct=score_mid_pct,
            score_high_pct=score_high_pct,
        )
        merged.loc[~has_news, "target_position"] = pd.to_numeric(
            full_signal_df.get("target_position"),
            errors="coerce",
        ).fillna(0.0).to_numpy()

    fused = _refresh_trade_signal_columns(merged)
    metadata = {
        "news_rows_loaded": int(len(news)),
        "news_rows_matched": int(matched_rows),
        "news_coverage_ratio": float(matched_rows / len(full_signal_df)) if len(full_signal_df) else 0.0,
        "news_weight": float(news_weight),
        "news_lookback": int(lookback),
        "news_fusion_mode": NEWS_FUSION_MODE,
        "news_factor_path": str(news_factor_path),
        "news_symbol": str(symbol).strip().upper() if symbol else None,
        "news_beta": beta,
    }
    return fused, metadata


__all__ = [
    "DEFAULT_NEWS_FACTOR_PATH",
    "NEWS_FUSION_MODE",
    "apply_news_fusion",
    "load_news_factor_csv",
]
