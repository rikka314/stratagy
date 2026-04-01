from __future__ import annotations

import logging
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import STRATEGY_PRESETS
from core.data import load_csv
from ui import single_stock as single_stock_ui
from ui.single_stock_workflow import (
    StrategyRequest,
    build_strategy_context_key,
    commit_current_artifact,
    ensure_strategy_workspace,
    freeze_params_snapshot,
    get_strategy_workspace,
    run_strategy_pipeline,
)


logging.disable(logging.CRITICAL)

FIXTURE_PATH = "data/aapl_clean_daily.csv"
FIXTURE_ROWS = 800
TRAIN_RATIO = 0.70
SEARCH_TRIALS = 3
MARKET = "US"
SYMBOL = "AAPL"
ADJUST = "qfq"


@dataclass
class CheckResult:
    check_id: str
    section: str
    passed: bool
    summary: str
    elapsed_seconds: float
    details: str | None = None


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r}, actual={actual!r}")


def first_preset() -> tuple[str, dict]:
    return next((name, cfg) for name, cfg in STRATEGY_PRESETS.items() if "entry_threshold" in cfg)


def build_test_params() -> dict:
    preset_name, preset = first_preset()
    return {
        "strategy_preset": preset_name,
        "market": MARKET,
        "adjust": ADJUST,
        "uploaded_file": None,
        **dict(preset),
        "use_trend_filter": True,
        "use_strength_filter": True,
        "use_rsi_filter": True,
        "use_macd_filter": True,
        "use_voting_entry": False,
        "entry_vote_threshold": 2.5,
    }


def load_fixture_df():
    return load_csv(FIXTURE_PATH).tail(FIXTURE_ROWS).reset_index(drop=True)


def build_runtime_context():
    df = load_fixture_df()
    params_snapshot = freeze_params_snapshot(build_test_params())
    split_idx = min(max(1, int(len(df) * TRAIN_RATIO)), len(df) - 1)
    context_key = build_strategy_context_key(
        market=MARKET,
        symbol=SYMBOL,
        adjust=ADJUST,
        df_raw=df,
        train_ratio=TRAIN_RATIO,
        uploaded_file=None,
    )
    return df, params_snapshot, split_idx, context_key


def reset_runtime_state() -> None:
    st.session_state.clear()


def run_direct_request(
    request: StrategyRequest,
    *,
    clear_state: bool = True,
    commit_artifact: bool = True,
):
    if clear_state:
        reset_runtime_state()
    df, params_snapshot, split_idx, context_key = build_runtime_context()
    ensure_strategy_workspace(context_key)
    result = run_strategy_pipeline(
        context_key=context_key,
        request=request,
        request_params_snapshot=params_snapshot,
        df_raw=df,
        split_idx=split_idx,
    )
    if commit_artifact and result.artifact is not None:
        commit_current_artifact(result.artifact)
        single_stock_ui._set_downstream_display_state(result.artifact)
    return result, df, params_snapshot, split_idx, context_key


def assert_downstream_defaults(artifact_id: str) -> None:
    expect_equal(
        st.session_state[single_stock_ui.SELECTED_ARTIFACT_IDS_KEY],
        [artifact_id],
        "selected_artifact_ids should reset to current artifact",
    )
    expect_equal(
        st.session_state[single_stock_ui.FOCUS_ARTIFACT_ID_KEY],
        artifact_id,
        "focus_artifact_id should reset to current artifact",
    )
    expect_equal(
        st.session_state[single_stock_ui.SIGNAL_DATASET_SPLIT_KEY],
        "test",
        "signal_dataset_split should reset to test",
    )


