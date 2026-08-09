from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from core.lightgbm_runtime import (
    LIGHTGBM_DEVICE_ENV,
    configure_lightgbm_environment,
    lightgbm_runtime_params,
    normalize_lightgbm_device,
    validate_lightgbm_device,
)
from model_test import preflight, runner, universe
from model_test.config import load_research_config
from model_test.models import ResearchConfig, StockProfile


def test_full_60_configs_freeze_research_scale_and_reproducibility() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    us = load_research_config(repo_root / "model-test" / "configs" / "full_us_deans_60.json")
    cn_a = load_research_config(repo_root / "model-test" / "configs" / "full_cn_a_deans_60.json")

    for config in (us, cn_a):
        assert config.main_pool_size == 60
        assert config.main_window_days == config.minimum_window_days == 1260
        assert config.rolling_window_days == 756
        assert config.rolling_window_count == 4
        assert config.search_trials == 240
        assert config.ga_population_size * (config.ga_generations + 1) == 240
        assert config.run_stage_b is config.run_robustness is True
        assert config.candidate_selection_mode == "hybrid"
        assert config.freeze_data_snapshot is True
        assert config.minimum_data_end_date == "2026-07-31"
        assert config.require_clean_worktree is True
        assert config.lightgbm_device_type == "cpu"
        assert config.selected_model_ids == ()

    estimate = preflight._task_estimate(us)
    assert estimate == {
        "pool_size": 60,
        "stage_a_model_count": 15,
        "stage_b_model_count_max": 4,
        "main_records_max": 1140,
        "rolling_records_max": 1920,
        "total_records_max": 3060,
    }


