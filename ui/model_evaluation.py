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

from ui.theme import render_html, render_route_nav, render_status_note


MODEL_EVALUATION_ROUTE = "model-evaluation"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUTS_ROOT = REPO_ROOT / "model-test" / "outputs"
TEXT_EMPTY = "暂无数据"
TEXT_NA = "N/A"


@dataclass(frozen=True)
class ModelEvaluationRun:
    run_id: str
    run_dir: Path
    report_path: Path
    modified_ts: float


def discover_model_evaluation_runs(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> list[ModelEvaluationRun]:
    """扫描可读 run，忽略内部目录、无报告目录和读取失败目录。"""
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
    """读取选中 run 的 report 与可选 MLflow manifest。"""
    report_payload = _load_json_mapping(run.report_path)
    if report_payload is None:
        raise ValueError(f"无法读取报告文件：{run.report_path}")

    mlflow_path = run.run_dir / "mlflow_run.json"
    try:
        mlflow_payload = _load_json_mapping(mlflow_path) if mlflow_path.is_file() else None
    except OSError:
        mlflow_payload = None
    return normalize_model_evaluation_payload(run, report_payload, mlflow_payload)


def normalize_model_evaluation_payload(
    run: ModelEvaluationRun,
    report_payload: dict[str, Any],
    mlflow_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把 report.json 归一成页面消费结构，并兜住旧 run 的缺字段情况。"""
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
        score_policy_text = "主窗口 + 稳健性综合评分"
    else:
        score_policy_text = "仅主窗口总分"

    quantstats_enabled = bool(config.get("enable_quantstats")) or bool(quantstats)
    quantstats_label = "未生成"
    if quantstats:
        quantstats_label = f"{len(quantstats)} 份 tear sheet"
    elif quantstats_enabled:
        quantstats_label = "已启用，暂未生成"

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
        "quantstats": quantstats,
        "failures": failures,
        "mlflow": mlflow_payload or {},
        "mlflow_recorded": bool(mlflow_payload),
        "config_name_label": _display_text(config.get("name")),
        "market_label": _display_text(config.get("market"), empty=TEXT_NA, na=TEXT_NA),
        "stock_count_label": _format_count_label(pool.get("stock_count")),
        "model_count_label": _format_count_label(model_count),
        "pool_size_label": _format_count_label(pool.get("stock_count")),
        "score_policy_text": score_policy_text,
        "feature_labels": {
            "robustness": "已启用" if robustness_enabled else "未启用",
            "quantstats": quantstats_label,
            "mlflow": "已记录 MLflow" if mlflow_payload else "未记录 MLflow",
        },
    }
    return normalized


def render_model_evaluation_page(*, outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> None:
    """渲染 `/strategy/model-evaluation`。"""
    render_route_nav(MODEL_EVALUATION_ROUTE)

    runs = discover_model_evaluation_runs(outputs_root)
    latest_run_label = runs[0].run_id if runs else TEXT_EMPTY
    latest_time_label = _format_timestamp_label(runs[0].modified_ts) if runs else TEXT_EMPTY

    render_html(
        f"""
<section class="analysis-page-shell">
  <div class="analysis-hero">
    <div class="analysis-hero-topline">
      <span class="analysis-pill accent">Model Evaluation</span>
      <span class="analysis-pill">{len(runs)} 个可读 run</span>
      <span class="analysis-pill">{html.escape(str(outputs_root.name))}</span>
    </div>
    <div class="analysis-hero-main">
      <div>
        <h1 class="analysis-title">只读浏览已有模型研究结果。</h1>
        <p class="analysis-subtitle">
          这个页面只读取本地 <code>model-test/outputs</code> 下的现有研究产物，不触发任何研究执行。
          默认展示最新可读 run，并允许在不同 run 之间切换浏览。
        </p>
      </div>
      <div class="analysis-quick-grid">
        <div class="analysis-quick-item">
          <span class="analysis-quick-label">公开路径</span>
          <span class="analysis-quick-value">/strategy/model-evaluation</span>
          <span class="analysis-quick-meta">只读结果浏览页</span>
        </div>
        <div class="analysis-quick-item">
          <span class="analysis-quick-label">最新可读 run</span>
          <span class="analysis-quick-value">{html.escape(latest_run_label)}</span>
          <span class="analysis-quick-meta">{html.escape(latest_time_label)}</span>
        </div>
        <div class="analysis-quick-item">
          <span class="analysis-quick-label">数据来源</span>
          <span class="analysis-quick-value">{html.escape(str(outputs_root))}</span>
          <span class="analysis-quick-meta">report.json / mlflow_run.json</span>
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
            st.markdown("<div class='surface-kicker'>Run Browser</div>", unsafe_allow_html=True)
            st.markdown("<h3 class='surface-title'>浏览已有研究 run</h3>", unsafe_allow_html=True)
            st.markdown(
                "<p class='surface-copy'>页面只消费 report.json 已汇总的结果和可选的 QuantStats / MLflow 元信息。</p>",
                unsafe_allow_html=True,
            )

            if not runs:
                render_status_note("当前没有可读取的研究 run。", tone="warning")
                st.caption(f"扫描目录：{outputs_root}")
            else:
                selected_run_id = st.selectbox(
                    "选择 run",
                    options=[run.run_id for run in runs],
                    index=0,
                    key="model-evaluation-run-select",
                )
                selected_run = next(run for run in runs if run.run_id == selected_run_id)
                try:
                    selected_payload = load_model_evaluation_payload(selected_run)
                except Exception as exc:
                    load_error = str(exc)
                    render_status_note("选中的 run 读取失败。", tone="error")
                    st.caption(load_error)
                else:
                    _render_kv_grid(
                        [
                            ("生成时间", selected_payload["generated_label"], selected_payload["last_modified_label"]),
                            ("配置名称", selected_payload["config_name_label"], f"run: {selected_payload['run_id']}"),
                            ("市场", selected_payload["market_label"], f"股票池 {selected_payload['stock_count_label']}"),
                            ("模型数量", selected_payload["model_count_label"], selected_payload["score_policy_text"]),
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
                    st.caption(f"报告文件：{selected_payload['report_path']}")

    with summary_col:
        with st.container(key="model-evaluation-summary-board"):
            st.markdown("<div class='surface-kicker'>Showcase</div>", unsafe_allow_html=True)
            st.markdown("<h3 class='surface-title'>当前 run 摘要</h3>", unsafe_allow_html=True)

            if selected_payload is None:
                message = load_error or "选择一个可读 run 后，这里会展示当前最佳模型和评分规则。"
                render_status_note(message, tone="warning" if load_error is None else "error")
            else:
                top_model = selected_payload["top_model"]
                _render_kv_grid(
                    [
                        ("Top 1 模型", _display_text(top_model.get("display_name")), _display_text(top_model.get("family_group"))),
                        ("总分", _format_number_text(top_model.get("total_score")), selected_payload["score_policy_text"]),
                        ("中位夏普", _format_number_text(top_model.get("median_sharpe")), f"阶段 {_display_text(top_model.get('stage'), empty=TEXT_NA, na=TEXT_NA)}"),
                        ("中位超额收益", _format_pct_text(top_model.get("median_excess_return")), f"股票池 {selected_payload['pool_size_label']}"),
                    ]
                )
                render_html(_top_rank_list_markup(selected_payload["top_models"]))
                render_html(
                    f"""
<div class="board-flow-row compact">
  <span>{html.escape(selected_payload['score_policy_text'])}</span>
  <span>{html.escape(selected_payload['feature_labels']['quantstats'])}</span>
  <span>{html.escape(selected_payload['feature_labels']['mlflow'])}</span>
  <span>最新更新时间 {html.escape(selected_payload['generated_label'])}</span>
</div>
                    """
                )

    with st.container(key="model-evaluation-tabs-shell"):
        tab_overview, tab_obs, tab_failures = st.tabs(["总览", "QuantStats / MLflow", "异常样本"])

        with tab_overview:
            with st.container(key="model-evaluation-detail-section-overview"):
                _render_data_section(
                    title="Top Models",
                    copy="主榜单固定读取 report.json 中的汇总结果，不在页面内重扫 artifacts。",
                    frame=_top_models_frame(selected_payload),
                )
                _render_data_section(
                    title="Family Summary",
                    copy="按 baseline / sm / fsm 族查看平均得分与最佳模型。",
                    frame=_family_summary_frame(selected_payload),
                )
                _render_data_section(
                    title="Search Method Summary",
                    copy="横向比较 random / bayesian / genetic 的平均表现与胜出模型。",
                    frame=_search_method_frame(selected_payload),
                )
                _render_data_section(
                    title="Robustness Summary",
                    copy="若 run 启用了 rolling robustness，这里显示稳健性汇总；否则只展示空态。",
                    frame=_robustness_frame(selected_payload),
                    empty_message="当前 run 没有 robustness 汇总。",
                )

        with tab_obs:
            with st.container(key="model-evaluation-detail-section-observability"):
                _render_quantstats_section(selected_payload)
                st.divider()
                _render_mlflow_section(selected_payload)

        with tab_failures:
            with st.container(key="model-evaluation-detail-section-failures"):
                _render_data_section(
                    title="Failures / Degraded Samples",
                    copy="这里只展示 report.json 里已汇总的异常样本，不重新追踪底层任务日志。",
                    frame=_failures_frame(selected_payload),
                    empty_message="当前 run 没有异常样本。",
                )


def _render_quantstats_section(payload: dict[str, Any] | None) -> None:
    st.markdown("<div class='surface-kicker'>QuantStats</div>", unsafe_allow_html=True)
    st.markdown("<h4 class='analysis-section-title'>Tear Sheet 列表</h4>", unsafe_allow_html=True)
    st.markdown(
        "<p class='analysis-section-copy'>v1 只展示条目摘要并提供文件下载，不在应用内嵌入整页 HTML。</p>",
        unsafe_allow_html=True,
    )
    if payload is None:
        render_status_note("当前没有可展示的 QuantStats 信息。")
        return

    quantstats = payload.get("quantstats", [])
    if not quantstats:
        render_status_note("当前 run 未生成 QuantStats tear sheet。")
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
                        f"模型ID {_display_text(row.get('model_id'), empty=TEXT_NA, na=TEXT_NA)}",
                        f"pooled run {_format_count_label(row.get('selected_record_count'))}",
                        f"分数 {_format_number_text(row.get('total_score'))}",
                    ]
                )
            )
            if file_path is None or not file_path.is_file():
                render_status_note("tearsheet.html 文件不存在，当前只保留元数据。", tone="warning")
        with action_col:
            if file_path is not None and file_path.is_file():
                st.download_button(
                    "下载 tear sheet",
                    data=file_path.read_bytes(),
                    file_name=file_path.name,
                    mime="text/html",
                    key=f"model-evaluation-qs-download-{index}",
                )


def _render_mlflow_section(payload: dict[str, Any] | None) -> None:
    st.markdown("<div class='surface-kicker'>MLflow</div>", unsafe_allow_html=True)
    st.markdown("<h4 class='analysis-section-title'>Run 元信息</h4>", unsafe_allow_html=True)
    st.markdown(
        "<p class='analysis-section-copy'>页面只显示 mlflow_run.json 元数据，不尝试启动或嵌入 MLflow UI。</p>",
        unsafe_allow_html=True,
    )
    if payload is None:
        render_status_note("当前没有可展示的 MLflow 信息。")
        return

    if not payload.get("mlflow_recorded"):
        render_status_note("未记录 MLflow。")
        return

    mlflow_payload = payload.get("mlflow", {})
    _render_kv_grid(
        [
            ("实验名", _display_text(mlflow_payload.get("experiment_name")), "experiment_name"),
            ("Run ID", _display_text(mlflow_payload.get("run_id"), empty=TEXT_NA, na=TEXT_NA), "run_id"),
            ("Tracking URI", _display_text(mlflow_payload.get("tracking_uri"), empty=TEXT_NA, na=TEXT_NA), "tracking_uri"),
            ("Artifact URI", _display_text(mlflow_payload.get("artifact_uri"), empty=TEXT_NA, na=TEXT_NA), "artifact_uri"),
        ]
    )


def _render_data_section(
    *,
    title: str,
    copy: str,
    frame: pd.DataFrame,
    empty_message: str = "暂无可展示结果。",
) -> None:
    st.markdown(f"<div class='surface-kicker'>{html.escape(title)}</div>", unsafe_allow_html=True)
    st.markdown(f"<h4 class='analysis-section-title'>{html.escape(title)}</h4>", unsafe_allow_html=True)
    st.markdown(f"<p class='analysis-section-copy'>{html.escape(copy)}</p>", unsafe_allow_html=True)
    if frame.empty:
        render_status_note(empty_message)
        return
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _top_models_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        (payload.get("model_summary") or payload.get("top_models")) if payload else [],
        [
            ("排名", lambda row: _display_text(row.get("rank"), empty=TEXT_NA, na=TEXT_NA)),
            ("模型", lambda row: _display_text(row.get("display_name"))),
            ("族", lambda row: _display_text(row.get("family_group"), empty=TEXT_NA, na=TEXT_NA)),
            ("阶段", lambda row: _display_text(row.get("stage"), empty=TEXT_NA, na=TEXT_NA)),
            ("总分", lambda row: _format_number_text(row.get("total_score"))),
            ("主窗口分", lambda row: _format_number_text(row.get("main_total_score"))),
            ("稳健性分", lambda row: _format_number_text(row.get("robustness_total_score"))),
            ("中位夏普", lambda row: _format_number_text(row.get("median_sharpe"))),
            ("中位超额收益", lambda row: _format_pct_text(row.get("median_excess_return"))),
        ],
    )


