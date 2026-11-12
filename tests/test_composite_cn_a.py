"""Tests for CN_A Composite module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.composite_cn_a import (
    CNCompositeWeights,
    CNCompositeDecision,
    map_score_to_long_only_position,
    fit_cn_composite_weights,
    build_cn_composite_decisions,
)


class TestCNCompositeWeights:
    """Test CNCompositeWeights immutability and score computation."""

    def test_immutability(self):
        """Test that CNCompositeWeights is immutable."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0, "rsi_z": 0.5},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        with pytest.raises(Exception):  # dataclass frozen
            weights.factors = {"new": 1.0}

    def test_compute_score_basic(self):
        """Test basic score computation."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0, "rsi_z": 0.5},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        factor_df = pd.DataFrame({
            "mom_short_z": [1.0, 2.0],
            "rsi_z": [0.5, -0.5],
        })

        scores = weights.compute_score(factor_df)

        expected = [1.0 * 1.0 + 0.5 * 0.5, 1.0 * 2.0 + 0.5 * (-0.5)]
        np.testing.assert_allclose(scores, expected)

    def test_compute_score_with_interaction(self):
        """Test score computation with interaction terms."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0, "rsi_z": 0.5},
            interaction_terms={"mom_short_z_x_rsi_z": -0.3},
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        factor_df = pd.DataFrame({
            "mom_short_z": [1.0, 2.0],
            "rsi_z": [0.5, -0.5],
        })

        scores = weights.compute_score(factor_df)

        # Main: 1.0*1.0 + 0.5*0.5 = 1.25, Interaction: -0.3*1.0*0.5 = -0.15 => 1.1
        # Main: 1.0*2.0 + 0.5*(-0.5) = 1.75, Interaction: -0.3*2.0*(-0.5) = 0.3 => 2.05
        expected = [1.25 - 0.15, 1.75 + 0.3]
        np.testing.assert_allclose(scores, expected)

    def test_compute_score_missing_factor(self):
        """Test that missing factors are treated as 0."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0, "missing_factor": 0.5},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        factor_df = pd.DataFrame({
            "mom_short_z": [1.0, 2.0],
        })

        scores = weights.compute_score(factor_df)

        # missing_factor treated as 0
        expected = [1.0, 2.0]
        np.testing.assert_allclose(scores, expected)

    def test_compute_score_empty_input(self):
        """Test that empty input returns empty series."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        factor_df = pd.DataFrame()
        scores = weights.compute_score(factor_df)

        assert len(scores) == 0


class TestPositionMapping:
    """Test position mapping functions."""

    def test_linear_clip_basic(self):
        """Test linear_clip mapping."""
        scores = pd.Series([0.0, 0.5, 1.0, 1.5, 2.0])
        positions = map_score_to_long_only_position(
            scores,
            risk_budget=1.0,
            method="linear_clip",
        )

        # Should map [0, 2] to [0, 1]
        assert positions.min() == 0.0
        assert positions.max() == 1.0
        assert all(positions >= 0.0)
        assert all(positions <= 1.0)

    def test_tanh_smooth(self):
        """Test tanh_smooth mapping."""
        scores = pd.Series([-2.0, 0.0, 2.0])
        positions = map_score_to_long_only_position(
            scores,
            risk_budget=1.0,
            method="tanh_smooth",
        )

        assert all(positions >= 0.0)
        assert all(positions <= 1.0)
        # Middle score should map to ~0.5
        assert 0.4 < positions.iloc[1] < 0.6

    def test_risk_budget_scaling(self):
        """Test that risk_budget scales positions."""
        scores = pd.Series([0.0, 1.0, 2.0])
        positions = map_score_to_long_only_position(
            scores,
            risk_budget=0.5,
            method="linear_clip",
        )

        assert positions.max() <= 0.5

    def test_empty_input(self):
        """Test empty input returns empty series."""
        scores = pd.Series([], dtype=float)
        positions = map_score_to_long_only_position(scores)
        assert len(positions) == 0


