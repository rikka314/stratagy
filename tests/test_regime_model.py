from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import streamlit as st

import core.regime_model as regime_model
from ui import single_stock_workflow as ssw


def _make_indicator_frame(*, rows: int = 90, direction: str = "up") -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    if direction == "down":
        close = np.linspace(200.0, 110.0, rows)
        ema_fast = close - 2.0
    else:
        close = np.linspace(100.0, 190.0, rows)
        ema_fast = close + 2.0

    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(rows, 1_000_000.0),
            "atr": np.full(rows, 1.0),
            "ema_fast": ema_fast,
            "ema_slow": close,
            "bb_width": np.linspace(0.18, 0.42, rows),
            "volume_ratio": np.linspace(1.0, 1.5, rows),
            "price_position": np.linspace(0.55, 0.9, rows),
            "drawdown": np.linspace(-0.02, -0.08, rows),
            "bb_position": np.linspace(0.4, 0.8, rows),
        }
    )


def _patch_regime_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(regime_model, "add_indicators", lambda df, **kwargs: df.copy())
    monkeypatch.setattr(
        regime_model,
        "mean_target_position",
        lambda df, window=60: pd.Series(np.ones(len(df), dtype=float), index=df.index),
    )
    monkeypatch.setattr(
        regime_model,
        "drift_target_position",
        lambda df, split_idx: pd.Series(np.ones(len(df), dtype=float), index=df.index),
    )

    def fake_rank(series: pd.Series, window: int) -> pd.Series:
        base = 0.9 if series.name in {"bb_width", "volume_ratio", "price_position"} else 0.1
        return pd.Series(np.full(len(series), base, dtype=float), index=series.index)

    def fake_percentile(series: pd.Series, window: int) -> pd.Series:
        if series.name == "regime_score":
            value = 0.9
        elif series.name in {"atr_pct", "market_atr_pct"}:
            value = 0.5
        else:
            value = 0.5
        return pd.Series(np.full(len(series), value, dtype=float), index=series.index)

    monkeypatch.setattr(regime_model, "rolling_rank", fake_rank)
    monkeypatch.setattr(regime_model, "rolling_percentile", fake_percentile)


