from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from ui.theme import render_route_nav, t


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_TEST_ROOT = REPO_ROOT / "model-test"
if str(MODEL_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_TEST_ROOT))

from model_test.campaign import (
    CAMPAIGNS_ROOT,
    list_campaign_ids,
    load_campaign_snapshot,
    request_pause,
    resume_campaign,
    start_campaign,
    tail_campaign_log,
)
from model_test.monitoring import build_stage_leaderboards, leaderboard_view, load_checkpoint_records


EXPERIMENT_MONITOR_ROUTE = "experiment-monitor"
CONTROL_ENV = "STRATAGY_RESEARCH_CONTROL"
US_BASELINE_DIR = MODEL_TEST_ROOT / "outputs" / "full_us_deans_60"


def research_control_enabled() -> bool:
    return os.getenv(CONTROL_ENV, "").strip() == "1"


def _completed_us_baseline() -> dict[str, Any] | None:
    """Return a compact verified snapshot for the intentionally completed US scope."""
    report_path = US_BASELINE_DIR / "report.json"
    runs_path = US_BASELINE_DIR / "runs.csv"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        config = report.get("config") or {}
        models = report.get("model_summary") or []
        top_models = report.get("top_models") or []
        records = pd.read_csv(runs_path, usecols=["status"])
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return None
    if (
        config.get("name") != "full_us_deans_60"
        or str(config.get("market") or "").upper() != "US"
        or len(models) != 19
        or len(records) != 5460
        or not top_models
    ):
        return None
    counts = records["status"].astype(str).str.lower().value_counts().to_dict()
    return {
        "record_count": len(records),
        "success": int(counts.get("success", 0)),
        "degraded": int(counts.get("degraded", 0)),
        "failed": int(counts.get("failed", 0)),
        "top_model": str(top_models[0].get("display_name") or top_models[0].get("model_id") or "N/A"),
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _duration_text(started_at: Any, completed_at: Any = None) -> str:
    start = _parse_datetime(started_at)
    end = _parse_datetime(completed_at) or datetime.now(timezone.utc)
    if start is None:
        return "N/A"
    seconds = max(0, int((end - start).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _overall_progress(snapshot) -> tuple[int, int]:
    completed = 0
    total = 0
    for run in snapshot.campaign.get("runs") or []:
        estimate = run.get("task_estimate") or {}
        total += int(estimate.get("total_records_max") or 0)
        output_subdir = str(run.get("output_subdir") or "")
        if not output_subdir or run.get("market") == "CROSS":
            continue
        frame = load_checkpoint_records(MODEL_TEST_ROOT / "outputs" / output_subdir)
        completed += int(len(frame))
    return completed, total


def _status_counts(progress: dict[str, Any]) -> dict[str, int]:
    raw = progress.get("status_counts")
    if not isinstance(raw, dict):
        return {}
    return {str(key).lower(): int(value) for key, value in raw.items()}


def _render_controls(campaign_id: str, status: str, enabled: bool, *, scope_complete: bool = False) -> None:
    left, middle, right = st.columns([1, 1, 3])
    with left:
        if status in {"preflight", "running", "resuming", "pause_requested"}:
            if st.button(
                t("安全暂停", "Safe pause"),
                disabled=not enabled or status == "pause_requested",
                width="stretch",
                key=f"pause-{campaign_id}",
            ):
                try:
                    request_pause(campaign_id)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        elif status in {"paused", "failed"} and not scope_complete:
            if st.button(
                t("恢复实验", "Resume"),
                disabled=not enabled,
                width="stretch",
                key=f"resume-{campaign_id}",
            ):
                try:
                    resume_campaign(campaign_id)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    with middle:
        st.button(t("刷新", "Refresh"), width="stretch", key=f"refresh-{campaign_id}")
    with right:
        if not enabled:
            st.caption(t("当前为只读模式；本地控制开关未启用。", "Read-only mode; local control is disabled."))
        elif status == "pause_requested":
            st.caption(t("暂停已请求，正在等待在途批次完整落盘。", "Pause requested; waiting for in-flight batches to checkpoint."))


def _render_run_table(snapshot, *, scope_complete: bool = False) -> None:
    rows = []
    for run in snapshot.campaign.get("runs") or []:
        estimate = run.get("task_estimate") or {}
        rows.append(
            {
                t("市场", "Market"): run.get("market"),
                t("配置", "Config"): run.get("config_name"),
                t("状态", "Status"): (
                    t("已完成", "completed") if scope_complete and run.get("market") == "US"
                    else t("已暂停", "paused") if scope_complete
                    else run.get("status")
                ),
                t("最大记录数", "Max records"): estimate.get("total_records_max") or "—",
                t("输出目录", "Output"): run.get("output_subdir"),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_leaderboard_tab(frame: pd.DataFrame, *, robustness: bool = False) -> None:
    view = leaderboard_view(frame, robustness=robustness)
    if view.empty:
        st.info(t("当前阶段还没有足够的已完成记录。", "No completed records are available for this stage yet."))
        return
    st.caption(t("临时排名会随样本覆盖率提高而变化。", "Provisional ranks change as sample coverage grows."))
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "coverage": st.column_config.ProgressColumn(
                t("覆盖率", "Coverage"), min_value=0.0, max_value=1.0, format="percent"
            ),
        },
    )


def _render_rankings(snapshot, campaign_id: str) -> None:
    active_run = snapshot.run or {}
    if active_run.get("market") == "CROSS" or not active_run.get("output_subdir"):
        st.info(t("跨市场汇总阶段不生成临时单市场榜单。", "Cross-market aggregation has no provisional single-market leaderboard."))
        return
    run_dir = MODEL_TEST_ROOT / "outputs" / str(active_run["output_subdir"])
    cache_key = f"experiment-monitor-records-{campaign_id}-{active_run['output_subdir']}"
    previous = st.session_state.get(cache_key)
    records = load_checkpoint_records(run_dir, fallback=previous if isinstance(previous, pd.DataFrame) else None)
    if not records.empty:
        st.session_state[cache_key] = records
    boards = build_stage_leaderboards(
        records,
        config_path=str(active_run["config_path"]),
        final_summary_path=run_dir / "model_summary.csv",
    )
    tabs = st.tabs(
        [
            t("Stage A 临时榜", "Stage A"),
            t("Stage B 临时榜", "Stage B"),
            t("滚动稳健性", "Rolling"),
            t("最终总榜", "Final"),
        ]
    )
    with tabs[0]:
        _render_leaderboard_tab(boards["stage_a"])
    with tabs[1]:
        _render_leaderboard_tab(boards["stage_b"])
    with tabs[2]:
        _render_leaderboard_tab(boards["rolling"], robustness=True)
    with tabs[3]:
        _render_leaderboard_tab(boards["final"])


def _render_campaign(campaign_id: str, *, enabled: bool) -> None:
    try:
        snapshot = load_campaign_snapshot(campaign_id)
    except Exception as exc:
        st.error(t(f"无法读取 campaign：{exc}", f"Unable to read campaign: {exc}"))
        return
    campaign = snapshot.campaign
    status = str(campaign.get("status") or "unknown")
    us_baseline = _completed_us_baseline()
    scope_complete = bool(us_baseline and status == "failed")
    _render_controls(campaign_id, status, enabled, scope_complete=scope_complete)

    completed, total = _overall_progress(snapshot)
    if scope_complete and us_baseline:
        completed = total = int(us_baseline["record_count"])
    progress_ratio = min(1.0, completed / total) if total else 0.0
    st.progress(progress_ratio, text=f"{completed:,} / {total:,}" if total else t("正在计算任务规模", "Estimating workload"))

    counts = _status_counts(snapshot.progress)
    if scope_complete and us_baseline:
        counts = {key: int(us_baseline[key]) for key in ("success", "degraded", "failed")}
    metrics = st.columns(6)
    metrics[0].metric(t("状态", "Status"), t("美股已完成", "US complete") if scope_complete else status)
    metrics[1].metric(t("阶段", "Phase"), t("研究范围已冻结", "Scope frozen") if scope_complete else snapshot.phase or "N/A")
    metrics[2].metric(t("成功", "Success"), counts.get("success", 0))
    metrics[3].metric(t("降级", "Degraded"), counts.get("degraded", 0))
    metrics[4].metric(t("失败", "Failed"), counts.get("failed", 0))
    metrics[5].metric(t("运行时间", "Elapsed"), _duration_text(campaign.get("started_at"), campaign.get("completed_at")))

    if scope_complete and us_baseline:
        st.success(
            t(
                f"美股全量研究已经完成，当前候选为 {us_baseline['top_model']}。A 股与跨市场阶段按当前研究范围暂停，无需恢复实验。",
                f"The full US study is complete; the current candidate is {us_baseline['top_model']}. "
                "CN A and cross-market stages are paused by scope, so the campaign does not need to resume.",
            )
        )
    elif snapshot.error:
        st.error(str(snapshot.error.get("message") or snapshot.error))
    if snapshot.progress.get("last_record_key"):
        st.caption(
            t("最近完成：", "Last completed: ")
            + " / ".join(str(item) for item in snapshot.progress["last_record_key"])
        )
    in_flight = int(snapshot.progress.get("in_flight_batches") or 0)
    pending = int(snapshot.progress.get("pending_batches") or 0)
    st.caption(t(f"在途批次 {in_flight} · 待提交批次 {pending}", f"In flight {in_flight} · pending {pending}"))

    st.subheader(t("市场运行序列", "Run sequence"))
    _render_run_table(snapshot, scope_complete=scope_complete)
    st.subheader(t("实时策略排名", "Live strategy rankings"))
    _render_rankings(snapshot, campaign_id)
    with st.expander(t("最近运行日志", "Recent log"), expanded=False):
        log_text = tail_campaign_log(campaign_id, line_count=120)
        st.code(log_text or t("暂无日志。", "No log output yet."), language="text")


def render_experiment_monitor_page() -> None:
    render_route_nav(EXPERIMENT_MONITOR_ROUTE)
    enabled = research_control_enabled()
    st.title(t("窗口 3B 全量实验", "Window 3B Full Research"))
    st.caption(
        t(
            "本地后台执行 US 60 → A 股 60 → 跨市场汇总；页面关闭后实验继续运行。",
            "Runs US 60 → CN A 60 → cross-market aggregation in a local background process.",
        )
    )

    campaign_ids = list_campaign_ids()
    if not campaign_ids:
        st.info(t("尚未创建正式 campaign。", "No formal campaign has been created."))
        if st.button(
            t("启动正式全量实验", "Start full campaign"),
            disabled=not enabled,
            type="primary",
        ):
            try:
                snapshot = start_campaign()
                st.session_state["experiment_monitor_campaign_id"] = snapshot.campaign["campaign_id"]
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if not enabled:
            st.caption(t("请通过本地 run.bat 启动控制模式。", "Launch local control mode through run.bat."))
        return

    selected_default = st.session_state.get("experiment_monitor_campaign_id")
    default_index = campaign_ids.index(selected_default) if selected_default in campaign_ids else 0
    campaign_id = st.selectbox(t("Campaign", "Campaign"), campaign_ids, index=default_index)
    st.session_state["experiment_monitor_campaign_id"] = campaign_id

    @st.fragment(run_every="2s")
    def _live_fragment() -> None:
        _render_campaign(campaign_id, enabled=enabled)

    _live_fragment()
