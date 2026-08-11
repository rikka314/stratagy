from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_multi_stock_header_is_compact_collapsible() -> None:
    source = (PROJECT_ROOT / "ui" / "multi_stock.py").read_text(encoding="utf-8")

    assert 'MULTI_HEADER_DETAILS_KEY = "multi_stock_header_details_expanded"' in source
    assert 'key="multi-stock-hero-compact"' in source
    assert 'key="multi-stock-hero-toggle"' in source
    assert 'class="analysis-hero-details"' in source


def test_multi_stock_navigation_and_summary_match_the_compact_analysis_layout() -> None:
    source = (PROJECT_ROOT / "ui" / "multi_stock.py").read_text(encoding="utf-8")
    theme_source = (PROJECT_ROOT / "ui" / "theme.py").read_text(encoding="utf-8")

    assert 'key="multi-stock-section-nav"' in source
    assert 'key="multi-stock-edit-popover"' in source
    assert 'with st.expander(tr("portfolio.removeStock"), expanded=False):' in source
    assert 'class="analysis-stock-list"' in source
    assert 'class="analysis-stock-row"' in source
    assert 'key="multi-stock-chart-switch"' in source
    assert 'figure.layout.title = None' in source
    assert "顶部先给出股票池摘要和明细表" not in source
    assert '<div class="surface-kicker">{tr("panel.basicInfo")}</div>' not in source
    assert 'div[class*="st-key-multi-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"])' in theme_source
    assert '''div[class*="st-key-multi-stock-section-nav"] [data-testid="stButtonGroup"] [role="radiogroup"] {
  display: flex !important;
  width: 100% !important;
  max-width: none !important;
  gap: 0 !important;
}''' in theme_source
    assert '''div[class*="st-key-multi-stock-section-nav"] :is([data-testid="stSegmentedControl"], [data-testid="stButtonGroup"]) button {
  flex: 1 1 0;
  min-width: 0;
  min-height: 2.25rem;''' in theme_source
    assert 'div[class*="st-key-multi-stock-edit-popover"] .stPopover button' in theme_source
    assert 'div[class*="st-key-multi-stock-chart-switch"] [data-testid="stRadioOption"]' in theme_source
    assert '"st-key-multi-stock-section-nav",' in theme_source
