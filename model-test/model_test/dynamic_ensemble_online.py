"""Phase-E online full-information expert weighting research.

This module is intentionally kept under ``model-test``.  It replays the
source-locked expert panel after a frozen offline MoE decision and updates the
allocation with complete-feedback Hedge / Exponentiated Gradient (EG).  The
online layer never charges ``strategy_return`` a second time and is not
imported by the Streamlit workflow.
"""

from __future__ import annotations

import itertools
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from model_test.dynamic_ensemble import (
    CASH_EXPERT_ID,
    DynamicEnsembleError,
    _baseline_definition,
    _load_phase_b_input,
    _performance_metrics,
    _relative_path,
    _sha256_file,
    constrain_expert_weights,
)
from model_test.dynamic_ensemble_v2 import _bounded_simplex_projection
from model_test.moe_baseline import MoEBaselineError, _canonical_market


PHASE_E_SCHEMA_VERSION = "1.0"
PRIMARY_HORIZON_DAYS = 20
ALGORITHMS = ("soft_moe", "hedge", "eg")
ONLINE_ALGORITHMS = ("hedge", "eg")
LEARNING_RATE_MODES = ("fixed", "volatility_adaptive")


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
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_finite(value: Any, *, field_name: str, allow_zero: bool = False) -> float:
    number = _finite_float(value)
    if number is None or (number < 0 if allow_zero else number <= 0):
        expected = "non-negative" if allow_zero else "positive"
        raise DynamicEnsembleError(f"{field_name} must be a {expected} finite number.")
    return number


