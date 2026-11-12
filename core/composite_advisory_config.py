"""Phase 0/1 research-only Composite Advisory configuration helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.composite_advisory import AdvisoryConfig, POLICIES, POLICY_VERSION


CONFIG_PATH = Path(__file__).resolve().parents[1] / "model-test/configs/composite_advisory_phase0_1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_advisory_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load and validate the frozen Phase 0 policy configuration."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("status") != "research_only":
        raise ValueError("Composite Advisory must remain research_only")
    if config.get("market") != "US":
        raise ValueError("Composite Advisory config must target US")
    if config.get("policy_version") != POLICY_VERSION:
        raise ValueError("policy version does not match implementation")
    if tuple(config.get("policies", ())) != POLICIES:
        raise ValueError("policy list does not match registered ablation set")
    if config.get("execution", {}).get("cost_treatment") != "ohlcv_gross_charge_once":
        raise ValueError("OHLCV research requires ohlcv_gross_charge_once")
    bounds = config.get("bounds")
    if not isinstance(bounds, dict):
        raise ValueError("missing advisory bounds")
    AdvisoryConfig(**bounds)
    return config


def _artifact_records(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["path"]): item
        for item in (manifest.get("artifacts") or {}).values()
        if isinstance(item, dict) and item.get("path")
    }


def source_lock(config: dict[str, Any], config_path: Path = CONFIG_PATH) -> dict[str, str]:
    """Hash manifests and every artifact they declare."""
    root = config_path.resolve().parents[2]
    manifest = root / config["source"]["data_manifest"]
    macro_manifest = root / config["source"]["macro_data_manifest"]
    source_data = json.loads(manifest.read_text(encoding="utf-8"))
    macro_data = json.loads(macro_manifest.read_text(encoding="utf-8"))
    snapshot_dir = root / config["source"]["snapshot_dir"]
    for entry in (source_data.get("universe") or {}).get("files", []):
        path = snapshot_dir / f"{str(entry['symbol']).upper()}_daily.csv"
        if not path.is_file() or sha256_file(path) != str(entry.get("sha256")):
            raise ValueError(f"snapshot artifact hash mismatch: {path.name}")
    for entry in _artifact_records(macro_data).values():
        path = root / config["source"]["macro_data_dir"] / str(entry["path"])
        if not path.is_file() or sha256_file(path) != str(entry.get("sha256")):
            raise ValueError(f"macro artifact hash mismatch: {path.name}")
    return {
        "config_sha256": sha256_file(config_path),
        "source_manifest_sha256": sha256_file(manifest),
        "macro_data_manifest_sha256": sha256_file(macro_manifest),
        "snapshot_artifacts_sha256": hashlib.sha256(
            "".join(
                sorted(
                    sha256_file(snapshot_dir / f"{str(item['symbol']).upper()}_daily.csv")
                    for item in (source_data.get("universe") or {}).get("files", [])
                )
            ).encode("ascii")
        ).hexdigest(),
        "macro_artifacts_sha256": hashlib.sha256(
            "".join(sorted(sha256_file(root / config["source"]["macro_data_dir"] / str(item["path"])) for item in _artifact_records(macro_data).values())).encode("ascii")
        ).hexdigest(),
    }


__all__ = ["CONFIG_PATH", "load_advisory_config", "sha256_file", "source_lock"]
