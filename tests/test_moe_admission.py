from __future__ import annotations

import pandas as pd
import pytest

from model_test.admission import assess_w11_admission, calculate_execution_turnover
from model_test.models import ResearchConfig
from model_test import runner


def test_execution_turnover_uses_the_same_target_position_unit_for_each_symbol() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["BBB", "AAA", "AAA", "BBB"],
            "date": pd.to_datetime(["2026-01-02", "2026-01-02", "2026-01-03", "2026-01-03"]),
            "final_target_position": [0.50, 0.25, 1.00, 0.00],
        }
    )

    turnover = calculate_execution_turnover(frame)

    observed = turnover.set_index(["symbol", "date"])["execution_turnover"]
    assert observed.loc[("AAA", pd.Timestamp("2026-01-02"))] == pytest.approx(0.25)
    assert observed.loc[("AAA", pd.Timestamp("2026-01-03"))] == pytest.approx(0.75)
    assert observed.loc[("BBB", pd.Timestamp("2026-01-02"))] == pytest.approx(0.50)
    assert observed.loc[("BBB", pd.Timestamp("2026-01-03"))] == pytest.approx(0.50)


def test_w11_requires_four_splits_and_three_non_inferior_windows() -> None:
    split_summary = pd.DataFrame(
        {
            "split_id": ["wf_01", "wf_02", "wf_03", "wf_04"],
            "not_worse_than_adaptive": [True, True, True, False],
            "drawdown_not_worse": [True, True, True, True],
            "turnover_ratio": [1.0, 1.1, 1.2, 1.25],
        }
    )

    decision = assess_w11_admission(split_summary)

    assert decision["status"] == "admitted"
    assert decision["not_worse_window_count"] == 3
    assert decision["split_count"] == 4


def test_replay_profiles_read_only_the_frozen_source_snapshot(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = tmp_path / "outputs" / "full_cn_a_source"
    snapshot = source_root / "data_snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / "000001_daily.csv").write_text(
        "date,open,high,low,close,volume\n2026-01-01,1,1,1,1,1\n", encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "symbol": "000001",
                "company_name": "Ping An",
                "history_days": 1260,
                "recent_days": 252,
                "total_return_1y": 0.1,
                "annualized_vol_1y": 0.2,
                "max_drawdown_1y": -0.1,
                "avg_dollar_volume_1y": 10_000_000,
                "trend_bucket": "Up",
                "volatility_bucket": "Low",
                "segment_key": "Up__Low",
            }
        ]
    ).to_csv(source_root / "stocks.csv", index=False)
    (source_root / "data_manifest.json").write_text(
        '{"market": "CN_A", "data": {"snapshot_sha256": "frozen"}}', encoding="utf-8"
    )
    monkeypatch.setattr(runner, "WORKSPACE_ROOT", tmp_path)

    profiles = runner.load_replay_stock_profiles(ResearchConfig(name="replay", market="CN_A", replay_source_subdir="full_cn_a_source"))

    assert len(profiles) == 1
    assert profiles[0].symbol == "000001"
    assert profiles[0].source_kind == "frozen_replay"
    assert profiles[0].data_path == str((snapshot / "000001_daily.csv").resolve())