def _path_value(config: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def load_online_ensemble_config(path: str | Path) -> dict[str, Any]:
    config = _json_object(Path(path))
    validate_online_ensemble_config(config)
    return config


def validate_online_ensemble_config(config: dict[str, Any]) -> None:
    """Validate the immutable market, return and safety contract for Phase E."""

    if str(config.get("schema_version")) != PHASE_E_SCHEMA_VERSION:
        raise DynamicEnsembleError(f"schema_version must be {PHASE_E_SCHEMA_VERSION!r}.")
    if str(config.get("phase") or "").upper() != "E":
        raise DynamicEnsembleError("phase must be 'E'.")
    try:
        _canonical_market(config.get("market"))
    except MoEBaselineError as exc:
        raise DynamicEnsembleError(str(exc)) from exc
    _relative_path(config.get("panel_output_dir"), field_name="panel_output_dir")
    source_path = _path_value(config, "phase_d_output_dir", "initial_output_dir", "phase_c_output_dir")
    if not source_path:
        raise DynamicEnsembleError("Phase E requires phase_d_output_dir (or a compatible initial_output_dir).")
    _relative_path(source_path, field_name="phase_d_output_dir")
    _relative_path(config.get("output_subdir"), field_name="output_subdir")
    if int(config.get("random_seed", -1)) != 42:
        raise DynamicEnsembleError("Phase E freezes random_seed at 42.")
    if config.get("training_scope") != "market_specific":
        raise DynamicEnsembleError("Phase E must train/evaluate one market at a time.")
    if config.get("cross_market_policy") != "ablation_only":
        raise DynamicEnsembleError("cross_market_policy must remain 'ablation_only'.")
    if int(config.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase E primary_horizon_days must remain 20.")
    if config.get("return_field") != "strategy_return":
        raise DynamicEnsembleError("Phase E must consume the source net strategy_return field.")
    if config.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase E must not recharge source transaction costs.")

    online = config.get("online")
    if not isinstance(online, dict):
        raise DynamicEnsembleError("online must be an object.")
    _positive_finite(online.get("base_learning_rate", online.get("learning_rate")), field_name="online.base_learning_rate")
    _positive_finite(online.get("reward_clip", 0.05), field_name="online.reward_clip")
    _positive_finite(online.get("volatility_floor", 0.005), field_name="online.volatility_floor")
    if int(online.get("volatility_lookback", 20)) <= 0:
        raise DynamicEnsembleError("online.volatility_lookback must be a positive integer.")
    if _positive_finite(online.get("min_learning_rate", 0.01), field_name="online.min_learning_rate") > _positive_finite(
        online.get("max_learning_rate", 2.0), field_name="online.max_learning_rate"
    ):
        raise DynamicEnsembleError("online.min_learning_rate cannot exceed online.max_learning_rate.")
    cash_id = online.get("cash_expert_id", CASH_EXPERT_ID)
    if cash_id != CASH_EXPERT_ID:
        raise DynamicEnsembleError("Phase E requires the frozen cash expert id 'cash'.")
    algorithms = online.get("algorithms", ["hedge", "eg"])
    if not isinstance(algorithms, list) or not algorithms or any(str(item) not in ONLINE_ALGORITHMS for item in algorithms):
        raise DynamicEnsembleError(f"online.algorithms must contain only {list(ONLINE_ALGORITHMS)}.")
    modes = online.get("learning_rate_modes", ["fixed", "volatility_adaptive"])
    if not isinstance(modes, list) or not modes or any(str(item) not in LEARNING_RATE_MODES for item in modes):
        raise DynamicEnsembleError(f"online.learning_rate_modes must contain only {list(LEARNING_RATE_MODES)}.")
    forgetting = online.get("forgetting_factors", [1.0, 0.98])
    if not isinstance(forgetting, list) or not forgetting:
        raise DynamicEnsembleError("online.forgetting_factors must be a non-empty list.")
    for value in forgetting:
        numeric = _positive_finite(value, field_name="online.forgetting_factors", allow_zero=True)
        if numeric > 1:
            raise DynamicEnsembleError("online.forgetting_factors values must be in [0, 1].")

    gating = config.get("gating", {})
    if not isinstance(gating, dict):
        raise DynamicEnsembleError("gating must be an object.")
    cap = _positive_finite(gating.get("max_risk_expert_weight", 0.4), field_name="gating.max_risk_expert_weight")
    if cap > 1:
        raise DynamicEnsembleError("gating.max_risk_expert_weight must be at most 1.")
    initial_variant = str(online.get("initial_variant", "moe_v2_regime_aware"))
    if not initial_variant:
        raise DynamicEnsembleError("online.initial_variant cannot be empty.")
    _positive_finite(online.get("max_weight_change", 0.15), field_name="online.max_weight_change")
    if float(online.get("max_weight_change", 0.15)) > 1:
        raise DynamicEnsembleError("online.max_weight_change must be at most 1.")


# Compatibility aliases make the phase easy to discover alongside the C/D modules.
load_dynamic_ensemble_online_config = load_online_ensemble_config
validate_dynamic_ensemble_online_config = validate_online_ensemble_config


def _normalize_weights(weights: dict[str, float], ids: Iterable[str]) -> dict[str, float]:
    normalized = {str(identifier): max(0.0, float(weights.get(str(identifier), 0.0))) for identifier in ids}
    total = sum(normalized.values())
    if not math.isfinite(total) or total <= 0:
        raise DynamicEnsembleError("online expert weights must have a positive finite total.")
    return {identifier: value / total for identifier, value in normalized.items()}


def _stable_exponential(log_values: dict[str, float], ids: list[str]) -> dict[str, float]:
    values = np.asarray([float(log_values.get(identifier, -np.inf)) for identifier in ids], dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        return {identifier: 1.0 / len(ids) for identifier in ids}
    peak = float(np.nanmax(values[finite]))
    exp_values = np.exp(np.clip(values - peak, -745.0, 0.0))
    total = float(exp_values.sum())
    if not math.isfinite(total) or total <= 0:
        return {identifier: 1.0 / len(ids) for identifier in ids}
    return {identifier: float(exp_values[index] / total) for index, identifier in enumerate(ids)}


def _prepare_reward_map(
    weights: dict[str, float],
    returns: dict[str, float | None],
    *,
    ids: list[str],
    cash_expert_id: str = CASH_EXPERT_ID,
) -> tuple[dict[str, float], dict[str, float], set[str]]:
    """Remove unavailable experts and transfer their allocation to Cash."""

    if cash_expert_id not in ids:
        raise DynamicEnsembleError("Cash expert must always be present in an online decision group.")
    prior = _normalize_weights(weights, ids)
    available: set[str] = set()
    reward_map: dict[str, float] = {}
    for identifier in ids:
        value = _finite_float(returns.get(identifier))
        if identifier == cash_expert_id or value is not None:
            available.add(identifier)
            reward_map[identifier] = 0.0 if value is None else value
    unavailable = set(ids).difference(available)
    for identifier in unavailable:
        prior[cash_expert_id] += prior.get(identifier, 0.0)
        prior[identifier] = 0.0
    return _normalize_weights(prior, ids), reward_map, unavailable


def hedge_update(
    previous_weights: dict[str, float],
    expert_returns: dict[str, float | None],
    *,
    learning_rate: float,
    forgetting_factor: float = 1.0,
    reward_clip: float = 0.05,
    cash_expert_id: str = CASH_EXPERT_ID,
) -> dict[str, float]:
    """Perform a numerically stable full-information Hedge update."""

    ids = [str(identifier) for identifier in previous_weights]
    if cash_expert_id not in ids:
        raise DynamicEnsembleError("Cash expert must always be present for Hedge.")
    prior, rewards, unavailable = _prepare_reward_map(previous_weights, expert_returns, ids=ids, cash_expert_id=cash_expert_id)
    logs: dict[str, float] = {}
    for identifier in ids:
        if identifier in unavailable:
            logs[identifier] = -np.inf
            continue
        reward = float(np.clip(rewards.get(identifier, 0.0), -reward_clip, reward_clip))
        logs[identifier] = float(forgetting_factor) * math.log(max(prior[identifier], 1e-300)) + float(learning_rate) * reward
    return _stable_exponential(logs, ids)


def exponentiated_gradient_update(
    previous_weights: dict[str, float],
    expert_returns: dict[str, float | None],
    *,
    learning_rate: float,
    forgetting_factor: float = 1.0,
    reward_clip: float = 0.05,
    cash_expert_id: str = CASH_EXPERT_ID,
) -> dict[str, float]:
    """Perform an EG update using returns centred by the current mixture reward."""

    ids = [str(identifier) for identifier in previous_weights]
    if cash_expert_id not in ids:
        raise DynamicEnsembleError("Cash expert must always be present for EG.")
    prior, rewards, unavailable = _prepare_reward_map(previous_weights, expert_returns, ids=ids, cash_expert_id=cash_expert_id)
    clipped = {identifier: float(np.clip(rewards.get(identifier, 0.0), -reward_clip, reward_clip)) for identifier in ids}
    mixture = sum(prior[identifier] * clipped.get(identifier, 0.0) for identifier in ids if identifier not in unavailable)
    logs: dict[str, float] = {}
    for identifier in ids:
        if identifier in unavailable:
            logs[identifier] = -np.inf
            continue
        logs[identifier] = float(forgetting_factor) * math.log(max(prior[identifier], 1e-300)) + float(learning_rate) * (clipped[identifier] - mixture)
    return _stable_exponential(logs, ids)


def apply_online_constraints(
    desired_weights: dict[str, float],
    previous_weights: dict[str, float] | None,
    *,
    ids: list[str],
    max_weight_change: float,
    max_risk_expert_weight: float,
    unavailable_ids: set[str] | None = None,
) -> tuple[dict[str, float], bool]:
    """Apply the frozen Cash/cap/simplex contract and daily movement bound."""

    unavailable = set(unavailable_ids or set())
    desired = dict(desired_weights)
    for identifier in unavailable:
        desired[identifier] = 0.0
    desired[CASH_EXPERT_ID] = float(desired.get(CASH_EXPERT_ID, 0.0))
    constrained, capped = constrain_expert_weights(
        _normalize_weights(desired, ids), max_risk_expert_weight=float(max_risk_expert_weight)
    )
    if previous_weights is None:
        return _normalize_weights(constrained, ids), bool(capped)
    projected, moved = _bounded_simplex_projection(
        constrained,
        previous_weights,
        ids=ids,
        max_change=float(max_weight_change),
        max_risk_expert_weight=float(max_risk_expert_weight),
        unavailable_ids=unavailable,
    )
    return projected, bool(capped or moved)


def _verify_artifact(directory: Path, manifest: dict[str, Any], key: str, *, phase: str) -> Path:
    artifacts = manifest.get("artifacts")
    descriptor = artifacts.get(key) if isinstance(artifacts, dict) else None
    if not isinstance(descriptor, dict) or not descriptor.get("path"):
        raise DynamicEnsembleError(f"{phase} manifest is missing artifact metadata for {key}.")
    path = directory / str(descriptor["path"])
    if not path.is_file():
        raise DynamicEnsembleError(f"{phase} artifact is missing: {path}")
    expected = str(descriptor.get("sha256") or "")
    if expected and _sha256_file(path) != expected:
        raise DynamicEnsembleError(f"{phase} artifact hash differs from its manifest: {path}")
    return path


def _load_initial_source(
    config: dict[str, Any], *, repo_root: Path, panel_dir: Path
) -> tuple[Path, dict[str, Any], pd.DataFrame, pd.DataFrame, str]:
    """Load the ready Phase-D output, with a strict Phase-C compatibility fallback."""

    raw_path = _path_value(config, "phase_d_output_dir", "initial_output_dir")
    phase = "D"
    if raw_path is None:
        raw_path = _path_value(config, "phase_c_output_dir")
        phase = "C"
    target = (repo_root / _relative_path(raw_path, field_name="initial_output_dir")).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise DynamicEnsembleError("initial online source must remain inside the repository.") from exc
    manifest_name = "moe_v2_manifest.json" if phase == "D" else "moe_manifest.json"
    manifest_path = target / manifest_name
    if not manifest_path.is_file():
        raise DynamicEnsembleError(f"Phase E requires a ready Phase-{phase} manifest.")
    manifest = _json_object(manifest_path)
    if manifest.get("phase") != phase or manifest.get("status") != "ready":
        raise DynamicEnsembleError(f"Phase E requires a ready Phase-{phase} initial source.")
    if _canonical_market(manifest.get("market")) != _canonical_market(config["market"]):
        raise DynamicEnsembleError("Phase E source and config markets must match.")
    if int(manifest.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase E source horizon does not match the frozen 20-day horizon.")
    if manifest.get("return_field") != "strategy_return" or manifest.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase E source return/cost contract is incompatible.")
    expected_panel = panel_dir.relative_to(repo_root).as_posix()
    if str(manifest.get("phase_b_panel_dir")) != expected_panel:
        raise DynamicEnsembleError("Phase E source was built from a different Phase-B panel directory.")
    phase_a_hash = _sha256_file(panel_dir / "data_manifest.json")
    phase_b_hash = _sha256_file(panel_dir / "expert_panel_manifest.json")
    if str(manifest.get("phase_a_manifest_sha256") or "") != phase_a_hash:
        raise DynamicEnsembleError("Phase E source Phase-A manifest hash no longer matches the panel.")
    if str(manifest.get("phase_b_manifest_sha256") or "") != phase_b_hash:
        raise DynamicEnsembleError("Phase E source Phase-B manifest hash no longer matches the panel.")
    weights_key = "daily_weights"
    weights_path = _verify_artifact(target, manifest, weights_key, phase=f"Phase-{phase}")
    summary_path = _verify_artifact(target, manifest, "summary", phase=f"Phase-{phase}")
    try:
        weights = pd.read_parquet(weights_path)
        summary = pd.read_csv(summary_path)
    except (OSError, ValueError, ImportError) as exc:
        raise DynamicEnsembleError(f"Phase E could not read the verified Phase-{phase} source.") from exc
    required = {"split_id", "variant", "date", "symbol", "expert_id", "expert_weight"}
    if missing := required - set(weights.columns):
        raise DynamicEnsembleError(f"Phase-{phase} daily weights are missing required columns: {sorted(missing)}")
    if weights.empty or summary.empty:
        raise DynamicEnsembleError("Phase E requires non-empty initial weights and summary artifacts.")
    return target, manifest, weights, summary, phase


def _return_panel(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    # Source panels are expected to be chronological, but the online replay
    # must remain causal even when a parquet reader or test fixture provides
    # rows in an arbitrary order.  Compute the next observed return only after
    # sorting within each symbol/expert timeline, then restore a deterministic
    # date/symbol/expert order for downstream joins.
    frame["expert_id"] = frame["expert_id"].astype(str)
    frame["strategy_return"] = pd.to_numeric(frame["strategy_return"], errors="coerce")
    frame["symbol"] = frame["symbol"].astype(str)
    frame = frame.sort_values(["symbol", "expert_id", "date"], kind="mergesort").copy()
    frame["realized_next_net_return"] = frame.groupby(["symbol", "expert_id"], sort=False)["strategy_return"].shift(-1)
    if "expert_status" not in frame:
        frame["expert_status"] = "available"
    return frame.sort_values(["date", "symbol", "expert_id"], kind="mergesort").reset_index(drop=True)


def _source_variant(config: dict[str, Any], source_weights: pd.DataFrame) -> str:
    requested = str(config.get("online", {}).get("initial_variant", "moe_v2_regime_aware"))
    variants = set(source_weights["variant"].astype(str))
    aliases = {
        "moe_v2": "moe_v2_regime_aware",
        "moe_regime_aware": "moe_v2_regime_aware",
        "moe_no_state": "moe_v2_no_state",
    }
    requested = aliases.get(requested, requested)
    if requested in variants:
        return requested
    fallback = [item for item in ("moe_v2_regime_aware", "moe_v2_no_state", "moe_regime_aware", "moe_no_state") if item in variants]
    if fallback:
        return fallback[0]
    raise DynamicEnsembleError(f"Phase E initial variant is unavailable: {requested}")


def _prepare_source_frame(
    panel: pd.DataFrame,
    source_weights: pd.DataFrame,
    *,
    source_variant: str,
    market: str,
) -> pd.DataFrame:
    source = source_weights.loc[source_weights["variant"].astype(str).eq(source_variant)].copy()
    if source.empty:
        raise DynamicEnsembleError(f"No initial Phase-E weights for variant {source_variant!r}.")
    source["date"] = pd.to_datetime(source["date"])
    source["symbol"] = source["symbol"].astype(str)
    source["expert_id"] = source["expert_id"].astype(str)
    source["expert_weight"] = pd.to_numeric(source["expert_weight"], errors="coerce").fillna(0.0)
    panel_frame = _return_panel(panel)
    # Phase-B stores split membership as JSON because one row can be eligible
    # for more than one walk-forward role.  Phase-C/D source artifacts already
    # materialize the concrete test split, so the join intentionally uses only
    # the point-in-time identity columns below.
    keys = ["date", "symbol", "expert_id"]
    # Source daily artifacts are already test-only.  Preserve their rows and
    # fill the canonical net next return/status from the Phase-B panel.
    panel_rows = panel_frame[keys + ["expert_status", "unavailable_reason", "target_position", "realized_next_net_return"]].copy()
    merged = source.merge(panel_rows, on=["date", "symbol", "expert_id"], how="left", suffixes=("", "_panel"))
    if "expert_status_panel" in merged:
        merged["expert_status"] = merged["expert_status_panel"].fillna(merged.get("expert_status", "available"))
    if "realized_next_net_return_panel" in merged:
        merged["realized_next_net_return"] = pd.to_numeric(
            merged["realized_next_net_return_panel"], errors="coerce"
        ).where(
            pd.to_numeric(merged["realized_next_net_return_panel"], errors="coerce").notna(),
            pd.to_numeric(merged.get("realized_next_net_return"), errors="coerce"),
        )
    merged["market"] = market
    if "expert_status" not in merged:
        merged["expert_status"] = "available"
    merged["expert_status"] = merged["expert_status"].fillna("available")
    merged["realized_next_net_return"] = pd.to_numeric(merged.get("realized_next_net_return"), errors="coerce")
    merged["test_membership"] = True
    return merged


def _volatility_learning_rate(
    history: list[float],
    *,
    base: float,
    floor: float,
    lookback: int,
    minimum: float,
    maximum: float,
) -> float:
    if len(history) < 2:
        volatility = float(floor)
    else:
        volatility = float(np.std(np.asarray(history[-lookback:], dtype=float), ddof=0))
        volatility = max(float(floor), volatility if math.isfinite(volatility) else float(floor))
    return float(np.clip(float(base) / volatility, float(minimum), float(maximum)))


def _initial_group_weights(group: pd.DataFrame, *, cap: float) -> dict[str, float]:
    ids = group["expert_id"].astype(str).tolist()
    if CASH_EXPERT_ID not in ids:
        raise DynamicEnsembleError("Cash expert is missing from the Phase-E initial decision group.")
    raw = {identifier: float(group.loc[group["expert_id"].eq(identifier), "expert_weight"].iloc[0]) for identifier in ids}
    available = set(group.loc[group["expert_status"].astype(str).eq("available"), "expert_id"].astype(str))
    unavailable = set(ids).difference(available)
    if CASH_EXPERT_ID not in available:
        raise DynamicEnsembleError("Cash expert is unavailable in the Phase-E initial decision group.")
    for identifier in unavailable:
        raw[identifier] = 0.0
    raw[CASH_EXPERT_ID] += sum(float(group.loc[group["expert_id"].eq(identifier), "expert_weight"].iloc[0]) for identifier in unavailable)
    return constrain_expert_weights(_normalize_weights(raw, ids), max_risk_expert_weight=cap)[0]


def _update_group(
    previous: dict[str, float],
    group: pd.DataFrame,
    *,
    algorithm: str,
    learning_rate: float,
    forgetting_factor: float,
    reward_clip: float,
    cap: float,
    max_change: float,
) -> tuple[dict[str, float], bool, set[str]]:
    ids = group["expert_id"].astype(str).tolist()
    returns = {
        str(row.expert_id): _finite_float(getattr(row, "realized_next_net_return", None))
        for row in group.itertuples(index=False)
    }
    statuses = {str(row.expert_id): str(getattr(row, "expert_status", "available")) for row in group.itertuples(index=False)}
    unavailable = {identifier for identifier in ids if statuses.get(identifier) != "available" or returns.get(identifier) is None}
    if algorithm == "hedge":
        desired = hedge_update(previous, returns, learning_rate=learning_rate, forgetting_factor=forgetting_factor, reward_clip=reward_clip)
    elif algorithm == "eg":
        desired = exponentiated_gradient_update(previous, returns, learning_rate=learning_rate, forgetting_factor=forgetting_factor, reward_clip=reward_clip)
    else:
        raise DynamicEnsembleError(f"Unsupported online algorithm: {algorithm}")
    risk_exit = any(float(previous.get(identifier, 0.0)) > 1e-12 for identifier in unavailable if identifier != CASH_EXPERT_ID)
    weights, constrained = apply_online_constraints(
        desired,
        previous,
        ids=ids,
        max_weight_change=max_change,
        max_risk_expert_weight=cap,
        unavailable_ids=unavailable,
    ) if not risk_exit else (
        apply_online_constraints(desired, None, ids=ids, max_weight_change=max_change, max_risk_expert_weight=cap, unavailable_ids=unavailable)[0],
        True,
    )
    return weights, bool(constrained), unavailable


def _decision_records(
    group: pd.DataFrame,
    *,
    split_id: str,
    variant: str,
    algorithm: str,
    learning_rate_mode: str,
    forgetting_factor: float,
    weights: dict[str, float],
    initial_weights: dict[str, float],
    previous_weights: dict[str, float] | None,
    learning_rate: float,
    reason: str | None,
) -> list[dict[str, Any]]:
    selected = group.copy()
    selected["expert_id"] = selected["expert_id"].astype(str)
    portfolio_return = 0.0
    valid = True
    for row in selected.itertuples(index=False):
        value = _finite_float(getattr(row, "realized_next_net_return", None))
        if float(weights.get(str(row.expert_id), 0.0)) > 0 and value is None:
            valid = False
        if value is not None:
            portfolio_return += float(weights.get(str(row.expert_id), 0.0)) * value
    if not valid:
        portfolio_return = np.nan
    turnover = 0.0 if previous_weights is None else 0.5 * sum(
        abs(float(weights.get(identifier, 0.0)) - float(previous_weights.get(identifier, 0.0)))
        for identifier in weights
    )
    for row in selected.itertuples(index=False):
        identifier = str(row.expert_id)
        current = float(weights.get(identifier, 0.0))
        prior = float((previous_weights or {}).get(identifier, 0.0))
        initial = float(initial_weights.get(identifier, 0.0))
        yield_row = {
            "schema_version": PHASE_E_SCHEMA_VERSION,
            "market": str(row.market),
            "split_id": str(split_id),
            "variant": variant,
            "algorithm": algorithm,
            "learning_rate_mode": learning_rate_mode,
            "forgetting_factor": float(forgetting_factor),
            "date": pd.Timestamp(row.date).date().isoformat(),
            "symbol": str(row.symbol),
            "expert_id": identifier,
            "expert_status": str(getattr(row, "expert_status", "available")),
            "initial_expert_weight": initial,
            "previous_expert_weight": prior,
            "expert_weight": current,
            "weight_change": current - prior,
            "expert_target_position": _finite_float(getattr(row, "target_position", None)),
            "realized_next_net_return": _finite_float(getattr(row, "realized_next_net_return", None)),
            "portfolio_return": _finite_float(portfolio_return),
            "portfolio_turnover": float(turnover),
            "learning_rate": float(learning_rate),
            "evaluation_status": "ready" if valid else "unavailable",
            "weight_change_reason": reason,
            "fallback_reason": reason if reason else None,
        }
        yield yield_row


def _simulate_algorithm(
    frame: pd.DataFrame,
    *,
    split_id: str,
    variant: str,
    algorithm: str,
    learning_rate_mode: str,
    forgetting_factor: float,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    online = config["online"]
    cap = float(config.get("gating", {}).get("max_risk_expert_weight", 0.4))
    max_change = float(online.get("max_weight_change", 0.15))
    base_eta = float(online.get("base_learning_rate", online.get("learning_rate")))
    reward_clip = float(online.get("reward_clip", 0.05))
    history_by_symbol: dict[str, list[float]] = {}
    state_by_symbol: dict[str, dict[str, float]] = {}
    previous_decision_by_symbol: dict[str, dict[str, float]] = {}
    initial_by_symbol: dict[str, dict[str, float]] = {}
    records: list[dict[str, Any]] = []
    for date, day in frame.sort_values(["date", "symbol", "expert_id"]).groupby("date", sort=True):
        for symbol, group in day.groupby("symbol", sort=True):
            symbol_key = str(symbol)
            ids = group["expert_id"].astype(str).tolist()
            first_decision = symbol_key not in state_by_symbol
            if first_decision:
                initial = _initial_group_weights(group, cap=cap)
                initial_by_symbol[symbol_key] = initial.copy()
                state_by_symbol[symbol_key] = initial.copy()
                previous = None
            else:
                previous = previous_decision_by_symbol[symbol_key].copy()
            unavailable = set(
                group.loc[group["expert_status"].astype(str).ne("available"), "expert_id"].astype(str)
            )
            if algorithm == "soft_moe":
                # The frozen offline decision is replayed exactly; this is the
                # soft-MoE control and carries no online update.
                desired = _normalize_weights(
                    {identifier: float(group.loc[group["expert_id"].eq(identifier), "expert_weight"].iloc[0]) for identifier in ids}, ids
                )
                # Keep the offline control's own daily weights; only repair
                # missing experts and enforce the frozen simplex/cap contract.
                weights = apply_online_constraints(
                    desired,
                    None,
                    ids=ids,
                    max_weight_change=max_change,
                    max_risk_expert_weight=cap,
                    unavailable_ids=unavailable,
                )[0]
                reason = "offline_soft_moe"
                eta = 0.0
            else:
                history = history_by_symbol.setdefault(symbol_key, [])
                if learning_rate_mode == "volatility_adaptive":
                    eta = _volatility_learning_rate(
                        history,
                        base=base_eta,
                        floor=float(online.get("volatility_floor", 0.005)),
                        lookback=int(online.get("volatility_lookback", 20)),
                        minimum=float(online.get("min_learning_rate", 0.01)),
                        maximum=float(online.get("max_learning_rate", 2.0)),
                    )
                else:
                    eta = base_eta
                # The decision uses only the prior online state.  The current
                # realized return is consumed below, after this row is saved.
                weights = state_by_symbol[symbol_key].copy()
                if unavailable:
                    weights = apply_online_constraints(
                        weights,
                        None,
                        ids=ids,
                        max_weight_change=max_change,
                        max_risk_expert_weight=cap,
                        unavailable_ids=unavailable,
                    )[0]
                reason = "initial_offline_moe" if first_decision else (
                    "missing_expert_safety_exit" if unavailable else "online_state"
                )
            records.extend(
                _decision_records(
                    group, split_id=split_id, variant=variant, algorithm=algorithm,
                    learning_rate_mode=learning_rate_mode, forgetting_factor=float(forgetting_factor),
                    weights=weights, initial_weights=initial_by_symbol[symbol_key],
                    previous_weights=previous, learning_rate=eta, reason=reason,
                )
            )
            previous_decision_by_symbol[symbol_key] = weights.copy()
            if algorithm != "soft_moe":
                updated, constrained, update_unavailable = _update_group(
                    weights,
                    group,
                    algorithm=algorithm,
                    learning_rate=eta,
                    forgetting_factor=float(forgetting_factor),
                    reward_clip=reward_clip,
                    cap=cap,
                    max_change=max_change,
                )
                if update_unavailable:
                    updated = apply_online_constraints(
                        updated,
                        None,
                        ids=ids,
                        max_weight_change=max_change,
                        max_risk_expert_weight=cap,
                        unavailable_ids=update_unavailable,
                    )[0]
                state_by_symbol[symbol_key] = _normalize_weights(updated, ids)
            else:
                state_by_symbol[symbol_key] = _normalize_weights(weights, ids)
            realized = pd.to_numeric(group["realized_next_net_return"], errors="coerce").dropna()
            if not realized.empty:
                history_by_symbol.setdefault(symbol_key, []).append(float(realized.mean()))
    return records


def _summary(weights: pd.DataFrame) -> pd.DataFrame:
    if weights.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    active = weights.loc[weights["evaluation_status"].eq("ready")].copy()
    for keys, frame in active.groupby(["market", "split_id", "variant", "algorithm", "learning_rate_mode", "forgetting_factor"], sort=True):
        market, split_id, variant, algorithm, mode, forgetting = keys
        decisions = frame.groupby(["date", "symbol"], sort=True).agg(
            portfolio_return=("portfolio_return", "first"),
            portfolio_turnover=("portfolio_turnover", "first"),
            max_weight_change=("weight_change", lambda values: float(pd.to_numeric(values, errors="coerce").abs().max())),
        ).reset_index()
        daily = decisions.groupby("date", sort=True)["portfolio_return"].mean().dropna()
        metrics = _performance_metrics(daily)
        rows.append(
            {
                "market": market, "split_id": split_id, "variant": variant,
                "algorithm": algorithm, "learning_rate_mode": mode, "forgetting_factor": float(forgetting),
                "status": "ready" if not daily.empty else "unavailable",
                "decision_count": int(len(decisions)), "daily_return_count": int(len(daily)),
                "mean_portfolio_turnover": _finite_float(decisions["portfolio_turnover"].mean()),
                "max_portfolio_turnover": _finite_float(decisions["portfolio_turnover"].max()),
                "max_daily_weight_change": _finite_float(decisions["max_weight_change"].max()),
                "total_return": metrics.get("total_return"), "annualized_return": metrics.get("annualized_return"),
                "sharpe": metrics.get("sharpe"), "max_drawdown": metrics.get("max_drawdown"),
                "worst_daily_return": _finite_float(daily.min()) if not daily.empty else None,
            }
        )
    return pd.DataFrame(rows)


def _drift_response(weights: pd.DataFrame) -> pd.DataFrame:
    """Measure response to a fixed midpoint structural-break replay.

    The midpoint is chosen before looking at returns.  Post-break winners and
    recovery are evaluation-only fields, so they never affect the update path.
    """

    rows: list[dict[str, Any]] = []
    for keys, frame in weights.groupby(["market", "split_id", "variant", "algorithm", "learning_rate_mode", "forgetting_factor"], sort=True):
        market, split_id, variant, algorithm, mode, forgetting = keys
        dates = sorted(pd.to_datetime(frame["date"]).unique())
        if len(dates) < 2:
            continue
        midpoint = len(dates) // 2
        break_date = pd.Timestamp(dates[midpoint]).date().isoformat()
        returns = frame.pivot_table(index="date", columns="expert_id", values="realized_next_net_return", aggfunc="first")
        pre = returns.loc[returns.index < break_date].mean(numeric_only=True)
        post = returns.loc[returns.index >= break_date].mean(numeric_only=True)
        pre_expert = str(pre.drop(labels=[CASH_EXPERT_ID], errors="ignore").idxmax()) if not pre.drop(labels=[CASH_EXPERT_ID], errors="ignore").empty else CASH_EXPERT_ID
        post_without_cash = post.drop(labels=[CASH_EXPERT_ID], errors="ignore")
        post_expert = str(post_without_cash.idxmax()) if not post_without_cash.empty else CASH_EXPERT_ID
        path = frame.loc[frame["expert_id"].eq(post_expert)].groupby("date", sort=True)["expert_weight"].first()
        threshold = 1.0 / max(2, int(frame["expert_id"].nunique()))
        recovery = None
        if post_expert != pre_expert:
            for date, value in path.items():
                if str(date) >= break_date and float(value) >= threshold:
                    recovery = str(date)
                    break
        delay = None if recovery is None else max(0, (pd.Timestamp(recovery) - pd.Timestamp(break_date)).days)
        rows.append(
            {
                "market": market, "split_id": split_id, "variant": variant, "algorithm": algorithm,
                "learning_rate_mode": mode, "forgetting_factor": float(forgetting),
                "break_date": break_date, "pre_break_best_expert": pre_expert,
                "post_break_best_expert": post_expert, "winner_switched": bool(post_expert != pre_expert),
                "recovery_date": recovery, "recovery_delay_days": delay,
                "pre_break_mean_return": _finite_float(pre.get(pre_expert)),
                "post_break_mean_return": _finite_float(post.get(post_expert)),
                "status": "ready",
            }
        )
    return pd.DataFrame(rows)


def _report(summary: pd.DataFrame, drift: pd.DataFrame, *, config: dict[str, Any], source_phase: str) -> str:
    lines = [
        "# Phase-E Online Expert Weighting",
        "",
        f"- Market: `{config['market']}`; primary horizon: `{config['primary_horizon_days']}` trading days",
        f"- Initial source: ready Phase-{source_phase} frozen soft-MoE weights",
        f"- Return semantics: `{config['return_field']}` / `{config['cost_treatment']}`",
        f"- Online algorithms: `{', '.join(config['online'].get('algorithms', ['hedge', 'eg']))}`",
        "",
        "## Comparison",
        "",
        "| Split | Variant | Algorithm | Mode | Forgetting | Total return | Sharpe | Max drawdown | Mean turnover |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        def fmt(value: Any) -> str:
            return "—" if value is None or (isinstance(value, float) and not math.isfinite(value)) else f"{float(value):.4f}"
        lines.append(
            f"| {row.split_id} | {row.variant} | {row.algorithm} | {row.learning_rate_mode} | {row.forgetting_factor:.3f} | "
            f"{fmt(row.total_return)} | {fmt(row.sharpe)} | {fmt(row.max_drawdown)} | {fmt(row.mean_portfolio_turnover)} |"
        )
    lines.extend([
        "", "## Market-drift response", "",
        f"The drift CSV contains `{len(drift)}` fixed-midpoint replay measurements. Post-break winners are evaluation-only; they never feed the online update.",
        "", "## Safety and reproducibility", "",
        "- Hedge and EG receive complete feedback from every available expert after each decision date.",
        "- The first decision in every purged test window is initialized from the frozen offline MoE; later decisions use only previously observed net returns.",
        "- Cash is mandatory, unavailable experts are moved to Cash, and risk-expert caps plus daily movement limits are enforced.",
        "- `strategy_return` is already net of source execution costs. Phase E never charges it again.",
        "- This remains research-only and does not alter Streamlit defaults.",
        "",
    ])
    return "\n".join(lines)


def materialize_online_ensemble(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_online_ensemble_config(config_file)
    panel_dir, panel, splits, panel_manifest, baselines = _load_phase_b_input(config, repo_root=root)
    source_dir, source_manifest, source_weights, source_summary, source_phase = _load_initial_source(
        config, repo_root=root, panel_dir=panel_dir
    )
    source_variant = _source_variant(config, source_weights)
    source_frame = _prepare_source_frame(panel, source_weights, source_variant=source_variant, market=str(config["market"]))
    # The source artifacts are test-only; retain only rows with an explicit
    # split and use the Phase-B panel's point-in-time next net return.
    source_frame["split_id"] = source_frame["split_id"].astype(str)
    split_ids = sorted(set(source_frame["split_id"]))
    expected_split_ids = set(str(value) for value in splits["split_id"])
    if not expected_split_ids.intersection(split_ids):
        raise DynamicEnsembleError("Phase E initial source has no overlap with the Phase-B test splits.")

    records: list[dict[str, Any]] = []
    online = config["online"]
    for split_id, split_frame in source_frame.groupby("split_id", sort=True):
        split_frame = split_frame.sort_values(["date", "symbol", "expert_id"]).copy()
        records.extend(
            _simulate_algorithm(
                split_frame, split_id=str(split_id), variant="soft_moe", algorithm="soft_moe",
                learning_rate_mode="offline", forgetting_factor=1.0, config=config,
            )
        )
        for algorithm, mode, forgetting in itertools.product(
            online.get("algorithms", ["hedge", "eg"]),
            online.get("learning_rate_modes", ["fixed", "volatility_adaptive"]),
            online.get("forgetting_factors", [1.0, 0.98]),
        ):
            records.extend(
                _simulate_algorithm(
                    split_frame, split_id=str(split_id), variant=f"{algorithm}_{mode}_ff{float(forgetting):.3f}",
                    algorithm=str(algorithm), learning_rate_mode=str(mode), forgetting_factor=float(forgetting), config=config,
                )
            )
    weights = pd.DataFrame(records)
    if weights.empty:
        raise DynamicEnsembleError("Phase E did not produce online decision rows.")
    summary = _summary(weights)
    drift = _drift_response(weights)
    if summary.empty:
        raise DynamicEnsembleError("Phase E did not produce a ready comparison summary.")
    target = Path(output_dir) if output_dir is not None else root / "model-test" / "outputs" / str(config["output_subdir"])
    target.mkdir(parents=True, exist_ok=True)
    weights_path = target / "moe_online_weights.parquet"
    summary_path = target / "moe_online_summary.csv"
    drift_path = target / "moe_online_drift_response.csv"
    comparison_path = target / "moe_online_comparison.csv"
    report_path = target / "moe_online_report.md"
    manifest_path = target / "moe_online_manifest.json"
    weights.to_parquet(weights_path, index=False)
    summary.to_csv(summary_path, index=False)
    drift.to_csv(drift_path, index=False)
    # Keep a compact comparison table with one row per algorithm family and
    # split, while retaining all parameter cells in the summary artifact.
    comparison = summary.copy()
    comparison.to_csv(comparison_path, index=False)
    report_path.write_text(_report(summary, drift, config=config, source_phase=source_phase), encoding="utf-8")
    artifact_paths = {
        "online_weights": weights_path,
        "summary": summary_path,
        "drift_response": drift_path,
        "comparison": comparison_path,
        "report": report_path,
    }
    baseline_definition = _baseline_definition(panel, panel_manifest, baselines)
    baseline_definition["equal_weight_expert_ids"] = sorted(baseline_definition["equal_weight_expert_ids"])
    manifest = {
        "schema_version": PHASE_E_SCHEMA_VERSION,
        "phase": "E",
        "status": "ready",
        "name": config.get("name"),
        "market": config["market"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": config_file.relative_to(root).as_posix(),
        "config_sha256": _sha256_file(config_file),
        "generator_code_version": source_manifest.get("generator_code_version"),
        "phase_a_manifest_sha256": _sha256_file(panel_dir / "data_manifest.json"),
        "phase_b_manifest_sha256": _sha256_file(panel_dir / "expert_panel_manifest.json"),
        "phase_b_panel_dir": panel_dir.relative_to(root).as_posix(),
        "initial_source_phase": source_phase,
        "initial_source_dir": source_dir.relative_to(root).as_posix(),
        "initial_source_manifest_sha256": _sha256_file(source_dir / ("moe_v2_manifest.json" if source_phase == "D" else "moe_manifest.json")),
        "initial_variant": source_variant,
        "random_seed": config["random_seed"],
        "primary_horizon_days": config["primary_horizon_days"],
        "return_field": config["return_field"],
        "cost_treatment": config["cost_treatment"],
        "online": config["online"],
        "gating": config.get("gating", {}),
        "expert_pool": panel_manifest.get("expert_pool"),
        "baseline_definition": baseline_definition,
        "artifacts": {
            name: {"path": path.name, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
            for name, path in artifact_paths.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**artifact_paths, "manifest": manifest_path}


# Naming aliases used by callers that follow the Phase C/D module name.
materialize_dynamic_ensemble_online = materialize_online_ensemble


__all__ = [
    "ALGORITHMS",
    "LEARNING_RATE_MODES",
    "ONLINE_ALGORITHMS",
    "PHASE_E_SCHEMA_VERSION",
    "apply_online_constraints",
    "exponentiated_gradient_update",
    "hedge_update",
    "load_dynamic_ensemble_online_config",
    "load_online_ensemble_config",
    "materialize_dynamic_ensemble_online",
    "materialize_online_ensemble",
    "validate_dynamic_ensemble_online_config",
    "validate_online_ensemble_config",
]