def success_case(case_id: str, request: StrategyRequest, expected_stage_keys: list[str]) -> str:
    result, _df, _params_snapshot, _split_idx, _context_key = run_direct_request(request)
    expect_equal(result.status, "success", f"{case_id} should succeed")
    expect(result.artifact is not None, f"{case_id} should return an artifact")
    expect_equal(result.info_messages, [], f"{case_id} first run should not hit cache")
    artifact = result.artifact
    workspace = get_strategy_workspace()
    expect_equal(workspace["current_artifact"].id, artifact.id, f"{case_id} should commit current artifact")
    assert_downstream_defaults(artifact.id)

    actual_stage_keys = [stage.stage_key for stage in artifact.pipeline_lineage]
    actual_lineage = [stage.display_label for stage in artifact.pipeline_lineage]
    expect_equal(actual_stage_keys, expected_stage_keys, f"{case_id} lineage mismatch")
    expect("best_params" not in st.session_state, f"{case_id} should not write best_params")
    expect("apply_best_params" not in st.session_state, f"{case_id} should not write apply_best_params")

    final_stage = artifact.pipeline_lineage[-1]
    if request.use_ml:
        expect(artifact.ml_quality is not None, f"{case_id} should expose ml_quality")
        expect_equal(
            final_stage.upstream_stage_key,
            expected_stage_keys[-2],
            f"{case_id} ML stage should consume the latest successful upstream stage",
        )
    else:
        expect(artifact.ml_quality is None, f"{case_id} should not expose ml_quality")

    if request.use_search:
        search_stage = artifact.pipeline_lineage[1]
        expect_equal(search_stage.upstream_stage_key, expected_stage_keys[0], f"{case_id} search upstream mismatch")

    if request.search_base == "fsm":
        expect("fa" not in actual_stage_keys, f"{case_id} should not render FA as a standalone stage")

    return f"{artifact.display_label} | {' -> '.join(actual_lineage)} | artifact={artifact.id}"


def edge_invalid_request() -> str:
    ok_request = StrategyRequest(family="search", search_base="sm")
    ok_result, *_ = run_direct_request(ok_request)
    expect(ok_result.artifact is not None, "prime artifact should exist")
    previous_id = ok_result.artifact.id

    bad_request = StrategyRequest(
        family="baseline",
        baseline_kind="naive",
        use_search=True,
        search_method="bayesian",
    )
    bad_result, _df, _params_snapshot, _split_idx, _context_key = run_direct_request(
        bad_request,
        clear_state=False,
        commit_artifact=False,
    )
    expect_equal(bad_result.status, "failed", "E1 should fail validation")
    expect(bad_result.artifact is None, "E1 should not return an artifact")
    workspace = get_strategy_workspace()
    expect_equal(workspace["current_artifact"].id, previous_id, "E1 should preserve previous current_artifact")
    return bad_result.error_message or "validation failed"


def edge_fa_failure() -> str:
    ok_request = StrategyRequest(family="search", search_base="sm")
    ok_result, *_ = run_direct_request(ok_request)
    expect(ok_result.artifact is not None, "prime artifact should exist")
    previous_id = ok_result.artifact.id

    failing_request = StrategyRequest(family="search", search_base="fsm")
    with patch("ui.single_stock_workflow.fit_fa", side_effect=RuntimeError("forced FA failure")):
        failing_result, *_ = run_direct_request(failing_request, clear_state=False, commit_artifact=False)

    expect_equal(failing_result.status, "failed", "E2 should fail")
    expect(failing_result.artifact is None, "E2 should not return an artifact")
    workspace = get_strategy_workspace()
    expect_equal(workspace["current_artifact"].id, previous_id, "E2 should preserve previous current_artifact")
    expect("forced FA failure" in (failing_result.error_message or ""), "E2 should expose FA failure reason")
    return failing_result.error_message or "forced FA failure"


def edge_search_failure() -> str:
    request = StrategyRequest(
        family="search",
        search_base="sm",
        use_search=True,
        search_method="bayesian",
        search_trials=SEARCH_TRIALS,
    )
    with patch("ui.single_stock_workflow._run_parameter_search", side_effect=RuntimeError("forced search failure")):
        result, *_ = run_direct_request(request)

    expect_equal(result.status, "degraded", "E3 should degrade to base stage")
    expect(result.artifact is not None, "E3 should still return a degraded artifact")
    stage_keys = [stage.stage_key for stage in result.artifact.pipeline_lineage]
    expect_equal(stage_keys, ["sm_base"], "E3 should fall back to the base SM stage")
    expect(result.warnings and "参数搜索失败" in result.warnings[0], "E3 should surface a warning")
    return result.warnings[0]


def edge_ml_failure() -> str:
    request = StrategyRequest(
        family="search",
        search_base="sm",
        use_search=True,
        search_method="bayesian",
        use_ml=True,
        ml_model_type="logistic",
        search_trials=SEARCH_TRIALS,
    )
    with patch("ui.single_stock_workflow.fit_ml_filter", side_effect=RuntimeError("forced ML failure")):
        result, *_ = run_direct_request(request)

    expect_equal(result.status, "degraded", "E4 should degrade to the latest successful upstream stage")
    expect(result.artifact is not None, "E4 should still return a degraded artifact")
    stage_keys = [stage.stage_key for stage in result.artifact.pipeline_lineage]
    expect_equal(stage_keys, ["sm_base", "search"], "E4 should fall back to the search stage")
    expect_equal(result.artifact.display_label, "SM+Search", "E4 should preserve the search artifact")
    expect(result.warnings and "ML 失败" in result.warnings[0], "E4 should surface a warning")
    return result.warnings[0]


