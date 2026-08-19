from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE_ROOT.parent
for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


from model_test import transformer_state_model as state_model
from model_test.transformer_state_model import (
    TransformerStateConfig,
    TransformerStateError,
    build_embedding_schema,
    fit_transformer_fold,
    validate_model_feature_schema,
)
from model_test.transformer_state_panel import (
    FEATURE_SCHEMA_NAME,
    PANEL_MANIFEST_NAME,
    SEQUENCE_PANEL_NAME,
    SOURCE_MANIFEST_NAME,
    SPLITS_NAME,
    TransformerStatePanelError,
    _json_object,
    _sha256_file,
    build_transformer_source_manifest,
    load_transformer_state_config,
    materialize_transformer_state_panel,
    transformer_code_lock,
    write_blocked_transformer_manifests,
)


MODEL_MANIFEST_NAME = "transformer_state_model_manifest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_manifest_artifact(output_dir: Path, manifest: dict[str, Any], key: str) -> Path:
    descriptor = (manifest.get("artifacts") or {}).get(key)
    if not isinstance(descriptor, dict) or not descriptor.get("path"):
        raise TransformerStatePanelError(f"W14 manifest lacks artifact metadata for {key}")
    path = output_dir / str(descriptor["path"])
    if not path.is_file() or _sha256_file(path) != str(descriptor.get("sha256") or ""):
        raise TransformerStatePanelError(f"W14 artifact is missing or hash-drifted: {path}")
    return path


def _membership_mask(frame: pd.DataFrame, split_id: str, role: str) -> np.ndarray:
    values: list[bool] = []
    for raw in frame["split_memberships_json"].fillna("[]"):
        try:
            memberships = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise TransformerStatePanelError("split_memberships_json is invalid") from exc
        values.append(
            any(
                str(item.get("split_id")) == split_id and str(item.get("role")) == role
                for item in memberships
            )
        )
    return np.asarray(values, dtype=bool)


