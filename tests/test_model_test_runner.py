from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from model_test import execution, observability, universe
from core.adaptive_regime import ADAPTIVE_MODEL_ID, ADAPTIVE_REGIME_KIND
from model_test.config import build_stage_a_model_specs, load_research_config
from model_test.models import ModelSpec, ResearchConfig, StockProfile, TaskSpec, WindowSpec
from model_test.reporting import build_report_payload, render_report_markdown
from model_test.summarize import MARKET_MATRIX_COLUMNS, build_market_strategy_matrix, build_market_strategy_recommendations
from model_test import runner



def test_market_strategy_matrix_and_recommendations_are_traceable() -> None:
    records = pd.DataFrame(
        [
            {
                "symbol": "AAPL", "model_id": "naive", "display_name": "Naive", "window_id": "main",
                "status": "success", "test_cumret": 0.03, "test_annret": 0.08, "test_sharpe": 0.5,
                "test_maxdd": -0.10, "test_excess_return": 0.0, "test_turnover": 0.1,
            },
            {
                "symbol": "AAPL", "model_id": "sm", "display_name": "SM", "window_id": "main",
                "status": "success", "test_cumret": 0.10, "test_annret": 0.24, "test_sharpe": 1.2,
                "test_maxdd": -0.08, "test_excess_return": 0.07, "test_turnover": 0.2,
                "net_total_return": 0.10, "total_transaction_cost": 0.001,
            },
            {
                "symbol": "MSFT", "model_id": "sm", "display_name": "SM", "window_id": "main",
                "status": "success", "test_cumret": 0.08, "test_annret": 0.20, "test_sharpe": 1.1,
                "test_maxdd": -0.09, "test_excess_return": 0.05, "test_turnover": 0.2,
                "net_total_return": 0.08, "total_transaction_cost": 0.001,
            },
            {
                "symbol": "AAPL", "model_id": "sm", "display_name": "SM", "window_id": "rolling_1",
                "status": "success", "test_cumret": 0.04, "test_annret": 0.10, "test_sharpe": 0.8,
                "test_maxdd": -0.07, "test_excess_return": 0.03, "net_total_return": 0.04,
            },
            {
                "symbol": "MSFT", "model_id": "sm", "display_name": "SM", "window_id": "rolling_1",
                "status": "success", "test_cumret": 0.03, "test_annret": 0.08, "test_sharpe": 0.7,
                "test_maxdd": -0.08, "test_excess_return": 0.02, "net_total_return": 0.03,
            },
            {
                "symbol": "TSLA", "model_id": "rsm", "display_name": "RSM", "window_id": "main",
                "status": "SKIPPED", "error_message": "unsupported market",
            },
        ]
    )

    matrix = build_market_strategy_matrix(records, "US")
    recommendations = build_market_strategy_recommendations(
        matrix,
        source_limitations={"CN_A": ["source run unavailable"]},
    )

    assert list(matrix.columns) == MARKET_MATRIX_COLUMNS
    assert matrix.loc[matrix["strategy_id"] == "sm", "successful_symbol_count"].iloc[0] == 2
    assert recommendations["markets"]["US"]["recommendation"] == "sm"
    assert recommendations["markets"]["US"]["evidence"]["matrix_rows"] == [
        {"market": "US", "strategy_id": "sm", "evaluation_window": "main"},
        {"market": "US", "strategy_id": "sm", "evaluation_window": "rolling_1"},
    ]
    assert recommendations["markets"]["CN_A"]["recommendation"] is None
    assert recommendations["markets"]["CN_A"]["confidence"] == "insufficient_evidence"


def test_recommendations_refuse_main_window_only_winner() -> None:
    matrix = pd.DataFrame(
        [
            {
                "market": "US", "strategy_id": "sm", "strategy_label": "SM",
                "evaluation_window": "main", "symbol_count": 6, "successful_symbol_count": 6,
                "failed_symbol_count": 0, "skipped_symbol_count": 0, "coverage_rate": 1.0,
                "total_return": 0.1, "annualized_return": 0.2, "sharpe": 1.2,
                "max_drawdown": -0.1, "total_turnover": 1.0, "total_transaction_cost": 0.001,
                "net_total_return": 0.1, "naive_win_rate": 0.8, "median_excess_return": 0.05,
                "rolling_rank_median": None, "rolling_direction_consistency": None,
                "degraded_run_rate": 0.0,
            }
        ],
        columns=MARKET_MATRIX_COLUMNS,
    )

    recommendations = build_market_strategy_recommendations(matrix)

    assert recommendations["markets"]["US"]["recommendation"] is None
    assert recommendations["markets"]["US"]["confidence"] == "insufficient_evidence"


