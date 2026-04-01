from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import streamlit as st

from core import ml_filter
from ui import single_stock_workflow as ssw


def _make_ml_signal_frame(
    *,
    rows: int,
    buy_positions: tuple[int, ...],
    hold_length: int,
    daily_return: float = 0.01,
) -> pd.DataFrame:
    close = 100.0 * np.power(1.0 + daily_return, np.arange(rows, dtype=float))
    target_position = np.zeros(rows, dtype=float)
    for start in buy_positions:
        end = min(rows, start + hold_length)
        target_position[start:end] = 1.0

    prev_position = pd.Series(target_position).shift(1).fillna(0.0).to_numpy()
    frame = pd.DataFrame(index=pd.RangeIndex(rows))
    frame["date"] = pd.date_range("2024-01-01", periods=rows, freq="D")
    frame["close"] = close
    frame["target_position"] = target_position
    frame["buy_signal"] = False
    frame.loc[list(buy_positions), "buy_signal"] = True
    frame["sell_signal"] = (target_position <= 0) & (prev_position > 0)
    frame["factor_score"] = np.linspace(0.2, 1.2, rows)
    frame["factor_percentile"] = np.linspace(0.2, 0.95, rows)
    frame["mom_short_z"] = 0.1
    frame["mom_long_z"] = 0.2
    frame["macd_z"] = 0.3
    frame["rsi_z"] = 0.4
    frame["vol_z"] = 0.1
    frame["bb_position_rank"] = 0.5
    frame["obv_trend_rank"] = 0.6
    frame["volume_ratio_rank"] = 0.7
    frame["price_position_rank"] = 0.8
    frame["drawdown_rank"] = 0.2
    frame["rsi"] = 55.0
    frame["macd"] = 1.0
    frame["signal"] = 0.5
    frame["adx"] = 25.0
    frame["atr"] = 1.0
    frame["volume_ratio"] = 1.2
    frame["bb_position"] = 0.4
    frame["bb_width"] = 0.1
    frame["price_position"] = 0.5
    frame["drawdown"] = -0.05
    frame["trend_ok"] = True
    frame["strength_ok"] = True
    frame["rsi_ok"] = True
    frame["macd_above"] = True
    frame["entry_count"] = 4.0
    frame["ema_fast"] = close + 0.5
    frame["ema_slow"] = close - 0.5
    return frame


def test_build_feature_bundle_respects_custom_horizon() -> None:
    signal_df = _make_ml_signal_frame(rows=30, buy_positions=(0,), hold_length=25, daily_return=0.01)

    bundle = ml_filter.build_feature_bundle(signal_df, horizon=20, min_excess_samples=1)
    feature_view = ml_filter.build_feature_view(bundle)

    expected_return = (1.01**20) - 1.0

    assert bundle.horizon == 20
    assert bundle.min_excess_samples == 1
    assert feature_view.iloc[0]["future_strategy_return"] == pytest.approx(expected_return)
    assert feature_view.iloc[0]["future_naive_return"] == pytest.approx(expected_return)
    assert feature_view.iloc[0]["future_excess_return"] == pytest.approx(0.0)


def test_materialize_label_frame_falls_back_only_for_sparse_or_single_class_primary_labels() -> None:
    abundant = pd.DataFrame(
        {
            "future_strategy_return": [0.10 if i % 2 == 0 else -0.05 for i in range(45)],
            "future_naive_return": [0.0] * 45,
            "future_excess_return": [0.04 if i % 2 == 0 else -0.03 for i in range(45)],
        }
    )
    sparse = abundant.iloc[:30].copy()
    collapsed = abundant.copy()
    collapsed["future_excess_return"] = 0.05

    abundant_labels = ml_filter._materialize_label_frame(abundant, min_excess_samples=40)
    sparse_labels = ml_filter._materialize_label_frame(sparse, min_excess_samples=40)
    collapsed_labels = ml_filter._materialize_label_frame(collapsed, min_excess_samples=40)

    assert set(abundant_labels["label_mode"]) == {"excess_return"}
    assert set(sparse_labels["label_mode"]) == {"absolute_return"}
    assert set(collapsed_labels["label_mode"]) == {"absolute_return"}


