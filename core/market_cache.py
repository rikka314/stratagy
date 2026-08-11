"""Versioned, bounded disk cache for daily market data."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
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
def _load_cached_market_dataframe(path: str, modified_ns: int) -> pd.DataFrame:
    """The hot layer; mtime is part of the cache key after atomic refreshes."""
    _ = modified_ns
    return pd.read_parquet(path)


@dataclass(frozen=True)
class MarketCacheHit:
    dataframe: pd.DataFrame
    freshness: Literal["fresh", "stale", "miss"]
    age_seconds: float


class MarketDataCache:
    """Disk cache that serves stale daily data while one refresh runs in background."""

    _refresh_lock = threading.Lock()
    _active_refreshes: set[tuple[str, str, str]] = set()

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
        market, symbol, adjust = normalized
        data_path, metadata_path = self._paths(market, symbol, adjust)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if int(metadata.get("schema_version", -1)) != MARKET_CACHE_SCHEMA_VERSION:
                return None
            fetched_at = float(metadata["fetched_at"])
            age_seconds = max(0.0, float(self._clock()) - fetched_at)
            if age_seconds > self.stale_seconds:
                return None
            dataframe = _load_cached_market_dataframe(str(data_path), data_path.stat().st_mtime_ns)
        except (OSError, ValueError, KeyError, ImportError):
            return None
        freshness: Literal["fresh", "stale"] = "fresh" if age_seconds <= self.fresh_seconds else "stale"
        return MarketCacheHit(dataframe=dataframe, freshness=freshness, age_seconds=age_seconds)

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
        }
        self._atomic_write(metadata_path, json.dumps(metadata, sort_keys=True).encode("utf-8"))
        self.cleanup()

    def cleanup(self) -> list[Path]:
        """Remove old entries first, then oldest cache files over the byte budget."""
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
