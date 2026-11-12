"""Tests for CN_A Composite Advisory module."""

import numpy as np
import pandas as pd
import pytest

from core.composite_advisory_cn_a import (
    CNAdvisoryConfig,
    CNCompositeAdvisory,
    CNCompositeAdvisoryDecision,
    POLICIES,
    decide_frame,
)


@pytest.fixture
def default_config():
    """Default advisory config for testing."""
    return CNAdvisoryConfig()


@pytest.fixture
def sample_factor_row():
    """Sample factor row with all required fields."""
    return pd.Series({
        "date": pd.Timestamp("2023-01-15"),
        "symbol": "600519",
        "market": "CN_A",
        "composite_score": 0.5,
        "composite_base_position": 0.8,
        "mom_long_z": 1.2,  # Trend
        "rsi_z": 0.8,  # Reversion
        "rel_strength_market": 0.05,  # Relative strength
        "market_vol_level": 0.15,  # Market volatility
    })


class TestCNAdvisoryConfig:
    """Test CN_A advisory configuration validation."""

    def test_default_config_valid(self):
        """Default config should be valid."""
        config = CNAdvisoryConfig()
        config.validate()  # Should not raise

    def test_invalid_trend_trigger(self):
        """Invalid trend trigger should raise."""
        with pytest.raises(ValueError, match="trend_trigger"):
            CNAdvisoryConfig(trend_trigger=1.5).validate()
        with pytest.raises(ValueError, match="trend_trigger"):
            CNAdvisoryConfig(trend_trigger=0.0).validate()

    def test_invalid_multipliers(self):
        """Invalid multipliers should raise."""
        with pytest.raises(ValueError, match="trend_conflict_multiplier"):
            CNAdvisoryConfig(trend_conflict_multiplier=1.5).validate()
        with pytest.raises(ValueError, match="reversion_multiplier"):
            CNAdvisoryConfig(reversion_multiplier=-0.1).validate()

    def test_non_finite_values(self):
        """Non-finite values should raise."""
        with pytest.raises(ValueError, match="finite"):
            CNAdvisoryConfig(trend_trigger=np.nan).validate()
        with pytest.raises(ValueError, match="finite"):
            CNAdvisoryConfig(macro_cap_floor=np.inf).validate()


