"""Re-fetch and lock the Phase 3 US OHLCV snapshot from Nasdaq historical data.

Nasdaq's public historical endpoint returns unadjusted OHLCV. This utility does
not infer split/dividend adjustments: the resulting manifest records the raw
data contract explicitly and the quality audit remains fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from refetch_us_snapshot import (
    DEFAULT_END,
    DEFAULT_MANIFEST,
    DEFAULT_START,
    _portable_snapshot_hash,
    _proxy_summary,
    _resolve_proxies,
    _sha256,
    _validate_frame,
)

NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


class NasdaqProviderError(RuntimeError):
    """Provider response or transport error preventing a valid snapshot."""


def _build_session(proxies: dict[str, str]) -> Any:
    import requests

    session = requests.Session()
    session.proxies.update(proxies)
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            ),
        }
    )
    return session


def _validate_symbol(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if not TICKER_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid US symbol: {symbol!r}")
    return normalized


def _parse_number(value: Any, field: str, symbol: str) -> float:
    if value is None:
        raise NasdaqProviderError(f"{symbol}: null Nasdaq {field}")
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    try:
        number = float(cleaned)
    except (TypeError, ValueError) as exc:
        raise NasdaqProviderError(
            f"{symbol}: invalid Nasdaq {field} value {value!r}"
        ) from exc
    if not np.isfinite(number):
        raise NasdaqProviderError(f"{symbol}: non-finite Nasdaq {field}")
    if field == "volume" and (number < 0 or not number.is_integer()):
        raise NasdaqProviderError(f"{symbol}: non-integer Nasdaq volume")
    return number


def _fetch_symbol(session: Any, symbol: str, start: str, end: str) -> pd.DataFrame:
    params = {
        "assetclass": "etf" if symbol == "SPY" else "stocks",
        "fromdate": start,
        "todate": end,
        "limit": "5000",
    }
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = session.get(
                NASDAQ_URL.format(symbol=symbol),
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - classify as transport failure
            if attempt + 1 == MAX_ATTEMPTS:
                raise NasdaqProviderError(
                    f"{symbol}: Nasdaq transport failed after {MAX_ATTEMPTS} attempts: {exc}"
                ) from exc
            time.sleep(2**attempt)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt + 1 == MAX_ATTEMPTS:
                raise NasdaqProviderError(
                    f"{symbol}: Nasdaq HTTP {response.status_code} after {MAX_ATTEMPTS} attempts"
                )
            time.sleep(2**attempt)
            continue
        if response.status_code != 200:
            raise NasdaqProviderError(f"{symbol}: Nasdaq HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise NasdaqProviderError(f"{symbol}: Nasdaq returned non-JSON data") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        table = data.get("tradesTable") if isinstance(data, dict) else None
        rows = table.get("rows") if isinstance(table, dict) else None
        if not isinstance(rows, list) or not rows:
            raise NasdaqProviderError(f"{symbol}: Nasdaq returned no historical rows")

        records: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise NasdaqProviderError(f"{symbol}: malformed Nasdaq row")
            try:
                records.append(
                    {
                        "date": pd.to_datetime(row["date"], format="%m/%d/%Y"),
                        "open": _parse_number(row["open"], "open", symbol),
                        "high": _parse_number(row["high"], "high", symbol),
                        "low": _parse_number(row["low"], "low", symbol),
                        "close": _parse_number(row["close"], "close", symbol),
                        "volume": _parse_number(row["volume"], "volume", symbol),
                    }
                )
            except KeyError as exc:
                raise NasdaqProviderError(
                    f"{symbol}: Nasdaq row missing field {exc.args[0]!r}"
                ) from exc
        frame = pd.DataFrame.from_records(records).sort_values("date")
        if frame["date"].duplicated().any():
            raise NasdaqProviderError(f"{symbol}: Nasdaq returned duplicate dates")
        frame["volume"] = frame["volume"].astype("int64")
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        return frame.reset_index(drop=True)
    raise AssertionError("unreachable")


def refetch(
    manifest_path: Path, output_dir: Path, start: str, end: str
) -> dict[str, Any]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty directory: {output_dir}")
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent)
    )
    snapshot_dir = temp_dir / "data_snapshot"
    snapshot_dir.mkdir()

    try:
        source = json.loads(manifest_path.read_text(encoding="utf-8"))
        if source.get("market") != "US":
            raise ValueError("source manifest market must be US")
        if source.get("status") not in {None, "research_only", "ready"}:
            raise ValueError("source manifest has an unsupported status")
        source_data = source.get("data", {})
        if source_data.get("adjustment") != "qfq":
            raise ValueError("source manifest must document the original qfq contract")
        symbols = [_validate_symbol(symbol) for symbol in source["universe"]["symbols"]]
        if len(symbols) != 60 or len(set(symbols)) != 60:
            raise ValueError("source manifest must contain exactly 60 unique US symbols")
        if (start, end) != (source_data.get("start"), source_data.get("end")):
            raise ValueError("requested window must match the source manifest window")

        try:
            import requests  # noqa: F401 - explicit dependency boundary
        except ImportError as exc:
            raise RuntimeError("requests is required for Nasdaq snapshot re-fetch") from exc

        proxies = _resolve_proxies()
        session = _build_session(proxies)
        issues: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        for symbol in symbols:
            print(f"Downloading and validating {symbol}...", flush=True)
            try:
                frame = _fetch_symbol(session, symbol, start, end)
                frame.insert(6, "symbol", symbol)
                frame.insert(7, "market", "US")
                frame.insert(8, "currency", "USD")
                frame.insert(9, "adjust", "raw_nasdaq_unadjusted")
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
                resolved_path = path.resolve()
                if snapshot_dir.resolve() not in resolved_path.parents:
                    raise NasdaqProviderError(f"{symbol}: snapshot path escaped output directory")
                frame.to_csv(path, index=False, date_format="%Y-%m-%d")
                entries.append(
                    {
                        "symbol": symbol,
                        "path": str(Path("data_snapshot") / path.name),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                        "rows": len(frame),
                        "start": str(frame["date"].min()),
                        "end": str(frame["date"].max()),
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
                "provider": "Nasdaq historical API",
                "endpoint": NASDAQ_URL,
                "proxy": _proxy_summary(proxies),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_fields": ["Open", "High", "Low", "Close", "Volume"],
                "adjustment_semantics": (
                    "raw unadjusted OHLCV; no split or dividend adjustment applied"
                ),
            },
            "data": {
                "source": "nasdaq_historical_api",
                "adjustment": "raw_nasdaq_unadjusted",
                "start": start,
                "end": end,
                "snapshot_sha256": _portable_snapshot_hash(entries),
            },
            "universe": {"symbols": symbols, "files": entries},
            "quality": {
                "issue_count": 0,
                "issues": [],
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
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model-test/outputs/full_us_deans_60_nasdaq"),
    )
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
