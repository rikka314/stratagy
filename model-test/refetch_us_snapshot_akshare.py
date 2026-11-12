"""Re-fetch and lock a complete US OHLCV snapshot with AkShare.

This research-only adapter uses AkShare's split-adjusted US daily endpoint,
validates the complete replacement universe, and refuses partial output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from refetch_us_snapshot import (
    DEFAULT_END,
    DEFAULT_START,
    _portable_snapshot_hash,
    _proxy_summary,
    _resolve_proxies,
    _sha256,
    _validate_frame,
)

AKSHARE_ADJUSTMENT = "qfq"
MINIMUM_ROWS = 2_000
REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


class AkShareProviderError(RuntimeError):
    """Provider response or transport error preventing a valid snapshot."""


def _validate_symbol(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if not TICKER_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid US symbol: {symbol!r}")
    return normalized


def _universe_fingerprint(symbols: list[str]) -> str:
    payload = json.dumps(symbols, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_semantic_fingerprint(source: dict[str, Any]) -> str:
    """Hash the source contract independently of its raw JSON formatting."""
    data = source.get("data") or {}
    universe = source.get("universe") or {}
    payload = {
        "market": source.get("market"),
        "start": data.get("start"),
        "end": data.get("end"),
        "adjustment": data.get("adjustment"),
        "symbols": universe.get("symbols"),
        "selection_rationale": universe.get("selection_rationale"),
        "replaced_symbols": universe.get("replaced_symbols", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_symbol(ak: Any, symbol: str) -> pd.DataFrame:
    frame = ak.stock_us_daily(symbol=symbol, adjust=AKSHARE_ADJUSTMENT)
    if frame is None or frame.empty:
        raise AkShareProviderError(f"{symbol}: AkShare returned no rows")
    missing = sorted(set(REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise AkShareProviderError(
            f"{symbol}: AkShare response missing columns: {', '.join(missing)}"
        )
    result = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce", format="mixed")
    for column in REQUIRED_COLUMNS[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if result["date"].isna().any():
        raise AkShareProviderError(f"{symbol}: AkShare returned malformed dates")
    if result["date"].duplicated().any():
        raise AkShareProviderError(f"{symbol}: AkShare returned duplicate dates")
    numeric = result.loc[:, list(REQUIRED_COLUMNS[1:])].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise AkShareProviderError(f"{symbol}: AkShare returned nonnumeric OHLCV values")
    result = result.sort_values("date")
    result["volume"] = result["volume"].astype("float64")
    return result.reset_index(drop=True)


def _validate_source(source: dict[str, Any], start: str, end: str) -> list[str]:
    if source.get("market") != "US":
        raise ValueError("source manifest market must be US")
    data = source.get("data")
    universe = source.get("universe")
    if not isinstance(data, dict) or not isinstance(universe, dict):
        raise ValueError("source manifest must contain data and universe objects")
    if data.get("adjustment") != AKSHARE_ADJUSTMENT:
        raise ValueError("source manifest adjustment must be qfq")
    raw_symbols = universe.get("symbols")
    if not isinstance(raw_symbols, list):
        raise ValueError("source manifest universe symbols must be a list")
    symbols = [_validate_symbol(symbol) for symbol in raw_symbols]
    if len(symbols) != 60 or len(set(symbols)) != 60:
        raise ValueError("source manifest must contain exactly 60 unique US symbols")
    if (start, end) != (data.get("start"), data.get("end")):
        raise ValueError("requested window must match the source manifest window")
    return symbols


def refetch(
    manifest_path: Path, output_dir: Path, start: str = DEFAULT_START, end: str = DEFAULT_END
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    snapshot_dir = temp_dir / "data_snapshot"
    snapshot_dir.mkdir()

    try:
        source = json.loads(manifest_path.read_text(encoding="utf-8"))
        symbols = _validate_source(source, start, end)
        source_fingerprint = _universe_fingerprint(symbols)
        source_semantic_fingerprint = _source_semantic_fingerprint(source)
        declared_fingerprint = (source.get("universe") or {}).get("fingerprint")
        if declared_fingerprint is not None and declared_fingerprint != source_fingerprint:
            raise ValueError("source universe fingerprint does not match its symbols")
        source_manifest_sha256 = _sha256(manifest_path)
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare is required for AkShare snapshot re-fetch") from exc

        proxies = _resolve_proxies()
        issues: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        for symbol in symbols:
            print(f"Downloading and validating {symbol}...", flush=True)
            try:
                frame = _load_symbol(ak, symbol)
                frame = frame.loc[
                    (frame["date"].dt.date >= pd.Timestamp(start).date())
                    & (frame["date"].dt.date <= pd.Timestamp(end).date())
                ].copy()
                if len(frame) < MINIMUM_ROWS:
                    issues.append(
                        {"symbol": symbol, "issue": "too_few_rows", "rows": len(frame)}
                    )
                frame["date"] = frame["date"].dt.date
                frame.insert(6, "symbol", symbol)
                frame.insert(7, "market", "US")
                frame.insert(8, "currency", "USD")
                frame.insert(9, "adjust", "qfq_akshare")
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
                        "path": (Path("data_snapshot") / path.name).as_posix(),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                        "rows": len(frame),
                        "start": str(frame["date"].min()),
                        "end": str(frame["date"].max()),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - retain per-symbol evidence
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
                "provider": "AkShare stock_us_daily",
                "adjustment": AKSHARE_ADJUSTMENT,
                "proxy": _proxy_summary(proxies),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_fields": ["open", "high", "low", "close", "volume"],
                "adjustment_semantics": (
                    "AkShare qfq split-adjusted OHLCV; provider adjustment retained"
                ),
            },
            "data": {
                "source": "akshare.stock_us_daily",
                "adjustment": "qfq_akshare",
                "start": start,
                "end": end,
                "source_manifest_sha256": source_manifest_sha256,
                "source_semantic_fingerprint": source_semantic_fingerprint,
                "snapshot_sha256": _portable_snapshot_hash(entries),
            },
            "universe": {
                "symbols": symbols,
                "fingerprint": source_fingerprint,
                "files": entries,
                "selection_rationale": source["universe"].get("selection_rationale"),
                "replaced_symbols": source["universe"].get("replaced_symbols", []),
            },
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
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("model-test/outputs/full_us_deans_60_akshare")
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
