from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ui.export_reports import build_multi_stock_export_html, build_single_stock_export_html
from ui.theme import apply_plotly_theme, route_href


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sample_figure(title: str) -> go.Figure:
    fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[1.0, 1.1, 1.05], mode="lines", name=title)])
    fig.update_layout(title=title)
    return fig


def test_single_stock_export_html_uses_w8_site_shell() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "open": [10.0, 10.5, 10.7],
            "high": [10.8, 10.9, 11.0],
            "low": [9.8, 10.2, 10.6],
            "close": [10.4, 10.8, 10.9],
            "volume": [1000, 1200, 1400],
        }
    )
    test_df = pd.DataFrame(
        {
            "strategy_equity": [1.0, 1.02],
            "buy_hold_equity": [1.0, 1.01],
            "strategy_return": [0.0, 0.02],
        }
    )
    model_payload = {
        "当前 · SM": {
            "short_label": "当前 · SM",
            "color": "#ba7349",
            "eval": {
                "cumret": 0.12,
                "annret": 0.18,
                "maxdd": -0.08,
                "sharpe": 1.42,
                "winrate": 0.57,
                "pnl_ratio": 1.31,
            },
        }
    }

    html = build_single_stock_export_html(
        title="单股策略分析 - AAPL",
        symbol="AAPL",
        df=df,
        test_df=test_df,
        model_payload=model_payload,
        active_models=["当前 · SM"],
        candle=_sample_figure("candle"),
        ind_fig=_sample_figure("indicator"),
        score_fig=_sample_figure("score"),
        equity_fig=_sample_figure("equity"),
        signal_fig=_sample_figure("signal"),
        suggestion="继续观察",
        indicator_title="指标小图",
        include_date=True,
        language="zh",
        theme="dark",
    )

    assert 'data-theme="dark"' in html
    assert 'class="export-hero"' in html
    assert "模型摘要表" in html
    assert "图表结果区" in html
    assert "single-candle-chart" in html
    assert "@media (max-width: 980px)" in html


def test_multi_stock_export_html_contains_detail_table_and_strategy_surface() -> None:
    stock_data_dict = {
        "AAPL": pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [100.0]}),
        "NVDA": pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [200.0]}),
    }
    comparison_stats = [
        {
            "symbol": "AAPL",
            "display_name": "Apple",
            "start_price": 100.0,
            "latest_price": 110.0,
            "total_return": 0.10,
            "annualized_return": 0.12,
            "high_price": 112.0,
            "low_price": 98.0,
            "data_days": 120,
        },
        {
            "symbol": "NVDA",
            "display_name": "NVIDIA",
            "start_price": 200.0,
            "latest_price": 240.0,
            "total_return": 0.20,
            "annualized_return": 0.24,
            "high_price": 245.0,
            "low_price": 190.0,
            "data_days": 120,
        },
    ]
    portfolio_result = {
        "fig": _sample_figure("portfolio"),
        "weights": {"AAPL": 0.4, "NVDA": 0.6},
        "individual_results": {
            "AAPL": {"total_return": 0.11, "sharpe": 1.2, "max_dd": -0.09},
            "NVDA": {"total_return": 0.23, "sharpe": 1.6, "max_dd": -0.12},
        },
        "port_total_return": 0.18,
        "port_sharpe": 1.48,
        "port_max_dd": -0.10,
        "bh_total_return": 0.15,
        "bh_sharpe": 1.22,
        "bh_max_dd": -0.11,
    }

    html = build_multi_stock_export_html(
        title="多股票对比分析",
        compare_stocks=["AAPL", "NVDA"],
        stock_data_dict=stock_data_dict,
        comparison_stats=comparison_stats,
        comparison_fig=_sample_figure("comparison"),
        rs_fig=_sample_figure("rs"),
        risk_return_fig=_sample_figure("risk_return"),
        factor_score_fig=_sample_figure("factor_score"),
        corr_fig=_sample_figure("corr"),
        periodic_heatmap_fig=_sample_figure("heatmap"),
        portfolio_result=portfolio_result,
        include_date=True,
        language="en",
        theme="light",
    )

    assert 'data-theme="light"' in html
    assert "Multi-stock overview" in html
    assert "Detailed comparison table" in html
    assert "Portfolio simulation" in html
    assert "multi-portfolio-chart" in html
    assert "Strategy return" in html


def test_public_route_contract_remains_on_strategy_base_path() -> None:
    config = tomllib.loads((REPO_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["baseUrlPath"] == "strategy"
    assert route_href("", language="en") == "/strategy?lang=en"
    assert route_href("stock-analysis", language="en") == "/strategy/stock-analysis?lang=en"
    assert route_href("stocks-analysis", language="zh") == "/strategy/stocks-analysis?lang=zh"
    assert (
        route_href("final-report", language="zh", query={"section": "section-2-models"})
        == "/strategy/final-report?lang=zh&section=section-2-models"
    )

    tree = ast.parse((REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    route_paths: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "Page":
            continue
        for keyword in node.keywords:
            if keyword.arg == "url_path" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                route_paths.add(keyword.value.value)

    assert {"stock-analysis", "stocks-analysis"}.issubset(route_paths)


def test_route_href_preserves_an_active_workspace_token(monkeypatch) -> None:
    import ui.theme as theme

    workspace_id = "a" * 32
    fake_st = type("FakeStreamlit", (), {"session_state": {"_strategy_workspace_id": workspace_id}, "query_params": {}})()
    monkeypatch.setattr(theme, "st", fake_st)
    monkeypatch.setattr(theme, "get_ui_language", lambda: "en")

    assert theme.route_href("stock-analysis") == f"/strategy/stock-analysis?lang=en&ws={workspace_id}"


def test_apply_plotly_theme_handles_array_trace_text() -> None:
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=[[0.1, -0.2], [0.3, 0.4]],
                text=np.array([["A", "B"], ["C", "D"]], dtype=object),
                texttemplate="%{text}",
            )
        ]
    )

    themed = apply_plotly_theme(fig)

    assert themed is fig
    assert themed.data[0].text is not None
