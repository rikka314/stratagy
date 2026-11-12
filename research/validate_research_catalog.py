"""Validate the frozen research catalog without creating evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = {
    "baseline_frozen",
    "passed_research_gate",
    "framework_complete_pending_real_data_gate",
    "not_admitted",
    "stopped",
    "pending",
    "unavailable",
    "completed",
}
REQUIRED_EXPERIMENT_KEYS = {
    "id",
    "title",
    "archive_path",
    "status",
    "date_range",
    "markets",
    "question",
    "decision",
    "gate",
    "sources",
    "evidence",
}


@dataclass(frozen=True)
class EvidenceCheck:
    experiment_id: str
    path: str
    required: bool
    present: bool
    sha256: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(repo_root: Path) -> dict[str, Any]:
    catalog_path = repo_root / "research" / "RESEARCH_CATALOG.json"
    with catalog_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Research catalog must be a JSON object")
    return payload


def _validate_experiment_shape(experiment: object) -> list[str]:
    if not isinstance(experiment, dict):
        return ["experiment entry is not an object"]

    errors: list[str] = []
    missing = sorted(REQUIRED_EXPERIMENT_KEYS - set(experiment))
    if missing:
        errors.append(f"missing keys: {', '.join(missing)}")

    status = experiment.get("status")
    if status not in ALLOWED_STATUSES:
        errors.append(f"unknown status: {status!r}")

    markets = experiment.get("markets")
    if not isinstance(markets, list) or not markets or not all(isinstance(item, str) for item in markets):
        errors.append("markets must be a non-empty list of strings")

    for key in ("sources", "evidence"):
        if not isinstance(experiment.get(key), list):
            errors.append(f"{key} must be a list")

    if not isinstance(experiment.get("id"), str) or not str(experiment.get("id")).strip():
        errors.append("id must be a non-empty string")
    return errors


def validate_catalog(repo_root: Path, *, include_hashes: bool = True) -> tuple[list[str], list[EvidenceCheck]]:
    payload = load_catalog(repo_root)
    experiments = payload.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        return ["catalog.experiments must be a non-empty list"], []

    errors: list[str] = []
    checks: list[EvidenceCheck] = []
    ids: set[str] = set()
    for index, experiment in enumerate(experiments):
        shape_errors = _validate_experiment_shape(experiment)
        errors.extend(f"experiments[{index}]: {message}" for message in shape_errors)
        if not isinstance(experiment, dict):
            continue

        experiment_id = str(experiment.get("id", f"index-{index}"))
        if experiment_id in ids:
            errors.append(f"duplicate experiment id: {experiment_id}")
        ids.add(experiment_id)

        archive_path = repo_root / str(experiment.get("archive_path", ""))
        if not archive_path.is_dir():
            errors.append(f"{experiment_id}: archive path missing: {experiment.get('archive_path')}")

        for source in experiment.get("sources", []):
            if not isinstance(source, str):
                errors.append(f"{experiment_id}: source path is not a string")
                continue
            if not (repo_root / source).exists():
                errors.append(f"{experiment_id}: source path missing: {source}")

        for evidence in experiment.get("evidence", []):
            if not isinstance(evidence, dict) or not isinstance(evidence.get("path"), str):
                errors.append(f"{experiment_id}: evidence entry must contain a path")
                continue
            evidence_path = str(evidence["path"])
            path = repo_root / evidence_path
            present = path.is_file()
            required = bool(evidence.get("required", False))
            digest = _sha256(path) if present and include_hashes else None
            checks.append(EvidenceCheck(experiment_id, evidence_path, required, present, digest))

            if not present and required and experiment.get("status") == "passed_research_gate":
                errors.append(f"{experiment_id}: passed experiment requires missing evidence: {evidence_path}")

    return errors, checks


def _print_report(errors: list[str], checks: list[EvidenceCheck]) -> None:
    print("Research catalog validation")
    print(f"  evidence entries: {len(checks)}")
    print(f"  present: {sum(item.present for item in checks)}")
    print(f"  pending/unavailable: {sum(not item.present for item in checks)}")
    if checks:
        for item in checks:
            state = "present" if item.present else "pending"
            required = "required" if item.required else "optional"
            suffix = f" sha256={item.sha256}" if item.sha256 else ""
            print(f"  - {item.experiment_id}: {state} ({required}) {item.path}{suffix}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Result: PASS (missing ignored outputs remain visible as pending)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-hashes", action="store_true", help="Skip SHA-256 calculation for present evidence")
    args = parser.parse_args(argv)

    try:
        errors, checks = validate_catalog(args.repo_root.resolve(), include_hashes=not args.no_hashes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Catalog validation failed: {exc}", file=sys.stderr)
        return 2
    _print_report(errors, checks)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