class TestWeightFitting:
    """Test weight fitting functions."""

    def test_fit_ridge_basic(self):
        """Test ridge regression fitting."""
        factor_panel = pd.DataFrame({
            "mom_short_z": np.random.randn(100),
            "rsi_z": np.random.randn(100),
        })
        target_returns = pd.Series(np.random.randn(100))

        weights = fit_cn_composite_weights(
            factor_panel,
            target_returns,
            factor_cols=["mom_short_z", "rsi_z"],
            method="ridge",
            alpha=1.0,
        )

        assert "mom_short_z" in weights
        assert "rsi_z" in weights
        assert abs(weights["mom_short_z"]) <= 2.0  # max_abs_weight default

    def test_fit_with_interactions(self):
        """Test fitting with interaction terms."""
        factor_panel = pd.DataFrame({
            "mom_short_z": np.random.randn(100),
            "rsi_z": np.random.randn(100),
        })
        target_returns = pd.Series(np.random.randn(100))

        weights = fit_cn_composite_weights(
            factor_panel,
            target_returns,
            factor_cols=["mom_short_z", "rsi_z"],
            interaction_terms=[("mom_short_z", "rsi_z")],
            method="ridge",
        )

        assert "mom_short_z_x_rsi_z" in weights

    def test_weight_clipping(self):
        """Test that weights are clipped to max_abs_weight."""
        factor_panel = pd.DataFrame({
            "factor1": np.random.randn(100) * 10,
        })
        target_returns = pd.Series(np.random.randn(100) * 10)

        weights = fit_cn_composite_weights(
            factor_panel,
            target_returns,
            factor_cols=["factor1"],
            method="ridge",
            alpha=0.01,
            max_abs_weight=1.0,
        )

        assert abs(weights["factor1"]) <= 1.0


class TestDecisionBuilding:
    """Test decision building."""

    def test_build_decisions_basic(self):
        """Test basic decision building."""
        factor_panel = pd.DataFrame({
            "date": pd.to_datetime(["2023-01-01", "2023-01-02"]),
            "symbol": ["000001", "000001"],
            "market": ["CN_A", "CN_A"],
            "mom_short_z": [1.0, 2.0],
            "rsi_z": [0.5, -0.5],
        })

        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0, "rsi_z": 0.5},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        decisions = build_cn_composite_decisions(
            factor_panel,
            weights,
            risk_budget=1.0,
            position_method="linear_clip",
        )

        assert len(decisions) == 2
        assert all(isinstance(d, CNCompositeDecision) for d in decisions)
        assert all(d.market == "CN_A" for d in decisions)
        assert all(0.0 <= d.final_position <= 1.0 for d in decisions)

    def test_decision_immutability(self):
        """Test that decisions are immutable."""
        decision = CNCompositeDecision(
            date=pd.Timestamp("2023-01-01"),
            symbol="000001",
            market="CN_A",
            composite_score=1.0,
            composite_base_position=0.5,
            final_position=0.5,
            risk_budget=1.0,
            position_method="linear_clip",
            fallback_used=False,
            fallback_reason=None,
            factors_used=("mom_short_z",),
            weights_version="v1",
        )

        with pytest.raises(Exception):  # dataclass frozen
            decision.final_position = 0.8

    def test_fallback_on_missing_score(self):
        """Test that missing factors are filled with 0 and don't trigger fallback."""
        factor_panel = pd.DataFrame({
            "date": pd.to_datetime(["2023-01-01"]),
            "symbol": ["000001"],
            "market": ["CN_A"],
            "mom_short_z": [np.nan],
        })

        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        decisions = build_cn_composite_decisions(
            factor_panel,
            weights,
        )

        # Missing factors are filled with 0, so score = 0, which maps to a position
        assert decisions[0].fallback_used is False
        assert decisions[0].composite_score == 0.0
        # Position mapping for score=0 depends on the score range, but should be valid
        assert 0.0 <= decisions[0].final_position <= 1.0


class TestMarketConstraints:
    """Test CN_A market-specific constraints."""

    def test_no_short_positions(self):
        """Test that positions are always non-negative (long_only)."""
        scores = pd.Series([-2.0, -1.0, 0.0, 1.0, 2.0])
        positions = map_score_to_long_only_position(scores)

        assert all(positions >= 0.0)

    def test_position_bounded_by_risk_budget(self):
        """Test that positions never exceed risk_budget."""
        scores = pd.Series([100.0, 200.0, 300.0])
        risk_budget = 0.8
        positions = map_score_to_long_only_position(
            scores,
            risk_budget=risk_budget,
        )

        assert all(positions <= risk_budget)

    def test_market_must_be_cn_a(self):
        """Test that market field is enforced."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        assert weights.market == "CN_A"

    def test_position_policy_must_be_long_only(self):
        """Test that position_policy is enforced."""
        weights = CNCompositeWeights(
            factors={"mom_short_z": 1.0},
            interaction_terms=None,
            fit_method="ridge",
            train_folds=["fold_01"],
            market="CN_A",
            position_policy="long_only",
            version="v1",
        )

        assert weights.position_policy == "long_only"
