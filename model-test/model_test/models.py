from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
    max_catalog_candidates: int = 500
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

    def to_dict(self) -> dict[str, Any]:
        return row_dict(self)


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    stage: StageName
    family_group: str
    request_payload: dict[str, Any]
    notes: str = ""

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