def build_harness_script() -> str:
    return f"""
from core.config import STRATEGY_PRESETS
from core.data import load_csv
from ui.single_stock import render_single_stock_page

preset_name, preset = next((name, cfg) for name, cfg in STRATEGY_PRESETS.items() if "entry_threshold" in cfg)
params = {{
    "strategy_preset": preset_name,
    "market": "{MARKET}",
    "adjust": "{ADJUST}",
    "uploaded_file": None,
    **dict(preset),
    "use_trend_filter": True,
    "use_strength_filter": True,
    "use_rsi_filter": True,
    "use_macd_filter": True,
    "use_voting_entry": False,
    "entry_vote_threshold": 2.5,
}}
df = load_csv("{FIXTURE_PATH}").tail({FIXTURE_ROWS}).reset_index(drop=True)
render_single_stock_page(params, df, "{SYMBOL}")
"""


def new_app() -> AppTest:
    at = AppTest.from_string(build_harness_script(), default_timeout=90)
    at.run()
    return at


def workspace_from_app(at: AppTest):
    return at.session_state["single_stock_strategy_workspace"]


def app_generate_baseline(at: AppTest) -> str:
    at.selectbox(key="single_stock_workflow_family").set_value("baseline").run()
    at.selectbox(key="single_stock_workflow_baseline_kind").set_value("naive").run()
    at.button(key="single_stock_generate_strategy").click().run(timeout=90)
    return workspace_from_app(at)["current_artifact"].id


def app_generate_sm(at: AppTest) -> str:
    at.selectbox(key="single_stock_workflow_family").set_value("search").run()
    at.selectbox(key="single_stock_workflow_search_base").set_value("sm").run()
    at.button(key="single_stock_generate_strategy").click().run(timeout=90)
    return workspace_from_app(at)["current_artifact"].id


def assert_app_defaults(at: AppTest, artifact_id: str) -> None:
    expect_equal(
        at.session_state[single_stock_ui.SELECTED_ARTIFACT_IDS_KEY],
        [artifact_id],
        "app selected_artifact_ids should reset to current artifact",
    )
    expect_equal(
        at.session_state[single_stock_ui.FOCUS_ARTIFACT_ID_KEY],
        artifact_id,
        "app focus_artifact_id should reset to current artifact",
    )
    expect_equal(
        at.session_state[single_stock_ui.SIGNAL_DATASET_SPLIT_KEY],
        "test",
        "app signal_dataset_split should reset to test",
    )


def edge_save_idempotent() -> str:
    at = new_app()
    artifact_id = app_generate_baseline(at)
    at.button(key="single_stock_save_current_artifact").click().run()
    first_saved_len = len(workspace_from_app(at)["saved_artifacts"])
    at.button(key="single_stock_save_current_artifact").click().run()
    second_saved_len = len(workspace_from_app(at)["saved_artifacts"])
    expect_equal(first_saved_len, 1, "E5 first save should add one snapshot")
    expect_equal(second_saved_len, 1, "E5 repeated save should be idempotent")
    assert_app_defaults(at, artifact_id)
    return f"saved_artifacts stays at {second_saved_len}"


def edge_context_reset() -> str:
    at = new_app()
    app_generate_baseline(at)
    at.button(key="single_stock_save_current_artifact").click().run()
    at.slider[0].set_value(0.75).run()

    workspace = workspace_from_app(at)
    expect(workspace["current_artifact"] is None, "E6 should clear current_artifact")
    expect_equal(len(workspace["saved_artifacts"]), 0, "E6 should clear saved_artifacts")
    expect_equal(
        at.selectbox(key="single_stock_workflow_family").value,
        "",
        "E6 should clear workflow request draft",
    )
    expect_equal(
        at.session_state[single_stock_ui.SELECTED_ARTIFACT_IDS_KEY],
        [],
        "E6 should clear downstream selected_artifact_ids",
    )
    expect(at.session_state[single_stock_ui.FOCUS_ARTIFACT_ID_KEY] is None, "E6 should clear focus_artifact_id")
    expect_equal(
        at.session_state[single_stock_ui.SIGNAL_DATASET_SPLIT_KEY],
        "test",
        "E6 should reset signal_dataset_split to test",
    )
    return "context reset clears workspace, draft, and downstream state"


