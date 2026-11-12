"""CN_A Composite: market-native factor weights and long-only position mapping.

This module provides CN_A-specific composite scoring that:
- Trains weights independently on CN_A data (no US weight copy)
- Uses long-only position semantics (no short exposure)
- Supports train-only weight fitting with validation/test holdout
- Outputs immutable decisions with full audit trail
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CNCompositeWeights:
    """CN_A Composite 权重配置（不可变）"""

    factors: dict[str, float]
    interaction_terms: dict[str, float] | None
    fit_method: str
    train_folds: list[str]
    market: Literal["CN_A"]
    position_policy: Literal["long_only"]
    version: str

    def compute_score(self, factor_df: pd.DataFrame) -> pd.Series:
        """计算 composite score，不修改输入。

        Args:
            factor_df: DataFrame with factors as columns

        Returns:
            Series of composite scores
        """
        if factor_df.empty:
            return pd.Series(dtype=float, index=factor_df.index)

        # Main effects
        score = pd.Series(0.0, index=factor_df.index)
        for factor, weight in self.factors.items():
            if factor in factor_df.columns:
                score = score + weight * factor_df[factor].fillna(0.0)

        # Interaction terms
        if self.interaction_terms:
            for term, weight in self.interaction_terms.items():
                parts = term.split("_x_")
                if len(parts) == 2 and all(p in factor_df.columns for p in parts):
                    interaction = factor_df[parts[0]].fillna(0.0) * factor_df[parts[1]].fillna(0.0)
                    score = score + weight * interaction

        return score


@dataclass(frozen=True)
class CNCompositeDecision:
    """CN_A Composite 决策记录（不可变）"""

    date: pd.Timestamp
    symbol: str
    market: Literal["CN_A"]
    composite_score: float
    composite_base_position: float
    final_position: float
    risk_budget: float
    position_method: str
    fallback_used: bool
    fallback_reason: str | None
    factors_used: tuple[str, ...]
    weights_version: str


def map_score_to_long_only_position(
    score: pd.Series,
    *,
    risk_budget: float = 1.0,
    method: Literal["linear_clip", "tanh_smooth", "quantile_5bin"] = "linear_clip",
    quantile_thresholds: tuple[float, ...] | None = None,
) -> pd.Series:
    """将 composite score 映射到 long-only position [0, risk_budget]。

    Args:
        score: Composite scores
        risk_budget: Maximum position size
        method: Mapping method
        quantile_thresholds: Quantile thresholds for binning (method=quantile_5bin)

    Returns:
        Series of positions in [0, risk_budget]
    """
    if score.empty:
        return pd.Series(dtype=float, index=score.index)

    if method == "linear_clip":
        # Normalize score to [0, 1] range, then scale to [0, risk_budget]
        score_min = score.min()
        score_max = score.max()
        if score_max > score_min:
            normalized = (score - score_min) / (score_max - score_min)
        else:
            normalized = pd.Series(0.5, index=score.index)
        position = normalized * risk_budget

    elif method == "tanh_smooth":
        # Use tanh for smooth mapping: tanh(score/2) maps to [-1, 1], shift to [0, 1]
        normalized = (np.tanh(score / 2.0) + 1.0) / 2.0
        position = normalized * risk_budget

    elif method == "quantile_5bin":
        # 5-bin quantile mapping
        if quantile_thresholds is None:
            quantile_thresholds = (0.2, 0.4, 0.6, 0.8)
        bins = [0.0, 0.25, 0.5, 0.75, 1.0]
        position = pd.cut(
            score.rank(pct=True),
            bins=[0.0] + list(quantile_thresholds) + [1.0],
            labels=bins,
            include_lowest=True,
        ).astype(float) * risk_budget

    else:
        raise ValueError(f"Unknown method: {method}")

    return position.clip(0.0, risk_budget)


def fit_cn_composite_weights(
    factor_panel: pd.DataFrame,
    target_returns: pd.Series,
    *,
    factor_cols: list[str],
    interaction_terms: list[tuple[str, str]] | None = None,
    method: Literal["ridge", "lasso", "elastic_net"] = "ridge",
    alpha: float = 1.0,
    max_abs_weight: float = 2.0,
) -> dict[str, float]:
    """在 CN_A train fold 上拟合 composite 权重。

    Args:
        factor_panel: Factor DataFrame (train only)
        target_returns: Target returns (train only)
        factor_cols: List of factor columns to use
        interaction_terms: List of (factor1, factor2) tuples for interactions
        method: Regularization method
        alpha: Regularization strength
        max_abs_weight: Maximum absolute weight value

    Returns:
        Dictionary of factor weights
    """
    from sklearn.linear_model import Ridge, Lasso, ElasticNet
    from sklearn.preprocessing import StandardScaler

    # Prepare features
    X = factor_panel[factor_cols].copy()

    # Add interaction terms
    interaction_names = []
    if interaction_terms:
        for f1, f2 in interaction_terms:
            if f1 in X.columns and f2 in X.columns:
                interaction_name = f"{f1}_x_{f2}"
                X[interaction_name] = X[f1] * X[f2]
                interaction_names.append(interaction_name)

    # Fill missing and standardize
    X = X.fillna(0.0)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Align target
    y = target_returns.reindex(X.index).fillna(0.0)

    # Fit model
    if method == "ridge":
        model = Ridge(alpha=alpha, random_state=42)
    elif method == "lasso":
        model = Lasso(alpha=alpha, random_state=42, max_iter=2000)
    elif method == "elastic_net":
        model = ElasticNet(alpha=alpha, l1_ratio=0.5, random_state=42, max_iter=2000)
    else:
        raise ValueError(f"Unknown method: {method}")

    model.fit(X_scaled, y)

    # Extract weights and clip
    weights = {}
    for i, col in enumerate(X.columns):
        weight = float(model.coef_[i])
        weight = np.clip(weight, -max_abs_weight, max_abs_weight)
        weights[col] = weight

    return weights


def build_cn_composite_decisions(
    factor_panel: pd.DataFrame,
    weights: CNCompositeWeights,
    *,
    risk_budget: float = 1.0,
    position_method: str = "linear_clip",
) -> list[CNCompositeDecision]:
    """构建 CN_A Composite 决策列表。

    Args:
        factor_panel: Factor panel with (date, symbol, market, factors...)
        weights: Composite weights object
        risk_budget: Maximum position size
        position_method: Position mapping method

    Returns:
        List of immutable decisions
    """
    if factor_panel.empty:
        return []

    # Compute all scores before mapping.  Mapping one score at a time makes
    # linear_clip see score_min == score_max and collapses every row to 50%.
    scores = weights.compute_score(factor_panel)
    positions = map_score_to_long_only_position(
        scores,
        risk_budget=risk_budget,
        method=position_method,
    )
    decisions = []

    for idx, row in factor_panel.iterrows():
        score = scores.loc[idx]
        position = positions.loc[idx]

        # Check fallback
        fallback_used = False
        fallback_reason = None
        if pd.isna(score):
            fallback_used = True
            fallback_reason = "score_missing"
            position = 0.0

        decision = CNCompositeDecision(
            date=row.get("date", pd.NaT),
            symbol=row.get("symbol", ""),
            market="CN_A",
            composite_score=float(score) if not pd.isna(score) else 0.0,
            composite_base_position=position,
            final_position=position,  # Phase 4: no advisory yet
            risk_budget=risk_budget,
            position_method=position_method,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            factors_used=tuple(weights.factors.keys()),
            weights_version=weights.version,
        )
        decisions.append(decision)

    return decisions
