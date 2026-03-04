"""
core 包 — 量化策略核心逻辑
============================
提供统一的公共 API，方便 ``from core import ...`` 一行导入。
"""

from core.config import (
    DATA_DIR,
    DEFAULT_SYMBOL,
    DEFAULT_ADJUST,
    DEFAULT_STOCKS,
    STRATEGY_PRESETS,
    _PRESET_PARAMS_FOR_OPTIMIZATION,
)
from core.data import (
    standardize_columns,
    ensure_date_column,
    fetch_data,
    load_csv,
    load_uploaded_bytes,
)
from core.indicators import (
    compute_rsi,
    rolling_zscore,
    rolling_percentile,
    compute_macd,
    compute_atr,
    compute_adx,
    compute_bollinger_bands,
    compute_obv,
    rolling_rank,
    add_indicators,
)
from core.signals import compute_signals
from core.backtest import (
    simulate_strategy,
    max_drawdown,
    sharpe_ratio,
    walk_forward_backtest,
)
from core.optimizer import (
    evaluate_presets_for_optimization,
    random_search_params,
    bayesian_optimize_params,
    genetic_algorithm_optimize_params,
)
from core.utils import (
    format_pct,
    load_or_fetch_stock,
    get_available_stocks,
    normalize_prices,
)
from core.visualization import (
    create_multi_stock_comparison_chart,
    create_correlation_heatmap,
    create_relative_strength_chart,
    create_risk_return_scatter,
    create_periodic_returns_heatmap,
    create_factor_score_comparison,
)
from core.portfolio import (
    run_portfolio_simulation,
    bayesian_optimize_portfolio,
)