def edge_same_session_rerun() -> str:
    at = new_app()
    artifact_id = app_generate_baseline(at)
    at.button(key="single_stock_save_current_artifact").click().run()
    at.run()

    workspace = workspace_from_app(at)
    expect_equal(workspace["current_artifact"].id, artifact_id, "E7 should preserve current_artifact on rerun")
    expect_equal(len(workspace["saved_artifacts"]), 1, "E7 should preserve saved_artifacts on rerun")
    assert_app_defaults(at, artifact_id)
    return "workspace survives same-session rerun"


def edge_refresh_new_session() -> str:
    at = new_app()
    app_generate_baseline(at)
    at.button(key="single_stock_save_current_artifact").click().run()

    fresh = new_app()
    workspace = workspace_from_app(fresh)
    expect(workspace["current_artifact"] is None, "E8 fresh session should not restore current_artifact")
    expect_equal(len(workspace["saved_artifacts"]), 0, "E8 fresh session should not restore saved_artifacts")
    expect_equal(
        fresh.selectbox(key="single_stock_workflow_family").value,
        "",
        "E8 fresh session should start at EMPTY",
    )
    return "fresh AppTest session starts empty"


def ui_replacement_defaults() -> str:
    at = new_app()
    first_id = app_generate_baseline(at)
    second_id = app_generate_sm(at)
    expect(first_id != second_id, "same-session generate should replace current_artifact")
    expect_equal(
        workspace_from_app(at)["current_artifact"].id,
        second_id,
        "newly generated artifact should become current_artifact",
    )
    assert_app_defaults(at, second_id)
    return f"current_artifact replaces {first_id} -> {second_id}"


def cache_hit_behavior() -> str:
    reset_runtime_state()
    df, params_snapshot, split_idx, context_key = build_runtime_context()

    request_sm = StrategyRequest(family="search", search_base="sm")
    request_sm_search_ml = StrategyRequest(
        family="search",
        search_base="sm",
        use_search=True,
        search_method="bayesian",
        use_ml=True,
        ml_model_type="logistic",
        search_trials=SEARCH_TRIALS,
    )

    ensure_strategy_workspace(context_key)
    first = run_strategy_pipeline(
        context_key=context_key,
        request=request_sm,
        request_params_snapshot=params_snapshot,
        df_raw=df,
        split_idx=split_idx,
    )
    second = run_strategy_pipeline(
        context_key=context_key,
        request=request_sm_search_ml,
        request_params_snapshot=params_snapshot,
        df_raw=df,
        split_idx=split_idx,
    )
    third = run_strategy_pipeline(
        context_key=context_key,
        request=request_sm_search_ml,
        request_params_snapshot=params_snapshot,
        df_raw=df,
        split_idx=split_idx,
    )

    expect_equal(first.info_messages, [], "cache baseline should miss on first request")
    expect_equal(second.info_messages, ["SM基础 命中缓存。"], "cache should reuse SM base for downstream requests")
    expect_equal(
        third.info_messages,
        ["SM基础 命中缓存。", "参数搜索阶段命中缓存。", "ML 阶段命中缓存。"],
        "cache should hit all stages on identical repeated request",
    )
    return "SM base survives downstream flags; repeated full request hits base/search/ML cache"


def run_check(section: str, check_id: str, fn: Callable[[], str]) -> CheckResult:
    start = time.perf_counter()
    try:
        summary = fn()
        return CheckResult(
            check_id=check_id,
            section=section,
            passed=True,
            summary=summary,
            elapsed_seconds=time.perf_counter() - start,
        )
    except Exception as exc:  # pragma: no cover - validation failure path
        return CheckResult(
            check_id=check_id,
            section=section,
            passed=False,
            summary=f"{exc.__class__.__name__}: {exc}",
            elapsed_seconds=time.perf_counter() - start,
            details=traceback.format_exc(),
        )


