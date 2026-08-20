"""Artifact orchestration for W16-W18 Transformer-state research stages."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model_test.transformer_state_execution import (
    ExecutionConfig,
    assert_summary_reconstructs,
    execute_state_decisions,
)
from model_test.transformer_state_model import (
    TransformerStateError,
    encode_sequences,
    restore_transformer_checkpoint,
)
from model_test.transformer_state_panel import (
    FEATURE_SCHEMA_NAME,
    LABEL_PANEL_NAME,
    PANEL_MANIFEST_NAME,
    SEQUENCE_PANEL_NAME,
    SOURCE_MANIFEST_NAME,
    SPLITS_NAME,
    TransformerStatePanelError,
    _json_object,
    _sha256_file,
    _snapshot_inventory,
    load_transformer_state_config,
    transformer_code_lock,
)
from model_test.transformer_state_retrieval import (
    FallbackAudit,
    RetrievalConfig,
    StateRetrievalError,
    run_state_retrieval,
)


MODEL_MANIFEST_NAME = "transformer_state_model_manifest.json"
RETRIEVAL_MANIFEST_NAME = "state_retrieval_manifest.json"
EXECUTION_MANIFEST_NAME = "state_execution_manifest.json"
EVIDENCE_MANIFEST_NAME = "transformer_state_evidence_manifest.json"

_PHASE_MANIFEST_NAMES = {
    "W13": SOURCE_MANIFEST_NAME,
    "W14": PANEL_MANIFEST_NAME,
    "W15": MODEL_MANIFEST_NAME,
    "W16": RETRIEVAL_MANIFEST_NAME,
    "W17": EXECUTION_MANIFEST_NAME,
    "W18": EVIDENCE_MANIFEST_NAME,
}

_US_EXACT_DAILY_MODEL_IDS = {
    "drift",
    "fsm",
    "naive",
    "rsm_adaptive_v1",
    "sm",
    "sm_bayesian",
    "sm_bayesian_ml_lgbm",
}


class TransformerStatePipelineError(ValueError):
    """Raised when a W16-W18 source lock or artifact contract is invalid."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _membership_mask(frame: pd.DataFrame, split_id: str, role: str) -> np.ndarray:
    values: list[bool] = []
    for raw in frame["split_memberships_json"].fillna("[]"):
        try:
            memberships = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise TransformerStatePipelineError("split_memberships_json is invalid") from exc
        values.append(
            any(
                str(item.get("split_id")) == split_id and str(item.get("role")) == role
                for item in memberships
            )
        )
    return np.asarray(values, dtype=bool)


def _stack_sequences(frame: pd.DataFrame) -> np.ndarray:
    try:
        return np.stack(
            [np.stack(value).astype(np.float64, copy=False) for value in frame["sequence_values"]]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TransformerStatePipelineError("sequence panel arrays are malformed") from exc


def _artifact_descriptor(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _verify_hash(path: Path, expected_sha256: str, description: str) -> None:
    if not path.is_file() or _sha256_file(path) != expected_sha256:
        raise TransformerStatePipelineError(f"{description} is missing or hash-drifted: {path}")


def _target_dir(root: Path, config: Mapping[str, Any], output_dir: str | Path | None) -> Path:
    target = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / "model-test" / "outputs" / str(config["output_subdir"])).resolve()
    )
    source_paths = [
        (root / str(config["sources"][key])).resolve()
        for key in ("phase_a_output_dir", "phase_b_output_dir", "full_run_output_dir")
    ]
    for source in source_paths:
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise TransformerStatePipelineError(
                f"Transformer output directory collides with frozen source directory: {source}"
            )
    return target


def _verify_manifest_artifact(
    target: Path,
    manifest: Mapping[str, Any],
    key: str,
) -> Path:
    descriptor = (manifest.get("artifacts") or {}).get(key)
    if not isinstance(descriptor, Mapping) or not descriptor.get("path") or not descriptor.get("sha256"):
        raise TransformerStatePipelineError(f"manifest lacks artifact descriptor: {key}")
    path = (target / str(descriptor["path"])).resolve()
    if not path.is_relative_to(target):
        raise TransformerStatePipelineError(f"artifact path escapes output directory: {path}")
    _verify_hash(path, str(descriptor["sha256"]), key)
    return path


def _verify_fixed_manifest_artifact(
    target: Path,
    manifest: Mapping[str, Any],
    key: str,
    filename: str,
) -> Path:
    path = _verify_manifest_artifact(target, manifest, key)
    expected = (target / filename).resolve()
    if path != expected:
        raise TransformerStatePipelineError(
            f"manifest artifact {key} must resolve to the fixed path {filename}"
        )
    return path