def test_cross_market_aggregation_writes_contract_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = tmp_path / "model-test"
    outputs_root = workspace_root / "outputs"
    monkeypatch.setattr(runner, "WORKSPACE_ROOT", workspace_root)
    source_records = {
        "US": [
            {"symbol": "AAPL", "model_id": "sm", "display_name": "SM", "window_id": "main", "status": "success", "test_cumret": 0.1, "test_annret": 0.2, "test_sharpe": 1.1, "test_maxdd": -0.1, "test_excess_return": 0.05},
            {"symbol": "MSFT", "model_id": "sm", "display_name": "SM", "window_id": "main", "status": "success", "test_cumret": 0.08, "test_annret": 0.18, "test_sharpe": 1.0, "test_maxdd": -0.1, "test_excess_return": 0.04},
        ],
        "CN_A": [
            {"symbol": "600519", "model_id": "naive", "display_name": "Naive", "window_id": "main", "status": "success", "test_cumret": 0.02, "test_annret": 0.04, "test_sharpe": 0.2, "test_maxdd": -0.15, "test_excess_return": 0.0},
        ],
    }
    for market, rows in source_records.items():
        source_dir = outputs_root / f"{market.lower()}_source"
        source_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_csv(source_dir / "runs.csv", index=False)
        (source_dir / "data_manifest.json").write_text(json.dumps({
            "schema_version": "1.0",
            "market": market,
            "run_id": f"{market}-run",
            "code_version": "test-sha",
            "data": {"source": "fixture", "adjustment": "qfq", "start": "2023-01-01", "end": "2024-01-01"},
            "universe": {"symbols": [row["symbol"] for row in rows], "selection_rationale": "fixture"},
            "evaluation": {"train_end": "2023-09-01", "test_start": "2023-09-02", "rolling_windows": []},
            "execution": {"commission_bps": 1 if market == "US" else 3, "slippage_bps": 2 if market == "US" else 5},
            "search": {"budget": 24},
            "news": {"available_lag_trading_days": 1, "coverage_threshold": 0.0},
        }), encoding="utf-8")
    config_path = tmp_path / "cross_market.json"
    config_path.write_text(json.dumps({
        "name": "cross_market", "output_subdir": "comparison",
        "cross_market_source_subdirs": {"US": "us_source", "CN_A": "cn_a_source"},
    }), encoding="utf-8")

    output_paths = runner.run_research(config_path)

    matrix = pd.read_csv(output_paths["market_strategy_matrix"])
    recommendations = json.loads(output_paths["market_strategy_recommendations"].read_text(encoding="utf-8"))
    report = output_paths["market_strategy_report"].read_text(encoding="utf-8")
    assert list(matrix.columns) == MARKET_MATRIX_COLUMNS
    assert set(recommendations["markets"]) == {"US", "CN_A"}
    assert "Comparison run ID" in report
    assert "source run" in report
    assert "Decision Rule" in report


def test_window3b_configs_freeze_same_common_candidates_and_market_costs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    us = load_research_config(repo_root / "model-test" / "configs" / "deans_window3b_us.json")
    cn_a = load_research_config(repo_root / "model-test" / "configs" / "deans_window3b_cn_a.json")
    cross = load_research_config(
        repo_root / "model-test" / "configs" / "deans_window3b_cross_market.json"
    )

    assert us.selected_model_ids == cn_a.selected_model_ids
    assert len(us.smoke_symbols) == len(cn_a.smoke_symbols) == 6
    assert us.run_robustness is cn_a.run_robustness is True
    assert us.rolling_window_count == cn_a.rolling_window_count == 3
    assert us.search_trials == cn_a.search_trials == 24
    assert us.execution == {"market": "US", "commission_bps": 1.0, "slippage_bps": 2.0}
    assert cn_a.execution == {"market": "CN_A", "commission_bps": 3.0, "slippage_bps": 5.0}
    assert cross.cross_market_source_subdirs == {
        "US": "deans_window3b_us",
        "CN_A": "deans_window3b_cn_a",
    }

    repo_root = Path(__file__).resolve().parents[1]
    locked_config = load_research_config(repo_root / "model-test" / "configs" / "us_v2_locked_240.json")
    smoke_locked_config = load_research_config(repo_root / "model-test" / "configs" / "smoke_us_v2_locked_240.json")
    fast_config = load_research_config(repo_root / "model-test" / "configs" / "us_v2_fast.json")

    assert locked_config.search_trials == 240
    assert locked_config.ga_population_size == 24
    assert locked_config.ga_generations == 9
    assert locked_config.run_robustness is True
    assert locked_config.robustness_weight == 0.4
    assert locked_config.score_weights["beat_naive_rate"] == 20.0
    assert locked_config.score_weights["stability"] == 20.0

    assert smoke_locked_config.search_trials == 240
    assert smoke_locked_config.ga_population_size == 24
    assert smoke_locked_config.ga_generations == 9
    assert smoke_locked_config.run_robustness is True
    assert smoke_locked_config.robustness_weight == 0.4

    assert fast_config.search_trials == 120
    assert fast_config.ga_population_size == 12
    assert fast_config.ga_generations == 9
    assert fast_config.main_pool_size == 24
    assert fast_config.run_robustness is False
    assert fast_config.robustness_weight == 0.4


