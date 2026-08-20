from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _safe_path_component(value: object, *, field: str) -> str:
    if pd.isna(value):
        raise ValueError(f"{field} must be a non-empty path component")
    text = str(value)
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or Path(text).name != text
    ):
        raise ValueError(f"{field} must be a single safe path component: {text!r}")
    return text


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit(runtime_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(runtime_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _runtime_patch_provenance(runtime_root: Path) -> dict[str, object]:
    status = subprocess.run(
        ["git", "-C", str(runtime_root), "status", "--short", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    changed = [line[3:].replace("\\", "/") for line in status if line.strip()]
    allowed = "model-test/model_test/observability.py"
    if changed != [allowed]:
        raise ValueError(f"Source runtime has unexpected tracked changes: {changed}")
    patch = subprocess.run(
        ["git", "-C", str(runtime_root), "diff", "--binary", "--", allowed],
        check=True,
        capture_output=True,
    ).stdout
    if not patch:
        raise ValueError("Source runtime daily-export patch is missing")
    return {
        "dirty": True,
        "allowed_patch_path": allowed,
        "allowed_patch_sha256": hashlib.sha256(patch).hexdigest(),
        "patched_file_sha256": _sha256_file(runtime_root / allowed),
    }


def _load_runtime(runtime_root: Path) -> dict[str, object]:
    runtime_model_test = runtime_root / "model-test"
    for candidate in (str(runtime_model_test), str(runtime_root)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    from model_test.config import (
        build_main_window,
        build_request_params_snapshot,
        build_stage_a_model_specs,
        load_research_config,
    )
    from model_test.execution import execute_tasks
    from model_test.models import TaskSpec

    return {
        "load_research_config": load_research_config,
        "build_request_params_snapshot": build_request_params_snapshot,
        "build_stage_a_model_specs": build_stage_a_model_specs,
        "build_main_window": build_main_window,
        "execute_tasks": execute_tasks,
        "TaskSpec": TaskSpec,
    }


def _validate_and_publish(
    *, source_returns_path: Path, daily: pd.DataFrame, destination: Path, tolerance: float = 1e-12
) -> dict[str, object]:
    source = pd.read_csv(source_returns_path)
    source_dates = pd.to_datetime(source["date"], errors="coerce").dt.normalize()
    source_returns = pd.to_numeric(source["strategy_return"], errors="coerce")
    daily_dates = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
    daily_returns = pd.to_numeric(daily["strategy_return"], errors="coerce")
    if source_dates.isna().any() or not np.isfinite(source_returns.to_numpy(dtype=float)).all():
        raise ValueError(f"Frozen returns are invalid: {source_returns_path}")
    if not source_dates.reset_index(drop=True).equals(daily_dates.reset_index(drop=True)):
        raise ValueError(f"Adaptive replay dates drifted: {source_returns_path.parent}")
    difference = np.abs(source_returns.to_numpy(dtype=float) - daily_returns.to_numpy(dtype=float))
    max_diff = float(difference.max(initial=0.0))
    if max_diff > float(tolerance):
        raise ValueError(
            f"Adaptive replay returns drifted for {source_returns_path.parent} "
            f"(max_abs_diff={max_diff:.3g})"
        )
    required = {"target_position", "position", "turnover", "strategy_return"}
    missing = sorted(required - set(daily.columns))
    if missing:
        raise ValueError(f"Adaptive replay daily artifact lacks columns: {missing}")
    numeric = daily[["target_position", "position", "turnover", "strategy_return"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("Adaptive replay daily artifact contains missing execution values")
    expected_turnover = numeric["position"].diff().abs()
    expected_turnover.iloc[0] = abs(float(numeric["position"].iloc[0]))
    turnover_diff = np.abs(
        numeric["turnover"].to_numpy(dtype=float) - expected_turnover.to_numpy(dtype=float)
    )
    turnover_max_diff = float(turnover_diff.max(initial=0.0))
    if turnover_max_diff > float(tolerance):
        raise ValueError(
            f"Adaptive replay turnover drifted (max_abs_diff={turnover_max_diff:.3g})"
        )
    pending = destination.with_suffix(".csv.pending")
    daily.to_csv(pending, index=False)
    os.replace(pending, destination)
    return {
        "row_count": int(len(daily)),
        "return_max_abs_diff": max_diff,
        "source_returns_sha256": _sha256_file(source_returns_path),
        "daily_sha256": _sha256_file(destination),
        "turnover_max_abs_diff": turnover_max_diff,
    }


def replay_adaptive(
    *,
    runtime_root: Path,
    source_output_dir: Path,
    scratch_output_dir: Path,
    expected_commit: str,
    max_workers: int,
) -> tuple[dict[str, object], Path]:
    runtime_root = runtime_root.resolve()
    source = source_output_dir.resolve()
    scratch = scratch_output_dir.resolve()
    if source == scratch or scratch.is_relative_to(source) or source.is_relative_to(scratch):
        raise ValueError("scratch_output_dir must be separate from source_output_dir")
    actual_commit = _source_commit(runtime_root)
    runtime_patch = _runtime_patch_provenance(runtime_root)
    if not actual_commit.startswith(expected_commit):
        raise ValueError(
            f"Source runtime commit {actual_commit} does not match expected {expected_commit}"
        )
    manifest = json.loads((source / "data_manifest.json").read_text(encoding="utf-8"))
    manifest_commit = str(manifest.get("code_version") or "")
    if not actual_commit.startswith(manifest_commit):
        raise ValueError(
            f"Source manifest code_version {manifest_commit!r} does not match {actual_commit}"
        )
    runtime = _load_runtime(runtime_root)
    config_path = runtime_root / "model-test" / "configs" / "full_us_deans_60.json"
    config = runtime["load_research_config"](config_path)
    params = runtime["build_request_params_snapshot"](config)
    records = pd.read_csv(source / "runs.csv", dtype={"symbol": "string"})
    adaptive_records = records.loc[
        records["model_id"].astype(str).eq("rsm_adaptive_v1")
        & records["window_kind"].astype(str).eq("main")
        & records["status"].astype(str).isin(["success", "degraded"])
    ].sort_values("symbol")
    if adaptive_records["symbol"].nunique() != 60 or len(adaptive_records) != 60:
        raise ValueError("Adaptive source replay requires exactly 60 ready main rows")
    for value in adaptive_records["symbol"]:
        _safe_path_component(value, field="symbol")
    adaptive_dir = source / "regime_artifacts"
    if not adaptive_dir.is_dir():
        raise ValueError(f"Adaptive artifacts are missing: {adaptive_dir}")
    os.environ["STRATAGY_ADAPTIVE_REGIME_ARTIFACT_DIR"] = str(adaptive_dir)

    specs = {
        spec.model_id: spec for spec in runtime["build_stage_a_model_specs"](config)
    }
    adaptive_spec = specs.get("rsm_adaptive_v1")
    if adaptive_spec is None:
        raise ValueError("Frozen source config has no rsm_adaptive_v1 spec")
    scratch.mkdir(parents=True, exist_ok=True)
    tasks: list[object] = []
    entries: list[dict[str, object]] = []
    for row in adaptive_records.to_dict("records"):
        symbol = str(row["symbol"])
        data_path = source / "data_snapshot" / f"{symbol}_daily.csv"
        artifact_dir = source / "artifacts" / symbol / "main" / "rsm_adaptive_v1"
        existing_daily = artifact_dir / "daily.csv"
        if existing_daily.is_file():
            proof = _validate_and_publish(
                source_returns_path=artifact_dir / "returns.csv",
                daily=pd.read_csv(existing_daily),
                destination=existing_daily,
            )
            entries.append({"symbol": symbol, **proof})
            continue
        history_days = int(pd.read_csv(data_path, usecols=["date"]).shape[0])
        tasks.append(
            runtime["TaskSpec"](
                symbol=symbol,
                company_name=str(row["company_name"]),
                segment_key=str(row["segment_key"]),
                trend_bucket=str(row["trend_bucket"]),
                volatility_bucket=str(row["volatility_bucket"]),
                source_kind="frozen_source_commit_replay",
                data_path=str(data_path),
                market=config.market,
                adjust=config.adjust,
                model=adaptive_spec,
                window=runtime["build_main_window"](config, history_days),
                params_snapshot=params,
                execution=config.execution,
            )
        )

    def publish(record: object) -> None:
        if record.status not in {"success", "degraded"}:
            raise ValueError(
                f"Adaptive source replay failed for {record.symbol}: {record.error_message}"
            )
        artifact_dir = source / "artifacts" / str(record.symbol) / "main" / "rsm_adaptive_v1"
        replay_dir = scratch / "artifacts" / str(record.symbol) / "main" / "rsm_adaptive_v1"
        daily = pd.read_csv(replay_dir / "daily.csv")
        proof = _validate_and_publish(
            source_returns_path=artifact_dir / "returns.csv",
            daily=daily,
            destination=artifact_dir / "daily.csv",
        )
        entries.append({"symbol": str(record.symbol), **proof})

    runtime["execute_tasks"](
        tasks,
        max(1, int(max_workers)),
        on_record=publish,
        artifacts_root=scratch / "artifacts",
    )

    payload = {
        "schema_version": "1.0",
        "phase": "W13_adaptive_source_commit_replay",
        "status": "ready",
        "market": "US",
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source_commit": actual_commit,
        "source_runtime_dir": runtime_root.as_posix(),
        "source_runtime_patch": runtime_patch,
        "source_manifest_sha256": _sha256_file(source / "data_manifest.json"),
        "adaptive_artifact_count": len(entries),
        "artifacts": entries,
    }
    path = source / "adaptive_exact_daily_replay_manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay US adaptive daily artifacts at the frozen source commit."
    )
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--source-output-dir", required=True)
    parser.add_argument("--scratch-output-dir", required=True)
    parser.add_argument("--expected-commit", default="1b3c1d3")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        payload, path = replay_adaptive(
            runtime_root=Path(args.runtime_root),
            source_output_dir=Path(args.source_output_dir),
            scratch_output_dir=Path(args.scratch_output_dir),
            expected_commit=args.expected_commit,
            max_workers=args.max_workers,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Adaptive source-commit replay failed: {exc}", file=sys.stderr)
        return 2
    print(f"manifest: {path}")
    print(f"status: {payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
