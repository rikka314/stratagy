from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import core.adaptive_regime as adaptive_regime


def _make_feature_frame(rows: int = 96) -> pd.DataFrame:
    base = np.linspace(-1.0, 1.0, rows)
    payload = {
        "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
    }
    for idx, column in enumerate(adaptive_regime.ADAPTIVE_STATE_FEATURE_COLUMNS, start=1):
        payload[column] = base * (idx / 10.0) + np.sin(np.linspace(0, idx, rows))
    return pd.DataFrame(payload)


def test_train_adaptive_state_model_falls_back_to_logistic_without_lightgbm(monkeypatch: pytest.MonkeyPatch) -> None:
    feature_df = _make_feature_frame()
    monkeypatch.setattr(adaptive_regime.importlib.util, "find_spec", lambda name: None)

    bundle = adaptive_regime.train_adaptive_state_model(feature_df)
    predicted = adaptive_regime.predict_adaptive_states(feature_df, bundle["classifier_bundle"])

    assert bundle["classifier_bundle"]["classifier_type"] == "logistic_regression"
    assert bundle["classifier_bundle"]["state_count"] >= 2
    assert predicted.notna().sum() == len(feature_df)
