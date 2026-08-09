from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.lightgbm_runtime import (
    configure_lightgbm_environment,
    validate_lightgbm_device,
)
from model_test import REPO_ROOT, WORKSPACE_ROOT
from model_test.config import (
    build_config_search_budget_summary,
    build_stage_a_model_specs,
    load_research_config,
)


def _repo_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _git_state() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        return {"revision": revision, "clean": not status, "changed_path_count": len(status)}
    except Exception as exc:
        return {"revision": "unknown", "clean": False, "error": str(exc)}


def _catalog_check(config) -> dict[str, Any]:
    path = _repo_path(config.catalog_path)
    if not path.is_file():
        return {"ready": False, "path": str(path), "error": "catalog is missing"}
    try:
        catalog = pd.read_csv(path, dtype=str)
    except Exception as exc:
        return {"ready": False, "path": str(path), "error": str(exc)}
    symbol_column = "symbol" if "symbol" in catalog.columns else "code"
    required = {symbol_column, "name"}
    missing = sorted(required - set(catalog.columns))
    return {
        "ready": not missing and len(catalog) >= int(config.max_catalog_candidates),
        "path": str(path),
        "row_count": int(len(catalog)),
        "symbol_column": symbol_column,
        "missing_columns": missing,
        "candidate_limit": int(config.max_catalog_candidates),
    }


def _dependency_check(config) -> dict[str, bool]:
    requested = {
        "lightgbm": True,
        "mlflow": bool(config.enable_mlflow),
        "quantstats": bool(config.enable_quantstats),
    }
    return {
        name: (not enabled or importlib.util.find_spec(name) is not None)
        for name, enabled in requested.items()
    }


def _task_estimate(config) -> dict[str, int]:
    pool_size = int(config.main_pool_size if not config.smoke_mode else len(config.smoke_symbols))
    stage_a_count = len(build_stage_a_model_specs(config))
    stage_b_max = 4 if config.run_stage_b else 0
    rolling_max = (
        pool_size * int(config.robustness_top_n) * int(config.rolling_window_count)
        if config.run_robustness
        else 0
    )
    main_max = pool_size * (stage_a_count + stage_b_max)
    return {
        "pool_size": pool_size,
        "stage_a_model_count": stage_a_count,
        "stage_b_model_count_max": stage_b_max,
        "main_records_max": main_max,
        "rolling_records_max": rolling_max,
        "total_records_max": main_max + rolling_max,
    }


def inspect_research_config(config_path: str | Path, *, allow_dirty: bool = False) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = load_research_config(config_path)
    configure_lightgbm_environment(
        device_type=config.lightgbm_device_type,
        gpu_platform_id=config.lightgbm_gpu_platform_id,
        gpu_device_id=config.lightgbm_gpu_device_id,
        gpu_use_dp=config.lightgbm_gpu_use_dp,
    )
    git = _git_state()
    catalog = _catalog_check(config)
    dependencies = _dependency_check(config)
    device = validate_lightgbm_device(config.lightgbm_device_type)
    search_budget = build_config_search_budget_summary(config)
    disk = shutil.disk_usage(WORKSPACE_ROOT)
    output_dir = WORKSPACE_ROOT / "outputs" / config.output_subdir
    checks = {
        "catalog": bool(catalog.get("ready")),
        "dependencies": all(dependencies.values()),
        "lightgbm_device": bool(device.get("available")),
        "uniform_search_budget": bool(search_budget.get("uniform_objective_budget")),
        "time_series_split": 0.0 < float(config.train_ratio) < 1.0 and not config.allow_short_main_window,
        "rolling_enabled": bool(config.run_robustness and config.rolling_window_count >= 3),
        "data_snapshot_enabled": bool(config.freeze_data_snapshot),
        "data_freshness_gate": bool(config.minimum_data_end_date),
        "disk_free_at_least_5gb": int(disk.free) >= 5 * 1024**3,
        "clean_worktree": bool(git.get("clean")) or allow_dirty or not config.require_clean_worktree,
        "output_not_started": not output_dir.exists(),
    }
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "config_name": config.name,
        "market": config.market,
        "ready": all(checks.values()),
        "checks": checks,
        "git": git,
        "catalog": catalog,
        "dependencies": dependencies,
        "lightgbm": device,
        "search_budget": search_budget,
        "task_estimate": _task_estimate(config),
        "compute": config.compute,
        "minimum_data_end_date": config.minimum_data_end_date,
        "disk_free_bytes": int(disk.free),
        "output_dir": str(output_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate full research configs before execution.")
    parser.add_argument("--config", action="append", required=True, help="Research config JSON; repeatable.")
    parser.add_argument("--allow-dirty", action="store_true", help="Ignore only the clean-worktree gate.")
    parser.add_argument(
        "--probe-device",
        action="append",
        default=[],
        help="Optionally probe an additional LightGBM device (cpu, gpu, or cuda).",
    )
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args(argv)

    reports = [inspect_research_config(path, allow_dirty=args.allow_dirty) for path in args.config]
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready": all(report["ready"] for report in reports),
        "configs": reports,
        "device_probes": [validate_lightgbm_device(device) for device in args.probe_device],
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
