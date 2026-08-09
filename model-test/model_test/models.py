from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal


StageName = Literal["A", "B"]
WindowKind = Literal["main", "rolling"]


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def row_dict(instance: Any) -> dict[str, Any]:
    data = asdict(instance)
    for key, value in list(data.items()):
        if isinstance(value, Path):
            data[key] = str(value)
    return data


@dataclass(frozen=True)
class ResearchConfig:
    name: str
    market: str = "US"
    adjust: str = "qfq"
    preset_name: str = "__balanced_default__"
    train_ratio: float = 0.7
    parallelism: int = 2
    output_subdir: str = "us_v1"
    enable_mlflow: bool = False
    mlflow_experiment_name: str = "strategy-model-test"
    mlflow_tracking_uri: str | None = None
    enable_quantstats: bool = False
    quantstats_top_n: int = 5
    sample_data_dir: str = "data"
    catalog_path: str = "core/catalogs/us_stock_catalog.csv"
    smoke_symbols: tuple[str, ...] = ()
    smoke_mode: bool = False
    run_stage_b: bool = True
    run_robustness: bool = True
    main_window_days: int = 756
    minimum_window_days: int = 252
    allow_short_main_window: bool = False
    rolling_window_days: int = 504
    rolling_step_days: int = 126
    rolling_window_count: int = 3
    robustness_top_n: int = 8
    main_pool_size: int = 60
    min_history_days: int = 750
    profile_lookback_days: int = 252
    min_avg_dollar_volume: float = 10_000_000.0
    # Kept for compatibility with existing US configs.  Unlike the legacy name,
    # this threshold is measured in the market's native traded-value currency.
    min_avg_traded_value: float | None = None
    market_proxy_symbol: str | None = None
    max_catalog_candidates: int = 500
    candidate_selection_mode: str = "head"
    candidate_selection_seed: int = 42
    cache_dir: str = "model-test/cache"
    universe_parallelism: int = 4
    search_trials: int = 60
    ga_population_size: int = 30
    ga_generations: int = 20
    robustness_weight: float = 0.4
    score_weights: dict[str, float] = field(default_factory=dict)
    request_params_overrides: dict[str, Any] = field(default_factory=dict)
    stage_b_request_overrides: dict[str, Any] = field(default_factory=dict)
    selected_model_ids: tuple[str, ...] = ()
    merge_into_existing_output: bool = False
    commission_bps: float | None = None
    slippage_bps: float | None = None
    cross_market_source_subdirs: dict[str, str] = field(default_factory=dict)
    freeze_data_snapshot: bool = False
    minimum_data_end_date: str | None = None
    require_clean_worktree: bool = False
    lightgbm_device_type: str = "cpu"
    lightgbm_gpu_platform_id: int = 0
    lightgbm_gpu_device_id: int = 0
    lightgbm_gpu_use_dp: bool = False

    def __post_init__(self) -> None:
        market_aliases = {"US": "US", "CN_A": "CN_A", "CN": "CN_A", "A": "CN_A"}
        market = str(self.market or "").strip().upper()
        if market not in market_aliases:
            raise ValueError(f"Unsupported market: {self.market!r}. Expected US or CN_A.")
        canonical_market = market_aliases[market]
        object.__setattr__(self, "market", canonical_market)
        if not self.market_proxy_symbol:
            object.__setattr__(self, "market_proxy_symbol", "SPY" if canonical_market == "US" else "000300")
        from core.market_rules import MarketExecutionConfig, default_execution_config

        defaults = default_execution_config(canonical_market)
        commission_bps = defaults.commission_bps if self.commission_bps is None else float(self.commission_bps)
        slippage_bps = defaults.slippage_bps if self.slippage_bps is None else float(self.slippage_bps)
        execution = MarketExecutionConfig(canonical_market, commission_bps, slippage_bps)
        object.__setattr__(self, "commission_bps", execution.commission_bps)
        object.__setattr__(self, "slippage_bps", execution.slippage_bps)
        selection_mode = str(self.candidate_selection_mode or "head").strip().lower()
        if selection_mode not in {"head", "hybrid"}:
            raise ValueError("candidate_selection_mode must be 'head' or 'hybrid'.")
        object.__setattr__(self, "candidate_selection_mode", selection_mode)
        if self.minimum_data_end_date:
            try:
                normalized_end_date = date.fromisoformat(str(self.minimum_data_end_date)).isoformat()
            except ValueError as exc:
                raise ValueError("minimum_data_end_date must use YYYY-MM-DD format.") from exc
            object.__setattr__(self, "minimum_data_end_date", normalized_end_date)
        from core.lightgbm_runtime import normalize_lightgbm_device

        object.__setattr__(
            self,
            "lightgbm_device_type",
            normalize_lightgbm_device(self.lightgbm_device_type),
        )

    @property
    def effective_min_avg_traded_value(self) -> float:
        if self.min_avg_traded_value is not None:
            return float(self.min_avg_traded_value)
        if self.market == "CN_A":
            return 50_000_000.0
        return float(self.min_avg_dollar_volume)

    def to_dict(self) -> dict[str, Any]:
        return row_dict(self)

    @property
    def execution(self) -> dict[str, float | str]:
        return {
            "market": self.market,
            "commission_bps": float(self.commission_bps or 0.0),
            "slippage_bps": float(self.slippage_bps or 0.0),
        }

    @property
    def compute(self) -> dict[str, object]:
        return {
            "parallelism": int(self.parallelism),
            "lightgbm_device_type": self.lightgbm_device_type,
            "lightgbm_gpu_platform_id": int(self.lightgbm_gpu_platform_id),
            "lightgbm_gpu_device_id": int(self.lightgbm_gpu_device_id),
            "lightgbm_gpu_use_dp": bool(self.lightgbm_gpu_use_dp),
        }

    @property
    def is_cross_market_aggregation(self) -> bool:
        return bool(self.cross_market_source_subdirs)


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    stage: StageName
    family_group: str
    request_payload: dict[str, Any]
    notes: str = ""
    supported_markets: tuple[str, ...] = ("US", "CN_A")
    unsupported_market_reasons: dict[str, str] = field(default_factory=dict)

    def skip_reason_for_market(self, market: str) -> str | None:
        normalized_market = str(market).strip().upper()
        if normalized_market == "CN":
            normalized_market = "CN_A"
        if normalized_market in self.supported_markets:
            return None
        return self.unsupported_market_reasons.get(
            normalized_market,
            f"{self.model_id} is not supported for market {normalized_market}.",
        )

    def build_request(self):
        from ui.single_stock_workflow import StrategyRequest

        return StrategyRequest(**self.request_payload)

    def to_dict(self) -> dict[str, Any]:
        return row_dict(self)