def test_compute_regime_signals_routes_into_trend_follow(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_regime_dependencies(monkeypatch)
    stock_df = _make_indicator_frame(direction="up")
    proxy_df = _make_indicator_frame(direction="up")

    signal_df, metadata = regime_model.compute_regime_signals(
        stock_df,
        split_idx=60,
        regime_kind="dual_state_router",
        fetcher=lambda symbol, adjust, market: proxy_df,
    )

    last = signal_df.iloc[-1]
    assert metadata["market_proxy_mode"] == "enabled"
    assert last["stock_trend_state"] == "Up"
    assert last["market_trend_state"] == "Up"
    assert last["execution_regime"] == "trend_follow"
    assert last["target_position"] == pytest.approx(1.0)
    assert {"anchor_mean_position", "anchor_drift_position", "regime_score_percentile"}.issubset(signal_df.columns)


def test_no_router_ablation_ignores_market_risk_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_regime_dependencies(monkeypatch)
    stock_df = _make_indicator_frame(direction="up")
    market_down_df = _make_indicator_frame(direction="down")

    router_df, _router_metadata = regime_model.compute_regime_signals(
        stock_df,
        split_idx=60,
        regime_kind="dual_state_router",
        fetcher=lambda symbol, adjust, market: market_down_df,
    )
    no_router_df, _no_router_metadata = regime_model.compute_regime_signals(
        stock_df,
        split_idx=60,
        regime_kind="no_router",
        fetcher=lambda symbol, adjust, market: market_down_df,
    )

    assert router_df.iloc[-1]["execution_regime"] == "risk_off"
    assert router_df.iloc[-1]["target_position"] == pytest.approx(0.0)
    assert no_router_df.iloc[-1]["execution_regime"] == "trend_follow"
    assert no_router_df.iloc[-1]["target_position"] == pytest.approx(1.0)


def test_run_strategy_pipeline_supports_regime_family(monkeypatch: pytest.MonkeyPatch) -> None:
    st.session_state.clear()
    date_index = pd.date_range("2024-01-01", periods=4, freq="D")
    stage = ssw.StageResult(
        stage_key="regime",
        display_label="Regime (Experimental)",
        short_label="Regime",
        params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0, "regime_kind": "dual_state_router"},
        train_sim_df=pd.DataFrame({"date": date_index[:2], "strategy_equity": [1.0, 1.02], "strategy_return": [0.0, 0.02]}),
        test_sim_df=pd.DataFrame(
            {
                "date": date_index[2:],
                "close": [102.0, 103.0],
                "strategy_equity": [1.0, 1.03],
                "strategy_return": [0.0, 0.03],
                "buy_hold_equity": [1.0, 1.01],
                "execution_regime": ["trend_follow", "trend_follow"],
                "target_position": [0.0, 1.0],
                "position": [0.0, 1.0],
            }
        ),
        trades_df=pd.DataFrame(),
        eval={"cumret": 0.03, "maxdd": -0.01, "sharpe": 1.2},
        equity_series=pd.Series([1.0, 1.03], index=date_index[2:], name="equity"),
        returns_series=pd.Series([0.0, 0.03], index=date_index[2:], name="returns"),
        ml_quality=None,
        upstream_stage_key=None,
        full_signal_df=pd.DataFrame(
            {
                "date": date_index,
                "close": [100.0, 101.0, 102.0, 103.0],
                "target_position": [0.0, 0.0, 0.0, 1.0],
                "buy_signal": [False, False, False, True],
                "sell_signal": [False, False, False, False],
                "execution_regime": ["risk_off", "range_selective", "trend_follow", "trend_follow"],
                "regime_score": [0.1, 0.2, 0.3, 0.4],
                "regime_score_percentile": [0.25, 0.5, 0.75, 0.9],
            }
        ),
        metadata={
            "warning_messages": ["market_proxy_unavailable: SPY data missing"],
            "regime_summary": {
                "market_proxy_symbol": "SPY",
                "market_proxy_mode": "fallback_stock_only",
                "latest_execution_regime": "trend_follow",
                "regime_table": [],
            },
        },
    )
    monkeypatch.setattr(ssw, "run_regime_stage", lambda **kwargs: (stage, False))

    result = ssw.run_strategy_pipeline(
        context_key="ctx_regime",
        request=ssw.StrategyRequest(family="regime", regime_kind="dual_state_router"),
        request_params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0},
        df_raw=pd.DataFrame({"date": date_index, "close": [100.0, 101.0, 102.0, 103.0]}),
        split_idx=2,
    )

    assert result.status == "success"
    assert result.artifact is not None
    assert result.artifact.display_label == "Regime (Experimental)"
    assert result.warnings == ["market_proxy_unavailable: SPY data missing"]


def _make_candidate_stage(
    *,
    display_label: str,
    short_label: str,
    dates: pd.DatetimeIndex,
    target_position: float,
    train_returns: list[float],
) -> ssw.StageResult:
    train_len = len(train_returns)
    test_dates = dates[train_len:]
    return ssw.StageResult(
        stage_key="search" if display_label != "Mean" else "baseline",
        display_label=display_label,
        short_label=short_label,
        params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0},
        train_sim_df=pd.DataFrame(
            {
                "date": dates[:train_len],
                "strategy_equity": np.cumprod([1.0 + value for value in train_returns]),
                "strategy_return": train_returns,
                "buy_hold_equity": np.cumprod([1.0, *([1.0] * max(train_len - 1, 0))])[:train_len],
            }
        ),
        test_sim_df=pd.DataFrame(
            {
                "date": test_dates,
                "strategy_equity": np.linspace(1.0, 1.05, len(test_dates)),
                "strategy_return": np.zeros(len(test_dates)),
                "buy_hold_equity": np.linspace(1.0, 1.01, len(test_dates)),
            }
        ),
        trades_df=pd.DataFrame(),
        eval={"cumret": 0.01, "maxdd": -0.01, "sharpe": 1.0},
        equity_series=pd.Series(np.linspace(1.0, 1.05, len(test_dates)), index=test_dates, name=f"{short_label}_equity"),
        returns_series=pd.Series(np.zeros(len(test_dates)), index=test_dates, name=f"{short_label}_returns"),
        ml_quality=None,
        upstream_stage_key=None,
        full_signal_df=pd.DataFrame(
            {
                "date": dates,
                "close": np.linspace(100.0, 105.0, len(dates)),
                "target_position": np.full(len(dates), target_position),
                "buy_signal": [False] * len(dates),
                "sell_signal": [False] * len(dates),
            }
        ),
        metadata={},
    )


