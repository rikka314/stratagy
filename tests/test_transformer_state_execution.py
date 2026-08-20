from __future__ import annotations

import json

import pandas as pd
import pytest

from model_test.transformer_state_execution import (
    TransformerStateExecutionError,
    assert_summary_reconstructs,
    execute_state_decisions,
    reconstruct_execution_summary,
)


def _panel() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=13)
    rows: list[dict[str, object]] = []
    specifications = {
        "sm": ([0.01] * 13, [0.25, 0.50, 0.75, 1.00, 0.75, 0.50, 0.25, 0.50, 0.75, 1.00, 0.75, 0.50, 0.25]),
        "adaptive_router": ([0.002] * 13, [0.20] * 13),
        "full_best": ([0.004] * 13, [0.40] * 13),
    }
    for expert_id, (returns, positions) in specifications.items():
        for index, date in enumerate(dates):
            rows.append(
                {
                    "date": date,
                    "symbol": "AAA",
                    "market": "US",
                    "expert_id": expert_id,
                    "expert_status": "available",
                    "strategy_return": returns[index],
                    "target_position": positions[index],
                    "close": 100.0 if index < 3 else 90.0,
                    "asset_return_1": -0.10 if index == 3 else 0.0,
                    "atr_pct": 0.02,
                    "benchmark_return": 0.0,
                    "regime": "calm",
                }
            )
    return pd.DataFrame(rows)


def _decisions() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=13)
    return pd.DataFrame(
        [
            {
                "split_id": "fold_1",
                "date": dates[0],
                "symbol": "AAA",
                "market": "US",
                "threshold": "state_match_balanced",
                "match_status": "matched",
                "selected_expert_id": "sm",
                "actual_best_expert_5d": "sm",
                "selected_realized_5d_utility": 0.4,
                "realized_best_5d_utility": 0.4,
                "top_k_expert_ids_json": json.dumps(["sm", "full_best"]),
            },
            # Must be ignored because AAA is still inside the first five-day window.
            {
                "split_id": "fold_1",
                "date": dates[2],
                "symbol": "AAA",
                "market": "US",
                "threshold": "state_match_balanced",
                "match_status": "matched",
                "selected_expert_id": "full_best",
            },
            {
                "split_id": "fold_1",
                "date": dates[5],
                "symbol": "AAA",
                "market": "US",
                "threshold": "state_match_balanced",
                "match_status": "unmatched",
                "selected_expert_id": None,
                "unmatched_reason": "similarity_below_threshold",
            },
        ]
    )


def _config() -> dict[str, object]:
    return {
        "execution": {
            "holding_days": 5,
            "matching_frequency_days": 5,
            "jump_guard_selection": "validation_only",
        },
        "selected_jump_guard": {
            "single_day_jump_down_atr_multiple": 2.0,
            "entry_drawdown_atr_multiple": 3.0,
            "market_crash_return": -0.04,
        },
        "fallback_expert_ids": {
            "full_run_best_guard": "full_best",
            "adaptive_guard": "adaptive_router",
            "cash_on_unmatched": "Cash",
        },
    }


def test_five_day_state_machine_guard_and_fallback_variants_are_auditable() -> None:
    result = execute_state_decisions(_decisions(), _panel(), config=_config())
    daily = result.daily_audit

    primary = daily.loc[daily["variant"].eq("full_run_best_guard")].sort_values("date")
    first_window = primary.loc[primary["decision_date"].eq(pd.Timestamp("2026-01-02"))]
    assert len(first_window) == 5
    assert first_window["selected_expert_id"].unique().tolist() == ["sm"]
    assert first_window["executed_expert_id"].tolist() == ["sm", "sm", "sm", "Cash", "Cash"]
    trigger = first_window.loc[first_window["jump_guard_trigger"].notna()].iloc[0]
    assert trigger["date"] == pd.Timestamp("2026-01-07")
    assert trigger["jump_guard_trigger"] == "single_day_jump_down"
    assert trigger["risk_exit_effective_date"] == pd.Timestamp("2026-01-08")
    assert trigger["strategy_return"] == pytest.approx(0.01)
    assert first_window.iloc[3]["strategy_return"] == 0.0
    assert first_window.iloc[3]["target_position"] == 0.0
    assert first_window["counterfactual_no_guard_return"].tolist() == pytest.approx([0.01] * 5)

    second = daily.loc[daily["decision_date"].eq(pd.Timestamp("2026-01-09"))]
    assert set(second.loc[second["variant"].eq("full_run_best_guard"), "executed_expert_id"]) == {"full_best"}
    assert set(second.loc[second["variant"].eq("adaptive_guard"), "executed_expert_id"]) == {"adaptive_router"}
    assert set(second.loc[second["variant"].eq("cash_on_unmatched"), "executed_expert_id"]) == {"Cash"}
    assert set(second["attribution_source"]) == {
        "full_run_best_guard", "adaptive_guard", "cash", "full_run_best_only"
    }

    # Source net strategy_return is consumed exactly; no state-level recharge is deducted.
    first_primary_day = first_window.iloc[0]
    assert first_primary_day["strategy_return"] == pytest.approx(0.01)
    assert first_primary_day["decision_target_position"] == pytest.approx(0.25)
    assert first_primary_day["source_expert_target_position"] == pytest.approx(0.50)
    assert first_primary_day["execution_turnover"] == pytest.approx(0.25)
    assert result.skipped_decisions["skip_reason"].tolist() == ["holding_window_active"] * 4
    assert_summary_reconstructs(daily, result.summary)


