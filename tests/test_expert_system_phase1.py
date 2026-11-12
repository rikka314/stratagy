from __future__ import annotations

import json

import numpy as np
import pandas as pd

from model_test.expert_system_phase1 import (
    append_macro_sequences,
    build_horizon_sequence_panel,
)
from run_phase1_baseline import _bootstrap_delta, _decision, _phase1_code_lock


def _membership(split_id: str, role: str) -> str:
    return json.dumps([{"split_id": split_id, "role": role}], sort_keys=True)


def test_horizon_panel_rebuilds_complete_utility_vector_without_changing_rows() -> None:
    dates = pd.bdate_range("2025-01-02", periods=30)
    experts = ("alpha", "cash")
    daily_rows = []
    for symbol in ("AAA", "BBB"):
        for expert in experts:
            for index, date in enumerate(dates):
                daily_rows.append(
                    {
                        "date": date,
                        "symbol": symbol,
                        "expert_id": expert,
                        "expert_status": "available",
                        "strategy_return": 0.001 if expert == "alpha" else 0.0,
                        "turnover": 0.0,
                        "split_memberships_json": _membership(
                            "wf_01", "train" if index < 5 else "validation"
                        ),
                    }
                )
    expert_panel = pd.DataFrame(daily_rows)
    sequence_panel = pd.DataFrame(
        {
            "date": [dates[0], dates[1], dates[0], dates[1]],
            "sequence_end_date": [dates[0], dates[1], dates[0], dates[1]],
            "sequence_dates": [[dates[0]], [dates[1]], [dates[0]], [dates[1]]],
            "sequence_values": [np.zeros((1, 28)).tolist() for _ in range(4)],
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "market": ["US"] * 4,
        }
    )

    result = build_horizon_sequence_panel(
        sequence_panel,
        expert_panel,
        horizon_days=5,
        expert_ids=experts,
        lambda_downside=1.0,
        lambda_turnover=0.1,
    )

    assert len(result) == len(sequence_panel)
    assert "date" in result.columns
    assert set(result["label_horizon_days"]) == {5}
    utilities = json.loads(result.iloc[0]["expert_utilities_json"])
    assert tuple(sorted(utilities)) == tuple(sorted(experts))
    assert utilities["alpha"] > utilities["cash"]
    assert result.iloc[0]["split_memberships_json"] == _membership("wf_01", "train")


def test_append_macro_sequences_expands_28_features_to_33() -> None:
    dates = pd.bdate_range("2025-01-02", periods=3)
    panel = pd.DataFrame(
        {
            "sequence_dates": [dates.tolist()],
            "sequence_values": [
                np.asarray(
                    [np.zeros(28, dtype=float) for _ in range(3)],
                    dtype=object,
                )
            ],
            "symbol": ["AAA"],
        }
    )
    macro = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * 3,
            "vix_level": [15.0, 16.0, 17.0],
            "rel_strength_vs_spy": [0.1, 0.2, 0.3],
            "market_breadth": [0.4, 0.5, 0.6],
            "beta_20d": [0.9, 1.0, 1.1],
            "sector_momentum": [0.01, 0.02, 0.03],
        }
    )

    augmented = append_macro_sequences(panel, macro)
    sequence = np.asarray(augmented.iloc[0]["sequence_values"].tolist(), dtype=float)

    assert sequence.shape == (3, 33)
    assert np.allclose(sequence[-1, -5:], [17.0, 0.3, 0.6, 1.1, 0.03])


def test_bootstrap_delta_treats_boolean_match_as_zero_one() -> None:
    dates = pd.bdate_range("2025-01-02", periods=3)
    base = {
        "fold_id": ["wf_01"] * 3,
        "query_date": dates,
        "symbol": ["AAA"] * 3,
    }
    candidate = pd.DataFrame({**base, "expert_match": [True, True, False]})
    reference = pd.DataFrame({**base, "expert_match": [False, True, False]})

    result = _bootstrap_delta(
        candidate,
        reference,
        metric="expert_match",
        iterations=100,
        random_seed=42,
    )

    assert result["observed_difference"] == 1.0 / 3.0


def test_horizon_decision_uses_per_day_utility_scale() -> None:
    comparisons = pd.DataFrame(
        [
            {"candidate": "B04", "reference": "B01", "metric": "query_selected_utility", "observed_difference": -0.1},
            {"candidate": "B04", "reference": "B01", "metric": "query_selected_utility_per_day", "observed_difference": 0.003},
            {"candidate": "B04", "reference": "B01", "metric": "expert_match", "observed_difference": 0.06},
            {"candidate": "B05", "reference": "B04", "metric": "query_selected_utility", "observed_difference": 0.0},
            {"candidate": "B05", "reference": "B04", "metric": "regret", "observed_difference": 0.0},
        ]
    )
    config = {
        "acceptance": {
            "b04_query_utility_per_day_delta_min": 0.002,
            "b04_match_rate_delta_min": 0.05,
            "b05_query_utility_delta_min": 0.003,
            "b05_regret_delta_max": 0.0,
        }
    }

    decision = _decision(comparisons, config)

    assert decision["horizon_pass"] is True
    assert decision["observed"]["b04_vs_b01_query_utility_per_day_delta"] == 0.003


def test_code_lock_covers_label_and_retrieval_implementations() -> None:
    lock = _phase1_code_lock()
    paths = {artifact["path"] for artifact in lock["artifacts"]}

    assert "model-test/model_test/expert_panel.py" in paths
    assert "model-test/model_test/transformer_state_baseline.py" in paths
    assert len(lock["aggregate_sha256"]) == 64