def test_stage_a_model_specs_include_rsm_variants() -> None:
    specs = build_stage_a_model_specs(ResearchConfig(name="rsm_case"))
    spec_map = {spec.model_id: spec for spec in specs}

    assert {"rsm", "rsm_no_market", "rsm_no_router", ADAPTIVE_MODEL_ID}.issubset(spec_map)
    assert spec_map["rsm"].request_payload == {"family": "regime", "regime_kind": "dual_state_router"}
    assert spec_map["rsm_no_market"].request_payload["regime_kind"] == "no_market"
    assert spec_map["rsm_no_router"].request_payload["regime_kind"] == "no_router"
    assert spec_map[ADAPTIVE_MODEL_ID].request_payload == {"family": "regime", "regime_kind": ADAPTIVE_REGIME_KIND}
    assert spec_map["rsm"].family_group == "rsm"


def test_cn_a_config_normalizes_market_and_applies_market_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "cn_a_deans_smoke.json"
    config_path.write_text(json.dumps({"market": " cn ", "smoke_mode": True}), encoding="utf-8")

    config = load_research_config(config_path)

    assert config.market == "CN_A"
    assert config.catalog_path == "core/catalogs/a_stock_catalog.csv"
    assert config.market_proxy_symbol == "000300"
    assert config.smoke_symbols == ("600519", "300750", "000001", "600036", "000858", "002594")
    assert config.effective_min_avg_traded_value == 50_000_000.0
    assert config.execution == {"market": "CN_A", "commission_bps": 3.0, "slippage_bps": 5.0}


def test_gate1_smoke_configs_freeze_market_costs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    us_config = load_research_config(repo_root / "model-test" / "configs" / "smoke_us_deans_gate1.json")
    cn_config = load_research_config(repo_root / "model-test" / "configs" / "smoke_cn_a_deans_gate1.json")

    assert us_config.execution == {"market": "US", "commission_bps": 1.0, "slippage_bps": 2.0}
    assert cn_config.execution == {"market": "CN_A", "commission_bps": 3.0, "slippage_bps": 5.0}
    assert us_config.selected_model_ids == cn_config.selected_model_ids == ("naive",)


def test_data_manifest_records_split_range_costs_and_seed(tmp_path: Path) -> None:
    source_path = tmp_path / "history.csv"
    pd.DataFrame({"date": pd.date_range("2026-01-01", periods=10, freq="B")}).to_csv(source_path, index=False)
    records_df = pd.DataFrame(
        [{
            "window_kind": "main",
            "status": "success",
            "window_start": "2026-01-01",
            "window_end": "2026-01-14",
            "data_path": str(source_path),
        }]
    )
    stocks_df = pd.DataFrame([{"symbol": "600519", "source_kind": "cache_csv"}])

    manifest = runner._build_data_manifest(ResearchConfig(name="manifest", market="CN_A", train_ratio=0.7), records_df, stocks_df)

    assert manifest["market"] == "CN_A"
    assert manifest["execution"] == {"market": "CN_A", "commission_bps": 3.0, "slippage_bps": 5.0}
    assert manifest["random_seed"] == 42
    assert manifest["data"]["start"] == "2026-01-01"
    assert manifest["data"]["end"] == "2026-01-14"
    assert manifest["evaluation"]["train_end"] == "2026-01-09"
    assert manifest["evaluation"]["test_start"] == "2026-01-12"


