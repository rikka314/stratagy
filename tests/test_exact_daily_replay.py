from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from model_test.config import build_stage_a_model_specs, load_research_config
from model_test.exact_daily_replay import (
    ExactDailyReplayError,
    _frozen_replay_spec,
    _safe_path_component,
    validate_daily_replay,
)


def _write_returns(path: Path, values: list[float]) -> None:
    pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(values), freq="B"),
            "strategy_return": values,
        }
    ).to_csv(path, index=False)


def test_validate_daily_replay_requires_exact_dates_returns_and_positions(tmp_path: Path) -> None:
    source_returns = tmp_path / "source_returns.csv"
    replay_returns = tmp_path / "replay_returns.csv"
    replay_daily = tmp_path / "daily.csv"
    values = [0.0, 0.01, -0.02]
    _write_returns(source_returns, values)
    _write_returns(replay_returns, values)
    pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=3, freq="B"),
            "target_position": [0.0, 0.5, 0.25],
            "turnover": [0.0, 0.5, 0.25],
            "strategy_return": values,
        }
    ).to_csv(replay_daily, index=False)

    proof = validate_daily_replay(
        source_returns_path=source_returns,
        replay_returns_path=replay_returns,
        replay_daily_path=replay_daily,
    )

    assert proof["row_count"] == 3
    assert proof["position_column"] == "target_position"
    assert proof["return_max_abs_diff"] == pytest.approx(0.0)
    assert proof["turnover_max_abs_diff"] == pytest.approx(0.0)

    daily = pd.read_csv(replay_daily)
    daily.loc[1, "strategy_return"] = 0.02
    daily.to_csv(replay_daily, index=False)
    with pytest.raises(ExactDailyReplayError, match="daily strategy_return"):
        validate_daily_replay(
            source_returns_path=source_returns,
            replay_returns_path=replay_returns,
            replay_daily_path=replay_daily,
        )


def test_validate_daily_replay_rejects_missing_turnover_or_position(tmp_path: Path) -> None:
    source_returns = tmp_path / "source_returns.csv"
    replay_returns = tmp_path / "replay_returns.csv"
    replay_daily = tmp_path / "daily.csv"
    _write_returns(source_returns, [0.0, 0.01])
    _write_returns(replay_returns, [0.0, 0.01])
    pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=2, freq="B"),
            "strategy_return": [0.0, 0.01],
        }
    ).to_csv(replay_daily, index=False)

    with pytest.raises(ExactDailyReplayError, match="target_position/position"):
        validate_daily_replay(
            source_returns_path=source_returns,
            replay_returns_path=replay_returns,
            replay_daily_path=replay_daily,
        )


def test_validate_daily_replay_rejects_nonfinite_or_inexact_turnover(tmp_path: Path) -> None:
    source_returns = tmp_path / "source_returns.csv"
    replay_returns = tmp_path / "replay_returns.csv"
    replay_daily = tmp_path / "daily.csv"
    _write_returns(source_returns, [0.0, 0.01])
    _write_returns(replay_returns, [0.0, 0.01])
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=2, freq="B"),
            "position": [0.0, 1.0],
            "target_position": [0.0, 1.0],
            "turnover": [0.0, 0.0],
            "strategy_return": [0.0, 0.01],
        }
    )
    daily.to_csv(replay_daily, index=False)

    with pytest.raises(ExactDailyReplayError, match="turnover differs"):
        validate_daily_replay(
            source_returns_path=source_returns,
            replay_returns_path=replay_returns,
            replay_daily_path=replay_daily,
        )

    daily.loc[1, "turnover"] = float("inf")
    daily.to_csv(replay_daily, index=False)
    with pytest.raises(ExactDailyReplayError, match="missing return/position/turnover"):
        validate_daily_replay(
            source_returns_path=source_returns,
            replay_returns_path=replay_returns,
            replay_daily_path=replay_daily,
        )


def test_frozen_replay_spec_disables_search_but_preserves_ml_contract() -> None:
    config = load_research_config("model-test/configs/full_us_deans_60.json")
    stage_a = {spec.model_id: spec for spec in build_stage_a_model_specs(config)}
    search = _frozen_replay_spec(stage_a["sm_bayesian"])

    assert search.request_payload["use_search"] is False
    assert search.request_payload["search_method"] == "bayesian"

    ml_source = stage_a["sm_bayesian"]
    ml_source = type(ml_source)(
        model_id="sm_bayesian_ml_lgbm",
        display_name="SM+Bayesian+ML-LGBM",
        stage="B",
        family_group="sm",
        request_payload={
            **ml_source.request_payload,
            "use_ml": True,
            "ml_model_type": "lgbm",
        },
    )
    ml = _frozen_replay_spec(ml_source)

    assert ml.request_payload["use_search"] is False
    assert ml.request_payload["use_ml"] is True
    assert ml.request_payload["ml_model_type"] == "lgbm"


def test_validate_daily_replay_rejects_return_drift(tmp_path: Path) -> None:
    source_returns = tmp_path / "source_returns.csv"
    replay_returns = tmp_path / "replay_returns.csv"
    replay_daily = tmp_path / "daily.csv"
    _write_returns(source_returns, [0.0, 0.01])
    _write_returns(replay_returns, [0.0, 0.02])
    replay_daily.write_text(
        json.dumps({"not": "csv"}),
        encoding="utf-8",
    )

    with pytest.raises(ExactDailyReplayError, match="source-net returns drifted"):
        validate_daily_replay(
            source_returns_path=source_returns,
            replay_returns_path=replay_returns,
            replay_daily_path=replay_daily,
        )


@pytest.mark.parametrize(
    "value",
    ["../escape", "..\\escape", ".", "..", "nested/name", "nested\\name", ""],
)
def test_exact_daily_paths_reject_unsafe_components(value: str) -> None:
    with pytest.raises(ExactDailyReplayError, match="single safe path component|non-empty"):
        _safe_path_component(value, field="symbol")