@dataclass(frozen=True)
class WindowSpec:
    window_id: str
    kind: WindowKind
    start_idx: int
    end_idx: int
    train_ratio: float
    available: bool = True
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return row_dict(self)


@dataclass(frozen=True)
class TaskSpec:
    symbol: str
    company_name: str
    segment_key: str
    trend_bucket: str
    volatility_bucket: str
    source_kind: str
    data_path: str
    market: str
    adjust: str
    model: ModelSpec
    window: WindowSpec
    params_snapshot: dict[str, Any]
    skip_reason: str | None = None
    execution: dict[str, float | str] | None = None


@dataclass
class StockProfile:
    symbol: str
    company_name: str
    source_kind: str
    data_path: str
    history_days: int
    recent_days: int
    total_return_1y: float | None
    annualized_vol_1y: float | None
    max_drawdown_1y: float | None
    avg_dollar_volume_1y: float | None
    trend_bucket: str = "Unknown"
    volatility_bucket: str = "Unknown"
    segment_key: str = "Unknown__Unknown"

    def to_row(self) -> dict[str, Any]:
        return row_dict(self)


@dataclass
class RunRecord:
    symbol: str
    company_name: str
    segment_key: str
    trend_bucket: str
    volatility_bucket: str
    source_kind: str
    data_path: str
    window_id: str
    window_kind: WindowKind
    window_start: str | None
    window_end: str | None
    window_days: int | None
    stage: StageName
    model_id: str
    display_name: str
    family_group: str
    status: str
    error_message: str | None = None
    warning_count: int = 0
    warnings_json: str = "[]"
    info_messages_json: str = "[]"
    lineage_json: str = "[]"
    params_snapshot_json: str = "{}"
    metadata_json: str = "{}"
    ml_quality_json: str = "{}"
    artifact_id: str | None = None
    artifact_dir: str | None = None
    returns_path: str | None = None
    benchmark_returns_path: str | None = None
    equity_path: str | None = None
    trades_path: str | None = None
    train_cumret: float | None = None
    train_annret: float | None = None
    train_maxdd: float | None = None
    train_sharpe: float | None = None
    test_cumret: float | None = None
    test_annret: float | None = None
    test_maxdd: float | None = None
    test_sharpe: float | None = None
    test_winrate: float | None = None
    test_pnl_ratio: float | None = None
    test_turnover: float | None = None
    test_excess_return: float | None = None
    ml_precision: float | None = None
    ml_recall: float | None = None
    ml_f1: float | None = None
    ml_pr_auc: float | None = None
    ml_signal_pass_rate: float | None = None
    train_test_gap: float | None = None
    total_turnover: float | None = None
    total_transaction_cost: float | None = None
    gross_total_return: float | None = None
    net_total_return: float | None = None

    def to_row(self) -> dict[str, Any]:
        return row_dict(self)


@dataclass
class ModelAggregate:
    model_id: str
    display_name: str
    family_group: str
    stage: StageName
    attempted_count: int
    valid_count: int
    success_rate: float
    degraded_rate: float
    beat_naive_rate: float | None
    median_annret: float | None
    median_excess_return: float | None
    median_sharpe: float | None
    median_maxdd: float | None
    annret_iqr: float | None
    sharpe_iqr: float | None
    median_train_test_gap: float | None
    reliability_raw: float
    beat_naive_score: float
    excess_return_score: float
    sharpe_score: float
    drawdown_score: float
    stability_score: float
    overfit_score: float
    reliability_score: float
    main_total_score: float
    total_score: float
    rank: int
    robustness_attempted_count: int | None = None
    robustness_valid_count: int | None = None
    robustness_success_rate: float | None = None
    robustness_degraded_rate: float | None = None
    robustness_median_annret: float | None = None
    robustness_median_excess_return: float | None = None
    robustness_median_sharpe: float | None = None
    robustness_median_maxdd: float | None = None
    robustness_annret_iqr: float | None = None
    robustness_sharpe_iqr: float | None = None
    robustness_reliability_raw: float | None = None
    robustness_excess_return_score: float | None = None
    robustness_sharpe_score: float | None = None
    robustness_drawdown_score: float | None = None
    robustness_stability_score: float | None = None
    robustness_reliability_score: float | None = None
    robustness_total_score: float | None = None

    def to_row(self) -> dict[str, Any]:
        return row_dict(self)
