"""
模型评估页
==========
只读浏览 `model-test/outputs` 里的已有研究产物。
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from core.visualization import create_news_ablation_chart
from ui.export_reports import build_model_evaluation_export_html
from ui.i18n import tr

from ui.theme import get_ui_language, render_html, render_route_nav, render_status_note, t


MODEL_EVALUATION_ROUTE = "model-evaluation"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUTS_ROOT = REPO_ROOT / "model-test" / "outputs"
TEXT_NA = "N/A"
RESEARCH_MARKETS = ("US", "CN_A")
RESEARCH_ARTIFACT_NAMES = {
    "recommendations": "market_strategy_recommendations.json",
    "matrix": "market_strategy_matrix.csv",
    "news_ablation": "news_ablation_summary.csv",
    "manifest": "data_manifest.json",
}
CONFIDENCE_VALUES = {"high", "medium", "low", "insufficient_evidence"}


@dataclass(frozen=True)
class ModelEvaluationRun:
    run_id: str
    run_dir: Path
    report_path: Path
    modified_ts: float


def discover_model_evaluation_runs(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> list[ModelEvaluationRun]:
    """run.scan.description"""
    try:
        entries = list(outputs_root.iterdir())
    except OSError:
        return []

    runs: list[ModelEvaluationRun] = []
    for entry in entries:
        try:
            if entry.name.startswith("_") or not entry.is_dir():
                continue
            report_path = entry / "report.json"
            if not report_path.is_file():
                continue
            try:
                modified_ts = report_path.stat().st_mtime
            except OSError:
                modified_ts = entry.stat().st_mtime
        except OSError:
            continue
        runs.append(
            ModelEvaluationRun(
                run_id=entry.name,
                run_dir=entry,
                report_path=report_path,
                modified_ts=modified_ts,
            )
        )
    return sorted(runs, key=lambda item: (item.modified_ts, item.run_id), reverse=True)


def load_model_evaluation_payload(run: ModelEvaluationRun) -> dict[str, Any]:
    """action.loadRunReport"""
    report_payload = _load_json_mapping(run.report_path)
    if report_payload is None:
        raise ValueError(f"无法读取报告文件：{run.report_path}")

    mlflow_path = run.run_dir / "mlflow_run.json"
    try:
        mlflow_payload = _load_json_mapping(mlflow_path) if mlflow_path.is_file() else None
    except OSError:
        mlflow_payload = None
    research_payload = load_market_research_payload(run)
    return normalize_model_evaluation_payload(run, report_payload, mlflow_payload, research_payload)


def load_market_research_payload(run: ModelEvaluationRun) -> dict[str, Any]:
    """Load optional Dean's Award research artifacts without breaking legacy runs."""
    issues: list[str] = []
    source_paths: dict[str, str] = {}

    recommendations: dict[str, Any] = {}
    recommendations_path = run.run_dir / RESEARCH_ARTIFACT_NAMES["recommendations"]
    if _path_is_file(recommendations_path):
        source_paths["recommendations"] = str(recommendations_path)
        loaded = _load_json_mapping(recommendations_path)
        if loaded is None:
            issues.append(f"Unreadable or invalid {recommendations_path.name}")
        else:
            recommendations = loaded

    matrix_records = _load_optional_csv_records(
        run.run_dir / RESEARCH_ARTIFACT_NAMES["matrix"],
        artifact_key="matrix",
        source_paths=source_paths,
        issues=issues,
    )
    news_records = _load_optional_csv_records(
        run.run_dir / RESEARCH_ARTIFACT_NAMES["news_ablation"],
        artifact_key="news_ablation",
        source_paths=source_paths,
        issues=issues,
    )

    manifest: dict[str, Any] = {}
    manifest_path = run.run_dir / RESEARCH_ARTIFACT_NAMES["manifest"]
    if _path_is_file(manifest_path):
        source_paths["manifest"] = str(manifest_path)
        loaded = _load_json_mapping(manifest_path)
        if loaded is None:
            issues.append(f"Unreadable or invalid {manifest_path.name}")
        else:
            manifest = loaded

    return normalize_market_research_payload(
        recommendations=recommendations,
        matrix_records=matrix_records,
        news_records=news_records,
        manifest=manifest,
        source_paths=source_paths,
        issues=issues,
    )


