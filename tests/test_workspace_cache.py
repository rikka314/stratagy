from __future__ import annotations

import json
import os
import threading
import time
from contextlib import nullcontext
from types import SimpleNamespace

import pandas as pd
import pytest

from core.market_cache import MarketDataCache
from core.workspace_cache import WorkspaceCacheError, WorkspaceSnapshotStore


def test_workspace_store_round_trips_upload_references(tmp_path) -> None:
    store = WorkspaceSnapshotStore(tmp_path, ttl_seconds=60)
    workspace_id = store.create_workspace_id()
    payload = {
        "routes": {
            "single": {"view": "analysis", "uploaded_name": "single.csv", "uploaded_bytes": b"single"},
            "multi": {"uploads": [{"symbol": "A", "name": "multi.csv", "bytes": b"multi"}]},
        },
        "widget_state": {"single_stock_analysis_section": "strategy"},
        "single_workspace": {"current_artifact": SimpleNamespace(id="artifact-1")},
    }

    meta = store.save(workspace_id, payload)
    restored = store.load(workspace_id)

    assert meta.size_bytes > 0
    assert restored is not None
    assert restored["routes"]["single"]["uploaded_bytes"] == b"single"
    assert restored["routes"]["multi"]["uploads"][0]["bytes"] == b"multi"
    assert restored["single_workspace"]["current_artifact"].id == "artifact-1"
    assert (tmp_path / workspace_id / "uploads").exists()


def test_workspace_store_expires_corrupts_safely_and_enforces_size(tmp_path) -> None:
    clock = [100.0]
    store = WorkspaceSnapshotStore(tmp_path, ttl_seconds=10, max_workspace_bytes=256, clock=lambda: clock[0])
    workspace_id = store.create_workspace_id()

    with pytest.raises(WorkspaceCacheError):
        store.save(workspace_id, {"blob": os.urandom(1_024)})
    assert not (tmp_path / workspace_id).exists()

    store = WorkspaceSnapshotStore(tmp_path, ttl_seconds=10, max_workspace_bytes=10_000, clock=lambda: clock[0])
    store.save(workspace_id, {"routes": {"single": {}, "multi": {}}, "widget_state": {"market": "US"}})
    (tmp_path / workspace_id / "snapshot.pkl.gz").write_bytes(b"not a snapshot")
    assert store.load(workspace_id) is None

    workspace_id = store.create_workspace_id()
    store.save(workspace_id, {"routes": {"single": {}, "multi": {}}, "widget_state": {"market": "US"}})
    clock[0] += 11
    assert store.load(workspace_id) is None
    assert not (tmp_path / workspace_id).exists()


def test_workspace_store_discards_oversized_upload_without_leaving_bytes(tmp_path) -> None:
    store = WorkspaceSnapshotStore(tmp_path, max_workspace_bytes=256)
    workspace_id = store.create_workspace_id()

    with pytest.raises(WorkspaceCacheError):
        store.save(
            workspace_id,
            {"routes": {"single": {"uploaded_bytes": os.urandom(1_024)}, "multi": {}}},
        )

    assert not (tmp_path / workspace_id).exists()


def test_workspace_store_evicts_oldest_snapshot_over_global_budget(tmp_path) -> None:
    clock = [1.0]
    store = WorkspaceSnapshotStore(tmp_path, ttl_seconds=60, max_workspace_bytes=10_000, max_total_bytes=10_000, clock=lambda: clock[0])
    first_id = store.create_workspace_id()
    first_meta = store.save(first_id, {"payload": os.urandom(800)})
    clock[0] += 1
    second_id = store.create_workspace_id()
    second_meta = store.save(second_id, {"payload": os.urandom(800)})
    second_dir_size = sum(item.stat().st_size for item in (tmp_path / second_id).rglob("*") if item.is_file())

    bounded = WorkspaceSnapshotStore(
        tmp_path,
        ttl_seconds=60,
        max_workspace_bytes=10_000,
        max_total_bytes=second_dir_size + 1,
        clock=lambda: clock[0],
    )
    bounded.cleanup()

    assert first_meta.size_bytes > 0
    assert bounded.load(first_id) is None
    assert bounded.load(second_id) is not None


