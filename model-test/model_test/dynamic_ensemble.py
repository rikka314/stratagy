"""Phase-C LightGBM soft-gating for the post-Gate-2 research line.

This module consumes only a ready, source-locked Phase-B expert panel.  It is
deliberately independent from Streamlit and the online strategy workflow.  The
source panel already contains net expert returns, so every comparison below
uses those values directly and never applies transaction costs a second time.
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from core.lightgbm_runtime import (
    configure_lightgbm_environment,
    lightgbm_runtime_params,
    normalize_lightgbm_device,
    validate_lightgbm_device,
)
from model_test.expert_panel import (
    LABEL_COLUMNS,
    PANEL_KEY_COLUMNS,
    ExpertPanelError,
    validate_panel_no_leakage,
)
from model_test.moe_baseline import _canonical_market


PHASE_C_SCHEMA_VERSION = "1.0"
PRIMARY_HORIZON_DAYS = 20
CASH_EXPERT_ID = "cash"
MODEL_VARIANTS = ("moe_no_state", "moe_regime_aware")
BASELINE_VARIANTS = ("best_single_expert", "equal_weight_experts", "adaptive_router_v1")
STATE_FEATURE_PREFIXES = ("state_", "regime_", "adaptive_")


class DynamicEnsembleError(ValueError):
    """Raised when a Phase-C input, model, or output contract is invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DynamicEnsembleError(f"Unreadable JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise DynamicEnsembleError(f"Expected a JSON object: {path}")
    return value


def _relative_path(value: Any, *, field_name: str) -> Path:
    raw = str(value or "").strip()
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise DynamicEnsembleError(f"{field_name} must be a non-empty repository-relative path.")
    return path


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _git_code_version(repo_root: Path) -> str:
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return f"{commit}-dirty" if commit and dirty else (commit or "unavailable")


def load_dynamic_ensemble_config(path: str | Path) -> dict[str, Any]:
    config = _json_object(Path(path))
    validate_dynamic_ensemble_config(config)
    return config


def validate_dynamic_ensemble_config(config: dict[str, Any]) -> None:
    if str(config.get("schema_version")) != PHASE_C_SCHEMA_VERSION:
        raise DynamicEnsembleError(f"schema_version must be {PHASE_C_SCHEMA_VERSION!r}.")
    if str(config.get("phase") or "").upper() != "C":
        raise DynamicEnsembleError("phase must be 'C'.")
    _canonical_market(config.get("market"))
    _relative_path(config.get("panel_output_dir"), field_name="panel_output_dir")
    _relative_path(config.get("output_subdir"), field_name="output_subdir")
    if int(config.get("random_seed", -1)) != 42:
        raise DynamicEnsembleError("Phase C freezes random_seed at 42.")
    if config.get("training_scope") != "market_specific":
        raise DynamicEnsembleError("Phase C must train one market at a time.")
    if config.get("cross_market_policy") != "ablation_only":
        raise DynamicEnsembleError("cross_market_policy must remain 'ablation_only'.")
    if int(config.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase C primary_horizon_days must remain 20.")
    if config.get("return_field") != "strategy_return":
        raise DynamicEnsembleError("Phase C must consume the source net strategy_return field.")
    if config.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase C must not recharge source transaction costs.")

    model = config.get("model")
    if not isinstance(model, dict):
        raise DynamicEnsembleError("model must be an object.")
    for key in ("n_estimators", "num_leaves", "min_child_samples", "n_jobs", "minimum_train_rows"):
        if int(model.get(key, 0)) <= 0:
            raise DynamicEnsembleError(f"model.{key} must be a positive integer.")
    for key in ("learning_rate",):
        value = _finite_float(model.get(key))
        if value is None or value <= 0:
            raise DynamicEnsembleError(f"model.{key} must be a positive finite number.")
    normalize_lightgbm_device(model.get("device_type", "cpu"))

    gating = config.get("gating")
    if not isinstance(gating, dict):
        raise DynamicEnsembleError("gating must be an object.")
    temperature = _finite_float(gating.get("temperature"))
    max_weight = _finite_float(gating.get("max_risk_expert_weight"))
    alpha = _finite_float(gating.get("smoothing_alpha"))
    if temperature is None or temperature <= 0:
        raise DynamicEnsembleError("gating.temperature must be positive and finite.")
    if max_weight is None or not 0 < max_weight <= 1:
        raise DynamicEnsembleError("gating.max_risk_expert_weight must be in (0, 1].")
    if alpha is None or not 0 < alpha <= 1:
        raise DynamicEnsembleError("gating.smoothing_alpha must be in (0, 1].")
    if gating.get("cash_expert_id", CASH_EXPERT_ID) != CASH_EXPERT_ID:
        raise DynamicEnsembleError("Phase C requires the frozen cash expert id 'cash'.")


def stable_softmax(scores: Iterable[float], *, temperature: float) -> np.ndarray:
    """Return a finite softmax without allowing an extreme score to overflow."""

    values = np.asarray(list(scores), dtype=float)
    if values.size == 0:
        return values
    if not np.isfinite(values).all():
        raise DynamicEnsembleError("softmax scores must be finite")
    scaled = values / float(temperature)
    shifted = scaled - np.max(scaled)
    weights = np.exp(np.clip(shifted, -700.0, 0.0))
    total = float(weights.sum())
    if not math.isfinite(total) or total <= 0:
        raise DynamicEnsembleError("softmax produced an invalid weight total")
    return weights / total


def constrain_expert_weights(
    raw_weights: dict[str, float],
    *,
    cash_expert_id: str = CASH_EXPERT_ID,
    max_risk_expert_weight: float = 0.40,
) -> tuple[dict[str, float], bool]:
    """Cap every non-cash expert and send any excess to the always-safe cash leg."""

    if cash_expert_id not in raw_weights:
        raise DynamicEnsembleError("Cash expert must always be available before constraining weights.")
    weights = {str(key): max(0.0, float(value)) for key, value in raw_weights.items()}
    total = float(sum(weights.values()))
    if not math.isfinite(total) or total <= 0:
        raise DynamicEnsembleError("raw expert weights must have a positive finite total")
    weights = {key: value / total for key, value in weights.items()}
    capped = False
    for expert_id in tuple(weights):
        if expert_id == cash_expert_id:
            continue
        if weights[expert_id] > max_risk_expert_weight:
            excess = weights[expert_id] - max_risk_expert_weight
            weights[expert_id] = max_risk_expert_weight
            weights[cash_expert_id] += excess
            capped = True
    total = float(sum(weights.values()))
    return {key: value / total for key, value in weights.items()}, capped


def _verify_manifest_artifact(directory: Path, manifest: dict[str, Any], artifact_key: str) -> Path:
    artifacts = manifest.get("artifacts")
    descriptor = artifacts.get(artifact_key) if isinstance(artifacts, dict) else None
    if not isinstance(descriptor, dict) or not descriptor.get("path"):
        raise DynamicEnsembleError(f"Phase-B manifest is missing artifact metadata for {artifact_key}.")
    path = directory / str(descriptor["path"])
    if not path.is_file():
        raise DynamicEnsembleError(f"Phase-B artifact is missing: {path}")
    expected = str(descriptor.get("sha256") or "")
    if expected and _sha256_file(path) != expected:
        raise DynamicEnsembleError(f"Phase-B artifact hash differs from its manifest: {path}")
    return path


def _load_phase_b_input(config: dict[str, Any], *, repo_root: Path) -> tuple[Path, pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame]:
    panel_dir = (repo_root / _relative_path(config["panel_output_dir"], field_name="panel_output_dir")).resolve()
    try:
        panel_dir.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise DynamicEnsembleError("panel_output_dir must remain inside the repository.") from exc
    manifest_path = panel_dir / "expert_panel_manifest.json"
    phase_a_path = panel_dir / "data_manifest.json"
    baseline_path = panel_dir / "baseline_results.csv"
    if not manifest_path.is_file() or not phase_a_path.is_file() or not baseline_path.is_file():
        raise DynamicEnsembleError(
            "Phase C requires expert_panel_manifest.json, ready Phase-A data_manifest.json, and baseline_results.csv."
        )
    manifest = _json_object(manifest_path)
    phase_a = _json_object(phase_a_path)
    if manifest.get("phase") != "B" or manifest.get("status") != "ready":
        raise DynamicEnsembleError("Phase C requires a ready Phase-B panel, not a pending or degraded panel.")
    if phase_a.get("phase") != "A" or phase_a.get("status") != "ready":
        raise DynamicEnsembleError("Phase C requires a ready Phase-A baseline source lock.")
    market = _canonical_market(config["market"])
    if _canonical_market(manifest.get("market")) != market or _canonical_market(phase_a.get("market")) != market:
        raise DynamicEnsembleError("Phase-A, Phase-B, and Phase-C markets must match.")
    if int(manifest.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase-B primary horizon does not match Phase-C's frozen 20-day horizon.")
    if manifest.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase-B return contract would recharge source transaction costs.")
    panel_path = _verify_manifest_artifact(panel_dir, manifest, "expert_day_panel")
    splits_path = _verify_manifest_artifact(panel_dir, manifest, "walk_forward_splits")
    try:
        panel = pd.read_parquet(panel_path)
        splits = pd.read_csv(splits_path)
        baselines = pd.read_csv(baseline_path)
    except (OSError, ValueError, ImportError) as exc:
        raise DynamicEnsembleError("Phase-C could not read the frozen Phase-B inputs.") from exc
    if panel.empty or splits.empty:
        raise DynamicEnsembleError("Phase-C requires a non-empty ready panel and walk-forward split file.")
    required = set(PANEL_KEY_COLUMNS) | {"expert_status", "target_position", "strategy_return", "future_utility", "split_memberships_json"}
    missing = required - set(panel.columns)
    if missing:
        raise DynamicEnsembleError(f"Phase-B panel is missing Phase-C required columns: {sorted(missing)}")
    try:
        validate_panel_no_leakage(panel, splits=splits, primary_horizon_days=PRIMARY_HORIZON_DAYS)
    except ExpertPanelError as exc:
        raise DynamicEnsembleError(f"Phase-B leakage validation failed: {exc}") from exc
    return panel_dir, panel, splits, manifest, baselines


def _state_feature_columns(columns: Iterable[str]) -> list[str]:
    return [
        str(column)
        for column in columns
        if str(column).lower().startswith(STATE_FEATURE_PREFIXES)
        or str(column).lower() in {"state_id", "regime_id", "adaptive_state_id"}
    ]


def _feature_schema(panel: pd.DataFrame, manifest: dict[str, Any]) -> dict[str, Any]:
    recorded = manifest.get("feature_columns")
    if not isinstance(recorded, list) or not recorded:
        raise DynamicEnsembleError("Phase-B manifest has no persisted point-in-time feature schema.")
    forbidden = set(PANEL_KEY_COLUMNS) | set(LABEL_COLUMNS) | {
        "future_utility",
        "label_end_date",
        "split_memberships_json",
        "expert_status",
        "unavailable_reason",
        "source_model_id",
        "source_run_id",
        "source_code_version",
        "source_data_snapshot_sha256",
        "source_manifest_sha256",
        "source_artifact_path",
        "source_artifact_sha256",
    }
    available = [str(column) for column in recorded if str(column) in panel.columns and str(column) not in forbidden]
    numeric = [
        column
        for column in available
        if pd.api.types.is_numeric_dtype(panel[column]) or pd.api.types.is_bool_dtype(panel[column])
    ]
    if not numeric:
        raise DynamicEnsembleError("Phase-B panel has no numeric point-in-time features suitable for LightGBM.")
    state_columns = _state_feature_columns(numeric)
    if not state_columns:
        raise DynamicEnsembleError(
            "Phase C requires at least one explicit state/regime/adaptive feature to compare no-state and regime-aware MoE."
        )
    expert_categories = sorted(str(value) for value in panel["expert_id"].dropna().unique())
    if CASH_EXPERT_ID not in expert_categories:
        raise DynamicEnsembleError("Phase-B panel lost the required cash expert.")
    full = ["expert_id", *numeric]
    no_state = [column for column in full if column not in state_columns]
    if len(no_state) == 1:
        raise DynamicEnsembleError("No-state MoE would have no non-identity feature after removing state features.")
    return {
        "categorical_features": ["expert_id"],
        "expert_id_categories": expert_categories,
        "full_feature_columns": full,
        "no_state_feature_columns": no_state,
        "state_feature_columns": state_columns,
        "dropped_non_numeric_features": [column for column in available if column not in numeric],
    }


def _feature_frame(frame: pd.DataFrame, columns: list[str], schema: dict[str, Any]) -> pd.DataFrame:
    values = pd.DataFrame(index=frame.index)
    categories = list(schema["expert_id_categories"])
    for column in columns:
        if column == "expert_id":
            values[column] = pd.Categorical(frame[column].astype(str), categories=categories)
        else:
            values[column] = pd.to_numeric(frame[column], errors="coerce")
    return values


def _fit_regressor(frame: pd.DataFrame, *, feature_columns: list[str], schema: dict[str, Any], config: dict[str, Any]):
    try:
        from lightgbm import LGBMRegressor
    except Exception as exc:  # pragma: no cover - dependency failure is environment-specific
        raise DynamicEnsembleError(f"LightGBM is unavailable: {exc}") from exc
    model_config = config["model"]
    valid = frame.loc[
        frame["expert_status"].eq("available") & pd.to_numeric(frame["future_utility"], errors="coerce").notna()
    ].copy()
    if len(valid) < int(model_config["minimum_train_rows"]):
        raise DynamicEnsembleError(
            f"LightGBM requires at least {model_config['minimum_train_rows']} available labeled rows; found {len(valid)}."
        )
    model = LGBMRegressor(
        objective="regression",
        n_estimators=int(model_config["n_estimators"]),
        learning_rate=float(model_config["learning_rate"]),
        num_leaves=int(model_config["num_leaves"]),
        min_child_samples=int(model_config["min_child_samples"]),
        n_jobs=int(model_config["n_jobs"]),
        random_state=int(config["random_seed"]),
        verbosity=-1,
        **lightgbm_runtime_params(),
    )
    features = _feature_frame(valid, feature_columns, schema)
    target = pd.to_numeric(valid["future_utility"], errors="coerce")
    model.fit(features, target, categorical_feature=["expert_id"])
    return model


def _membership_mask(panel: pd.DataFrame, *, split_id: str, role: str) -> pd.Series:
    values: list[bool] = []
    for raw in panel["split_memberships_json"].fillna("[]"):
        try:
            entries = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise DynamicEnsembleError("split_memberships_json is not valid JSON") from exc
        values.append(any(str(item.get("split_id")) == split_id and item.get("role") == role for item in entries))
    return pd.Series(values, index=panel.index, dtype=bool)


def _test_panel_for_split(panel: pd.DataFrame, *, split_id: str) -> pd.DataFrame:
    membership = _membership_mask(panel, split_id=split_id, role="test")
    if not membership.any():
        raise DynamicEnsembleError(f"Split {split_id} contains no complete test labels after purge/embargo.")
    keys = pd.MultiIndex.from_frame(panel.loc[membership, ["date", "symbol"]].drop_duplicates())
    all_keys = pd.MultiIndex.from_frame(panel[["date", "symbol"]])
    selected = panel.loc[all_keys.isin(keys)].copy()
    selected["test_membership"] = _membership_mask(selected, split_id=split_id, role="test").to_numpy()
    return selected


def _with_next_net_return(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out = out.sort_values(["symbol", "expert_id", "date"]).reset_index(drop=True)
    out["realized_next_net_return"] = out.groupby(["symbol", "expert_id"], sort=False)["strategy_return"].shift(-1)
    return out


def _eligible_for_weight(frame: pd.DataFrame) -> pd.Series:
    positions = pd.to_numeric(frame["target_position"], errors="coerce")
    return frame["expert_status"].eq("available") & (
        frame["expert_id"].eq(CASH_EXPERT_ID) | positions.notna()
    ) & frame["test_membership"].astype(bool)


def _format_reasons(reasons: Iterable[str]) -> str | None:
    values = [value for value in dict.fromkeys(reasons) if value]
    return "; ".join(values) if values else None


def _dynamic_weights_for_group(
    group: pd.DataFrame,
    *,
    previous: dict[str, float] | None,
    temperature: float,
    max_risk_expert_weight: float,
    smoothing_alpha: float,
) -> tuple[dict[str, float], dict[str, float], str, str | None]:
    eligible = group.loc[group["eligible_for_weight"].astype(bool)].copy()
    eligible_ids = eligible["expert_id"].astype(str).tolist()
    reasons: list[str] = []
    if CASH_EXPERT_ID not in eligible_ids:
        return {}, {}, "unavailable", "cash expert is unavailable"
    risk_ids = [expert_id for expert_id in eligible_ids if expert_id != CASH_EXPERT_ID]
    if not risk_ids:
        return {CASH_EXPERT_ID: 1.0}, {CASH_EXPERT_ID: 1.0}, "fallback", "cash_only"
    missing = group.loc[
        ~group["expert_id"].astype(str).isin(eligible_ids) & ~group["expert_id"].astype(str).eq(CASH_EXPERT_ID), "expert_id"
    ]
    if not missing.empty:
        reasons.append("missing_experts_re_normalized")
    scores = pd.to_numeric(eligible["predicted_utility"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(scores).all():
        equal = np.repeat(1.0 / len(eligible_ids), len(eligible_ids))
        raw = dict(zip(eligible_ids, equal, strict=True))
        reasons.append("nonfinite_prediction_equal_weight_fallback")
    else:
        raw = dict(zip(eligible_ids, stable_softmax(scores, temperature=temperature), strict=True))
    weights = raw.copy()
    if previous:
        prior = {expert_id: max(0.0, float(previous.get(expert_id, 0.0))) for expert_id in eligible_ids}
        prior_total = sum(prior.values())
        if prior_total > 0:
            prior = {expert_id: value / prior_total for expert_id, value in prior.items()}
            weights = {
                expert_id: smoothing_alpha * raw[expert_id] + (1.0 - smoothing_alpha) * prior[expert_id]
                for expert_id in eligible_ids
            }
            reasons.append("exponential_smoothing")
    weights, capped = constrain_expert_weights(
        weights,
        cash_expert_id=CASH_EXPERT_ID,
        max_risk_expert_weight=max_risk_expert_weight,
    )
    if capped:
        reasons.append("risk_expert_cap")
    return raw, weights, "ready", _format_reasons(reasons)


def _baseline_weights_for_group(
    group: pd.DataFrame,
    *,
    variant: str,
    best_expert_id: str | None,
    adaptive_expert_id: str | None,
    equal_weight_expert_ids: set[str],
) -> tuple[dict[str, float], str, str | None]:
    eligible = set(group.loc[group["eligible_for_weight"].astype(bool), "expert_id"].astype(str))
    if variant == "best_single_expert":
        if not best_expert_id or best_expert_id not in eligible:
            return {}, "unavailable", "frozen best single expert is unavailable"
        return {best_expert_id: 1.0}, "ready", None
    if variant == "adaptive_router_v1":
        if not adaptive_expert_id or adaptive_expert_id not in eligible:
            return {}, "unavailable", "adaptive_router_v1 is unavailable for this market or date"
        return {adaptive_expert_id: 1.0}, "ready", None
    required = set(equal_weight_expert_ids)
    if not required or not required.issubset(eligible):
        missing = sorted(required - eligible)
        return {}, "unavailable", f"frozen equal-weight experts unavailable: {', '.join(missing)}"
    weight = 1.0 / len(required)
    return {expert_id: weight for expert_id in sorted(required)}, "ready", None


def _decision_records(
    group: pd.DataFrame,
    *,
    variant: str,
    split_id: str,
    weights: dict[str, float],
    raw_weights: dict[str, float] | None,
    status: str,
    reason: str | None,
    previous: dict[str, float] | None,
) -> list[dict[str, Any]]:
    positions = pd.to_numeric(group["target_position"], errors="coerce")
    final_position = float(
        sum(float(weights.get(str(row.expert_id), 0.0)) * (0.0 if pd.isna(position) else float(position))
            for row, position in zip(group.itertuples(index=False), positions, strict=True))
    )
    records: list[dict[str, Any]] = []
    for row, position in zip(group.itertuples(index=False), positions, strict=True):
        expert_id = str(row.expert_id)
        weight = float(weights.get(expert_id, 0.0))
        before = float((previous or {}).get(expert_id, 0.0))
        records.append(
            {
                "schema_version": PHASE_C_SCHEMA_VERSION,
                "market": str(row.market),
                "split_id": split_id,
                "variant": variant,
                "date": pd.Timestamp(row.date).date().isoformat(),
                "symbol": str(row.symbol),
                "expert_id": expert_id,
                "expert_status": str(row.expert_status),
                "is_test_label": bool(row.test_membership),
                "predicted_utility": _finite_float(getattr(row, "predicted_utility", None)),
                "future_utility": _finite_float(getattr(row, "future_utility", None)),
                "expert_target_position": _finite_float(position),
                "raw_expert_weight": _finite_float((raw_weights or {}).get(expert_id, 0.0)),
                "expert_weight": weight,
                "weight_change": weight - before,
                "weighted_target_position": weight * (0.0 if pd.isna(position) else float(position)),
                "final_target_position": final_position,
                "realized_next_net_return": _finite_float(getattr(row, "realized_next_net_return", None)),
                "evaluation_status": status,
                "weight_change_reason": reason,
                "fallback_reason": reason if status != "ready" or (reason and "fallback" in reason) else None,
            }
        )
    return records


def _expert_id_for_source_model(panel: pd.DataFrame, source_model_id: str | None) -> str | None:
    if not source_model_id:
        return None
    matches = panel.loc[panel["source_model_id"].astype(str) == str(source_model_id), "expert_id"].dropna().astype(str).unique()
    return str(matches[0]) if len(matches) == 1 else None


def _baseline_definition(panel: pd.DataFrame, manifest: dict[str, Any], baselines: pd.DataFrame) -> dict[str, Any]:
    required = {"control_id", "status", "selected_model_ids"}
    if not required.issubset(baselines.columns):
        raise DynamicEnsembleError("baseline_results.csv is missing frozen control columns required by Phase C.")
    control_rows = {str(row.control_id): row for row in baselines.itertuples(index=False)}
    best_row = control_rows.get("best_single_expert")
    if best_row is None or str(best_row.status) != "ready":
        raise DynamicEnsembleError("The frozen best_single_expert baseline is not ready.")
    try:
        selected = json.loads(str(best_row.selected_model_ids))
    except json.JSONDecodeError as exc:
        raise DynamicEnsembleError("best_single_expert selected_model_ids is invalid JSON.") from exc
    if not isinstance(selected, list) or len(selected) != 1:
        raise DynamicEnsembleError("best_single_expert must freeze exactly one source model.")
    best_expert_id = _expert_id_for_source_model(panel, str(selected[0]))
    if not best_expert_id:
        raise DynamicEnsembleError("The frozen best single source model is absent from the Phase-B panel.")
    router_row = control_rows.get("adaptive_router_v1")
    adaptive_expert_id = None
    if router_row is not None and str(router_row.status) == "ready":
        source_model_id = getattr(router_row, "source_model_id", None)
        adaptive_expert_id = _expert_id_for_source_model(panel, str(source_model_id or "rsm_adaptive_v1"))
    experts = manifest.get("expert_pool")
    if not isinstance(experts, list):
        raise DynamicEnsembleError("Phase-B manifest is missing the frozen expert pool.")
    equal_ids = {
        str(item.get("expert_id"))
        for item in experts
        if isinstance(item, dict) and item.get("include_in_equal_weight") is True
    }
    if not equal_ids:
        raise DynamicEnsembleError("The frozen equal-weight baseline has no eligible experts.")
    return {
        "best_expert_id": best_expert_id,
        "adaptive_expert_id": adaptive_expert_id,
        "equal_weight_expert_ids": equal_ids,
    }


def _run_variant(
    panel: pd.DataFrame,
    splits: pd.DataFrame,
    *,
    variant: str,
    feature_columns: list[str],
    schema: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    gating = config["gating"]
    for split in splits.itertuples(index=False):
        split_id = str(split.split_id)
        train_mask = _membership_mask(panel, split_id=split_id, role="train")
        train = panel.loc[train_mask].copy()
        model = _fit_regressor(train, feature_columns=feature_columns, schema=schema, config=config)
        test = _test_panel_for_split(panel, split_id=split_id)
        test["eligible_for_weight"] = _eligible_for_weight(test)
        test["predicted_utility"] = np.nan
        eligible = test["eligible_for_weight"].astype(bool)
        if eligible.any():
            test.loc[eligible, "predicted_utility"] = model.predict(_feature_frame(test.loc[eligible], feature_columns, schema))
        previous_by_symbol: dict[str, dict[str, float]] = {}
        for (_, symbol), group in test.sort_values(["date", "symbol", "expert_id"]).groupby(["date", "symbol"], sort=True):
            previous = previous_by_symbol.get(str(symbol))
            raw, weights, status, reason = _dynamic_weights_for_group(
                group,
                previous=previous,
                temperature=float(gating["temperature"]),
                max_risk_expert_weight=float(gating["max_risk_expert_weight"]),
                smoothing_alpha=float(gating["smoothing_alpha"]),
            )
            records.extend(
                _decision_records(
                    group,
                    variant=variant,
                    split_id=split_id,
                    weights=weights,
                    raw_weights=raw,
                    status=status,
                    reason=reason,
                    previous=previous,
                )
            )
            if status in {"ready", "fallback"}:
                previous_by_symbol[str(symbol)] = weights
    return records


def _run_baselines(
    panel: pd.DataFrame,
    splits: pd.DataFrame,
    *,
    definition: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for split in splits.itertuples(index=False):
        split_id = str(split.split_id)
        test = _test_panel_for_split(panel, split_id=split_id)
        test["eligible_for_weight"] = _eligible_for_weight(test)
        test["predicted_utility"] = np.nan
        for variant in BASELINE_VARIANTS:
            for (_, _), group in test.sort_values(["date", "symbol", "expert_id"]).groupby(["date", "symbol"], sort=True):
                weights, status, reason = _baseline_weights_for_group(
                    group,
                    variant=variant,
                    best_expert_id=definition["best_expert_id"],
                    adaptive_expert_id=definition["adaptive_expert_id"],
                    equal_weight_expert_ids=definition["equal_weight_expert_ids"],
                )
                records.extend(
                    _decision_records(
                        group,
                        variant=variant,
                        split_id=split_id,
                        weights=weights,
                        raw_weights=None,
                        status=status,
                        reason=reason,
                        previous=None,
                    )
                )
    return records


def _performance_metrics(returns: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {"total_return": None, "annualized_return": None, "sharpe": None, "max_drawdown": None}
    equity = (1.0 + clean).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    annualized = float(equity.iloc[-1] ** (252.0 / len(clean)) - 1.0) if len(clean) else None
    volatility = float(clean.std(ddof=0))
    sharpe = float(math.sqrt(252.0) * clean.mean() / volatility) if volatility > 0 else None
    drawdown = equity / equity.cummax() - 1.0
    return {
        "total_return": total,
        "annualized_return": annualized,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
    }


def _summary(weights: pd.DataFrame) -> pd.DataFrame:
    if weights.empty:
        return pd.DataFrame()
    active = weights.loc[weights["evaluation_status"].isin(["ready", "fallback"])].copy()
    active["realized_next_net_return"] = pd.to_numeric(active["realized_next_net_return"], errors="coerce")
    active["future_utility"] = pd.to_numeric(active["future_utility"], errors="coerce")
    active["expert_weight"] = pd.to_numeric(active["expert_weight"], errors="coerce").fillna(0.0)
    rows: list[dict[str, Any]] = []
    for (market, split_id, variant), frame in active.groupby(["market", "split_id", "variant"], sort=True):
        group_rows: list[dict[str, Any]] = []
        for (date, symbol), group in frame.groupby(["date", "symbol"], sort=True):
            selected = group.loc[group["expert_weight"] > 0]
            valid_return = selected["realized_next_net_return"].notna().all() and not selected.empty
            group_rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "net_return": float((selected["expert_weight"] * selected["realized_next_net_return"]).sum()) if valid_return else np.nan,
                    "weighted_future_utility": float((selected["expert_weight"] * selected["future_utility"]).sum())
                    if selected["future_utility"].notna().all() and not selected.empty
                    else np.nan,
                }
            )
        groups = pd.DataFrame(group_rows)
        daily = groups.groupby("date", sort=True)["net_return"].mean().dropna()
        metrics = _performance_metrics(daily)
        rows.append(
            {
                "market": market,
                "split_id": split_id,
                "variant": variant,
                "status": "ready" if not daily.empty else "unavailable",
                "decision_count": int(len(groups)),
                "daily_return_count": int(len(daily)),
                "mean_weighted_future_utility": _finite_float(groups["weighted_future_utility"].mean()),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _feature_importance(model: Any, feature_columns: list[str]) -> list[dict[str, Any]]:
    gain = getattr(model, "feature_importances_", None)
    if gain is None:
        return []
    return [
        {"feature": feature, "importance_split": int(value)}
        for feature, value in sorted(zip(feature_columns, gain, strict=True), key=lambda item: int(item[1]), reverse=True)
    ]


def _report_markdown(summary: pd.DataFrame, *, config: dict[str, Any], schema: dict[str, Any]) -> str:
    lines = [
        "# Phase-C LightGBM Soft-Gating MoE v1",
        "",
        f"- Market: `{config['market']}`",
        f"- Primary horizon: `{config['primary_horizon_days']}` trading days",
        f"- Return semantics: `{config['return_field']}` / `{config['cost_treatment']}`",
        f"- Risk-expert cap: `{config['gating']['max_risk_expert_weight']:.0%}`; smoothing alpha: `{config['gating']['smoothing_alpha']}`",
        f"- Regime-aware state features: `{', '.join(schema['state_feature_columns'])}`",
        "",
        "## Walk-forward comparison",
        "",
        "| Split | Variant | Status | Daily returns | Total return | Sharpe | Max drawdown |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        def fmt(value: Any) -> str:
            return "—" if value is None or (isinstance(value, float) and not math.isfinite(value)) else f"{float(value):.4f}"

        lines.append(
            f"| {row.split_id} | {row.variant} | {row.status} | {row.daily_return_count} | "
            f"{fmt(row.total_return)} | {fmt(row.sharpe)} | {fmt(row.max_drawdown)} |"
        )
    lines.extend(
        [
            "",
            "## Safety guarantees",
            "",
            "- Only Phase-B train memberships train a walk-forward fold; its test memberships remain out of fit.",
            "- The cash expert is always required; missing risk experts receive zero weight and remaining weights re-normalize.",
            "- Every non-cash expert is capped before the final target position is calculated.",
            "- Source `strategy_return` is already net of source execution costs and is not charged a second time.",
            "- This artifact is research-only and is not imported by the Streamlit workflow.",
            "",
        ]
    )
    return "\n".join(lines)


def materialize_dynamic_ensemble(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Train/evaluate Phase-C soft-gating and write its frozen research artifacts."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_dynamic_ensemble_config(config_file)
    panel_dir, panel, splits, panel_manifest, baselines = _load_phase_b_input(config, repo_root=root)
    configure_lightgbm_environment(device_type=str(config["model"].get("device_type", "cpu")))
    device_check = validate_lightgbm_device(str(config["model"].get("device_type", "cpu")))
    if not device_check.get("available"):
        raise DynamicEnsembleError(f"LightGBM device preflight failed: {device_check.get('error', 'unknown error')}")

    panel = _with_next_net_return(panel)
    schema = _feature_schema(panel, panel_manifest)
    definition = _baseline_definition(panel, panel_manifest, baselines)
    model_records = []
    model_records.extend(
        _run_variant(
            panel,
            splits,
            variant="moe_no_state",
            feature_columns=schema["no_state_feature_columns"],
            schema=schema,
            config=config,
        )
    )
    model_records.extend(
        _run_variant(
            panel,
            splits,
            variant="moe_regime_aware",
            feature_columns=schema["full_feature_columns"],
            schema=schema,
            config=config,
        )
    )
    model_records.extend(_run_baselines(panel, splits, definition=definition))
    weights = pd.DataFrame(model_records)
    if weights.empty:
        raise DynamicEnsembleError("Phase C did not produce any walk-forward decisions.")
    summary = _summary(weights)
    if not set(MODEL_VARIANTS).issubset(set(summary.loc[summary["status"].eq("ready"), "variant"])):
        raise DynamicEnsembleError("Phase C did not produce ready walk-forward results for both MoE variants.")

    full_train = panel.loc[
        panel["expert_status"].eq("available") & pd.to_numeric(panel["future_utility"], errors="coerce").notna()
    ].copy()
    full_model = _fit_regressor(full_train, feature_columns=schema["full_feature_columns"], schema=schema, config=config)
    no_state_model = _fit_regressor(full_train, feature_columns=schema["no_state_feature_columns"], schema=schema, config=config)
    schema["feature_importance"] = {
        "moe_regime_aware": _feature_importance(full_model, schema["full_feature_columns"]),
        "moe_no_state": _feature_importance(no_state_model, schema["no_state_feature_columns"]),
    }

    target = Path(output_dir) if output_dir is not None else root / "model-test" / "outputs" / str(config["output_subdir"])
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "moe_model.pkl"
    schema_path = target / "moe_feature_schema.json"
    weights_path = target / "moe_daily_weights.parquet"
    summary_path = target / "moe_summary.csv"
    report_path = target / "moe_report.md"
    manifest_path = target / "moe_manifest.json"
    with model_path.open("wb") as handle:
        pickle.dump(
            {
                "schema_version": PHASE_C_SCHEMA_VERSION,
                "market": config["market"],
                "regime_aware_model": full_model,
                "no_state_model": no_state_model,
                "feature_schema": schema,
            },
            handle,
        )
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    weights.to_parquet(weights_path, index=False)
    summary.to_csv(summary_path, index=False)
    report_path.write_text(_report_markdown(summary, config=config, schema=schema), encoding="utf-8")
    manifest = {
        "schema_version": PHASE_C_SCHEMA_VERSION,
        "phase": "C",
        "status": "ready",
        "name": config.get("name"),
        "market": config["market"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_code_version": _git_code_version(root),
        "config_path": config_file.relative_to(root).as_posix(),
        "config_sha256": _sha256_file(config_file),
        "phase_b_panel_dir": panel_dir.relative_to(root).as_posix(),
        "phase_b_manifest_sha256": _sha256_file(panel_dir / "expert_panel_manifest.json"),
        "phase_a_manifest_sha256": _sha256_file(panel_dir / "data_manifest.json"),
        "random_seed": config["random_seed"],
        "primary_horizon_days": config["primary_horizon_days"],
        "return_field": config["return_field"],
        "cost_treatment": config["cost_treatment"],
        "model": config["model"],
        "gating": config["gating"],
        "lightgbm_preflight": device_check,
        "feature_schema": schema,
        "baseline_definition": {
            **definition,
            "equal_weight_expert_ids": sorted(definition["equal_weight_expert_ids"]),
        },
        "artifacts": {
            "moe_model": {"path": model_path.name, "sha256": _sha256_file(model_path), "size_bytes": model_path.stat().st_size},
            "feature_schema": {"path": schema_path.name, "sha256": _sha256_file(schema_path)},
            "daily_weights": {"path": weights_path.name, "sha256": _sha256_file(weights_path), "size_bytes": weights_path.stat().st_size},
            "summary": {"path": summary_path.name, "sha256": _sha256_file(summary_path)},
            "report": {"path": report_path.name, "sha256": _sha256_file(report_path)},
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "model": model_path,
        "feature_schema": schema_path,
        "daily_weights": weights_path,
        "summary": summary_path,
        "report": report_path,
        "manifest": manifest_path,
    }


__all__ = [
    "BASELINE_VARIANTS",
    "CASH_EXPERT_ID",
    "DynamicEnsembleError",
    "MODEL_VARIANTS",
    "constrain_expert_weights",
    "load_dynamic_ensemble_config",
    "materialize_dynamic_ensemble",
    "stable_softmax",
    "validate_dynamic_ensemble_config",
]
