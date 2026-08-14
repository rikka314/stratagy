from __future__ import annotations

from pathlib import Path

import pandas as pd


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


def test_multi_stock_data_signature_tracks_upload_content_and_manual_refresh(monkeypatch) -> None:
    from ui import multi_stock
    from core.utils import MARKET_DATA_REFRESH_EPOCH_KEY

    monkeypatch.setitem(multi_stock.st.session_state, MARKET_DATA_REFRESH_EPOCH_KEY, 0)
    versions = {"AAPL": "revision:one", "MSFT": "revision:one"}
    monkeypatch.setattr(
        multi_stock,
        "market_data_cache_entry_version",
        lambda symbol, _adjust, market: versions.get(symbol),
    )
    common = {
        "market": "US",
        "adjust": "qfq",
        "compare_stocks": ["AAPL", "MSFT"],
        "start_ts": pd.Timestamp("2025-01-01"),
        "end_ts": pd.Timestamp("2026-01-01"),
    }
    first = multi_stock._build_multi_analysis_data_signature(
        **common,
        uploads=[{"symbol": "UPLOAD", "name": "same.csv", "bytes": b"close,10\n"}],
    )
    changed = multi_stock._build_multi_analysis_data_signature(
        **common,
        uploads=[{"symbol": "UPLOAD", "name": "same.csv", "bytes": b"close,11\n"}],
    )
    assert first != changed

    monkeypatch.setitem(multi_stock.st.session_state, MARKET_DATA_REFRESH_EPOCH_KEY, 1)
    refreshed = multi_stock._build_multi_analysis_data_signature(
        **common,
        uploads=[{"symbol": "UPLOAD", "name": "same.csv", "bytes": b"close,10\n"}],
    )
    assert first != refreshed

    versions["AAPL"] = "revision:two"
    background_refreshed = multi_stock._build_multi_analysis_data_signature(
        **common,
        uploads=[{"symbol": "UPLOAD", "name": "same.csv", "bytes": b"close,10\n"}],
    )
    assert refreshed != background_refreshed


def test_multi_strategy_signature_tracks_historical_data_revisions() -> None:
    from ui import multi_stock

    first = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.5, 11.5],
            "volume": [100.0, 110.0],
        }
    )
    revised = first.copy()
    revised.loc[0, "close"] = 10.25

    params = {"entry_threshold": 0.5}
    weights = {"AAPL": 1.0}
    assert multi_stock._build_multi_strategy_signature({"AAPL": first}, params, weights) != (
        multi_stock._build_multi_strategy_signature({"AAPL": revised}, params, weights)
    )