class TestCNCompositeAdvisory:
    """Test CN_A Composite Advisory decision logic."""

    def test_init_with_default_config(self):
        """Engine should initialize with default config."""
        engine = CNCompositeAdvisory()
        assert engine.config is not None
        assert isinstance(engine.config, CNAdvisoryConfig)

    def test_init_with_custom_config(self, default_config):
        """Engine should accept custom config."""
        config = CNAdvisoryConfig(trend_trigger=0.6)
        engine = CNCompositeAdvisory(config=config)
        assert engine.config.trend_trigger == 0.6

    def test_composite_only_no_reduction(self, sample_factor_row):
        """Composite-only policy should not apply advisory."""
        engine = CNCompositeAdvisory()
        decision = engine.decide(sample_factor_row, policy="composite_only")

        assert decision.composite_base_position == 0.8
        assert decision.final_position == 0.8  # No reduction
        assert decision.advisory_multiplier == 1.0
        assert not decision.fallback_used
        assert "no_reduction" in decision.reason_codes

    def test_cash_policy_zeros_position(self, sample_factor_row):
        """Cash policy should zero out position."""
        engine = CNCompositeAdvisory()
        decision = engine.decide(sample_factor_row, policy="cash")

        assert decision.final_position == 0.0
        assert decision.advisory_multiplier == 0.0
        assert "cash_policy" in decision.reason_codes

    def test_composite_zero_prevents_opening(self, sample_factor_row):
        """Advisory cannot open position when composite is zero."""
        row = sample_factor_row.copy()
        row["composite_base_position"] = 0.0

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_all_advisories")

        assert decision.final_position == 0.0
        assert "composite_zero" in decision.reason_codes

    def test_trend_weak_reduces_position(self, sample_factor_row):
        """Weak trend should reduce position."""
        row = sample_factor_row.copy()
        row["mom_long_z"] = 0.3  # Weak trend (< 0.5 after normalization)

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_trend")

        assert decision.final_position < decision.composite_base_position
        assert "trend_weak" in decision.reason_codes
        assert decision.advisory_multiplier == 0.75  # Default conflict multiplier

    def test_reversion_overbought_reduces_position(self, sample_factor_row):
        """Overbought signal should reduce position."""
        row = sample_factor_row.copy()
        row["rsi_z"] = 2.0  # High RSI (overbought)

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_reversion")

        assert decision.final_position < decision.composite_base_position
        assert "reversion_overbought" in decision.reason_codes
        assert decision.advisory_multiplier == 0.70

    def test_relative_weak_reduces_position(self, sample_factor_row):
        """Weak relative strength should reduce position."""
        row = sample_factor_row.copy()
        row["rel_strength_market"] = -0.10  # Underperforming

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_relative_strength")

        assert decision.final_position < decision.composite_base_position
        assert "relative_weak" in decision.reason_codes
        assert decision.advisory_multiplier == 0.75

    def test_macro_risk_caps_position(self, sample_factor_row):
        """High market risk should cap position."""
        row = sample_factor_row.copy()
        row["market_vol_level"] = 0.40  # High volatility

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_macro_cap")

        assert decision.final_position < decision.composite_base_position
        assert "macro_risk_cap" in decision.reason_codes
        assert decision.macro_risk_level > 0.5

    def test_all_advisories_combines_reductions(self, sample_factor_row):
        """All advisories should combine reductions."""
        row = sample_factor_row.copy()
        row["mom_long_z"] = 0.3  # Weak trend
        row["rsi_z"] = 2.0  # Overbought
        row["market_vol_level"] = 0.35  # High risk

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_all_advisories")

        # Should trigger multiple reductions
        assert decision.final_position < decision.composite_base_position
        assert len(decision.reason_codes) > 1
        # Multiplier should be minimum of all applied multipliers
        assert decision.advisory_multiplier < 1.0

    def test_fallback_on_invalid_base_position(self, sample_factor_row):
        """Invalid base position should trigger fallback."""
        row = sample_factor_row.copy()
        row["composite_base_position"] = np.nan

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_only")

        assert decision.fallback_used
        assert decision.fallback_reason == "invalid_base_position"
        assert decision.final_position == 0.0

    def test_fallback_on_missing_required_field(self, sample_factor_row):
        """Missing required field should trigger fallback."""
        row = sample_factor_row.copy()
        del row["composite_base_position"]  # This is truly required

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_only")

        assert decision.fallback_used
        assert decision.fallback_reason == "missing_composite_base_position"

    def test_position_never_exceeds_base(self, sample_factor_row):
        """Final position should never exceed base position."""
        engine = CNCompositeAdvisory()

        for policy in POLICIES:
            if policy == "cash":
                continue
            decision = engine.decide(sample_factor_row, policy=policy)
            assert decision.final_position <= decision.composite_base_position

    def test_position_always_non_negative(self, sample_factor_row):
        """Final position should always be non-negative (long-only)."""
        engine = CNCompositeAdvisory()

        for policy in POLICIES:
            decision = engine.decide(sample_factor_row, policy=policy)
            assert decision.final_position >= 0.0

    def test_previous_position_limits_change(self, sample_factor_row):
        """Previous position should limit position change."""
        row = sample_factor_row.copy()
        row["composite_base_position"] = 0.8
        row["mom_long_z"] = 0.3  # Weak trend, will reduce

        engine = CNCompositeAdvisory()
        decision = engine.decide(
            row,
            policy="composite_plus_trend",
            previous_position=0.7,
        )

        # Change should be limited by max_single_decision_change (0.25)
        assert abs(decision.final_position - 0.7) <= 0.25
        if abs(decision.final_position - 0.7) > 0.20:
            assert "position_change_limit" in decision.reason_codes

    def test_invalid_previous_position_triggers_fallback(self, sample_factor_row):
        """Invalid previous position should trigger fallback."""
        engine = CNCompositeAdvisory()
        decision = engine.decide(
            sample_factor_row,
            policy="composite_only",
            previous_position=np.nan,
        )

        assert decision.fallback_used
        assert decision.fallback_reason == "invalid_previous_position"

    def test_unknown_policy_raises(self, sample_factor_row):
        """Unknown policy should raise ValueError."""
        engine = CNCompositeAdvisory()
        with pytest.raises(ValueError, match="Unknown policy"):
            engine.decide(sample_factor_row, policy="unknown_policy")


