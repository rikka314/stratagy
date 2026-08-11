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
        st.session_state[WORKSPACE_MARKER_KEY] = _snapshot_marker(_snapshot_payload())
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
        payload = _snapshot_payload()
        marker = _snapshot_marker(payload)
        if marker == st.session_state.get(WORKSPACE_MARKER_KEY):
            return False
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
            if isinstance(key, str):
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


def _snapshot_marker(payload: dict[str, Any]) -> str:
    """Use lightweight result identities so ordinary reruns avoid re-pickling artifacts."""
    single_workspace = payload.get("single_workspace", {})
    multi_workspace = payload.get("multi_workspace", {})
    current = single_workspace.get("current_artifact") if isinstance(single_workspace, dict) else None
    saved = single_workspace.get("saved_artifacts", []) if isinstance(single_workspace, dict) else []
    marker = {
        "routes": _route_marker(payload.get("routes", {})),
        "widgets": payload.get("widget_state", {}),
        "single": {
            "context_key": single_workspace.get("context_key") if isinstance(single_workspace, dict) else None,
            "current_id": getattr(current, "id", None),
            "current_signature": getattr(current, "request_signature", None),
            "saved_ids": [getattr(item, "id", None) for item in saved],
        },
        "multi": {
            "signature": multi_workspace.get("signature") if isinstance(multi_workspace, dict) else None,
            "optimization_signature": multi_workspace.get("optimization_signature") if isinstance(multi_workspace, dict) else None,
            "portfolio_result_identity": id(multi_workspace.get("portfolio_result")) if isinstance(multi_workspace, dict) and multi_workspace.get("portfolio_result") is not None else None,
            "optimization_result_identity": id(multi_workspace.get("optimization_result")) if isinstance(multi_workspace, dict) and multi_workspace.get("optimization_result") is not None else None,
        },
    }
    return hashlib.sha256(pickle.dumps(marker, protocol=pickle.HIGHEST_PROTOCOL)).hexdigest()


def _route_marker(routes: object) -> object:
    if not isinstance(routes, dict):
        return routes
    route_copy = copy.deepcopy(routes)
    for route_name in ("single", "multi"):
        state = route_copy.get(route_name)
        if not isinstance(state, dict):
            continue
        if isinstance(state.get("uploaded_bytes"), (bytes, bytearray)):
            raw = bytes(state["uploaded_bytes"])
            state["uploaded_bytes"] = ("bytes", len(raw), hashlib.sha256(raw).hexdigest())
        for item in state.get("uploads", []):
            if isinstance(item, dict) and isinstance(item.get("bytes"), (bytes, bytearray)):
                raw = bytes(item["bytes"])
                item["bytes"] = ("bytes", len(raw), hashlib.sha256(raw).hexdigest())
    return route_copy