def test_unknown_market_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "bad_market.json"
    config_path.write_text(json.dumps({"market": "HK"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Expected US or CN_A"):
        load_research_config(config_path)


def test_cn_a_regime_specs_are_explicitly_skipped() -> None:
    specs = {spec.model_id: spec for spec in build_stage_a_model_specs(ResearchConfig(name="cn_case", market="CN_A"))}

    assert specs["sm"].skip_reason_for_market("CN_A") is None
    assert "SPY market proxy" in specs["rsm"].skip_reason_for_market("CN_A")
    assert "adaptive state artifacts" in specs[ADAPTIVE_MODEL_ID].skip_reason_for_market("CN_A")


def test_cn_a_catalog_and_profile_use_six_digit_symbols_and_amount_filter() -> None:
    config = ResearchConfig(name="cn_universe", market="CN_A", max_catalog_candidates=3)
    catalog_path = Path(__file__).resolve().parents[1] / "core" / "catalogs" / "a_stock_catalog.csv"

    candidates = universe._build_candidate_entries(config, catalog_path)
    metrics = universe._compute_recent_profile(
        pd.DataFrame(
            {
                "close": [10.0, 12.0],
                "volume": [100.0, 100.0],
                "amount": [60_000_000.0, 80_000_000.0],
            }
        ),
        lookback_days=2,
    )

    assert [candidate["symbol"] for candidate in candidates] == ["000001", "000002", "000004"]
    assert metrics["avg_dollar_volume_1y"] == 70_000_000.0


def test_unsupported_task_returns_explicit_skipped_record() -> None:
    model = ModelSpec(
        "rsm",
        "RSM",
        "A",
        "rsm",
        {"family": "regime", "regime_kind": "dual_state_router"},
        supported_markets=("US",),
        unsupported_market_reasons={"CN_A": "CN_A regime routing is not supported."},
    )
    task = TaskSpec(
        symbol="600519",
        company_name="贵州茅台",
        segment_key="Up__Mid",
        trend_bucket="Up",
        volatility_bucket="Mid",
        source_kind="sample_csv",
        data_path="not-read.csv",
        market="CN_A",
        adjust="qfq",
        model=model,
        window=WindowSpec(window_id="main", kind="main", start_idx=0, end_idx=3, train_ratio=0.7),
        params_snapshot={},
        skip_reason=model.skip_reason_for_market("CN_A"),
    )

    records = execution.run_task_batch([task])

    assert len(records) == 1
    assert records[0].status == "SKIPPED"
    assert records[0].error_message == "CN_A regime routing is not supported."


def test_resolve_rolling_specs_excludes_adaptive_router() -> None:
    model_summary_df = pd.DataFrame(
        [
            {"model_id": ADAPTIVE_MODEL_ID, "display_name": "RSM-AdaptiveV1", "total_score": 90.0},
            {"model_id": "sm_random", "display_name": "SM+Random", "total_score": 80.0},
            {"model_id": "fsm_genetic", "display_name": "FSM+Genetic", "total_score": 70.0},
        ]
    )
    final_specs = [
        ModelSpec(ADAPTIVE_MODEL_ID, "RSM-AdaptiveV1", "A", "rsm", {"family": "regime", "regime_kind": ADAPTIVE_REGIME_KIND}),
        ModelSpec("sm_random", "SM+Random", "A", "sm", {"family": "search", "search_base": "sm", "use_search": True, "search_method": "random"}),
        ModelSpec("fsm_genetic", "FSM+Genetic", "A", "fsm", {"family": "search", "search_base": "fsm", "use_search": True, "search_method": "genetic"}),
    ]

    rolling_specs = runner._resolve_rolling_specs(
        ResearchConfig(name="robust_case", robustness_weight=0.3, robustness_top_n=2),
        model_summary_df,
        final_specs,
    )

    assert [spec.model_id for spec in rolling_specs] == ["sm_random", "fsm_genetic"]


def test_mlflow_quantstats_config_defaults_and_profiles() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fast_config = load_research_config(repo_root / "model-test" / "configs" / "us_v2_fast.json")
    smoke_mlflow_qs = load_research_config(
        repo_root / "model-test" / "configs" / "smoke_us_v2_locked_240_mlflow_qs.json"
    )
    fast_mlflow_qs = load_research_config(repo_root / "model-test" / "configs" / "us_v2_fast_mlflow_qs.json")

    assert fast_config.enable_mlflow is False
    assert fast_config.mlflow_experiment_name == "strategy-model-test"
    assert fast_config.mlflow_tracking_uri is None
    assert fast_config.enable_quantstats is False
    assert fast_config.quantstats_top_n == 5

    assert smoke_mlflow_qs.enable_mlflow is True
    assert smoke_mlflow_qs.enable_quantstats is True
    assert smoke_mlflow_qs.output_subdir == "smoke_us_v2_locked_240_mlflow_qs"

    assert fast_mlflow_qs.enable_mlflow is True
    assert fast_mlflow_qs.enable_quantstats is True
    assert fast_mlflow_qs.output_subdir == "us_v2_fast_mlflow_qs"
    assert fast_mlflow_qs.run_robustness is False


def test_build_rolling_tasks_freezes_main_params_and_disables_search(monkeypatch: pytest.MonkeyPatch) -> None:
    config = ResearchConfig(
        name="locked_case",
        train_ratio=0.7,
        rolling_window_count=1,
        rolling_window_days=30,
        rolling_step_days=10,
    )
    profile = StockProfile(
        symbol="AAPL",
        company_name="Apple Inc.",
        source_kind="sample_csv",
        data_path="data/aapl_daily.csv",
        history_days=120,
        recent_days=120,
        total_return_1y=0.1,
        annualized_vol_1y=0.2,
        max_drawdown_1y=-0.1,
        avg_dollar_volume_1y=1_000_000.0,
        trend_bucket="Up",
        volatility_bucket="Mid",
        segment_key="Up__Mid",
    )
    rolling_window = WindowSpec(
        window_id="rolling_1",
        kind="rolling",
        start_idx=10,
        end_idx=40,
        train_ratio=0.7,
    )
    monkeypatch.setattr(runner, "build_rolling_windows", lambda _config, _df_len: [rolling_window])

    search_spec = ModelSpec(
        "sm_bayesian",
        "SM+Bayesian",
        "A",
        "sm",
        {
            "family": "search",
            "search_base": "sm",
            "use_search": True,
            "search_method": "bayesian",
            "search_trials": 240,
            "ga_population_size": 24,
            "ga_generations": 9,
        },
    )
    ml_spec = ModelSpec(
        "sm_bayesian_ml_logistic",
        "SM+Bayesian+ML-LR",
        "B",
        "sm",
        {
            "family": "search",
            "search_base": "sm",
            "use_search": True,
            "search_method": "bayesian",
            "search_trials": 240,
            "ga_population_size": 24,
            "ga_generations": 9,
            "use_ml": True,
            "ml_model_type": "logistic",
            "ml_horizon_days": 20,
            "ml_min_excess_samples": 40,
        },
    )

    main_records_df = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "window_kind": "main",
                "status": "success",
                "model_id": "sm_bayesian",
                "params_snapshot_json": json.dumps({"ema_fast": 11, "ema_slow": 33, "stop_loss_mult": 1.5}),
            },
            {
                "symbol": "AAPL",
                "window_kind": "main",
                "status": "success",
                "model_id": "sm_bayesian_ml_logistic",
                "params_snapshot_json": json.dumps({"ema_fast": 13, "ema_slow": 55, "stop_loss_mult": 2.0}),
            },
        ]
    )
    lookup = runner._build_main_record_lookup(main_records_df)

    tasks = runner._build_rolling_tasks(
        [profile],
        [search_spec, ml_spec],
        config,
        {"ema_fast": 20, "ema_slow": 60, "stop_loss_mult": 4.0},
        lookup,
    )

    assert len(tasks) == 2

    search_task = next(task for task in tasks if task.model.model_id == "sm_bayesian")
    ml_task = next(task for task in tasks if task.model.model_id == "sm_bayesian_ml_logistic")

    assert search_task.model.request_payload["use_search"] is False
    assert search_task.model.request_payload["search_method"] == "bayesian"
    assert search_task.params_snapshot["ema_fast"] == 11
    assert search_task.params_snapshot["ema_slow"] == 33

    assert ml_task.model.request_payload["use_search"] is False
    assert ml_task.model.request_payload["use_ml"] is True
    assert ml_task.model.request_payload["ml_model_type"] == "logistic"
    assert ml_task.params_snapshot["ema_fast"] == 13
    assert ml_task.params_snapshot["ema_slow"] == 55