def _family_summary_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("family_summary") if payload else [],
        [
            ("模型族", lambda row: _display_text(row.get("family_group"))),
            ("模型数", lambda row: _format_count_label(row.get("model_count"))),
            ("平均总分", lambda row: _format_number_text(row.get("avg_total_score"))),
            ("最佳模型", lambda row: _display_text(row.get("top_display_name"))),
            ("最佳分数", lambda row: _format_number_text(row.get("top_total_score"))),
        ],
    )


def _search_method_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("search_method_summary") if payload else [],
        [
            ("方法", lambda row: _display_text(row.get("method"))),
            ("模型数", lambda row: _format_count_label(row.get("model_count"))),
            ("平均总分", lambda row: _format_number_text(row.get("avg_total_score"))),
            ("最佳模型", lambda row: _display_text(row.get("top_display_name"))),
            ("最佳分数", lambda row: _format_number_text(row.get("top_total_score"))),
        ],
    )


def _robustness_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("robustness_summary") if payload else [],
        [
            ("模型", lambda row: _display_text(row.get("display_name"))),
            ("族", lambda row: _display_text(row.get("family_group"), empty=TEXT_NA, na=TEXT_NA)),
            ("阶段", lambda row: _display_text(row.get("stage"), empty=TEXT_NA, na=TEXT_NA)),
            ("稳健性总分", lambda row: _format_number_text(row.get("robustness_total_score"))),
            ("成功率", lambda row: _format_pct_text(row.get("success_rate"))),
            ("中位夏普", lambda row: _format_number_text(row.get("median_sharpe"))),
            ("中位超额收益", lambda row: _format_pct_text(row.get("median_excess_return"))),
        ],
    )