def test_route_adaptive_signal_frame_switches_candidates() -> None:
    original_min_state_days = ssw.ADAPTIVE_MIN_STATE_DAYS
    ssw.ADAPTIVE_MIN_STATE_DAYS = 2
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    feature_df = pd.DataFrame(
        {
            "date": dates,
            "open": np.linspace(100.0, 105.0, 6),
            "high": np.linspace(101.0, 106.0, 6),
            "low": np.linspace(99.0, 104.0, 6),
            "close": np.linspace(100.0, 105.0, 6),
            "volume": np.full(6, 1_000_000.0),
        }
    )
    predicted_states = pd.Series([pd.NA, 0, 0, 1, 1, 1], dtype="Int64")
    mean_stage = _make_candidate_stage(display_label="Mean", short_label="Mean", dates=dates, target_position=0.2, train_returns=[0.0, 0.01, 0.0])
    sm_stage = _make_candidate_stage(display_label="SM", short_label="SM", dates=dates, target_position=0.8, train_returns=[0.0, 0.04, 0.03])
    fsm_stage = _make_candidate_stage(display_label="FSM", short_label="FSM", dates=dates, target_position=1.0, train_returns=[0.0, 0.01, 0.01])
    local_metrics_df = pd.DataFrame(
        [
            {
                "scope_level": "symbol",
                "scope_key": "ctx_adaptive",
                "state_id": 0,
                "model_id": "mean",
                "state_day_count": 2,
                "excess_return": 0.01,
                "sharpe": 0.2,
                "max_drawdown": -0.05,
                "policy_score": 40.0,
            },
            {
                "scope_level": "symbol",
                "scope_key": "ctx_adaptive",
                "state_id": 0,
                "model_id": "sm",
                "state_day_count": 2,
                "excess_return": 0.08,
                "sharpe": 1.4,
                "max_drawdown": -0.02,
                "policy_score": 95.0,
            },
        ]
    )
    offline_metrics_df = pd.DataFrame(
        [
            {
                "scope_level": "global",
                "scope_key": "global",
                "state_id": 1,
                "model_id": "fsm",
                "state_day_count": 30,
                "excess_return": 0.2,
                "sharpe": 1.5,
                "max_drawdown": -0.05,
                "policy_score": 95.0,
            }
        ]
    )

    try:
        routed_df, metadata = ssw._route_adaptive_signal_frame(
            feature_df=feature_df,
            predicted_state_ids=predicted_states,
            candidate_stages={"mean": mean_stage, "sm": sm_stage, "fsm": fsm_stage},
            split_idx=3,
            symbol="ctx_adaptive",
            segment_key="Flat__Low",
            local_metrics_df=local_metrics_df,
            offline_metrics_df=offline_metrics_df,
            candidate_pool_mode="default",
        )

        assert routed_df.iloc[2]["selected_model_id"] == "sm"
        assert routed_df.iloc[4]["selected_model_id"] == "fsm"
        assert routed_df.iloc[4]["target_position"] == pytest.approx(1.0)
        assert metadata["selected_model_id"] == "fsm"
        assert metadata["policy_source"] == "global"
        assert metadata["candidate_pool_mode"] == "default"
    finally:
        ssw.ADAPTIVE_MIN_STATE_DAYS = original_min_state_days