def normalize_market_research_payload(
    *,
    recommendations: dict[str, Any] | None = None,
    matrix_records: list[dict[str, Any]] | None = None,
    news_records: list[dict[str, Any]] | None = None,
    manifest: dict[str, Any] | None = None,
    source_paths: dict[str, str] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """Adapt frozen Gate-0 artifacts into a UI-safe, traceable payload."""
    recommendations = _ensure_mapping(recommendations)
    manifest = _ensure_mapping(manifest)
    source_paths = dict(source_paths or {})
    normalized_issues = [str(item) for item in (issues or []) if str(item).strip()]

    matrix = _normalize_market_records(matrix_records, artifact_label="strategy matrix", issues=normalized_issues)
    news_ablation = _normalize_market_records(news_records, artifact_label="news ablation", issues=normalized_issues)
    raw_markets = _ensure_mapping(recommendations.get("markets"))
    market_payloads: dict[str, dict[str, Any]] = {}

    for market in RESEARCH_MARKETS:
        if raw_markets and market not in raw_markets:
            normalized_issues.append(f"Recommendation payload is missing required market '{market}'")
        raw_entry = _ensure_mapping(raw_markets.get(market))
        recommendation = _optional_text(raw_entry.get("recommendation"))
        confidence = str(raw_entry.get("confidence") or "insufficient_evidence").strip().lower()
        if confidence not in CONFIDENCE_VALUES:
            normalized_issues.append(f"{market} recommendation has unknown confidence '{confidence}'")
            confidence = "insufficient_evidence"

        limitations = _normalize_text_list(raw_entry.get("limitations"))
        evidence = _ensure_mapping(raw_entry.get("evidence"))
        market_rows = [row for row in matrix if row.get("market") == market]
        trace_rows = (
            [
                row
                for row in market_rows
                if str(row.get("strategy_id") or "").strip() == recommendation
            ]
            if recommendation is not None
            else market_rows
        )
        market_payloads[market] = {
            "market": market,
            "recommendation": recommendation,
            "confidence": confidence,
            "evidence": evidence,
            "limitations": limitations,
            "trace_rows": trace_rows,
        }

    has_recommendations = bool(raw_markets)
    present_markets = {str(row.get("market") or "") for row in matrix}
    recommendations_traceable = all(
        market in raw_markets
        and bool(market_payloads[market]["trace_rows"])
        for market in RESEARCH_MARKETS
    )
    return {
        "schema_version": _display_text(recommendations.get("schema_version"), empty=TEXT_NA, na=TEXT_NA),
        "generated_at": recommendations.get("generated_at"),
        "markets": market_payloads,
        "matrix": matrix,
        "news_ablation": news_ablation,
        "manifest": manifest,
        "source_paths": source_paths,
        "issues": list(dict.fromkeys(normalized_issues)),
        "has_recommendations": has_recommendations,
        "has_matrix": bool(matrix),
        "has_news_ablation": bool(news_ablation),
        "cross_market_ready": (
            has_recommendations
            and set(RESEARCH_MARKETS).issubset(present_markets)
            and recommendations_traceable
        ),
        "available": bool(has_recommendations or matrix or news_ablation),
    }


def normalize_model_evaluation_payload(
    run: ModelEvaluationRun,
    report_payload: dict[str, Any],
    mlflow_payload: dict[str, Any] | None = None,
    research_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """task.normalizeReportJson"""
    config = _ensure_mapping(report_payload.get("config"))
    pool = _ensure_mapping(report_payload.get("pool"))
    score_policy = _ensure_mapping(report_payload.get("score_policy"))
    search_budget = _ensure_mapping(report_payload.get("search_budget"))
    top_models = _ensure_records(report_payload.get("top_models"))
    model_summary = _ensure_records(report_payload.get("model_summary"))
    family_summary = _ensure_records(report_payload.get("family_summary"))
    search_method_summary = _ensure_records(report_payload.get("search_method_summary"))
    robustness_summary = _ensure_records(report_payload.get("robustness_summary"))
    failures = _ensure_records(report_payload.get("failures"))
    ml_gain = _ensure_records(report_payload.get("ml_gain"))
    segment_highlights = _ensure_records(report_payload.get("segment_highlights"))
    adaptive_router = _ensure_mapping(report_payload.get("adaptive_router"))
    quantstats = [
        {
            **row,
            "resolved_quantstats_html_path": str(resolved_path) if resolved_path is not None else None,
        }
        for row in _ensure_records(report_payload.get("quantstats"))
        for resolved_path in [_resolve_run_path(run, row.get("quantstats_html_path"))]
    ]

    model_count = len(model_summary) or len(top_models)
    robustness_enabled = bool(config.get("run_robustness")) or bool(robustness_summary)
    robustness_weight = _coerce_float(score_policy.get("robustness_weight"))
    if robustness_weight is None:
        robustness_weight = _coerce_float(config.get("robustness_weight"))

    if robustness_enabled and robustness_weight is not None and 0 < robustness_weight < 1:
        score_policy_text = f"{1 - robustness_weight:.0%} 主窗口 + {robustness_weight:.0%} 稳健性"
    elif robustness_enabled:
        score_policy_text = tr("scoring.mainAndRobustness")
    else:
        score_policy_text = tr("scoring.main_window_only")

    quantstats_enabled = bool(config.get("enable_quantstats")) or bool(quantstats)
    quantstats_label = tr("status.notGenerated")
    if quantstats:
        quantstats_label = tr("modelEvaluation.quantstatsCount", count=len(quantstats))
    elif quantstats_enabled:
        quantstats_label = tr("status.enabled_not_generated")

    normalized = {
        "run_id": run.run_id,
        "run_dir": str(run.run_dir),
        "report_path": str(run.report_path),
        "generated_at": report_payload.get("generated_at"),
        "generated_label": _format_datetime_text(report_payload.get("generated_at")),
        "last_modified_label": _format_timestamp_label(run.modified_ts),
        "config": config,
        "pool": pool,
        "score_policy": score_policy,
        "search_budget": search_budget,
        "stage_winners": _ensure_mapping(report_payload.get("stage_winners")),
        "top_models": top_models,
        "top_model": top_models[0] if top_models else {},
        "model_summary": model_summary,
        "family_summary": family_summary,
        "search_method_summary": search_method_summary,
        "robustness_summary": robustness_summary,
        "ml_gain": ml_gain,
        "segment_highlights": segment_highlights,
        "adaptive_router": adaptive_router,
        "quantstats": quantstats,
        "failures": failures,
        "mlflow": mlflow_payload or {},
        "mlflow_recorded": bool(mlflow_payload),
        "research": research_payload or normalize_market_research_payload(),
        "config_name_label": _display_text(config.get("name")),
        "market_label": _display_text(config.get("market"), empty=TEXT_NA, na=TEXT_NA),
        "stock_count_label": _format_count_label(pool.get("stock_count")),
        "model_count_label": _format_count_label(model_count),
        "pool_size_label": _format_count_label(pool.get("stock_count")),
        "score_policy_text": score_policy_text,
        "feature_labels": {
            "robustness": tr("status.enabled") if robustness_enabled else tr("state.disabled"),
            "quantstats": quantstats_label,
            "mlflow": tr("mlflow.recorded") if mlflow_payload else tr("mlflow.notRecorded"),
        },
        "is_us_research_baseline": (
            str(config.get("name") or run.run_id) == "full_us_deans_60"
            and str(config.get("market") or "").upper() == "US"
            and len(model_summary) == 19
            and bool(robustness_summary)
        ),
    }
    return normalized


def render_model_evaluation_page(*, outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> None:
    """route.rendering"""
    render_route_nav(MODEL_EVALUATION_ROUTE)

    runs = discover_model_evaluation_runs(outputs_root)
    latest_run_label = runs[0].run_id if runs else _empty_text()
    latest_time_label = _format_timestamp_label(runs[0].modified_ts) if runs else _empty_text()

    render_html(
        f"""
<section class="analysis-page-shell">
  <div class="analysis-hero">
    <div class="analysis-hero-topline">
      <span class="analysis-pill accent">{_page_text("modelEvaluation.heroPill", "Evidence-first research", zh_fallback="证据优先的研究")}</span>
      <span class="analysis-pill">{_page_text("modelEvaluation.readableRuns", "{count} readable runs", zh_fallback="{count} 个可读运行", count=len(runs))}</span>
      <span class="analysis-pill">{html.escape(str(outputs_root.name))}</span>
    </div>
    <div class="analysis-hero-main">
      <div>
        <h1 class="analysis-title">{tr("modelEvaluation.title")}</h1>
        <p class="analysis-subtitle">{tr("modelEvaluation.copy")}</p>
      </div>
      <div class="analysis-quick-grid">
        <div class="analysis-quick-item">
          <span class="analysis-quick-label">{_page_text("modelEvaluation.publicPath", "Public path", zh_fallback="公开路径")}</span>
          <span class="analysis-quick-value">/strategy/model-evaluation</span>
          <span class="analysis-quick-meta">{_page_text("modelEvaluation.publicPathMeta", "Read-only research browser", zh_fallback="只读研究浏览器")}</span>
        </div>
        <div class="analysis-quick-item">
          <span class="analysis-quick-label">{_page_text("modelEvaluation.latestRun", "Latest run", zh_fallback="最新运行")}</span>
          <span class="analysis-quick-value">{html.escape(latest_run_label)}</span>
          <span class="analysis-quick-meta">{html.escape(latest_time_label)}</span>
        </div>
        <div class="analysis-quick-item">
          <span class="analysis-quick-label">{_page_text("modelEvaluation.dataSource", "Data source", zh_fallback="数据来源")}</span>
          <span class="analysis-quick-value">model-test/outputs</span>
          <span class="analysis-quick-meta">{tr("modelEvaluation.dataSourceMeta")}</span>
        </div>
      </div>
    </div>
  </div>
</section>
        """
    )

    selected_payload: dict[str, Any] | None = None
    load_error: str | None = None

    control_col, summary_col = st.columns([0.94, 1.06], gap="large")

    with control_col:
        with st.container(key="model-evaluation-control-card"):
            st.markdown(f"<div class='surface-kicker'>{html.escape(_page_text('modelEvaluation.runBrowserKicker', 'Run browser', zh_fallback='运行浏览器'))}</div>", unsafe_allow_html=True)
            st.markdown(tr("section.browseExistingRuns"), unsafe_allow_html=True)
            st.markdown(
                tr("page.description.consumesReportOnly"),
                unsafe_allow_html=True,
            )

            if not runs:
                render_status_note(tr("research.run.empty"), tone="warning")
                st.caption(t(f"扫描目录：{outputs_root}", f"Scanned directory: {outputs_root}"))
            else:
                selected_run_id = st.selectbox(
                    tr("action.selectRun"),
                    options=[run.run_id for run in runs],
                    index=0,
                    key="model-evaluation-run-select",
                )
                selected_run = next(run for run in runs if run.run_id == selected_run_id)
                try:
                    selected_payload = load_model_evaluation_payload(selected_run)
                except Exception as exc:
                    load_error = str(exc)
                    render_status_note(tr("run.selectionFailed"), tone="error")
                    st.caption(load_error)
                else:
                    _render_kv_grid(
                        [
                            (tr("meta.generatedTime"), selected_payload["generated_label"], selected_payload["last_modified_label"]),
                            (tr("configuration.name"), selected_payload["config_name_label"], tr("modelEvaluation.runMeta", run_id=selected_payload["run_id"])),
                            (tr("market.name"), selected_payload["market_label"], t(f"股票池 {selected_payload['stock_count_label']}", f"Stock pool {selected_payload['stock_count_label']}")),
                            (tr("model.count"), selected_payload["model_count_label"], selected_payload["score_policy_text"]),
                        ]
                    )
                    render_html(
                        _pill_row_markup(
                            [
                                selected_payload["feature_labels"]["robustness"],
                                selected_payload["feature_labels"]["quantstats"],
                                selected_payload["feature_labels"]["mlflow"],
                            ]
                        )
                    )
                    st.caption(tr("modelEvaluation.reportFile", path=selected_payload["report_path"]))

    with summary_col:
        with st.container(key="model-evaluation-summary-board"):
            st.markdown(f"<div class='surface-kicker'>{html.escape(_page_text('modelEvaluation.showcaseKicker', 'Research snapshot', zh_fallback='研究快照'))}</div>", unsafe_allow_html=True)
            st.markdown(tr("run.currentSummary"), unsafe_allow_html=True)

            if selected_payload is None:
                message = load_error or tr("instruction.selectRunForModel")
                render_status_note(message, tone="warning" if load_error is None else "error")
            else:
                top_model = selected_payload["top_model"]
                _render_kv_grid(
                    [
                        (tr("model.top1"), _display_text(top_model.get("display_name")), _display_text(top_model.get("family_group"))),
                        (tr("score.total"), _format_number_text(top_model.get("total_score")), selected_payload["score_policy_text"]),
                        (tr("performance.medianSharpe"), _format_number_text(top_model.get("median_sharpe")), t(f"阶段 {_display_text(top_model.get('stage'), empty=TEXT_NA, na=TEXT_NA)}", f"Stage {_display_text(top_model.get('stage'), empty=TEXT_NA, na=TEXT_NA)}")),
                        (tr("performance.medianExcessReturn"), _format_pct_text(top_model.get("median_excess_return")), t(f"股票池 {selected_payload['pool_size_label']}", f"Stock pool {selected_payload['pool_size_label']}")),
                    ]
                )
                render_html(_top_rank_list_markup(selected_payload["top_models"]))
                render_html(
                    f"""
<div class="board-flow-row compact">
  <span>{html.escape(selected_payload['score_policy_text'])}</span>
  <span>{html.escape(selected_payload['feature_labels']['quantstats'])}</span>
  <span>{html.escape(selected_payload['feature_labels']['mlflow'])}</span>
  <span>{html.escape(tr("modelEvaluation.lastUpdated", time=selected_payload["generated_label"]))}</span>
</div>
                    """
                )

    _render_research_conclusion(selected_payload)
    _render_evaluation_export(selected_payload)

    with st.container(key="model-evaluation-tabs-shell"):
        tab_evidence, tab_robustness, tab_limits, tab_obs = st.tabs(
            [t("证据", "Evidence"), t("稳定性", "Stability"), t("局限", "Limits"), t("元数据", "Metadata")]
        )

        with tab_evidence:
            with st.container(key="model-evaluation-detail-section-evidence"):
                _render_market_strategy_evidence(selected_payload)
                st.divider()
                _render_data_section(
                    title=_page_text("modelEvaluation.section.topModels", "Top models", zh_fallback="领先模型"),
                    copy=tr("note.main_leaderboard_source"),
                    frame=_top_models_frame(selected_payload),
                )
                _render_data_section(
                    title=tr("modelEvaluation.section.familySummary"),
                    copy=tr("model.family.scoreOverview"),
                    frame=_family_summary_frame(selected_payload),
                )
                _render_data_section(
                    title=tr("modelEvaluation.section.searchMethodSummary"),
                    copy=tr("model.comparisonDescription"),
                    frame=_search_method_frame(selected_payload),
                )

        with tab_robustness:
            with st.container(key="model-evaluation-detail-section-robustness"):
                _render_news_ablation_section(selected_payload)
                st.divider()
                _render_data_section(
                    title=tr("modelEvaluation.section.robustnessSummary"),
                    copy=tr("results.rolling_robustness_summary"),
                    frame=_robustness_frame(selected_payload),
                    empty_message=tr("run.noRobustnessSummary"),
                )

        with tab_limits:
            with st.container(key="model-evaluation-detail-section-limits"):
                _render_research_limitations(selected_payload)
                st.divider()
                _render_data_section(
                    title=tr("modelEvaluation.section.failures"),
                    copy=tr("anomaly.summaryOnly"),
                    frame=_failures_frame(selected_payload),
                    empty_message=tr("run.no_anomalous_samples"),
                )

        with tab_obs:
            with st.container(key="model-evaluation-detail-section-observability"):
                _render_quantstats_section(selected_payload)
                st.divider()
                _render_mlflow_section(selected_payload)


def _render_research_conclusion(payload: dict[str, Any] | None) -> None:
    if payload and payload.get("is_us_research_baseline"):
        _render_us_research_baseline(payload)
        return

    with st.container(key="model-evaluation-research-conclusion"):
        st.markdown(
            f"<div class='surface-kicker'>{html.escape(t('跨市场结论', 'Cross-market conclusion'))}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(t("## US 与 CN_A 策略建议", "## US vs CN_A recommendations"))
        st.markdown(t(
            "结论先于支撑表格展示；每条建议都连接到对应的市场与策略记录、样本数量和局限。",
            "The conclusion is shown before the supporting tables. Every recommendation is linked "
            "to its matching market/strategy rows, sample counts, and limitations.",
        ))

        if payload is None:
            render_status_note(t("请选择一个可读运行以查看跨市场结论。", "Select a readable run to inspect its cross-market conclusions."))
            return

        research = _ensure_mapping(payload.get("research"))
        if not research.get("has_recommendations"):
            render_status_note(
                t(
                    "此运行没有跨市场建议产物，下方仍可查看旧版报告。",
                    "No cross-market recommendation artifact is available for this run. "
                    "The legacy report remains accessible below.",
                ),
                tone="warning",
            )
            return

        cards: list[str] = []
        markets = _ensure_mapping(research.get("markets"))
        for market in RESEARCH_MARKETS:
            entry = _ensure_mapping(markets.get(market))
            recommendation = _display_text(
                entry.get("recommendation"),
                empty=t("暂无建议", "No recommendation"),
                na=t("暂无建议", "No recommendation"),
            )
            trace_rows = _ensure_records(entry.get("trace_rows"))
            evidence_text = _trace_summary(trace_rows, _ensure_mapping(entry.get("evidence")))
            confidence_text = _confidence_label(entry.get("confidence"))
            meta_text = t(
                f"置信度：{confidence_text} · {evidence_text}",
                f"{confidence_text} confidence · {evidence_text}",
            )
            cards.append(
                f"""
<div class="analysis-kv-item">
  <span class="analysis-kv-label">{html.escape(market)}</span>
  <span class="analysis-kv-value">{html.escape(recommendation)}</span>
  <span class="analysis-kv-meta">{html.escape(meta_text)}</span>
</div>
                """
            )
        render_html(f"<div class='analysis-kv-grid'>{''.join(cards)}</div>")

        if not research.get("cross_market_ready"):
            render_status_note(
                t(
                    "建议已经载入，但策略矩阵没有同时包含 US 与 CN_A 的追溯记录；请把当前结论视为不完整。",
                    "Recommendations were loaded, but the strategy matrix does not contain trace rows "
                    "for both US and CN_A. Treat the conclusion as incomplete.",
                ),
                tone="warning",
            )


def _render_us_research_baseline(payload: dict[str, Any]) -> None:
    """Render the frozen US conclusion before detailed evidence tables."""
    top_model = _ensure_mapping(payload.get("top_model"))
    adaptive = _ensure_mapping(payload.get("adaptive_router"))
    ml_gain = _ensure_records(payload.get("ml_gain"))
    model_summary = _ensure_records(payload.get("model_summary"))
    robustness = _ensure_records(payload.get("robustness_summary"))
    degraded_count = len(_ensure_records(payload.get("failures")))
    top_name = _display_text(top_model.get("display_name"))
    top_score = _format_number_text(top_model.get("total_score"))
    top_excess = _format_pct_text(top_model.get("median_excess_return"))
    top_sharpe = _format_number_text(top_model.get("median_sharpe"))
    rolling_sharpe = _format_number_text(top_model.get("robustness_median_sharpe"))
    beat_naive = _format_pct_text(top_model.get("beat_naive_rate"))
    negative_ml = sum(1 for row in ml_gain if (_coerce_float(row.get("score_delta")) or 0.0) < 0)
    state_count = _format_count_label(adaptive.get("state_count"))

    with st.container(key="model-evaluation-research-conclusion"):
        st.markdown(
            f"<div class='surface-kicker'>{html.escape(t('已冻结的美股研究基线', 'Frozen US research baseline'))}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(t("## 美股研究已完成", "## US research completed"))
        st.markdown(
            t(
                "60 只美股、19 个模型、1,260 日主窗口与 4 个 rolling 窗口已经完成。"
                "当前结论只适用于美股；A 股与跨市场研究已暂停，不能从本结果外推。",
                "The 60-stock US study is complete across 19 models, a 1,260-day main window, "
                "and four rolling windows. This conclusion is US-only; CN A and cross-market "
                "research are paused and must not be inferred from these results.",
            )
        )
        render_html(
            f"""
<div class="analysis-kv-grid">
  <div class="analysis-kv-item">
    <span class="analysis-kv-label">{html.escape(t('当前离线候选', 'Current offline candidate'))}</span>
    <span class="analysis-kv-value">{html.escape(top_name)}</span>
    <span class="analysis-kv-meta">{html.escape(t(f'综合分 {top_score} · rolling Sharpe {rolling_sharpe}', f'Total score {top_score} · rolling Sharpe {rolling_sharpe}'))}</span>
  </div>
  <div class="analysis-kv-item">
    <span class="analysis-kv-label">{html.escape(t('收益边界', 'Return boundary'))}</span>
    <span class="analysis-kv-value">{html.escape(top_excess)}</span>
    <span class="analysis-kv-meta">{html.escape(t(f'主窗口中位超额收益 · 跑赢 Naive {beat_naive}', f'Median main-window excess return · beat Naive {beat_naive}'))}</span>
  </div>
  <div class="analysis-kv-item">
    <span class="analysis-kv-label">{html.escape(t('主窗口风险调整表现', 'Main-window risk-adjusted result'))}</span>
    <span class="analysis-kv-value">{html.escape(top_sharpe)}</span>
    <span class="analysis-kv-meta">{html.escape(t('中位 Sharpe；综合第一不等于稳定跑赢买入持有', 'Median Sharpe; rank one does not mean consistently beating buy-and-hold'))}</span>
  </div>
  <div class="analysis-kv-item">
    <span class="analysis-kv-label">{html.escape(t('研究完整性', 'Research completeness'))}</span>
    <span class="analysis-kv-value">{len(model_summary)} / {len(robustness)}</span>
    <span class="analysis-kv-meta">{html.escape(t(f'主窗口模型 / rolling 模型 · {degraded_count} 条降级', f'main-window / rolling models · {degraded_count} degraded records'))}</span>
  </div>
</div>
            """
        )
        render_status_note(
            t(
                f"产品口径：{top_name} 作为默认研究候选，Naive 必须并列展示；"
                f"{len(ml_gain)} 条 ML 对照中 {negative_ml} 条综合分下降，因此 ML 不默认启用；"
                f"Adaptive router 的 {state_count} 个状态只用于状态感知路由。",
                f"Product rule: show {top_name} as the default research candidate beside Naive. "
                f"ML is opt-in because {negative_ml} of {len(ml_gain)} comparisons reduced the total score; "
                f"the adaptive router's {state_count} states are for state-aware routing only.",
            ),
            tone="warning",
        )


def _render_evaluation_export(payload: dict[str, Any] | None) -> None:
    if payload is None:
        return
    news_rows = _ensure_records(_ensure_mapping(payload.get("research")).get("news_ablation"))
    news_fig = create_news_ablation_chart(news_rows) if news_rows else None
    try:
        export_html = build_model_evaluation_export_html(
            payload=payload,
            news_ablation_fig=news_fig,
            language=get_ui_language(),
            theme="light",
        )
    except Exception as exc:
        render_status_note(t(f"研究 HTML 暂时无法导出：{exc}", f"Research HTML export is unavailable: {exc}"), tone="warning")
        return

    st.download_button(
        t("下载研究 HTML", "Download research HTML"),
        data=export_html.encode("utf-8"),
        file_name=f"{payload.get('run_id', 'research-run')}-research-evidence.html",
        mime="text/html",
        key="model-evaluation-research-export",
    )


def _render_market_strategy_evidence(payload: dict[str, Any] | None) -> None:
    _render_data_section(
        title=t("建议证据", "Recommendation evidence"),
        copy=t("每一行都把市场结论连接到作为证据的具体策略与窗口指标。", "Each row connects a market conclusion to the exact strategy/window metrics used as evidence."),
        frame=_recommendation_evidence_frame(payload),
        empty_message=t("暂无可追溯的跨市场建议证据。", "No traceable cross-market recommendation evidence is available."),
    )
    st.divider()
    _render_data_section(
        title=t("US 与 CN_A 策略矩阵", "US vs CN_A strategy matrix"),
        copy=t("对比样本外指标、样本覆盖率、交易成本与滚动稳定性。", "Comparable out-of-sample metrics, sample coverage, trading cost, and rolling stability."),
        frame=_market_strategy_matrix_frame(payload),
        empty_message=t("此运行没有可用的 market_strategy_matrix.csv。", "No market_strategy_matrix.csv is available for this run."),
    )


def _render_news_ablation_section(payload: dict[str, Any] | None) -> None:
    st.markdown(f"<div class='surface-kicker'>{html.escape(t('新闻消融', 'News ablation'))}</div>", unsafe_allow_html=True)
    st.markdown(t("#### 新闻融合对比", "#### News-fusion comparison"))
    st.markdown(t(
        "在不同新闻权重和回看窗口下比较同一基础策略，并同时观察覆盖率、回退完整性与表现。",
        "Compare the same base strategy across news weights and lookback windows; coverage and "
        "fallback integrity remain visible beside performance.",
    ))
    research = _ensure_mapping(payload.get("research")) if payload else {}
    rows = _ensure_records(research.get("news_ablation"))
    if not rows:
        render_status_note(t("此运行没有可用的 news_ablation_summary.csv。", "No news_ablation_summary.csv is available for this run."))
        return

    fig = create_news_ablation_chart(rows)
    st.plotly_chart(
        fig,
        width="stretch",
        config={"displaylogo": False, "responsive": True},
        key="model-evaluation-news-ablation-chart",
    )
    for message, tone in _news_quality_notes(research):
        render_status_note(message, tone=tone)
    st.dataframe(_news_ablation_frame(payload), width="stretch", hide_index=True)


def _render_research_limitations(payload: dict[str, Any] | None) -> None:
    st.markdown(f"<div class='surface-kicker'>{html.escape(t('已知边界', 'Known boundaries'))}</div>", unsafe_allow_html=True)
    st.markdown(t("#### 建议的局限", "#### Recommendation limitations"))
    st.markdown(t("在解释胜出策略或新闻带来的表面提升前，请先阅读这些边界。", "Read these boundaries before interpreting a winner or an apparent news uplift."))

    research = _ensure_mapping(payload.get("research")) if payload else {}
    rows: list[dict[str, str]] = []
    for market in RESEARCH_MARKETS:
        entry = _ensure_mapping(_ensure_mapping(research.get("markets")).get(market))
        for limitation in _normalize_text_list(entry.get("limitations")):
            rows.append({t("市场 / 来源", "Market / source"): market, t("局限", "Limitation"): limitation})
    for issue in _normalize_text_list(research.get("issues")):
        rows.append({t("市场 / 来源", "Market / source"): t("产物校验", "Artifact validation"), t("局限", "Limitation"): issue})

    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        render_status_note(t("此运行没有记录研究局限。", "No research limitations were recorded for this run."))


def _render_quantstats_section(payload: dict[str, Any] | None) -> None:
    st.markdown("<div class='surface-kicker'>QuantStats</div>", unsafe_allow_html=True)
    st.markdown(tr("tearSheet.list.title"), unsafe_allow_html=True)
    st.markdown(
        tr("report.v1.limitedEmbed"),
        unsafe_allow_html=True,
    )
    if payload is None:
        render_status_note(tr("quantstats.no_data"))
        return

    quantstats = payload.get("quantstats", [])
    if not quantstats:
        render_status_note(tr("quantstats.tearSheet.notGenerated"))
        return

    for index, row in enumerate(quantstats, start=1):
        info_col, action_col = st.columns([1.7, 0.7], gap="medium")
        file_path = _resolve_run_path_from_string(row.get("resolved_quantstats_html_path"))
        with info_col:
            st.markdown(
                f"**#{_display_text(row.get('rank'), empty=TEXT_NA, na=TEXT_NA)} {_display_text(row.get('display_name'))}**"
            )
            st.caption(
                " / ".join(
                    [
                        tr("model.idLabel", value=_display_text(row.get("model_id"), empty=TEXT_NA, na=TEXT_NA)),
                        tr("modelEvaluation.quantstatsPooledRun", count=_format_count_label(row.get("selected_record_count"))),
                        tr("score.label", value=_format_number_text(row.get("total_score"))),
                    ]
                )
            )
            if file_path is None or not file_path.is_file():
                render_status_note(tr("file.tearsheet_missing"), tone="warning")
        with action_col:
            if file_path is not None and file_path.is_file():
                st.download_button(
                    tr("action.downloadTearSheet"),
                    data=file_path.read_bytes(),
                    file_name=file_path.name,
                    mime="text/html",
                    key=f"model-evaluation-qs-download-{index}",
                )


def _render_mlflow_section(payload: dict[str, Any] | None) -> None:
    st.markdown("<div class='surface-kicker'>MLflow</div>", unsafe_allow_html=True)
    st.markdown(tr("section.run_metadata"), unsafe_allow_html=True)
    st.markdown(
        tr("mlflow.uiScopeNote"),
        unsafe_allow_html=True,
    )
    if payload is None:
        render_status_note(tr("mlflow.info.empty"))
        return

    if not payload.get("mlflow_recorded"):
        render_status_note(tr("state.mlflowNotRecorded"))
        return

    mlflow_payload = payload.get("mlflow", {})
    _render_kv_grid(
        [
            (tr("experiment.name"), _display_text(mlflow_payload.get("experiment_name")), "experiment_name"),
            (tr("mlflow.runId"), _display_text(mlflow_payload.get("run_id"), empty=TEXT_NA, na=TEXT_NA), "run_id"),
            (_page_text("mlflow.trackingUri", "Tracking URI", zh_fallback="跟踪 URI"), _display_text(mlflow_payload.get("tracking_uri"), empty=TEXT_NA, na=TEXT_NA), "tracking_uri"),
            (tr("mlflow.artifactUri"), _display_text(mlflow_payload.get("artifact_uri"), empty=TEXT_NA, na=TEXT_NA), "artifact_uri"),
        ]
    )


def _render_data_section(
    *,
    title: str,
    copy: str,
    frame: pd.DataFrame,
    empty_message: str | None = None,
) -> None:
    st.markdown(f"<div class='surface-kicker'>{html.escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<h4 class='analysis-section-title'>{html.escape(title)}</h4>", unsafe_allow_html=True)
    st.markdown(f"<p class='analysis-section-copy'>{html.escape(copy)}</p>", unsafe_allow_html=True)
    if frame.empty:
        render_status_note(empty_message or tr("results.notAvailable"))
        return
    st.dataframe(frame, width="stretch", hide_index=True)


def _top_models_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        (payload.get("model_summary") or payload.get("top_models")) if payload else [],
        [
            (tr("field.rank"), lambda row: _display_text(row.get("rank"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("common.model"), lambda row: _display_text(row.get("display_name"))),
            (tr("category.family"), lambda row: _display_text(row.get("family_group"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("common.phase"), lambda row: _display_text(row.get("stage"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("score.total"), lambda row: _format_number_text(row.get("total_score"))),
            (tr("metric.mainWindowScore"), lambda row: _format_number_text(row.get("main_total_score"))),
            (tr("metric.robustnessScore"), lambda row: _format_number_text(row.get("robustness_total_score"))),
            (tr("performance.medianSharpe"), lambda row: _format_number_text(row.get("median_sharpe"))),
            (tr("performance.medianExcessReturn"), lambda row: _format_pct_text(row.get("median_excess_return"))),
        ],
    )


def _family_summary_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("family_summary") if payload else [],
        [
            (tr("model.family"), lambda row: _display_text(row.get("family_group"))),
            (tr("model.count"), lambda row: _format_count_label(row.get("model_count"))),
            (tr("metric.averageTotalScore"), lambda row: _format_number_text(row.get("avg_total_score"))),
            (tr("model.bestModel"), lambda row: _display_text(row.get("top_display_name"))),
            (tr("metrics.bestScore"), lambda row: _format_number_text(row.get("top_total_score"))),
        ],
    )


def _search_method_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("search_method_summary") if payload else [],
        [
            (tr("common.method"), lambda row: _display_text(row.get("method"))),
            (tr("model.count"), lambda row: _format_count_label(row.get("model_count"))),
            (tr("metric.averageTotalScore"), lambda row: _format_number_text(row.get("avg_total_score"))),
            (tr("model.bestModel"), lambda row: _display_text(row.get("top_display_name"))),
            (tr("metrics.bestScore"), lambda row: _format_number_text(row.get("top_total_score"))),
        ],
    )


def _robustness_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("robustness_summary") if payload else [],
        [
            (tr("common.model"), lambda row: _display_text(row.get("display_name"))),
            (tr("category.family"), lambda row: _display_text(row.get("family_group"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("common.phase"), lambda row: _display_text(row.get("stage"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("score.robustness_total"), lambda row: _format_number_text(row.get("robustness_total_score"))),
            (tr("metric.success_rate"), lambda row: _format_pct_text(row.get("success_rate"))),
            (tr("performance.medianSharpe"), lambda row: _format_number_text(row.get("median_sharpe"))),
            (tr("performance.medianExcessReturn"), lambda row: _format_pct_text(row.get("median_excess_return"))),
        ],
    )


def _failures_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("failures") if payload else [],
        [
            (tr("instrument.type.stock"), lambda row: _display_text(row.get("symbol"))),
            (tr("common.model"), lambda row: _display_text(row.get("display_name") or row.get("model_id"))),
            (tr("common.window"), lambda row: _display_text(row.get("window_id"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("label.status"), lambda row: _display_text(row.get("status"), empty=TEXT_NA, na=TEXT_NA)),
            (tr("button.explanation"), lambda row: _failure_message(row)),
        ],
    )


def _recommendation_evidence_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame()
    research = _ensure_mapping(payload.get("research"))
    if not research.get("has_recommendations"):
        return pd.DataFrame()

    frame_rows: list[dict[str, str]] = []
    markets = _ensure_mapping(research.get("markets"))
    for market in RESEARCH_MARKETS:
        entry = _ensure_mapping(markets.get(market))
        recommendation = _display_text(
            entry.get("recommendation"),
            empty=t("暂无建议", "No recommendation"),
            na=t("暂无建议", "No recommendation"),
        )
        confidence = _confidence_label(entry.get("confidence"))
        evidence = _evidence_summary(_ensure_mapping(entry.get("evidence")))
        trace_rows = _ensure_records(entry.get("trace_rows")) or [{}]
        for row in trace_rows:
            frame_rows.append(
                {
                    t("市场", "Market"): market,
                    t("建议策略", "Recommendation"): recommendation,
                    t("证据策略", "Evidence strategy"): _display_text(
                        row.get("strategy_label") or row.get("strategy_id"),
                        empty=TEXT_NA,
                        na=TEXT_NA,
                    ),
                    t("置信度", "Confidence"): confidence,
                    t("窗口", "Window"): _display_text(row.get("evaluation_window"), empty=TEXT_NA, na=TEXT_NA),
                    t("样本", "Samples"): _sample_trace_label(row),
                    t("覆盖率", "Coverage"): _format_pct_text(row.get("coverage_rate")),
                    t("净收益", "Net return"): _format_pct_text(row.get("net_total_return")),
                    "Sharpe": _format_number_text(row.get("sharpe")),
                    t("最大回撤", "Max drawdown"): _format_pct_text(row.get("max_drawdown")),
                    t("证据", "Evidence"): evidence,
                }
            )
    return pd.DataFrame(frame_rows)


def _market_strategy_matrix_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    research = _ensure_mapping(payload.get("research")) if payload else {}
    rows = _ensure_records(research.get("matrix"))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                t("市场", "Market"): _display_text(row.get("market"), empty=TEXT_NA, na=TEXT_NA),
                t("策略", "Strategy"): _display_text(row.get("strategy_label") or row.get("strategy_id")),
                t("窗口", "Window"): _display_text(row.get("evaluation_window"), empty=TEXT_NA, na=TEXT_NA),
                t("样本", "Samples"): _sample_trace_label(row),
                t("覆盖率", "Coverage"): _format_pct_text(row.get("coverage_rate")),
                t("净收益", "Net return"): _format_pct_text(row.get("net_total_return")),
                "Sharpe": _format_number_text(row.get("sharpe")),
                t("最大回撤", "Max drawdown"): _format_pct_text(row.get("max_drawdown")),
                t("换手", "Turnover"): _format_number_text(row.get("total_turnover")),
                t("成本", "Cost"): _format_pct_text(row.get("total_transaction_cost")),
                t("滚动排名", "Rolling rank"): _format_number_text(row.get("rolling_rank_median")),
                t("方向一致性", "Direction consistency"): _format_pct_text(row.get("rolling_direction_consistency")),
                t("降级率", "Degraded"): _format_pct_text(row.get("degraded_run_rate")),
            }
            for row in rows
        ]
    )


def _news_ablation_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    research = _ensure_mapping(payload.get("research")) if payload else {}
    rows = _ensure_records(research.get("news_ablation"))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                t("市场", "Market"): _display_text(row.get("market"), empty=TEXT_NA, na=TEXT_NA),
                t("基础策略", "Base strategy"): _display_text(row.get("base_strategy_id")),
                t("新闻权重", "News weight"): _format_number_text(row.get("news_weight")),
                t("回看窗口", "Lookback"): t(f"{_format_count_label(row.get('lookback_days'))} 天", f"{_format_count_label(row.get('lookback_days'))}d"),
                t("样本", "Samples"): _format_count_label(row.get("symbol_count")),
                t("匹配行数", "Matched rows"): _format_count_label(row.get("matched_row_count")),
                t("覆盖率", "Coverage"): _format_pct_text(row.get("coverage_rate")),
                t("回退匹配率", "Fallback match"): _format_pct_text(row.get("fallback_position_match_rate")),
                t("净收益", "Net return"): _format_pct_text(row.get("net_total_return")),
                "Sharpe": _format_number_text(row.get("sharpe")),
                t("最大回撤", "Max drawdown"): _format_pct_text(row.get("max_drawdown")),
                t("泄漏违规数", "Leakage violations"): _format_count_label(row.get("future_leakage_violation_count")),
                t("状态", "Status"): _display_text(row.get("status"), empty=TEXT_NA, na=TEXT_NA),
                t("跳过原因", "Skip reason"): _display_text(row.get("skip_reason"), empty="", na=""),
            }
            for row in rows
        ]
    )


def _news_quality_notes(research: dict[str, Any]) -> list[tuple[str, str]]:
    rows = _ensure_records(research.get("news_ablation"))
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    notes: list[tuple[str, str]] = []

    coverage = pd.to_numeric(frame.get("coverage_rate", pd.Series(dtype=float)), errors="coerce").dropna()
    if not coverage.empty:
        notes.append(
            (
                t(
                    f"观测到的新闻覆盖率为 {coverage.min():.1%}–{coverage.max():.1%}；解读表现变化时需同时考虑覆盖率。",
                    f"Observed news coverage ranges from {coverage.min():.1%} to {coverage.max():.1%}; "
                    "interpret performance changes together with this coverage.",
                ),
                "info",
            )
        )
        threshold = _coerce_float(_ensure_mapping(_ensure_mapping(research.get("manifest")).get("news")).get("coverage_threshold"))
        if threshold is not None and threshold > 0 and bool((coverage < threshold).any()):
            notes.append(
                (
                    t(
                        f"至少一条消融记录低于 manifest 中 {threshold:.1%} 的覆盖率阈值。",
                        f"At least one ablation row is below the manifest coverage threshold of {threshold:.1%}.",
                    ),
                    "warning",
                )
            )

    leakage = pd.to_numeric(
        frame.get("future_leakage_violation_count", pd.Series(dtype=float)),
        errors="coerce",
    ).fillna(0)
    if bool((leakage > 0).any()):
        notes.append((t("检测到未来信息泄漏违规；受影响记录不得作为建议依据。", "Future-leakage violations were recorded; affected rows must not support a recommendation."), "error"))

    fallback = pd.to_numeric(
        frame.get("fallback_position_match_rate", pd.Series(dtype=float)),
        errors="coerce",
    ).dropna()
    if not fallback.empty and bool((fallback < 1.0 - 1e-9).any()):
        notes.append((t("部分无新闻记录未保持上游策略仓位。", "Some no-news rows did not preserve the upstream strategy position."), "warning"))
    return notes


def _records_to_frame(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame_rows: list[dict[str, str]] = []
    for row in rows:
        frame_rows.append({label: formatter(row) for label, formatter in columns})
    return pd.DataFrame(frame_rows)


def _pill_row_markup(items: list[str]) -> str:
    pills = "".join(f"<span>{html.escape(str(item))}</span>" for item in items if item)
    return f"<div class='board-flow-row compact'>{pills}</div>"


def _top_rank_list_markup(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return tr("message.no_results_to_display")
    items = []
    for row in rows[:5]:
        stage = _display_text(row.get("stage"), empty=TEXT_NA, na=TEXT_NA)
        score = _format_number_text(row.get("total_score"))
        meta = t(f"阶段 {stage} · 分数 {score}", f"Stage {stage} · Score {score}")
        items.append(
            f"""
<div class="model-eval-rank-item">
  <span class="model-eval-rank-badge">#{html.escape(_display_text(row.get("rank"), empty=TEXT_NA, na=TEXT_NA))}</span>
  <div class="model-eval-rank-copy">
    <div class="model-eval-rank-title">{html.escape(_display_text(row.get("display_name")))}</div>
    <div class="model-eval-rank-meta">
      {html.escape(_display_text(row.get("family_group"), empty=TEXT_NA, na=TEXT_NA))}
      · {html.escape(meta)}
    </div>
  </div>
</div>
            """
        )
    return f"<div class='model-eval-rank-list'>{''.join(items)}</div>"


def _render_kv_grid(items: list[tuple[str, str, str]]) -> None:
    cards = []
    for label, value, meta in items:
        cards.append(
            f"""
<div class="analysis-kv-item">
  <span class="analysis-kv-label">{html.escape(str(label))}</span>
  <span class="analysis-kv-value">{html.escape(str(value))}</span>
  <span class="analysis-kv-meta">{html.escape(str(meta))}</span>
</div>
            """
        )
    render_html(f"<div class='analysis-kv-grid'>{''.join(cards)}</div>")


def _load_optional_csv_records(
    path: Path,
    *,
    artifact_key: str,
    source_paths: dict[str, str],
    issues: list[str],
) -> list[dict[str, Any]]:
    if not _path_is_file(path):
        return []
    source_paths[artifact_key] = str(path)
    try:
        frame = pd.read_csv(path)
    except Exception:
        issues.append(f"Unreadable or invalid {path.name}")
        return []
    if frame.empty:
        return []
    return frame.where(pd.notna(frame), None).to_dict(orient="records")


def _normalize_market_records(
    records: list[dict[str, Any]] | None,
    *,
    artifact_label: str,
    issues: list[str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in _ensure_records(records):
        market = str(row.get("market") or "").strip().upper()
        if market not in RESEARCH_MARKETS:
            issues.append(f"Ignored {artifact_label} row with unknown market '{market or 'missing'}'")
            continue
        normalized.append({**row, "market": market})
    return normalized


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _path_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _confidence_label(value: Any) -> str:
    normalized = str(value or "insufficient_evidence").strip().lower()
    return {
        "high": t("高", "High"),
        "medium": t("中", "Medium"),
        "low": t("低", "Low"),
        "insufficient_evidence": t("证据不足", "Insufficient evidence"),
    }.get(normalized, t("证据不足", "Insufficient evidence"))


def _page_text(key: str, fallback: str, *, zh_fallback: str | None = None, **kwargs: Any) -> str:
    """Use the shared catalog when present and a window-local fallback otherwise."""
    translated = tr(key, **kwargs)
    if translated != key:
        return translated
    localized_fallback = t(zh_fallback or fallback, fallback)
    try:
        return localized_fallback.format(**kwargs)
    except Exception:
        return localized_fallback


def _sample_trace_label(row: dict[str, Any]) -> str:
    successful = _format_count_label(row.get("successful_symbol_count"))
    total = _format_count_label(row.get("symbol_count"))
    if successful == TEXT_NA and total == TEXT_NA:
        return TEXT_NA
    return t(f"成功 {successful} / 总计 {total}", f"{successful} successful / {total} total")


def _evidence_summary(evidence: dict[str, Any]) -> str:
    if not evidence:
        return t("未提供结构化证据说明", "No structured evidence note")
    parts: list[str] = []
    for key, value in evidence.items():
        if _is_missing(value):
            continue
        if isinstance(value, (dict, list, tuple)) and not value:
            continue
        if isinstance(value, (dict, list, tuple)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = str(value)
        parts.append(f"{str(key).replace('_', ' ')}: {rendered}")
    return "; ".join(parts) if parts else t("未提供结构化证据说明", "No structured evidence note")


def _trace_summary(trace_rows: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
    if not trace_rows:
        return _evidence_summary(evidence)
    row = trace_rows[0]
    parts = [
        _sample_trace_label(row),
        t(f"覆盖率 {_format_pct_text(row.get('coverage_rate'))}", f"coverage {_format_pct_text(row.get('coverage_rate'))}"),
        f"Sharpe {_format_number_text(row.get('sharpe'))}",
        t(f"净收益 {_format_pct_text(row.get('net_total_return'))}", f"net return {_format_pct_text(row.get('net_total_return'))}"),
    ]
    parts.append(t(f"{len(trace_rows)} 条矩阵证据", f"{len(trace_rows)} matrix row(s)"))
    return " · ".join(parts)


def _load_json_mapping(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _ensure_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ensure_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _resolve_run_path(run: ModelEvaluationRun, path_value: Any) -> Path | None:
    if _is_missing(path_value):
        return None
    candidate = Path(str(path_value))
    if not candidate.is_absolute():
        candidate = run.run_dir / candidate
    return candidate


def _resolve_run_path_from_string(path_value: Any) -> Path | None:
    if _is_missing(path_value):
        return None
    return Path(str(path_value))


def _failure_message(row: dict[str, Any]) -> str:
    error_message = row.get("error_message")
    if not _is_missing(error_message):
        return _display_text(error_message)

    warnings_json = row.get("warnings_json")
    if isinstance(warnings_json, str) and warnings_json.strip():
        try:
            warnings = json.loads(warnings_json)
        except Exception:
            warnings = warnings_json
        if isinstance(warnings, list):
            joined = "；".join(str(item) for item in warnings if str(item).strip())
            if joined:
                return joined
        return str(warnings)
    return _empty_text()


def _empty_text() -> str:
    return tr("common.noData")


def _display_text(value: Any, *, empty: str | None = None, na: str = TEXT_NA) -> str:
    empty_text = _empty_text() if empty is None else empty
    if value is None:
        return empty_text
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or empty_text
    if _is_missing(value):
        return na
    return str(value)


def _format_number_text(value: Any) -> str:
    numeric = _coerce_float(value)
    if numeric is None:
        return TEXT_NA
    return f"{numeric:.2f}"


def _format_pct_text(value: Any) -> str:
    numeric = _coerce_float(value)
    if numeric is None:
        return TEXT_NA
    return f"{numeric:.2%}"


def _format_count_label(value: Any) -> str:
    numeric = _coerce_float(value)
    if numeric is None:
        return TEXT_NA
    return str(int(numeric))


def _format_timestamp_label(timestamp_value: float) -> str:
    try:
        dt = datetime.fromtimestamp(float(timestamp_value)).astimezone()
    except Exception:
        return _empty_text()
    return dt.strftime("%Y-%m-%d %H:%M")


def _format_datetime_text(value: Any) -> str:
    if _is_missing(value):
        return _empty_text()
    try:
        dt = pd.Timestamp(value)
    except Exception:
        return _display_text(value)
    if dt.tzinfo is not None:
        dt = dt.tz_convert(datetime.now().astimezone().tzinfo)
    return dt.strftime("%Y-%m-%d %H:%M")


def _coerce_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except Exception:
        return False
    return bool(result) if isinstance(result, (bool, int)) else False
