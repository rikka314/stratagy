"""Tests for transformer_state_diagnostic module."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_test.transformer_state_diagnostic import (
    DiagnosticConfig,
    DiagnosticError,
    ExpertDecomposition,
    SamplingBiasAnalysis,
    _analyze_sampling_bias,
    _make_decision,
)


def test_diagnostic_config_validation():
    """Test DiagnosticConfig validation."""
    with pytest.raises(DiagnosticError, match="Baseline output not found"):
        DiagnosticConfig(
            baseline_output_dir=Path("/nonexistent"),
            source_panel_path=Path("/nonexistent"),
            expert_ids=("a", "b"),
        )


def test_expert_decomposition_creation():
    """Test ExpertDecomposition dataclass."""
    decomp = ExpertDecomposition(
        expert_id="test",
        method="pca_single_day",
        fold_id="wf_01",
        neighbor_utility_mean=0.01,
        neighbor_utility_std=0.05,
        query_selected_utility_mean=0.005,
        query_oracle_utility_mean=0.02,
        regret=0.015,
        availability_rate=0.95,
        consistency_relative_to_random=0.03,
        utility_relative_to_random=-0.002,
    )

    assert decomp.expert_id == "test"
    assert decomp.regret == 0.015


def test_sampling_bias_analysis_creation():
    """Test SamplingBiasAnalysis dataclass."""
    sampling = SamplingBiasAnalysis(
        method="pca_single_day",
        fold_id="wf_01",
        n_train_rows=5000,
        n_unique_dates=200,
        rows_per_date_mean=25.0,
        rows_per_date_std=5.0,
        rows_per_date_max=50,
        consecutive_day_clusters=5,
        max_consecutive_days=20,
        date_coverage_span_days=300,
        temporal_concentration_entropy=4.5,
    )

    assert sampling.n_train_rows == 5000
    assert sampling.max_consecutive_days == 20


def test_make_decision_continue():
    """Test decision logic for continue case."""
    decompositions = [
        ExpertDecomposition(
            expert_id="expert_a",
            method="pca_single_day",
            fold_id="wf_01",
            neighbor_utility_mean=0.01,
            neighbor_utility_std=0.05,
            query_selected_utility_mean=0.008,  # positive vs random
            query_oracle_utility_mean=0.02,
            regret=0.012,
            availability_rate=0.95,
            consistency_relative_to_random=0.02,
            utility_relative_to_random=0.005,  # positive
        ),
        ExpertDecomposition(
            expert_id="expert_b",
            method="pca_single_day",
            fold_id="wf_01",
            neighbor_utility_mean=0.005,
            neighbor_utility_std=0.04,
            query_selected_utility_mean=0.004,
            query_oracle_utility_mean=0.015,
            regret=0.011,
            availability_rate=0.90,
            consistency_relative_to_random=0.025,
            utility_relative_to_random=0.002,  # positive
        ),
    ]

    sampling = [
        SamplingBiasAnalysis(
            method="pca_single_day",
            fold_id="wf_01",
            n_train_rows=5000,
            n_unique_dates=200,
            rows_per_date_mean=25.0,
            rows_per_date_std=5.0,
            rows_per_date_max=40,  # not severe
            consecutive_day_clusters=5,
            max_consecutive_days=8,  # not severe
            date_coverage_span_days=300,
            temporal_concentration_entropy=4.5,
        )
    ]

    comparison = pd.DataFrame([
        {
            "method": "random_neighbor",
            "mean_query_selected_utility": 0.0,
            "std_neighbor_utility": 0.08,
        }
    ])

    decision, rationale, summary = _make_decision(decompositions, sampling, comparison)

    assert decision == "continue"
    assert "CONTINUE" in rationale
    assert summary["n_experts_with_positive_utility"] == 2


def test_make_decision_refactor():
    """Test decision logic for refactor case."""
    decompositions = [
        ExpertDecomposition(
            expert_id="expert_a",
            method="pca_single_day",
            fold_id="wf_01",
            neighbor_utility_mean=0.01,
            neighbor_utility_std=0.05,
            query_selected_utility_mean=-0.005,  # negative
            query_oracle_utility_mean=0.02,
            regret=0.025,
            availability_rate=0.95,
            consistency_relative_to_random=0.02,
            utility_relative_to_random=-0.008,  # negative
        ),
    ]

    sampling = [
        SamplingBiasAnalysis(
            method="pca_single_day",
            fold_id="wf_01",
            n_train_rows=5000,
            n_unique_dates=100,
            rows_per_date_mean=50.0,
            rows_per_date_std=10.0,
            rows_per_date_max=80,  # severe
            consecutive_day_clusters=3,
            max_consecutive_days=25,  # severe
            date_coverage_span_days=300,
            temporal_concentration_entropy=3.0,
        )
    ]

    comparison = pd.DataFrame([
        {
            "method": "random_neighbor",
            "mean_query_selected_utility": 0.0,
            "std_neighbor_utility": 0.08,
        }
    ])

    decision, rationale, summary = _make_decision(decompositions, sampling, comparison)

    assert decision == "refactor"
    assert "REFACTOR" in rationale
    assert "sampling bias" in rationale.lower()


def test_make_decision_stop():
    """Test decision logic for stop case."""
    decompositions = [
        ExpertDecomposition(
            expert_id="expert_a",
            method="pca_single_day",
            fold_id="wf_01",
            neighbor_utility_mean=0.01,
            neighbor_utility_std=0.04,  # better consistency
            query_selected_utility_mean=-0.005,  # but worse utility
            query_oracle_utility_mean=0.02,
            regret=0.025,
            availability_rate=0.95,
            consistency_relative_to_random=0.04,  # improved
            utility_relative_to_random=-0.008,  # degraded
        ),
    ]

    sampling = [
        SamplingBiasAnalysis(
            method="pca_single_day",
            fold_id="wf_01",
            n_train_rows=5000,
            n_unique_dates=200,
            rows_per_date_mean=25.0,
            rows_per_date_std=5.0,
            rows_per_date_max=40,  # not severe
            consecutive_day_clusters=5,
            max_consecutive_days=8,  # not severe
            date_coverage_span_days=300,
            temporal_concentration_entropy=4.5,
        )
    ]

    comparison = pd.DataFrame([
        {
            "method": "random_neighbor",
            "mean_query_selected_utility": 0.0,
            "std_neighbor_utility": 0.08,
        }
    ])

    decision, rationale, summary = _make_decision(decompositions, sampling, comparison)

    assert decision == "stop"
    assert "STOP" in rationale
    assert "consistent but consistently worse" in rationale.lower() or "not supported" in rationale.lower()


def test_analyze_sampling_bias_basic():
    """Test sampling bias analysis with synthetic data."""
    # Create synthetic panel
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    panel = pd.DataFrame({
        "date": dates.repeat(10),  # 10 rows per date
        "symbol": ["A", "B", "C", "D", "E"] * 200,
    })
    panel.index = range(len(panel))

    split_membership = {i: "train" for i in range(500)}  # First 50 dates

    result = _analyze_sampling_bias(panel, "test_method", "wf_01", split_membership)

    assert result.n_train_rows == 500
    assert result.n_unique_dates == 50
    assert result.rows_per_date_mean == 10.0
    assert result.rows_per_date_max == 10
    assert result.max_consecutive_days > 10  # consecutive dates
