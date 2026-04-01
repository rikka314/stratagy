from __future__ import annotations

import json
import threading
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st

from core.ml_filter import build_feature_bundle, build_feature_view
from core.optimizer import SearchEvaluationCache, SearchEvaluationResult, SearchMetrics, SearchOptimizationResult
from model_test.config import load_research_config
from model_test.models import ResearchConfig
from model_test import universe
from ui import single_stock_workflow as ssw


def _write_history_csv(path: Path, *, rows: int, close_start: float) -> None:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [close_start + i for i in range(rows)],
            "high": [close_start + i + 1.0 for i in range(rows)],
            "low": [close_start + i - 1.0 for i in range(rows)],
            "close": [close_start + i + 0.5 for i in range(rows)],
            "volume": [1_000_000 + i * 10_000 for i in range(rows)],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _make_search_signal_df() -> pd.DataFrame:
    close = pd.Series([100, 102, 103, 101, 104, 106], dtype=float)
    target_position = pd.Series([0.0, 1.0, 1.0, 0.0, 1.0, 0.0], dtype=float)
    prev_position = target_position.shift(1).fillna(0.0)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(close), freq="D"),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "atr": 1.0,
            "target_position": target_position,
            "buy_signal": (target_position > 0) & (prev_position <= 0),
            "sell_signal": (target_position <= 0) & (prev_position > 0),
        }
    )


def _make_ml_signal_df() -> pd.DataFrame:
    close = pd.Series([10, 11, 12, 13, 14, 13, 15, 16, 17], dtype=float)
    target_position = pd.Series([0, 1, 1, 0, 1, 0, 1, 1, 0], dtype=float)
    prev_position = target_position.shift(1).fillna(0.0)
    index = pd.RangeIndex(len(close))
    frame = pd.DataFrame(index=index)
    frame["date"] = pd.date_range("2024-02-01", periods=len(close), freq="D")
    frame["close"] = close
    frame["open"] = close - 0.5
    frame["high"] = close + 1.0
    frame["low"] = close - 1.0
    frame["target_position"] = target_position
    frame["buy_signal"] = (target_position > 0) & (prev_position <= 0)
    frame["sell_signal"] = (target_position <= 0) & (prev_position > 0)
    frame["factor_score"] = pd.Series(range(len(close)), dtype=float)
    frame["factor_percentile"] = pd.Series([0.1, 0.2, 0.3, 0.1, 0.8, 0.2, 0.9, 0.7, 0.4], dtype=float)
    frame["mom_short_z"] = 0.1
    frame["mom_long_z"] = 0.2
    frame["macd_z"] = 0.3
    frame["rsi_z"] = 0.4
    frame["vol_z"] = 0.5
    frame["bb_position_rank"] = 0.6
    frame["obv_trend_rank"] = 0.7
    frame["volume_ratio_rank"] = 0.8
    frame["price_position_rank"] = 0.9
    frame["drawdown_rank"] = 0.2
    frame["rsi"] = 55.0
    frame["macd"] = 1.0
    frame["signal"] = 0.5
    frame["adx"] = 20.0
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
    frame["ema_fast"] = close - 0.3
    frame["ema_slow"] = close - 0.9
    return frame


def test_load_research_config_applies_cache_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"name": "case", "parallelism": 2}), encoding="utf-8")

    config = load_research_config(config_path)

    assert config.cache_dir == "model-test/cache"
    assert config.universe_parallelism == 4


def test_build_main_research_profiles_reuses_cache_and_rebuilds_only_changed_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data-cache"
    sample_dir = tmp_path / "sample-data"
    cache_dir = tmp_path / "research-cache"
    catalog_path = tmp_path / "catalog.csv"

    symbols = {
        "AAPL": "Apple Inc",
        "MSFT": "Microsoft Corp",
        "NVDA": "NVIDIA Corp",
    }
    for offset, symbol in enumerate(symbols):
        _write_history_csv(data_dir / f"{symbol.lower()}_daily.csv", rows=160, close_start=50 + offset * 20)

    pd.DataFrame({"symbol": list(symbols.keys()), "name": list(symbols.values())}).to_csv(catalog_path, index=False)

    config = ResearchConfig(
        name="cache_case",
        catalog_path=str(catalog_path),
        sample_data_dir=str(sample_dir),
        cache_dir=str(cache_dir),
        smoke_mode=False,
        main_window_days=120,
        min_history_days=120,
        profile_lookback_days=30,
        main_pool_size=2,
        min_avg_dollar_volume=1.0,
        max_catalog_candidates=3,
        parallelism=2,
        universe_parallelism=2,
    )

    monkeypatch.setattr(universe, "DATA_DIR", str(data_dir))

    read_counts: dict[str, int] = {}
    read_lock = threading.Lock()
    original_read_market_csv = universe._read_market_csv

    def counting_read_market_csv(path: Path) -> pd.DataFrame:
        symbol = path.stem.replace("_daily", "").upper()
        with read_lock:
            read_counts[symbol] = read_counts.get(symbol, 0) + 1
        return original_read_market_csv(path)

    monkeypatch.setattr(universe, "_read_market_csv", counting_read_market_csv)

    first_profiles = universe.build_main_research_profiles(config)
    assert len(first_profiles) == 2
    assert set(read_counts) == {"AAPL", "MSFT", "NVDA"}

    read_counts.clear()
    second_profiles = universe.build_main_research_profiles(config)
    assert [profile.symbol for profile in second_profiles] == [profile.symbol for profile in first_profiles]
    assert read_counts == {}

    touched_path = data_dir / "aapl_daily.csv"
    touched_path.touch()

    read_counts.clear()
    third_profiles = universe.build_main_research_profiles(config)
    assert len(third_profiles) == 2
    assert read_counts == {"AAPL": 1}


