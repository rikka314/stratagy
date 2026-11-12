from __future__ import annotations

import importlib
from types import SimpleNamespace
from pathlib import Path

import pytest

from ui import theme


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeLoadingSlot:
    def __init__(self) -> None:
        self.empty_calls = 0

    def empty(self) -> None:
        self.empty_calls += 1


def test_analysis_route_replaces_entry_without_restore_banner_or_unconditional_marker() -> None:
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    workspace_source = (PROJECT_ROOT / "ui" / "workspace.py").read_text(encoding="utf-8")

    assert "render_workspace_restore_notice" not in app_source
    assert "def render_workspace_restore_notice" not in workspace_source
    assert "analysis-render-pending" not in app_source
    assert "entry_slot = st.empty()" in app_source
    assert "entry_slot.empty()" in app_source


def test_multi_data_load_owns_one_loading_path() -> None:
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    multi_source = (PROJECT_ROOT / "ui" / "multi_stock.py").read_text(encoding="utf-8")

    render_position = app_source.index("render_multi_stock_page(")
    clear_position = app_source.index("_clear_route_analysis_loading()", render_position)
    assert clear_position > render_position
    assert 'st.spinner(tr("data.loadingComparison"))' not in multi_source
    assert 'st.container(key="multi-stock-data-load-surface")' not in multi_source
    assert "show_spinner=False" in multi_source


def test_multi_cache_miss_renders_the_shared_loading_marker_when_route_is_not_loading() -> None:
    multi_source = (PROJECT_ROOT / "ui" / "multi_stock.py").read_text(encoding="utf-8")

    assert 'cache_miss = analysis_cache.get("data_signature") != data_signature' in multi_source
    assert "if not bool(st.session_state.get(ROUTE_ANALYSIS_LOADING_KEY, False))" in multi_source
    assert "render_route_loading_marker((compare_stocks or [\"stocks\"])[0])" in multi_source
    assert "clear_route_loading_slot(local_loading_slot)" in multi_source


def test_route_loading_guard_clears_state_and_placeholders_on_ordinary_error(monkeypatch) -> None:
    monkeypatch.setenv("STRATAGY_PERF_IMPORT_PROBE", "1")
    app = importlib.import_module("app")
    fake_st = SimpleNamespace(session_state={app.ROUTE_ANALYSIS_LOADING_KEY: True})
    monkeypatch.setattr(app, "st", fake_st)
    loading_slot = _FakeLoadingSlot()

    @app._route_analysis_loading_error_safe
    def failing_render() -> None:
        app.register_route_loading_slot(loading_slot)
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError, match="render failed"):
        failing_render()

    assert fake_st.session_state[app.ROUTE_ANALYSIS_LOADING_KEY] is False
    assert loading_slot.empty_calls == 1


def test_route_loading_guard_does_not_intercept_streamlit_control_flow(monkeypatch) -> None:
    monkeypatch.setenv("STRATAGY_PERF_IMPORT_PROBE", "1")
    app = importlib.import_module("app")
    fake_st = SimpleNamespace(session_state={app.ROUTE_ANALYSIS_LOADING_KEY: True})
    monkeypatch.setattr(app, "st", fake_st)
    loading_slot = _FakeLoadingSlot()

    class _RerunSignal(BaseException):
        pass

    @app._route_analysis_loading_error_safe
    def rerun_render() -> None:
        app.register_route_loading_slot(loading_slot)
        raise _RerunSignal

    with pytest.raises(_RerunSignal):
        rerun_render()

    assert fake_st.session_state[app.ROUTE_ANALYSIS_LOADING_KEY] is True
    assert loading_slot.empty_calls == 0
    theme.reset_route_loading_slots()


def test_route_loading_slot_registry_is_identity_safe_and_clears_each_slot_once() -> None:
    outer_slot = _FakeLoadingSlot()
    local_slot = _FakeLoadingSlot()
    theme.reset_route_loading_slots()

    theme.register_route_loading_slot(outer_slot)
    theme.register_route_loading_slot(outer_slot)
    theme.register_route_loading_slot(local_slot)
    theme.clear_route_loading_slot(local_slot)
    theme.clear_route_loading_slots()

    assert outer_slot.empty_calls == 1
    assert local_slot.empty_calls == 1


def test_ordinary_reruns_keep_stale_tree_visible_and_noninteractive() -> None:
    theme_source = (PROJECT_ROOT / "ui" / "theme.py").read_text(encoding="utf-8")

    stale_rule = theme_source.split(
        '[data-testid="stElementContainer"][data-stale="true"] {',
        maxsplit=1,
    )[1].split("}", maxsplit=1)[0]

    assert "opacity: 1 !important;" in stale_rule
    assert "visibility: visible !important;" in stale_rule
    assert "transition: none !important;" in stale_rule
    assert "pointer-events: none !important;" in stale_rule
    assert "display: none" not in stale_rule
    assert 'div[class*="st-key-single-stock-basic-section"]:has(' not in theme_source
    assert 'div[class*="st-key-single-stock-strategy-section"]:has(' not in theme_source
    assert 'body:has(.route-loading-state) div[class*="st-key-single-entry-split"]' in theme_source
    assert 'body:has(.analysis-render-pending)' not in theme_source


def test_in_analysis_stock_switch_reuses_route_loading_state() -> None:
    single_source = (PROJECT_ROOT / "ui" / "single_stock.py").read_text(encoding="utf-8")
    switch_source = single_source.split("def _switch_single_stock_symbol", maxsplit=1)[1].split(
        "def _render_basic_info_section", maxsplit=1
    )[0]

    assert 'ROUTE_ANALYSIS_LOADING_KEY = "_route_analysis_loading"' in single_source
    assert "st.session_state[ROUTE_ANALYSIS_LOADING_KEY] = True" in switch_source


def test_in_analysis_multi_stock_edits_reuse_route_loading_state() -> None:
    multi_source = (PROJECT_ROOT / "ui" / "multi_stock.py").read_text(encoding="utf-8")
    remove_source = multi_source.split("def _remove_multi_route_item", maxsplit=1)[1].split(
        "def _add_multi_route_symbol", maxsplit=1
    )[0]
    add_source = multi_source.split("def _add_multi_route_symbol", maxsplit=1)[1].split(
        "def _get_multi_strategy_workspace", maxsplit=1
    )[0]

    assert 'ROUTE_ANALYSIS_LOADING_KEY = "_route_analysis_loading"' in multi_source
    assert "st.session_state[ROUTE_ANALYSIS_LOADING_KEY] = True" in remove_source
    assert "st.session_state[ROUTE_ANALYSIS_LOADING_KEY] = True" in add_source
