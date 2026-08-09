"""
core 包 - 量化策略核心逻辑
=========================
提供兼容旧版 ``from core import ...`` 的 lazy 公共 API。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MAP = {
    # config
    "DATA_DIR": "core.config",
    "DEFAULT_SYMBOL": "core.config",
    "DEFAULT_ADJUST": "core.config",
    "DEFAULT_STOCKS": "core.config",
    "STRATEGY_PRESETS": "core.config",
    "_PRESET_PARAMS_FOR_OPTIMIZATION": "core.config",
    # data
    "standardize_columns": "core.data",
    "ensure_date_column": "core.data",
    "fetch_data": "core.data",
    "fetch_a_stock": "core.data",
    "get_stock_label_map": "core.data",
    "load_a_stock_catalog": "core.data",
    "load_us_stock_catalog": "core.data",
    "load_csv": "core.data",
    "load_uploaded_bytes": "core.data",
    "search_stock_candidates": "core.data",
    "search_a_stock_candidates": "core.data",
    # indicators
    "compute_rsi": "core.indicators",
    "rolling_zscore": "core.indicators",
    "rolling_percentile": "core.indicators",
    "compute_macd": "core.indicators",
    "compute_atr": "core.indicators",
    "compute_adx": "core.indicators",
    "compute_bollinger_bands": "core.indicators",
    "compute_obv": "core.indicators",
    "rolling_rank": "core.indicators",
    "add_indicators": "core.indicators",
    # FA / ML
    "FAModel": "core.fa_filter",
    "fit_fa": "core.fa_filter",
    "transform_fa": "core.fa_filter",
    "MLModel": "core.ml_filter",
    "build_feature_table": "core.ml_filter",
    "fit_ml_filter": "core.ml_filter",
    "predict_filter": "core.ml_filter",
    "apply_filter": "core.ml_filter",
    "evaluate_ml_quality": "core.ml_filter",
    # strategy chain
    "compute_signals": "core.signals",
    "simulate_strategy": "core.backtest",
    "max_drawdown": "core.backtest",
    "sharpe_ratio": "core.backtest",
    "walk_forward_backtest": "core.backtest",
    # optimizer
    "evaluate_presets_for_optimization": "core.optimizer",
    "random_search_params": "core.optimizer",
    "bayesian_optimize_params": "core.optimizer",
    "genetic_algorithm_optimize_params": "core.optimizer",
    # utils
    "format_pct": "core.utils",
    "load_or_fetch_stock": "core.utils",
    "get_available_stocks": "core.utils",
    "normalize_prices": "core.utils",
    # visualization
    "create_multi_stock_comparison_chart": "core.visualization",
    "create_correlation_heatmap": "core.visualization",
    "create_relative_strength_chart": "core.visualization",
    "create_risk_return_scatter": "core.visualization",
    "create_periodic_returns_heatmap": "core.visualization",
    "create_factor_score_comparison": "core.visualization",
    # portfolio
    "run_portfolio_simulation": "core.portfolio",
    "bayesian_optimize_portfolio": "core.portfolio",
    # baselines
    "naive_baseline": "core.baselines",
    "mean_baseline": "core.baselines",
    "drift_baseline": "core.baselines",
    "run_all_baselines": "core.baselines",
    # evaluation
    "compute_performance_metrics": "core.evaluation",
    "compute_trade_stats": "core.evaluation",
    "evaluate_strategy": "core.evaluation",
    "build_comparison_table": "core.evaluation",
}

_MODULE_EXPORTS = {
    "adaptive_regime",
    "backtest",
    "baselines",
    "config",
    "data",
    "evaluation",
    "fa_filter",
    "indicators",
    "market_context",
    "market_rules",
    "ml_filter",
    "news_factor",
    "optimizer",
    "perf",
    "portfolio",
    "regime_model",
    "signals",
    "utils",
    "visualization",
}

__all__ = tuple(sorted(_EXPORT_MAP))


def __getattr__(name: str) -> Any:
    if name in _MODULE_EXPORTS:
        value = import_module(f"core.{name}")
        globals()[name] = value
        return value

    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *__all__])
