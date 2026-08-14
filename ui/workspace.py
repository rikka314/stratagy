"""Session-state hydration and checkpoints for temporary analysis workspaces."""

from __future__ import annotations

import copy
import hashlib
import pickle
from time import perf_counter
from typing import Any

import streamlit as st

from core.workspace_cache import WorkspaceCacheError, WorkspaceSnapshotStore, is_valid_workspace_id
from core.perf import emit_performance_event
from ui.i18n import tr


WORKSPACE_QUERY_KEY = "ws"
WORKSPACE_SESSION_ID_KEY = "_strategy_workspace_id"
WORKSPACE_HYDRATED_ID_KEY = "_strategy_workspace_hydrated_id"
WORKSPACE_MARKER_KEY = "_strategy_workspace_marker"
WORKSPACE_RESTORED_NOTICE_KEY = "_strategy_workspace_restored_notice"

SINGLE_ROUTE_STATE_KEY = "route_single_state"
MULTI_ROUTE_STATE_KEY = "route_multi_state"
SINGLE_WORKSPACE_KEY = "single_stock_strategy_workspace"
MULTI_WORKSPACE_KEY = "multi_stock_strategy_workspace"

_EXCLUDED_KEYS = {
    "single_stock_stage_cache",
    "single_stock_stage_cache_lru",
    "single_stock_display_cache",
    "multi_stock_analysis_cache",
    # These two objects have dedicated, portable snapshot branches below.  Do
    # not also collect them through the broad ``single_stock_`` /
    # ``multi_stock_`` widget prefixes: that duplicates large DataFrames and
    # Plotly figures in a checkpoint, and defeats the lightweight marker.
    SINGLE_WORKSPACE_KEY,
    MULTI_WORKSPACE_KEY,
    WORKSPACE_SESSION_ID_KEY,
    WORKSPACE_HYDRATED_ID_KEY,
    WORKSPACE_MARKER_KEY,
    WORKSPACE_RESTORED_NOTICE_KEY,
}
_DIRECT_KEYS = {
    "market",
    "adjust",
    "compare_stocks",
    "entry_threshold",
    "exit_threshold",
    "stop_loss_mult",
    "take_profit_mult",
    "weight_bb",
    "weight_obv",
    "weight_volume",
    "weight_price",
    "weight_drawdown",
    "momentum_short",
    "momentum_long",
    "score_lookback",
    "score_mid_pct",
    "score_high_pct",
    "weight_mom_short",
    "weight_mom_long",
    "weight_macd",
    "weight_rsi",
    "weight_vol",
    "entry_min_signals",
    "exit_min_signals",
}
_PERSISTED_PREFIXES = (
    "sidebar_",
    "compare_stocks_selector_",
    "single_stock_",
    "multi_stock_",
    "search_adj_",
    "multi_adj_",
    "portfolio_",
    "strategy_preset_",
    "ema_",
    "macd_",
    "rsi_",
    "adx_",
    "atr_",
    "bb_",
    "indicator_",
    "feedback_",
)
# Streamlit action widgets are write-protected: restoring their boolean
# value through ``st.session_state`` before the widget is created raises
# ``StreamlitValueAssignmentNotAllowedError``.  Keep durable controls (text,
# selectbox, slider, segmented control, etc.) but never persist one-shot
# button state, including dynamically keyed list actions.
_NON_PERSISTED_WIDGET_KEYS = {
    "home_stock_market_us",
    "home_stock_market_cn",
    "home_stock_next",
    "single_entry_upload_btn",
    "single_entry_refresh_market_context",
    "single_stock_header_details_toggle",
    "single_stock_strategy_help",
    "single_stock_generate_strategy",
    "single_stock_save_current_artifact",
    "single_stock_switch_direct",
    "single_export_btn",
    "multi_entry_refresh_market_context",
    "multi_stock_header_details_toggle",
    "multi_stock_generate_strategy",
    "multi_stock_add_direct",
    "btn_optimize_portfolio",
}
_NON_PERSISTED_WIDGET_PREFIXES = (
    "single_entry_rec_",
    "single_stock_switch_",
    "multi_entry_rec_",
    "multi_entry_remove_",
    "multi_stock_add_",
    "multi_stock_remove_",
)


def _store() -> WorkspaceSnapshotStore:
    return WorkspaceSnapshotStore()