class TestDecideFrame:
    """Test frame-level advisory decisions."""

    def test_empty_frame_returns_empty(self):
        """Empty frame should return empty result."""
        result = decide_frame(pd.DataFrame(), policy="composite_only")
        assert result.empty
        assert "date" in result.columns

    def test_single_row_frame(self, sample_factor_row):
        """Single-row frame should work."""
        frame = pd.DataFrame([sample_factor_row])
        result = decide_frame(frame, policy="composite_only")

        assert len(result) == 1
        assert result.iloc[0]["composite_base_position"] == 0.8
        assert result.iloc[0]["final_position"] == 0.8

    def test_multi_row_frame_preserves_order(self, sample_factor_row):
        """Multi-row frame should preserve row order."""
        rows = []
        for i in range(5):
            row = sample_factor_row.copy()
            row["date"] = pd.Timestamp("2023-01-15") + pd.Timedelta(days=i)
            row["composite_base_position"] = 0.6 + i * 0.05
            rows.append(row)

        frame = pd.DataFrame(rows)
        result = decide_frame(frame, policy="composite_only")

        assert len(result) == 5
        assert all(result["date"] == frame["date"])
        assert all(result["composite_base_position"].values == frame["composite_base_position"].values)

    def test_position_change_propagates_across_rows(self, sample_factor_row):
        """Position changes should propagate across sequential rows."""
        rows = []
        for i in range(3):
            row = sample_factor_row.copy()
            row["date"] = pd.Timestamp("2023-01-15") + pd.Timedelta(days=i)
            row["composite_base_position"] = 0.8
            row["mom_long_z"] = 0.3 if i == 1 else 1.2  # Weak trend on day 2
            rows.append(row)

        frame = pd.DataFrame(rows)
        result = decide_frame(frame, policy="composite_plus_trend")

        # Day 1: full position
        assert result.iloc[0]["final_position"] == 0.8
        # Day 2: reduced due to weak trend
        assert result.iloc[1]["final_position"] < 0.8
        # Day 3: cannot jump back more than max_change from day 2
        day2_pos = result.iloc[1]["final_position"]
        day3_pos = result.iloc[2]["final_position"]
        assert abs(day3_pos - day2_pos) <= 0.25

    def test_custom_config_applied(self, sample_factor_row):
        """Custom config should be applied to all decisions."""
        config = CNAdvisoryConfig(trend_conflict_multiplier=0.5)

        row = sample_factor_row.copy()
        row["mom_long_z"] = 0.3  # Weak trend
        frame = pd.DataFrame([row])

        result = decide_frame(frame, policy="composite_plus_trend", config=config)

        # Should use custom multiplier 0.5 instead of default 0.75
        assert result.iloc[0]["advisory_multiplier"] == 0.5


class TestAdvisoryBounds:
    """Test that advisory decisions respect all safety bounds."""

    def test_final_position_in_bounds(self, sample_factor_row):
        """Final position must be in [0, base_position]."""
        engine = CNCompositeAdvisory()

        for _ in range(100):
            row = sample_factor_row.copy()
            row["composite_base_position"] = np.random.uniform(0.0, 1.0)
            row["mom_long_z"] = np.random.uniform(-2.0, 2.0)
            row["rsi_z"] = np.random.uniform(-2.0, 2.0)

            decision = engine.decide(row, policy="composite_plus_all_advisories")

            assert 0.0 <= decision.final_position <= decision.composite_base_position
            assert decision.final_position <= 1.0

    def test_multiplier_never_increases_position(self, sample_factor_row):
        """Advisory multiplier should never exceed 1.0 (no position increase)."""
        engine = CNCompositeAdvisory()

        for policy in POLICIES:
            if policy == "cash":
                continue
            decision = engine.decide(sample_factor_row, policy=policy)
            assert decision.advisory_multiplier <= 1.0

    def test_decision_change_limited(self, sample_factor_row):
        """Position change should be limited by max_single_decision_change."""
        row = sample_factor_row.copy()
        row["composite_base_position"] = 1.0
        row["market_vol_level"] = 0.50  # Very high risk

        engine = CNCompositeAdvisory()
        decision = engine.decide(row, policy="composite_plus_macro_cap")

        # Even with high risk, change should be limited
        change = row["composite_base_position"] - decision.final_position
        assert change <= 0.25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
