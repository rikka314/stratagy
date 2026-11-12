"""Build the CN_A Phase 0 source lock without changing research inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
SOURCE_NAMES = ("full_cn_a_admission_60", "full_cn_a_deans_60")
EXPECTED_START_DATE = "2021-05-12"
EXPECTED_END_DATE = "2026-08-17"
MINIMUM_REQUIRED_END_DATE = "2026-07-31"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_snapshot_hash(entries: list[dict[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def git_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_source(source_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    source_dir = REPO_ROOT / "model-test" / "outputs" / source_name
    manifest_path = source_dir / "data_manifest.json"
    config_path = source_dir / "config_snapshot.json"
    if not manifest_path.is_file() or not config_path.is_file():
        raise RuntimeError(f"{source_name}: manifest or config snapshot is missing")

    manifest = load_json(manifest_path)
    config = load_json(config_path)
    issues: list[str] = []
    data = manifest.get("data") or {}
    execution = manifest.get("execution") or {}
    symbols = [str(symbol) for symbol in (manifest.get("universe") or {}).get("symbols", [])]
    files = (manifest.get("universe") or {}).get("files") or []
    snapshot_dir = source_dir / "data_snapshot"
    actual_entries: list[dict[str, Any]] = []
    observed_ranges: list[tuple[str, str]] = []
    missing_dates: dict[str, int] = {}
    duplicate_dates: dict[str, int] = {}
    invalid_rows: dict[str, int] = {}
    non_positive_prices: dict[str, int] = {}

    if manifest.get("market") != "CN_A" or config.get("market") != "CN_A":
        issues.append("market is not canonical CN_A")
    if data.get("source") != "frozen_csv":
        issues.append("data source is not frozen_csv")
    if data.get("adjustment") != "qfq" or config.get("adjust") != "qfq":
        issues.append("adjustment is not qfq")
    if execution.get("commission_bps") != 3.0 or execution.get("slippage_bps") != 5.0:
        issues.append("manifest execution cost is not 3 + 5 bps")
    if config.get("commission_bps") != 3.0 or config.get("slippage_bps") != 5.0:
        issues.append("config execution cost is not 3 + 5 bps")
    if data.get("start") != EXPECTED_START_DATE or data.get("end") != EXPECTED_END_DATE:
        issues.append("manifest research window does not match the frozen Phase 0 window")
    if data.get("minimum_required_end_date") != MINIMUM_REQUIRED_END_DATE:
        issues.append("manifest minimum required end date does not match Phase 0")
    if len(symbols) != 60 or len(set(symbols)) != 60:
        issues.append(f"universe symbol count/uniqueness invalid: {len(symbols)}")
    file_symbols = [str(entry.get("symbol", "")) for entry in files if isinstance(entry, dict)]
    if len(file_symbols) != len(files) or len(set(file_symbols)) != len(file_symbols):
        issues.append("manifest universe.files contains invalid or duplicate symbols")
    if file_symbols != symbols:
        issues.append("manifest universe.files symbols do not match universe.symbols")
    if len(files) != len(symbols):
        issues.append("manifest universe.files does not match symbol list")

    for entry in files:
        symbol = str(entry.get("symbol", ""))
        path = snapshot_dir / f"{symbol}_daily.csv"
        if not path.is_file():
            issues.append(f"missing snapshot: {path.name}")
            continue
        actual_hash = sha256_file(path)
        actual_size = path.stat().st_size
        if actual_hash != str(entry.get("sha256", "")):
            issues.append(f"snapshot hash mismatch: {path.name}")
        if actual_size != int(entry.get("size_bytes", -1)):
            issues.append(f"snapshot size mismatch: {path.name}")
        actual_entries.append({"symbol": symbol, "sha256": actual_hash, "size_bytes": actual_size})
        try:
            frame = pd.read_csv(path, usecols=lambda column: column in REQUIRED_COLUMNS)
            missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
            if missing_columns:
                issues.append(f"{path.name}: missing columns {missing_columns}")
                continue
            if frame.empty:
                issues.append(f"{path.name}: snapshot has no data rows")
                continue
            dates = pd.to_datetime(frame["date"], errors="coerce")
            numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]].apply(
                pd.to_numeric, errors="coerce"
            )
            invalid_count = int(dates.isna().sum() + numeric.isna().sum().sum())
            if invalid_count:
                invalid_rows[symbol] = invalid_count
                issues.append(f"{path.name}: invalid date or OHLCV values ({invalid_count})")
            duplicates = int(dates.duplicated().sum())
            if duplicates:
                duplicate_dates[symbol] = duplicates
                issues.append(f"{path.name}: duplicate dates ({duplicates})")
            non_positive = int((numeric.loc[:, ["open", "high", "low", "close"]] <= 0).sum().sum())
            if non_positive:
                non_positive_prices[symbol] = non_positive
                issues.append(f"{path.name}: non-positive prices ({non_positive})")
            if dates.notna().any():
                start_date = dates.min().date().isoformat()
                end_date = dates.max().date().isoformat()
                observed_ranges.append((start_date, end_date))
                if start_date > EXPECTED_START_DATE:
                    issues.append(f"{path.name}: data starts after frozen window start")
                if end_date < MINIMUM_REQUIRED_END_DATE:
                    issues.append(f"{path.name}: data ends before minimum required end date")
            expected_days = pd.date_range(dates.min(), dates.max(), freq="B") if dates.notna().any() else []
            missing_dates[symbol] = max(0, len(expected_days) - int(dates.nunique()))
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"{path.name}: cannot inspect CSV ({exc})")

    actual_names = {path.name for path in snapshot_dir.glob("*.csv")}
    expected_names = {f"{symbol}_daily.csv" for symbol in symbols}
    unexpected = sorted(actual_names - expected_names)
    if unexpected:
        issues.append("unmanifested snapshot files: " + ", ".join(unexpected))
    recorded_hash = str(data.get("snapshot_sha256", ""))
    actual_aggregate = portable_snapshot_hash(actual_entries) if len(actual_entries) == len(files) else ""
    if actual_aggregate != recorded_hash:
        issues.append("snapshot aggregate hash mismatch")

    quality = {
        "source": source_name,
        "status": "ready" if not issues else "failed",
        "market": manifest.get("market"),
        "symbol_count": len(symbols),
        "snapshot_file_count": len(actual_entries),
        "snapshot_sha256_recorded": recorded_hash,
        "snapshot_sha256_recomputed": actual_aggregate,
        "snapshot_manifest_sha256": sha256_file(manifest_path),
        "config_snapshot_sha256": sha256_file(config_path),
        "date_start": min((start for start, _ in observed_ranges), default=None),
        "date_end": max((end for _, end in observed_ranges), default=None),
        "manifest_date_start": data.get("start"),
        "manifest_date_end": data.get("end"),
        "minimum_required_end_date": data.get("minimum_required_end_date"),
        "missing_business_days_by_symbol": missing_dates,
        "duplicate_dates_by_symbol": duplicate_dates,
        "invalid_rows_by_symbol": invalid_rows,
        "non_positive_price_values_by_symbol": non_positive_prices,
        "issues": issues,
    }
    lock = {
        "source_name": source_name,
        "source_dir": str(source_dir.relative_to(REPO_ROOT)),
        "data_manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "config_snapshot": str(config_path.relative_to(REPO_ROOT)),
        "snapshot_dir": str(snapshot_dir.relative_to(REPO_ROOT)),
        "market": manifest.get("market"),
        "universe_symbols": symbols,
        "symbol_count": len(symbols),
        "date_range": {"start": quality["date_start"], "end": quality["date_end"]},
        "snapshot_sha256": actual_aggregate,
        "source_manifest_sha256": quality["snapshot_manifest_sha256"],
        "config_snapshot_sha256": quality["config_snapshot_sha256"],
        "execution": {
            "commission_bps": execution.get("commission_bps"),
            "slippage_bps": execution.get("slippage_bps"),
            "source_net_cost_treatment": "source_net_no_recharge",
            "ohlcv_cost_treatment": "ohlcv_gross_charge_once",
        },
        "quality_status": quality["status"],
    }
    return lock, quality


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "model-test/outputs/cn_a_factor_composite_source_lock")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    locks: dict[str, Any] = {}
    qualities: dict[str, Any] = {}
    for source_name in SOURCE_NAMES:
        lock, quality = inspect_source(source_name)
        locks[source_name] = lock
        qualities[source_name] = quality

    symbols_match = locks[SOURCE_NAMES[0]]["universe_symbols"] == locks[SOURCE_NAMES[1]]["universe_symbols"]
    snapshot_match = locks[SOURCE_NAMES[0]]["snapshot_sha256"] == locks[SOURCE_NAMES[1]]["snapshot_sha256"]
    benchmark_path = REPO_ROOT / "data/macro/cn_a_000300_daily.parquet"
    benchmark_status = "ready" if benchmark_path.is_file() else "unavailable"
    benchmark_reason = None if benchmark_status == "ready" else "no frozen market-native 000300 artifact is present"
    sources_ready = all(item["status"] == "ready" for item in qualities.values())
    source_checks_ready = sources_ready and symbols_match and snapshot_match
    overall_status = (
        "ready"
        if source_checks_ready and benchmark_status == "ready"
        else "pending"
        if source_checks_ready and benchmark_status != "ready"
        else "failed"
    )
    source_lock = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": git_version(),
        "status": overall_status,
        "market": "CN_A",
        "primary_development_source": "full_cn_a_admission_60",
        "formal_confirmation_source": "full_cn_a_deans_60",
        "sources": locks,
        "cross_source_checks": {"symbols_match": symbols_match, "snapshot_hash_match": snapshot_match},
        "benchmark": {
            "policy": "cn_a_native_then_frozen_universe_equal_weight",
            "preferred_symbol": "000300",
            "preferred_source": "market_native_frozen_artifact",
            "preferred_artifact": str(benchmark_path.relative_to(REPO_ROOT)),
            "preferred_status": benchmark_status,
            "fallback_source": "frozen_universe_equal_weight_close_return",
            "fallback_status": "registered_policy_only",
            "fallback_is_implicit": False,
            "reason": benchmark_reason,
        },
        "execution": locks[SOURCE_NAMES[0]]["execution"],
        "stop_gate_triggered": overall_status != "ready",
        "stop_gate_reasons": [
            "source manifest or snapshot quality failed" if not source_checks_ready else None,
            "preferred 000300 benchmark unavailable; use only registered equal-weight fallback"
            if benchmark_status != "ready"
            else None,
        ],
    }
    source_lock["stop_gate_reasons"] = [reason for reason in source_lock["stop_gate_reasons"] if reason]
    (output / "source_lock.json").write_text(json.dumps(source_lock, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "source_quality.json").write_text(json.dumps(qualities, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# CN_A Factor Composite Phase 0 Source Quality",
        "",
        f"Status: {overall_status}",
        "Decision: continue to Phase 1/2 only with the registered benchmark policy",
        "Market: CN_A",
        "Primary development source: `full_cn_a_admission_60`",
        "Formal confirmation source: `full_cn_a_deans_60`",
        "Benchmark: preferred `000300` market-native artifact is unavailable; fallback is frozen-universe equal-weight close-return and must be explicit.",
        "Execution: 3 bps commission + 5 bps slippage; source net returns use `source_net_no_recharge`, OHLCV experiments use `ohlcv_gross_charge_once`.",
        "",
        "## Checks",
        "",
        f"- Both source snapshots contain 60 files: `{all(item['snapshot_file_count'] == 60 for item in qualities.values())}`",
        f"- Cross-source symbol sets match: `{symbols_match}`",
        f"- Cross-source snapshot hashes match: `{snapshot_match}`",
        f"- Snapshot quality status: `{', '.join(f'{name}={item['status']}' for name, item in qualities.items())}`",
        f"- Preferred benchmark status: `{benchmark_status}`",
        "",
        "Production impact: none",
        "Streamlit impact: none",
        "",
        "Phase 0 does not train Composite, tune advisory rules, or authorize UI/production changes.",
    ]
    (output / "source_quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": overall_status, "output": str(output), "benchmark_status": benchmark_status}, ensure_ascii=False))
    return 0 if overall_status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
