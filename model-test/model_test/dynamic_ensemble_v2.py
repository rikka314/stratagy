"""Phase-D uncertainty- and risk-aware dynamic ensemble research.

The module deliberately stays in ``model-test``.  It consumes the same
source-locked Phase-A/B panel used by Phase C plus a verified Phase-C output,
then evaluates quantile-gated MoE v2 against the already materialized v1
decisions.  It must not be imported by the Streamlit workflow.
"""

from __future__ import annotations

import itertools
import json
import math
import pickle
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
from model_test.dynamic_ensemble import (
    CASH_EXPERT_ID,
    DynamicEnsembleError,
    MODEL_VARIANTS as PHASE_C_MODEL_VARIANTS,
    _baseline_definition,
    _feature_frame,
    _feature_schema,
    _git_code_version,
    _load_phase_b_input,
    _membership_mask,
    _performance_metrics,
    _relative_path,
    _sha256_file,
    _test_panel_for_split,
    _with_next_net_return,
    _eligible_for_weight,
    constrain_expert_weights,
    stable_softmax,
)
from model_test.moe_baseline import _canonical_market


PHASE_D_SCHEMA_VERSION = "1.1"
PRIMARY_HORIZON_DAYS = 20
MODEL_VARIANTS = ("moe_v2_no_state", "moe_v2_regime_aware")
FALLBACK_POLICIES = {"cash", "equal_weight", "adaptive_router"}


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DynamicEnsembleError(f"Unreadable JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise DynamicEnsembleError(f"Expected a JSON object: {path}")
    return value


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _positive_finite(value: Any, *, field_name: str, allow_zero: bool = False) -> float:
    numeric = _finite_float(value)
    if numeric is None or (numeric < 0 if allow_zero else numeric <= 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise DynamicEnsembleError(f"{field_name} must be a {comparator} finite number.")
    return numeric


def load_dynamic_ensemble_v2_config(path: str | Path) -> dict[str, Any]:
    config = _json_object(Path(path))
    validate_dynamic_ensemble_v2_config(config)
    return config


def validate_dynamic_ensemble_v2_config(config: dict[str, Any]) -> None:
    """Reject any config that changes the frozen research or safety contract."""

    if str(config.get("schema_version")) != PHASE_D_SCHEMA_VERSION:
        raise DynamicEnsembleError(f"schema_version must be {PHASE_D_SCHEMA_VERSION!r}.")
    if str(config.get("phase") or "").upper() != "D":
        raise DynamicEnsembleError("phase must be 'D'.")
    _canonical_market(config.get("market"))
    _relative_path(config.get("panel_output_dir"), field_name="panel_output_dir")
    _relative_path(config.get("phase_c_output_dir"), field_name="phase_c_output_dir")
    _relative_path(config.get("output_subdir"), field_name="output_subdir")
    if int(config.get("random_seed", -1)) != 42:
        raise DynamicEnsembleError("Phase D freezes random_seed at 42.")
    if config.get("training_scope") != "market_specific":
        raise DynamicEnsembleError("Phase D must train one market at a time.")
    if config.get("cross_market_policy") != "ablation_only":
        raise DynamicEnsembleError("cross_market_policy must remain 'ablation_only'.")
    if int(config.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase D primary_horizon_days must remain 20.")
    if config.get("return_field") != "strategy_return":
        raise DynamicEnsembleError("Phase D must consume the source net strategy_return field.")
    if config.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase D must not recharge source transaction costs.")

    model = config.get("model")
    if not isinstance(model, dict):
        raise DynamicEnsembleError("model must be an object.")
    for key in ("n_estimators", "num_leaves", "min_child_samples", "n_jobs", "minimum_train_rows"):
        if int(model.get(key, 0)) <= 0:
            raise DynamicEnsembleError(f"model.{key} must be a positive integer.")
    _positive_finite(model.get("learning_rate"), field_name="model.learning_rate")
    normalize_lightgbm_device(model.get("device_type", "cpu"))

    gating = config.get("gating")
    if not isinstance(gating, dict):
        raise DynamicEnsembleError("gating must be an object.")
    _positive_finite(gating.get("temperature"), field_name="gating.temperature")
    cap = _positive_finite(gating.get("max_risk_expert_weight"), field_name="gating.max_risk_expert_weight")
    if cap > 1:
        raise DynamicEnsembleError("gating.max_risk_expert_weight must be at most 1.")
    alpha = _positive_finite(gating.get("smoothing_alpha"), field_name="gating.smoothing_alpha")
    if alpha > 1:
        raise DynamicEnsembleError("gating.smoothing_alpha must be at most 1.")
    if gating.get("cash_expert_id", CASH_EXPERT_ID) != CASH_EXPERT_ID:
        raise DynamicEnsembleError("Phase D requires the frozen cash expert id 'cash'.")

    quantiles = config.get("quantiles")
    if not isinstance(quantiles, dict):
        raise DynamicEnsembleError("quantiles must be an object.")
    lower = _positive_finite(quantiles.get("lower"), field_name="quantiles.lower")
    median = _positive_finite(quantiles.get("median"), field_name="quantiles.median")
    if not 0 < lower < median < 1:
        raise DynamicEnsembleError("quantiles must satisfy 0 < lower < median < 1.")

    uncertainty = config.get("uncertainty")
    if not isinstance(uncertainty, dict):
        raise DynamicEnsembleError("uncertainty must be an object.")
    for key in ("gamma", "confidence_width_threshold", "disagreement_std_threshold"):
        _positive_finite(uncertainty.get(key), field_name=f"uncertainty.{key}", allow_zero=(key == "gamma"))
    _positive_finite(uncertainty.get("ood_max_abs_zscore"), field_name="uncertainty.ood_max_abs_zscore")

    fallback = config.get("fallback")
    if not isinstance(fallback, dict):
        raise DynamicEnsembleError("fallback must be an object.")
    for key in ("low_confidence_policy", "high_disagreement_policy", "out_of_distribution_policy"):
        if fallback.get(key) not in FALLBACK_POLICIES:
            raise DynamicEnsembleError(f"fallback.{key} must be one of {sorted(FALLBACK_POLICIES)}.")

    risk = config.get("risk")
    if not isinstance(risk, dict):
        raise DynamicEnsembleError("risk must be an object.")
    for key in ("max_weight_change", "max_portfolio_turnover", "drawdown_trigger"):
        value = _positive_finite(risk.get(key), field_name=f"risk.{key}")
        if value > 1:
            raise DynamicEnsembleError(f"risk.{key} must be at most 1.")
    scale = _positive_finite(risk.get("drawdown_risk_scale"), field_name="risk.drawdown_risk_scale", allow_zero=True)
    if scale > 1:
        raise DynamicEnsembleError("risk.drawdown_risk_scale must be in [0, 1].")
    if int(risk.get("minimum_holding_days", -1)) < 0:
        raise DynamicEnsembleError("risk.minimum_holding_days must be a non-negative integer.")
    threshold = _positive_finite(
        risk.get("position_active_threshold"), field_name="risk.position_active_threshold", allow_zero=True
    )
    if threshold > 1:
        raise DynamicEnsembleError("risk.position_active_threshold must be in [0, 1].")

    ablation = config.get("ablation")
    if not isinstance(ablation, dict):
        raise DynamicEnsembleError("ablation must be an object.")
    for key in ("temperatures", "max_risk_expert_weights", "smoothing_alphas"):
        values = ablation.get(key)
        if not isinstance(values, list) or not values:
            raise DynamicEnsembleError(f"ablation.{key} must be a non-empty list.")
        for value in values:
            numeric = _positive_finite(value, field_name=f"ablation.{key}")
            if key != "temperatures" and numeric > 1:
                raise DynamicEnsembleError(f"ablation.{key} values must be at most 1.")


def _verify_artifact(directory: Path, manifest: dict[str, Any], artifact_key: str, *, phase_name: str) -> Path:
    artifacts = manifest.get("artifacts")
    descriptor = artifacts.get(artifact_key) if isinstance(artifacts, dict) else None
    if not isinstance(descriptor, dict) or not descriptor.get("path"):
        raise DynamicEnsembleError(f"{phase_name} manifest is missing artifact metadata for {artifact_key}.")
    path = directory / str(descriptor["path"])
    if not path.is_file():
        raise DynamicEnsembleError(f"{phase_name} artifact is missing: {path}")
    expected = str(descriptor.get("sha256") or "")
    if expected and _sha256_file(path) != expected:
        raise DynamicEnsembleError(f"{phase_name} artifact hash differs from its manifest: {path}")
    return path


def _load_phase_c_input(
    config: dict[str, Any], *, repo_root: Path, panel_dir: Path
) -> tuple[Path, dict[str, Any], pd.DataFrame, pd.DataFrame]:
    target = (repo_root / _relative_path(config["phase_c_output_dir"], field_name="phase_c_output_dir")).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise DynamicEnsembleError("phase_c_output_dir must remain inside the repository.") from exc
    manifest_path = target / "moe_manifest.json"
    if not manifest_path.is_file():
        raise DynamicEnsembleError("Phase D requires the ready Phase-C moe_manifest.json.")
    manifest = _json_object(manifest_path)
    if manifest.get("phase") != "C" or manifest.get("status") != "ready":
        raise DynamicEnsembleError("Phase D requires a ready Phase-C source artifact.")
    if _canonical_market(manifest.get("market")) != _canonical_market(config["market"]):
        raise DynamicEnsembleError("Phase-C and Phase-D markets must match.")
    if int(manifest.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase-C primary horizon does not match Phase-D's frozen 20-day horizon.")
    if manifest.get("return_field") != "strategy_return" or manifest.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase-C return contract is incompatible with Phase D.")
    expected_panel_dir = panel_dir.relative_to(repo_root).as_posix()
    if str(manifest.get("phase_b_panel_dir")) != expected_panel_dir:
        raise DynamicEnsembleError("Phase-C output was built from a different Phase-B panel directory.")
    for key, filename in (("phase_b_manifest_sha256", "expert_panel_manifest.json"), ("phase_a_manifest_sha256", "data_manifest.json")):
        if str(manifest.get(key) or "") != _sha256_file(panel_dir / filename):
            raise DynamicEnsembleError(f"Phase-C {key} no longer matches the source-locked panel.")
    weights_path = _verify_artifact(target, manifest, "daily_weights", phase_name="Phase-C")
    summary_path = _verify_artifact(target, manifest, "summary", phase_name="Phase-C")
    _verify_artifact(target, manifest, "feature_schema", phase_name="Phase-C")
    try:
        weights = pd.read_parquet(weights_path)
        summary = pd.read_csv(summary_path)
    except (OSError, ValueError, ImportError) as exc:
        raise DynamicEnsembleError("Phase-D could not read the verified Phase-C artifacts.") from exc
    if weights.empty or summary.empty:
        raise DynamicEnsembleError("Phase-D requires non-empty Phase-C decisions and summary artifacts.")
    required = {"split_id", "variant", "date", "symbol", "expert_id", "expert_weight", "realized_next_net_return", "evaluation_status"}
    if missing := required - set(weights.columns):
        raise DynamicEnsembleError(f"Phase-C daily weights are missing required columns: {sorted(missing)}")
    return target, manifest, weights, summary


def _fit_quantile_regressor(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    schema: dict[str, Any],
    config: dict[str, Any],
    quantile: float,
):
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
        objective="quantile",
        alpha=float(quantile),
        n_estimators=int(model_config["n_estimators"]),
        learning_rate=float(model_config["learning_rate"]),
        num_leaves=int(model_config["num_leaves"]),
        min_child_samples=int(model_config["min_child_samples"]),
        n_jobs=int(model_config["n_jobs"]),
        random_state=int(config["random_seed"]),
        verbosity=-1,
        **lightgbm_runtime_params(),
    )
    model.fit(
        _feature_frame(valid, feature_columns, schema),
        pd.to_numeric(valid["future_utility"], errors="coerce"),
        categorical_feature=["expert_id"],
    )
    return model


def _training_distribution(frame: pd.DataFrame, feature_columns: list[str]) -> dict[str, dict[str, float]]:
    """Persist only train-fold numeric moments for a simple point-in-time OOD check."""

    distribution: dict[str, dict[str, float]] = {}
    for column in feature_columns:
        if column == "expert_id":
            continue
        values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            continue
        mean = float(values.mean())
        std = float(values.std(ddof=0))
        distribution[column] = {"mean": mean, "std": std}
    if not distribution:
        raise DynamicEnsembleError("Phase-D OOD check has no finite numeric training features.")
    return distribution


def _add_ood_scores(frame: pd.DataFrame, distribution: dict[str, dict[str, float]], *, threshold: float) -> pd.DataFrame:
    out = frame.copy()
    maximum = pd.Series(0.0, index=out.index, dtype=float)
    observed = pd.Series(False, index=out.index, dtype=bool)
    for column, moments in distribution.items():
        values = pd.to_numeric(out[column], errors="coerce")
        valid = values.notna() & np.isfinite(values)
        if not valid.any():
            continue
        std = float(moments["std"])
        centered = (values - float(moments["mean"])).abs()
        zscore = centered if std <= 1e-12 else centered / std
        maximum.loc[valid] = np.maximum(maximum.loc[valid], zscore.loc[valid])
        observed.loc[valid] = True
    out["ood_max_abs_zscore"] = maximum.where(observed, np.nan)
    out["input_out_of_distribution"] = observed & maximum.gt(float(threshold))
    return out


def _normalize_weights(weights: dict[str, float], *, ids: Iterable[str]) -> dict[str, float]:
    normalized = {str(expert_id): max(0.0, float(weights.get(str(expert_id), 0.0))) for expert_id in ids}
    total = float(sum(normalized.values()))
    if not math.isfinite(total) or total <= 0:
        raise DynamicEnsembleError("expert weights must have a positive finite total")
    return {expert_id: value / total for expert_id, value in normalized.items()}


def _fallback_weights(
    group: pd.DataFrame,
    *,
    policy: str,
    definition: dict[str, Any],
    max_risk_expert_weight: float,
) -> tuple[dict[str, float], str]:
    eligible = set(group.loc[group["eligible_for_weight"].astype(bool), "expert_id"].astype(str))
    if CASH_EXPERT_ID not in eligible:
        return {}, "cash_expert_unavailable"
    if policy == "cash":
        return {CASH_EXPERT_ID: 1.0}, "cash"
    if policy == "adaptive_router":
        expert_id = definition.get("adaptive_expert_id")
        if expert_id and expert_id in eligible:
            weights, _ = constrain_expert_weights(
                {CASH_EXPERT_ID: 0.0, str(expert_id): 1.0},
                max_risk_expert_weight=max_risk_expert_weight,
            )
            return weights, "adaptive_router"
        return {CASH_EXPERT_ID: 1.0}, "adaptive_router_unavailable_cash"
    equal = sorted(eligible.intersection(set(definition["equal_weight_expert_ids"])))
    if not equal:
        return {CASH_EXPERT_ID: 1.0}, "equal_weight_unavailable_cash"
    raw = {expert_id: 1.0 / len(equal) for expert_id in equal}
    raw[CASH_EXPERT_ID] = 0.0
    weights, _ = constrain_expert_weights(raw, max_risk_expert_weight=max_risk_expert_weight)
    return weights, "equal_weight"


def _quantile_weights_for_group(
    group: pd.DataFrame,
    *,
    previous: dict[str, float] | None,
    definition: dict[str, Any],
    gating: dict[str, Any],
    uncertainty: dict[str, Any],
    fallback: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float], str, str | None, dict[str, Any], bool]:
    """Turn point-in-time quantile predictions into a conservative safe allocation."""

    eligible = group.loc[group["eligible_for_weight"].astype(bool)].copy()
    eligible_ids = eligible["expert_id"].astype(str).tolist()
    diagnostics = {
        "mean_uncertainty_width": None,
        "max_uncertainty_width": None,
        "prediction_disagreement": None,
        "input_out_of_distribution": False,
        "fallback_trigger": None,
        "fallback_policy": None,
    }
    if CASH_EXPERT_ID not in eligible_ids:
        return {}, {}, "unavailable", "cash expert is unavailable", diagnostics, True
    risk = eligible.loc[~eligible["expert_id"].eq(CASH_EXPERT_ID)].copy()
    if risk.empty:
        return {CASH_EXPERT_ID: 1.0}, {CASH_EXPERT_ID: 1.0}, "fallback", "cash_only", diagnostics, True

    lower = pd.to_numeric(eligible["predicted_lower_utility"], errors="coerce").to_numpy(dtype=float)
    median = pd.to_numeric(eligible["predicted_median_utility"], errors="coerce").to_numpy(dtype=float)
    widths = np.abs(median - lower)
    conservative = median - float(uncertainty["gamma"]) * widths
    eligible["uncertainty_width"] = widths
    eligible["conservative_score"] = conservative
    risk = eligible.loc[~eligible["expert_id"].eq(CASH_EXPERT_ID)].copy()
    risk_widths = pd.to_numeric(risk["uncertainty_width"], errors="coerce")
    risk_scores = pd.to_numeric(risk["predicted_median_utility"], errors="coerce")
    diagnostics["mean_uncertainty_width"] = _finite_float(risk_widths.mean())
    diagnostics["max_uncertainty_width"] = _finite_float(risk_widths.max())
    diagnostics["prediction_disagreement"] = _finite_float(risk_scores.std(ddof=0))
    diagnostics["input_out_of_distribution"] = bool(risk["input_out_of_distribution"].fillna(False).any())

    triggers: list[tuple[str, str]] = []
    if diagnostics["input_out_of_distribution"]:
        triggers.append(("out_of_distribution", str(fallback["out_of_distribution_policy"])))
    if risk_widths.notna().all() and risk_widths.ge(float(uncertainty["confidence_width_threshold"])).all():
        triggers.append(("low_confidence", str(fallback["low_confidence_policy"])))
    if (
        diagnostics["prediction_disagreement"] is not None
        and float(diagnostics["prediction_disagreement"]) > float(uncertainty["disagreement_std_threshold"])
    ):
        triggers.append(("high_disagreement", str(fallback["high_disagreement_policy"])))
    if triggers:
        trigger, policy = triggers[0]
        weights, resolved = _fallback_weights(
            group,
            policy=policy,
            definition=definition,
            max_risk_expert_weight=float(gating["max_risk_expert_weight"]),
        )
        diagnostics["fallback_trigger"] = trigger
        diagnostics["fallback_policy"] = resolved
        return weights, weights.copy(), "fallback", f"{trigger}:{resolved}", diagnostics, True

    scores = eligible["conservative_score"].to_numpy(dtype=float)
    if not np.isfinite(scores).all():
        raw = {expert_id: 1.0 / len(eligible_ids) for expert_id in eligible_ids}
        reason = "nonfinite_quantile_prediction_equal_weight_fallback"
    else:
        raw = dict(zip(eligible_ids, stable_softmax(scores, temperature=float(gating["temperature"])), strict=True))
        reason = None
    weights = raw.copy()
    if previous:
        prior_values = {expert_id: float(previous.get(expert_id, 0.0)) for expert_id in eligible_ids}
        # A disappeared risk expert must leave to Cash, never be silently
        # redistributed to the remaining risk experts by the smoother.
        prior_values[CASH_EXPERT_ID] += sum(
            float(value) for expert_id, value in previous.items() if expert_id not in set(eligible_ids)
        )
        prior = _normalize_weights(prior_values, ids=eligible_ids)
        weights = {
            expert_id: float(gating["smoothing_alpha"]) * raw[expert_id]
            + (1.0 - float(gating["smoothing_alpha"])) * prior[expert_id]
            for expert_id in eligible_ids
        }
        reason = "; ".join(item for item in (reason, "exponential_smoothing") if item)
    weights, capped = constrain_expert_weights(
        weights,
        cash_expert_id=CASH_EXPERT_ID,
        max_risk_expert_weight=float(gating["max_risk_expert_weight"]),
    )
    if capped:
        reason = "; ".join(item for item in (reason, "risk_expert_cap") if item)
    return raw, weights, "ready", reason, diagnostics, False


def _final_target_position(group: pd.DataFrame, weights: dict[str, float]) -> float:
    positions = pd.to_numeric(group["target_position"], errors="coerce")
    return float(
        sum(
            float(weights.get(str(row.expert_id), 0.0)) * (0.0 if pd.isna(position) else float(position))
            for row, position in zip(group.itertuples(index=False), positions, strict=True)
        )
    )


def _scale_risk_to_cash(weights: dict[str, float], *, scale: float) -> dict[str, float]:
    ids = list(weights)
    if CASH_EXPERT_ID not in weights:
        raise DynamicEnsembleError("Cash expert is required before risk scaling.")
    adjusted = {expert_id: (float(value) * scale if expert_id != CASH_EXPERT_ID else 0.0) for expert_id, value in weights.items()}
    adjusted[CASH_EXPERT_ID] = 1.0 - sum(adjusted.values())
    return _normalize_weights(adjusted, ids=ids)


def _strictly_reduces_risk(current: dict[str, float], previous: dict[str, float]) -> bool:
    """Return whether a safety exception lowers total non-Cash exposure."""

    current_risk = sum(float(weight) for expert_id, weight in current.items() if expert_id != CASH_EXPERT_ID)
    previous_risk = sum(float(weight) for expert_id, weight in previous.items() if expert_id != CASH_EXPERT_ID)
    return current_risk < previous_risk - 1e-12


def _bounded_simplex_projection(
    desired: dict[str, float],
    previous: dict[str, float],
    *,
    ids: list[str],
    max_change: float,
    max_risk_expert_weight: float,
    unavailable_ids: set[str],
) -> tuple[dict[str, float], bool]:
    """Project a desired allocation onto sum-one, risk-cap, and daily-move bounds."""

    target = _normalize_weights(desired, ids=ids)
    prior = _normalize_weights(previous, ids=ids)
    lower: dict[str, float] = {}
    upper: dict[str, float] = {}
    for expert_id in ids:
        if expert_id in unavailable_ids and expert_id != CASH_EXPERT_ID:
            lower[expert_id] = upper[expert_id] = 0.0
            continue
        lower[expert_id] = max(0.0, prior[expert_id] - max_change)
        cap = 1.0 if expert_id == CASH_EXPERT_ID else max_risk_expert_weight
        upper[expert_id] = min(cap, prior[expert_id] + max_change)
    if sum(lower.values()) > 1.0 + 1e-9 or sum(upper.values()) < 1.0 - 1e-9:
        raise DynamicEnsembleError("max_weight_change bounds cannot form a valid expert allocation.")
    lo = min(lower[expert_id] - target[expert_id] for expert_id in ids) - 1.0
    hi = max(upper[expert_id] - target[expert_id] for expert_id in ids) + 1.0
    for _ in range(80):
        shift = (lo + hi) / 2.0
        total = sum(min(upper[expert_id], max(lower[expert_id], target[expert_id] + shift)) for expert_id in ids)
        if total < 1.0:
            lo = shift
        else:
            hi = shift
    result = {expert_id: min(upper[expert_id], max(lower[expert_id], target[expert_id] + hi)) for expert_id in ids}
    total = sum(result.values())
    result[CASH_EXPERT_ID] += 1.0 - total
    result = _normalize_weights(result, ids=ids)
    changed = any(abs(result[expert_id] - target[expert_id]) > 1e-8 for expert_id in ids)
    return result, changed


def _allocation_turnover(current: dict[str, float], previous: dict[str, float] | None, *, ids: Iterable[str]) -> float:
    if not previous:
        return 0.0
    return 0.5 * sum(abs(float(current.get(expert_id, 0.0)) - float(previous.get(expert_id, 0.0))) for expert_id in ids)


def _record_rows(
    group: pd.DataFrame,
    *,
    variant: str,
    split_id: str,
    raw_weights: dict[str, float],
    weights: dict[str, float],
    previous: dict[str, float] | None,
    status: str,
    reason: str | None,
    diagnostics: dict[str, Any],
    turnover: float,
    drawdown_before: float,
    risk_scale: float,
    holding_days: int,
    minimum_holding_applied: bool,
) -> list[dict[str, Any]]:
    final_position = _final_target_position(group, weights)
    rows: list[dict[str, Any]] = []
    for row in group.itertuples(index=False):
        expert_id = str(row.expert_id)
        weight = float(weights.get(expert_id, 0.0))
        previous_weight = _finite_float((previous or {}).get(expert_id)) if previous else None
        position = _finite_float(getattr(row, "target_position", None))
        rows.append(
            {
                "schema_version": PHASE_D_SCHEMA_VERSION,
                "market": str(row.market),
                "split_id": split_id,
                "variant": variant,
                "date": pd.Timestamp(row.date).date().isoformat(),
                "symbol": str(row.symbol),
                "expert_id": expert_id,
                "expert_status": str(row.expert_status),
                "is_test_label": bool(row.test_membership),
                "predicted_lower_utility": _finite_float(getattr(row, "predicted_lower_utility", None)),
                "predicted_median_utility": _finite_float(getattr(row, "predicted_median_utility", None)),
                "uncertainty_width": _finite_float(getattr(row, "uncertainty_width", None)),
                "conservative_score": _finite_float(getattr(row, "conservative_score", None)),
                "input_ood_max_abs_zscore": _finite_float(getattr(row, "ood_max_abs_zscore", None)),
                "input_out_of_distribution": bool(getattr(row, "input_out_of_distribution", False)),
                "future_utility": _finite_float(getattr(row, "future_utility", None)),
                "expert_target_position": position,
                "raw_expert_weight": _finite_float(raw_weights.get(expert_id, 0.0)),
                "previous_expert_weight": previous_weight,
                "is_initial_allocation": previous is None,
                "expert_weight": weight,
                "weight_change": weight - previous_weight if previous_weight is not None else None,
                "weighted_target_position": weight * (position or 0.0),
                "final_target_position": final_position,
                "realized_next_net_return": _finite_float(getattr(row, "realized_next_net_return", None)),
                "portfolio_turnover": turnover,
                "drawdown_before": drawdown_before,
                "risk_scale": risk_scale,
                "holding_days": holding_days,
                "minimum_holding_applied": minimum_holding_applied,
                "mean_uncertainty_width": diagnostics["mean_uncertainty_width"],
                "max_uncertainty_width": diagnostics["max_uncertainty_width"],
                "prediction_disagreement": diagnostics["prediction_disagreement"],
                "evaluation_status": status,
                "weight_change_reason": reason,
                "fallback_reason": reason if status != "ready" else None,
                "fallback_trigger": diagnostics["fallback_trigger"],
                "fallback_policy": diagnostics["fallback_policy"],
            }
        )
    return rows


def _simulate_quantile_policy(
    test: pd.DataFrame,
    *,
    split_id: str,
    variant: str,
    definition: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Simulate decisions chronologically so risk state is strictly pre-decision."""

    frame = test.copy()
    records: list[dict[str, Any]] = []
    previous_by_symbol: dict[str, dict[str, float]] = {}
    equity_by_symbol: dict[str, float] = {}
    peak_by_symbol: dict[str, float] = {}
    holding_by_symbol: dict[str, int] = {}
    active_by_symbol: dict[str, bool] = {}
    risk = policy["risk"]
    for _, day in frame.sort_values(["date", "symbol", "expert_id"]).groupby("date", sort=True):
        pending: list[dict[str, Any]] = []
        for symbol, group in day.groupby("symbol", sort=True):
            symbol_key = str(symbol)
            previous = previous_by_symbol.get(symbol_key)
            ids = group["expert_id"].astype(str).tolist()
            raw, weights, status, reason, diagnostics, safety_override = _quantile_weights_for_group(
                group,
                previous=previous,
                definition=definition,
                gating=policy["gating"],
                uncertainty=policy["uncertainty"],
                fallback=policy["fallback"],
            )
            equity = equity_by_symbol.get(symbol_key, 1.0)
            peak = peak_by_symbol.get(symbol_key, 1.0)
            drawdown = equity / peak - 1.0 if peak > 0 else 0.0
            risk_scale = 1.0
            if status != "unavailable" and drawdown <= -float(risk["drawdown_trigger"]):
                risk_scale = float(risk["drawdown_risk_scale"])
                weights = _scale_risk_to_cash(weights, scale=risk_scale)
                raw = raw or weights.copy()
                reason = "; ".join(item for item in (reason, "drawdown_risk_scale") if item)
                safety_override = True
            proposed_position = _final_target_position(group, weights) if weights else 0.0
            was_active = active_by_symbol.get(symbol_key, False)
            holding_days = holding_by_symbol.get(symbol_key, 0)
            minimum_holding_applied = False
            if (
                previous
                and was_active
                and proposed_position <= float(risk["position_active_threshold"])
                and holding_days < int(risk["minimum_holding_days"])
                and not safety_override
            ):
                weights = _normalize_weights(previous, ids=ids)
                reason = "; ".join(item for item in (reason, "minimum_holding_period") if item)
                minimum_holding_applied = True
            unavailable_ids = set(group.loc[~group["eligible_for_weight"].astype(bool), "expert_id"].astype(str))
            if previous and any(float(previous.get(expert_id, 0.0)) > 1e-12 for expert_id in unavailable_ids):
                safety_override = True
                reason = "; ".join(item for item in (reason, "missing_expert_safety_exit") if item)
            if previous and safety_override and not _strictly_reduces_risk(weights, previous):
                safety_override = False
                reason = "; ".join(item for item in (reason, "safety_constraints_enforced") if item)
            if previous and status != "unavailable" and not safety_override:
                weights, projected = _bounded_simplex_projection(
                    weights,
                    previous,
                    ids=ids,
                    max_change=float(risk["max_weight_change"]),
                    max_risk_expert_weight=float(policy["gating"]["max_risk_expert_weight"]),
                    unavailable_ids=unavailable_ids,
                )
                if projected:
                    reason = "; ".join(item for item in (reason, "max_daily_weight_change") if item)
            elif previous and safety_override:
                reason = "; ".join(item for item in (reason, "safety_override_weight_change") if item)
            elif previous is None:
                reason = "; ".join(item for item in (reason, "initial_allocation") if item)
            pending.append(
                {
                    "symbol": symbol_key,
                    "group": group,
                    "ids": ids,
                    "raw": raw,
                    "weights": weights,
                    "previous": previous,
                    "status": status,
                    "reason": reason,
                    "diagnostics": diagnostics,
                    "safety_override": safety_override,
                    "drawdown": drawdown,
                    "risk_scale": risk_scale,
                    "holding_days": holding_days,
                    "minimum_holding_applied": minimum_holding_applied,
                }
            )

        with_previous = [item for item in pending if item["previous"] and item["status"] != "unavailable"]
        total_turnover = sum(_allocation_turnover(item["weights"], item["previous"], ids=item["ids"]) for item in with_previous)
        cap_total = float(risk["max_portfolio_turnover"]) * len(with_previous)
        fixed_turnover = sum(
            _allocation_turnover(item["weights"], item["previous"], ids=item["ids"])
            for item in with_previous
            if item["safety_override"]
        )
        flexible = [item for item in with_previous if not item["safety_override"]]
        flexible_turnover = sum(
            _allocation_turnover(item["weights"], item["previous"], ids=item["ids"]) for item in flexible
        )
        if total_turnover > cap_total + 1e-12 and flexible_turnover > 0:
            scale = max(0.0, min(1.0, (cap_total - fixed_turnover) / flexible_turnover))
            for item in flexible:
                item["weights"] = {
                    expert_id: float(item["previous"].get(expert_id, 0.0))
                    + scale * (float(item["weights"].get(expert_id, 0.0)) - float(item["previous"].get(expert_id, 0.0)))
                    for expert_id in item["ids"]
                }
                item["weights"] = _normalize_weights(item["weights"], ids=item["ids"])
                item["reason"] = "; ".join(item_text for item_text in (item["reason"], "max_portfolio_turnover") if item_text)

        for item in pending:
            symbol_key = item["symbol"]
            group = item["group"]
            turnover = _allocation_turnover(item["weights"], item["previous"], ids=item["ids"])
            records.extend(
                _record_rows(
                    group,
                    variant=variant,
                    split_id=split_id,
                    raw_weights=item["raw"],
                    weights=item["weights"],
                    previous=item["previous"],
                    status=item["status"],
                    reason=item["reason"],
                    diagnostics=item["diagnostics"],
                    turnover=turnover,
                    drawdown_before=float(item["drawdown"]),
                    risk_scale=float(item["risk_scale"]),
                    holding_days=int(item["holding_days"]),
                    minimum_holding_applied=bool(item["minimum_holding_applied"]),
                )
            )
            if item["status"] == "unavailable":
                continue
            final_position = _final_target_position(group, item["weights"])
            threshold = float(risk["position_active_threshold"])
            is_active = final_position > threshold
            prior_active = active_by_symbol.get(symbol_key, False)
            holding_by_symbol[symbol_key] = holding_by_symbol.get(symbol_key, 0) + 1 if is_active and prior_active else int(is_active)
            active_by_symbol[symbol_key] = is_active
            previous_by_symbol[symbol_key] = _normalize_weights(item["weights"], ids=item["ids"])
            selected = group.loc[[float(item["weights"].get(str(expert_id), 0.0)) > 0 for expert_id in group["expert_id"]]].copy()
            realized = pd.to_numeric(selected["realized_next_net_return"], errors="coerce")
            if not selected.empty and realized.notna().all():
                next_return = float(
                    sum(
                        float(item["weights"].get(str(row.expert_id), 0.0)) * float(row.realized_next_net_return)
                        for row in selected.itertuples(index=False)
                    )
                )
                equity = equity_by_symbol.get(symbol_key, 1.0) * (1.0 + next_return)
                equity_by_symbol[symbol_key] = equity
                peak_by_symbol[symbol_key] = max(peak_by_symbol.get(symbol_key, 1.0), equity)
    return records


def _calibration_records(test: pd.DataFrame, *, split_id: str, variant: str, lower_quantile: float) -> dict[str, Any]:
    eligible = test.loc[test["eligible_for_weight"].astype(bool)].copy()
    actual = pd.to_numeric(eligible["future_utility"], errors="coerce")
    lower = pd.to_numeric(eligible["predicted_lower_utility"], errors="coerce")
    median = pd.to_numeric(eligible["predicted_median_utility"], errors="coerce")
    valid = actual.notna() & lower.notna() & median.notna()
    if not valid.any():
        return {
            "split_id": split_id,
            "variant": variant,
            "status": "unavailable",
            "sample_count": 0,
            "lower_quantile": lower_quantile,
            "observed_lower_tail_rate": None,
            "median_mae": None,
            "mean_uncertainty_width": None,
        }
    width = (median.loc[valid] - lower.loc[valid]).abs()
    return {
        "split_id": split_id,
        "variant": variant,
        "status": "ready",
        "sample_count": int(valid.sum()),
        "lower_quantile": lower_quantile,
        "observed_lower_tail_rate": float((actual.loc[valid] <= lower.loc[valid]).mean()),
        "median_mae": float((actual.loc[valid] - median.loc[valid]).abs().mean()),
        "mean_uncertainty_width": float(width.mean()),
    }


def _run_v2_variant(
    panel: pd.DataFrame,
    splits: pd.DataFrame,
    *,
    variant: str,
    feature_columns: list[str],
    schema: dict[str, Any],
    config: dict[str, Any],
    definition: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, pd.DataFrame]]:
    records: list[dict[str, Any]] = []
    calibration: list[dict[str, Any]] = []
    prediction_frames: dict[str, pd.DataFrame] = {}
    for split in splits.itertuples(index=False):
        split_id = str(split.split_id)
        train = panel.loc[_membership_mask(panel, split_id=split_id, role="train")].copy()
        lower_model = _fit_quantile_regressor(
            train, feature_columns=feature_columns, schema=schema, config=config, quantile=float(config["quantiles"]["lower"])
        )
        median_model = _fit_quantile_regressor(
            train, feature_columns=feature_columns, schema=schema, config=config, quantile=float(config["quantiles"]["median"])
        )
        test = _test_panel_for_split(panel, split_id=split_id)
        test["eligible_for_weight"] = _eligible_for_weight(test)
        eligible = test["eligible_for_weight"].astype(bool)
        test["predicted_lower_utility"] = np.nan
        test["predicted_median_utility"] = np.nan
        if eligible.any():
            features = _feature_frame(test.loc[eligible], feature_columns, schema)
            test.loc[eligible, "predicted_lower_utility"] = lower_model.predict(features)
            test.loc[eligible, "predicted_median_utility"] = median_model.predict(features)
        cash = test["expert_id"].eq(CASH_EXPERT_ID) & eligible
        test.loc[cash, "predicted_lower_utility"] = 0.0
        test.loc[cash, "predicted_median_utility"] = 0.0
        test["uncertainty_width"] = (
            pd.to_numeric(test["predicted_median_utility"], errors="coerce")
            - pd.to_numeric(test["predicted_lower_utility"], errors="coerce")
        ).abs()
        test["conservative_score"] = pd.to_numeric(test["predicted_median_utility"], errors="coerce") - float(
            config["uncertainty"]["gamma"]
        ) * test["uncertainty_width"]
        test = _add_ood_scores(
            test,
            _training_distribution(train, feature_columns),
            threshold=float(config["uncertainty"]["ood_max_abs_zscore"]),
        )
        records.extend(
            _simulate_quantile_policy(
                test,
                split_id=split_id,
                variant=variant,
                definition=definition,
                policy={key: config[key] for key in ("gating", "uncertainty", "fallback", "risk")},
            )
        )
        calibration.append(
            _calibration_records(test, split_id=split_id, variant=variant, lower_quantile=float(config["quantiles"]["lower"]))
        )
        prediction_frames[split_id] = test
    return records, calibration, prediction_frames


def _summary(weights: pd.DataFrame) -> pd.DataFrame:
    if weights.empty:
        return pd.DataFrame()
    active = weights.loc[weights["evaluation_status"].isin(["ready", "fallback"])].copy()
    if active.empty:
        return pd.DataFrame()
    active["expert_weight"] = pd.to_numeric(active["expert_weight"], errors="coerce").fillna(0.0)
    active["realized_next_net_return"] = pd.to_numeric(active["realized_next_net_return"], errors="coerce")
    active["future_utility"] = pd.to_numeric(active.get("future_utility"), errors="coerce")
    rows: list[dict[str, Any]] = []
    for (market, split_id, variant), frame in active.groupby(["market", "split_id", "variant"], sort=True):
        decisions: list[dict[str, Any]] = []
        for (date, symbol), group in frame.groupby(["date", "symbol"], sort=True):
            selected = group.loc[group["expert_weight"] > 0]
            valid_return = not selected.empty and selected["realized_next_net_return"].notna().all()
            decisions.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "net_return": float((selected["expert_weight"] * selected["realized_next_net_return"]).sum()) if valid_return else np.nan,
                    "turnover": _finite_float(group["portfolio_turnover"].iloc[0]) if "portfolio_turnover" in group else None,
                    "max_weight_change": float(pd.to_numeric(group["weight_change"], errors="coerce").abs().max()),
                    "fallback": bool(group["evaluation_status"].eq("fallback").any()),
                }
            )
        decision_frame = pd.DataFrame(decisions)
        daily = decision_frame.groupby("date", sort=True)["net_return"].mean().dropna()
        metrics = _performance_metrics(daily)
        tail_count = max(1, int(math.ceil(len(daily) * 0.05))) if len(daily) else 0
        rows.append(
            {
                "market": market,
                "split_id": split_id,
                "variant": variant,
                "status": "ready" if not daily.empty else "unavailable",
                "decision_count": int(len(decision_frame)),
                "daily_return_count": int(len(daily)),
                "mean_portfolio_turnover": _finite_float(decision_frame["turnover"].mean()),
                "max_portfolio_turnover": _finite_float(decision_frame["turnover"].max()),
                "max_daily_weight_change": _finite_float(decision_frame["max_weight_change"].max()),
                "fallback_decision_count": int(decision_frame["fallback"].sum()),
                "worst_daily_return": _finite_float(daily.min()),
                "tail_loss_cvar_5": _finite_float(daily.nsmallest(tail_count).mean()) if tail_count else None,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _annotate_phase_c_turnover(weights: pd.DataFrame) -> pd.DataFrame:
    """Derive v1 turnover only for comparison; no costs are added to returns."""

    out = weights.copy()
    out["portfolio_turnover"] = 0.0
    for (_, _, symbol), frame in out.groupby(["split_id", "variant", "symbol"], sort=True):
        previous: dict[str, float] | None = None
        for _, day in frame.groupby("date", sort=True):
            current = {str(row.expert_id): float(row.expert_weight) for row in day.itertuples(index=False)}
            ids = list(current)
            turnover = _allocation_turnover(current, previous, ids=ids)
            out.loc[day.index, "portfolio_turnover"] = turnover
            previous = current
    return out


def _ablation_rows(
    prediction_frames: dict[str, pd.DataFrame],
    *,
    variant: str,
    definition: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    combinations = itertools.product(
        config["ablation"]["temperatures"],
        config["ablation"]["max_risk_expert_weights"],
        config["ablation"]["smoothing_alphas"],
    )
    for temperature, cap, alpha in combinations:
        policy = {key: config[key] for key in ("gating", "uncertainty", "fallback", "risk")}
        policy["gating"] = {**policy["gating"], "temperature": float(temperature), "max_risk_expert_weight": float(cap), "smoothing_alpha": float(alpha)}
        records: list[dict[str, Any]] = []
        for split_id, test in prediction_frames.items():
            records.extend(
                _simulate_quantile_policy(test, split_id=split_id, variant=variant, definition=definition, policy=policy)
            )
        summary = _summary(pd.DataFrame(records))
        for row in summary.itertuples(index=False):
            rows.append(
                {
                    "variant": variant,
                    "split_id": row.split_id,
                    "temperature": float(temperature),
                    "max_risk_expert_weight": float(cap),
                    "smoothing_alpha": float(alpha),
                    **row._asdict(),
                }
            )
    return rows


def _feature_importance(model: Any, feature_columns: list[str]) -> list[dict[str, Any]]:
    values = getattr(model, "feature_importances_", None)
    if values is None:
        return []
    return [
        {"feature": feature, "importance_split": int(value)}
        for feature, value in sorted(zip(feature_columns, values, strict=True), key=lambda item: int(item[1]), reverse=True)
    ]


def _report_markdown(
    comparison: pd.DataFrame,
    calibration: pd.DataFrame,
    ablation: pd.DataFrame,
    *,
    config: dict[str, Any],
) -> str:
    lines = [
        "# Phase-D Uncertainty- and Risk-Aware MoE v2",
        "",
        f"- Market: `{config['market']}`; primary horizon: `{config['primary_horizon_days']}` trading days",
        f"- Quantiles: lower `{config['quantiles']['lower']}`, median `{config['quantiles']['median']}`; gamma `{config['uncertainty']['gamma']}`",
        f"- Fallback policy: low confidence → `{config['fallback']['low_confidence_policy']}`, disagreement → `{config['fallback']['high_disagreement_policy']}`, OOD → `{config['fallback']['out_of_distribution_policy']}`",
        f"- Risk limits: weight move `{config['risk']['max_weight_change']:.0%}`, aggregate turnover `{config['risk']['max_portfolio_turnover']:.0%}`, drawdown trigger `{config['risk']['drawdown_trigger']:.0%}`",
        "",
        "## MoE v1 / v2 comparison",
        "",
        "| Split | Variant | Status | Total return | Sharpe | Max drawdown | Tail loss (5%) | Mean turnover | Fallbacks |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison.itertuples(index=False):
        def fmt(value: Any) -> str:
            return "—" if value is None or (isinstance(value, float) and not math.isfinite(value)) else f"{float(value):.4f}"

        lines.append(
            f"| {row.split_id} | {row.variant} | {row.status} | {fmt(row.total_return)} | {fmt(row.sharpe)} | "
            f"{fmt(row.max_drawdown)} | {fmt(row.tail_loss_cvar_5)} | {fmt(row.mean_portfolio_turnover)} | {row.fallback_decision_count} |"
        )
    lines.extend(["", "## Uncertainty calibration", "", "| Split | Variant | Samples | Lower-tail rate | Median MAE | Mean width |", "|---|---|---:|---:|---:|---:|"])
    for row in calibration.itertuples(index=False):
        lines.append(
            f"| {row.split_id} | {row.variant} | {row.sample_count} | {row.observed_lower_tail_rate if pd.notna(row.observed_lower_tail_rate) else '—'} | "
            f"{row.median_mae if pd.notna(row.median_mae) else '—'} | {row.mean_uncertainty_width if pd.notna(row.mean_uncertainty_width) else '—'} |"
        )
    lines.extend(
        [
            "",
            "## Risk-constraint ablation",
            "",
            f"The CSV contains `{len(ablation)}` split-level cells across the temperature, expert-cap, and smoothing grid.",
            "",
            "## Safety guarantees",
            "",
            "- Quantile models fit only the purged Phase-B train memberships; test memberships remain out of fit.",
            "- Conservative score is median utility minus gamma times the lower/median quantile width; Cash is fixed at zero utility and always available.",
            "- Low confidence, excessive score disagreement, and OOD inputs take an auditable configured fallback path.",
            "- Weight-change and aggregate-turnover limits apply to ordinary rebalances. Safety fallbacks and drawdown de-risking may bypass them only to reduce risk, and are recorded as such.",
            "- Source `strategy_return` is already net of source execution costs. This research layer never charges it a second time.",
            "- This remains research-only and does not import Streamlit or change online defaults.",
            "",
        ]
    )
    return "\n".join(lines)


def materialize_dynamic_ensemble_v2(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Train/evaluate Phase-D quantile-gating and write source-locked artifacts."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_dynamic_ensemble_v2_config(config_file)
    panel_dir, panel, splits, panel_manifest, baselines = _load_phase_b_input(config, repo_root=root)
    phase_c_dir, phase_c_manifest, phase_c_weights, _ = _load_phase_c_input(config, repo_root=root, panel_dir=panel_dir)
    configure_lightgbm_environment(device_type=str(config["model"].get("device_type", "cpu")))
    device_check = validate_lightgbm_device(str(config["model"].get("device_type", "cpu")))
    if not device_check.get("available"):
        raise DynamicEnsembleError(f"LightGBM device preflight failed: {device_check.get('error', 'unknown error')}")

    panel = _with_next_net_return(panel)
    schema = _feature_schema(panel, panel_manifest)
    definition = _baseline_definition(panel, panel_manifest, baselines)
    all_records: list[dict[str, Any]] = []
    all_calibration: list[dict[str, Any]] = []
    prediction_sets: dict[str, dict[str, pd.DataFrame]] = {}
    for variant, features in (
        ("moe_v2_no_state", schema["no_state_feature_columns"]),
        ("moe_v2_regime_aware", schema["full_feature_columns"]),
    ):
        records, calibration, prediction_frames = _run_v2_variant(
            panel,
            splits,
            variant=variant,
            feature_columns=features,
            schema=schema,
            config=config,
            definition=definition,
        )
        all_records.extend(records)
        all_calibration.extend(calibration)
        prediction_sets[variant] = prediction_frames
    weights = pd.DataFrame(all_records)
    summary = _summary(weights)
    if not set(MODEL_VARIANTS).issubset(set(summary.loc[summary["status"].eq("ready"), "variant"])):
        raise DynamicEnsembleError("Phase D did not produce ready walk-forward results for both MoE v2 variants.")
    calibration = pd.DataFrame(all_calibration)
    ablation = pd.DataFrame(
        [
            row
            for variant, frames in prediction_sets.items()
            for row in _ablation_rows(frames, variant=variant, definition=definition, config=config)
        ]
    )

    v1 = phase_c_weights.loc[phase_c_weights["variant"].isin(PHASE_C_MODEL_VARIANTS)].copy()
    v1["variant"] = v1["variant"].map({"moe_no_state": "moe_v1_no_state", "moe_regime_aware": "moe_v1_regime_aware"})
    v1 = _annotate_phase_c_turnover(v1)
    comparison = pd.concat([_summary(v1), summary], ignore_index=True, sort=False)

    full_train = panel.loc[
        panel["expert_status"].eq("available") & pd.to_numeric(panel["future_utility"], errors="coerce").notna()
    ].copy()
    final_models: dict[str, Any] = {}
    schema["quantile_feature_importance"] = {}
    for variant, features in (
        ("moe_v2_no_state", schema["no_state_feature_columns"]),
        ("moe_v2_regime_aware", schema["full_feature_columns"]),
    ):
        lower_model = _fit_quantile_regressor(
            full_train, feature_columns=features, schema=schema, config=config, quantile=float(config["quantiles"]["lower"])
        )
        median_model = _fit_quantile_regressor(
            full_train, feature_columns=features, schema=schema, config=config, quantile=float(config["quantiles"]["median"])
        )
        final_models[variant] = {"lower_quantile_model": lower_model, "median_quantile_model": median_model}
        schema["quantile_feature_importance"][variant] = {
            "lower": _feature_importance(lower_model, features),
            "median": _feature_importance(median_model, features),
        }

    target = Path(output_dir) if output_dir is not None else root / "model-test" / "outputs" / str(config["output_subdir"])
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "moe_v2_model.pkl"
    schema_path = target / "moe_v2_feature_schema.json"
    weights_path = target / "moe_v2_daily_weights.parquet"
    summary_path = target / "moe_v2_summary.csv"
    calibration_path = target / "moe_uncertainty_calibration.csv"
    ablation_path = target / "moe_risk_ablation.csv"
    comparison_path = target / "moe_v1_v2_comparison.csv"
    report_path = target / "moe_v2_report.md"
    manifest_path = target / "moe_v2_manifest.json"
    with model_path.open("wb") as handle:
        pickle.dump(
            {
                "schema_version": PHASE_D_SCHEMA_VERSION,
                "market": config["market"],
                "quantiles": config["quantiles"],
                "models": final_models,
                "feature_schema": schema,
            },
            handle,
        )
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    weights.to_parquet(weights_path, index=False)
    summary.to_csv(summary_path, index=False)
    calibration.to_csv(calibration_path, index=False)
    ablation.to_csv(ablation_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    report_path.write_text(_report_markdown(comparison, calibration, ablation, config=config), encoding="utf-8")
    artifact_paths = {
        "moe_v2_model": model_path,
        "feature_schema": schema_path,
        "daily_weights": weights_path,
        "summary": summary_path,
        "uncertainty_calibration": calibration_path,
        "risk_ablation": ablation_path,
        "v1_v2_comparison": comparison_path,
        "report": report_path,
    }
    manifest = {
        "schema_version": PHASE_D_SCHEMA_VERSION,
        "phase": "D",
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
        "phase_c_output_dir": phase_c_dir.relative_to(root).as_posix(),
        "phase_c_manifest_sha256": _sha256_file(phase_c_dir / "moe_manifest.json"),
        "phase_c_source_lock": {
            "phase_b_manifest_sha256": phase_c_manifest.get("phase_b_manifest_sha256"),
            "phase_a_manifest_sha256": phase_c_manifest.get("phase_a_manifest_sha256"),
        },
        "random_seed": config["random_seed"],
        "primary_horizon_days": config["primary_horizon_days"],
        "return_field": config["return_field"],
        "cost_treatment": config["cost_treatment"],
        "model": config["model"],
        "quantiles": config["quantiles"],
        "gating": config["gating"],
        "uncertainty": config["uncertainty"],
        "fallback": config["fallback"],
        "risk": config["risk"],
        "ablation": config["ablation"],
        "lightgbm_preflight": device_check,
        "feature_schema": schema,
        "baseline_definition": {**definition, "equal_weight_expert_ids": sorted(definition["equal_weight_expert_ids"])},
        "artifacts": {
            name: {"path": path.name, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
            for name, path in artifact_paths.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**artifact_paths, "manifest": manifest_path}


__all__ = [
    "FALLBACK_POLICIES",
    "MODEL_VARIANTS",
    "PHASE_D_SCHEMA_VERSION",
    "load_dynamic_ensemble_v2_config",
    "materialize_dynamic_ensemble_v2",
    "validate_dynamic_ensemble_v2_config",
]
