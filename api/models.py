"""Validated public request models for the Strategy API."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyRequestInput(StrictModel):
    family: Literal["baseline", "search", "regime", "composite"]
    baseline_kind: Literal["naive", "mean", "drift"] | None = None
    search_base: Literal["sm", "fsm"] | None = None
    regime_kind: Literal["dual_state_router", "no_market", "no_router", "adaptive_router_v1"] | None = None
    use_search: bool = False
    search_method: Literal["bayesian", "genetic", "random"] | None = None
    use_ml: bool = False
    use_news: bool = False
    news_fusion_mode: Literal["residual_gate"] = "residual_gate"
    news_weight: float = Field(default=0.4, ge=0.0, le=2.0)
    news_lookback: int = Field(default=20, ge=2, le=252)
    ml_model_type: Literal["logistic", "lgbm"] | None = None
    ml_horizon_days: int = Field(default=10, ge=1, le=252)
    ml_min_excess_samples: int = Field(default=20, ge=1, le=10_000)
    search_trials: int = Field(default=60, ge=1, le=240)
    ga_population_size: int = Field(default=30, ge=4, le=100)
    ga_generations: int = Field(default=20, ge=1, le=100)
    composite_policy: Literal[
        "composite_only", "composite_plus_trend", "composite_plus_reversion",
        "composite_plus_relative_strength", "composite_plus_macro_cap",
        "composite_plus_all_advisories",
    ] = "composite_only"
    composite_risk_budget: float = Field(default=1.0, gt=0.0, le=1.0)
    composite_position_method: Literal["linear_clip", "tanh_smooth", "quantile_5bin"] = "linear_clip"


class StockLoadRequest(StrictModel):
    market: Literal["US", "CN_A", "A"] = "US"
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.^_-]+$")
    adjust: Literal["qfq", "hfq", "none"] = "qfq"
    start_date: str | None = None
    end_date: str | None = None
    force_refresh: bool = False


class DatasetSliceRequest(StrictModel):
    start_date: str | None = None
    end_date: str | None = None


class DatasetAnalysisRequest(DatasetSliceRequest):
    period: Literal['D', 'W', 'M'] = 'D'
    train_ratio: float = Field(default=.7, ge=.6, le=.9)
    params: dict[str, Any] = Field(default_factory=dict)


class SingleJobRequest(StrictModel):
    dataset_id: str = Field(min_length=20, max_length=128)
    train_ratio: float = Field(default=0.7, ge=0.5, le=0.9)
    request: StrategyRequestInput
    params: dict[str, Any] = Field(default_factory=dict)


class PortfolioRequest(StrictModel):
    dataset_ids: list[str] = Field(min_length=2, max_length=20)
    weights: dict[str, float] | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_weights(self) -> "PortfolioRequest":
        if self.weights is not None:
            if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in self.weights.values()):
                raise ValueError("weights must be finite non-negative numbers")
            total = sum(self.weights.values())
            if not math.isfinite(total) or total <= 0:
                raise ValueError("weights must have a finite positive sum")
        return self


class PortfolioOptimizeRequest(PortfolioRequest):
    n_trials: int = Field(default=30, ge=5, le=100)


class CampaignStartRequest(StrictModel):
    campaign_id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