def test_load_checkpoint_records_keeps_latest_resume_record(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / runner.CHECKPOINT_RUNS_FILENAME
    pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "window_id": "main",
                "model_id": "sm_random",
                "status": "success",
                "params_snapshot_json": json.dumps({"ema_fast": 10}),
            },
            {
                "symbol": "AAPL",
                "window_id": "main",
                "model_id": "sm_random",
                "status": "success",
                "params_snapshot_json": json.dumps({"ema_fast": 20}),
            },
        ]
    ).to_csv(checkpoint_path, index=False)

    records_df = runner._load_checkpoint_records(output_dir)

    assert len(records_df) == 1
    assert json.loads(records_df.iloc[0]["params_snapshot_json"])["ema_fast"] == 20


def test_load_checkpoint_records_preserves_a_share_symbol_leading_zeros(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / runner.CHECKPOINT_RUNS_FILENAME
    pd.DataFrame(
        [
            {
                "symbol": "000001",
                "window_id": "main",
                "model_id": "naive",
                "status": "success",
            }
        ]
    ).to_csv(checkpoint_path, index=False)

    records_df = runner._load_checkpoint_records(output_dir)

    assert records_df.iloc[0]["symbol"] == "000001"


def test_report_payload_includes_uniform_search_budget_note() -> None:
    config = ResearchConfig(
        name="locked_case",
        search_trials=240,
        ga_population_size=24,
        ga_generations=9,
        robustness_weight=0.3,
    )

    payload = build_report_payload(
        config=config,
        stocks_df=pd.DataFrame(),
        model_summary_df=pd.DataFrame(),
        segment_summary_df=pd.DataFrame(),
        robustness_df=pd.DataFrame(),
        records_df=pd.DataFrame(),
        stage_winners={},
    )
    markdown = render_report_markdown(payload)

    assert payload["search_budget"]["uniform_objective_budget"] is True
    assert payload["search_budget"]["effective_search_budget"] == 240
    assert "240" in markdown
    assert "fixed seed `42`" in markdown


def test_report_payload_includes_adaptive_router_sections() -> None:
    payload = build_report_payload(
        config=ResearchConfig(name="adaptive_case"),
        stocks_df=pd.DataFrame(),
        model_summary_df=pd.DataFrame(),
        segment_summary_df=pd.DataFrame(),
        robustness_df=pd.DataFrame(),
        records_df=pd.DataFrame(),
        stage_winners={},
        adaptive_router_summary={
            "state_summary": [
                {
                    "state_id": 0,
                    "sample_ratio": 0.25,
                    "dominant_global_model_id": "sm_random",
                    "top_features": ["ret_20", "adx", "corr_60"],
                }
            ],
            "routing_summary": [
                {
                    "state_id": 0,
                    "dominant_symbol_model_id": "sm_random",
                    "symbol_policy_coverage": 0.5,
                    "global_model_id": "sm_random",
                }
            ],
        },
    )

    markdown = render_report_markdown(payload)

    assert payload["adaptive_router"]["state_summary"][0]["state_id"] == 0
    assert "Adaptive Regime State Summary" in markdown
    assert "Adaptive Routing Summary" in markdown


def test_missing_optional_dependencies_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observability, "_optional_dependency_available", lambda _name: False)

    with pytest.raises(RuntimeError, match="mlflow, quantstats"):
        observability.ensure_optional_dependencies(
            ResearchConfig(
                name="obs_case",
                enable_mlflow=True,
                enable_quantstats=True,
            )
        )


