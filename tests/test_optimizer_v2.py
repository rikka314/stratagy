from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

import core.optimizer as optimizer
from core.optimizer import SearchEvaluationCache, SearchEvaluationResult, SearchMetrics
from model_test.config import build_request_params_snapshot, build_stage_b_model_specs, load_research_config


def test_v2_candidate_normalization_and_validation() -> None:
    common_kwargs = {"hold_until_exit": True, "hold_min_position": 0.2}
    param_space = optimizer._resolve_search_param_space(common_kwargs)

    clipped = optimizer._clip_candidate_params(
        {
            "momentum_short": 2.2,
            "momentum_long": 80.0,
            "score_lookback": 120.0,
            "score_mid_pct": 0.10,
            "score_high_pct": 1.20,
            "entry_min_signals": 5.6,
            "exit_min_signals": -3.0,
            "use_strength_filter": 0,
            "use_rsi_filter": "true",
            "use_macd_filter": "false",
        },
        param_space=param_space,
    )

    assert clipped["momentum_short"] == 3
    assert clipped["momentum_long"] == 60
    assert clipped["score_lookback"] == 80
    assert clipped["score_mid_pct"] == pytest.approx(0.40)
    assert clipped["score_high_pct"] == pytest.approx(0.95)
    assert clipped["entry_min_signals"] == 5
    assert clipped["exit_min_signals"] == 1
    assert clipped["use_strength_filter"] is False
    assert clipped["use_rsi_filter"] is True
    assert clipped["use_macd_filter"] is False

    defaults = optimizer._normalize_candidate_params({}, param_space=param_space)

    invalid_momentum = dict(defaults, momentum_short=20, momentum_long=20)
    invalid_percentiles = dict(defaults, score_mid_pct=0.8, score_high_pct=0.8)
    invalid_signal_counts = dict(defaults, entry_min_signals=2, exit_min_signals=3)

    assert not optimizer._is_valid_candidate(invalid_momentum, param_space=param_space)
    assert not optimizer._is_valid_candidate(invalid_percentiles, param_space=param_space)
    assert not optimizer._is_valid_candidate(invalid_signal_counts, param_space=param_space)


def test_v2_metric_scoring_prefers_higher_excess_return_and_lower_turnover() -> None:
    slower = SearchMetrics(
        sharpe=1.0,
        total_return=0.22,
        max_drawdown=-0.10,
        excess_return=0.03,
        turnover=0.60,
    )
    cleaner = SearchMetrics(
        sharpe=1.0,
        total_return=0.20,
        max_drawdown=-0.10,
        excess_return=0.08,
        turnover=0.20,
    )

    assert optimizer._score_metrics(cleaner) > optimizer._score_metrics(slower)


def test_v2_search_evaluation_cache_normalizes_duplicate_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def fake_evaluate_candidate_frame(**kwargs):
        calls["count"] += 1
        return SearchEvaluationResult(
            params=dict(kwargs["candidate_params"]),
            full_signal_df=pd.DataFrame({"close": [1.0, 1.1], "target_position": [0.0, 1.0], "atr": [1.0, 1.0]}),
            raw_score=1.0,
            train_metrics=SearchMetrics(sharpe=0.5, total_return=0.1, max_drawdown=-0.02, excess_return=0.03, turnover=0.1),
            validation_metrics=SearchMetrics(
                sharpe=0.4,
                total_return=0.08,
                max_drawdown=-0.03,
                excess_return=0.02,
                turnover=0.1,
            ),
        )

    monkeypatch.setattr(optimizer, "_evaluate_candidate_frame", fake_evaluate_candidate_frame)

    cache = SearchEvaluationCache(
        df_raw=pd.DataFrame({"close": [1.0, 1.1, 1.2]}),
        split_idx=2,
        common_kwargs={"hold_until_exit": True, "hold_min_position": 0.2},
        fsm_mode=False,
    )

    first = cache.evaluate(
        {
            "ema_fast": 10,
            "ema_slow": 20,
            "momentum_short": 5.0,
            "momentum_long": 20.0,
            "use_strength_filter": 1,
            "use_rsi_filter": "true",
            "use_macd_filter": "false",
        }
    )
    second = cache.evaluate(
        {
            "ema_fast": 10,
            "ema_slow": 20,
            "momentum_short": 5,
            "momentum_long": 20,
            "use_strength_filter": True,
            "use_rsi_filter": True,
            "use_macd_filter": False,
        }
    )

    assert first is not None
    assert second is not None
    assert calls["count"] == 1
    assert cache.hits == 1
    assert first.params["use_strength_filter"] is True
    assert first.params["use_macd_filter"] is False