def test_workspace_session_checkpoint_hydrates_completed_state(monkeypatch, tmp_path) -> None:
    from ui import workspace

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state: dict = {}
            self.query_params: dict = {}

    fake_st = FakeStreamlit()
    store = WorkspaceSnapshotStore(tmp_path)
    monkeypatch.setattr(workspace, "st", fake_st)
    monkeypatch.setattr(workspace, "_store", lambda: store)

    workspace_id = workspace.ensure_workspace_session()
    fake_st.session_state.update(
        {
            "route_single_state": {"view": "analysis", "market": "US", "symbol": "AAPL", "uploaded_bytes": b"csv"},
            "sidebar_market": "US",
            "single_stock_analysis_section": "strategy",
            "single_stock_strategy_workspace": {
                "context_key": "ctx-1",
                "current_artifact": SimpleNamespace(id="artifact-1", request_signature="request-1"),
                "saved_artifacts": [],
            },
        }
    )
    assert workspace.checkpoint_workspace() is True

    fake_st.session_state.clear()
    assert workspace.ensure_workspace_session() == workspace_id
    assert fake_st.session_state["route_single_state"]["uploaded_bytes"] == b"csv"
    assert fake_st.session_state["single_stock_strategy_workspace"]["current_artifact"].id == "artifact-1"
    assert fake_st.session_state["single_stock_analysis_section"] == "strategy"


def test_workspace_snapshot_keeps_special_workspaces_out_of_generic_widget_state(monkeypatch) -> None:
    from ui import workspace

    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setattr(workspace, "st", fake_st)

    current_artifact = SimpleNamespace(id="artifact-1", request_signature="request-1", payload={"rows": [1, 2]})
    portfolio_result = {
        "fig": SimpleNamespace(kind="figure"),
        "port_total_return": 0.12,
        "port_sharpe": 1.3,
        "port_max_dd": -0.08,
        "bh_total_return": 0.09,
        "bh_sharpe": 0.9,
        "bh_max_dd": -0.11,
        "weights": {"AAPL": 0.5, "MSFT": 0.5},
        "individual_results": {
            "AAPL": {"total_return": 0.15, "sharpe": 1.4, "max_dd": -0.07},
            "MSFT": {"total_return": 0.10, "sharpe": 1.2, "max_dd": -0.09},
        },
    }
    fake_st.session_state.update(
        {
            workspace.SINGLE_WORKSPACE_KEY: {
                "context_key": "ctx-1",
                "current_artifact": current_artifact,
                "saved_artifacts": [],
            },
            workspace.MULTI_WORKSPACE_KEY: {
                "signature": "portfolio-1",
                "portfolio_result": portfolio_result,
                "optimization_signature": None,
                "optimization_result": None,
                "heatmap_cache": {},
            },
        }
    )

    first_payload = workspace._snapshot_payload()
    second_payload = workspace._snapshot_payload()

    assert workspace.SINGLE_WORKSPACE_KEY not in first_payload["widget_state"]
    assert workspace.MULTI_WORKSPACE_KEY not in first_payload["widget_state"]
    assert first_payload["single_workspace"]["current_artifact"] is current_artifact
    assert first_payload["multi_workspace"]["portfolio_result"].get("fig") is None
    # Portable portfolio results are copied on every snapshot.  Their marker
    # must still be stable or every ordinary rerun becomes a disk write.
    assert workspace._snapshot_marker(first_payload) == workspace._snapshot_marker(second_payload)

    fake_st.session_state[workspace.WORKSPACE_SESSION_ID_KEY] = "a" * 24
    fake_st.session_state[workspace.WORKSPACE_HYDRATED_ID_KEY] = "a" * 24
    fake_st.session_state[workspace.WORKSPACE_MARKER_KEY] = workspace._current_workspace_marker()
    monkeypatch.setattr(
        workspace,
        "_snapshot_payload",
        lambda: pytest.fail("an unchanged rerun must not rebuild its result snapshot"),
    )

    assert workspace.checkpoint_workspace() is False