def test_run_artifact_export_writes_bundle_and_path_fields(tmp_path: Path) -> None:
    model = ModelSpec(
        "sm_bayesian",
        "SM+Bayesian",
        "A",
        "sm",
        {
            "family": "search",
            "search_base": "sm",
            "use_search": True,
            "search_method": "bayesian",
            "search_trials": 240,
            "ga_population_size": 24,
            "ga_generations": 9,
        },
    )
    task = TaskSpec(
        symbol="AAPL",
        company_name="Apple Inc.",
        segment_key="Up__Mid",
        trend_bucket="Up",
        volatility_bucket="Mid",
        source_kind="sample_csv",
        data_path="data/aapl_daily.csv",
        market="US",
        adjust="qfq",
        model=model,
        window=WindowSpec(window_id="main", kind="main", start_idx=0, end_idx=3, train_ratio=0.7),
        params_snapshot={"ema_fast": 11, "ema_slow": 33, "stop_loss_mult": 1.5},
    )
    train_sim_df = pd.DataFrame(
        {
            "strategy_equity": [1.0, 1.1, 1.21],
            "buy_hold_equity": [1.0, 1.05, 1.1025],
        }
    )
    test_sim_df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "strategy_return": [0.0, 0.10, -0.05],
            "gross_strategy_return": [0.0, 0.101, -0.049],
            "turnover": [0.0, 1.0, 0.5],
            "transaction_cost": [0.0, 0.001, 0.0005],
            "strategy_equity": [1.0, 1.10, 1.045],
            "buy_hold_equity": [1.0, 1.04, 1.0816],
        }
    )
    date_index = pd.to_datetime(test_sim_df["date"])
    artifact = SimpleNamespace(
        id="artifact-1",
        pipeline_lineage=[
            SimpleNamespace(
                stage_key="search",
                display_label="SM+Bayesian",
                short_label="SMB",
                train_sim_df=train_sim_df,
                metadata={"search_method": "bayesian"},
            )
        ],
        params_snapshot={"ema_fast": 11, "ema_slow": 33, "stop_loss_mult": 1.5},
        ml_quality={"precision": 0.6},
        eval={
            "cumret": 0.20,
            "annret": 0.30,
            "maxdd": -0.10,
            "sharpe": 1.2,
            "winrate": 0.5,
            "pnl_ratio": 1.5,
            "turnover": 0.2,
            "excess_return": 0.1,
        },
        returns_series=pd.Series([0.0, 0.10, -0.05], index=date_index, name="returns"),
        equity_series=pd.Series([1.0, 1.10, 1.045], index=date_index, name="equity"),
        test_sim_df=test_sim_df,
        trades_df=pd.DataFrame({"entry_date": ["2024-01-02"], "exit_date": ["2024-01-03"]}),
    )
    result = SimpleNamespace(
        status="success",
        error_message=None,
        warnings=[],
        info_messages=[],
        artifact=artifact,
    )

    record = execution._record_from_result(
        task,
        window_start="2024-01-01",
        window_end="2024-01-03",
        window_days=3,
        result=result,
        artifacts_root=tmp_path / "artifacts",
    )

    artifact_dir = tmp_path / "artifacts" / "AAPL" / "main" / "sm_bayesian"
    assert artifact_dir.exists()
    assert record.artifact_id == "artifact-1"
    assert Path(record.artifact_dir) == artifact_dir
    assert Path(record.returns_path).exists()
    assert Path(record.benchmark_returns_path).exists()
    assert Path(record.equity_path).exists()
    assert Path(record.trades_path).exists()
    assert record.total_turnover == pytest.approx(1.5)
    assert record.total_transaction_cost == pytest.approx(0.0015)
    assert record.gross_total_return == pytest.approx((1.101 * 0.951) - 1.0)
    assert record.net_total_return == pytest.approx((1.10 * 0.95) - 1.0)

    returns_df = pd.read_csv(record.returns_path)
    benchmark_df = pd.read_csv(record.benchmark_returns_path)
    equity_df = pd.read_csv(record.equity_path)
    metadata = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))

    assert list(returns_df.columns) == ["date", "strategy_return"]
    assert list(benchmark_df.columns) == ["date", "benchmark_return"]
    assert list(equity_df.columns) == ["date", "strategy_equity"]
    assert metadata["artifact_id"] == "artifact-1"
    assert metadata["model_id"] == "sm_bayesian"
    assert metadata["status"] == "success"
    assert metadata["lineage"][0]["stage_key"] == "search"

    skipped = execution._skipped_record(task)
    assert skipped.returns_path is None
    assert skipped.benchmark_returns_path is None
    assert skipped.equity_path is None
    assert skipped.trades_path is None