def _query_value() -> str | None:
    try:
        value = st.query_params.get(WORKSPACE_QUERY_KEY)
    except (AttributeError, KeyError, TypeError):
        return None
    return str(value) if is_valid_workspace_id(value) else None


def _set_query_value(workspace_id: str) -> None:
    try:
        st.query_params[WORKSPACE_QUERY_KEY] = workspace_id
    except (AttributeError, KeyError, TypeError):
        pass


def current_workspace_id() -> str | None:
    value = st.session_state.get(WORKSPACE_SESSION_ID_KEY)
    return str(value) if is_valid_workspace_id(value) else _query_value()


def ensure_workspace_session() -> str:
    """Hydrate an URL workspace once, or attach a new opaque workspace id."""
    requested_id = _query_value()
    hydrated_id = st.session_state.get(WORKSPACE_HYDRATED_ID_KEY)
    if requested_id and requested_id != hydrated_id:
        restore_started_at = perf_counter()
        payload = _store().load(requested_id)
        if payload is not None:
            _apply_snapshot(payload)
            st.session_state[WORKSPACE_RESTORED_NOTICE_KEY] = True
        st.session_state[WORKSPACE_SESSION_ID_KEY] = requested_id
        st.session_state[WORKSPACE_HYDRATED_ID_KEY] = requested_id
        st.session_state[WORKSPACE_MARKER_KEY] = _current_workspace_marker()
        emit_performance_event(
            "workspace", "restore", (perf_counter() - restore_started_at) * 1000,
            cache="hit" if payload is not None else "miss",
        )
        return requested_id

    existing_id = current_workspace_id()
    if existing_id:
        st.session_state[WORKSPACE_SESSION_ID_KEY] = existing_id
        st.session_state[WORKSPACE_HYDRATED_ID_KEY] = existing_id
        return existing_id

    workspace_id = _store().create_workspace_id()
    st.session_state[WORKSPACE_SESSION_ID_KEY] = workspace_id
    st.session_state[WORKSPACE_HYDRATED_ID_KEY] = workspace_id
    _set_query_value(workspace_id)
    return workspace_id


def checkpoint_workspace() -> bool:
    """Persist only if route, widgets, or completed analysis results changed."""
    workspace_id = ensure_workspace_session()
    checkpoint_started_at = perf_counter()
    try:
        # Compute the compact state marker before building a portable snapshot.
        # The latter deep-copies result series, so doing it first prevents every
        # ordinary rerun from serializing completed analyses again.
        marker = _current_workspace_marker()
        if marker == st.session_state.get(WORKSPACE_MARKER_KEY):
            return False
        payload = _snapshot_payload()
        _store().save(workspace_id, payload)
    except Exception:
        emit_performance_event(
            "workspace", "checkpoint", (perf_counter() - checkpoint_started_at) * 1000,
            cache="error",
        )
        return False
    st.session_state[WORKSPACE_MARKER_KEY] = marker
    emit_performance_event(
        "workspace", "checkpoint", (perf_counter() - checkpoint_started_at) * 1000,
        cache="write",
    )
    return True


def clear_workspace_session() -> None:
    workspace_id = current_workspace_id()
    if workspace_id:
        _store().clear(workspace_id)
    for key in list(st.session_state):
        if key in _EXCLUDED_KEYS or key in _DIRECT_KEYS or key in {SINGLE_ROUTE_STATE_KEY, MULTI_ROUTE_STATE_KEY, SINGLE_WORKSPACE_KEY, MULTI_WORKSPACE_KEY}:
            st.session_state.pop(key, None)
        elif key.startswith(_PERSISTED_PREFIXES):
            st.session_state.pop(key, None)
    try:
        del st.query_params[WORKSPACE_QUERY_KEY]
    except (AttributeError, KeyError, TypeError):
        pass


def render_workspace_restore_notice() -> None:
    if st.session_state.pop(WORKSPACE_RESTORED_NOTICE_KEY, False):
        st.info(tr("workspace.restoredNotice"))


def render_workspace_sidebar_actions() -> None:
    """Render a reset action before the normal sidebar widgets are created."""
    with st.sidebar:
        st.caption(tr("workspace.temporaryNotice"))
        st.button(
            tr("workspace.startFresh"),
            key="workspace_start_fresh",
            use_container_width=True,
            on_click=clear_workspace_session,
        )