def print_report(results: list[CheckResult]) -> None:
    print("# W5 Workflow Validation")
    print()
    print(f"- Timestamp: {datetime.now().isoformat(timespec='seconds')}")
    print(f"- Fixture: `{FIXTURE_PATH}` tail `{FIXTURE_ROWS}` rows")
    print(f"- Train ratio: `{TRAIN_RATIO:.2f}`")
    print(f"- Search trials: `{SEARCH_TRIALS}`")
    print()

    sections = [
        ("path", "C Matrix"),
        ("edge", "E Matrix"),
        ("behavior", "Behavior"),
    ]
    for section_key, title in sections:
        section_results = [result for result in results if result.section == section_key]
        if not section_results:
            continue
        print(f"## {title}")
        print()
        print("| Check | Status | Elapsed(s) | Summary |")
        print("|---|---|---:|---|")
        for result in section_results:
            status = "PASS" if result.passed else "FAIL"
            elapsed = f"{result.elapsed_seconds:.2f}"
            summary = result.summary.replace("\n", " ").replace("|", "\\|")
            print(f"| {result.check_id} | {status} | {elapsed} | {summary} |")
        print()

    failures = [result for result in results if not result.passed]
    print("## Summary")
    print()
    print(f"- Passed: {len(results) - len(failures)}/{len(results)}")
    print(f"- Failed: {len(failures)}")
    if failures:
        print()
        print("## Failure Details")
        print()
        for result in failures:
            print(f"### {result.check_id}")
            print()
            print("```text")
            print((result.details or result.summary).rstrip())
            print("```")
            print()


def main() -> int:
    checks: list[CheckResult] = []

    checks.extend(
        [
            run_check("path", "C1", lambda: success_case("C1", StrategyRequest(family="baseline", baseline_kind="naive"), ["baseline"])),
            run_check("path", "C2", lambda: success_case("C2", StrategyRequest(family="search", search_base="sm"), ["sm_base"])),
            run_check(
                "path",
                "C3",
                lambda: success_case(
                    "C3",
                    StrategyRequest(
                        family="search",
                        search_base="sm",
                        use_search=True,
                        search_method="bayesian",
                        search_trials=SEARCH_TRIALS,
                    ),
                    ["sm_base", "search"],
                ),
            ),
            run_check(
                "path",
                "C4",
                lambda: success_case(
                    "C4",
                    StrategyRequest(
                        family="search",
                        search_base="sm",
                        use_ml=True,
                        ml_model_type="logistic",
                    ),
                    ["sm_base", "ml"],
                ),
            ),
            run_check(
                "path",
                "C5",
                lambda: success_case(
                    "C5",
                    StrategyRequest(
                        family="search",
                        search_base="sm",
                        use_search=True,
                        search_method="bayesian",
                        use_ml=True,
                        ml_model_type="logistic",
                        search_trials=SEARCH_TRIALS,
                    ),
                    ["sm_base", "search", "ml"],
                ),
            ),
            run_check("path", "C6", lambda: success_case("C6", StrategyRequest(family="search", search_base="fsm"), ["fsm_base"])),
            run_check(
                "path",
                "C7",
                lambda: success_case(
                    "C7",
                    StrategyRequest(
                        family="search",
                        search_base="fsm",
                        use_search=True,
                        search_method="bayesian",
                        search_trials=SEARCH_TRIALS,
                    ),
                    ["fsm_base", "search"],
                ),
            ),
            run_check(
                "path",
                "C8",
                lambda: success_case(
                    "C8",
                    StrategyRequest(
                        family="search",
                        search_base="fsm",
                        use_ml=True,
                        ml_model_type="logistic",
                    ),
                    ["fsm_base", "ml"],
                ),
            ),
            run_check(
                "path",
                "C9",
                lambda: success_case(
                    "C9",
                    StrategyRequest(
                        family="search",
                        search_base="fsm",
                        use_search=True,
                        search_method="bayesian",
                        use_ml=True,
                        ml_model_type="logistic",
                        search_trials=SEARCH_TRIALS,
                    ),
                    ["fsm_base", "search", "ml"],
                ),
            ),
        ]
    )

    checks.extend(
        [
            run_check("edge", "E1", edge_invalid_request),
            run_check("edge", "E2", edge_fa_failure),
            run_check("edge", "E3", edge_search_failure),
            run_check("edge", "E4", edge_ml_failure),
            run_check("edge", "E5", edge_save_idempotent),
            run_check("edge", "E6", edge_context_reset),
            run_check("edge", "E7", edge_same_session_rerun),
            run_check("edge", "E8", edge_refresh_new_session),
        ]
    )

    checks.extend(
        [
            run_check("behavior", "B1", ui_replacement_defaults),
            run_check("behavior", "B2", cache_hit_behavior),
        ]
    )

    print_report(checks)
    return 0 if all(result.passed for result in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
