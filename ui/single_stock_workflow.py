"""
单股页策略编排层
================
把 `StrategyRequest -> stage_result -> StrategyArtifact -> strategy_workspace`
从 `ui/single_stock.py` 中拆出，集中处理请求校验、阶段缓存、流水线串联与上下文失效。
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
import streamlit as st
from ui.i18n import tr

from core.backtest import simulate_strategy
from core.adaptive_regime import (
    ADAPTIVE_MIN_STATE_DAYS,
    ADAPTIVE_ONLINE_DEFAULT_CANDIDATE_ALIASES,
    ADAPTIVE_REGIME_KIND,
    aggregate_candidate_state_day_rows,
    build_adaptive_feature_frame,
    classify_segment_key,
    load_adaptive_regime_artifacts,
    normalize_distribution,
    predict_adaptive_states,
    score_candidate_state_metrics,
)
from core.baselines import drift_target_position, mean_target_position
from core.evaluation import evaluate_strategy
from core.fa_filter import fit_fa
from core.indicators import add_indicators, compute_atr
from core.ml_filter import (
    apply_filter,
    build_feature_bundle,
    build_feature_table,
    build_feature_view,
    evaluate_ml_quality,
    fit_ml_filter,
    predict_filter,
)
from core.news_factor import DEFAULT_NEWS_FACTOR_PATH, NEWS_FUSION_MODE, apply_news_fusion
from core.optimizer import (
    SearchEvaluationCache,
    SearchOptimizationResult,
    bayesian_optimize_params,
    evaluate_presets_for_optimization,
    genetic_algorithm_optimize_params,
    random_search_params,
)
from core.regime_model import compute_regime_signals, summarize_regime_diagnostics
from core.signals import compute_signals


WORKSPACE_STATE_KEY = "single_stock_strategy_workspace"
STAGE_CACHE_STATE_KEY = "single_stock_stage_cache"
STAGE_CACHE_LRU_KEY = "single_stock_stage_cache_lru"
STAGE_CACHE_MAX_ENTRIES = 12

_INDICATOR_PARAM_KEYS = (
    "rsi_period",
    "macd_fast",
    "macd_slow",
    "macd_signal",
    "ema_fast",
    "ema_slow",
    "adx_period",
    "atr_period",
    "bb_period",
    "bb_std",
    "indicator_period",
)

_SIGNAL_PARAM_KEYS = (
    "rsi_lower",
    "rsi_upper",
    "adx_threshold",
    "momentum_short",
    "momentum_long",
    "score_lookback",
    "score_mid_pct",
    "score_high_pct",
    "entry_threshold",
    "exit_threshold",
    "weight_mom_short",
    "weight_mom_long",
    "weight_macd",
    "weight_rsi",
    "weight_vol",
    "weight_bb",
    "weight_obv",
    "weight_volume",
    "weight_price",
    "weight_drawdown",
    "use_trend_filter",
    "use_strength_filter",
    "use_rsi_filter",
    "use_macd_filter",
    "use_voting_entry",
    "entry_vote_threshold",
    "exit_min_signals",
    "entry_min_signals",
    "hold_until_exit",
    "hold_min_position",
)

_SIM_PARAM_KEYS = (
    "stop_loss_mult",
    "take_profit_mult",
)

_FROZEN_PARAM_KEYS = (
    *_INDICATOR_PARAM_KEYS,
    *_SIGNAL_PARAM_KEYS,
    *_SIM_PARAM_KEYS,
    "strategy_preset",
)


@dataclass(frozen=True)
class StrategyRequest:
    family: Literal["baseline", "search", "regime"] | None = None
    baseline_kind: Literal["naive", "mean", "drift"] | None = None
    search_base: Literal["sm", "fsm"] | None = None
    regime_kind: Literal["dual_state_router", "no_market", "no_router", "adaptive_router_v1"] | None = None
    use_search: bool = False
    search_method: Literal["bayesian", "genetic", "random"] | None = None
    use_ml: bool = False
    use_news: bool = False
    news_fusion_mode: Literal["residual_gate"] = NEWS_FUSION_MODE
    news_factor_path: str | None = None
    news_weight: float = 0.4
    news_lookback: int = 20
    ml_model_type: Literal["logistic", "lgbm"] | None = None
    ml_horizon_days: int = 10
    ml_min_excess_samples: int = 20
    search_trials: int = 60
    ga_population_size: int = 30
    ga_generations: int = 20


@dataclass
class StageResult:
    stage_key: str
    display_label: str
    short_label: str
    params_snapshot: dict[str, Any]
    train_sim_df: pd.DataFrame
    test_sim_df: pd.DataFrame
    trades_df: pd.DataFrame | None
    eval: dict[str, Any]
    equity_series: pd.Series
    returns_series: pd.Series
    ml_quality: dict[str, float | None] | None
    upstream_stage_key: str | None
    full_signal_df: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyArtifact:
    id: str
    context_key: str
    display_label: str
    pipeline_lineage: list[StageResult]
    params_snapshot: dict[str, Any]
    train_sim_df: pd.DataFrame
    test_sim_df: pd.DataFrame
    trades_df: pd.DataFrame | None
    eval: dict[str, Any]
    equity_series: pd.Series
    returns_series: pd.Series
    ml_quality: dict[str, float | None] | None
    full_signal_df: pd.DataFrame
    request_signature: str


@dataclass
class PipelineRunResult:
    artifact: StrategyArtifact | None
    status: Literal["success", "degraded", "failed"]
    warnings: list[str] = field(default_factory=list)
    info_messages: list[str] = field(default_factory=list)
    error_message: str | None = None


def _normalize_for_json(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize_for_json(asdict(value))
    if isinstance(value, dict):
        return {str(k): _normalize_for_json(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_for_json(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _hash_payload(payload: Any, prefix: str = "") -> str:
    normalized = _normalize_for_json(payload)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.md5(encoded.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{digest}" if prefix else digest


def _build_time_index(df: pd.DataFrame) -> pd.Index:
    if "date" in df.columns:
        time_index = pd.to_datetime(df["date"], errors="coerce")
        if time_index.notna().any():
            return pd.Index(time_index)
    return pd.RangeIndex(len(df))


def _refresh_trade_signal_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "target_position" not in out.columns:
        return out

    target_position = pd.to_numeric(out["target_position"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    prev_position = target_position.shift(1)
    if len(prev_position) > 0:
        prev_position.iloc[0] = target_position.iloc[0]
    prev_position = prev_position.fillna(0.0)
    out["target_position"] = target_position
    out["buy_signal"] = (target_position > 0) & (prev_position <= 0)
    out["sell_signal"] = (target_position <= 0) & (prev_position > 0)
    return out


def _fingerprint_dataframe(df: pd.DataFrame) -> str:
    fingerprint_columns = [col for col in ("date", "open", "high", "low", "close", "volume") if col in df.columns]
    if not fingerprint_columns:
        return _hash_payload({"rows": int(len(df)), "columns": list(df.columns)}, prefix="df_")

    hashed = pd.util.hash_pandas_object(df[fingerprint_columns], index=True)
    digest = hashlib.md5(hashed.to_numpy().tobytes()).hexdigest()[:12]
    return f"df_{digest}"


def freeze_params_snapshot(params: dict[str, Any]) -> dict[str, Any]:
    return {key: params[key] for key in _FROZEN_PARAM_KEYS if key in params}


def build_request_signature(request: StrategyRequest, params_snapshot: dict[str, Any]) -> str:
    return _hash_payload({"request": asdict(request), "params_snapshot": params_snapshot}, prefix="req_")


def build_strategy_context_key(
    *,
    market: str,
    symbol: str,
    adjust: str,
    df_raw: pd.DataFrame,
    train_ratio: float,
    uploaded_file: Any = None,
) -> str:
    date_index = pd.to_datetime(df_raw["date"], errors="coerce") if "date" in df_raw.columns else pd.Series(dtype="datetime64[ns]")
    if not date_index.empty and date_index.notna().any():
        date_range = {
            "start": date_index.min().date().isoformat(),
            "end": date_index.max().date().isoformat(),
        }
    else:
        date_range = {"rows": int(len(df_raw))}

    payload = {
        "market": market,
        "symbol": symbol if uploaded_file is None else None,
        # Date range and ticker alone are not a sufficient identity: a
        # refreshed market cache can revise an existing bar, and an entry-page
        # upload is restored from route state rather than ``uploaded_file``.
        # Fingerprinting the normalized input for every source prevents either
        # path from reusing a stale workflow/artifact for different data.
        "data_fingerprint": _fingerprint_dataframe(df_raw),
        "data_source_kind": "uploaded" if uploaded_file is not None else "cached",
        "adjust": adjust,
        "date_range": date_range,
        "train_split_ratio": round(float(train_ratio), 4),
    }
    return _hash_payload(payload, prefix="ctx_")


def get_strategy_workspace() -> dict[str, Any]:
    return st.session_state.setdefault(
        WORKSPACE_STATE_KEY,
        {
            "context_key": None,
            "current_artifact": None,
            "saved_artifacts": [],
        },
    )


def ensure_strategy_workspace(context_key: str) -> tuple[dict[str, Any], bool]:
    workspace = get_strategy_workspace()
    previous_context_key = workspace.get("context_key")
    if previous_context_key == context_key:
        return workspace, False

    workspace["context_key"] = context_key
    workspace["current_artifact"] = None
    workspace["saved_artifacts"] = []
    st.session_state[WORKSPACE_STATE_KEY] = workspace
    return workspace, previous_context_key is not None


def commit_current_artifact(artifact: StrategyArtifact) -> None:
    workspace = get_strategy_workspace()
    workspace["current_artifact"] = artifact
    st.session_state[WORKSPACE_STATE_KEY] = workspace


def save_current_artifact() -> tuple[Literal["saved", "exists", "missing"], StrategyArtifact | None]:
    workspace = get_strategy_workspace()
    current_artifact: StrategyArtifact | None = workspace.get("current_artifact")
    if current_artifact is None:
        return "missing", None

    saved_artifacts: list[StrategyArtifact] = workspace.setdefault("saved_artifacts", [])
    for saved_artifact in saved_artifacts:
        if saved_artifact.id == current_artifact.id:
            return "exists", saved_artifact

    saved_copy = copy.deepcopy(current_artifact)
    saved_artifacts.append(saved_copy)
    st.session_state[WORKSPACE_STATE_KEY] = workspace
    return "saved", saved_copy


def get_workspace_status(
    workspace: dict[str, Any],
    request: StrategyRequest,
    params_snapshot: dict[str, Any],
) -> str:
    current_artifact: StrategyArtifact | None = workspace.get("current_artifact")
    if current_artifact is None:
        return "REQUEST_DRAFT"

    current_signature = build_request_signature(request, params_snapshot)
    if current_artifact.request_signature != current_signature:
        return "REQUEST_DRAFT"

    return "CURRENT_AND_SAVED" if workspace.get("saved_artifacts") else "CURRENT_READY"


def _stage_cache_bucket(stage_key: str) -> OrderedDict[str, StageResult]:
    stage_cache = st.session_state.setdefault(STAGE_CACHE_STATE_KEY, {})
    bucket = stage_cache.setdefault(stage_key, OrderedDict())
    if not isinstance(bucket, OrderedDict):
        bucket = OrderedDict(bucket)
        stage_cache[stage_key] = bucket
    return bucket


def _touch_stage_cache_entry(stage_key: str, cache_key: str) -> None:
    stage_cache = st.session_state.setdefault(STAGE_CACHE_STATE_KEY, {})
    lru: OrderedDict[tuple[str, str], None] = st.session_state.setdefault(STAGE_CACHE_LRU_KEY, OrderedDict())
    token = (stage_key, cache_key)
    lru.pop(token, None)
    lru[token] = None
    while len(lru) > STAGE_CACHE_MAX_ENTRIES:
        evicted_stage_key, evicted_cache_key = lru.popitem(last=False)[0]
        bucket = stage_cache.get(evicted_stage_key)
        if isinstance(bucket, dict):
            bucket.pop(evicted_cache_key, None)


def _build_stage_cache_key(
    *,
    context_key: str,
    stage_request_slice: dict[str, Any],
    stage_input_params_snapshot: dict[str, Any],
) -> str:
    return _hash_payload(
        {
            "context_key": context_key,
            "stage_request_slice": stage_request_slice,
            "stage_input_params_snapshot": stage_input_params_snapshot,
        }
    )


def _cached_stage(
    *,
    stage_key: str,
    context_key: str,
    stage_request_slice: dict[str, Any],
    stage_input_params_snapshot: dict[str, Any],
    builder,
) -> tuple[StageResult, bool]:
    bucket = _stage_cache_bucket(stage_key)
    cache_key = _build_stage_cache_key(
        context_key=context_key,
        stage_request_slice=stage_request_slice,
        stage_input_params_snapshot=stage_input_params_snapshot,
    )
    cached = bucket.get(cache_key)
    if cached is not None:
        bucket.move_to_end(cache_key)
        _touch_stage_cache_entry(stage_key, cache_key)
        return cached, True

    stage_result = builder()
    bucket[cache_key] = stage_result
    _touch_stage_cache_entry(stage_key, cache_key)
    return stage_result, False


def _indicator_kwargs_from_snapshot(params_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: params_snapshot[key] for key in _INDICATOR_PARAM_KEYS}


def _signal_kwargs_from_snapshot(params_snapshot: dict[str, Any]) -> dict[str, Any]:
    signal_kwargs = {key: params_snapshot[key] for key in _SIGNAL_PARAM_KEYS if key in params_snapshot}
    signal_kwargs.setdefault("hold_until_exit", False)
    signal_kwargs.setdefault("hold_min_position", 0.2)
    if not signal_kwargs.get("use_voting_entry", False):
        signal_kwargs["entry_vote_threshold"] = 2.5
    return signal_kwargs


def _sim_kwargs_from_snapshot(params_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "initial_position": 0,
        "stop_loss_mult": float(params_snapshot["stop_loss_mult"]),
        "take_profit_mult": float(params_snapshot["take_profit_mult"]),
    }


def _build_equity_series(sim_df: pd.DataFrame, name: str) -> pd.Series:
    return pd.Series(
        pd.to_numeric(sim_df["strategy_equity"], errors="coerce").to_numpy(),
        index=_build_time_index(sim_df),
        name=name,
    )


def _build_returns_series(sim_df: pd.DataFrame, name: str) -> pd.Series:
    return pd.Series(
        pd.to_numeric(sim_df["strategy_return"], errors="coerce").fillna(0.0).to_numpy(),
        index=_build_time_index(sim_df),
        name=name,
    )


def _build_stage_result_from_signal_df(
    *,
    stage_key: str,
    display_label: str,
    short_label: str,
    params_snapshot: dict[str, Any],
    full_signal_df: pd.DataFrame,
    split_idx: int,
    stop_loss_mult: float,
    take_profit_mult: float,
    initial_position: int = 0,
    upstream_stage_key: str | None = None,
    ml_quality: dict[str, float | None] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StageResult:
    train_slice = _refresh_trade_signal_columns(full_signal_df.iloc[:split_idx].copy())
    test_slice = _refresh_trade_signal_columns(full_signal_df.iloc[split_idx:].copy())
    if train_slice.empty:
        raise ValueError(tr("error.emptyTrainingSet"))
    if test_slice.empty:
        raise ValueError(tr("error.empty_test_set"))

    train_sim_df, _train_trades = simulate_strategy(
        train_slice,
        initial_position=initial_position,
        stop_loss_mult=stop_loss_mult,
        take_profit_mult=take_profit_mult,
        return_trades=True,
    )
    test_sim_df, test_trades_df = simulate_strategy(
        test_slice,
        initial_position=initial_position,
        stop_loss_mult=stop_loss_mult,
        take_profit_mult=take_profit_mult,
        return_trades=True,
    )

    benchmark_series = pd.Series(
        pd.to_numeric(test_sim_df["buy_hold_equity"], errors="coerce").to_numpy(),
        index=_build_time_index(test_sim_df),
        name="benchmark",
    )
    equity_series = _build_equity_series(test_sim_df, f"{short_label}_equity")
    returns_series = _build_returns_series(test_sim_df, f"{short_label}_returns")
    eval_result = evaluate_strategy(
        display_label,
        equity_series,
        benchmark_series,
        trades_df=test_trades_df,
    )

    return StageResult(
        stage_key=stage_key,
        display_label=display_label,
        short_label=short_label,
        params_snapshot=copy.deepcopy(params_snapshot),
        train_sim_df=train_sim_df,
        test_sim_df=test_sim_df,
        trades_df=test_trades_df,
        eval=eval_result,
        equity_series=equity_series,
        returns_series=returns_series,
        ml_quality=copy.deepcopy(ml_quality),
        upstream_stage_key=upstream_stage_key,
        full_signal_df=full_signal_df.copy(),
        metadata=copy.deepcopy(metadata or {}),
    )


def _clone_stage_result(
    stage_result: StageResult,
    *,
    stage_key: str,
    display_label: str,
    short_label: str,
    params_snapshot: dict[str, Any],
    upstream_stage_key: str | None,
    ml_quality: dict[str, float | None] | None = None,
    metadata: dict[str, Any] | None = None,
) -> StageResult:
    return StageResult(
        stage_key=stage_key,
        display_label=display_label,
        short_label=short_label,
        params_snapshot=copy.deepcopy(params_snapshot),
        train_sim_df=stage_result.train_sim_df.copy(),
        test_sim_df=stage_result.test_sim_df.copy(),
        trades_df=stage_result.trades_df.copy() if stage_result.trades_df is not None else None,
        eval=copy.deepcopy(stage_result.eval),
        equity_series=stage_result.equity_series.copy(),
        returns_series=stage_result.returns_series.copy(),
        ml_quality=copy.deepcopy(ml_quality if ml_quality is not None else stage_result.ml_quality),
        upstream_stage_key=upstream_stage_key,
        full_signal_df=stage_result.full_signal_df.copy(),
        metadata=copy.deepcopy(metadata or {}),
    )


def _build_optimizer_common_kwargs(params_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "momentum_short": params_snapshot["momentum_short"],
        "momentum_long": params_snapshot["momentum_long"],
        "score_lookback": params_snapshot["score_lookback"],
        "score_mid_pct": params_snapshot["score_mid_pct"],
        "score_high_pct": params_snapshot["score_high_pct"],
        "weight_mom_short": params_snapshot["weight_mom_short"],
        "weight_mom_long": params_snapshot["weight_mom_long"],
        "weight_macd": params_snapshot["weight_macd"],
        "weight_rsi": params_snapshot["weight_rsi"],
        "weight_vol": params_snapshot["weight_vol"],
        "use_trend_filter": params_snapshot["use_trend_filter"],
        "use_strength_filter": params_snapshot["use_strength_filter"],
        "use_rsi_filter": params_snapshot["use_rsi_filter"],
        "use_macd_filter": params_snapshot["use_macd_filter"],
        "hold_until_exit": params_snapshot.get("hold_until_exit", False),
        "hold_min_position": params_snapshot.get("hold_min_position", 0.2),
    }


def _build_regime_stage_params_snapshot(params_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "stop_loss_mult": float(params_snapshot["stop_loss_mult"]),
        "take_profit_mult": float(params_snapshot["take_profit_mult"]),
    }


def _build_adaptive_candidate_request(model_id: str) -> StrategyRequest:
    if model_id in {"naive", "mean", "drift"}:
        return StrategyRequest(family="baseline", baseline_kind=model_id)
    if model_id == "sm":
        return StrategyRequest(family="search", search_base="sm")
    if model_id == "fsm":
        return StrategyRequest(family="search", search_base="fsm")

    search_map = {
        "sm_bayesian": ("sm", "bayesian"),
        "sm_random": ("sm", "random"),
        "sm_genetic": ("sm", "genetic"),
        "fsm_bayesian": ("fsm", "bayesian"),
        "fsm_random": ("fsm", "random"),
        "fsm_genetic": ("fsm", "genetic"),
    }
    if model_id not in search_map:
        raise ValueError(f"Unsupported adaptive candidate model_id: {model_id}")

    search_base, search_method = search_map[model_id]
    return StrategyRequest(
        family="search",
        search_base=search_base,
        use_search=True,
        search_method=search_method,
    )


def _resolve_adaptive_candidate_pool(routing_summary: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    winners = dict(routing_summary.get("global_search_winners") or {})
    alias_to_model: dict[str, str] = {}
    ordered_model_ids: list[str] = []

    for alias in ADAPTIVE_ONLINE_DEFAULT_CANDIDATE_ALIASES:
        if alias == "sm_best_search":
            model_id = str(winners.get("sm_best_search") or winners.get("sm") or "sm")
        elif alias == "fsm_best_search":
            model_id = str(winners.get("fsm_best_search") or winners.get("fsm") or "fsm")
        else:
            model_id = alias
        alias_to_model[alias] = model_id
        if model_id not in ordered_model_ids:
            ordered_model_ids.append(model_id)
    return ordered_model_ids, alias_to_model


def _run_adaptive_candidate_stage(
    *,
    context_key: str,
    model_id: str,
    params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
) -> StageResult:
    request = _build_adaptive_candidate_request(model_id)
    if request.family == "baseline":
        stage_result, _cached = run_baseline_path(
            context_key=context_key,
            request=request,
            df_raw=df_raw,
            split_idx=split_idx,
        )
        return stage_result

    if request.search_base == "sm":
        base_stage, _cached = run_sm_base_stage(
            context_key=context_key,
            params_snapshot=params_snapshot,
            df_raw=df_raw,
            split_idx=split_idx,
        )
    else:
        base_stage, _cached = run_fsm_base_stage(
            context_key=context_key,
            params_snapshot=params_snapshot,
            df_raw=df_raw,
            split_idx=split_idx,
        )

    if not request.use_search:
        return base_stage

    search_stage, _cached = run_search_stage(
        context_key=context_key,
        request=request,
        upstream_stage=base_stage,
        df_raw=df_raw,
        split_idx=split_idx,
    )
    return search_stage


def _build_adaptive_candidate_day_rows(
    *,
    feature_df: pd.DataFrame,
    predicted_state_ids: pd.Series,
    candidate_stages: dict[str, StageResult],
    split_idx: int,
    symbol: str,
    segment_key: str,
) -> pd.DataFrame:
    state_frame = pd.DataFrame(
        {
            "date": pd.to_datetime(feature_df.get("date"), errors="coerce"),
            "state_id": predicted_state_ids,
            "benchmark_return": pd.to_numeric(feature_df.get("close"), errors="coerce").pct_change().fillna(0.0),
            "symbol": symbol,
            "segment_key": segment_key,
        }
    ).iloc[:split_idx].copy()
    state_frame = state_frame.dropna(subset=["date"])
    state_frame = state_frame[pd.to_numeric(state_frame["state_id"], errors="coerce").notna()].copy()
    if state_frame.empty:
        return pd.DataFrame(
            columns=["date", "state_id", "benchmark_return", "symbol", "segment_key", "model_id", "strategy_return"]
        )
    state_frame["state_id"] = state_frame["state_id"].astype(int)

    rows: list[pd.DataFrame] = []
    for model_id, stage in candidate_stages.items():
        train_returns = stage.train_sim_df.copy()
        if "date" not in train_returns.columns or "strategy_return" not in train_returns.columns:
            continue
        train_returns = train_returns[["date", "strategy_return"]].copy()
        train_returns["date"] = pd.to_datetime(train_returns["date"], errors="coerce")
        train_returns = train_returns.dropna(subset=["date"])
        merged = state_frame.merge(train_returns, on="date", how="left")
        merged["strategy_return"] = pd.to_numeric(merged["strategy_return"], errors="coerce").fillna(0.0)
        merged["model_id"] = model_id
        rows.append(
            merged[
                ["date", "state_id", "benchmark_return", "symbol", "segment_key", "model_id", "strategy_return"]
            ]
        )
    if not rows:
        return pd.DataFrame(
            columns=["date", "state_id", "benchmark_return", "symbol", "segment_key", "model_id", "strategy_return"]
        )
    return pd.concat(rows, ignore_index=True)


def _pick_best_adaptive_model(
    metrics_df: pd.DataFrame,
    *,
    scope_level: str,
    scope_key: str,
    state_id: int,
    allowed_model_ids: list[str],
) -> str | None:
    if metrics_df.empty:
        return None
    state_mask = (
        (metrics_df["scope_level"].astype(str) == scope_level)
        & (metrics_df["scope_key"].astype(str) == str(scope_key))
        & (pd.to_numeric(metrics_df["state_id"], errors="coerce") == int(state_id))
        & (metrics_df["model_id"].astype(str).isin(allowed_model_ids))
        & (pd.to_numeric(metrics_df["state_day_count"], errors="coerce") >= int(ADAPTIVE_MIN_STATE_DAYS))
    )
    subset = metrics_df.loc[state_mask].copy()
    if subset.empty:
        return None
    top = subset.sort_values(
        ["policy_score", "excess_return", "sharpe", "max_drawdown", "model_id"],
        ascending=[False, False, False, False, True],
    ).iloc[0]
    return str(top["model_id"])


def _resolve_adaptive_state_model(
    *,
    symbol: str,
    segment_key: str,
    state_id: int,
    local_metrics_df: pd.DataFrame,
    offline_metrics_df: pd.DataFrame,
    allowed_model_ids: list[str],
) -> tuple[str, str]:
    model_id = _pick_best_adaptive_model(
        local_metrics_df,
        scope_level="symbol",
        scope_key=symbol,
        state_id=state_id,
        allowed_model_ids=allowed_model_ids,
    )
    if model_id is not None:
        return model_id, "symbol"

    model_id = _pick_best_adaptive_model(
        offline_metrics_df,
        scope_level="segment",
        scope_key=segment_key,
        state_id=state_id,
        allowed_model_ids=allowed_model_ids,
    )
    if model_id is not None:
        return model_id, "segment"

    model_id = _pick_best_adaptive_model(
        offline_metrics_df,
        scope_level="global",
        scope_key="global",
        state_id=state_id,
        allowed_model_ids=allowed_model_ids,
    )
    if model_id is not None:
        return model_id, "global"

    return "mean", "fallback_mean"


def _route_adaptive_signal_frame(
    *,
    feature_df: pd.DataFrame,
    predicted_state_ids: pd.Series,
    candidate_stages: dict[str, StageResult],
    split_idx: int,
    symbol: str,
    segment_key: str,
    local_metrics_df: pd.DataFrame,
    offline_metrics_df: pd.DataFrame,
    candidate_pool_mode: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    routed_df = feature_df.reset_index(drop=True).copy()
    predicted_state_ids = pd.Series(predicted_state_ids, index=routed_df.index, dtype="Int64")
    allowed_model_ids = list(candidate_stages.keys())

    selected_model_ids: list[str] = []
    policy_sources: list[str] = []
    for state_value in predicted_state_ids:
        if pd.isna(state_value):
            selected_model_ids.append("mean")
            policy_sources.append("fallback_mean")
            continue
        model_id, policy_source = _resolve_adaptive_state_model(
            symbol=symbol,
            segment_key=segment_key,
            state_id=int(state_value),
            local_metrics_df=local_metrics_df,
            offline_metrics_df=offline_metrics_df,
            allowed_model_ids=allowed_model_ids,
        )
        if model_id not in candidate_stages:
            model_id = "mean"
            policy_source = "fallback_mean"
        selected_model_ids.append(model_id)
        policy_sources.append(policy_source)

    routed_df["predicted_state_id"] = predicted_state_ids
    routed_df["selected_model_id"] = pd.Series(selected_model_ids, index=routed_df.index, dtype="object")
    routed_df["policy_source"] = pd.Series(policy_sources, index=routed_df.index, dtype="object")
    routed_df["candidate_pool_mode"] = candidate_pool_mode
    routed_df["execution_regime"] = pd.Series(
        [
            f"state_{int(state_value)}" if not pd.isna(state_value) else "state_unknown"
            for state_value in predicted_state_ids
        ],
        index=routed_df.index,
        dtype="object",
    )
    routed_df["target_position"] = 0.0

    for model_id, stage in candidate_stages.items():
        candidate_signal_df = stage.full_signal_df.reset_index(drop=True).copy()
        if len(candidate_signal_df) != len(routed_df):
            raise ValueError(f"Adaptive candidate {model_id} returned a mismatched signal length.")
        mask = routed_df["selected_model_id"] == model_id
        if not bool(mask.any()):
            continue
        candidate_positions = pd.to_numeric(candidate_signal_df["target_position"], errors="coerce").fillna(0.0)
        routed_df.loc[mask, "target_position"] = candidate_positions.loc[mask].to_numpy()

    routed_df = _refresh_trade_signal_columns(routed_df)

    test_slice = routed_df.iloc[split_idx:].copy()
    latest_row = routed_df.iloc[-1] if not routed_df.empty else pd.Series(dtype="object")
    metadata = {
        "predicted_state_id": int(latest_row["predicted_state_id"]) if pd.notna(latest_row.get("predicted_state_id")) else None,
        "selected_model_id": str(latest_row.get("selected_model_id") or "mean"),
        "policy_source": str(latest_row.get("policy_source") or "fallback_mean"),
        "candidate_pool_mode": candidate_pool_mode,
        "segment_key": segment_key,
        "state_distribution": normalize_distribution(test_slice["execution_regime"]) if not test_slice.empty else {},
        "model_usage_distribution": normalize_distribution(test_slice["selected_model_id"]) if not test_slice.empty else {},
        "policy_source_distribution": normalize_distribution(test_slice["policy_source"]) if not test_slice.empty else {},
    }
    return routed_df, metadata


def _build_legacy_regime_stage_result(
    *,
    request: StrategyRequest,
    stage_params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
    market: str,
    adjust: str,
) -> StageResult:
    full_signal_df, regime_metadata = compute_regime_signals(
        df_raw,
        split_idx=split_idx,
        adjust=adjust,
        regime_kind=request.regime_kind or "dual_state_router",
        market=market,
    )
    sim_kwargs = _sim_kwargs_from_snapshot(stage_params_snapshot)
    effective_snapshot = {
        **stage_params_snapshot,
        "market": market,
        "adjust": adjust,
        "regime_kind": request.regime_kind,
    }
    stage_result = _build_stage_result_from_signal_df(
        stage_key="regime",
        display_label="Regime (Experimental)",
        short_label="Regime",
        params_snapshot=effective_snapshot,
        full_signal_df=full_signal_df,
        split_idx=split_idx,
        stop_loss_mult=sim_kwargs["stop_loss_mult"],
        take_profit_mult=sim_kwargs["take_profit_mult"],
        initial_position=sim_kwargs["initial_position"],
        upstream_stage_key=None,
        metadata={
            **copy.deepcopy(regime_metadata),
            "family": "regime",
            "regime_kind": request.regime_kind,
            "run_status": "success",
        },
    )
    regime_summary = summarize_regime_diagnostics(
        stage_result.full_signal_df,
        sim_df=stage_result.test_sim_df,
        market_proxy_symbol=str(regime_metadata.get("market_proxy_symbol") or "SPY"),
        market_proxy_mode=str(regime_metadata.get("market_proxy_mode") or "enabled"),
        market_proxy_unavailable=bool(regime_metadata.get("market_proxy_unavailable")),
        market_proxy_warning=(
            str(regime_metadata["market_proxy_warning"])
            if regime_metadata.get("market_proxy_warning")
            else None
        ),
    )
    stage_result.metadata["regime_summary"] = regime_summary
    if regime_metadata.get("market_proxy_warning"):
        stage_result.metadata.setdefault("warning_messages", []).append(str(regime_metadata["market_proxy_warning"]))
    return stage_result


def _merge_effective_params(
    params_snapshot: dict[str, Any],
    optimizer_result: SearchOptimizationResult,
) -> dict[str, Any]:
    effective = copy.deepcopy(params_snapshot)
    for key, value in optimizer_result.best_params.items():
        effective[key] = value
    return effective


def _build_baseline_signal_frame(df_raw: pd.DataFrame, baseline_kind: str, split_idx: int) -> pd.DataFrame:
    baseline_df = df_raw.copy()
    baseline_df["atr"] = compute_atr(baseline_df, period=14)

    if baseline_kind == "naive":
        baseline_df["target_position"] = 1.0
    elif baseline_kind == "mean":
        baseline_df["target_position"] = mean_target_position(baseline_df, window=60)
    elif baseline_kind == "drift":
        baseline_df["target_position"] = drift_target_position(baseline_df, split_idx=split_idx)
    else:
        raise ValueError(f"未知 baseline_kind: {baseline_kind}")

    return _refresh_trade_signal_columns(baseline_df)


def run_baseline_path(
    *,
    context_key: str,
    request: StrategyRequest,
    df_raw: pd.DataFrame,
    split_idx: int,
) -> tuple[StageResult, bool]:
    label_map = {
        "naive": (tr("strategy.naiveBuyAndHold"), "Naive", 1),
        "mean": (tr("baseline.mean"), "Mean", 0),
        "drift": (tr("metric.driftBaseline"), "Drift", 0),
    }
    if request.baseline_kind not in label_map:
        raise ValueError(tr("baseline.path.invalidKind"))

    display_label, short_label, initial_position = label_map[request.baseline_kind]
    params_snapshot = {
        "baseline_kind": request.baseline_kind,
        "stop_loss_mult": 0.0,
        "take_profit_mult": 0.0,
    }

    return _cached_stage(
        stage_key="baseline",
        context_key=context_key,
        stage_request_slice={"family": "baseline", "baseline_kind": request.baseline_kind},
        stage_input_params_snapshot={},
        builder=lambda: _build_stage_result_from_signal_df(
            stage_key="baseline",
            display_label=display_label,
            short_label=short_label,
            params_snapshot=params_snapshot,
            full_signal_df=_build_baseline_signal_frame(df_raw, request.baseline_kind, split_idx),
            split_idx=split_idx,
            stop_loss_mult=0.0,
            take_profit_mult=0.0,
            initial_position=initial_position,
            upstream_stage_key=None,
            metadata={"family": "baseline", "baseline_kind": request.baseline_kind},
        ),
    )


def run_sm_base_stage(
    *,
    context_key: str,
    params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
) -> tuple[StageResult, bool]:
    def _builder() -> StageResult:
        df_indicators = add_indicators(df_raw, **_indicator_kwargs_from_snapshot(params_snapshot))
        full_signal_df = compute_signals(df_indicators, **_signal_kwargs_from_snapshot(params_snapshot))
        sim_kwargs = _sim_kwargs_from_snapshot(params_snapshot)
        return _build_stage_result_from_signal_df(
            stage_key="sm_base",
            display_label=tr("model.sm_basic"),
            short_label="SM",
            params_snapshot=params_snapshot,
            full_signal_df=full_signal_df,
            split_idx=split_idx,
            stop_loss_mult=sim_kwargs["stop_loss_mult"],
            take_profit_mult=sim_kwargs["take_profit_mult"],
            initial_position=sim_kwargs["initial_position"],
            upstream_stage_key=None,
            metadata={"family": "search", "search_base": "sm"},
        )

    return _cached_stage(
        stage_key="sm_base",
        context_key=context_key,
        stage_request_slice={"family": "search", "search_base": "sm"},
        stage_input_params_snapshot=params_snapshot,
        builder=_builder,
    )


def run_fsm_base_stage(
    *,
    context_key: str,
    params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
) -> tuple[StageResult, bool]:
    def _builder() -> StageResult:
        df_indicators = add_indicators(df_raw, **_indicator_kwargs_from_snapshot(params_snapshot))
        signal_kwargs = _signal_kwargs_from_snapshot(params_snapshot)
        manual_signal_df = compute_signals(df_indicators, **signal_kwargs)
        fa_model = fit_fa(manual_signal_df.iloc[:split_idx].copy())
        fsm_signal_df = compute_signals(
            df_indicators,
            **signal_kwargs,
            fsm_mode=True,
            fa_model=fa_model,
        )
        effective_snapshot = copy.deepcopy(params_snapshot)
        effective_snapshot["fa_n_components"] = int(fa_model.n_components)
        sim_kwargs = _sim_kwargs_from_snapshot(params_snapshot)
        return _build_stage_result_from_signal_df(
            stage_key="fsm_base",
            display_label=tr("model.fsmBase"),
            short_label="FSM",
            params_snapshot=effective_snapshot,
            full_signal_df=fsm_signal_df,
            split_idx=split_idx,
            stop_loss_mult=sim_kwargs["stop_loss_mult"],
            take_profit_mult=sim_kwargs["take_profit_mult"],
            initial_position=sim_kwargs["initial_position"],
            upstream_stage_key=None,
            metadata={
                "family": "search",
                "search_base": "fsm",
                "fa_n_components": int(fa_model.n_components),
            },
        )

    return _cached_stage(
        stage_key="fsm_base",
        context_key=context_key,
        stage_request_slice={"family": "search", "search_base": "fsm"},
        stage_input_params_snapshot=params_snapshot,
        builder=_builder,
    )


def run_regime_stage(
    *,
    context_key: str,
    request: StrategyRequest,
    params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
    market: str = "US",
    adjust: str = "qfq",
) -> tuple[StageResult, bool]:
    if request.regime_kind is None:
        raise ValueError(tr("regime.missing_kind"))

    stage_params_snapshot = _build_regime_stage_params_snapshot(params_snapshot)
    # The legacy router only consumes execution-risk parameters, while the
    # adaptive router builds SM/FSM/search candidates from the complete
    # frozen request.  Reusing an adaptive final stage after an indicator or
    # signal change would otherwise return a stale routed result.
    cache_input_params_snapshot = (
        params_snapshot
        if request.regime_kind == ADAPTIVE_REGIME_KIND
        else stage_params_snapshot
    )

    def _builder() -> StageResult:
        if request.regime_kind != ADAPTIVE_REGIME_KIND:
            return _build_legacy_regime_stage_result(
                request=request,
                stage_params_snapshot=stage_params_snapshot,
                df_raw=df_raw,
                split_idx=split_idx,
                market=market,
                adjust=adjust,
            )

        try:
            adaptive_artifacts = load_adaptive_regime_artifacts(expected_market=market)
            feature_df, feature_metadata = build_adaptive_feature_frame(
                df_raw,
                adjust=adjust,
                market=market,
            )
            predicted_state_ids = predict_adaptive_states(
                feature_df,
                adaptive_artifacts["state_classifier_bundle"],
            )
            candidate_model_ids, alias_to_model = _resolve_adaptive_candidate_pool(
                adaptive_artifacts["routing_policy_summary"]
            )
            candidate_stages = {
                model_id: _run_adaptive_candidate_stage(
                    context_key=context_key,
                    model_id=model_id,
                    params_snapshot=params_snapshot,
                    df_raw=df_raw,
                    split_idx=split_idx,
                )
                for model_id in candidate_model_ids
            }

            bucket_rules = dict(
                adaptive_artifacts["routing_policy_summary"].get("segment_bucket_rules") or {}
            )
            segment_key = classify_segment_key(df_raw, bucket_rules)
            candidate_day_rows = _build_adaptive_candidate_day_rows(
                feature_df=feature_df,
                predicted_state_ids=predicted_state_ids,
                candidate_stages=candidate_stages,
                split_idx=split_idx,
                symbol=str(context_key),
                segment_key=segment_key,
            )
            local_metrics_df = score_candidate_state_metrics(
                aggregate_candidate_state_day_rows(
                    candidate_day_rows,
                    scope_level="symbol",
                    scope_key_column="symbol",
                )
            )
            offline_metrics_df = adaptive_artifacts["candidate_state_metrics"].copy()
            routed_signal_df, adaptive_metadata = _route_adaptive_signal_frame(
                feature_df=feature_df,
                predicted_state_ids=predicted_state_ids,
                candidate_stages=candidate_stages,
                split_idx=split_idx,
                symbol=str(context_key),
                segment_key=segment_key,
                local_metrics_df=local_metrics_df,
                offline_metrics_df=offline_metrics_df,
                candidate_pool_mode="default",
            )

            sim_kwargs = _sim_kwargs_from_snapshot(stage_params_snapshot)
            effective_snapshot = {
                **stage_params_snapshot,
                "market": market,
                "adjust": adjust,
                "regime_kind": request.regime_kind,
            }
            stage_result = _build_stage_result_from_signal_df(
                stage_key="regime",
                display_label="Adaptive Router V1",
                short_label="Adaptive",
                params_snapshot=effective_snapshot,
                full_signal_df=routed_signal_df,
                split_idx=split_idx,
                stop_loss_mult=sim_kwargs["stop_loss_mult"],
                take_profit_mult=sim_kwargs["take_profit_mult"],
                initial_position=sim_kwargs["initial_position"],
                upstream_stage_key=None,
                metadata={
                    **copy.deepcopy(feature_metadata),
                    **copy.deepcopy(adaptive_metadata),
                    "family": "regime",
                    "regime_kind": request.regime_kind,
                    "adaptive_artifact_dir": str(adaptive_artifacts["artifact_dir"]),
                    "adaptive_alias_to_model": alias_to_model,
                    "global_search_winners": adaptive_artifacts["routing_policy_summary"].get("global_search_winners", {}),
                    "run_status": "success",
                },
            )
            regime_summary = summarize_regime_diagnostics(
                stage_result.full_signal_df,
                sim_df=stage_result.test_sim_df,
                market_proxy_symbol=str(feature_metadata.get("market_proxy_symbol") or "SPY"),
                market_proxy_mode=str(feature_metadata.get("market_proxy_mode") or "enabled"),
                market_proxy_unavailable=bool(feature_metadata.get("market_proxy_unavailable")),
                market_proxy_warning=(
                    str(feature_metadata["market_proxy_warning"])
                    if feature_metadata.get("market_proxy_warning")
                    else None
                ),
            )
            regime_summary.update(
                {
                    "candidate_pool_mode": adaptive_metadata["candidate_pool_mode"],
                    "segment_key": adaptive_metadata["segment_key"],
                    "latest_selected_model_id": adaptive_metadata["selected_model_id"],
                    "latest_predicted_state_id": adaptive_metadata["predicted_state_id"],
                    "latest_policy_source": adaptive_metadata["policy_source"],
                    "state_distribution": adaptive_metadata["state_distribution"],
                    "model_usage_distribution": adaptive_metadata["model_usage_distribution"],
                    "policy_source_distribution": adaptive_metadata["policy_source_distribution"],
                }
            )
            stage_result.metadata["regime_summary"] = regime_summary
            if feature_metadata.get("market_proxy_warning"):
                stage_result.metadata.setdefault("warning_messages", []).append(str(feature_metadata["market_proxy_warning"]))
            return stage_result
        except Exception as exc:
            fallback_request = StrategyRequest(family="regime", regime_kind="dual_state_router")
            fallback_stage = _build_legacy_regime_stage_result(
                request=fallback_request,
                stage_params_snapshot=stage_params_snapshot,
                df_raw=df_raw,
                split_idx=split_idx,
                market=market,
                adjust=adjust,
            )
            warning = f"adaptive_router_v1 artifact fallback -> dual_state_router: {exc}"
            fallback_stage.display_label = "Adaptive Router V1"
            fallback_stage.short_label = "Adaptive"
            fallback_stage.metadata.update(
                {
                    "regime_kind": request.regime_kind,
                    "requested_regime_kind": request.regime_kind,
                    "effective_regime_kind": "dual_state_router",
                    "run_status": "degraded",
                    "adaptive_fallback_reason": str(exc),
                }
            )
            fallback_stage.metadata.setdefault("warning_messages", []).append(warning)
            if isinstance(fallback_stage.metadata.get("regime_summary"), dict):
                fallback_stage.metadata["regime_summary"]["latest_selected_model_id"] = "dual_state_router"
                fallback_stage.metadata["regime_summary"]["latest_policy_source"] = "fallback_mean"
            return fallback_stage

    return _cached_stage(
        stage_key="regime",
        context_key=context_key,
        stage_request_slice={"family": "regime", "regime_kind": request.regime_kind},
        stage_input_params_snapshot=cache_input_params_snapshot,
        builder=_builder,
    )


def _run_parameter_search(
    *,
    request: StrategyRequest,
    params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
) -> SearchOptimizationResult:
    common_kwargs = _build_optimizer_common_kwargs(params_snapshot)
    evaluation_cache = SearchEvaluationCache(
        df_raw=df_raw,
        split_idx=split_idx,
        common_kwargs=common_kwargs,
        fsm_mode=request.search_base == "fsm",
    )
    optimizer_kwargs = {
        "df_raw": df_raw,
        "split_idx": split_idx,
        "fsm_mode": request.search_base == "fsm",
        "evaluation_cache": evaluation_cache,
        **common_kwargs,
    }

    seed_params, _seed_name, _seed_scores = evaluate_presets_for_optimization(**optimizer_kwargs)
    search_method = request.search_method or "bayesian"

    if search_method == "bayesian":
        result = bayesian_optimize_params(
            n_trials=int(request.search_trials),
            seed_params=seed_params or None,
            **optimizer_kwargs,
        )
    elif search_method == "genetic":
        result = genetic_algorithm_optimize_params(
            population_size=int(request.ga_population_size),
            generations=int(request.ga_generations),
            seed_params=seed_params or None,
            **optimizer_kwargs,
        )
    elif search_method == "random":
        result = random_search_params(
            n_trials=int(request.search_trials),
            seed_params=seed_params or None,
            **optimizer_kwargs,
        )
    else:
        raise ValueError(f"未知 search_method: {search_method}")

    if not result:
        raise ValueError(tr("paramSearch.noValidResults"))
    return result


def run_search_stage(
    *,
    context_key: str,
    request: StrategyRequest,
    upstream_stage: StageResult,
    df_raw: pd.DataFrame,
    split_idx: int,
) -> tuple[StageResult, bool]:
    if not request.use_search:
        raise ValueError(tr("strategy.param_search_disabled"))

    stage_request_slice = {
        "family": "search",
        "search_base": request.search_base,
        "use_search": True,
        "search_method": request.search_method,
        "search_trials": int(request.search_trials),
        "ga_population_size": int(request.ga_population_size),
        "ga_generations": int(request.ga_generations),
        "upstream_stage_key": upstream_stage.stage_key,
    }

    def _builder() -> StageResult:
        optimizer_result = _run_parameter_search(
            request=request,
            params_snapshot=upstream_stage.params_snapshot,
            df_raw=df_raw,
            split_idx=split_idx,
        )
        effective_snapshot = _merge_effective_params(upstream_stage.params_snapshot, optimizer_result)
        display_label = "SM+Search" if request.search_base == "sm" else "FSM+Search"
        short_label = display_label
        sim_kwargs = _sim_kwargs_from_snapshot(effective_snapshot)
        return _build_stage_result_from_signal_df(
            stage_key="search",
            display_label=display_label,
            short_label=short_label,
            params_snapshot=effective_snapshot,
            full_signal_df=optimizer_result.full_signal_df,
            split_idx=split_idx,
            stop_loss_mult=sim_kwargs["stop_loss_mult"],
            take_profit_mult=sim_kwargs["take_profit_mult"],
            initial_position=sim_kwargs["initial_position"],
            upstream_stage_key=upstream_stage.stage_key,
            metadata={
                "optimizer_result": optimizer_result.to_metadata(),
                "search_method": request.search_method,
            },
        )

    return _cached_stage(
        stage_key="search",
        context_key=context_key,
        stage_request_slice=stage_request_slice,
        stage_input_params_snapshot=upstream_stage.params_snapshot,
        builder=_builder,
    )


def _build_ml_display_label(request: StrategyRequest, upstream_stage: StageResult) -> tuple[str, str]:
    base_prefix = "FSM" if request.search_base == "fsm" else "SM"
    if upstream_stage.stage_key in {"search", "news"}:
        if upstream_stage.stage_key == "news":
            ml_suffix = "ML-LGBM" if request.ml_model_type == "lgbm" else "ML-LR"
            return f"{upstream_stage.display_label}+{ml_suffix}", f"{upstream_stage.short_label}+{ml_suffix}"
        base_prefix = f"{base_prefix}+Search"

    ml_suffix = "ML-LGBM" if request.ml_model_type == "lgbm" else "ML-LR"
    display_label = f"{base_prefix}+{ml_suffix}"
    return display_label, display_label


def _build_news_display_label(upstream_stage: StageResult) -> tuple[str, str]:
    base_label = upstream_stage.display_label
    base_short = upstream_stage.short_label
    if upstream_stage.stage_key == "sm_base":
        base_label = "SM"
        base_short = "SM"
    elif upstream_stage.stage_key == "fsm_base":
        base_label = "FSM"
        base_short = "FSM"
    return f"{base_label}+News", f"{base_short}+News"


def run_news_stage(
    *,
    context_key: str,
    request: StrategyRequest,
    upstream_stage: StageResult,
    split_idx: int,
    symbol: str | None = None,
) -> tuple[StageResult, bool]:
    if not request.use_news:
        raise ValueError("News Fusion is disabled for this request")

    news_factor_path = request.news_factor_path or DEFAULT_NEWS_FACTOR_PATH
    stage_request_slice = {
        "family": "search",
        "search_base": request.search_base,
        "use_news": True,
        "news_fusion_mode": request.news_fusion_mode,
        "news_factor_path": news_factor_path,
        "news_weight": float(request.news_weight),
        "news_lookback": int(request.news_lookback),
        "upstream_stage_key": upstream_stage.stage_key,
    }

    def _builder() -> StageResult:
        fused_signal_df, news_metadata = apply_news_fusion(
            upstream_stage.full_signal_df.copy(),
            news_factor_path=news_factor_path,
            symbol=symbol,
            news_weight=float(request.news_weight),
            news_lookback=int(request.news_lookback),
            split_idx=split_idx,
            score_mid_pct=float(upstream_stage.params_snapshot.get("score_mid_pct", 0.60)),
            score_high_pct=float(upstream_stage.params_snapshot.get("score_high_pct", 0.80)),
        )
        effective_snapshot = copy.deepcopy(upstream_stage.params_snapshot)
        effective_snapshot.update(
            {
                "use_news": True,
                "news_fusion_mode": request.news_fusion_mode,
                "news_factor_path": news_factor_path,
                "news_weight": float(request.news_weight),
                "news_lookback": int(request.news_lookback),
            }
        )
        display_label, short_label = _build_news_display_label(upstream_stage)
        sim_kwargs = _sim_kwargs_from_snapshot(upstream_stage.params_snapshot)
        return _build_stage_result_from_signal_df(
            stage_key="news",
            display_label=display_label,
            short_label=short_label,
            params_snapshot=effective_snapshot,
            full_signal_df=fused_signal_df,
            split_idx=split_idx,
            stop_loss_mult=sim_kwargs["stop_loss_mult"],
            take_profit_mult=sim_kwargs["take_profit_mult"],
            initial_position=sim_kwargs["initial_position"],
            upstream_stage_key=upstream_stage.stage_key,
            metadata=news_metadata,
        )

    return _cached_stage(
        stage_key="news",
        context_key=context_key,
        stage_request_slice=stage_request_slice,
        stage_input_params_snapshot=upstream_stage.params_snapshot,
        builder=_builder,
    )


def run_ml_stage(
    *,
    context_key: str,
    request: StrategyRequest,
    upstream_stage: StageResult,
    split_idx: int,
) -> tuple[StageResult, bool]:
    if not request.use_ml:
        raise ValueError(tr("ml.filter_disabled"))

    stage_request_slice = {
        "family": "search",
        "search_base": request.search_base,
        "use_ml": True,
        "ml_model_type": request.ml_model_type,
        "ml_horizon_days": int(request.ml_horizon_days),
        "ml_min_excess_samples": int(request.ml_min_excess_samples),
        "upstream_stage_key": upstream_stage.stage_key,
    }

    def _builder() -> StageResult:
        full_signal_df = _refresh_trade_signal_columns(upstream_stage.full_signal_df.copy())
        feature_bundle = build_feature_bundle(
            full_signal_df,
            horizon=int(request.ml_horizon_days),
            min_excess_samples=int(request.ml_min_excess_samples),
        )
        train_features = build_feature_view(
            feature_bundle,
            max_signal_pos=split_idx,
            label_boundary_limit=split_idx,
        )
        if train_features.empty or train_features["ml_label"].notna().sum() == 0:
            raise ValueError(tr("error.mlTrainingDataEmpty"))

        ml_model = fit_ml_filter(
            train_features,
            train_features["ml_label"],
            model_type=request.ml_model_type or "logistic",
        )

        full_features = build_feature_view(feature_bundle)
        filtered_full_signal_df = apply_filter(
            full_signal_df.copy(),
            ml_model,
            feature_df=full_features if not full_features.empty else None,
        )

        test_features = build_feature_view(
            feature_bundle,
            min_signal_pos=split_idx,
        )
        if test_features.empty:
            ml_quality = evaluate_ml_quality([], [], threshold=ml_model.threshold)
        else:
            test_proba = predict_filter(ml_model, test_features)
            ml_quality = evaluate_ml_quality(
                test_features["ml_label"],
                test_proba,
                threshold=ml_model.threshold,
            )

        display_label, short_label = _build_ml_display_label(request, upstream_stage)
        sim_kwargs = _sim_kwargs_from_snapshot(upstream_stage.params_snapshot)
        return _build_stage_result_from_signal_df(
            stage_key="ml",
            display_label=display_label,
            short_label=short_label,
            params_snapshot=upstream_stage.params_snapshot,
            full_signal_df=filtered_full_signal_df,
            split_idx=split_idx,
            stop_loss_mult=sim_kwargs["stop_loss_mult"],
            take_profit_mult=sim_kwargs["take_profit_mult"],
            initial_position=sim_kwargs["initial_position"],
            upstream_stage_key=upstream_stage.stage_key,
            ml_quality=ml_quality,
            metadata={
                "ml_model_type": request.ml_model_type,
                "threshold": float(ml_model.threshold),
                "ml_horizon_days": int(request.ml_horizon_days),
                "ml_min_excess_samples": int(request.ml_min_excess_samples),
            },
        )

    return _cached_stage(
        stage_key="ml",
        context_key=context_key,
        stage_request_slice=stage_request_slice,
        stage_input_params_snapshot=upstream_stage.params_snapshot,
        builder=_builder,
    )


def assemble_strategy_artifact(
    *,
    context_key: str,
    request: StrategyRequest,
    request_params_snapshot: dict[str, Any],
    lineage: list[StageResult],
) -> StrategyArtifact:
    final_stage = lineage[-1]
    artifact_id = _hash_payload(
        {
            "context_key": context_key,
            "request": asdict(request),
            # ``request_signature`` already treats this snapshot as the
            # strategy identity.  Include it here too so display-cache and
            # strategy-library IDs cannot collide when a final stage exposes
            # only a reduced execution snapshot (notably adaptive regime).
            "request_params_snapshot": request_params_snapshot,
            "params_snapshot": final_stage.params_snapshot,
            "display_label": final_stage.display_label,
        },
        prefix="artifact_",
    )
    return StrategyArtifact(
        id=artifact_id,
        context_key=context_key,
        display_label=final_stage.display_label,
        pipeline_lineage=list(lineage),
        params_snapshot=copy.deepcopy(final_stage.params_snapshot),
        train_sim_df=final_stage.train_sim_df.copy(),
        test_sim_df=final_stage.test_sim_df.copy(),
        trades_df=final_stage.trades_df.copy() if final_stage.trades_df is not None else None,
        eval=copy.deepcopy(final_stage.eval),
        equity_series=final_stage.equity_series.copy(),
        returns_series=final_stage.returns_series.copy(),
        ml_quality=copy.deepcopy(final_stage.ml_quality),
        full_signal_df=final_stage.full_signal_df.copy(),
        request_signature=build_request_signature(request, request_params_snapshot),
    )


def _validate_request(request: StrategyRequest) -> None:
    if request.family == "baseline":
        if request.baseline_kind not in {"naive", "mean", "drift"}:
            raise ValueError(tr("rule.baselineFamilyRequired"))
        if (
            request.use_search
            or request.use_ml
            or request.use_news
            or request.search_base
            or request.regime_kind
            or request.search_method
            or request.ml_model_type
        ):
            raise ValueError(tr("restriction.baselineNoEnhancements"))
        return

    if request.family == "regime":
        if request.regime_kind not in {"dual_state_router", "no_market", "no_router", ADAPTIVE_REGIME_KIND}:
            raise ValueError(tr("validation.regimePath"))
        if request.baseline_kind or request.search_base or request.use_search or request.use_ml or request.use_news:
            raise ValueError(tr("regime.path.restriction.noBaselineSearchML"))
        if request.search_method or request.ml_model_type:
            raise ValueError(tr("regime.path.restriction.noSearchML"))
        return

    if request.family != "search":
        raise ValueError(tr("validation.familyParam"))
    if request.search_base not in {"sm", "fsm"}:
        raise ValueError(tr("search.path_required"))
    if request.use_search and request.search_method not in {"bayesian", "genetic", "random"}:
        raise ValueError(tr("validation.param_search_method_required"))
    if request.use_ml and request.ml_model_type not in {"logistic", "lgbm"}:
        raise ValueError(tr("validation.mlModelRequired"))
    if request.use_news:
        if request.news_fusion_mode != NEWS_FUSION_MODE:
            raise ValueError("News Fusion v1 only supports residual_gate mode")
        if not (request.news_factor_path or DEFAULT_NEWS_FACTOR_PATH):
            raise ValueError("News Fusion requires a news factor CSV path")
        if int(request.news_lookback) <= 1:
            raise ValueError("news_lookback must be greater than 1")
    if int(request.ml_horizon_days) <= 0:
        raise ValueError(tr("validation.mlHorizonDays"))
    if int(request.ml_min_excess_samples) <= 0:
        raise ValueError(tr("validation.ml_min_excess_samples"))


def run_strategy_pipeline(
    *,
    context_key: str,
    request: StrategyRequest,
    request_params_snapshot: dict[str, Any],
    df_raw: pd.DataFrame,
    split_idx: int,
    symbol: str | None = None,
    market: str = "US",
    adjust: str = "qfq",
) -> PipelineRunResult:
    try:
        _validate_request(request)
    except Exception as exc:
        return PipelineRunResult(
            artifact=None,
            status="failed",
            error_message=str(exc),
        )

    lineage: list[StageResult] = []
    cache_messages: list[str] = []
    success_warnings: list[str] = []

    try:
        if request.family == "baseline":
            baseline_stage, baseline_cached = run_baseline_path(
                context_key=context_key,
                request=request,
                df_raw=df_raw,
                split_idx=split_idx,
            )
            lineage.append(baseline_stage)
            if baseline_cached:
                cache_messages.append(tr("baseline.cache_hit"))
        elif request.family == "regime":
            regime_stage, regime_cached = run_regime_stage(
                context_key=context_key,
                request=request,
                params_snapshot=request_params_snapshot,
                df_raw=df_raw,
                split_idx=split_idx,
                market=market,
                adjust=adjust,
            )
            lineage.append(regime_stage)
            if regime_cached:
                cache_messages.append(tr("regime.cache_hit"))
            success_warnings.extend([str(item) for item in regime_stage.metadata.get("warning_messages", [])])
            final_status = "degraded" if regime_stage.metadata.get("run_status") == "degraded" else "success"
            artifact = assemble_strategy_artifact(
                context_key=context_key,
                request=request,
                request_params_snapshot=request_params_snapshot,
                lineage=lineage,
            )
            return PipelineRunResult(
                artifact=artifact,
                status=final_status,
                warnings=success_warnings,
                info_messages=cache_messages,
            )
        else:
            if request.search_base == "sm":
                latest_stage, base_cached = run_sm_base_stage(
                    context_key=context_key,
                    params_snapshot=request_params_snapshot,
                    df_raw=df_raw,
                    split_idx=split_idx,
                )
            else:
                latest_stage, base_cached = run_fsm_base_stage(
                    context_key=context_key,
                    params_snapshot=request_params_snapshot,
                    df_raw=df_raw,
                    split_idx=split_idx,
                )
            lineage.append(latest_stage)
            if base_cached:
                cache_messages.append(f"{latest_stage.display_label} 命中缓存。")

            warnings: list[str] = []
            if request.use_search:
                try:
                    latest_stage, search_cached = run_search_stage(
                        context_key=context_key,
                        request=request,
                        upstream_stage=latest_stage,
                        df_raw=df_raw,
                        split_idx=split_idx,
                    )
                    lineage.append(latest_stage)
                    if search_cached:
                        cache_messages.append(tr("paramSearch.cacheHit"))
                except Exception as exc:
                    warnings.append(f"参数搜索失败，已回退到基础策略：{exc}")
                    artifact = assemble_strategy_artifact(
                        context_key=context_key,
                        request=request,
                        request_params_snapshot=request_params_snapshot,
                        lineage=lineage,
                    )
                    return PipelineRunResult(
                        artifact=artifact,
                        status="degraded",
                        warnings=warnings,
                        info_messages=cache_messages,
                    )

            if request.use_news:
                try:
                    latest_stage, news_cached = run_news_stage(
                        context_key=context_key,
                        request=request,
                        upstream_stage=latest_stage,
                        split_idx=split_idx,
                        symbol=symbol,
                    )
                    lineage.append(latest_stage)
                    if news_cached:
                        cache_messages.append("News Fusion 命中缓存。")
                except Exception as exc:
                    warnings = [f"News Fusion 失败，已保留最近一步成功结果：{exc}"]
                    artifact = assemble_strategy_artifact(
                        context_key=context_key,
                        request=request,
                        request_params_snapshot=request_params_snapshot,
                        lineage=lineage,
                    )
                    return PipelineRunResult(
                        artifact=artifact,
                        status="degraded",
                        warnings=warnings,
                        info_messages=cache_messages,
                    )

            if request.use_ml:
                try:
                    latest_stage, ml_cached = run_ml_stage(
                        context_key=context_key,
                        request=request,
                        upstream_stage=latest_stage,
                        split_idx=split_idx,
                    )
                    lineage.append(latest_stage)
                    if ml_cached:
                        cache_messages.append(tr("ml.cache.hit"))
                except Exception as exc:
                    warnings = [f"ML 失败，已保留最近一步成功结果：{exc}"]
                    artifact = assemble_strategy_artifact(
                        context_key=context_key,
                        request=request,
                        request_params_snapshot=request_params_snapshot,
                        lineage=lineage,
                    )
                    return PipelineRunResult(
                        artifact=artifact,
                        status="degraded",
                        warnings=warnings,
                        info_messages=cache_messages,
                    )

        artifact = assemble_strategy_artifact(
            context_key=context_key,
            request=request,
            request_params_snapshot=request_params_snapshot,
            lineage=lineage,
        )
        return PipelineRunResult(
            artifact=artifact,
            status="success",
            warnings=success_warnings,
            info_messages=cache_messages,
        )
    except Exception as exc:
        return PipelineRunResult(
            artifact=None,
            status="failed",
            error_message=str(exc),
            info_messages=cache_messages,
        )


def build_lineage_model_payloads(artifact: StrategyArtifact | None) -> dict[str, dict[str, Any]]:
    if artifact is None:
        return {}

    color_map = {
        "baseline": "#c8ae7d",
        "sm_base": "#2f5d62",
        "fsm_base": "#8f3b2e",
        "search": "#f39c12",
        "ml": "#7d5a9e",
        "news": "#256d85",
        "regime": "#18636c",
    }

    payload: dict[str, dict[str, Any]] = {}
    lineage_length = len(artifact.pipeline_lineage)
    for idx, stage in enumerate(artifact.pipeline_lineage):
        payload[stage.display_label] = {
            "label": stage.display_label,
            "short_label": stage.short_label,
            "eval": copy.deepcopy(stage.eval),
            "equity_series": stage.equity_series.copy(),
            "returns_series": stage.returns_series.copy(),
            "color": color_map.get(stage.stage_key, "#2f5d62"),
            "dash": "solid" if idx == lineage_length - 1 else "dash",
            "sim_df": stage.test_sim_df.copy(),
            "trades_df": stage.trades_df.copy() if stage.trades_df is not None else None,
            "ml_quality": copy.deepcopy(stage.ml_quality),
        }
    return payload


__all__ = [
    "PipelineRunResult",
    "STAGE_CACHE_STATE_KEY",
    "StrategyArtifact",
    "StrategyRequest",
    "WORKSPACE_STATE_KEY",
    "assemble_strategy_artifact",
    "build_lineage_model_payloads",
    "build_request_signature",
    "build_strategy_context_key",
    "commit_current_artifact",
    "ensure_strategy_workspace",
    "freeze_params_snapshot",
    "get_strategy_workspace",
    "get_workspace_status",
    "run_strategy_pipeline",
    "save_current_artifact",
]