def _snapshot_payload() -> dict[str, Any]:
    single_workspace = st.session_state.get(SINGLE_WORKSPACE_KEY, {})
    multi_workspace = st.session_state.get(MULTI_WORKSPACE_KEY, {})
    return {
        "routes": {
            "single": copy.deepcopy(st.session_state.get(SINGLE_ROUTE_STATE_KEY, {})),
            "multi": copy.deepcopy(st.session_state.get(MULTI_ROUTE_STATE_KEY, {})),
        },
        "widget_state": _collect_widget_state(),
        "single_workspace": {
            "context_key": single_workspace.get("context_key"),
            "current_artifact": single_workspace.get("current_artifact"),
            "saved_artifacts": copy.deepcopy(single_workspace.get("saved_artifacts", [])),
        }
        if isinstance(single_workspace, dict)
        else {},
        "multi_workspace": {
            "signature": multi_workspace.get("signature"),
            "portfolio_result": _portable_portfolio_result(multi_workspace.get("portfolio_result")),
            "optimization_signature": multi_workspace.get("optimization_signature"),
            "optimization_result": multi_workspace.get("optimization_result"),
        }
        if isinstance(multi_workspace, dict)
        else {},
    }


def _collect_widget_state() -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in st.session_state.items():
        if not isinstance(key, str) or key in _EXCLUDED_KEYS:
            continue
        if _is_non_persisted_widget_key(key):
            continue
        if key in _DIRECT_KEYS or key.startswith(_PERSISTED_PREFIXES):
            try:
                pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            except (pickle.PickleError, TypeError, ValueError):
                continue
            values[key] = copy.deepcopy(value)
    return values


def _portable_portfolio_result(value: object) -> object:
    """Figures are regenerated from equity and return series after hydration."""
    if not isinstance(value, dict):
        return value
    portable = copy.deepcopy(value)
    portable.pop("fig", None)
    return portable


def _apply_snapshot(payload: dict[str, Any]) -> None:
    widget_state = payload.get("widget_state", {})
    if isinstance(widget_state, dict):
        for key, value in widget_state.items():
            if isinstance(key, str) and not _is_non_persisted_widget_key(key):
                st.session_state[key] = value

    routes = payload.get("routes", {})
    if isinstance(routes, dict):
        for route_name, state_key in (("single", SINGLE_ROUTE_STATE_KEY), ("multi", MULTI_ROUTE_STATE_KEY)):
            route_state = routes.get(route_name)
            if isinstance(route_state, dict):
                st.session_state[state_key] = route_state

    single_workspace = payload.get("single_workspace")
    if isinstance(single_workspace, dict):
        st.session_state[SINGLE_WORKSPACE_KEY] = {
            "context_key": single_workspace.get("context_key"),
            "current_artifact": single_workspace.get("current_artifact"),
            "saved_artifacts": list(single_workspace.get("saved_artifacts", [])),
        }

    multi_workspace = payload.get("multi_workspace")
    if isinstance(multi_workspace, dict):
        st.session_state[MULTI_WORKSPACE_KEY] = {
            "signature": multi_workspace.get("signature"),
            "portfolio_result": multi_workspace.get("portfolio_result"),
            "optimization_signature": multi_workspace.get("optimization_signature"),
            "optimization_result": multi_workspace.get("optimization_result"),
            "heatmap_cache": {},
        }


def _current_workspace_marker() -> str:
    """Build a marker from live state without copying result payloads."""
    return _workspace_marker(
        routes={
            "single": st.session_state.get(SINGLE_ROUTE_STATE_KEY, {}),
            "multi": st.session_state.get(MULTI_ROUTE_STATE_KEY, {}),
        },
        widget_state=_collect_widget_state(),
        single_workspace=st.session_state.get(SINGLE_WORKSPACE_KEY, {}),
        multi_workspace=st.session_state.get(MULTI_WORKSPACE_KEY, {}),
    )


def _is_non_persisted_widget_key(key: str) -> bool:
    if key == "single_stock_switch_query":
        return False
    return key in _NON_PERSISTED_WIDGET_KEYS or key.startswith(_NON_PERSISTED_WIDGET_PREFIXES)


def _snapshot_marker(payload: dict[str, Any]) -> str:
    """Return the equivalent lightweight marker for a serialized payload."""
    return _workspace_marker(
        routes=payload.get("routes", {}),
        widget_state=payload.get("widget_state", {}),
        single_workspace=payload.get("single_workspace", {}),
        multi_workspace=payload.get("multi_workspace", {}),
    )