def test_workspace_snapshot_does_not_restore_button_widget_state(monkeypatch) -> None:
    from ui import workspace

    fake_st = SimpleNamespace(
        session_state={
            "home_stock_next": True,
            "single_entry_rec_AAPL": True,
            "single_stock_header_details_toggle": True,
            "single_stock_switch_AAPL": True,
            "single_stock_switch_query": "Apple",
            "single_stock_analysis_section": "basics",
            "multi_stock_remove_market_MSFT": True,
            "btn_optimize_portfolio": True,
            "single_stock_header_details_expanded": True,
            "multi_stock_header_details_expanded": True,
            "multi_stock_header_details_toggle": True,
            "multi_stock_add_MSFT": True,
            "multi_stock_remove_download_AAPL": True,
            "multi_stock_generate_strategy": True,
        }
    )
    monkeypatch.setattr(workspace, "st", fake_st)

    payload = workspace._snapshot_payload()

    assert "home_stock_next" not in payload["widget_state"]
    assert "single_entry_rec_AAPL" not in payload["widget_state"]
    assert "single_stock_header_details_toggle" not in payload["widget_state"]
    assert "single_stock_switch_AAPL" not in payload["widget_state"]
    assert payload["widget_state"]["single_stock_switch_query"] == "Apple"
    assert "multi_stock_remove_market_MSFT" not in payload["widget_state"]
    assert "btn_optimize_portfolio" not in payload["widget_state"]
    assert payload["widget_state"]["single_stock_analysis_section"] == "basics"
    assert payload["widget_state"]["single_stock_header_details_expanded"] is True
    assert payload["widget_state"]["multi_stock_header_details_expanded"] is True

    fake_st.session_state.clear()
    workspace._apply_snapshot(
        {
            "widget_state": {
                "single_stock_header_details_toggle": True,
                "single_stock_switch_query": "Microsoft",
                "single_stock_analysis_section": "strategy",
                "single_stock_header_details_expanded": True,
                "multi_stock_header_details_expanded": True,
                "multi_stock_header_details_toggle": True,
                "multi_stock_generate_strategy": True,
            }
        }
    )
    assert "single_stock_header_details_toggle" not in fake_st.session_state
    assert fake_st.session_state["single_stock_switch_query"] == "Microsoft"
    assert fake_st.session_state["single_stock_analysis_section"] == "strategy"
    assert fake_st.session_state["single_stock_header_details_expanded"] is True
    assert fake_st.session_state["multi_stock_header_details_expanded"] is True
    assert "multi_stock_header_details_toggle" not in fake_st.session_state
    assert "multi_stock_generate_strategy" not in fake_st.session_state


def test_market_cache_separates_keys_and_keeps_stale_data_on_refresh_failure(tmp_path) -> None:
    clock = [1_000.0]
    cache = MarketDataCache(tmp_path, fresh_seconds=10, stale_seconds=100, clock=lambda: clock[0])
    fresh = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [10.0]})
    other = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [20.0]})
    calls = [0]

    def fetch() -> pd.DataFrame:
        calls[0] += 1
        return fresh

    first = cache.get_or_fetch(market="US", symbol="AAPL", adjust="none", fetcher=fetch)
    second = cache.get_or_fetch(market="US", symbol="AAPL", adjust="none", fetcher=fetch)
    cache.write("CN_A", "AAPL", "qfq", other)

    assert first is not None and first.freshness == "miss"
    assert second is not None and second.freshness == "fresh"
    assert calls == [1]
    assert cache.read("CN_A", "AAPL", "qfq").dataframe["close"].iloc[0] == 20.0

    clock[0] += 11
    refresh_started = threading.Event()

    def failed_refresh() -> pd.DataFrame:
        refresh_started.set()
        raise RuntimeError("source unavailable")

    stale = cache.get_or_fetch(market="US", symbol="AAPL", adjust="none", fetcher=failed_refresh)
    assert stale is not None and stale.freshness == "stale"
    assert stale.dataframe["close"].iloc[0] == 10.0
    assert refresh_started.wait(timeout=1)
    assert cache.read("US", "AAPL", "none").dataframe["close"].iloc[0] == 10.0