def test_run_ml_stage_passes_request_label_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    st.session_state.clear()
    captured: dict[str, int] = {}

    def fake_build_feature_bundle(df, horizon=10, min_excess_samples=20):
        captured["horizon"] = int(horizon)
        captured["min_excess_samples"] = int(min_excess_samples)
        return object()

    def fake_build_feature_view(bundle, **kwargs):
        if "max_signal_pos" in kwargs:
            return pd.DataFrame({"ml_label": [1.0], "signal_pos": [1]})
        if "min_signal_pos" in kwargs:
            return pd.DataFrame({"ml_label": [1.0], "signal_pos": [4]})
        return pd.DataFrame({"ml_label": [1.0], "signal_pos": [1]})

    monkeypatch.setattr(ssw, "build_feature_bundle", fake_build_feature_bundle)
    monkeypatch.setattr(ssw, "build_feature_view", fake_build_feature_view)
    monkeypatch.setattr(ssw, "fit_ml_filter", lambda *args, **kwargs: SimpleNamespace(threshold=0.5))
    monkeypatch.setattr(ssw, "apply_filter", lambda df, ml_model, feature_df=None: df.copy())
    monkeypatch.setattr(ssw, "predict_filter", lambda ml_model, feature_df: np.array([0.9], dtype=float))
    monkeypatch.setattr(
        ssw,
        "evaluate_ml_quality",
        lambda labels, proba, threshold=0.5: {"precision": 1.0, "recall": 1.0},
    )

    def fake_build_stage_result_from_signal_df(**kwargs):
        return ssw.StageResult(
            stage_key=kwargs["stage_key"],
            display_label=kwargs["display_label"],
            short_label=kwargs["short_label"],
            params_snapshot=kwargs["params_snapshot"],
            train_sim_df=pd.DataFrame(),
            test_sim_df=pd.DataFrame(),
            trades_df=None,
            eval={},
            equity_series=pd.Series(dtype=float),
            returns_series=pd.Series(dtype=float),
            ml_quality=kwargs.get("ml_quality"),
            upstream_stage_key=kwargs.get("upstream_stage_key"),
            full_signal_df=kwargs["full_signal_df"].copy(),
            metadata=kwargs.get("metadata", {}),
        )

    monkeypatch.setattr(ssw, "_build_stage_result_from_signal_df", fake_build_stage_result_from_signal_df)

    upstream_stage = ssw.StageResult(
        stage_key="search",
        display_label="SM+Search",
        short_label="SM+Search",
        params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0},
        train_sim_df=pd.DataFrame(),
        test_sim_df=pd.DataFrame(),
        trades_df=None,
        eval={},
        equity_series=pd.Series(dtype=float),
        returns_series=pd.Series(dtype=float),
        ml_quality=None,
        upstream_stage_key="sm_base",
        full_signal_df=pd.DataFrame({"target_position": [0.0, 1.0, 1.0, 0.0], "close": [1.0, 1.1, 1.2, 1.3], "atr": [1.0, 1.0, 1.0, 1.0]}),
        metadata={},
    )

    request = ssw.StrategyRequest(
        family="search",
        search_base="sm",
        use_search=True,
        search_method="bayesian",
        use_ml=True,
        ml_model_type="logistic",
        ml_horizon_days=20,
        ml_min_excess_samples=40,
    )

    stage, cached = ssw.run_ml_stage(
        context_key="ctx_ml_v2",
        request=request,
        upstream_stage=upstream_stage,
        split_idx=3,
    )

    assert cached is False
    assert captured == {"horizon": 20, "min_excess_samples": 40}
    assert stage.metadata["ml_horizon_days"] == 20
    assert stage.metadata["ml_min_excess_samples"] == 40