def test_summary_exactly_reconstructs_returns_turnover_coverage_and_attribution() -> None:
    result = execute_state_decisions(_decisions(), _panel(), config=_config())
    rebuilt = reconstruct_execution_summary(result.daily_audit)

    pd.testing.assert_frame_equal(result.summary, rebuilt)
    row = result.summary.loc[
        (result.summary["variant"] == "full_run_best_guard")
        & (result.summary["threshold"] == "state_match_balanced")
    ].iloc[0]
    assert row["matched_decision_coverage"] == pytest.approx(0.5)
    assert row["fallback_full_run_best_coverage"] == pytest.approx(0.5)
    assert row["selected_expert_frequency_json"] == json.dumps(
        {"full_best": 0.5, "sm": 0.5}, sort_keys=True, separators=(",", ":")
    )
    assert row["actual_best_expert_hit_rate"] == pytest.approx(1.0)
    assert row["top_k_retrieval_consistency"] == pytest.approx(1.0)
    assert row["predicted_vs_realized_5d_utility_regret"] == pytest.approx(0.0)
    assert row["match_return_contribution"] + row["full_run_best_guard_return_contribution"] == pytest.approx(
        row["total_return"]
    )

    corrupted = result.summary.copy()
    corrupted.loc[0, "total_return"] += 0.01
    with pytest.raises(TransformerStateExecutionError, match="does not exactly reconstruct"):
        assert_summary_reconstructs(result.daily_audit, corrupted)


def test_execution_rejects_duplicate_panel_keys_and_missing_source_net_values() -> None:
    duplicated = pd.concat([_panel(), _panel().iloc[[0]]], ignore_index=True)
    with pytest.raises(TransformerStateExecutionError, match="unique"):
        execute_state_decisions(_decisions(), duplicated, config=_config())

    missing = _panel()
    missing.loc[(missing["expert_id"] == "sm") & (missing["date"] == pd.Timestamp("2026-01-05")), "strategy_return"] = None
    with pytest.raises(TransformerStateExecutionError, match="source-net strategy_return"):
        execute_state_decisions(_decisions(), missing, config=_config())


def test_w16_decision_aliases_and_neighbor_fallback_audit_are_preserved() -> None:
    decision = _decisions().iloc[[1]].copy()
    decision["date"] = pd.Timestamp("2026-01-02")
    decision = decision.drop(columns=["threshold", "match_status"])
    decision["threshold_variant"] = "state_match_strict"
    decision["decision_status"] = "fallback"
    decision["neighbors_json"] = json.dumps(
        [{"date": "2025-12-30", "best_expert_5d": "full_best", "similarity": 0.91}]
    )
    decision["fallback_policy"] = "full_run_best_guard"
    decision["fallback_source_run"] = "frozen_us"
    decision["fallback_source_model_id"] = "sm_bayesian"
    decision["fallback_expert_id"] = "full_best"
    decision["fallback_summary_sha256"] = "a" * 64
    decision["fallback_source_manifest_sha256"] = "b" * 64

    daily = execute_state_decisions(decision, _panel(), config=_config()).daily_audit
    marker = daily.loc[
        daily["variant"].eq("full_run_best_guard") & daily["decision_marker"]
    ].iloc[0]

    assert marker["threshold"] == "state_match_strict"
    assert marker["match_status"] == "unmatched"
    assert marker["neighbors_json"] == decision.iloc[0]["neighbors_json"]
    assert marker["fallback_source_run"] == "frozen_us"
    assert marker["fallback_source_manifest_sha256"] == "b" * 64

    variant_markers = daily.loc[daily["decision_marker"]].set_index("variant")
    assert variant_markers.loc["adaptive_guard", "fallback_policy"] == "adaptive_guard"
    assert variant_markers.loc["adaptive_guard", "fallback_expert_id"] == "adaptive_router"
    assert variant_markers.loc["cash_on_unmatched", "fallback_policy"] == "cash_on_unmatched"
    assert variant_markers.loc["cash_on_unmatched", "fallback_expert_id"] == "Cash"
    assert variant_markers.loc["full_run_best_only", "fallback_policy"] == "full_run_best_only"