def test_hybrid_catalog_candidates_are_deterministic_and_not_head_only(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    pd.DataFrame(
        {
            "code": [f"{index:06d}" for index in range(1, 101)],
            "name": [f"Stock {index}" for index in range(1, 101)],
        }
    ).to_csv(catalog, index=False)
    config = ResearchConfig(
        name="hybrid",
        market="CN_A",
        max_catalog_candidates=20,
        candidate_selection_mode="hybrid",
        candidate_selection_seed=42,
    )

    first = universe._build_candidate_entries(config, catalog)
    second = universe._build_candidate_entries(config, catalog)

    assert first == second
    assert [item["symbol"] for item in first[:5]] == ["000001", "000002", "000003", "000004", "000005"]
    assert any(int(item["symbol"]) > 20 for item in first[5:])


def test_data_snapshot_freezes_files_without_overwriting_existing_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("date,open,high,low,close,volume\n2026-01-01,1,1,1,1,1\n", encoding="utf-8")
    profile = StockProfile(
        symbol="AAPL",
        company_name="Apple",
        source_kind="sample_csv",
        data_path=str(source),
        history_days=1,
        recent_days=1,
        total_return_1y=0.0,
        annualized_vol_1y=0.0,
        max_drawdown_1y=0.0,
        avg_dollar_volume_1y=1.0,
    )

    frozen = runner._freeze_stock_profile_data([profile], tmp_path / "run")
    snapshot = Path(frozen[0].data_path)
    original = snapshot.read_text(encoding="utf-8")
    source.write_text("changed", encoding="utf-8")
    frozen_again = runner._freeze_stock_profile_data([profile], tmp_path / "run")

    assert frozen[0].source_kind == "frozen_csv"
    assert Path(frozen_again[0].data_path).read_text(encoding="utf-8") == original


def test_stale_local_history_is_refetched_when_freshness_gate_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    pd.DataFrame(
        {"date": ["2026-01-02"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}
    ).to_csv(sample_dir / "aapl_daily.csv", index=False)
    fresh = pd.DataFrame(
        {"date": ["2026-08-07"], "open": [2], "high": [2], "low": [2], "close": [2], "volume": [2]}
    )
    cache = tmp_path / "cache.csv"
    monkeypatch.setattr(universe, "fetch_data", lambda *_args: fresh.copy())
    monkeypatch.setattr(universe, "_write_cache", lambda *_args: cache)
    monkeypatch.setattr(universe, "_resolve_data_cache_dir", lambda: tmp_path / "data_cache")
    config = ResearchConfig(
        name="freshness",
        market="US",
        sample_data_dir=str(sample_dir),
        minimum_data_end_date="2026-07-31",
    )

    frame, source_kind, source_path = universe.load_symbol_history("AAPL", config, prefer_sample=True)

    assert source_kind == "fetched"
    assert source_path == cache.resolve()
    assert pd.to_datetime(frame["date"]).max() == pd.Timestamp("2026-08-07")


def test_lightgbm_runtime_is_explicit_and_cpu_build_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_lightgbm_environment(device_type="cpu")
    assert lightgbm_runtime_params() == {"device_type": "cpu"}
    assert validate_lightgbm_device("cpu")["available"] is True
    with pytest.raises(ValueError, match="Unsupported LightGBM device"):
        normalize_lightgbm_device("automatic")
    monkeypatch.delenv(LIGHTGBM_DEVICE_ENV, raising=False)


def test_full_run_clean_worktree_gate_blocks_dirty_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_code_version", lambda: "abc123-dirty")
    config = ResearchConfig(name="full", require_clean_worktree=True)

    with pytest.raises(RuntimeError, match="clean git worktree"):
        runner._ensure_research_runtime(config)


def test_market_recommendation_payload_keeps_shared_benchmark_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "model-test"
    outputs_root = workspace_root / "outputs"
    monkeypatch.setattr(runner, "WORKSPACE_ROOT", workspace_root)

    def _record(symbol: str, model: str, window: str, annret: float, excess: float) -> dict[str, object]:
        return {
            "symbol": symbol,
            "model_id": model,
            "display_name": model.upper(),
            "window_id": window,
            "window_kind": "main" if window == "main" else "rolling",
            "status": "success",
            "test_cumret": annret / 2,
            "test_annret": annret,
            "test_sharpe": annret * 5,
            "test_maxdd": -0.1,
            "test_excess_return": excess,
            "net_total_return": annret / 2,
        }

    source_records = {
        "US": [
            *[_record(symbol, "naive", "main", 0.05, 0.0) for symbol in ("AAPL", "MSFT")],
            *[_record(symbol, "rsm", "main", 0.20, 0.15) for symbol in ("AAPL", "MSFT")],
            *[_record(symbol, "rsm", "rolling_1", 0.10, 0.05) for symbol in ("AAPL", "MSFT")],
        ],
        "CN_A": [
            *[_record(symbol, "naive", "main", 0.04, 0.0) for symbol in ("600519", "000001")],
        ],
    }
    for market, rows in source_records.items():
        source_dir = outputs_root / f"{market.lower()}_source"
        source_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_csv(source_dir / "runs.csv", index=False)
        (source_dir / "data_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "market": market,
                    "run_id": f"{market}-run",
                    "code_version": "clean-sha",
                    "data": {},
                    "universe": {},
                    "evaluation": {},
                    "execution": {"commission_bps": 1.0, "slippage_bps": 2.0},
                    "search": {},
                    "news": {},
                }
            ),
            encoding="utf-8",
        )
    config_path = tmp_path / "cross.json"
    config_path.write_text(
        json.dumps(
            {
                "output_subdir": "comparison",
                "cross_market_source_subdirs": {"US": "us_source", "CN_A": "cn_a_source"},
            }
        ),
        encoding="utf-8",
    )

    outputs = runner.run_research(config_path)
    recommendations = json.loads(outputs["market_strategy_recommendations"].read_text(encoding="utf-8"))

    assert recommendations["decision_scope"] == "market_specific"
    assert recommendations["markets"]["US"]["recommendation"] == "rsm"
    assert recommendations["shared_benchmark"]["eligible_strategy_ids"] == ["naive"]
    assert recommendations["shared_benchmark"]["markets"]["US"]["recommendation"] is None