def _failures_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    return _records_to_frame(
        payload.get("failures") if payload else [],
        [
            ("股票", lambda row: _display_text(row.get("symbol"))),
            ("模型", lambda row: _display_text(row.get("display_name") or row.get("model_id"))),
            ("窗口", lambda row: _display_text(row.get("window_id"), empty=TEXT_NA, na=TEXT_NA)),
            ("状态", lambda row: _display_text(row.get("status"), empty=TEXT_NA, na=TEXT_NA)),
            ("说明", lambda row: _failure_message(row)),
        ],
    )


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
        return "<div class='model-eval-rank-empty'>暂无可展示结果。</div>"
    items = []
    for row in rows[:5]:
        items.append(
            f"""
<div class="model-eval-rank-item">
  <span class="model-eval-rank-badge">#{html.escape(_display_text(row.get("rank"), empty=TEXT_NA, na=TEXT_NA))}</span>
  <div class="model-eval-rank-copy">
    <div class="model-eval-rank-title">{html.escape(_display_text(row.get("display_name")))}</div>
    <div class="model-eval-rank-meta">
      {html.escape(_display_text(row.get("family_group"), empty=TEXT_NA, na=TEXT_NA))}
      · 阶段 {html.escape(_display_text(row.get("stage"), empty=TEXT_NA, na=TEXT_NA))}
      · 分数 {html.escape(_format_number_text(row.get("total_score")))}
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
    return TEXT_EMPTY


def _display_text(value: Any, *, empty: str = TEXT_EMPTY, na: str = TEXT_NA) -> str:
    if value is None:
        return empty
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or empty
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
        return TEXT_EMPTY
    return dt.strftime("%Y-%m-%d %H:%M")


def _format_datetime_text(value: Any) -> str:
    if _is_missing(value):
        return TEXT_EMPTY
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
