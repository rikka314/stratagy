"""Serializable chart presentations for the archived research reader."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from ui.research_browser import REPO_ROOT, _chart_frame, load_research_experiments


@lru_cache(maxsize=4)
def _experiments(repo_root: Path):
    return load_research_experiments(repo_root)[0]


def _labels(language: str) -> dict[str, str]:
    zh = language == "zh"
    return {
        "sharpe": "Sharpe",
        "query_utility": "查询效用" if zh else "Query utility",
        "regret": "遗憾" if zh else "Regret",
        "utility_regret": "效用 / 遗憾" if zh else "Utility / regret",
        "candidate": "候选策略" if zh else "Candidate",
        "adaptive": "Adaptive 对照" if zh else "Adaptive control",
        "net_return": "净收益" if zh else "Net return",
        "max_drawdown": "最大回撤" if zh else "Max drawdown",
        "metric": "指标" if zh else "Metric",
        "pass_rate": "Fold 通过率" if zh else "Fold pass rate",
        "score": "综合分" if zh else "Total score",
        "score_axis": "分数" if zh else "Score",
    }


def _figure(experiment_id: str, frame: pd.DataFrame, language: str) -> tuple[str, go.Figure] | None:
    label = _labels(language)
    zh = language == "zh"
    figure = go.Figure()
    if experiment_id == "cn_a_composite_only" and {"model_name", "sharpe_mean"}.issubset(frame.columns):
        figure.add_bar(x=frame["model_name"].tolist(), y=frame["sharpe_mean"].tolist(), name=label["sharpe"])
        figure.update_yaxes(title_text=label["sharpe"])
        title = "CN_A Composite 与 SM/FSM 的统一 Sharpe 对比" if zh else "Unified CN_A Sharpe comparison: Composite vs SM/FSM"
    elif experiment_id == "transformer_state_feasibility" and {"method", "mean_query_selected_utility", "mean_regret"}.issubset(frame.columns):
        grouped = frame.groupby("method", as_index=False)[["mean_query_selected_utility", "mean_regret"]].mean()
        figure.add_bar(x=grouped["method"].tolist(), y=grouped["mean_query_selected_utility"].tolist(), name=label["query_utility"])
        figure.add_bar(x=grouped["method"].tolist(), y=grouped["mean_regret"].tolist(), name=label["regret"])
        figure.update_yaxes(title_text=label["utility_regret"])
        title = "查询效用与遗憾：为什么 Transformer 在门前停止" if zh else "Query utility and regret: why Transformer stopped"
    elif experiment_id == "adaptive_dynamic_experts" and {"split_id", "candidate_total_return", "adaptive_total_return"}.issubset(frame.columns):
        figure.add_bar(x=frame["split_id"].tolist(), y=frame["candidate_total_return"].tolist(), name=label["candidate"])
        figure.add_bar(x=frame["split_id"].tolist(), y=frame["adaptive_total_return"].tolist(), name=label["adaptive"])
        figure.update_yaxes(tickformat=".1%", title_text=label["net_return"])
        title = "W11 US 四个窗口：候选策略与 adaptive control" if zh else "W11 US: candidate vs adaptive control across four windows"
    elif experiment_id == "cn_a_composite_advisory" and {"policy", "sharpe", "max_drawdown"}.issubset(frame.columns):
        grouped = frame.groupby("policy", as_index=False)[["sharpe", "max_drawdown"]].mean()
        figure.add_bar(x=grouped["policy"].tolist(), y=grouped["sharpe"].tolist(), name=label["sharpe"])
        figure.add_bar(x=grouped["policy"].tolist(), y=grouped["max_drawdown"].tolist(), name=label["max_drawdown"])
        figure.update_yaxes(title_text=label["metric"])
        title = "Advisory 消融：收益与风险必须同时看" if zh else "Advisory ablation: read return and risk together"
    elif experiment_id == "us_composite" and {"strategy_variant", "pass_rate"}.issubset(frame.columns):
        figure.add_bar(x=frame["strategy_variant"].tolist(), y=frame["pass_rate"].tolist(), name=label["pass_rate"])
        figure.update_yaxes(tickformat=".0%", title_text=label["pass_rate"])
        title = "US Composite 跨 fold 准入率" if zh else "US Composite cross-fold admission rate"
    elif {"display_name", "total_score"}.issubset(frame.columns):
        sample = frame.sort_values("rank").head(10) if "rank" in frame.columns else frame.head(10)
        figure.add_bar(x=sample["display_name"].tolist(), y=sample["total_score"].tolist(), name=label["score"])
        figure.update_yaxes(title_text=label["score_axis"])
        title = "基线模型综合分（前十）" if zh else "Baseline composite score (top ten)"
    else:
        return None

    figure.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=20, b=110),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.08, x=0),
    )
    return title, figure


def research_chart(experiment_id: str, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Return both language editions of the same archived Plotly chart."""
    experiments = _experiments(repo_root)
    experiment = next((item for item in experiments if item.experiment_id == experiment_id), None)
    if experiment is None:
        return {"available": False, "reason": "unknown_experiment"}

    source, frame = _chart_frame(experiment, repo_root)
    if frame.empty:
        return {
            "available": False,
            "reason": "missing_artifact",
            "message": {
                "zh": "没有找到可绘图的已落地 CSV；这不是零结果。",
                "en": "No materialized CSV is available for a chart; this is not a zero result.",
            },
        }

    editions: dict[str, Any] = {}
    for language in ("zh", "en"):
        result = _figure(experiment_id, frame, language)
        if result is None:
            return {
                "available": False,
                "reason": "unsupported_schema",
                "source": source,
                "message": {
                    "zh": "该实验的已落地数据暂不满足图表字段要求。",
                    "en": "The materialized data does not contain the fields needed for a chart.",
                },
            }
        title, figure = result
        editions[language] = {
            "title": title,
            "figure": json.loads(pio.to_json(figure, validate=True, remove_uids=True)),
        }

    supplemental = any(item.path == source and item.supplemental for item in experiment.evidence)
    return {
        "available": True,
        "source": source,
        "supplemental": supplemental,
        "editions": editions,
    }