def _load_ready_manifests(
    root: Path,
    config_file: Path,
    config: Mapping[str, Any],
    target: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifests = []
    for filename, phase in (
        (SOURCE_MANIFEST_NAME, "W13"),
        (PANEL_MANIFEST_NAME, "W14"),
        (MODEL_MANIFEST_NAME, "W15"),
    ):
        path = target / filename
        if not path.is_file():
            raise TransformerStatePipelineError(f"{phase} manifest is missing: {path}")
        manifest = _json_object(path)
        if manifest.get("status") != "ready":
            raise TransformerStatePipelineError(f"{phase} is not ready")
        manifests.append(manifest)
    source, panel, model = manifests
    config_hash = _sha256_file(config_file)
    source_path = target / SOURCE_MANIFEST_NAME
    panel_path = target / PANEL_MANIFEST_NAME
    if source.get("config_sha256") != config_hash or source.get("market") != config["market"]:
        raise TransformerStatePipelineError("W13 config/market hash drifted before W16")
    if panel.get("config_sha256") != config_hash:
        raise TransformerStatePipelineError("W14 config hash drifted before W16")
    if panel.get("source_manifest_sha256") != _sha256_file(source_path):
        raise TransformerStatePipelineError("W13 source manifest drifted before W16")
    if model.get("source_lock", {}).get("config_sha256") != config_hash:
        raise TransformerStatePipelineError("W15 config hash drifted before W16")
    model_lock = model.get("source_lock", {})
    expected_model_hashes = {
        "source_manifest_sha256": _sha256_file(source_path),
        "panel_manifest_sha256": _sha256_file(panel_path),
    }
    for key, expected in expected_model_hashes.items():
        if model_lock.get(key) != expected:
            raise TransformerStatePipelineError(f"W15 source lock drifted: {key}")
    verified = {
        "sequence_panel_sha256": _sha256_file(
            _verify_fixed_manifest_artifact(
                target, panel, "state_sequence_panel", SEQUENCE_PANEL_NAME
            )
        ),
        "feature_schema_sha256": _sha256_file(
            _verify_fixed_manifest_artifact(target, panel, "feature_schema", FEATURE_SCHEMA_NAME)
        ),
        "splits_sha256": _sha256_file(
            _verify_fixed_manifest_artifact(target, panel, "walk_forward_splits", SPLITS_NAME)
        ),
    }
    _verify_fixed_manifest_artifact(target, panel, "state_label_panel", LABEL_PANEL_NAME)
    for key, expected in verified.items():
        if model_lock.get(key) != expected:
            raise TransformerStatePipelineError(f"W15 artifact source lock drifted: {key}")
    current_lock = transformer_code_lock(root)
    locked = model.get("source_lock", {}).get("code_lock", {}).get("aggregate_sha256")
    if locked != current_lock["aggregate_sha256"]:
        raise TransformerStatePipelineError("Transformer implementation changed after W15 training")
    return source, panel, model


def _memory_rows(
    sequences: pd.DataFrame,
    labels: pd.DataFrame,
    mask: np.ndarray,
    *,
    split_id: str,
    source_sha256: str,
    encoder_sha256: str,
    feature_schema_sha256: str,
) -> pd.DataFrame:
    selected = sequences.loc[
        mask,
        ["date", "symbol", "market", "best_expert_5d", "label_margin", "label_status"],
    ].copy()
    selected["date"] = pd.to_datetime(selected["date"], errors="raise").dt.normalize()
    selected = selected[selected["label_status"].eq("ready") & selected["best_expert_5d"].notna()]
    label_values = labels[
        [
            "date",
            "symbol",
            "expert_id",
            "future_utility",
            "future_net_return",
            "future_downside",
        ]
    ].copy()
    label_values["date"] = pd.to_datetime(label_values["date"], errors="raise").dt.normalize()
    label_values = label_values.rename(columns={"expert_id": "best_expert_5d"})
    selected = selected.merge(
        label_values,
        on=["date", "symbol", "best_expert_5d"],
        how="left",
        validate="one_to_one",
    )
    selected = selected.rename(
        columns={
            "future_utility": "future_5d_utility",
            "future_net_return": "future_5d_net_return",
            "future_downside": "future_5d_downside",
        }
    )
    required = ["future_5d_utility", "future_5d_net_return", "future_5d_downside", "label_margin"]
    for column in required:
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    if not np.isfinite(selected[required].to_numpy(dtype=float)).all():
        raise TransformerStatePipelineError(f"{split_id} train labels lack realized utility components")
    selected["future_5d_drawdown"] = -selected.pop("future_5d_downside").abs()
    selected["label_status"] = "available"
    selected["split_id"] = split_id
    selected["role"] = "train"
    selected["source_manifest_sha256"] = source_sha256
    selected["encoder_sha256"] = encoder_sha256
    selected["feature_schema_sha256"] = feature_schema_sha256
    return selected.reset_index(drop=True)


def _query_rows(
    sequences: pd.DataFrame,
    labels: pd.DataFrame,
    mask: np.ndarray,
    embeddings: np.ndarray,
    *,
    split_id: str,
    source_sha256: str,
    encoder_sha256: str,
    feature_schema_sha256: str,
) -> pd.DataFrame:
    query = sequences.loc[mask, ["date", "symbol", "market"]].copy().reset_index(drop=True)
    query["date"] = pd.to_datetime(query["date"], errors="raise").dt.normalize()
    query["split_id"] = split_id
    query["embedding"] = [row.tolist() for row in embeddings]
    query["source_manifest_sha256"] = source_sha256
    query["encoder_sha256"] = encoder_sha256
    query["feature_schema_sha256"] = feature_schema_sha256
    availability = labels.loc[
        labels["expert_status"].astype(str).eq("available"),
        ["date", "symbol", "expert_id"],
    ].copy()
    availability["date"] = pd.to_datetime(availability["date"], errors="raise").dt.normalize()
    availability = (
        availability.groupby(["date", "symbol"], sort=False)["expert_id"]
        .agg(lambda values: json.dumps(sorted(set(values.astype(str)))))
        .rename("available_experts_json")
        .reset_index()
    )
    query = query.merge(availability, on=["date", "symbol"], how="left", validate="one_to_one")
    if query["available_experts_json"].isna().any():
        raise TransformerStatePipelineError(f"{split_id} query expert availability is missing")
    return query


def _fallback_audit(root: Path, config: Mapping[str, Any]) -> FallbackAudit:
    sources = config["sources"]
    guard = config["full_run_best_guard"]
    full_run = (root / str(sources["full_run_output_dir"])).resolve()
    summary_path = full_run / "model_summary.csv"
    manifest_path = full_run / "data_manifest.json"
    _verify_hash(
        summary_path,
        str(sources["full_run_model_summary_sha256"]),
        "frozen full-run summary",
    )
    _verify_hash(
        manifest_path,
        str(sources["full_run_source_manifest_sha256"]),
        "frozen full-run source manifest",
    )
    return FallbackAudit(
        fallback_policy="full_run_best_guard",
        fallback_source_run=str(guard["authoritative_run"]),
        fallback_source_model_id=str(guard["source_model_id"]),
        fallback_expert_id=str(guard["expert_id"]),
        fallback_summary_sha256=_sha256_file(summary_path),
        fallback_source_manifest_sha256=_sha256_file(manifest_path),
    )


def materialize_state_retrieval(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run W16 fold-local train memory construction and test-only retrieval."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = _target_dir(root, config, output_dir)
    _, panel_manifest, model_manifest = _load_ready_manifests(
        root, config_file, config, target
    )
    try:
        sequences = pd.read_parquet(target / SEQUENCE_PANEL_NAME)
        labels = pd.read_parquet(target / LABEL_PANEL_NAME)
        splits = pd.read_csv(target / SPLITS_NAME)
    except (OSError, ValueError, ImportError) as exc:
        raise TransformerStatePipelineError("W16 could not read W14 panels") from exc
    sequence_values = _stack_sequences(sequences)
    source_sha = _sha256_file(target / SOURCE_MANIFEST_NAME)
    feature_schema_sha = _sha256_file(target / FEATURE_SCHEMA_NAME)
    retrieval_config = RetrievalConfig.from_mapping(config)
    fallback = _fallback_audit(root, config)
    memories: list[pd.DataFrame] = []
    distributions: list[pd.DataFrame] = []
    decisions: list[pd.DataFrame] = []
    thresholds: dict[str, Any] = {}
    folds: list[dict[str, Any]] = []

    model_fold_entries = model_manifest.get("folds", [])
    fold_manifests = {str(item["split_id"]): item for item in model_fold_entries}
    split_ids = splits["split_id"].astype(str).tolist()
    if (
        len(model_fold_entries) != len(fold_manifests)
        or set(fold_manifests) != set(split_ids)
        or any(item.get("status") != "ready" for item in model_fold_entries)
    ):
        raise TransformerStatePipelineError("W15 fold manifest coverage differs from W14 splits")
    expected_fold_lock = _expected_w15_fold_source_lock(root, config_file, target, panel_manifest)
    for split_id in splits["split_id"].astype(str):
        fold_entry = fold_manifests.get(split_id)
        if not fold_entry or fold_entry.get("status") != "ready":
            raise TransformerStatePipelineError(f"{split_id} W15 checkpoint is not ready")
        fold_manifest, fold_artifacts = _verify_w15_fold_manifest(
            target,
            fold_entry,
            market=str(config["market"]),
            expected_source_lock=expected_fold_lock,
        )
        encoder_path = fold_artifacts["transformer_encoder"]
        encoder_sha = _sha256_file(encoder_path)
        model, scaler, schema = restore_transformer_checkpoint(encoder_path)
        if schema.get("feature_schema_sha256") != feature_schema_sha:
            raise TransformerStatePipelineError(f"{split_id} embedding feature schema drifted")
        train_mask = _membership_mask(sequences, split_id, "train")
        test_mask = _membership_mask(sequences, split_id, "test")
        if not train_mask.any() or not test_mask.any():
            raise TransformerStatePipelineError(f"{split_id} lacks train/test sequences")
        train_all = sequences.loc[train_mask].reset_index(drop=True)
        train_ready = train_all["label_status"].eq("ready") & train_all["best_expert_5d"].notna()
        train_embeddings = encode_sequences(
            model,
            scaler,
            sequence_values[train_mask][train_ready.to_numpy()],
        )
        memory_rows = _memory_rows(
            sequences,
            labels,
            train_mask,
            split_id=split_id,
            source_sha256=source_sha,
            encoder_sha256=encoder_sha,
            feature_schema_sha256=feature_schema_sha,
        )
        if len(memory_rows) != len(train_embeddings):
            raise TransformerStatePipelineError(f"{split_id} train embedding/label rows are misaligned")
        test_embeddings = encode_sequences(model, scaler, sequence_values[test_mask])
        query_rows = _query_rows(
            sequences,
            labels,
            test_mask,
            test_embeddings,
            split_id=split_id,
            source_sha256=source_sha,
            encoder_sha256=encoder_sha,
            feature_schema_sha256=feature_schema_sha,
        )
        artifacts = run_state_retrieval(
            train_rows=memory_rows,
            train_embeddings=train_embeddings,
            query_rows=query_rows,
            config=retrieval_config,
            fallback=fallback,
            available_experts=set(str(value) for value in config["experts"]),
        )
        fold_decisions = artifacts.decisions.copy()
        for field, value in fallback.payload().items():
            fold_decisions[f"full_run_best_{field}"] = value
        fold_decisions["adaptive_fallback_source_run"] = Path(
            str(config["sources"]["phase_b_output_dir"])
        ).name
        fold_decisions["adaptive_fallback_source_model_id"] = "rsm_adaptive_v1"
        fold_decisions["adaptive_fallback_summary_sha256"] = str(
            config["sources"]["phase_b_manifest_sha256"]
        )
        fold_decisions["adaptive_fallback_source_manifest_sha256"] = source_sha
        memories.append(artifacts.memory_bank)
        distributions.append(artifacts.similarity_distribution)
        decisions.append(fold_decisions)
        thresholds[split_id] = artifacts.thresholds
        matched = fold_decisions["decision_status"].eq("matched")
        folds.append(
            {
                "split_id": split_id,
                "status": "ready",
                "memory_row_count": int(len(artifacts.memory_bank)),
                "test_query_count": int(len(query_rows)),
                "decision_row_count": int(len(fold_decisions)),
                "matched_decision_count": int(matched.sum()),
                "matched_decision_coverage": float(matched.mean()),
                "thresholds": artifacts.thresholds,
                "encoder_sha256": encoder_sha,
            }
        )

    memory = pd.concat(memories, ignore_index=True)
    distribution = pd.concat(distributions, ignore_index=True)
    decision_frame = pd.concat(decisions, ignore_index=True)
    memory_path = target / "state_memory_bank.parquet"
    distribution_path = target / "state_similarity_distribution.csv"
    thresholds_path = target / "state_thresholds.json"
    decisions_path = target / "state_match_decisions.parquet"
    report_path = target / "state_retrieval_report.md"
    memory.to_parquet(memory_path, index=False)
    distribution.to_csv(distribution_path, index=False)
    _json_write(thresholds_path, {"schema_version": "1.0", "folds": thresholds})
    decision_frame.to_parquet(decisions_path, index=False)
    report_lines = [
        "# W16 State Retrieval Report",
        "",
        f"- Market: `{config['market']}`",
        f"- Memory scope: `split_train_only`",
        f"- Fold count: `{len(folds)}`",
        f"- Decision rows: `{len(decision_frame)}`",
        "",
        "| Split | Memory rows | Queries | Matched coverage |",
        "|---|---:|---:|---:|",
    ]
    report_lines.extend(
        f"| {fold['split_id']} | {fold['memory_row_count']} | {fold['test_query_count']} | "
        f"{fold['matched_decision_coverage']:.2%} |"
        for fold in folds
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "phase": "W16",
        "status": "ready",
        "created_at": _utc_now(),
        "market": config["market"],
        "fold_count": len(folds),
        "folds": folds,
        "memory_scope": "split_train_only",
        "threshold_source": "fold_train_strictly_prior",
        "source_lock": {
            "config_sha256": _sha256_file(config_file),
            "source_manifest_sha256": source_sha,
            "panel_manifest_sha256": _sha256_file(target / PANEL_MANIFEST_NAME),
            "model_manifest_sha256": _sha256_file(target / MODEL_MANIFEST_NAME),
            "feature_schema_sha256": feature_schema_sha,
            "label_panel_sha256": _sha256_file(target / LABEL_PANEL_NAME),
            "splits_sha256": _sha256_file(target / SPLITS_NAME),
            "code_lock": transformer_code_lock(root),
        },
        "full_run_best_only": {
            "expert_id": fallback.fallback_expert_id,
            "source_run": fallback.fallback_source_run,
        },
        "artifacts": {},
    }
    manifest["artifacts"] = {
        "state_memory_bank": _artifact_descriptor(memory_path, relative_to=target),
        "state_similarity_distribution": _artifact_descriptor(
            distribution_path, relative_to=target
        ),
        "state_thresholds": _artifact_descriptor(thresholds_path, relative_to=target),
        "state_match_decisions": _artifact_descriptor(decisions_path, relative_to=target),
        "state_retrieval_report": _artifact_descriptor(report_path, relative_to=target),
    }
    manifest_path = target / RETRIEVAL_MANIFEST_NAME
    _json_write(manifest_path, manifest)
    return manifest, manifest_path


def _load_execution_market_data(root: Path, config: Mapping[str, Any]) -> pd.DataFrame:
    snapshot_dir = root / str(config["sources"]["full_run_output_dir"]) / "data_snapshot"
    frames: list[pd.DataFrame] = []
    for path in sorted(snapshot_dir.glob("*_daily.csv")):
        frame = pd.read_csv(path, usecols=["date", "high", "low", "close", "symbol", "market"])
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
        frame = frame.sort_values("date")
        previous_close = frame["close"].shift(1)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous_close).abs(),
                (frame["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr_pct"] = true_range.rolling(14, min_periods=5).mean() / frame["close"].abs()
        frames.append(frame[["date", "symbol", "market", "close", "atr_pct"]])
    if not frames:
        raise TransformerStatePipelineError(f"no frozen daily OHLCV found in {snapshot_dir}")
    return pd.concat(frames, ignore_index=True)


def _resolve_w15_fold_output_dir(target: Path, split_id: Any) -> Path:
    split_id = str(split_id or "")
    if (
        not split_id
        or split_id in {".", ".."}
        or "/" in split_id
        or "\\" in split_id
        or Path(split_id).name != split_id
    ):
        raise TransformerStatePipelineError(f"W15 split_id is not a safe path component: {split_id!r}")
    fold_root = (target / "folds").resolve()
    fold_dir = (fold_root / split_id).resolve()
    if fold_dir.parent != fold_root:
        raise TransformerStatePipelineError(f"W15 fold directory escapes output root: {fold_dir}")
    return fold_dir


def _resolve_w15_fold_manifest(target: Path, item: Mapping[str, Any]) -> Path:
    split_id = str(item.get("split_id") or "")
    described = (target / str(item.get("manifest_path") or "")).resolve()
    expected = _resolve_w15_fold_output_dir(target, split_id) / "manifest.json"
    if not split_id or not described.is_relative_to(target) or described != expected:
        raise TransformerStatePipelineError(f"W15 fold manifest path is invalid for {split_id!r}")
    return described


def _expected_w15_fold_source_lock(
    root: Path,
    config_file: Path,
    target: Path,
    panel_manifest: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "config_sha256": _sha256_file(config_file),
        "source_manifest_sha256": _sha256_file(target / SOURCE_MANIFEST_NAME),
        "panel_manifest_sha256": _sha256_file(target / PANEL_MANIFEST_NAME),
        "sequence_panel_sha256": _sha256_file(
            _verify_manifest_artifact(target, panel_manifest, "state_sequence_panel")
        ),
        "feature_schema_sha256": _sha256_file(
            _verify_manifest_artifact(target, panel_manifest, "feature_schema")
        ),
        "code_lock_aggregate_sha256": transformer_code_lock(root)["aggregate_sha256"],
    }


def _verify_w15_fold_manifest(
    target: Path,
    item: Mapping[str, Any],
    *,
    market: str,
    expected_source_lock: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Path]]:
    fold_manifest_path = _resolve_w15_fold_manifest(target, item)
    split_id = str(item["split_id"])
    _verify_hash(
        fold_manifest_path,
        str(item.get("manifest_sha256") or ""),
        f"{split_id} W15 manifest",
    )
    fold_manifest = _json_object(fold_manifest_path)
    if (
        item.get("status") != "ready"
        or fold_manifest.get("status") != "ready"
        or fold_manifest.get("market") != market
        or str(fold_manifest.get("split_id")) != split_id
    ):
        raise TransformerStatePipelineError(f"{split_id} W15 fold identity/status drifted")
    fold_lock = fold_manifest.get("source_lock", {})
    for key, expected in expected_source_lock.items():
        if fold_lock.get(key) != expected:
            raise TransformerStatePipelineError(f"{split_id} W15 fold source lock drifted: {key}")
    required_artifacts = {
        "transformer_encoder",
        "state_embedding_schema",
        "train_metrics",
        "validation_metrics",
        "training_log",
    }
    artifacts = fold_manifest.get("artifacts", {})
    if not isinstance(artifacts, Mapping) or not required_artifacts.issubset(artifacts):
        raise TransformerStatePipelineError(f"{split_id} W15 fold artifacts are incomplete")
    fold_dir = fold_manifest_path.parent
    paths: dict[str, Path] = {}
    for key, descriptor in artifacts.items():
        if not isinstance(descriptor, Mapping) or not descriptor.get("path") or not descriptor.get("sha256"):
            raise TransformerStatePipelineError(f"{split_id} lacks W15 artifact {key}")
        artifact_path = (fold_dir / str(descriptor["path"])).resolve()
        if not artifact_path.is_relative_to(fold_dir):
            raise TransformerStatePipelineError(f"{split_id} W15 artifact path escapes fold directory")
        _verify_hash(artifact_path, str(descriptor["sha256"]), f"{split_id} {key}")
        paths[str(key)] = artifact_path
    return fold_manifest, paths


def materialize_state_execution(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run W17 non-overlapping five-day execution and write reconstructible evidence."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = _target_dir(root, config, output_dir)
    source_manifest, panel_manifest, model_manifest = _load_ready_manifests(
        root,
        config_file,
        config,
        target,
    )
    model_folds = model_manifest.get("folds", [])
    model_fold_ids = [str(item.get("split_id")) for item in model_folds]
    if len(model_folds) != 4 or len(set(model_fold_ids)) != 4:
        raise TransformerStatePipelineError("W17 requires four distinct W15 folds")
    expected_fold_lock = _expected_w15_fold_source_lock(root, config_file, target, panel_manifest)
    for item in model_folds:
        _verify_w15_fold_manifest(
            target,
            item,
            market=str(config["market"]),
            expected_source_lock=expected_fold_lock,
        )
    retrieval_path = target / RETRIEVAL_MANIFEST_NAME
    if not retrieval_path.is_file():
        raise TransformerStatePipelineError("W17 requires a ready W16 manifest")
    retrieval = _json_object(retrieval_path)
    if retrieval.get("status") != "ready":
        raise TransformerStatePipelineError("W16 is not ready")
    if retrieval.get("source_lock", {}).get("config_sha256") != _sha256_file(config_file):
        raise TransformerStatePipelineError("config drifted after W16")
    label_path = _verify_manifest_artifact(target, panel_manifest, "state_label_panel")
    feature_schema_path = _verify_manifest_artifact(target, panel_manifest, "feature_schema")
    splits_path = _verify_manifest_artifact(target, panel_manifest, "walk_forward_splits")
    retrieval_lock = retrieval.get("source_lock", {})
    expected_retrieval_lock = {
        "config_sha256": _sha256_file(config_file),
        "source_manifest_sha256": _sha256_file(target / SOURCE_MANIFEST_NAME),
        "panel_manifest_sha256": _sha256_file(target / PANEL_MANIFEST_NAME),
        "model_manifest_sha256": _sha256_file(target / MODEL_MANIFEST_NAME),
        "feature_schema_sha256": _sha256_file(feature_schema_path),
        "label_panel_sha256": _sha256_file(label_path),
        "splits_sha256": _sha256_file(splits_path),
    }
    for key, expected in expected_retrieval_lock.items():
        if retrieval_lock.get(key) != expected:
            raise TransformerStatePipelineError(f"W16 source lock drifted before W17: {key}")
    if source_manifest.get("market") != config["market"] or model_manifest.get("market") != config["market"]:
        raise TransformerStatePipelineError("W13/W15 market drifted before W17")
    locked = retrieval_lock.get("code_lock", {}).get("aggregate_sha256")
    if locked != transformer_code_lock(root)["aggregate_sha256"]:
        raise TransformerStatePipelineError("Transformer implementation changed after W16")
    decisions_path = _verify_manifest_artifact(target, retrieval, "state_match_decisions")
    decisions = pd.read_parquet(decisions_path)
    phase_b_dir = root / str(config["sources"]["phase_b_output_dir"])
    panel_path = phase_b_dir / "expert_day_panel.parquet"
    _verify_hash(
        panel_path,
        str(config["sources"]["phase_b_panel_sha256"]),
        "Phase-B expert panel",
    )
    expert_panel = pd.read_parquet(panel_path)
    expert_panel["date"] = pd.to_datetime(expert_panel["date"], errors="raise").dt.normalize()
    label_panel = pd.read_parquet(label_path)
    evaluation_labels = label_panel[
        ["date", "symbol", "market", "expert_id", "future_utility", "best_expert_5d"]
    ].copy()
    evaluation_labels["date"] = pd.to_datetime(
        evaluation_labels["date"], errors="raise"
    ).dt.normalize()
    expert_panel = expert_panel.drop(
        columns=[column for column in ("future_utility", "best_expert_5d") if column in expert_panel]
    ).merge(
        evaluation_labels,
        on=["date", "symbol", "market", "expert_id"],
        how="left",
        validate="one_to_one",
    )
    full_run_dir = (root / str(config["sources"]["full_run_output_dir"])).resolve()
    full_run_manifest_path = full_run_dir / "data_manifest.json"
    _verify_hash(
        full_run_manifest_path,
        str(config["sources"]["full_run_source_manifest_sha256"]),
        "frozen full-run source manifest",
    )
    snapshot = _snapshot_inventory(
        dict(config),
        full_dir=full_run_dir,
        full_manifest=_json_object(full_run_manifest_path),
    )
    source_snapshot = source_manifest.get("market_snapshot", {})
    if (
        snapshot.get("aggregate_sha256") != source_snapshot.get("aggregate_sha256")
        or snapshot.get("file_count") != source_snapshot.get("file_count")
        or set(snapshot.get("symbols", [])) != set(source_snapshot.get("symbols", []))
    ):
        raise TransformerStatePipelineError("frozen market snapshot drifted before W17")
    market_data = _load_execution_market_data(root, config)
    expert_panel = expert_panel.merge(
        market_data,
        on=["date", "symbol", "market"],
        how="left",
        validate="many_to_one",
    )
    if "market_return_1" not in expert_panel:
        raise TransformerStatePipelineError("Phase-B panel lacks market_return_1")
    expert_panel["benchmark_return"] = pd.to_numeric(
        expert_panel["market_return_1"], errors="coerce"
    )
    if not np.isfinite(expert_panel["benchmark_return"].to_numpy(dtype=float)).all():
        raise TransformerStatePipelineError("Phase-B benchmark_return is missing or non-finite")
    if "regime" not in expert_panel:
        expert_panel["regime"] = expert_panel.get("state_market_regime_id_20")
    execution_config = ExecutionConfig.from_mapping(config)
    result = execute_state_decisions(decisions, expert_panel, config=execution_config)
    assert_summary_reconstructs(result.daily_audit, result.summary)
    daily_path = target / "state_execution_daily.parquet"
    summary_path = target / "state_execution_summary.csv"
    skipped_path = target / "state_execution_skipped_decisions.csv"
    report_path = target / "state_execution_report.md"
    result.daily_audit.to_parquet(daily_path, index=False)
    result.summary.to_csv(summary_path, index=False)
    result.skipped_decisions.to_csv(skipped_path, index=False)
    report_lines = [
        "# W17 State Execution Report",
        "",
        f"- Market: `{config['market']}`",
        f"- Daily audit rows: `{len(result.daily_audit)}`",
        f"- Summary rows: `{len(result.summary)}`",
        f"- Skipped overlapping decisions: `{len(result.skipped_decisions)}`",
        "- Return field: `strategy_return` (source-net; no recharge)",
        "- Execution timing: decision close observed on t; position effective from t+1",
    ]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "phase": "W17",
        "status": "ready",
        "created_at": _utc_now(),
        "market": config["market"],
        "fold_count": int(result.daily_audit["split_id"].nunique()),
        "return_field": "strategy_return",
        "cost_treatment": "source_net_no_recharge",
        "execution_config": asdict(execution_config),
        "summary_reconstructs": True,
        "source_lock": {
            "config_sha256": _sha256_file(config_file),
            "retrieval_manifest_sha256": _sha256_file(retrieval_path),
            "phase_b_panel_sha256": _sha256_file(panel_path),
            "label_panel_sha256": _sha256_file(label_path),
            "data_snapshot_sha256": str(snapshot["aggregate_sha256"]),
            "code_lock": transformer_code_lock(root),
        },
        "artifacts": {
            "state_execution_daily": _artifact_descriptor(daily_path, relative_to=target),
            "state_execution_summary": _artifact_descriptor(summary_path, relative_to=target),
            "state_execution_skipped_decisions": _artifact_descriptor(
                skipped_path, relative_to=target
            ),
            "state_execution_report": _artifact_descriptor(report_path, relative_to=target),
        },
    }
    manifest_path = target / EXECUTION_MANIFEST_NAME
    _json_write(manifest_path, manifest)
    return manifest, manifest_path


def _assert_daily_numeric_integrity(daily: pd.DataFrame) -> None:
    numeric_columns = [
        "strategy_return",
        "target_position",
        "decision_target_position",
        "source_expert_strategy_return",
        "source_expert_target_position",
        "counterfactual_no_guard_return",
        "adaptive_return",
        "execution_turnover",
        "equity_before",
        "geometric_return_contribution",
        "full_run_best_only_return",
    ]
    missing = sorted(set(numeric_columns) - set(daily.columns))
    if missing:
        raise TransformerStatePipelineError(f"W17 daily audit lacks numeric fields: {missing}")
    numeric = daily[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=np.float64)).all():
        raise TransformerStatePipelineError("W17 daily execution values are non-finite")
    ordered = daily.assign(
        _target_position=numeric["target_position"],
        _execution_turnover=numeric["execution_turnover"],
    ).sort_values(["split_id", "threshold", "variant", "symbol", "date"], kind="stable")
    previous = ordered.groupby(
        ["split_id", "threshold", "variant", "symbol"], sort=False
    )["_target_position"].shift(1).fillna(0.0)
    expected = (ordered["_target_position"] - previous).abs().to_numpy(dtype=np.float64)
    actual = ordered["_execution_turnover"].to_numpy(dtype=np.float64)
    if not np.allclose(actual, expected, rtol=0.0, atol=1e-12):
        raise TransformerStatePipelineError("W17 execution turnover does not reconstruct from positions")