def test_run_strategy_pipeline_marks_adaptive_regime_fallback_as_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    st.session_state.clear()
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    degraded_stage = ssw.StageResult(
        stage_key="regime",
        display_label="Adaptive Router V1",
        short_label="Adaptive",
        params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0, "regime_kind": "adaptive_router_v1"},
        train_sim_df=pd.DataFrame({"date": dates[:2], "strategy_equity": [1.0, 1.01], "strategy_return": [0.0, 0.01]}),
        test_sim_df=pd.DataFrame(
            {
                "date": dates[2:],
                "close": [102.0, 103.0],
                "strategy_equity": [1.0, 1.02],
                "strategy_return": [0.0, 0.02],
                "buy_hold_equity": [1.0, 1.01],
                "target_position": [0.0, 0.5],
                "position": [0.0, 0.5],
            }
        ),
        trades_df=pd.DataFrame(),
        eval={"cumret": 0.02, "maxdd": -0.01, "sharpe": 1.0},
        equity_series=pd.Series([1.0, 1.02], index=dates[2:], name="equity"),
        returns_series=pd.Series([0.0, 0.02], index=dates[2:], name="returns"),
        ml_quality=None,
        upstream_stage_key=None,
        full_signal_df=pd.DataFrame(
            {
                "date": dates,
                "close": [100.0, 101.0, 102.0, 103.0],
                "target_position": [0.0, 0.0, 0.0, 0.5],
                "buy_signal": [False, False, False, True],
                "sell_signal": [False, False, False, False],
            }
        ),
        metadata={
            "run_status": "degraded",
            "warning_messages": ["adaptive fallback"],
        },
    )
    monkeypatch.setattr(ssw, "run_regime_stage", lambda **kwargs: (degraded_stage, False))

    result = ssw.run_strategy_pipeline(
        context_key="ctx_adaptive_fallback",
        request=ssw.StrategyRequest(family="regime", regime_kind="adaptive_router_v1"),
        request_params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0},
        df_raw=pd.DataFrame({"date": dates, "close": [100.0, 101.0, 102.0, 103.0]}),
        split_idx=2,
    )

    assert result.status == "degraded"
    assert result.artifact is not None
    assert result.warnings == ["adaptive fallback"]


def test_adaptive_regime_cache_key_includes_the_full_frozen_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def capture_cached_stage(**kwargs):
        captured.append(kwargs)
        return object(), False

    monkeypatch.setattr(ssw, "_cached_stage", capture_cached_stage)
    params_snapshot = {
        "stop_loss_mult": 2.0,
        "take_profit_mult": 4.0,
        "ema_fast": 20,
        "ema_slow": 60,
        "entry_threshold": 0.5,
    }

    ssw.run_regime_stage(
        context_key="ctx-adaptive",
        request=ssw.StrategyRequest(family="regime", regime_kind="adaptive_router_v1"),
        params_snapshot=params_snapshot,
        df_raw=pd.DataFrame(),
        split_idx=1,
    )

    assert captured[0]["stage_input_params_snapshot"] == params_snapshot


def test_adaptive_artifact_id_changes_with_frozen_request_parameters() -> None:
    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "strategy_equity": [1.0, 1.01],
            "strategy_return": [0.0, 0.01],
        }
    )
    stage = ssw.StageResult(
        stage_key="regime",
        display_label="Adaptive Router V1",
        short_label="Adaptive",
        params_snapshot={
            "stop_loss_mult": 2.0,
            "take_profit_mult": 4.0,
            "market": "US",
            "adjust": "qfq",
            "regime_kind": "adaptive_router_v1",
        },
        train_sim_df=frame.copy(),
        test_sim_df=frame.copy(),
        trades_df=None,
        eval={},
        equity_series=pd.Series([1.0, 1.01], index=dates),
        returns_series=pd.Series([0.0, 0.01], index=dates),
        ml_quality=None,
        upstream_stage_key=None,
        full_signal_df=frame.copy(),
    )
    request = ssw.StrategyRequest(family="regime", regime_kind="adaptive_router_v1")

    first = ssw.assemble_strategy_artifact(
        context_key="ctx-adaptive",
        request=request,
        request_params_snapshot={"ema_fast": 20, "entry_threshold": 0.5},
        lineage=[stage],
    )
    second = ssw.assemble_strategy_artifact(
        context_key="ctx-adaptive",
        request=request,
        request_params_snapshot={"ema_fast": 10, "entry_threshold": 0.8},
        lineage=[stage],
    )

    assert first.request_signature != second.request_signature
    assert first.id != second.id
