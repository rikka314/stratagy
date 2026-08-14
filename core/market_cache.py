"""Versioned, bounded disk cache for daily market data."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import pandas as pd
import streamlit as st

from core.config import DATA_DIR


MARKET_CACHE_SCHEMA_VERSION = 1
MARKET_CACHE_FRESH_SECONDS = 24 * 60 * 60
MARKET_CACHE_STALE_SECONDS = 7 * 24 * 60 * 60
MARKET_CACHE_MAX_BYTES = 512 * 1024 * 1024


@st.cache_data(show_spinner=False, max_entries=16)
def _load_cached_market_dataframe(
    path: str,
    modified_ns: int,
    revision: str,
) -> pd.DataFrame:
    """The hot layer; file mtime and published revision form its cache key."""
    _ = modified_ns, revision
    return pd.read_parquet(path)


@dataclass(frozen=True)
class MarketCacheHit:
    dataframe: pd.DataFrame
    freshness: Literal["fresh", "stale", "miss"]
    age_seconds: float


@dataclass(frozen=True)
class _MarketCacheEntry:
    """Validated on-disk entry metadata used by lightweight cache probes."""

    data_path: Path
    metadata_path: Path
    metadata: dict[str, object]
    freshness: Literal["fresh", "stale"]
    age_seconds: float
    data_modified_ns: int
    metadata_modified_ns: int


class MarketDataCache:
    """Disk cache that serves stale daily data while one refresh runs in background."""

    _refresh_lock = threading.Lock()
    _active_refreshes: set[tuple[str, str, str]] = set()
    # ``data.parquet`` and ``metadata.json`` are separately atomically
    # replaced.  This lock makes their combined publication atomic for all
    # readers in this process, including stale-while-refresh worker threads.
    _publish_lock = threading.RLock()

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        fresh_seconds: int = MARKET_CACHE_FRESH_SECONDS,
        stale_seconds: int = MARKET_CACHE_STALE_SECONDS,
        max_bytes: int = MARKET_CACHE_MAX_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root) if root is not None else Path(DATA_DIR) / "runtime-cache" / "market"
        self.fresh_seconds = int(fresh_seconds)
        self.stale_seconds = int(stale_seconds)
        self.max_bytes = int(max_bytes)
        self._clock = clock

    def get_or_fetch(
        self,
        *,
        market: str,
        symbol: str,
        adjust: str,
        fetcher: Callable[[], pd.DataFrame | None],
    ) -> MarketCacheHit | None:
        normalized = self._normalize_key(market, symbol, adjust)
        if normalized is None:
            return None
        hit = self.read(*normalized)
        if hit is not None and hit.freshness == "fresh":
            return hit
        if hit is not None and hit.freshness == "stale":
            self._schedule_refresh(normalized, fetcher)
            return hit

        dataframe = fetcher()
        if dataframe is None or dataframe.empty:
            return None
        self.write(*normalized, dataframe)
        return MarketCacheHit(dataframe=dataframe, freshness="miss", age_seconds=0.0)

    def read(self, market: str, symbol: str, adjust: str) -> MarketCacheHit | None:
        normalized = self._normalize_key(market, symbol, adjust)
        if normalized is None:
            return None

        # Keep the parquet read inside the publication lock.  A writer
        # publishes the parquet file and its metadata as one critical section,
        # so a reader can never pair a new dataframe with old metadata (or the
        # reverse) during a background refresh.
        with self._publish_lock:
            entry = self._inspect_entry(normalized)
            if entry is None:
                return None
            try:
                dataframe = _load_cached_market_dataframe(
                    str(entry.data_path),
                    entry.data_modified_ns,
                    self._entry_revision(entry),
                )
            except (OSError, ValueError, ImportError):
                return None
        return MarketCacheHit(
            dataframe=dataframe,
            freshness=entry.freshness,
            age_seconds=entry.age_seconds,
        )

    def entry_version(self, market: str, symbol: str, adjust: str) -> str | None:
        """Return an opaque, cheap version token for a usable cache entry.

        This probes only metadata and file stat information; it never reads a
        parquet dataframe.  The token changes on every successful ``write``
        and also when a valid entry crosses from fresh to stale, allowing a UI
        cache to re-enter ``get_or_fetch`` and schedule background refresh.
        Old metadata created before ``revision`` was introduced remains valid
        through a stable stat-based fallback token.
        """
        normalized = self._normalize_key(market, symbol, adjust)
        if normalized is None:
            return None

        with self._publish_lock:
            entry = self._inspect_entry(normalized)
            if entry is None:
                return None

            base = self._entry_revision(entry)
            return f"{base}:{entry.freshness}"

    def write(
        self,
        market: str,
        symbol: str,
        adjust: str,
        dataframe: pd.DataFrame,
        *,
        fetched_at: float | None = None,
    ) -> None:
        normalized = self._normalize_key(market, symbol, adjust)
        if normalized is None:
            raise ValueError("invalid market cache key")
        market, symbol, adjust = normalized
        data_path, metadata_path = self._paths(market, symbol, adjust)
        with self._publish_lock:
            data_path.parent.mkdir(parents=True, exist_ok=True)
            self._restrict_directory(data_path.parent)

            with tempfile.NamedTemporaryFile(dir=data_path.parent, suffix=".parquet", delete=False) as handle:
                temporary_path = Path(handle.name)
            try:
                dataframe.to_parquet(temporary_path, index=False)
                os.replace(temporary_path, data_path)
            finally:
                temporary_path.unlink(missing_ok=True)

            metadata = {
                "schema_version": MARKET_CACHE_SCHEMA_VERSION,
                "market": market,
                "symbol": symbol,
                "adjust": adjust,
                "fetched_at": float(self._clock()) if fetched_at is None else float(fetched_at),
                # A UUID remains unique even when several updates share the
                # same timestamp resolution or a deterministic test clock.
                "revision": uuid.uuid4().hex,
            }
            self._atomic_write(metadata_path, json.dumps(metadata, sort_keys=True).encode("utf-8"))
            self._cleanup_unlocked()

    def cleanup(self) -> list[Path]:
        """Remove old entries first, then oldest cache files over the byte budget."""
        with self._publish_lock:
            return self._cleanup_unlocked()

    def _cleanup_unlocked(self) -> list[Path]:
        """Cleanup implementation; caller must hold ``_publish_lock``."""
        if not self.root.exists():
            return []
        removed: list[Path] = []
        now = float(self._clock())
        entries: list[tuple[Path, Path, float, int]] = []
        for metadata_path in self.root.rglob("metadata.json"):
            data_path = metadata_path.with_name("data.parquet")
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                fetched_at = float(metadata["fetched_at"])
                size = data_path.stat().st_size + metadata_path.stat().st_size
            except (OSError, ValueError, KeyError):
                metadata_path.unlink(missing_ok=True)
                data_path.unlink(missing_ok=True)
                continue
            if now - fetched_at > self.stale_seconds:
                metadata_path.unlink(missing_ok=True)
                data_path.unlink(missing_ok=True)
                removed.append(data_path.parent)
                continue
            entries.append((data_path, metadata_path, fetched_at, size))

        total_size = sum(size for _data, _metadata, _fetched, size in entries)
        for data_path, metadata_path, _fetched_at, size in sorted(entries, key=lambda item: item[2]):
            if total_size <= self.max_bytes:
                break
            data_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            removed.append(data_path.parent)
            total_size -= size
        return removed

    def list_symbols(self, market: str) -> list[str]:
        normalized_market = "CN_A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
        market_root = self.root / normalized_market
        with self._publish_lock:
            if not market_root.exists():
                return []
            symbols: set[str] = set()
            now = float(self._clock())
            for metadata_path in market_root.rglob("metadata.json"):
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if now - float(metadata["fetched_at"]) <= self.stale_seconds:
                        symbol = str(metadata.get("symbol") or "").strip().upper()
                        if symbol:
                            symbols.add(symbol)
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(symbols)

    def _inspect_entry(
        self,
        cache_key: tuple[str, str, str],
    ) -> _MarketCacheEntry | None:
        """Validate a cache entry without loading its dataframe.

        The caller holds ``_publish_lock`` so the metadata and parquet stat
        belong to the same publication generation.
        """
        market, symbol, adjust = cache_key
        data_path, metadata_path = self._paths(market, symbol, adjust)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                return None
            if int(metadata.get("schema_version", -1)) != MARKET_CACHE_SCHEMA_VERSION:
                return None
            fetched_at = float(metadata["fetched_at"])
            age_seconds = max(0.0, float(self._clock()) - fetched_at)
            if age_seconds > self.stale_seconds:
                return None
            data_modified_ns = data_path.stat().st_mtime_ns
            metadata_modified_ns = metadata_path.stat().st_mtime_ns
        except (OSError, ValueError, KeyError, TypeError):
            return None
        freshness: Literal["fresh", "stale"] = "fresh" if age_seconds <= self.fresh_seconds else "stale"
        return _MarketCacheEntry(
            data_path=data_path,
            metadata_path=metadata_path,
            metadata=metadata,
            freshness=freshness,
            age_seconds=age_seconds,
            data_modified_ns=data_modified_ns,
            metadata_modified_ns=metadata_modified_ns,
        )

    @staticmethod
    def _entry_revision(entry: _MarketCacheEntry) -> str:
        revision = entry.metadata.get("revision")
        if isinstance(revision, str) and revision:
            return f"revision:{revision}"
        # Compatibility for existing v1 metadata.  Both mtimes are part of
        # the token so a later write that adds a revision necessarily
        # invalidates it, even when a test clock is fixed.
        return (
            "legacy:"
            f"{entry.metadata.get('fetched_at')}"
            f":{entry.data_modified_ns}:{entry.metadata_modified_ns}"
        )

    def _schedule_refresh(
        self,
        cache_key: tuple[str, str, str],
        fetcher: Callable[[], pd.DataFrame | None],
    ) -> None:
        with self._refresh_lock:
            if cache_key in self._active_refreshes:
                return
            self._active_refreshes.add(cache_key)

        def refresh() -> None:
            try:
                dataframe = fetcher()
                if dataframe is not None and not dataframe.empty:
                    self.write(*cache_key, dataframe)
            except Exception:
                # The last known-good cache stays intact on every refresh failure.
                pass
            finally:
                with self._refresh_lock:
                    self._active_refreshes.discard(cache_key)

        threading.Thread(target=refresh, name=f"market-refresh-{cache_key[1]}", daemon=True).start()

    def _paths(self, market: str, symbol: str, adjust: str) -> tuple[Path, Path]:
        parent = self.root / market / symbol / adjust
        return parent / "data.parquet", parent / "metadata.json"

    @staticmethod
    def _normalize_key(market: str, symbol: str, adjust: str) -> tuple[str, str, str] | None:
        normalized_market = "CN_A" if str(market).strip().upper() in {"A", "CN", "CN_A"} else "US"
        normalized_symbol = re.sub(r"[^A-Za-z0-9._-]", "", str(symbol).strip().upper())
        normalized_adjust = re.sub(r"[^a-z0-9_-]", "", str(adjust or "none").strip().lower()) or "none"
        if not normalized_symbol:
            return None
        return normalized_market, normalized_symbol, normalized_adjust

    @staticmethod
    def _restrict_directory(path: Path) -> None:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass

    @staticmethod
    def _atomic_write(path: Path, value: bytes) -> None:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(value)
            temporary_path = Path(handle.name)
        try:
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