def _safe_manifest_component(value: Any, *, field: str) -> str:
    if value is None or pd.isna(value):
        raise TransformerStatePipelineError(f"{field} is empty")
    text = str(value)
    if not text or text in {".", ".."} or "/" in text or "\\" in text or Path(text).name != text:
        raise TransformerStatePipelineError(f"{field} is not a safe path component: {text!r}")
    return text


def _verify_us_exact_daily_lineage(
    root: Path,
    config: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if config["market"] != "US":
        return {
            "admission_source_outputs_overwritten": False,
            "frozen_full_run_returns_modified": False,
            "exact_daily_artifacts_added": False,
            "exact_daily_artifact_count_verified": 0,
            "adaptive_exact_daily_artifact_count_verified": 0,
        }
    lineage = source_manifest.get("exact_daily_lineage", {})
    full_run = (root / str(config["sources"]["full_run_output_dir"])).resolve()
    backfill_path = full_run / "exact_daily_backfill_manifest.json"
    adaptive_path = full_run / "adaptive_exact_daily_replay_manifest.json"
    _verify_hash(
        backfill_path,
        str(lineage.get("backfill_manifest_sha256") or ""),
        "exact daily backfill manifest",
    )
    _verify_hash(
        adaptive_path,
        str(lineage.get("adaptive_replay_manifest_sha256") or ""),
        "adaptive exact daily manifest",
    )
    backfill = _json_object(backfill_path)
    adaptive = _json_object(adaptive_path)
    backfill_entries = backfill.get("artifacts", [])
    adaptive_entries = adaptive.get("artifacts", [])
    expected_backfill = int(lineage.get("artifact_count", 0))
    expected_adaptive = int(lineage.get("adaptive_artifact_count", 0))
    if (
        backfill.get("status") != "ready"
        or backfill.get("market") != "US"
        or int(backfill.get("artifact_count", 0)) != expected_backfill
        or len(backfill_entries) != expected_backfill
        or adaptive.get("status") != "ready"
        or adaptive.get("market") != "US"
        or int(adaptive.get("adaptive_artifact_count", 0)) != expected_adaptive
        or len(adaptive_entries) != expected_adaptive
    ):
        raise TransformerStatePipelineError("exact daily lineage manifests are incomplete")
    backfill_model_ids = {
        _safe_manifest_component(value, field="exact-daily expert model_id")
        for value in backfill.get("expert_model_ids", [])
    }
    if backfill_model_ids != _US_EXACT_DAILY_MODEL_IDS:
        raise TransformerStatePipelineError("exact daily expert model set drifted")

    seen: set[tuple[str, str]] = set()
    proof_tolerance = float(backfill.get("return_tolerance", 0.0))
    if not np.isfinite(proof_tolerance) or proof_tolerance < 0:
        raise TransformerStatePipelineError("exact daily proof tolerance is invalid")
    for entry in backfill_entries:
        symbol = _safe_manifest_component(entry.get("symbol"), field="exact-daily symbol")
        model_id = _safe_manifest_component(entry.get("model_id"), field="exact-daily model_id")
        key = (symbol, model_id)
        if key in seen:
            raise TransformerStatePipelineError(f"duplicate exact daily lineage entry: {key}")
        seen.add(key)
        artifact_dir = (full_run / "artifacts" / symbol / "main" / model_id).resolve()
        if not artifact_dir.is_relative_to(full_run):
            raise TransformerStatePipelineError("exact daily artifact path escapes full-run directory")
        _verify_hash(
            artifact_dir / "returns.csv",
            str(entry.get("source_returns_sha256") or ""),
            f"{symbol}/{model_id} frozen returns",
        )
        _verify_hash(
            artifact_dir / "daily.csv",
            str(entry.get("daily_sha256") or ""),
            f"{symbol}/{model_id} exact daily",
        )
        if (
            int(entry.get("row_count", 0)) <= 0
            or not np.isfinite(float(entry.get("return_max_abs_diff", np.nan)))
            or float(entry.get("return_max_abs_diff", np.inf)) > proof_tolerance
            or not np.isfinite(float(entry.get("turnover_max_abs_diff", np.nan)))
            or float(entry.get("turnover_max_abs_diff", np.inf)) > proof_tolerance
        ):
            raise TransformerStatePipelineError(f"{symbol}/{model_id} exact daily proof is invalid")
    exact_symbols = {symbol for symbol, _ in seen}
    expected_symbols = set(source_manifest.get("market_snapshot", {}).get("symbols", []))
    expected_grid = {
        (symbol, model_id)
        for symbol in expected_symbols
        for model_id in _US_EXACT_DAILY_MODEL_IDS
    }
    if len(expected_symbols) != 60 or seen != expected_grid:
        raise TransformerStatePipelineError("exact daily artifacts do not cover the frozen 60x7 grid")

    adaptive_seen: set[str] = set()
    for entry in adaptive_entries:
        symbol = _safe_manifest_component(entry.get("symbol"), field="adaptive exact-daily symbol")
        if symbol in adaptive_seen:
            raise TransformerStatePipelineError(f"duplicate adaptive exact daily entry: {symbol}")
        adaptive_seen.add(symbol)
        artifact_dir = (full_run / "artifacts" / symbol / "main" / "rsm_adaptive_v1").resolve()
        _verify_hash(
            artifact_dir / "returns.csv",
            str(entry.get("source_returns_sha256") or ""),
            f"{symbol}/rsm_adaptive_v1 frozen returns",
        )
        _verify_hash(
            artifact_dir / "daily.csv",
            str(entry.get("daily_sha256") or ""),
            f"{symbol}/rsm_adaptive_v1 exact daily",
        )
        if (
            int(entry.get("row_count", 0)) <= 0
            or not np.isfinite(float(entry.get("return_max_abs_diff", np.nan)))
            or float(entry.get("return_max_abs_diff", np.inf)) > 1e-12
            or not np.isfinite(float(entry.get("turnover_max_abs_diff", np.nan)))
            or float(entry.get("turnover_max_abs_diff", np.inf)) > 1e-12
        ):
            raise TransformerStatePipelineError(f"{symbol}/rsm_adaptive_v1 proof is invalid")
    if adaptive_seen != exact_symbols:
        raise TransformerStatePipelineError("adaptive exact daily artifacts do not cover all symbols")

    expected_patch = lineage.get("source_runtime_patch", {})
    actual_patch = adaptive.get("source_runtime_patch", {})
    if actual_patch != expected_patch or not actual_patch.get("dirty"):
        raise TransformerStatePipelineError("adaptive source runtime patch lineage drifted")
    runtime_dir = Path(str(adaptive.get("source_runtime_dir") or "")).resolve()
    if not runtime_dir.is_relative_to(root):
        raise TransformerStatePipelineError("adaptive source runtime path escapes repository")
    patch_path = str(actual_patch.get("allowed_patch_path") or "")
    patched_file = (runtime_dir / patch_path).resolve()
    if not patched_file.is_relative_to(runtime_dir):
        raise TransformerStatePipelineError("adaptive runtime patch path escapes source runtime")
    _verify_hash(
        patched_file,
        str(actual_patch.get("patched_file_sha256") or ""),
        "adaptive patched runtime file",
    )
    try:
        commit = subprocess.run(
            ["git", "-C", str(runtime_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(runtime_dir), "status", "--short", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        completed = subprocess.run(
            ["git", "-C", str(runtime_dir), "diff", "--binary", "--", patch_path],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TransformerStatePipelineError("adaptive source runtime patch cannot be reproduced") from exc
    changed = [line[3:].replace("\\", "/") for line in status if line.strip()]
    if commit != str(adaptive.get("source_commit") or "") or changed != [patch_path.replace("\\", "/")]:
        raise TransformerStatePipelineError("adaptive source runtime commit/dirty paths drifted")
    patch_sha = hashlib.sha256(completed.stdout).hexdigest()
    if patch_sha != str(actual_patch.get("allowed_patch_sha256") or ""):
        raise TransformerStatePipelineError("adaptive source runtime patch hash drifted")
    return {
        "admission_source_outputs_overwritten": False,
        "frozen_full_run_returns_modified": False,
        "exact_daily_artifacts_added": True,
        "exact_daily_artifact_count_verified": len(backfill_entries),
        "adaptive_exact_daily_artifact_count_verified": len(adaptive_entries),
    }


def _assert_execution_evidence_complete(
    decisions: pd.DataFrame,
    daily: pd.DataFrame,
    skipped: pd.DataFrame,
    *,
    expected_variants: set[str],
    holding_days: int,
) -> None:
    decision_columns = ["split_id", "date", "symbol", "market", "threshold_variant"]
    daily_marker_columns = ["split_id", "decision_date", "symbol", "market", "threshold"]
    skipped_columns = ["split_id", "date", "symbol", "market", "threshold"]
    for frame, columns, label in (
        (decisions, decision_columns, "W16 decisions"),
        (daily, [*daily_marker_columns, "variant"], "W17 daily markers"),
        (skipped, [*skipped_columns, "variant"], "W17 skipped decisions"),
    ):
        missing = sorted(set(columns) - set(frame.columns))
        if missing:
            raise TransformerStatePipelineError(f"{label} lacks identity columns: {missing}")

    decision_keys = decisions[decision_columns].copy()
    decision_keys["date"] = pd.to_datetime(decision_keys["date"], errors="coerce")
    if decision_keys["date"].isna().any() or decision_keys.duplicated().any():
        raise TransformerStatePipelineError("W16 decision identities are invalid or duplicated")
    decision_keys = decision_keys.rename(columns={"threshold_variant": "threshold"})
    expected_keys = set(decision_keys.itertuples(index=False, name=None))

    daily_key_columns = ["split_id", "date", "symbol", "market", "threshold", "variant"]
    if daily.duplicated(daily_key_columns).any():
        raise TransformerStatePipelineError("W17 daily execution identities are duplicated")
    window_columns = ["split_id", "symbol", "market", "threshold", "variant", "decision_date"]
    window_sizes = daily.groupby(window_columns, dropna=False).size()
    if window_sizes.empty or not window_sizes.eq(holding_days).all():
        raise TransformerStatePipelineError("W17 execution windows are not complete holding periods")
    holding_numbers = pd.to_numeric(daily["holding_day"], errors="coerce")
    expected_holding_numbers = set(range(1, holding_days + 1))
    holding_sets = daily.assign(_holding_day=holding_numbers).groupby(window_columns, dropna=False)[
        "_holding_day"
    ].agg(lambda values: set(values.astype(int)) if values.notna().all() else set())
    if any(values != expected_holding_numbers for values in holding_sets):
        raise TransformerStatePipelineError("W17 holding-day sequence is incomplete")
    marker_counts = daily.assign(_marker=daily["decision_marker"].astype(bool)).groupby(
        window_columns, dropna=False
    )["_marker"].sum()
    if not marker_counts.eq(1).all():
        raise TransformerStatePipelineError("W17 execution windows must contain one decision marker")

    markers = daily.loc[daily["decision_marker"].astype(bool), [*daily_marker_columns, "variant"]].copy()
    markers["decision_date"] = pd.to_datetime(markers["decision_date"], errors="coerce")
    skipped_keys = skipped[[*skipped_columns, "variant"]].copy()
    skipped_keys["date"] = pd.to_datetime(skipped_keys["date"], errors="coerce")
    if markers["decision_date"].isna().any() or skipped_keys["date"].isna().any():
        raise TransformerStatePipelineError("W17 executed/skipped decision dates are invalid")
    markers = markers.rename(columns={"decision_date": "date"})
    for variant in expected_variants:
        executed_variant = markers.loc[markers["variant"].astype(str).eq(variant)].drop(columns="variant")
        skipped_variant = skipped_keys.loc[
            skipped_keys["variant"].astype(str).eq(variant)
        ].drop(columns="variant")
        if executed_variant.duplicated().any() or skipped_variant.duplicated().any():
            raise TransformerStatePipelineError(f"W17 {variant} decision audit identities are duplicated")
        executed_set = set(executed_variant.itertuples(index=False, name=None))
        skipped_set = set(skipped_variant.itertuples(index=False, name=None))
        if executed_set & skipped_set or executed_set | skipped_set != expected_keys:
            raise TransformerStatePipelineError(
                f"W17 {variant} executed/skipped audit does not exactly cover W16 decisions"
            )


def materialize_full_evidence_manifest(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Seal the W18 market-specific W13-W17 evidence chain without modifying source outputs."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = _target_dir(root, config, output_dir)
    phases = {
        "W13": target / SOURCE_MANIFEST_NAME,
        "W14": target / PANEL_MANIFEST_NAME,
        "W15": target / MODEL_MANIFEST_NAME,
        "W16": target / RETRIEVAL_MANIFEST_NAME,
        "W17": target / EXECUTION_MANIFEST_NAME,
    }
    entries: dict[str, Any] = {}
    values: dict[str, dict[str, Any]] = {}
    for phase, path in phases.items():
        if not path.is_file():
            raise TransformerStatePipelineError(f"{phase} manifest is missing")
        value = _json_object(path)
        if value.get("status") != "ready":
            raise TransformerStatePipelineError(f"{phase} is not ready")
        if value.get("market") != config["market"]:
            raise TransformerStatePipelineError(f"{phase} market differs from config")
        values[phase] = value
        entries[phase] = {
            "path": path.relative_to(target).as_posix(),
            "sha256": _sha256_file(path),
            "status": "ready",
        }
    source = values["W13"]
    panel = values["W14"]
    model = values["W15"]
    retrieval = values["W16"]
    execution = values["W17"]
    config_sha = _sha256_file(config_file)
    current_code = transformer_code_lock(root)
    current_code_sha = current_code["aggregate_sha256"]
    if source.get("config_sha256") != config_sha or panel.get("config_sha256") != config_sha:
        raise TransformerStatePipelineError("W13/W14 config lock drifted before evidence sealing")
    if panel.get("source_manifest_sha256") != _sha256_file(phases["W13"]):
        raise TransformerStatePipelineError("W14 no longer references the current W13 manifest")
    if model.get("source_lock", {}).get("panel_manifest_sha256") != _sha256_file(phases["W14"]):
        raise TransformerStatePipelineError("W15 no longer references the current W14 manifest")
    if retrieval.get("source_lock", {}).get("model_manifest_sha256") != _sha256_file(phases["W15"]):
        raise TransformerStatePipelineError("W16 no longer references the current W15 manifest")
    if execution.get("source_lock", {}).get("retrieval_manifest_sha256") != _sha256_file(
        phases["W16"]
    ):
        raise TransformerStatePipelineError("W17 no longer references the current W16 manifest")
    if execution.get("source_lock", {}).get("data_snapshot_sha256") != source.get(
        "market_snapshot", {}
    ).get("aggregate_sha256"):
        raise TransformerStatePipelineError("W17 no longer references the W13 market snapshot")
    for phase, lock in (
        ("W13", source.get("code_lock", {})),
        ("W14", panel.get("code_lock", {})),
        ("W15", model.get("source_lock", {}).get("code_lock", {})),
        ("W16", retrieval.get("source_lock", {}).get("code_lock", {})),
        ("W17", execution.get("source_lock", {}).get("code_lock", {})),
    ):
        if lock.get("aggregate_sha256") != current_code_sha:
            raise TransformerStatePipelineError(f"{phase} code lock drifted before evidence sealing")
    for key in panel.get("artifacts", {}):
        _verify_manifest_artifact(target, panel, key)
    for key in retrieval.get("artifacts", {}):
        _verify_manifest_artifact(target, retrieval, key)
    for key in execution.get("artifacts", {}):
        _verify_manifest_artifact(target, execution, key)
    fold_ids = [str(item["split_id"]) for item in model.get("folds", [])]
    if (
        len(fold_ids) != 4
        or len(set(fold_ids)) != 4
        or any(item.get("status") != "ready" for item in model["folds"])
    ):
        raise TransformerStatePipelineError("W18 requires four ready W15 folds")
    if retrieval.get("fold_count") != 4 or execution.get("fold_count") != 4:
        raise TransformerStatePipelineError("W18 requires four ready retrieval/execution folds")
    expected_fold_lock = _expected_w15_fold_source_lock(root, config_file, target, panel)
    for item in model["folds"]:
        _verify_w15_fold_manifest(
            target,
            item,
            market=str(config["market"]),
            expected_source_lock=expected_fold_lock,
        )
    expected_thresholds = {
        "state_match_loose",
        "state_match_balanced",
        "state_match_strict",
    }
    expected_variants = {
        "full_run_best_guard",
        "adaptive_guard",
        "cash_on_unmatched",
        "full_run_best_only",
    }
    if any(set(item.get("thresholds", {})) != expected_thresholds for item in retrieval["folds"]):
        raise TransformerStatePipelineError("W16 fold thresholds are incomplete")
    decisions_path = target / retrieval["artifacts"]["state_match_decisions"]["path"]
    daily_path = target / execution["artifacts"]["state_execution_daily"]["path"]
    summary_path = target / execution["artifacts"]["state_execution_summary"]["path"]
    decisions = pd.read_parquet(decisions_path)
    daily = pd.read_parquet(daily_path)
    summary = pd.read_csv(summary_path)
    for column in ("split_id", "market", "symbol", "regime", "threshold", "variant"):
        summary[column] = summary[column].astype(str)
    if set(decisions["split_id"].astype(str)) != set(fold_ids) or set(
        decisions["threshold_variant"].astype(str)
    ) != expected_thresholds:
        raise TransformerStatePipelineError("W16 decisions do not cover every fold/threshold")
    decision_matrix = decisions.groupby(["split_id", "threshold_variant"], dropna=False).size()
    if len(decision_matrix) != 4 * 3 or (decision_matrix <= 0).any():
        raise TransformerStatePipelineError("W16 decision matrix is incomplete")
    retrieval_folds = {str(item["split_id"]): item for item in retrieval["folds"]}
    if set(retrieval_folds) != set(fold_ids):
        raise TransformerStatePipelineError("W16 fold identities differ from W15")
    for split_id, item in retrieval_folds.items():
        expected_query_count = int(item.get("test_query_count", 0))
        if expected_query_count <= 0 or int(item.get("decision_row_count", 0)) != 3 * expected_query_count:
            raise TransformerStatePipelineError(f"W16 {split_id} manifest decision counts are invalid")
        for threshold in expected_thresholds:
            if int(decision_matrix.get((split_id, threshold), 0)) != expected_query_count:
                raise TransformerStatePipelineError(
                    f"W16 {split_id}/{threshold} does not contain every test query"
                )
    for frame, label in ((daily, "daily"), (summary, "summary")):
        if set(frame["split_id"].astype(str)) != set(fold_ids):
            raise TransformerStatePipelineError(f"W17 {label} folds are incomplete")
        if set(frame["threshold"].astype(str)) != expected_thresholds:
            raise TransformerStatePipelineError(f"W17 {label} thresholds are incomplete")
        if set(frame["variant"].astype(str)) != expected_variants:
            raise TransformerStatePipelineError(f"W17 {label} fallback variants are incomplete")
        matrix = frame.groupby(["split_id", "threshold", "variant"], dropna=False).size()
        if len(matrix) != 4 * 3 * 4 or (matrix <= 0).any():
            raise TransformerStatePipelineError(f"W17 {label} evidence matrix is incomplete")
    skipped_path = target / execution["artifacts"]["state_execution_skipped_decisions"]["path"]
    skipped = pd.read_csv(skipped_path)
    if set(skipped["variant"].astype(str)) != expected_variants:
        raise TransformerStatePipelineError("W17 skipped-decision variants are incomplete")
    _assert_execution_evidence_complete(
        decisions,
        daily,
        skipped,
        expected_variants=expected_variants,
        holding_days=int(execution["execution_config"]["holding_days"]),
    )
    required_daily = {
        "decision_date",
        "effective_date",
        "holding_window_end_date",
        "decision_target_position",
        "execution_turnover",
        "jump_guard_trigger",
        "risk_exit_effective_date",
        "strategy_return",
    }
    if not required_daily.issubset(daily.columns):
        raise TransformerStatePipelineError("W17 daily audit lacks execution/jump reconstruction fields")
    _assert_daily_numeric_integrity(daily)
    assert_summary_reconstructs(daily, summary)
    source_evidence = _verify_us_exact_daily_lineage(root, config, source)
    evidence = {
        "schema_version": "1.0",
        "phase": "W18" if config["market"] == "US" else "W19",
        "status": "ready",
        "created_at": _utc_now(),
        "market": config["market"],
        "output_subdir": config["output_subdir"],
        "fold_count": 4,
        "split_ids": fold_ids,
        "threshold_variants": sorted(expected_thresholds),
        "fallback_variants": sorted(expected_variants),
        "runtime": model.get("runtime"),
        "phases": entries,
        **source_evidence,
        "code_lock": current_code,
    }
    path = target / EVIDENCE_MANIFEST_NAME
    _json_write(path, evidence)
    return evidence, path


def write_blocked_late_stage_manifest(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    stage: str,
    reason: str,
    output_dir: str | Path | None = None,
) -> Path:
    """Replace stale W16-W18 readiness with an explicit blocked stage result."""

    filenames = {
        "retrieval": RETRIEVAL_MANIFEST_NAME,
        "execution": EXECUTION_MANIFEST_NAME,
        "evidence": EVIDENCE_MANIFEST_NAME,
    }
    if stage not in filenames:
        raise TransformerStatePipelineError(f"unsupported late-stage blocker: {stage}")
    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = _target_dir(root, config, output_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / filenames[stage]
    _json_write(
        path,
        {
            "schema_version": "1.0",
            "phase": {"retrieval": "W16", "execution": "W17", "evidence": "W18"}[stage],
            "status": "blocked",
            "created_at": _utc_now(),
            "market": config["market"],
            "reason": str(reason),
            "config_sha256": _sha256_file(config_file),
            "code_lock": transformer_code_lock(root),
        },
    )
    return path


def invalidate_downstream_manifests(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    after_phase: str,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Immediately mark every downstream manifest stale after an upstream refresh."""

    phases = list(_PHASE_MANIFEST_NAMES)
    if after_phase not in phases:
        raise TransformerStatePipelineError(f"unsupported invalidation phase: {after_phase}")
    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = _target_dir(root, config, output_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for phase in phases[phases.index(after_phase) + 1 :]:
        path = target / _PHASE_MANIFEST_NAMES[phase]
        _json_write(
            path,
            {
                "schema_version": "1.0",
                "phase": phase,
                "status": "blocked",
                "created_at": _utc_now(),
                "market": config["market"],
                "reason": f"stale_after_{after_phase.lower()}_refresh",
                "invalidated_by_phase": after_phase,
                "config_sha256": _sha256_file(config_file),
                "code_lock": transformer_code_lock(root),
                "stale_artifacts_retained_but_invalidated": True,
            },
        )
        written[phase] = path
    return written


__all__ = [
    "EVIDENCE_MANIFEST_NAME",
    "EXECUTION_MANIFEST_NAME",
    "RETRIEVAL_MANIFEST_NAME",
    "TransformerStatePipelineError",
    "materialize_full_evidence_manifest",
    "materialize_state_execution",
    "materialize_state_retrieval",
    "invalidate_downstream_manifests",
    "write_blocked_late_stage_manifest",
]
