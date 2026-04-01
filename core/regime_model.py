"""
Regime Switching Model (RSM)
============================
US-only dual-state router that combines stock states, optional SPY market
proxy states, and Mean/Drift anchor policies into a fixed, interpretable
execution regime.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

from core.baselines import drift_target_position, mean_target_position
from core.indicators import add_indicators, rolling_percentile, rolling_rank

RegimeKind = Literal["dual_state_router", "no_market", "no_router"]

DEFAULT_MARKET_PROXY_SYMBOL = "SPY"
_REGIME_LOOKBACK = 60
_REALIZED_VOL_WINDOW = 20
_RELATIVE_RET_WINDOW = 20
_EFFICIENCY_WINDOW = 20
_REGIME_INDICATOR_DEFAULTS = {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_fast": 20,
    "ema_slow": 60,
    "adx_period": 14,
    "atr_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    "indicator_period": 20,
}
_TREND_REGIME = "trend_follow"
_RANGE_REGIME = "range_selective"
_RISK_OFF_REGIME = "risk_off"
_REGIME_ORDER = (_TREND_REGIME, _RANGE_REGIME, _RISK_OFF_REGIME)


def _normalize_date_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last").sort_values("date")
    return out.reset_index(drop=True)


def _ensure_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    required_indicator_columns = {
        "atr",
        "ema_fast",
        "ema_slow",
        "bb_width",
        "volume_ratio",
        "price_position",
        "drawdown",
        "bb_position",
    }
    normalized = _normalize_date_frame(df)
    if required_indicator_columns.issubset(normalized.columns):
        return normalized
    return add_indicators(normalized, **_REGIME_INDICATOR_DEFAULTS)


def _compute_efficiency_ratio(close: pd.Series, window: int) -> pd.Series:
    displacement = close.diff(window).abs()
    travel = close.diff().abs().rolling(window=window, min_periods=window).sum()
    ratio = displacement / travel.replace(0, np.nan)
    return ratio.clip(lower=0.0, upper=1.0)


def _build_feature_frame(df: pd.DataFrame, *, prefix: str = "") -> pd.DataFrame:
    feature_df = _ensure_indicator_frame(df)
    close = pd.to_numeric(feature_df["close"], errors="coerce")
    atr = pd.to_numeric(feature_df["atr"], errors="coerce")
    ema_fast = pd.to_numeric(feature_df["ema_fast"], errors="coerce")
    ema_slow = pd.to_numeric(feature_df["ema_slow"], errors="coerce")

    feature_df[f"{prefix}ret_20"] = close.pct_change(_RELATIVE_RET_WINDOW)
    feature_df[f"{prefix}ret_60"] = close.pct_change(_REGIME_LOOKBACK)
    feature_df[f"{prefix}atr_pct"] = atr / close.replace(0, np.nan)
    feature_df[f"{prefix}atr_pct_percentile"] = rolling_percentile(feature_df[f"{prefix}atr_pct"], _REGIME_LOOKBACK)
    feature_df[f"{prefix}realized_vol_20"] = (
        close.pct_change().rolling(window=_REALIZED_VOL_WINDOW, min_periods=_REALIZED_VOL_WINDOW).std() * np.sqrt(20.0)
    )
    feature_df[f"{prefix}ema_spread_pct"] = (ema_fast - ema_slow) / close.replace(0, np.nan)
    feature_df[f"{prefix}bb_width_rank"] = rolling_rank(pd.to_numeric(feature_df["bb_width"], errors="coerce"), _REGIME_LOOKBACK)
    feature_df[f"{prefix}efficiency_ratio_20"] = _compute_efficiency_ratio(close, _EFFICIENCY_WINDOW)
    feature_df[f"{prefix}volume_ratio_rank"] = rolling_rank(
        pd.to_numeric(feature_df["volume_ratio"], errors="coerce"),
        _REGIME_LOOKBACK,
    )
    feature_df[f"{prefix}price_position_rank"] = rolling_rank(
        pd.to_numeric(feature_df["price_position"], errors="coerce"),
        _REGIME_LOOKBACK,
    )
    feature_df[f"{prefix}drawdown_rank"] = rolling_rank(
        pd.to_numeric(feature_df["drawdown"], errors="coerce"),
        _REGIME_LOOKBACK,
    )
    return feature_df


def _map_trend_state(spread_pct: pd.Series, ret_60: pd.Series) -> pd.Series:
    up = (spread_pct > 0) & (ret_60 > 0.08)
    down = (spread_pct < 0) & (ret_60 < -0.05)
    return pd.Series(
        np.select([up, down], ["Up", "Down"], default="Flat"),
        index=ret_60.index,
        dtype="object",
    )


def _map_vol_state(percentile: pd.Series) -> pd.Series:
    pct = pd.to_numeric(percentile, errors="coerce").fillna(0.5)
    return pd.Series(
        np.select([pct < 0.33, pct >= 0.67], ["Low", "High"], default="Mid"),
        index=pct.index,
        dtype="object",
    )


def _trend_position_from_score(score_percentile: pd.Series) -> np.ndarray:
    pct = pd.to_numeric(score_percentile, errors="coerce").fillna(0.0)
    return np.select(
        [pct >= 0.85, pct >= 0.75, pct >= 0.60],
        [1.0, 0.8, 0.6],
        default=0.0,
    ).astype(float)


def _range_position_from_score(score_percentile: pd.Series) -> np.ndarray:
    pct = pd.to_numeric(score_percentile, errors="coerce").fillna(0.0)
    return np.select(
        [pct >= 0.85, pct >= 0.70],
        [0.6, 0.3],
        default=0.0,
    ).astype(float)


def _refresh_trade_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    target_position = pd.to_numeric(out.get("target_position", 0.0), errors="coerce").fillna(0.0).clip(0.0, 1.0)
    previous_position = target_position.shift(1)
    if len(previous_position) > 0:
        previous_position.iloc[0] = target_position.iloc[0]
    previous_position = previous_position.fillna(0.0)
    out["target_position"] = target_position
    out["buy_signal"] = (target_position > 0) & (previous_position <= 0)
    out["sell_signal"] = (target_position <= 0) & (previous_position > 0)
    return out


def build_market_proxy_frame(
    stock_df: pd.DataFrame,
    *,
    adjust: str = "qfq",
    market_proxy_symbol: str = DEFAULT_MARKET_PROXY_SYMBOL,
    fetcher: Callable[[str, str, str], pd.DataFrame | None] | None = None,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "market_proxy_symbol": market_proxy_symbol,
        "market_proxy_mode": "enabled",
        "market_proxy_unavailable": False,
        "market_proxy_warning": None,
    }
    if fetcher is None:
        from core.utils import load_or_fetch_stock

        fetcher = load_or_fetch_stock

    try:
        proxy_df = fetcher(market_proxy_symbol, adjust, "US")
    except Exception as exc:  # pragma: no cover - defensive fallback
        metadata["market_proxy_unavailable"] = True
        metadata["market_proxy_mode"] = "fallback_stock_only"
        metadata["market_proxy_warning"] = f"market_proxy_unavailable: {exc}"
        return None, metadata

    if proxy_df is None or proxy_df.empty:
        metadata["market_proxy_unavailable"] = True
        metadata["market_proxy_mode"] = "fallback_stock_only"
        metadata["market_proxy_warning"] = "market_proxy_unavailable: SPY data missing"
        return None, metadata

    proxy_frame = _normalize_date_frame(proxy_df)
    if proxy_frame.empty:
        metadata["market_proxy_unavailable"] = True
        metadata["market_proxy_mode"] = "fallback_stock_only"
        metadata["market_proxy_warning"] = "market_proxy_unavailable: SPY data empty after date normalization"
        return None, metadata

    return proxy_frame, metadata


def compute_regime_features(
    df: pd.DataFrame,
    *,
    split_idx: int,
    adjust: str = "qfq",
    regime_kind: RegimeKind = "dual_state_router",
    market_proxy_symbol: str = DEFAULT_MARKET_PROXY_SYMBOL,
    fetcher: Callable[[str, str, str], pd.DataFrame | None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    stock_frame = _build_feature_frame(df)
    metadata: dict[str, Any] = {
        "family": "regime",
        "regime_kind": regime_kind,
        "market_proxy_symbol": market_proxy_symbol,
        "market_proxy_mode": "enabled",
        "market_proxy_unavailable": False,
        "market_proxy_warning": None,
        "warning_messages": [],
    }

    market_feature_frame: pd.DataFrame | None = None
    if regime_kind == "no_market":
        metadata["market_proxy_mode"] = "disabled"
    else:
        market_proxy_df, proxy_metadata = build_market_proxy_frame(
            stock_frame,
            adjust=adjust,
            market_proxy_symbol=market_proxy_symbol,
            fetcher=fetcher,
        )
        metadata.update(proxy_metadata)
        if market_proxy_df is not None:
            market_feature_frame = _build_feature_frame(market_proxy_df, prefix="market_")
            market_feature_frame = (
                market_feature_frame.set_index("date")
                .reindex(stock_frame["date"])
                .ffill()
                .bfill()
                .reset_index()
                .rename(columns={"index": "date"})
            )
            market_columns = [
                "date",
                "market_ret_20",
                "market_ret_60",
                "market_atr_pct",
                "market_atr_pct_percentile",
                "market_realized_vol_20",
                "market_ema_spread_pct",
            ]
            stock_frame = stock_frame.merge(market_feature_frame[market_columns], on="date", how="left")
        elif proxy_metadata.get("market_proxy_warning"):
            metadata["warning_messages"].append(str(proxy_metadata["market_proxy_warning"]))

    stock_frame["stock_trend_state"] = _map_trend_state(stock_frame["ema_spread_pct"], stock_frame["ret_60"])
    stock_frame["stock_vol_state"] = _map_vol_state(stock_frame["atr_pct_percentile"])

    if market_feature_frame is not None:
        stock_frame["market_trend_state"] = _map_trend_state(
            stock_frame["market_ema_spread_pct"],
            stock_frame["market_ret_60"],
        )
        stock_frame["market_vol_state"] = _map_vol_state(stock_frame["market_atr_pct_percentile"])
        stock_frame["rel_market_ret_20"] = (
            pd.to_numeric(stock_frame["ret_20"], errors="coerce")
            - pd.to_numeric(stock_frame["market_ret_20"], errors="coerce")
        )
    else:
        fallback_label = "Disabled" if regime_kind == "no_market" else "ProxyUnavailable"
        stock_frame["market_trend_state"] = fallback_label
        stock_frame["market_vol_state"] = fallback_label
        stock_frame["rel_market_ret_20"] = 0.0

    stock_frame["anchor_mean_position"] = mean_target_position(stock_frame, window=_REGIME_LOOKBACK)
    stock_frame["anchor_drift_position"] = drift_target_position(stock_frame, split_idx=split_idx)

    stock_frame["regime_score"] = (
        0.25 * pd.to_numeric(stock_frame["rel_market_ret_20"], errors="coerce").fillna(0.0)
        + 0.20 * pd.to_numeric(stock_frame["efficiency_ratio_20"], errors="coerce").fillna(0.0)
        + 0.15 * pd.to_numeric(stock_frame["price_position_rank"], errors="coerce").fillna(0.0)
        + 0.15 * pd.to_numeric(stock_frame["volume_ratio_rank"], errors="coerce").fillna(0.0)
        + 0.15 * pd.to_numeric(stock_frame["bb_width_rank"], errors="coerce").fillna(0.0)
        - 0.10 * pd.to_numeric(stock_frame["drawdown_rank"], errors="coerce").fillna(0.0)
    )
    stock_frame["regime_score_percentile"] = rolling_percentile(stock_frame["regime_score"], _REGIME_LOOKBACK).fillna(0.0)

    if regime_kind == "no_router":
        execution_regime = np.select(
            [
                pd.to_numeric(stock_frame["anchor_mean_position"], errors="coerce").fillna(0.0) >= 1.0,
                pd.to_numeric(stock_frame["anchor_drift_position"], errors="coerce").fillna(0.0) >= 1.0,
            ],
            [_TREND_REGIME, _RANGE_REGIME],
            default=_RISK_OFF_REGIME,
        )
    elif market_feature_frame is None:
        execution_regime = np.select(
            [
                (stock_frame["stock_trend_state"] == "Down") | (stock_frame["stock_vol_state"] == "High"),
                (stock_frame["stock_trend_state"] == "Up") & (stock_frame["stock_vol_state"] != "High"),
            ],
            [_RISK_OFF_REGIME, _TREND_REGIME],
            default=_RANGE_REGIME,
        )
    else:
        execution_regime = np.select(
            [
                (stock_frame["market_trend_state"] == "Down")
                | (stock_frame["market_vol_state"] == "High")
                | (stock_frame["stock_trend_state"] == "Down"),
                (stock_frame["market_trend_state"] == "Up")
                & (stock_frame["stock_trend_state"] == "Up")
                & (stock_frame["stock_vol_state"] != "High"),
            ],
            [_RISK_OFF_REGIME, _TREND_REGIME],
            default=_RANGE_REGIME,
        )
    stock_frame["execution_regime"] = pd.Series(execution_regime, index=stock_frame.index, dtype="object")

    trend_position = _trend_position_from_score(stock_frame["regime_score_percentile"])
    range_position = _range_position_from_score(stock_frame["regime_score_percentile"])
    stock_frame["target_position"] = 0.0

    trend_mask = (
        (stock_frame["execution_regime"] == _TREND_REGIME)
        & (pd.to_numeric(stock_frame["anchor_mean_position"], errors="coerce").fillna(0.0) >= 1.0)
    )
    range_mask = (
        (stock_frame["execution_regime"] == _RANGE_REGIME)
        & (pd.to_numeric(stock_frame["anchor_drift_position"], errors="coerce").fillna(0.0) >= 1.0)
    )
    stock_frame.loc[trend_mask, "target_position"] = trend_position[trend_mask.to_numpy(dtype=bool)]
    stock_frame.loc[range_mask, "target_position"] = range_position[range_mask.to_numpy(dtype=bool)]
    stock_frame.loc[stock_frame["execution_regime"] == _RISK_OFF_REGIME, "target_position"] = 0.0

    feature_columns = [
        "ret_20",
        "ret_60",
        "atr_pct",
        "atr_pct_percentile",
        "realized_vol_20",
        "ema_spread_pct",
        "bb_width_rank",
        "efficiency_ratio_20",
        "volume_ratio_rank",
        "price_position_rank",
        "drawdown_rank",
        "rel_market_ret_20",
        "regime_score",
        "regime_score_percentile",
        "anchor_mean_position",
        "anchor_drift_position",
        "stock_trend_state",
        "stock_vol_state",
        "market_trend_state",
        "market_vol_state",
        "execution_regime",
        "target_position",
    ]
    for column in feature_columns:
        if column not in stock_frame.columns:
            stock_frame[column] = np.nan

    return stock_frame, metadata


def compute_regime_signals(
    df: pd.DataFrame,
    *,
    split_idx: int,
    adjust: str = "qfq",
    regime_kind: RegimeKind = "dual_state_router",
    market_proxy_symbol: str = DEFAULT_MARKET_PROXY_SYMBOL,
    fetcher: Callable[[str, str, str], pd.DataFrame | None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    feature_df, metadata = compute_regime_features(
        df,
        split_idx=split_idx,
        adjust=adjust,
        regime_kind=regime_kind,
        market_proxy_symbol=market_proxy_symbol,
        fetcher=fetcher,
    )
    signal_df = _refresh_trade_signal_columns(feature_df)
    return signal_df, metadata


def summarize_regime_diagnostics(
    signal_df: pd.DataFrame,
    *,
    sim_df: pd.DataFrame | None = None,
    market_proxy_symbol: str = DEFAULT_MARKET_PROXY_SYMBOL,
    market_proxy_mode: str = "enabled",
    market_proxy_unavailable: bool = False,
    market_proxy_warning: str | None = None,
) -> dict[str, Any]:
    def _coerce_scalar(value: object, default: float = 0.0) -> float:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.isna(numeric):
            return float(default)
        return float(numeric)

    diagnostics_df = signal_df.copy()
    if sim_df is not None and not sim_df.empty:
        merge_columns = ["date", "execution_regime"]
        if "execution_regime" not in sim_df.columns and "execution_regime" in diagnostics_df.columns:
            sim_df = sim_df.merge(
                diagnostics_df[merge_columns],
                on="date",
                how="left",
            )
        diagnostics_df = sim_df.copy()

    if diagnostics_df.empty or "execution_regime" not in diagnostics_df.columns:
        regime_table = [
            {
                "regime": regime,
                "day_count": 0,
                "day_ratio": 0.0,
                "return_contribution": 0.0,
                "exposure_ratio": 0.0,
            }
            for regime in _REGIME_ORDER
        ]
        return {
            "market_proxy_symbol": market_proxy_symbol,
            "market_proxy_mode": market_proxy_mode,
            "market_proxy_unavailable": market_proxy_unavailable,
            "market_proxy_warning": market_proxy_warning,
            "latest_execution_regime": None,
            "regime_table": regime_table,
            "execution_regime_day_ratio": {row["regime"]: row["day_ratio"] for row in regime_table},
            "execution_regime_return_contribution": {row["regime"]: row["return_contribution"] for row in regime_table},
            "branch_exposure_ratio": {row["regime"]: row["exposure_ratio"] for row in regime_table},
        }

    regime_counts = diagnostics_df["execution_regime"].value_counts(dropna=False)
    total_days = max(int(regime_counts.sum()), 1)
    observed_regimes = [
        str(value)
        for value in diagnostics_df["execution_regime"].dropna().astype(str).tolist()
        if str(value)
    ]
    ordered_regimes = list(_REGIME_ORDER)
    for regime in observed_regimes:
        if regime not in ordered_regimes:
            ordered_regimes.append(regime)
    return_by_regime = (
        diagnostics_df.groupby("execution_regime")["strategy_return"].sum()
        if "strategy_return" in diagnostics_df.columns
        else pd.Series(dtype=float)
    )
    exposure_by_regime = (
        diagnostics_df.groupby("execution_regime")["position"].sum()
        if "position" in diagnostics_df.columns
        else diagnostics_df.groupby("execution_regime")["target_position"].sum()
        if "target_position" in diagnostics_df.columns
        else pd.Series(dtype=float)
    )
    total_exposure = float(pd.to_numeric(exposure_by_regime, errors="coerce").fillna(0.0).sum())

    regime_table: list[dict[str, Any]] = []
    for regime in ordered_regimes:
        day_count = int(regime_counts.get(regime, 0))
        contribution = _coerce_scalar(return_by_regime.get(regime, 0.0))
        exposure = _coerce_scalar(exposure_by_regime.get(regime, 0.0))
        regime_table.append(
            {
                "regime": regime,
                "day_count": day_count,
                "day_ratio": day_count / total_days,
                "return_contribution": contribution,
                "exposure_ratio": (exposure / total_exposure) if total_exposure > 0 else 0.0,
            }
        )

    return {
        "market_proxy_symbol": market_proxy_symbol,
        "market_proxy_mode": market_proxy_mode,
        "market_proxy_unavailable": market_proxy_unavailable,
        "market_proxy_warning": market_proxy_warning,
        "latest_execution_regime": str(diagnostics_df["execution_regime"].iloc[-1]),
        "regime_table": regime_table,
        "execution_regime_day_ratio": {row["regime"]: row["day_ratio"] for row in regime_table},
        "execution_regime_return_contribution": {row["regime"]: row["return_contribution"] for row in regime_table},
        "branch_exposure_ratio": {row["regime"]: row["exposure_ratio"] for row in regime_table},
    }


__all__ = [
    "DEFAULT_MARKET_PROXY_SYMBOL",
    "RegimeKind",
    "build_market_proxy_frame",
    "compute_regime_features",
    "compute_regime_signals",
    "summarize_regime_diagnostics",
]
