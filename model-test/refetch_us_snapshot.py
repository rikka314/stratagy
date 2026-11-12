"""Re-fetch and lock the Phase 3 US OHLCV snapshot with yfinance.

This is a research-only data acquisition utility. It never overwrites an
existing snapshot and does not repair, clip, or winsorize market data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd


PROXY_ENV_NAMES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")
PROXY_TIMEOUT_SECONDS = 15


DEFAULT_MANIFEST = Path("model-test/outputs/full_us_deans_60/data_manifest.json")
DEFAULT_OUTPUT = Path("model-test/outputs/full_us_deans_60_refetched")
DEFAULT_START = "2016-07-19"
DEFAULT_END = "2026-08-07"
REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")


def _parse_windows_proxy_server(proxy_server: str) -> dict[str, str]:
    value = str(proxy_server or "").strip()
    if not value:
        return {}
    if "=" not in value:
        proxy_url = value if "://" in value else f"http://{value}"
        return {"http": proxy_url, "https": proxy_url}
    proxies: dict[str, str] = {}
    for entry in value.split(";"):
        scheme, separator, address = entry.partition("=")
        scheme = scheme.strip().lower()
        address = address.strip()
        if separator and scheme in {"http", "https"} and address:
            proxies[scheme] = address if "://" in address else f"http://{address}"
    if "http" in proxies and "https" not in proxies:
        proxies["https"] = proxies["http"]
    return proxies


def _resolve_proxies() -> dict[str, str]:
    """Resolve explicit env proxies, then the active Windows user proxy."""
    env = {
        key.lower(): value.strip()
        for key, value in os.environ.items()
        if key.lower() in {name.lower() for name in PROXY_ENV_NAMES} and value.strip()
    }
    if env:
        fallback = env.get("all_proxy")
        return {
            scheme: env.get(f"{scheme}_proxy") or fallback
            for scheme in ("http", "https")
            if env.get(f"{scheme}_proxy") or fallback
        }
    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                enabled = bool(winreg.QueryValueEx(key, "ProxyEnable")[0])
                server = str(winreg.QueryValueEx(key, "ProxyServer")[0])
            return _parse_windows_proxy_server(server) if enabled else {}
        except (ImportError, OSError, TypeError, ValueError):
            return {}
    return {}


def _proxy_redacted_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if not parsed.hostname:
            return "configured"
        return parsed.scheme or "configured"
    except ValueError:
        return "invalid"


def _proxy_summary(proxies: dict[str, str]) -> dict[str, Any]:
    return {
        "enabled": bool(proxies),
        "schemes": sorted(proxies),
        "endpoints": {key: _proxy_redacted_url(value) for key, value in proxies.items()},
    }


def _build_yfinance_session(proxies: dict[str, str]) -> Any:
    try:
        from curl_cffi import requests as curl_requests

        session = curl_requests.Session(impersonate="chrome")
    except (ImportError, TypeError):
        import requests as curl_requests

        session = curl_requests.Session()
    session.proxies.update(proxies)
    session.headers.update({"User-Agent": "stratagy-phase3-research/1.0"})
    return session


def _diagnose_proxy(session: Any) -> None:
    """Fail fast using the same session backend as yfinance."""
    if not getattr(session, "proxies", None):
        raise RuntimeError(
            "No proxy configured. Set HTTPS_PROXY/HTTP_PROXY/ALL_PROXY or enable "
            "the Windows Internet Settings proxy before downloading."
        )
    response = session.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/SPY",
        params={"range": "5d", "interval": "1d"},
        timeout=PROXY_TIMEOUT_SECONDS,
    )
    if response.status_code in {401, 403}:
        raise RuntimeError(
            f"Yahoo proxy authentication/authorization failed (HTTP {response.status_code})"
        )
    if response.status_code == 429:
        raise RuntimeError("Yahoo is rate-limiting the configured proxy (HTTP 429)")
    response.raise_for_status()
    payload = response.json()
    if not payload.get("chart", {}).get("result"):
        raise RuntimeError("Yahoo proxy diagnostic returned no chart data")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_snapshot_hash(entries: list[dict[str, Any]]) -> str:
    payload = [
        {key: entry[key] for key in ("symbol", "sha256", "size_bytes")}
        for entry in entries
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _flatten_download_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        if symbol in frame.columns.get_level_values(-1):
            frame = frame.xs(symbol, axis=1, level=-1)
        elif symbol in frame.columns.get_level_values(0):
            frame = frame.xs(symbol, axis=1, level=0)
        else:
            raise ValueError(f"download response has no columns for {symbol}")
    result = frame.copy()
    result.columns = [str(column) for column in result.columns]
    expected = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    if not result.columns.is_unique or not expected.issubset(result.columns):
        raise ValueError("download response is missing required OHLCV columns")
    return result.loc[:, ["Open", "High", "Low", "Close", "Adj Close", "Volume"]]


def _adjust_ohlc(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"download response missing columns: {', '.join(missing)}")

    prices = raw.loc[:, ["Open", "High", "Low", "Close", "Adj Close"]].apply(
        pd.to_numeric, errors="coerce"
    )
    volume = pd.to_numeric(raw["Volume"], errors="coerce")
    factor = prices["Adj Close"] / prices["Close"]
    return pd.DataFrame(
        {
            "open": prices["Open"] * factor,
            "high": prices["High"] * factor,
            "low": prices["Low"] * factor,
            "close": prices["Adj Close"],
            "volume": volume,
        },
        index=raw.index,
    )


def _validate_frame(
    frame: pd.DataFrame, symbol: str, start: date, end: date
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    dates = pd.to_datetime(frame.index, errors="coerce", utc=True).tz_localize(None)
    frame = frame.copy()
    frame.index = dates
    if frame.index.hasnans or not frame.index.is_monotonic_increasing:
        issues.append({"symbol": symbol, "issue": "invalid_or_unsorted_dates"})
    if frame.index.duplicated().any():
        issues.append({"symbol": symbol, "issue": "duplicate_dates"})
    if frame.index.notna().any():
        raw_start = frame.index.min().date()
        raw_end = frame.index.max().date()
        if raw_start < start or raw_end > end:
            issues.append(
                {
                    "symbol": symbol,
                    "issue": "dates_outside_requested_window",
                    "observed_start": str(raw_start),
                    "observed_end": str(raw_end),
                }
            )
    frame = frame.loc[(dates.date >= start) & (dates.date <= end)]

    if frame.empty:
        return issues + [{"symbol": symbol, "issue": "empty_window"}]
    if frame.index.min().date() > start or frame.index.max().date() < end:
        issues.append(
            {
                "symbol": symbol,
                "issue": "incomplete_window_coverage",
                "observed_start": str(frame.index.min().date()),
                "observed_end": str(frame.index.max().date()),
            }
        )
    if len(frame) < 2000:
        issues.append(
            {"symbol": symbol, "issue": "too_few_rows", "rows": int(len(frame))}
        )

    values = frame.loc[:, list(REQUIRED_COLUMNS[1:])].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        issues.append({"symbol": symbol, "issue": "non_finite_values"})
    if (frame.loc[:, ["open", "high", "low", "close"]] <= 0).any().any():
        issues.append({"symbol": symbol, "issue": "non_positive_price"})
    if (frame["volume"] < 0).any():
        issues.append({"symbol": symbol, "issue": "negative_volume"})

    bad_ohlc = (
        frame["high"] < frame[["open", "close", "low"]].max(axis=1)
    ) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    if bad_ohlc.any():
        issues.append({"symbol": symbol, "issue": "invalid_ohlc_order"})

    returns = frame["close"].pct_change(fill_method=None)
    anomaly_count = int((returns.abs() > 0.25).sum())
    if anomaly_count:
        issues.append(
            {
                "symbol": symbol,
                "issue": "large_close_return",
                "count": anomaly_count,
                "max_abs_return": float(returns.abs().max()),
            }
        )
    return issues


def _download_symbol(
    yf: Any,
    symbol: str,
    start: str,
    end: str,
    session: Any,
) -> pd.DataFrame:
    return _download_batch(yf, [symbol], start, end, session)[symbol]


def _download_batch(
    yf: Any,
    symbols: list[str],
    start: str,
    end: str,
    session: Any,
) -> dict[str, pd.DataFrame]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            raw = yf.download(
                symbols,
                start=start,
                end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
                auto_adjust=False,
                actions=False,
                progress=False,
                group_by="column",
                threads=False,
                session=session,
            )
            if raw is None or raw.empty:
                raise ValueError("empty download response")
            if not isinstance(raw.columns, pd.MultiIndex):
                if len(symbols) != 1:
                    raise ValueError("multi-symbol response is not MultiIndex")
                raw_by_symbol = {symbols[0]: raw}
            else:
                raw_by_symbol = {
                    symbol: _flatten_download_frame(raw, symbol) for symbol in symbols
                }
            result: dict[str, pd.DataFrame] = {}
            for symbol, symbol_raw in raw_by_symbol.items():
                adjusted = _adjust_ohlc(symbol_raw)
                adjusted.index = pd.to_datetime(adjusted.index).tz_localize(None)
                adjusted = adjusted.loc[
                    (adjusted.index.date >= pd.Timestamp(start).date())
                    & (adjusted.index.date <= pd.Timestamp(end).date())
                ]
                adjusted.index.name = "date"
                result[symbol] = adjusted.reset_index()
            return result
        except Exception as exc:  # noqa: BLE001 - retry then preserve provider error
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"yfinance failed after 3 attempts: {last_error}")


def refetch(
    manifest_path: Path, output_dir: Path, start: str, end: str
) -> dict[str, Any]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty directory: {output_dir}")
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    snapshot_dir = temp_dir / "data_snapshot"
    snapshot_dir.mkdir()

    try:
        source = json.loads(manifest_path.read_text(encoding="utf-8"))
        if source.get("market") != "US":
            raise ValueError("source manifest market must be US")
        if source.get("status") not in {None, "research_only", "ready"}:
            raise ValueError("source manifest has an unsupported status")
        if source.get("data", {}).get("adjustment") != "qfq":
            raise ValueError("source manifest must document the original qfq contract")
        symbols = [str(symbol) for symbol in source["universe"]["symbols"]]
        if len(symbols) != 60 or len(set(symbols)) != 60:
            raise ValueError("source manifest must contain exactly 60 unique US symbols")
        if start != source["data"]["start"] or end != source["data"]["end"]:
            raise ValueError("requested window must match the source manifest window")
    
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is required for US snapshot re-fetch") from exc
    
        proxies = _resolve_proxies()
        session = _build_yfinance_session(proxies)
        _diagnose_proxy(session)
    
        issues: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        print(
            f"Downloading batch of {len(symbols)} symbols "
            f"via proxy {_proxy_summary(proxies)}...",
            flush=True,
        )
        try:
            downloaded = _download_batch(yf, symbols, start, end, session)
        except Exception as exc:  # noqa: BLE001 - preserve batch provider failure
            raise RuntimeError(f"US snapshot download failed: {exc}") from exc
    
        for symbol in symbols:
            print(f"Validating {symbol}...", flush=True)
            try:
                frame = downloaded[symbol]
                frame.insert(6, "symbol", symbol)
                frame.insert(7, "market", "US")
                frame.insert(8, "currency", "USD")
                frame.insert(9, "adjust", "adj_close_factor_yfinance")
                frame = frame[
                    [
                        "date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "symbol",
                        "market",
                        "currency",
                        "adjust",
                    ]
                ]
                issues.extend(
                    _validate_frame(
                        frame.set_index("date"),
                        symbol,
                        pd.Timestamp(start).date(),
                        pd.Timestamp(end).date(),
                    )
                )
                path = snapshot_dir / f"{symbol}_daily.csv"
                frame.to_csv(path, index=False, date_format="%Y-%m-%d")
                entries.append(
                    {
                        "symbol": symbol,
                        "path": str(path.resolve()),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                        "rows": len(frame),
                        "start": str(frame["date"].min().date()),
                        "end": str(frame["date"].max().date()),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - preserve per-symbol evidence
                issues.append(
                    {"symbol": symbol, "issue": "download_failed", "message": str(exc)}
                )
                print(f"FAILED {symbol}: {exc}", file=sys.stderr, flush=True)
    
        if len(entries) != len(symbols):
            raise RuntimeError("one or more symbols failed; no manifest was accepted")
        if issues:
            raise RuntimeError(
                f"data quality audit failed for {len(issues)} issue(s); no manifest was accepted"
            )
    
        manifest = {
            "schema_version": "1.1",
            "status": "research_only",
            "market": "US",
            "source": {
                "provider": "Yahoo Finance via yfinance",
                "provider_symbol_namespace": "US equities",
                "yfinance_version": str(getattr(yf, "__version__", "unknown")),
                "proxy": _proxy_summary(proxies),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_fields": ["Open", "High", "Low", "Close", "Adj Close", "Volume"],
                "adjustment_semantics": (
                    "OHLC multiplied by Adj Close / Close; adjusted close retained as close; "
                    "raw Volume retained"
                ),
            },
            "data": {
                "source": "yfinance",
                "adjustment": "adj_close_factor_yfinance",
                "start": start,
                "end": end,
                "snapshot_sha256": _portable_snapshot_hash(entries),
            },
            "universe": {"symbols": symbols, "files": entries},
            "quality": {
                "issue_count": len(issues),
                "issues": issues,
                "large_return_threshold": 0.25,
                "clipping_applied": False,
                "winsorization_applied": False,
            },
        }
        (temp_dir / "data_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pd.DataFrame(issues).to_csv(temp_dir / "download_quality_issues.csv", index=False)
        temp_dir.replace(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    args = parser.parse_args()
    manifest = refetch(args.manifest, args.output, args.start, args.end)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "snapshot_sha256": manifest["data"]["snapshot_sha256"],
                "issue_count": manifest["quality"]["issue_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
