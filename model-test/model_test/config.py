from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.adaptive_regime import ADAPTIVE_MODEL_ID, ADAPTIVE_REGIME_KIND
from core.config import STRATEGY_PRESETS
from ui.single_stock_workflow import freeze_params_snapshot

from model_test.models import ModelSpec, ResearchConfig, WindowSpec


DEFAULT_SMOKE_SYMBOLS = (
    "AAPL",
    "TSLA",
    "NVDA",
    "GOOGL",
    "META",
    "ORCL",
    "ADM",
    "NTR",
    "CTVA",
)

DEFAULT_SCORE_WEIGHTS = {
    "beat_naive_rate": 20.0,
    "median_excess_return": 15.0,
    "median_sharpe": 15.0,
    "drawdown_control": 15.0,
    "stability": 20.0,
    "overfit_discipline": 10.0,
    "reliability": 5.0,
}

DEFAULT_ROBUSTNESS_WEIGHT = 0.4
DEFAULT_SEARCH_SEED = 42


def recommended_parallelism() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, min(12, cpu_count // 2 or 1))


def resolve_parallelism(raw_value: Any) -> int:
    if raw_value is None:
        return recommended_parallelism()
    if isinstance(raw_value, str) and raw_value.strip().lower() == "auto":
        return recommended_parallelism()
    try:
        parsed = int(raw_value)
    except Exception as exc:
        raise ValueError(f"Invalid parallelism value: {raw_value!r}") from exc
    if parsed <= 0:
        return recommended_parallelism()
    return parsed


def resolve_universe_parallelism(raw_value: Any, parallelism: int) -> int:
    default_value = min(16, max(4, int(parallelism)))
    if raw_value is None:
        return default_value
    if isinstance(raw_value, str) and raw_value.strip().lower() == "auto":
        return default_value
    try:
        parsed = int(raw_value)
    except Exception as exc:
        raise ValueError(f"Invalid universe_parallelism value: {raw_value!r}") from exc
    if parsed <= 0:
        return default_value
    return parsed


def load_research_config(config_path: str | Path) -> ResearchConfig:
    path = Path(config_path)
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    parallelism = resolve_parallelism(raw.get("parallelism", 0))
    mlflow_tracking_uri = raw.get("mlflow_tracking_uri")
    if isinstance(mlflow_tracking_uri, str) and not mlflow_tracking_uri.strip():
        mlflow_tracking_uri = None

    merged: dict[str, Any] = {
        "name": raw.get("name", path.stem),
        "market": raw.get("market", "US"),
        "adjust": raw.get("adjust", "qfq"),
        "preset_name": raw.get("preset_name", "__balanced_default__"),
        "train_ratio": raw.get("train_ratio", 0.7),
        "parallelism": parallelism,
        "output_subdir": raw.get("output_subdir", path.stem),
        "enable_mlflow": raw.get("enable_mlflow", False),
        "mlflow_experiment_name": raw.get("mlflow_experiment_name", "strategy-model-test"),
        "mlflow_tracking_uri": mlflow_tracking_uri,
        "enable_quantstats": raw.get("enable_quantstats", False),
        "quantstats_top_n": raw.get("quantstats_top_n", 5),
        "sample_data_dir": raw.get("sample_data_dir", "data"),
        "catalog_path": raw.get("catalog_path", "core/catalogs/us_stock_catalog.csv"),
        "smoke_symbols": tuple(raw.get("smoke_symbols", DEFAULT_SMOKE_SYMBOLS)),
        "smoke_mode": raw.get("smoke_mode", False),
        "run_stage_b": raw.get("run_stage_b", True),
        "run_robustness": raw.get("run_robustness", True),
        "main_window_days": raw.get("main_window_days", 756),
        "minimum_window_days": raw.get("minimum_window_days", 252),
        "allow_short_main_window": raw.get("allow_short_main_window", False),
        "rolling_window_days": raw.get("rolling_window_days", 504),
        "rolling_step_days": raw.get("rolling_step_days", 126),
        "rolling_window_count": raw.get("rolling_window_count", 3),
        "robustness_top_n": raw.get("robustness_top_n", 8),
        "main_pool_size": raw.get("main_pool_size", 60),
        "min_history_days": raw.get("min_history_days", 750),
        "profile_lookback_days": raw.get("profile_lookback_days", 252),
        "min_avg_dollar_volume": raw.get("min_avg_dollar_volume", 10_000_000.0),
        "max_catalog_candidates": raw.get("max_catalog_candidates", 500),
        "cache_dir": raw.get("cache_dir", "model-test/cache"),
        "universe_parallelism": resolve_universe_parallelism(raw.get("universe_parallelism"), parallelism),
        "search_trials": raw.get("search_trials", 60),
        "ga_population_size": raw.get("ga_population_size", 30),
        "ga_generations": raw.get("ga_generations", 20),
        "robustness_weight": float(raw.get("robustness_weight", DEFAULT_ROBUSTNESS_WEIGHT)),
        "score_weights": {**DEFAULT_SCORE_WEIGHTS, **raw.get("score_weights", {})},
        "request_params_overrides": dict(raw.get("request_params_overrides", {})),
        "stage_b_request_overrides": dict(raw.get("stage_b_request_overrides", {})),
        "selected_model_ids": tuple(str(item) for item in raw.get("selected_model_ids", []) if str(item).strip()),
        "merge_into_existing_output": bool(raw.get("merge_into_existing_output", False)),
    }
    config = ResearchConfig(**merged)
    if config.market.upper() != "US":
        raise ValueError("V1 research runner currently supports US market only.")
    return config


def build_search_budget_summary(
    *,
    search_trials: int,
    ga_population_size: int,
    ga_generations: int,
) -> dict[str, Any]:
    search_trials = int(search_trials)
    ga_population_size = int(ga_population_size)
    ga_generations = int(ga_generations)
    genetic_total_evals = ga_population_size * (ga_generations + 1)
    return {
        "random_trials": search_trials,
        "bayesian_trials": search_trials,
        "ga_population_size": ga_population_size,
        "ga_generations": ga_generations,
        "ga_total_evals": genetic_total_evals,
        "effective_search_budget": min(search_trials, genetic_total_evals),
        "uniform_objective_budget": (
            search_trials == genetic_total_evals
        ),
        "search_seed": DEFAULT_SEARCH_SEED,
    }


def build_config_search_budget_summary(config: ResearchConfig) -> dict[str, Any]:
    return build_search_budget_summary(
        search_trials=config.search_trials,
        ga_population_size=config.ga_population_size,
        ga_generations=config.ga_generations,
    )


def resolve_preset_name(preset_name: str | None) -> str:
    keys = list(STRATEGY_PRESETS.keys())
    if not keys:
        raise ValueError("STRATEGY_PRESETS is empty.")
    if preset_name in STRATEGY_PRESETS:
        return str(preset_name)

    alias_map = {
        None: keys[1] if len(keys) > 1 else keys[0],
        "__balanced_default__": keys[1] if len(keys) > 1 else keys[0],
        "__conservative_trend__": keys[0],
        "__aggressive_breakout__": keys[2] if len(keys) > 2 else keys[0],
        "__custom__": keys[-1],
    }
    if preset_name in alias_map:
        return alias_map[preset_name]
    raise ValueError(f"Unknown preset alias: {preset_name}")


def build_request_params_snapshot(config: ResearchConfig) -> dict[str, Any]:
    preset_name = resolve_preset_name(config.preset_name)
    preset = dict(STRATEGY_PRESETS[preset_name])
    preset.update(
        {
            "strategy_preset": preset_name,
            "use_trend_filter": True,
            "use_strength_filter": True,
            "use_rsi_filter": True,
            "use_macd_filter": True,
            "use_voting_entry": False,
            "entry_vote_threshold": 2.5,
        }
    )
    preset.update(config.request_params_overrides)
    return freeze_params_snapshot(preset)


def build_stage_a_model_specs(config: ResearchConfig) -> list[ModelSpec]:
    specs = [
        ModelSpec("naive", "Naive", "A", "baseline", {"family": "baseline", "baseline_kind": "naive"}),
        ModelSpec("mean", "Mean", "A", "baseline", {"family": "baseline", "baseline_kind": "mean"}),
        ModelSpec("drift", "Drift", "A", "baseline", {"family": "baseline", "baseline_kind": "drift"}),
        ModelSpec("sm", "SM", "A", "sm", {"family": "search", "search_base": "sm"}),
        ModelSpec("fsm", "FSM", "A", "fsm", {"family": "search", "search_base": "fsm"}),
        ModelSpec(
            "rsm",
            "RSM",
            "A",
            "rsm",
            {"family": "regime", "regime_kind": "dual_state_router"},
        ),
        ModelSpec(
            "rsm_no_market",
            "RSM-NoMarket",
            "A",
            "rsm",
            {"family": "regime", "regime_kind": "no_market"},
            notes="Research-only ablation without SPY proxy",
        ),
        ModelSpec(
            "rsm_no_router",
            "RSM-NoRouter",
            "A",
            "rsm",
            {"family": "regime", "regime_kind": "no_router"},
            notes="Research-only ablation without dual-state router",
        ),
        ModelSpec(
            ADAPTIVE_MODEL_ID,
            "RSM-AdaptiveV1",
            "A",
            "rsm",
            {"family": "regime", "regime_kind": ADAPTIVE_REGIME_KIND},
            notes="Adaptive regime router with offline state artifacts and online local fallback hierarchy",
        ),
        ModelSpec(
            "sm_bayesian",
            "SM+Bayesian",
            "A",
            "sm",
            {
                "family": "search",
                "search_base": "sm",
                "use_search": True,
                "search_method": "bayesian",
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
            },
        ),
        ModelSpec(
            "sm_random",
            "SM+Random",
            "A",
            "sm",
            {
                "family": "search",
                "search_base": "sm",
                "use_search": True,
                "search_method": "random",
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
            },
        ),
        ModelSpec(
            "sm_genetic",
            "SM+Genetic",
            "A",
            "sm",
            {
                "family": "search",
                "search_base": "sm",
                "use_search": True,
                "search_method": "genetic",
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
            },
        ),
        ModelSpec(
            "fsm_bayesian",
            "FSM+Bayesian",
            "A",
            "fsm",
            {
                "family": "search",
                "search_base": "fsm",
                "use_search": True,
                "search_method": "bayesian",
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
            },
        ),
        ModelSpec(
            "fsm_random",
            "FSM+Random",
            "A",
            "fsm",
            {
                "family": "search",
                "search_base": "fsm",
                "use_search": True,
                "search_method": "random",
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
            },
        ),
        ModelSpec(
            "fsm_genetic",
            "FSM+Genetic",
            "A",
            "fsm",
            {
                "family": "search",
                "search_base": "fsm",
                "use_search": True,
                "search_method": "genetic",
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
            },
        ),
    ]
    if not config.selected_model_ids:
        return specs
    selected = set(config.selected_model_ids)
    return [spec for spec in specs if spec.model_id in selected]


def build_stage_b_model_specs(config: ResearchConfig, winners: dict[str, str]) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    for base_key in ("sm", "fsm"):
        winner_model_id = winners.get(base_key)
        if not winner_model_id or "_" not in winner_model_id:
            continue
        _base_prefix, search_method = winner_model_id.split("_", 1)
        for ml_model_type, ml_suffix in (("logistic", "ML-LR"), ("lgbm", "ML-LGBM")):
            request_payload = {
                "family": "search",
                "search_base": base_key,
                "use_search": True,
                "search_method": search_method,
                "search_trials": config.search_trials,
                "ga_population_size": config.ga_population_size,
                "ga_generations": config.ga_generations,
                "use_ml": True,
                "ml_model_type": ml_model_type,
            }
            request_payload.update(config.stage_b_request_overrides)
            specs.append(
                ModelSpec(
                    f"{winner_model_id}_ml_{ml_model_type}",
                    f"{base_key.upper()}+{search_method.title()}+{ml_suffix}",
                    "B",
                    base_key,
                    request_payload,
                    notes=f"Stage B extension of {winner_model_id}",
                )
            )
    if not config.selected_model_ids:
        return specs
    selected = set(config.selected_model_ids)
    return [spec for spec in specs if spec.model_id in selected]


def build_main_window(config: ResearchConfig, df_len: int) -> WindowSpec:
    if df_len >= config.main_window_days:
        return WindowSpec(
            window_id="main",
            kind="main",
            start_idx=df_len - config.main_window_days,
            end_idx=df_len,
            train_ratio=config.train_ratio,
        )
    if config.allow_short_main_window and df_len >= config.minimum_window_days:
        return WindowSpec(
            window_id="main",
            kind="main",
            start_idx=0,
            end_idx=df_len,
            train_ratio=config.train_ratio,
        )
    return WindowSpec(
        window_id="main",
        kind="main",
        start_idx=0,
        end_idx=max(df_len, 0),
        train_ratio=config.train_ratio,
        available=False,
        reason=(
            f"needs {config.main_window_days} rows"
            if not config.allow_short_main_window
            else f"needs at least {config.minimum_window_days} rows"
        ),
    )


def build_rolling_windows(config: ResearchConfig, df_len: int) -> list[WindowSpec]:
    windows: list[WindowSpec] = []
    for ordinal in range(config.rolling_window_count):
        offset = config.rolling_window_count - ordinal - 1
        end_idx = df_len - offset * config.rolling_step_days
        start_idx = end_idx - config.rolling_window_days
        if start_idx < 0 or end_idx > df_len:
            windows.append(
                WindowSpec(
                    window_id=f"rolling_{ordinal + 1}",
                    kind="rolling",
                    start_idx=0,
                    end_idx=0,
                    train_ratio=config.train_ratio,
                    available=False,
                    reason=f"needs rolling window {ordinal + 1} with {config.rolling_window_days} rows",
                )
            )
            continue
        windows.append(
            WindowSpec(
                window_id=f"rolling_{ordinal + 1}",
                kind="rolling",
                start_idx=start_idx,
                end_idx=end_idx,
                train_ratio=config.train_ratio,
            )
        )
    return windows