def test_v2_research_config_applies_request_and_stage_b_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "us_v2.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "us_v2",
                "request_params_overrides": {
                    "hold_until_exit": True,
                    "hold_min_position": 0.2,
                },
                "stage_b_request_overrides": {
                    "ml_horizon_days": 20,
                    "ml_min_excess_samples": 40,
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_research_config(config_path)
    params_snapshot = build_request_params_snapshot(config)
    specs = build_stage_b_model_specs(config, {"sm": "sm_bayesian"})

    assert params_snapshot["hold_until_exit"] is True
    assert params_snapshot["hold_min_position"] == pytest.approx(0.2)
    assert specs
    request = specs[0].build_request()
    assert request.ml_horizon_days == 20
    assert request.ml_min_excess_samples == 40


def test_random_search_uses_fixed_seed_42(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, int] = {}
    original_default_rng = optimizer.np.random.default_rng

    def fake_default_rng(seed=None):
        captured["seed"] = int(seed)
        return original_default_rng(seed)

    class DummyCache:
        param_space: dict[str, tuple[object, object, object, str]] = {}
        regularization_lam = 0.0

        def evaluate(self, _candidate):
            return None

    monkeypatch.setattr(optimizer.np.random, "default_rng", fake_default_rng)
    monkeypatch.setattr(optimizer, "_ensure_evaluation_cache", lambda **kwargs: DummyCache())

    result = optimizer.random_search_params(
        df_raw=pd.DataFrame(),
        split_idx=0,
        n_trials=0,
    )

    assert result is None
    assert captured["seed"] == 42


def test_bayesian_search_uses_seeded_tpe_sampler(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeLogging:
        WARNING = 0

        @staticmethod
        def set_verbosity(_value) -> None:
            return None

    class FakeSamplers:
        class TPESampler:
            def __init__(self, *, seed: int) -> None:
                captured["seed"] = seed

    class FakeStudy:
        def enqueue_trial(self, _params) -> None:
            return None

        def optimize(self, _objective, n_trials: int, show_progress_bar: bool, callbacks) -> None:
            captured["n_trials"] = n_trials
            captured["show_progress_bar"] = show_progress_bar
            for callback in callbacks:
                callback(self, None)

    class FakeOptuna:
        logging = FakeLogging()
        samplers = FakeSamplers

        @staticmethod
        def create_study(*, direction: str, sampler) -> FakeStudy:
            captured["direction"] = direction
            captured["sampler"] = sampler
            return FakeStudy()

    class DummyCache:
        param_space = {"ema_fast": (12, 5, 50, "int")}
        regularization_lam = 0.0

        def evaluate(self, _candidate):
            return None

    monkeypatch.setitem(sys.modules, "optuna", FakeOptuna)
    monkeypatch.setattr(optimizer, "_ensure_evaluation_cache", lambda **kwargs: DummyCache())

    result = optimizer.bayesian_optimize_params(
        df_raw=pd.DataFrame(),
        split_idx=0,
        n_trials=0,
    )

    assert result is None
    assert captured["direction"] == "maximize"
    assert captured["seed"] == 42
    assert captured["n_trials"] == 0
    assert captured["show_progress_bar"] is False