def test_market_cache_version_changes_after_background_refresh(tmp_path, monkeypatch) -> None:
    clock = [1_000.0]
    cache = MarketDataCache(tmp_path, fresh_seconds=10, stale_seconds=100, clock=lambda: clock[0])
    old_frame = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [10.0]})
    new_frame = pd.DataFrame({"date": pd.to_datetime(["2026-01-02"]), "close": [11.0]})
    cache.write("US", "AAPL", "none", old_frame)

    fresh_version = cache.entry_version("US", "AAPL", "none")
    assert fresh_version is not None and fresh_version.endswith(":fresh")

    clock[0] += 11
    stale_version = cache.entry_version("US", "AAPL", "none")
    assert stale_version is not None and stale_version.endswith(":stale")
    assert stale_version != fresh_version

    allow_refresh = threading.Event()
    published_refresh = threading.Event()
    original_write = cache.write

    def write_and_signal(*args, **kwargs) -> None:
        original_write(*args, **kwargs)
        published_refresh.set()

    monkeypatch.setattr(cache, "write", write_and_signal)

    def refresh() -> pd.DataFrame:
        assert allow_refresh.wait(timeout=1)
        return new_frame

    stale = cache.get_or_fetch(market="US", symbol="AAPL", adjust="none", fetcher=refresh)
    assert stale is not None and stale.freshness == "stale"
    assert stale.dataframe["close"].iloc[0] == 10.0
    assert cache.entry_version("US", "AAPL", "none") == stale_version

    allow_refresh.set()
    assert published_refresh.wait(timeout=1)

    refreshed_version = cache.entry_version("US", "AAPL", "none")
    assert refreshed_version is not None and refreshed_version.endswith(":fresh")
    assert refreshed_version != stale_version
    refreshed = cache.read("US", "AAPL", "none")
    assert refreshed is not None and refreshed.dataframe["close"].iloc[0] == 11.0


def test_market_cache_entry_version_is_stable_for_failed_refresh_and_legacy_metadata(tmp_path) -> None:
    clock = [1_000.0]
    cache = MarketDataCache(tmp_path, fresh_seconds=10, stale_seconds=100, clock=lambda: clock[0])
    frame = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "close": [10.0]})
    cache.write("US", "AAPL", "none", frame)

    _data_path, metadata_path = cache._paths("US", "AAPL", "none")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("revision")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    fresh_legacy_version = cache.entry_version("US", "AAPL", "none")
    assert fresh_legacy_version is not None and fresh_legacy_version.startswith("legacy:")
    assert cache.entry_version("US", "AAPL", "none") == fresh_legacy_version

    clock[0] += 11
    stale_legacy_version = cache.entry_version("US", "AAPL", "none")
    assert stale_legacy_version is not None and stale_legacy_version.endswith(":stale")
    assert stale_legacy_version != fresh_legacy_version

    refresh_started = threading.Event()

    def failed_refresh() -> pd.DataFrame:
        refresh_started.set()
        raise RuntimeError("source unavailable")

    stale = cache.get_or_fetch(
        market="US",
        symbol="AAPL",
        adjust="none",
        fetcher=failed_refresh,
    )
    assert stale is not None and stale.freshness == "stale"
    assert refresh_started.wait(timeout=1)

    # Wait for the worker to release its per-key guard before checking the
    # no-write outcome.  A failed refresh must not manufacture a new revision.
    cache_key = ("US", "AAPL", "none")
    deadline = time.monotonic() + 1
    while cache_key in cache._active_refreshes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert cache_key not in cache._active_refreshes
    assert cache.entry_version("US", "AAPL", "none") == stale_legacy_version
    preserved = cache.read("US", "AAPL", "none")
    assert preserved is not None and preserved.dataframe["close"].iloc[0] == 10.0