def test_quantstats_generation_updates_summary_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class _Reports:
        @staticmethod
        def html(returns, benchmark=None, output=None, title=None):
            calls.append(
                {
                    "returns": returns.copy(),
                    "benchmark": benchmark.copy() if benchmark is not None else None,
                    "output": output,
                    "title": title,
                }
            )
            Path(output).write_text("<html>tear sheet</html>", encoding="utf-8")

    monkeypatch.setattr(
        observability,
        "_import_optional_dependency",
        lambda module_name: SimpleNamespace(reports=_Reports()) if module_name == "quantstats" else None,
    )

    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    def _write_series_csv(path: Path, column: str, rows: list[tuple[str, float]]) -> str:
        pd.DataFrame(rows, columns=["date", column]).to_csv(path, index=False)
        return str(path)

    model_top_returns_1 = _write_series_csv(
        output_dir / "top_1_returns.csv",
        "strategy_return",
        [("2024-01-01", 0.10), ("2024-01-02", 0.20)],
    )
    model_top_returns_2 = _write_series_csv(
        output_dir / "top_2_returns.csv",
        "strategy_return",
        [("2024-01-02", 0.30), ("2024-01-03", 0.50)],
    )
    model_top_benchmark_1 = _write_series_csv(
        output_dir / "top_1_benchmark.csv",
        "benchmark_return",
        [("2024-01-01", 0.02), ("2024-01-02", 0.04)],
    )
    model_top_benchmark_2 = _write_series_csv(
        output_dir / "top_2_benchmark.csv",
        "benchmark_return",
        [("2024-01-02", 0.06), ("2024-01-03", 0.08)],
    )
    model_mid_returns = _write_series_csv(
        output_dir / "mid_returns.csv",
        "strategy_return",
        [("2024-01-01", 0.05), ("2024-01-02", 0.07)],
    )
    model_mid_benchmark = _write_series_csv(
        output_dir / "mid_benchmark.csv",
        "benchmark_return",
        [("2024-01-01", 0.01), ("2024-01-02", 0.02)],
    )
    model_low_returns = _write_series_csv(
        output_dir / "low_returns.csv",
        "strategy_return",
        [("2024-01-01", -0.01), ("2024-01-02", 0.01)],
    )
    model_low_benchmark = _write_series_csv(
        output_dir / "low_benchmark.csv",
        "benchmark_return",
        [("2024-01-01", 0.00), ("2024-01-02", 0.01)],
    )

    records_df = pd.DataFrame(
        [
                {
                    "symbol": "AAPL",
                    "window_id": "main",
                    "window_kind": "main",
                    "status": "success",
                    "model_id": "model_top",
                "returns_path": model_top_returns_1,
                "benchmark_returns_path": model_top_benchmark_1,
            },
                {
                    "symbol": "NVDA",
                    "window_id": "main",
                    "window_kind": "main",
                    "status": "degraded",
                    "model_id": "model_top",
                "returns_path": model_top_returns_2,
                "benchmark_returns_path": model_top_benchmark_2,
            },
                {
                    "symbol": "MSFT",
                    "window_id": "main",
                    "window_kind": "main",
                    "status": "success",
                    "model_id": "model_mid",
                "returns_path": model_mid_returns,
                "benchmark_returns_path": model_mid_benchmark,
            },
                {
                    "symbol": "TSLA",
                    "window_id": "main",
                    "window_kind": "main",
                    "status": "success",
                    "model_id": "model_low",
                "returns_path": model_low_returns,
                "benchmark_returns_path": model_low_benchmark,
            },
        ]
    )
    model_summary_df = pd.DataFrame(
        [
            {
                "model_id": "model_top",
                "display_name": "Model Top",
                "family_group": "sm",
                "stage": "A",
                "beat_naive_rate": 0.75,
                "median_sharpe": 1.4,
                "median_excess_return": 0.12,
                "total_score": 88.0,
                "main_total_score": 90.0,
                "robustness_total_score": 82.0,
                "rank": 1,
            },
            {
                "model_id": "model_mid",
                "display_name": "Model Mid",
                "family_group": "fsm",
                "stage": "A",
                "beat_naive_rate": 0.60,
                "median_sharpe": 1.1,
                "median_excess_return": 0.08,
                "total_score": 72.0,
                "main_total_score": 72.0,
                "robustness_total_score": None,
                "rank": 2,
            },
            {
                "model_id": "model_low",
                "display_name": "Model Low",
                "family_group": "baseline",
                "stage": "A",
                "beat_naive_rate": 0.30,
                "median_sharpe": 0.4,
                "median_excess_return": -0.01,
                "total_score": 40.0,
                "main_total_score": 40.0,
                "robustness_total_score": None,
                "rank": 3,
            },
        ]
    )

    updated_summary, quantstats_entries, quantstats_dir = observability.generate_quantstats_outputs(
        config=ResearchConfig(name="obs_case", enable_quantstats=True, quantstats_top_n=2),
        output_dir=output_dir,
        model_summary_df=model_summary_df,
        records_df=records_df,
    )

    assert quantstats_dir.exists()
    assert len(quantstats_entries) == 2
    assert calls and len(calls) == 2
    assert updated_summary.loc[updated_summary["model_id"] == "model_top", "quantstats_html_path"].iloc[0]
    assert updated_summary.loc[updated_summary["model_id"] == "model_mid", "quantstats_html_path"].iloc[0]
    assert pd.isna(updated_summary.loc[updated_summary["model_id"] == "model_low", "quantstats_html_path"].iloc[0])

    pooled_returns = pd.read_csv(quantstats_dir / "1_model_top" / "returns.csv")
    assert pooled_returns["strategy_return"].round(4).tolist() == [0.1, 0.25, 0.5]

    payload = build_report_payload(
        config=ResearchConfig(name="obs_case"),
        stocks_df=pd.DataFrame(),
        model_summary_df=updated_summary,
        segment_summary_df=pd.DataFrame(),
        robustness_df=pd.DataFrame(),
        records_df=records_df,
        stage_winners={},
        quantstats_entries=quantstats_entries,
    )
    markdown = render_report_markdown(payload)

    assert payload["quantstats"][0]["model_id"] == "model_top"
    assert "QuantStats Tear Sheets" in markdown
    assert "1_model_top" in markdown