def test_search_evaluation_cache_reuses_duplicate_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_evaluate_candidate_frame(**kwargs):
        calls["count"] += 1
        return SearchEvaluationResult(
            params={"ema_fast": 10, "ema_slow": 20},
            full_signal_df=pd.DataFrame({"target_position": [0.0, 1.0], "close": [1.0, 1.1], "atr": [1.0, 1.0]}),
            raw_score=1.23,
            train_metrics=SearchMetrics(0.5, 0.1, -0.02),
            validation_metrics=SearchMetrics(0.4, 0.08, -0.03),
        )

    monkeypatch.setattr("core.optimizer._evaluate_candidate_frame", fake_evaluate_candidate_frame)

    cache = SearchEvaluationCache(
        df_raw=pd.DataFrame({"close": [1.0, 1.1, 1.2]}),
        split_idx=2,
        common_kwargs={},
        fsm_mode=False,
    )

    first = cache.evaluate({"ema_fast": 10, "ema_slow": 20})
    second = cache.evaluate({"ema_fast": 10, "ema_slow": 20})

    assert first is not None
    assert second is not None
    assert calls["count"] == 1
    assert cache.hits == 1


def test_run_search_stage_uses_optimizer_signal_df_without_recomputing_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st.session_state.clear()
    signal_df = _make_search_signal_df()

    optimizer_result = SearchOptimizationResult(
        best_params={"ema_fast": 9, "ema_slow": 21},
        method_name="random_search",
        score=1.0,
        train_metrics=SearchMetrics(0.5, 0.1, -0.02),
        validation_metrics=SearchMetrics(0.4, 0.08, -0.03),
        full_signal_df=signal_df,
    )

    monkeypatch.setattr(ssw, "_run_parameter_search", lambda **kwargs: optimizer_result)
    monkeypatch.setattr(ssw, "run_sm_base_stage", lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected recompute")))
    monkeypatch.setattr(ssw, "run_fsm_base_stage", lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected recompute")))

    upstream_stage = ssw.StageResult(
        stage_key="sm_base",
        display_label="SM",
        short_label="SM",
        params_snapshot={"stop_loss_mult": 0.0, "take_profit_mult": 0.0},
        train_sim_df=pd.DataFrame(),
        test_sim_df=pd.DataFrame(),
        trades_df=None,
        eval={},
        equity_series=pd.Series(dtype=float),
        returns_series=pd.Series(dtype=float),
        ml_quality=None,
        upstream_stage_key=None,
        full_signal_df=pd.DataFrame(),
        metadata={},
    )

    request = ssw.StrategyRequest(
        family="search",
        search_base="sm",
        use_search=True,
        search_method="random",
    )
    stage, cached = ssw.run_search_stage(
        context_key="ctx_test",
        request=request,
        upstream_stage=upstream_stage,
        df_raw=pd.DataFrame(),
        split_idx=3,
    )

    assert cached is False
    assert stage.stage_key == "search"
    assert stage.metadata["optimizer_result"]["method_name"] == "random_search"
    pd.testing.assert_frame_equal(stage.full_signal_df.reset_index(drop=True), signal_df.reset_index(drop=True))


def test_build_feature_view_blocks_training_label_leakage() -> None:
    signal_df = _make_ml_signal_df()
    bundle = build_feature_bundle(signal_df, horizon=2, min_excess_samples=1)

    train_features = build_feature_view(
        bundle,
        max_signal_pos=6,
        label_boundary_limit=6,
    )
    full_features = build_feature_view(bundle)
    test_features = build_feature_view(bundle, min_signal_pos=6)

    cross_boundary_row = train_features.loc[train_features["signal_pos"] == 4].iloc[0]
    full_row = full_features.loc[full_features["signal_pos"] == 4].iloc[0]

    assert pd.isna(cross_boundary_row["future_excess_return"])
    assert pd.isna(cross_boundary_row["ml_label"])
    assert not pd.isna(full_row["future_excess_return"])
    assert test_features["signal_pos"].tolist() == [6]