def test_market_load_fresh_hit_does_not_create_a_spinner(monkeypatch, tmp_path) -> None:
    from core import utils

    frame = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-01"]), "close": [10.0]}
    )
    cache = MarketDataCache(tmp_path, fresh_seconds=60, stale_seconds=120)
    cache.write("US", "AAPL", "none", frame)
    spinner_calls: list[str] = []
    fake_st = SimpleNamespace(
        spinner=lambda label: (spinner_calls.append(label) or nullcontext()),
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(utils, "st", fake_st)
    monkeypatch.setattr(utils, "_MARKET_DATA_CACHE", cache)
    monkeypatch.setattr(utils, "DATA_DIR", str(tmp_path / "legacy"))

    fetch_calls: list[str] = []
    monkeypatch.setattr(
        utils,
        "fetch_data",
        lambda *_args, **_kwargs: fetch_calls.append("fetch") or frame,
    )

    loaded = utils.load_or_fetch_stock("AAPL", "none", market="US")

    assert loaded is not None
    assert loaded["close"].iloc[0] == 10.0
    assert spinner_calls == []
    assert fetch_calls == []


def test_market_load_force_refresh_replaces_the_shared_cache(monkeypatch, tmp_path) -> None:
    from core import utils

    old_frame = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-01"]), "close": [10.0]}
    )
    new_frame = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-02"]), "close": [11.0]}
    )
    cache = MarketDataCache(tmp_path, fresh_seconds=60, stale_seconds=120)
    cache.write("US", "AAPL", "none", old_frame)
    fake_st = SimpleNamespace(
        spinner=lambda _label: nullcontext(),
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(utils, "st", fake_st)
    monkeypatch.setattr(utils, "_MARKET_DATA_CACHE", cache)
    monkeypatch.setattr(utils, "DATA_DIR", str(tmp_path / "legacy"))
    monkeypatch.setattr(utils, "fetch_data", lambda *_args, **_kwargs: new_frame)

    loaded = utils.load_or_fetch_stock(
        "AAPL",
        "none",
        market="US",
        force_refresh=True,
    )

    assert loaded is not None
    assert loaded["close"].iloc[0] == 11.0
    assert cache.read("US", "AAPL", "none").dataframe["close"].iloc[0] == 11.0


def test_strategy_context_key_changes_when_same_symbol_data_changes() -> None:
    from ui.single_stock_workflow import build_strategy_context_key

    first = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "open": [9.0, 10.0],
            "high": [11.0, 12.0],
            "low": [8.0, 9.0],
            "close": [10.0, 11.0],
            "volume": [100.0, 110.0],
        }
    )
    second = first.copy()
    second.loc[1, "close"] = 13.0

    first_key = build_strategy_context_key(
        market="US",
        symbol="AAPL",
        adjust="none",
        df_raw=first,
        train_ratio=0.7,
    )
    second_key = build_strategy_context_key(
        market="US",
        symbol="AAPL",
        adjust="none",
        df_raw=second,
        train_ratio=0.7,
    )

    assert first_key != second_key


def test_stage_cache_has_a_global_lru_limit(monkeypatch) -> None:
    from ui import single_stock_workflow as workflow

    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setattr(workflow, "st", fake_st)
    for index in range(14):
        workflow._cached_stage(
            stage_key="baseline" if index % 2 else "search",
            context_key="ctx",
            stage_request_slice={"index": index},
            stage_input_params_snapshot={},
            builder=lambda index=index: SimpleNamespace(index=index),
        )

    stage_cache = fake_st.session_state[workflow.STAGE_CACHE_STATE_KEY]
    assert sum(len(bucket) for bucket in stage_cache.values()) == workflow.STAGE_CACHE_MAX_ENTRIES
