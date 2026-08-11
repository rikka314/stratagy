from __future__ import annotations

import os
import threading
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