def _workspace_marker(
    *,
    routes: object,
    widget_state: object,
    single_workspace: object,
    multi_workspace: object,
) -> str:
    """Hash only state that can alter a persisted workspace result."""
    current = single_workspace.get("current_artifact") if isinstance(single_workspace, dict) else None
    saved = single_workspace.get("saved_artifacts", []) if isinstance(single_workspace, dict) else []
    marker = {
        "routes": _route_marker(routes),
        "widgets": widget_state,
        "single": {
            "context_key": single_workspace.get("context_key") if isinstance(single_workspace, dict) else None,
            "current_id": getattr(current, "id", None),
            "current_signature": getattr(current, "request_signature", None),
            "saved_ids": [getattr(item, "id", None) for item in saved],
        },
        "multi": {
            "signature": multi_workspace.get("signature") if isinstance(multi_workspace, dict) else None,
            "optimization_signature": multi_workspace.get("optimization_signature") if isinstance(multi_workspace, dict) else None,
            "portfolio_result": _portfolio_result_marker(
                multi_workspace.get("portfolio_result") if isinstance(multi_workspace, dict) else None
            ),
            "optimization_result_identity": (
                id(multi_workspace.get("optimization_result"))
                if isinstance(multi_workspace, dict)
                and multi_workspace.get("optimization_result") is not None
                else None
            ),
        },
    }
    return hashlib.sha256(pickle.dumps(marker, protocol=pickle.HIGHEST_PROTOCOL)).hexdigest()


def _portfolio_result_marker(value: object) -> object:
    """Return a stable, compact identity for a persisted portfolio result.

    ``_portable_portfolio_result`` deep-copies the result to remove its
    figure.  Using ``id()`` on that copy made every ordinary rerun look like a
    new result and forced another disk checkpoint.  Keep only scalar outcome
    fields that change when a portfolio result materially changes.
    """
    if not isinstance(value, dict):
        return None

    metrics = tuple(
        (key, value.get(key))
        for key in (
            "port_total_return",
            "port_sharpe",
            "port_max_dd",
            "bh_total_return",
            "bh_sharpe",
            "bh_max_dd",
        )
    )
    weights = value.get("weights")
    weight_marker = (
        tuple(sorted((str(symbol), weight) for symbol, weight in weights.items()))
        if isinstance(weights, dict)
        else None
    )
    individual_results = value.get("individual_results")
    individual_marker = (
        tuple(
            sorted(
                (
                    str(symbol),
                    result.get("total_return"),
                    result.get("sharpe"),
                    result.get("max_dd"),
                )
                for symbol, result in individual_results.items()
                if isinstance(result, dict)
            )
        )
        if isinstance(individual_results, dict)
        else None
    )
    return metrics, weight_marker, individual_marker


def _route_marker(routes: object) -> object:
    if not isinstance(routes, dict):
        return routes
    # Route state may contain a user-uploaded CSV of several megabytes.  A
    # marker is computed on every rerun, so a recursive deepcopy here would
    # copy the entire upload even when nothing changed.  Build a shallow,
    # schema-shaped copy and replace only byte payloads with fingerprints.
    route_marker: dict[object, object] = {}
    for route_name, route_state in routes.items():
        if not isinstance(route_state, dict):
            route_marker[route_name] = route_state
            continue
        state_marker = dict(route_state)
        raw = state_marker.get("uploaded_bytes")
        if isinstance(raw, (bytes, bytearray)):
            raw_bytes = bytes(raw)
            state_marker["uploaded_bytes"] = (
                "bytes",
                len(raw_bytes),
                hashlib.sha256(raw_bytes).hexdigest(),
            )
        uploads = state_marker.get("uploads")
        if isinstance(uploads, list):
            upload_markers: list[object] = []
            for item in uploads:
                if not isinstance(item, dict):
                    upload_markers.append(item)
                    continue
                item_marker = dict(item)
                raw_upload = item_marker.get("bytes")
                if isinstance(raw_upload, (bytes, bytearray)):
                    raw_bytes = bytes(raw_upload)
                    item_marker["bytes"] = (
                        "bytes",
                        len(raw_bytes),
                        hashlib.sha256(raw_bytes).hexdigest(),
                    )
                upload_markers.append(item_marker)
            state_marker["uploads"] = upload_markers
        route_marker[route_name] = state_marker
    return route_marker