def _json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def train_transformer_state_folds(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Fit W15 fold-local encoders or persist an explicit unavailable result."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / "model-test" / "outputs" / str(config["output_subdir"])).resolve()
    )
    source_manifest_path = target / SOURCE_MANIFEST_NAME
    panel_manifest_path = target / PANEL_MANIFEST_NAME
    if not source_manifest_path.is_file() or not panel_manifest_path.is_file():
        raise TransformerStatePanelError("W15 requires completed W13/W14 manifests")
    source_manifest = _json_object(source_manifest_path)
    panel_manifest = _json_object(panel_manifest_path)
    if source_manifest.get("status") != "ready" or panel_manifest.get("status") != "ready":
        raise TransformerStatePanelError("W15 requires ready W13/W14 inputs")
    if panel_manifest.get("config_sha256") != _sha256_file(config_file):
        raise TransformerStatePanelError("W15 config differs from the W14 source lock")
    if panel_manifest.get("source_manifest_sha256") != _sha256_file(source_manifest_path):
        raise TransformerStatePanelError("W13 source manifest changed after W14 materialization")
    current_code_lock = transformer_code_lock(root)
    if panel_manifest.get("code_lock", {}).get("aggregate_sha256") != current_code_lock[
        "aggregate_sha256"
    ]:
        raise TransformerStatePanelError("W13-W15 implementation code changed after W14 materialization")
    sequence_path = _verify_manifest_artifact(target, panel_manifest, "state_sequence_panel")
    feature_schema_path = _verify_manifest_artifact(target, panel_manifest, "feature_schema")
    splits_path = _verify_manifest_artifact(target, panel_manifest, "walk_forward_splits")
    try:
        sequences = pd.read_parquet(sequence_path)
        splits = pd.read_csv(splits_path)
    except (OSError, ValueError, ImportError) as exc:
        raise TransformerStatePanelError("W15 could not read W14 artifacts") from exc
    feature_schema = _json_object(feature_schema_path)
    feature_columns = validate_model_feature_schema(feature_schema)
    required = {
        "sequence_values",
        "best_expert_5d",
        "label_margin",
        "label_status",
        "expert_utilities_json",
        "split_memberships_json",
    }
    missing = required - set(sequences.columns)
    if missing:
        raise TransformerStatePanelError(f"W15 sequence panel lacks fields: {sorted(missing)}")
    try:
        sequence_values = np.stack(
            [np.stack(value).astype(np.float64, copy=False) for value in sequences["sequence_values"]]
        )
    except (TypeError, ValueError) as exc:
        raise TransformerStatePanelError("W15 sequence arrays do not match the frozen feature schema") from exc
    labels = sequences["best_expert_5d"].fillna("").astype(str).to_numpy()
    margins = pd.to_numeric(sequences["label_margin"], errors="coerce").to_numpy(dtype=float)
    expert_utilities: list[dict[str, Any]] = []
    for raw in sequences["expert_utilities_json"]:
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise TransformerStatePanelError("W15 expert utility payload is invalid JSON") from exc
        if not isinstance(value, dict):
            raise TransformerStatePanelError("W15 expert utility payload must be an object")
        expert_utilities.append(value)
    eligible = sequences["label_status"].eq("ready").to_numpy() & np.isfinite(margins) & (labels != "")
    model_config = TransformerStateConfig.from_mapping(config)
    model_config.validate()
    runtime = state_model.torch_dependency_preflight()
    fold_entries: list[dict[str, Any]] = []
    overall_status = "ready"

    for split in splits.to_dict("records"):
        split_id = str(split["split_id"])
        train_role = _membership_mask(sequences, split_id, "train")
        validation_role = _membership_mask(sequences, split_id, "validation")
        if not train_role.any() or not validation_role.any():
            raise TransformerStatePanelError(f"{split_id} lacks train/validation sequences")
        train_indexes = np.flatnonzero(train_role)
        validation_indexes = np.flatnonzero(validation_role)
        result = fit_transformer_fold(
            train_sequences=sequence_values[train_indexes],
            train_labels=labels[train_indexes],
            train_margins=np.where(np.isfinite(margins[train_indexes]), margins[train_indexes], 0.0),
            validation_sequences=sequence_values[validation_indexes],
            validation_labels=labels[validation_indexes],
            validation_margins=np.where(
                np.isfinite(margins[validation_indexes]), margins[validation_indexes], 0.0
            ),
            train_expert_utilities=[expert_utilities[index] for index in train_indexes],
            validation_expert_utilities=[expert_utilities[index] for index in validation_indexes],
            feature_columns=feature_columns,
            feature_schema=feature_schema,
            config=model_config,
            train_supervision_mask=eligible[train_indexes],
            validation_supervision_mask=eligible[validation_indexes],
        )
        fold_dir = target / "folds" / split_id
        fold_dir.mkdir(parents=True, exist_ok=True)
        selected_sequence_length = (
            result.selected_candidate.sequence_length
            if result.selected_candidate is not None and result.selected_candidate.sequence_length is not None
            else int(config["panel"]["primary_sequence_length"])
        )
        selected_embedding_dim = (
            result.selected_candidate.embedding_dim
            if result.selected_candidate is not None
            else int(config["transformer"]["embedding_dimension"])
        )
        embedding_schema = build_embedding_schema(
            feature_columns=feature_columns,
            sequence_length=int(selected_sequence_length),
            embedding_dim=int(selected_embedding_dim),
            scaler=result.scaler,
            label_vocabulary=result.label_vocabulary,
            feature_schema_sha256=_sha256_file(feature_schema_path),
        )
        embedding_schema["status"] = result.status
        embedding_schema["runtime"] = runtime
        embedding_schema_path = fold_dir / "state_embedding_schema.json"
        train_metrics_path = fold_dir / "train_metrics.json"
        validation_metrics_path = fold_dir / "validation_metrics.json"
        training_log_path = fold_dir / "training_log.json"
        fold_manifest_path = fold_dir / "manifest.json"
        _json_write(embedding_schema_path, embedding_schema)
        _json_write(train_metrics_path, {"status": result.status, "metrics": result.train_metrics})
        _json_write(
            validation_metrics_path,
            {"status": result.status, "metrics": result.validation_metrics},
        )
        _json_write(training_log_path, result.training_log)
        model_path: Path | None = None
        if result.model is not None:
            model_path = fold_dir / "transformer_encoder.pt"
            state_model.torch.save(
                {
                    "state_dict": result.model.state_dict(),
                    "model_payload": result.payload(model_config),
                    "embedding_schema": embedding_schema,
                },
                model_path,
            )
        if result.status != "ready":
            overall_status = "unavailable"
        fold_manifest = {
            "schema_version": "1.0",
            "phase": "W15",
            "status": result.status,
            "created_at": _utc_now(),
            "market": config["market"],
            "split_id": split_id,
            "fit_roles": ["train"],
            "selection_roles": ["validation"],
            "forbidden_selection_roles": ["test"],
            "train_sequence_count": int(train_role.sum()),
            "train_supervision_count": int(eligible[train_indexes].sum()),
            "validation_sequence_count": int(validation_role.sum()),
            "validation_supervision_count": int(eligible[validation_indexes].sum()),
            "runtime": runtime,
            "availability": result.availability,
            "selected_candidate": (
                None
                if result.selected_candidate is None
                else {
                    "embedding_dim": result.selected_candidate.embedding_dim,
                    "num_layers": result.selected_candidate.num_layers,
                    "num_heads": result.selected_candidate.num_heads,
                    "feedforward_dim": result.selected_candidate.feedforward_dim,
                    "dropout": result.selected_candidate.dropout,
                    "sequence_length": result.selected_candidate.sequence_length,
                }
            ),
            "label_vocabulary": result.label_vocabulary,
            "model_state_sha256": result.model_sha256,
            "source_lock": {
                "config_sha256": _sha256_file(config_file),
                "source_manifest_sha256": _sha256_file(source_manifest_path),
                "panel_manifest_sha256": _sha256_file(panel_manifest_path),
                "sequence_panel_sha256": _sha256_file(sequence_path),
                "feature_schema_sha256": _sha256_file(feature_schema_path),
                "code_lock_aggregate_sha256": current_code_lock["aggregate_sha256"],
            },
            "artifacts": {
                "transformer_encoder": (
                    None
                    if model_path is None
                    else {
                        "path": model_path.name,
                        "sha256": _sha256_file(model_path),
                        "size_bytes": model_path.stat().st_size,
                    }
                ),
                "state_embedding_schema": {
                    "path": embedding_schema_path.name,
                    "sha256": _sha256_file(embedding_schema_path),
                },
                "train_metrics": {
                    "path": train_metrics_path.name,
                    "sha256": _sha256_file(train_metrics_path),
                },
                "validation_metrics": {
                    "path": validation_metrics_path.name,
                    "sha256": _sha256_file(validation_metrics_path),
                },
                "training_log": {
                    "path": training_log_path.name,
                    "sha256": _sha256_file(training_log_path),
                },
            },
        }
        _json_write(fold_manifest_path, fold_manifest)
        fold_entries.append(
            {
                "split_id": split_id,
                "status": result.status,
                "reason": result.availability.get("reason"),
                "manifest_path": fold_manifest_path.relative_to(target).as_posix(),
                "manifest_sha256": _sha256_file(fold_manifest_path),
            }
        )

    overall = {
        "schema_version": "1.0",
        "phase": "W15",
        "status": overall_status,
        "created_at": _utc_now(),
        "market": config["market"],
        "runtime": runtime,
        "fit_roles": ["train"],
        "selection_roles": ["validation"],
        "forbidden_selection_roles": ["test"],
        "fold_count": int(len(fold_entries)),
        "folds": fold_entries,
        "source_lock": {
            "config_sha256": _sha256_file(config_file),
            "source_manifest_sha256": _sha256_file(source_manifest_path),
            "panel_manifest_sha256": _sha256_file(panel_manifest_path),
            "sequence_panel_sha256": _sha256_file(sequence_path),
            "feature_schema_sha256": _sha256_file(feature_schema_path),
            "splits_sha256": _sha256_file(splits_path),
            "code_lock": current_code_lock,
        },
        "next_stage_allowed": overall_status == "ready",
    }
    manifest_path = target / MODEL_MANIFEST_NAME
    _json_write(manifest_path, overall)
    return overall, manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the source-locked W13/W14/W15 Transformer-state research stages."
    )
    parser.add_argument("--config", required=True, help="Path to transformer_state_{market}.json")
    parser.add_argument(
        "--stage",
        choices=("source", "panel", "model", "all"),
        default="all",
        help="Stop after the requested research stage (default: all)",
    )
    parser.add_argument("--output-dir", help="Optional output directory override")
    args = parser.parse_args(argv)
    try:
        if args.stage == "source":
            manifest, path = build_transformer_source_manifest(
                args.config, repo_root=REPO_ROOT, output_dir=args.output_dir
            )
            print(f"source_manifest: {path}")
            print(f"status: {manifest['status']}")
            return 0
        if args.stage in {"panel", "all"}:
            outputs = materialize_transformer_state_panel(
                args.config, repo_root=REPO_ROOT, output_dir=args.output_dir
            )
            for name, path in outputs.items():
                print(f"{name}: {path}")
            if args.stage == "panel":
                return 0
        overall, manifest_path = train_transformer_state_folds(
            args.config, repo_root=REPO_ROOT, output_dir=args.output_dir
        )
        print(f"model_manifest: {manifest_path}")
        print(f"status: {overall['status']}")
        return 0 if overall["status"] == "ready" else 3
    except (TransformerStatePanelError, TransformerStateError) as exc:
        try:
            blocked = write_blocked_transformer_manifests(
                args.config,
                repo_root=REPO_ROOT,
                reason=str(exc),
                output_dir=args.output_dir,
            )
            for name, path in blocked.items():
                print(f"blocked_{name}: {path}", file=sys.stderr)
        except (TransformerStatePanelError, OSError, ValueError):
            pass
        print(f"Transformer-state run failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