def test_realized_five_day_regret_uses_each_execution_variant_expert() -> None:
    panel = _panel()
    cash = panel.loc[panel["expert_id"].eq("sm")].copy()
    cash["expert_id"] = "Cash"
    cash["strategy_return"] = 0.0
    cash["target_position"] = 0.0
    panel = pd.concat([panel, cash], ignore_index=True)
    utilities = {"sm": 0.4, "full_best": 0.3, "adaptive_router": 0.2, "Cash": 0.0}
    panel["future_utility"] = panel["expert_id"].map(utilities)
    panel["best_expert_5d"] = "sm"
    decision = _decisions().iloc[[2]].copy()
    decision["date"] = pd.Timestamp("2026-01-02")

    daily = execute_state_decisions(decision, panel, config=_config()).daily_audit
    markers = daily.loc[daily["decision_marker"]].set_index("variant")

    assert markers.loc["full_run_best_guard", "selected_realized_5d_utility"] == pytest.approx(0.3)
    assert markers.loc["adaptive_guard", "selected_realized_5d_utility"] == pytest.approx(0.2)
    assert markers.loc["cash_on_unmatched", "selected_realized_5d_utility"] == pytest.approx(0.0)
    assert markers["realized_best_5d_utility"].tolist() == pytest.approx([0.4] * 4)


def test_incomplete_five_day_tail_is_skipped() -> None:
    decision = _decisions().iloc[[0]].copy()
    decision["date"] = pd.bdate_range("2026-01-02", periods=13)[-3]

    with pytest.raises(TransformerStateExecutionError, match="no executable"):
        execute_state_decisions(decision, _panel(), config=_config())


def test_w16_full_run_best_unavailable_executes_cash_in_primary_and_control() -> None:
    decision = _decisions().iloc[[2]].copy()
    decision["date"] = pd.Timestamp("2026-01-02")
    decision["selected_expert_id"] = "cash"
    decision["full_run_best_available"] = False
    decision["full_run_best_execution_expert_id"] = "cash"
    decision["full_run_best_fallback_reason"] = "full_run_best_unavailable_cash"
    decision["full_run_best_expert_unavailable_reason"] = "full_run_best_unavailable:full_best"

    daily = execute_state_decisions(decision, _panel(), config=_config()).daily_audit
    markers = daily.loc[daily["decision_marker"]].set_index("variant")

    for variant in ("full_run_best_guard", "full_run_best_only"):
        assert markers.loc[variant, "selected_expert_id"] == "cash"
        assert markers.loc[variant, "attribution_source"] == "cash"
        assert markers.loc[variant, "fallback_expert_id"] == "cash"
        assert markers.loc[variant, "fallback_reason"] == "full_run_best_unavailable_cash"
        assert markers.loc[variant, "expert_unavailable_reason"] == "full_run_best_unavailable:full_best"
    controlled = daily.loc[daily["variant"].isin(["full_run_best_guard", "full_run_best_only"])]
    assert controlled["strategy_return"].eq(0.0).all()
    assert controlled["target_position"].eq(0.0).all()
    controlled_summary = reconstruct_execution_summary(controlled)
    assert controlled_summary["fallback_cash_coverage"].eq(1.0).all()
    assert controlled_summary["fallback_full_run_best_coverage"].eq(0.0).all()
    assert controlled_summary["full_run_best_guard_return_contribution"].eq(0.0).all()
    assert controlled_summary["cash_return_contribution"].eq(0.0).all()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_execution_config_rejects_nonfinite_jump_guard_values(value: float) -> None:
    config = _config()
    config["selected_jump_guard"] = {
        **config["selected_jump_guard"],
        "single_day_jump_down_atr_multiple": value,
    }

    with pytest.raises(TransformerStateExecutionError, match="must be finite"):
        execute_state_decisions(_decisions().iloc[[0]], _panel(), config=config)


def test_summary_drawdown_includes_initial_equity_and_overflow_fails_closed() -> None:
    panel = _panel()
    sm_rows = panel["expert_id"].eq("sm")
    panel.loc[sm_rows, "strategy_return"] = 0.0
    first_effective = pd.bdate_range("2026-01-02", periods=13)[1]
    panel.loc[sm_rows & panel["date"].eq(first_effective), "strategy_return"] = -0.1
    result = execute_state_decisions(_decisions().iloc[[0]], panel, config=_config())
    primary = result.summary.loc[result.summary["variant"].eq("full_run_best_guard")].iloc[0]
    assert primary["max_drawdown"] == pytest.approx(-0.1)

    panel.loc[sm_rows, "strategy_return"] = 1e308
    with pytest.raises(TransformerStateExecutionError, match="must be finite"):
        execute_state_decisions(_decisions().iloc[[0]], panel, config=_config())