def test_mlflow_logging_writes_manifest_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "model-test"
    workspace_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(observability, "WORKSPACE_ROOT", workspace_root)

    captured: dict[str, object] = {
        "params": {},
        "metrics": {},
        "artifact_paths": [],
        "artifact_dirs": [],
    }

    class _RunInfo:
        run_id = "run-123"
        artifact_uri = "file:///tmp/mlruns/run-123/artifacts"

    class _ActiveRun:
        info = _RunInfo()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeMlflow:
        def set_tracking_uri(self, uri):
            captured["tracking_uri"] = uri

        def set_experiment(self, name):
            captured["experiment_name"] = name

        def start_run(self, run_name=None):
            captured["run_name"] = run_name
            return _ActiveRun()

        def log_param(self, key, value):
            captured["params"][key] = value

        def set_tags(self, tags):
            captured["tags"] = tags

        def log_metric(self, key, value):
            captured["metrics"][key] = value

        def log_artifact(self, path):
            captured["artifact_paths"].append(Path(path).name)

        def log_artifacts(self, path, artifact_path=None):
            captured["artifact_dirs"].append((Path(path).name, artifact_path))

    monkeypatch.setattr(
        observability,
        "_import_optional_dependency",
        lambda module_name: _FakeMlflow() if module_name == "mlflow" else None,
    )

    output_dir = tmp_path / "outputs" / "obs_case"
    output_dir.mkdir(parents=True, exist_ok=True)
    quantstats_dir = output_dir / "quantstats"
    quantstats_dir.mkdir(parents=True, exist_ok=True)
    (quantstats_dir / "tearsheet.html").write_text("<html></html>", encoding="utf-8")

    artifact_paths = {
        "runs": output_dir / "runs.csv",
        "stocks": output_dir / "stocks.csv",
        "model_summary": output_dir / "model_summary.csv",
        "segment_summary": output_dir / "segment_summary.csv",
        "robustness_summary": output_dir / "robustness_summary.csv",
        "report_json": output_dir / "report.json",
        "report_md": output_dir / "report.md",
    }
    for path in artifact_paths.values():
        path.write_text("placeholder", encoding="utf-8")

    mlflow_run_path = observability.log_research_run_to_mlflow(
        config=ResearchConfig(name="obs_case", enable_mlflow=True),
        output_dir=output_dir,
        records_df=pd.DataFrame(
            [
                {"symbol": "AAPL", "status": "success"},
                {"symbol": "NVDA", "status": "degraded"},
                {"symbol": "TSLA", "status": "failed"},
                {"symbol": "MSFT", "status": "SKIPPED"},
            ]
        ),
        model_summary_df=pd.DataFrame(
            [
                {
                    "model_id": "model_top",
                    "total_score": 88.0,
                    "main_total_score": 90.0,
                    "robustness_total_score": 82.0,
                }
            ]
        ),
        artifacts=artifact_paths,
        quantstats_dir=quantstats_dir,
    )

    manifest = json.loads(mlflow_run_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-123"
    assert manifest["experiment_name"] == "strategy-model-test"
    assert captured["experiment_name"] == "strategy-model-test"
    assert captured["params"]["enable_mlflow"] is True
    assert captured["metrics"]["record_count"] == 4.0
    assert "runs.csv" in captured["artifact_paths"]
    assert "mlflow_run.json" in captured["artifact_paths"]
    assert ("quantstats", "quantstats") in captured["artifact_dirs"]
