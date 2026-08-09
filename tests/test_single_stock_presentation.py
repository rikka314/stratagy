from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from core.visualization import _hide_invalid_legend_entries
from ui.single_stock import _localized_stock_names, _strategy_module_help_markup
from ui.theme import apply_plotly_theme


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_single_stock_names_follow_active_language_order() -> None:
    assert _localized_stock_names("SKHY", "US", "zh") == ("SK海力士", "SK hynix Inc.")
    assert _localized_stock_names("SKHY", "US", "en") == ("SK hynix Inc.", "SK海力士")


def test_single_stock_basic_section_omits_removed_helper_copy_and_identity_chips() -> None:
    source = (PROJECT_ROOT / "ui" / "single_stock.py").read_text(encoding="utf-8")

    assert "左侧用文字快速交代当前标的状态" not in source
    assert "补足左下摘要区的空白" not in source
    assert '<span class="analysis-chart-chip">标的 ' not in source
    assert '<span class="analysis-chart-chip">显示名 ' not in source


def test_single_stock_header_is_compact_collapsible_and_chart_meta_is_removed() -> None:
    source = (PROJECT_ROOT / "ui" / "single_stock.py").read_text(encoding="utf-8")

    assert 'HEADER_DETAILS_KEY = "single_stock_header_details_expanded"' in source
    assert 'key="single-stock-hero-compact"' in source
    assert 'class="analysis-hero-details"' in source
    assert 'key="single-stock-section-nav"' in source
    assert "最新收盘 {html.escape(latest_close)}" not in source
    assert "EMA 快线 {html.escape(ema_fast_value)}" not in source
    assert "EMA 慢线 {html.escape(ema_slow_value)}" not in source


def test_single_stock_navigation_uses_compact_segmented_control_and_right_aligned_switch() -> None:
    theme_source = (PROJECT_ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    source = (PROJECT_ROOT / "ui" / "single_stock.py").read_text(encoding="utf-8")

    assert 'div[class*="st-key-single-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"])' in theme_source
    assert 'div[class*="st-key-single-stock-switch-popover"] .stPopover button' in theme_source
    assert '"st-key-single-stock-section-nav",' in theme_source
    assert 'div[class*="st-key-single-stock-section-nav"] div[class*="st-key-single_stock_analysis_section"]' in theme_source
    assert 'div[class*="st-key-single-stock-switch-popover"] > [data-testid="stLayoutWrapper"]' in theme_source
    assert "align-items: flex-end;" in theme_source
    assert "animation: analysis-detail-slide-down" in theme_source
    assert "help=details_label" not in source


def test_strategy_workbench_omits_redundant_copy_and_keeps_contextual_help() -> None:
    source = (PROJECT_ROOT / "ui" / "single_stock.py").read_text(encoding="utf-8")

    assert 'tr("single.strategy.workspaceCopy")' not in source
    assert 'tr("single.strategy.controlCopy")' not in source
    assert 'tr("single.strategy.entryCopy")' not in source
    assert 'tr("single.strategy.configCopy")' not in source
    assert 'tr("single.strategy.libraryCopy")' not in source
    assert 'tr("strategy.generation_flow")' not in source
    assert 'tr("strategy.workflowSteps")' not in source
    assert 'tr("single.strategy.resultPlaceholderCopy")' not in source
    assert 'tr("single.strategy.workflowCopy")' not in source
    assert 'tr("strategy.configurationHint")' not in source
    assert 'tr("action.generateArtifact.note")' not in source
    assert "single-stock-strategy-help-trigger" in source
    assert 'st.markdown(f"**{title}**", help=tooltip, width="content")' in source
    assert "strategy-tooltip-content" not in source


def test_strategy_empty_board_uses_quiet_background_wordmark() -> None:
    source = (PROJECT_ROOT / "ui" / "single_stock.py").read_text(encoding="utf-8")
    theme_source = (PROJECT_ROOT / "ui" / "theme.py").read_text(encoding="utf-8")

    assert 'tr("single.strategy.emptyBackdrop")' in source
    assert "strategy-result-empty-mark" not in source
    assert "border: 1px dashed var(--surface-line-strong);" not in theme_source
    assert ".strategy-result-empty-wordmark" in theme_source


def test_strategy_help_dialog_explains_paths_and_tradeoffs_bilingually() -> None:
    zh_markup = _strategy_module_help_markup("zh")
    en_markup = _strategy_module_help_markup("en")

    for label in ("Naive Baseline", "Search · FSM", "Adaptive Regime", "News / ML 增强"):
        assert label in zh_markup
    for label in ("Naive Baseline", "Search · FSM", "Adaptive Regime", "News / ML add-ons"):
        assert label in en_markup
    assert "至少勾选两条" in zh_markup
    assert "Select at least two" in en_markup


def test_strategy_panels_use_equal_height_scrollable_desktop_workspace() -> None:
    theme_source = (PROJECT_ROOT / "ui" / "theme.py").read_text(encoding="utf-8")

    assert 'div[class*="st-key-single-stock-strategy-control-panel"]' in theme_source
    assert 'div[class*="st-key-single-stock-strategy-result-board"]' in theme_source
    assert "flex: 0 0 clamp(44rem, calc(100vh - 5.5rem), 68rem) !important;" in theme_source
    assert "height: clamp(44rem, calc(100vh - 5.5rem), 68rem);" in theme_source
    assert "max-height: clamp(44rem, calc(100vh - 5.5rem), 68rem);" in theme_source
    assert "overflow-y: auto;" in theme_source
    assert ".strategy-result-empty" in theme_source


def test_invalid_plotly_legend_names_are_hidden() -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1], y=[1], name=None))
    fig.add_trace(go.Scatter(x=[1], y=[2], name="undefined"))
    fig.add_trace(go.Scatter(x=[1], y=[3], name="MACD"))
    fig.add_shape(type="line", x0=0, x1=1, y0=0, y1=1, name="undefined", showlegend=True)

    _hide_invalid_legend_entries(fig)

    assert fig.data[0].showlegend is False
    assert fig.data[1].showlegend is False
    assert fig.data[2].showlegend is None
    assert fig.layout.shapes[0].showlegend is False


def test_plotly_theme_does_not_materialize_an_empty_chart_title() -> None:
    fig = go.Figure(data=[go.Scatter(x=[1], y=[1], name="MACD")])

    apply_plotly_theme(fig)

    assert fig.layout.title.to_plotly_json() == {}
