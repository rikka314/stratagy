"""
参数优化模块
============
预设评估、随机搜索、贝叶斯优化（Optuna）、遗传算法优化。
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from core.backtest import max_drawdown, sharpe_ratio, simulate_strategy
from core.config import _PRESET_PARAMS_FOR_OPTIMIZATION
from core.fa_filter import fit_fa
from core.indicators import add_indicators
from core.signals import compute_signals


SearchParamSpec = tuple[Any, Any, Any, str]
DEFAULT_SEARCH_RANDOM_SEED = 42


LEGACY_SEARCH_PARAM_SPACE: dict[str, SearchParamSpec] = {
    "ema_fast": (12, 5, 50, "int"),
    "ema_slow": (60, 20, 200, "int"),
    "macd_fast": (12, 5, 20, "int"),
    "macd_slow": (26, 10, 40, "int"),
    "macd_signal": (9, 5, 20, "int"),
    "rsi_period": (14, 5, 30, "int"),
    "rsi_lower": (30.0, 10, 50, "float"),
    "rsi_upper": (70.0, 50, 90, "float"),
    "adx_period": (14, 5, 30, "int"),
    "atr_period": (14, 5, 30, "int"),
    "bb_period": (20, 5, 50, "int"),
    "bb_std": (2.0, 1.0, 3.0, "float"),
    "indicator_period": (20, 5, 60, "int"),
    "entry_threshold": (0.5, -1.0, 2.0, "float"),
    "exit_threshold": (-0.5, -2.0, 0.5, "float"),
    "adx_threshold": (20.0, 10, 35, "float"),
    "stop_loss_mult": (2.0, 0.5, 4.0, "float"),
    "take_profit_mult": (4.0, 1.0, 6.0, "float"),
    "weight_bb": (0.8, 0.0, 2.0, "float"),
    "weight_obv": (1.0, 0.0, 2.0, "float"),
    "weight_volume": (0.6, 0.0, 1.5, "float"),
    "weight_price": (0.7, 0.0, 1.5, "float"),
    "weight_drawdown": (0.5, 0.0, 1.5, "float"),
}

SEARCH_PARAM_SPACE: dict[str, SearchParamSpec] = {
    **LEGACY_SEARCH_PARAM_SPACE,
    "momentum_short": (5, 3, 15, "int"),
    "momentum_long": (20, 10, 60, "int"),
    "score_lookback": (30, 10, 80, "int"),
    "score_mid_pct": (0.6, 0.40, 0.75, "float"),
    "score_high_pct": (0.8, 0.60, 0.95, "float"),
    "entry_min_signals": (3, 1, 5, "int"),
    "exit_min_signals": (2, 1, 4, "int"),
    "use_strength_filter": (True, False, True, "bool"),
    "use_rsi_filter": (True, False, True, "bool"),
    "use_macd_filter": (True, False, True, "bool"),
}


def _resolve_optimizer_worker_limit(default_limit: int) -> int:
    env_value = os.getenv("STRATAGY_OPTIMIZER_MAX_WORKERS")
    if env_value is None or env_value == "":
        return max(1, int(default_limit))
    try:
        parsed = int(env_value)
    except Exception:
        return max(1, int(default_limit))
    return max(1, min(int(default_limit), parsed))


@dataclass(frozen=True)
class SearchMetrics:
    sharpe: float
    total_return: float
    max_drawdown: float
    excess_return: float = 0.0
    turnover: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "sharpe": float(self.sharpe),
            "return": float(self.total_return),
            "total_return": float(self.total_return),
            "excess_return": float(self.excess_return),
            "max_drawdown": float(self.max_drawdown),
            "turnover": float(self.turnover),
        }


@dataclass
class SearchEvaluationResult:
    params: dict[str, Any]
    full_signal_df: pd.DataFrame
    raw_score: float
    train_metrics: SearchMetrics
    validation_metrics: SearchMetrics

    def to_optimization_result(self, *, method_name: str, score: float) -> "SearchOptimizationResult":
        return SearchOptimizationResult(
            best_params=dict(self.params),
            method_name=str(method_name),
            score=float(score),
            train_metrics=self.train_metrics,
            validation_metrics=self.validation_metrics,
            full_signal_df=self.full_signal_df.copy(),
        )


@dataclass
class SearchOptimizationResult:
    best_params: dict[str, Any]
    method_name: str
    score: float
    train_metrics: SearchMetrics
    validation_metrics: SearchMetrics
    full_signal_df: pd.DataFrame

    def to_metadata(self) -> dict[str, Any]:
        return {
            "best_params": dict(self.best_params),
            "method_name": str(self.method_name),
            "score": float(self.score),
            "train_metrics": self.train_metrics.to_dict(),
            "validation_metrics": self.validation_metrics.to_dict(),
        }


def _resolve_search_param_space(common_kwargs: dict[str, Any] | None) -> dict[str, SearchParamSpec]:
    if common_kwargs and bool(common_kwargs.get("hold_until_exit", False)):
        return SEARCH_PARAM_SPACE
    return LEGACY_SEARCH_PARAM_SPACE


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value) != 0
    if isinstance(value, (np.floating, float)):
        if np.isnan(value):
            return False
        return float(value) != 0.0
    return bool(value)


def _normalize_candidate_params(
    candidate_params: dict[str, Any] | None,
    *,
    param_space: dict[str, SearchParamSpec] | None = None,
) -> dict[str, Any]:
    active_param_space = param_space or SEARCH_PARAM_SPACE
    normalized: dict[str, Any] = {}
    source = candidate_params or {}
    for name, (default, _lo, _hi, param_type) in active_param_space.items():
        value = source.get(name, default)
        if param_type == "int":
            normalized[name] = int(round(float(value)))
        elif param_type == "bool":
            normalized[name] = _coerce_bool(value)
        else:
            normalized[name] = float(value)
    return normalized


def _clip_candidate_params(
    candidate_params: dict[str, Any] | None,
    *,
    param_space: dict[str, SearchParamSpec] | None = None,
) -> dict[str, Any]:
    active_param_space = param_space or SEARCH_PARAM_SPACE
    clipped = _normalize_candidate_params(candidate_params, param_space=active_param_space)
    for name, (_default, lo, hi, param_type) in active_param_space.items():
        if param_type == "bool":
            clipped[name] = _coerce_bool(clipped[name])
            continue
        value = np.clip(clipped[name], lo, hi)
        clipped[name] = int(round(value)) if param_type == "int" else float(value)
    return clipped


def _normalize_candidate_key(
    candidate_params: dict[str, Any] | None,
    *,
    param_space: dict[str, SearchParamSpec] | None = None,
) -> tuple[tuple[str, Any], ...]:
    active_param_space = param_space or SEARCH_PARAM_SPACE
    normalized = _normalize_candidate_params(candidate_params, param_space=active_param_space)
    return tuple((name, normalized[name]) for name in active_param_space)


def _is_valid_candidate(
    candidate_params: dict[str, Any],
    *,
    param_space: dict[str, SearchParamSpec] | None = None,
) -> bool:
    normalized = _normalize_candidate_params(candidate_params, param_space=param_space)
    if normalized["ema_fast"] >= normalized["ema_slow"]:
        return False
    if normalized["macd_fast"] >= normalized["macd_slow"]:
        return False
    if normalized["entry_threshold"] <= normalized["exit_threshold"]:
        return False
    if "momentum_short" in normalized and normalized["momentum_short"] >= normalized["momentum_long"]:
        return False
    if "score_mid_pct" in normalized and normalized["score_mid_pct"] >= normalized["score_high_pct"]:
        return False
    if "exit_min_signals" in normalized and normalized["exit_min_signals"] > normalized["entry_min_signals"]:
        return False
    return True


def _regularization_penalty(
    candidate_params: dict[str, Any],
    *,
    lam: float = 0.02,
    param_space: dict[str, SearchParamSpec] | None = None,
) -> float:
    active_param_space = param_space or SEARCH_PARAM_SPACE
    penalty = 0.0
    normalized = _normalize_candidate_params(candidate_params, param_space=active_param_space)
    for name, (default, lo, hi, param_type) in active_param_space.items():
        if param_type == "bool":
            penalty += float(normalized[name] != _coerce_bool(default))
            continue
        span = hi - lo
        if span > 0:
            penalty += ((normalized[name] - default) / span) ** 2
    return lam * penalty


def _build_signal_frame_for_search(
    *,
    df_raw: pd.DataFrame,
    split_idx: int,
    indicator_params: dict[str, Any],
    signal_params: dict[str, Any],
    fsm_mode: bool = False,
    fa_fit_end_idx: int | None = None,
) -> pd.DataFrame:
    df_indicators = add_indicators(df_raw, **indicator_params)
    if not fsm_mode:
        return compute_signals(df_indicators, **signal_params)

    manual_df = compute_signals(df_indicators, **signal_params)
    fa_train_end = int(fa_fit_end_idx) if fa_fit_end_idx is not None else int(split_idx)
    fa_train_end = max(1, min(fa_train_end, len(manual_df)))
    fa_model = fit_fa(manual_df.iloc[:fa_train_end].copy())
    return compute_signals(
        df_indicators,
        **signal_params,
        fsm_mode=True,
        fa_model=fa_model,
    )


def _score_simulation(sim_df: pd.DataFrame) -> SearchMetrics:
    if sim_df is None or sim_df.empty:
        return SearchMetrics(sharpe=0.0, total_return=0.0, max_drawdown=0.0, excess_return=0.0, turnover=0.0)

    total_return = float(sim_df["strategy_equity"].iloc[-1] - 1)
    excess_return = float(sim_df["strategy_equity"].iloc[-1] - sim_df["buy_hold_equity"].iloc[-1])
    sharpe = float(sharpe_ratio(sim_df["strategy_return"]))
    drawdown = float(max_drawdown(sim_df["strategy_equity"]))
    raw_position = sim_df["position"] if "position" in sim_df.columns else pd.Series(0.0, index=sim_df.index)
    position = pd.to_numeric(raw_position, errors="coerce").fillna(0.0)
    prev_position = position.shift(1).fillna(0.0)
    entries = ((position > 1e-8) & (prev_position <= 1e-8)).sum()
    turnover = float(entries / len(sim_df)) if len(sim_df) > 0 else 0.0
    return SearchMetrics(
        sharpe=sharpe,
        total_return=total_return,
        max_drawdown=drawdown,
        excess_return=excess_return,
        turnover=turnover,
    )


def _score_metrics(metrics: SearchMetrics) -> float:
    return float(
        metrics.sharpe
        + 2.0 * metrics.excess_return
        - 0.5 * abs(metrics.max_drawdown)
        - 0.25 * metrics.turnover
    )


def _sub_train_end(split_idx: int) -> int:
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        return int(split_idx)
    return sub_train_end


def _indicator_params_from_candidate(candidate_params: dict[str, Any]) -> dict[str, Any]:
    return {
        "rsi_period": int(candidate_params["rsi_period"]),
        "macd_fast": int(candidate_params["macd_fast"]),
        "macd_slow": int(candidate_params["macd_slow"]),
        "macd_signal": int(candidate_params["macd_signal"]),
        "ema_fast": int(candidate_params["ema_fast"]),
        "ema_slow": int(candidate_params["ema_slow"]),
        "adx_period": int(candidate_params["adx_period"]),
        "atr_period": int(candidate_params["atr_period"]),
        "bb_period": int(candidate_params["bb_period"]),
        "bb_std": float(candidate_params["bb_std"]),
        "indicator_period": int(candidate_params["indicator_period"]),
    }


def _candidate_or_common_value(candidate_params: dict[str, Any], common_kwargs: dict[str, Any], name: str) -> Any:
    if name in candidate_params:
        return candidate_params[name]
    if name in common_kwargs:
        return common_kwargs[name]
    return SEARCH_PARAM_SPACE.get(name, (None, None, None, ""))[0]


def _default_candidate_from_common_kwargs(
    common_kwargs: dict[str, Any],
    *,
    param_space: dict[str, SearchParamSpec],
) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for name, (default, _lo, _hi, _param_type) in param_space.items():
        candidate[name] = common_kwargs.get(name, default)
    return _normalize_candidate_params(candidate, param_space=param_space)


def _signal_params_from_candidate(
    candidate_params: dict[str, Any],
    common_kwargs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "rsi_lower": float(candidate_params["rsi_lower"]),
        "rsi_upper": float(candidate_params["rsi_upper"]),
        "adx_threshold": float(candidate_params["adx_threshold"]),
        "momentum_short": int(_candidate_or_common_value(candidate_params, common_kwargs, "momentum_short")),
        "momentum_long": int(_candidate_or_common_value(candidate_params, common_kwargs, "momentum_long")),
        "score_lookback": int(_candidate_or_common_value(candidate_params, common_kwargs, "score_lookback")),
        "score_mid_pct": float(_candidate_or_common_value(candidate_params, common_kwargs, "score_mid_pct")),
        "score_high_pct": float(_candidate_or_common_value(candidate_params, common_kwargs, "score_high_pct")),
        "weight_mom_short": common_kwargs["weight_mom_short"],
        "weight_mom_long": common_kwargs["weight_mom_long"],
        "weight_macd": common_kwargs["weight_macd"],
        "weight_rsi": common_kwargs["weight_rsi"],
        "weight_vol": common_kwargs["weight_vol"],
        "entry_threshold": float(candidate_params["entry_threshold"]),
        "exit_threshold": float(candidate_params["exit_threshold"]),
        "use_trend_filter": bool(common_kwargs["use_trend_filter"]),
        "use_strength_filter": bool(_candidate_or_common_value(candidate_params, common_kwargs, "use_strength_filter")),
        "use_rsi_filter": bool(_candidate_or_common_value(candidate_params, common_kwargs, "use_rsi_filter")),
        "use_macd_filter": bool(_candidate_or_common_value(candidate_params, common_kwargs, "use_macd_filter")),
        "weight_bb": float(candidate_params["weight_bb"]),
        "weight_obv": float(candidate_params["weight_obv"]),
        "weight_volume": float(candidate_params["weight_volume"]),
        "weight_price": float(candidate_params["weight_price"]),
        "weight_drawdown": float(candidate_params["weight_drawdown"]),
        "exit_min_signals": int(_candidate_or_common_value(candidate_params, common_kwargs, "exit_min_signals")),
        "entry_min_signals": int(_candidate_or_common_value(candidate_params, common_kwargs, "entry_min_signals")),
        "hold_until_exit": bool(common_kwargs.get("hold_until_exit", False)),
        "hold_min_position": float(common_kwargs.get("hold_min_position", 0.2)),
    }


def _evaluate_candidate_frame(
    *,
    df_raw: pd.DataFrame,
    split_idx: int,
    sub_train_end: int,
    candidate_params: dict[str, Any],
    common_kwargs: dict[str, Any],
    fsm_mode: bool,
    param_space: dict[str, SearchParamSpec],
) -> SearchEvaluationResult | None:
    normalized = _normalize_candidate_params(candidate_params, param_space=param_space)
    if not _is_valid_candidate(normalized, param_space=param_space):
        return None

    try:
        full_signal_df = _build_signal_frame_for_search(
            df_raw=df_raw,
            split_idx=split_idx,
            fa_fit_end_idx=sub_train_end,
            indicator_params=_indicator_params_from_candidate(normalized),
            signal_params=_signal_params_from_candidate(normalized, common_kwargs),
            fsm_mode=fsm_mode,
        )
        train_sim = simulate_strategy(
            full_signal_df.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=float(normalized["stop_loss_mult"]),
            take_profit_mult=float(normalized["take_profit_mult"]),
        )
        train_metrics = _score_simulation(train_sim)

        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                full_signal_df.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=float(normalized["stop_loss_mult"]),
                take_profit_mult=float(normalized["take_profit_mult"]),
            )
            validation_metrics = _score_simulation(val_sim)
            train_score = _score_metrics(train_metrics)
            validation_score = _score_metrics(validation_metrics)
            raw_score = (
                0.25 * train_score
                + 0.75 * validation_score
                - 0.20 * abs(train_score - validation_score)
            )
        else:
            validation_metrics = train_metrics
            raw_score = _score_metrics(train_metrics)
    except Exception:
        return None

    return SearchEvaluationResult(
        params=normalized,
        full_signal_df=full_signal_df,
        raw_score=float(raw_score),
        train_metrics=train_metrics,
        validation_metrics=validation_metrics,
    )


class SearchEvaluationCache:
    """
    请求级候选评估缓存。

    key = 规范化参数元组 + fsm_mode + split 签名
    """

    def __init__(
        self,
        *,
        df_raw: pd.DataFrame,
        split_idx: int,
        common_kwargs: dict[str, Any],
        fsm_mode: bool = False,
    ) -> None:
        self._df_raw = df_raw
        self._split_idx = int(split_idx)
        self._sub_train_end = _sub_train_end(self._split_idx)
        self._common_kwargs = dict(common_kwargs)
        self._fsm_mode = bool(fsm_mode)
        self._param_space = _resolve_search_param_space(self._common_kwargs)
        self._regularization_lam = 0.03 if bool(self._common_kwargs.get("hold_until_exit", False)) else 0.02
        self._split_signature = (
            int(len(df_raw)),
            int(self._split_idx),
            int(self._sub_train_end),
        )
        self._cache: dict[tuple[Any, ...], SearchEvaluationResult | None] = {}
        self._inflight: dict[tuple[Any, ...], threading.Event] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def split_idx(self) -> int:
        return self._split_idx

    @property
    def sub_train_end(self) -> int:
        return self._sub_train_end

    @property
    def param_space(self) -> dict[str, SearchParamSpec]:
        return self._param_space

    @property
    def regularization_lam(self) -> float:
        return self._regularization_lam

    def _cache_key(self, candidate_params: dict[str, Any] | None) -> tuple[Any, ...]:
        return (
            _normalize_candidate_key(candidate_params, param_space=self._param_space),
            self._fsm_mode,
            self._split_signature,
        )

    def evaluate(self, candidate_params: dict[str, Any] | None) -> SearchEvaluationResult | None:
        cache_key = self._cache_key(candidate_params)
        should_compute = False

        while True:
            with self._lock:
                if cache_key in self._cache:
                    self.hits += 1
                    return self._cache[cache_key]
                inflight = self._inflight.get(cache_key)
                if inflight is None:
                    inflight = threading.Event()
                    self._inflight[cache_key] = inflight
                    self.misses += 1
                    should_compute = True
                    break
            inflight.wait()

        result: SearchEvaluationResult | None = None
        try:
            result = _evaluate_candidate_frame(
                df_raw=self._df_raw,
                split_idx=self._split_idx,
                sub_train_end=self._sub_train_end,
                candidate_params=_normalize_candidate_params(candidate_params, param_space=self._param_space),
                common_kwargs=self._common_kwargs,
                fsm_mode=self._fsm_mode,
                param_space=self._param_space,
            )
            return result
        finally:
            if should_compute:
                with self._lock:
                    self._cache[cache_key] = result
                    event = self._inflight.pop(cache_key)
                    event.set()


def _ensure_evaluation_cache(
    *,
    evaluation_cache: SearchEvaluationCache | None,
    df_raw: pd.DataFrame,
    split_idx: int,
    common_kwargs: dict[str, Any],
    fsm_mode: bool,
) -> SearchEvaluationCache:
    if evaluation_cache is not None:
        return evaluation_cache
    return SearchEvaluationCache(
        df_raw=df_raw,
        split_idx=split_idx,
        common_kwargs=common_kwargs,
        fsm_mode=fsm_mode,
    )


def _random_candidate(
    rng: np.random.Generator,
    *,
    param_space: dict[str, SearchParamSpec],
) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for name, (_default, lo, hi, param_type) in param_space.items():
        if param_type == "int":
            candidate[name] = int(rng.integers(int(lo), int(hi) + 1))
        elif param_type == "bool":
            candidate[name] = bool(rng.integers(0, 2))
        else:
            candidate[name] = float(rng.uniform(float(lo), float(hi)))
    return candidate


def _suggest_candidate(trial, *, param_space: dict[str, SearchParamSpec]) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for name, (_default, lo, hi, param_type) in param_space.items():
        if param_type == "int":
            candidate[name] = trial.suggest_int(name, int(lo), int(hi))
        elif param_type == "bool":
            candidate[name] = trial.suggest_categorical(name, [False, True])
        else:
            candidate[name] = trial.suggest_float(name, float(lo), float(hi))
    return candidate


def evaluate_presets_for_optimization(
    df_raw: pd.DataFrame,
    split_idx: int,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    hold_until_exit: bool = False,
    hold_min_position: float = 0.2,
    fsm_mode: bool = False,
    evaluation_cache: SearchEvaluationCache | None = None,
) -> tuple[dict[str, Any], str, list[tuple[str, float]]]:
    """
    快速评估 3 个预设策略在训练集上的表现，返回最佳预设参数。
    用于贝叶斯优化/遗传算法热启动。
    """
    common_kwargs = {
        "momentum_short": momentum_short,
        "momentum_long": momentum_long,
        "score_lookback": score_lookback,
        "score_mid_pct": score_mid_pct,
        "score_high_pct": score_high_pct,
        "weight_mom_short": weight_mom_short,
        "weight_mom_long": weight_mom_long,
        "weight_macd": weight_macd,
        "weight_rsi": weight_rsi,
        "weight_vol": weight_vol,
        "use_trend_filter": use_trend_filter,
        "use_strength_filter": use_strength_filter,
        "use_rsi_filter": use_rsi_filter,
        "use_macd_filter": use_macd_filter,
        "hold_until_exit": hold_until_exit,
        "hold_min_position": hold_min_position,
    }
    cache = _ensure_evaluation_cache(
        evaluation_cache=evaluation_cache,
        df_raw=df_raw,
        split_idx=split_idx,
        common_kwargs=common_kwargs,
        fsm_mode=fsm_mode,
    )
    active_param_space = cache.param_space
    default_candidate = _default_candidate_from_common_kwargs(common_kwargs, param_space=active_param_space)

    best_score = -np.inf
    best_name = ""
    best_params: dict[str, Any] | None = None
    scores: list[tuple[str, float]] = []

    for name, params in _PRESET_PARAMS_FOR_OPTIMIZATION.items():
        preset_candidate = dict(default_candidate)
        preset_candidate.update(params)
        result = cache.evaluate(preset_candidate)
        if result is None:
            scores.append((name, -np.inf))
            continue
        scores.append((name, float(result.raw_score)))
        if result.raw_score > best_score:
            best_score = float(result.raw_score)
            best_name = name
            best_params = dict(result.params)

    return best_params or {}, best_name, scores


def random_search_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    n_trials: int,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    hold_until_exit: bool = False,
    hold_min_position: float = 0.2,
    progress_callback=None,
    seed_params: dict[str, Any] | None = None,
    random_seed: int = DEFAULT_SEARCH_RANDOM_SEED,
    fsm_mode: bool = False,
    evaluation_cache: SearchEvaluationCache | None = None,
) -> SearchOptimizationResult | None:
    """
    随机搜索最优参数（含防过拟合：子验证集 + 正则化）。
    """
    rng = np.random.default_rng(int(random_seed))
    common_kwargs = {
        "momentum_short": momentum_short,
        "momentum_long": momentum_long,
        "score_lookback": score_lookback,
        "score_mid_pct": score_mid_pct,
        "score_high_pct": score_high_pct,
        "weight_mom_short": weight_mom_short,
        "weight_mom_long": weight_mom_long,
        "weight_macd": weight_macd,
        "weight_rsi": weight_rsi,
        "weight_vol": weight_vol,
        "use_trend_filter": use_trend_filter,
        "use_strength_filter": use_strength_filter,
        "use_rsi_filter": use_rsi_filter,
        "use_macd_filter": use_macd_filter,
        "hold_until_exit": hold_until_exit,
        "hold_min_position": hold_min_position,
    }
    cache = _ensure_evaluation_cache(
        evaluation_cache=evaluation_cache,
        df_raw=df_raw,
        split_idx=split_idx,
        common_kwargs=common_kwargs,
        fsm_mode=fsm_mode,
    )
    active_param_space = cache.param_space

    best_result: SearchOptimizationResult | None = None

    def _random_individual() -> dict[str, Any]:
        return _random_candidate(rng, param_space=active_param_space)

    for trial_i in range(int(n_trials)):
        if progress_callback:
            progress_callback(trial_i + 1, int(n_trials))

        if trial_i == 0 and seed_params:
            candidate = _clip_candidate_params(seed_params, param_space=active_param_space)
        else:
            candidate = _random_individual()

        evaluation = cache.evaluate(candidate)
        if evaluation is None:
            continue

        score = float(
            evaluation.raw_score
            - _regularization_penalty(
                evaluation.params,
                lam=cache.regularization_lam,
                param_space=active_param_space,
            )
        )
        if best_result is None or score > best_result.score:
            best_result = evaluation.to_optimization_result(
                method_name="random_search",
                score=score,
            )

    return best_result


def bayesian_optimize_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    n_trials: int,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    hold_until_exit: bool = False,
    hold_min_position: float = 0.2,
    progress_callback=None,
    seed_params: dict[str, Any] | None = None,
    random_seed: int = DEFAULT_SEARCH_RANDOM_SEED,
    fsm_mode: bool = False,
    evaluation_cache: SearchEvaluationCache | None = None,
) -> SearchOptimizationResult | None:
    """
    使用贝叶斯优化（Optuna）搜索最优参数（含热启动 + 防过拟合）。
    """
    try:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        st.error("需要安装 optuna 库。请运行：pip install optuna")
        return None

    common_kwargs = {
        "momentum_short": momentum_short,
        "momentum_long": momentum_long,
        "score_lookback": score_lookback,
        "score_mid_pct": score_mid_pct,
        "score_high_pct": score_high_pct,
        "weight_mom_short": weight_mom_short,
        "weight_mom_long": weight_mom_long,
        "weight_macd": weight_macd,
        "weight_rsi": weight_rsi,
        "weight_vol": weight_vol,
        "use_trend_filter": use_trend_filter,
        "use_strength_filter": use_strength_filter,
        "use_rsi_filter": use_rsi_filter,
        "use_macd_filter": use_macd_filter,
        "hold_until_exit": hold_until_exit,
        "hold_min_position": hold_min_position,
    }
    cache = _ensure_evaluation_cache(
        evaluation_cache=evaluation_cache,
        df_raw=df_raw,
        split_idx=split_idx,
        common_kwargs=common_kwargs,
        fsm_mode=fsm_mode,
    )
    active_param_space = cache.param_space

    best_result: SearchOptimizationResult | None = None

    def objective(trial) -> float:
        candidate = _suggest_candidate(trial, param_space=active_param_space)
        evaluation = cache.evaluate(candidate)
        if evaluation is None:
            return -np.inf

        score = float(
            evaluation.raw_score
            - _regularization_penalty(
                evaluation.params,
                lam=cache.regularization_lam,
                param_space=active_param_space,
            )
        )
        nonlocal best_result
        if best_result is None or score > best_result.score:
            best_result = evaluation.to_optimization_result(
                method_name="bayesian",
                score=score,
            )
        return score

    sampler = optuna.samplers.TPESampler(seed=int(random_seed))
    study = optuna.create_study(direction="maximize", sampler=sampler)

    if seed_params:
        clipped_seed = _clip_candidate_params(seed_params, param_space=active_param_space)
        study.enqueue_trial({key: clipped_seed[key] for key in active_param_space})

    completed_trials = [0]

    def _optuna_callback(study, trial) -> None:
        completed_trials[0] += 1
        if progress_callback:
            progress_callback(completed_trials[0], int(n_trials))

    study.optimize(
        objective,
        n_trials=int(n_trials),
        show_progress_bar=False,
        callbacks=[_optuna_callback],
    )
    return best_result


def genetic_algorithm_optimize_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    population_size: int = 30,
    generations: int = 20,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.2,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    hold_until_exit: bool = False,
    hold_min_position: float = 0.2,
    progress_callback=None,
    seed_params: dict[str, Any] | None = None,
    random_seed: int = DEFAULT_SEARCH_RANDOM_SEED,
    fsm_mode: bool = False,
    evaluation_cache: SearchEvaluationCache | None = None,
) -> SearchOptimizationResult | None:
    """
    使用遗传算法搜索最优参数（含热启动 + 多核并行 + 精英保留 + 防过拟合）。
    """
    rng = np.random.default_rng(int(random_seed))
    population_size = int(population_size)
    generations = int(generations)
    common_kwargs = {
        "momentum_short": momentum_short,
        "momentum_long": momentum_long,
        "score_lookback": score_lookback,
        "score_mid_pct": score_mid_pct,
        "score_high_pct": score_high_pct,
        "weight_mom_short": weight_mom_short,
        "weight_mom_long": weight_mom_long,
        "weight_macd": weight_macd,
        "weight_rsi": weight_rsi,
        "weight_vol": weight_vol,
        "use_trend_filter": use_trend_filter,
        "use_strength_filter": use_strength_filter,
        "use_rsi_filter": use_rsi_filter,
        "use_macd_filter": use_macd_filter,
        "hold_until_exit": hold_until_exit,
        "hold_min_position": hold_min_position,
    }
    cache = _ensure_evaluation_cache(
        evaluation_cache=evaluation_cache,
        df_raw=df_raw,
        split_idx=split_idx,
        common_kwargs=common_kwargs,
        fsm_mode=fsm_mode,
    )
    active_param_space = cache.param_space
    param_names = list(active_param_space.keys())

    def _random_individual() -> dict[str, Any]:
        return _random_candidate(rng, param_space=active_param_space)

    def _gaussian_mutate(candidate: dict[str, Any], rate: float) -> dict[str, Any]:
        mutated = dict(candidate)
        for name, (_default, lo, hi, param_type) in active_param_space.items():
            if rng.random() < rate:
                if param_type == "bool":
                    mutated[name] = not _coerce_bool(mutated[name])
                else:
                    span = hi - lo
                    mutated[name] = mutated[name] + rng.normal(0, span * 0.1)
        return _clip_candidate_params(mutated, param_space=active_param_space)

    def _tournament_select(population: list[dict[str, Any]], fitnesses: list[float], k: int = 3) -> dict[str, Any]:
        indices = rng.choice(len(population), size=k, replace=False)
        best_idx = int(indices[0])
        for idx in indices[1:]:
            idx = int(idx)
            if fitnesses[idx] > fitnesses[best_idx]:
                best_idx = idx
        return dict(population[best_idx])

    def _blx_alpha_crossover(parent1: dict[str, Any], parent2: dict[str, Any], alpha: float = 0.5) -> dict[str, Any]:
        child: dict[str, Any] = {}
        for name in param_names:
            p1 = parent1[name]
            p2 = parent2[name]
            if active_param_space[name][3] == "bool":
                child[name] = p1 if rng.random() < 0.5 else p2
                continue
            lo_value = min(p1, p2)
            hi_value = max(p1, p2)
            span = hi_value - lo_value
            child[name] = rng.uniform(lo_value - alpha * span, hi_value + alpha * span)
        return _clip_candidate_params(child, param_space=active_param_space)

    def _evaluate(candidate: dict[str, Any]) -> float:
        evaluation = cache.evaluate(candidate)
        if evaluation is None:
            return -np.inf
        return float(
            evaluation.raw_score
            - _regularization_penalty(
                evaluation.params,
                lam=cache.regularization_lam,
                param_space=active_param_space,
            )
        )

    max_workers = _resolve_optimizer_worker_limit(min(os.cpu_count() or 1, population_size, 8))
    population: list[dict[str, Any]] = []

    if seed_params:
        seed_candidate = _clip_candidate_params(seed_params, param_space=active_param_space)
        if _is_valid_candidate(seed_candidate, param_space=active_param_space):
            population.append(seed_candidate)
            for _ in range(3):
                mutated_seed = _gaussian_mutate(seed_candidate, 0.5)
                if _is_valid_candidate(mutated_seed, param_space=active_param_space):
                    population.append(mutated_seed)

    max_init_attempts = population_size * 10
    attempts = 0
    while len(population) < population_size and attempts < max_init_attempts:
        candidate = _random_individual()
        if _is_valid_candidate(candidate, param_space=active_param_space):
            population.append(candidate)
        attempts += 1
    if len(population) < population_size:
        return None

    total_evals = population_size + generations * population_size
    completed_evals = [0]

    fitnesses = [0.0] * len(population)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(_evaluate, candidate): idx for idx, candidate in enumerate(population)}
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            fitnesses[idx] = float(future.result())
            completed_evals[0] += 1
            if progress_callback:
                progress_callback(completed_evals[0], total_evals)

    elite_count = 2
    best_candidate: dict[str, Any] | None = None
    best_score = -np.inf

    for _generation in range(generations):
        generation_best_idx = int(np.argmax(fitnesses))
        if fitnesses[generation_best_idx] > best_score:
            best_score = float(fitnesses[generation_best_idx])
            best_candidate = dict(population[generation_best_idx])

        sorted_indices = list(np.argsort(fitnesses)[::-1])
        new_population = [dict(population[idx]) for idx in sorted_indices[:elite_count]]
        new_fitnesses = [float(fitnesses[idx]) for idx in sorted_indices[:elite_count]]

        children: list[dict[str, Any]] = []
        while len(new_population) + len(children) < population_size:
            parent1 = _tournament_select(population, fitnesses)
            parent2 = _tournament_select(population, fitnesses)

            if rng.random() < crossover_rate:
                child = _blx_alpha_crossover(parent1, parent2)
            else:
                child = dict(parent1)

            child = _gaussian_mutate(child, mutation_rate)
            for _ in range(5):
                if _is_valid_candidate(child, param_space=active_param_space):
                    break
                child = _gaussian_mutate(_random_individual(), mutation_rate)

            if not _is_valid_candidate(child, param_space=active_param_space):
                child = _random_individual()
                if not _is_valid_candidate(child, param_space=active_param_space):
                    continue
            children.append(child)

        child_fitnesses = [0.0] * len(children)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {executor.submit(_evaluate, candidate): idx for idx, candidate in enumerate(children)}
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                child_fitnesses[idx] = float(future.result())
                completed_evals[0] += 1
                if progress_callback:
                    progress_callback(completed_evals[0], total_evals)

        new_population.extend(children)
        new_fitnesses.extend(child_fitnesses)
        population = new_population
        fitnesses = new_fitnesses

    final_best_idx = int(np.argmax(fitnesses))
    if fitnesses[final_best_idx] > best_score:
        best_score = float(fitnesses[final_best_idx])
        best_candidate = dict(population[final_best_idx])

    if best_candidate is None or not np.isfinite(best_score):
        return None

    best_evaluation = cache.evaluate(best_candidate)
    if best_evaluation is None:
        return None
    return best_evaluation.to_optimization_result(
        method_name="genetic_algorithm",
        score=best_score,
    )


__all__ = [
    "DEFAULT_SEARCH_RANDOM_SEED",
    "SearchMetrics",
    "SearchEvaluationResult",
    "SearchOptimizationResult",
    "SearchEvaluationCache",
    "evaluate_presets_for_optimization",
    "random_search_params",
    "bayesian_optimize_params",
    "genetic_algorithm_optimize_params",
]
