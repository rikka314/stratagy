"""Phase-F selected-action contextual-bandit comparison research.

The offline replay can observe every expert return, but a deployed policy may
only receive the reward of the allocation it actually chose.  This module uses
the already source-locked Phase-E decision variants as actions and deliberately
updates LinUCB / contextual Thompson Sampling from the selected action alone.
It is an ablation: no Streamlit import, no production strategy selection and
no claim that counterfactual rewards were observed online.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import numpy as np
import pandas as pd

from model_test.dynamic_ensemble import (
    CASH_EXPERT_ID,
    DynamicEnsembleError,
    _git_code_version,
    _load_phase_b_input,
    _performance_metrics,
    _relative_path,
    _sha256_file,
)
from model_test.moe_baseline import MoEBaselineError, _canonical_market


PHASE_F_SCHEMA_VERSION = "1.0"
PRIMARY_HORIZON_DAYS = 20
BANDIT_ALGORITHMS = ("linucb", "contextual_thompson")
FEEDBACK_MODE = "selected_action_only"
_FORBIDDEN_CONTEXT_COLUMNS = {
    "future_utility",
    "strategy_return",
    "realized_next_net_return",
    "label_end_date",
    "split_memberships_json",
    "unavailable_reason",
}


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


def _path_value(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if value in (None, ""):
        raise DynamicEnsembleError(f"Phase F requires {key}.")
    return str(value)


def load_dynamic_ensemble_bandit_config(path: str | Path) -> dict[str, Any]:
    config = _json_object(Path(path))
    validate_dynamic_ensemble_bandit_config(config)
    return config


def validate_dynamic_ensemble_bandit_config(config: dict[str, Any]) -> None:
    """Validate the fail-closed Phase-F partial-feedback research contract."""

    if str(config.get("schema_version")) != PHASE_F_SCHEMA_VERSION:
        raise DynamicEnsembleError(f"schema_version must be {PHASE_F_SCHEMA_VERSION!r}.")
    if str(config.get("phase") or "").upper() != "F":
        raise DynamicEnsembleError("phase must be 'F'.")
    try:
        _canonical_market(config.get("market"))
    except MoEBaselineError as exc:
        raise DynamicEnsembleError(str(exc)) from exc
    _relative_path(_path_value(config, "panel_output_dir"), field_name="panel_output_dir")
    _relative_path(_path_value(config, "phase_e_output_dir"), field_name="phase_e_output_dir")
    _relative_path(_path_value(config, "output_subdir"), field_name="output_subdir")
    if int(config.get("random_seed", -1)) != 42:
        raise DynamicEnsembleError("Phase F freezes random_seed at 42.")
    if config.get("training_scope") != "market_specific":
        raise DynamicEnsembleError("Phase F must train/evaluate one market at a time.")
    if config.get("cross_market_policy") != "ablation_only":
        raise DynamicEnsembleError("cross_market_policy must remain 'ablation_only'.")
    if int(config.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase F primary_horizon_days must remain 20.")
    if config.get("return_field") != "strategy_return":
        raise DynamicEnsembleError("Phase F must consume the source net strategy_return field.")
    if config.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase F must not recharge source transaction costs.")
    if config.get("feedback_mode") != FEEDBACK_MODE:
        raise DynamicEnsembleError("Phase F only permits feedback_mode='selected_action_only'.")
    if config.get("research_only") is not True:
        raise DynamicEnsembleError("Phase F must remain explicitly research_only.")

    context = config.get("context")
    if not isinstance(context, dict):
        raise DynamicEnsembleError("context must be an object.")
    features = context.get("feature_columns")
    if not isinstance(features, list) or not features or any(not str(item).strip() for item in features):
        raise DynamicEnsembleError("context.feature_columns must be a non-empty list.")
    lowered = [str(item).strip().lower() for item in features]
    if len(set(lowered)) != len(lowered):
        raise DynamicEnsembleError("context.feature_columns cannot contain duplicates.")
    for feature in lowered:
        if feature in _FORBIDDEN_CONTEXT_COLUMNS or feature.startswith("future_") or feature.endswith("_label"):
            raise DynamicEnsembleError(f"Phase F context cannot use future or reward column: {feature}.")

    bandit = config.get("bandit")
    if not isinstance(bandit, dict):
        raise DynamicEnsembleError("bandit must be an object.")
    algorithms = bandit.get("algorithms")
    if not isinstance(algorithms, list) or not algorithms or any(str(item) not in BANDIT_ALGORITHMS for item in algorithms):
        raise DynamicEnsembleError(f"bandit.algorithms must contain only {list(BANDIT_ALGORITHMS)}.")
    _positive_finite(bandit.get("ridge_lambda", 1.0), field_name="bandit.ridge_lambda")
    _positive_finite(bandit.get("observation_variance", 0.0004), field_name="bandit.observation_variance")
    _positive_finite(bandit.get("reward_clip", 0.05), field_name="bandit.reward_clip")
    _positive_finite(
        bandit.get("incremental_action_switch_cost_bps", 0.0),
        field_name="bandit.incremental_action_switch_cost_bps",
        allow_zero=True,
    )
    for key in ("linucb_alphas", "thompson_scales"):
        values = bandit.get(key, [0.5])
        if not isinstance(values, list) or not values:
            raise DynamicEnsembleError(f"bandit.{key} must be a non-empty list.")
        for value in values:
            _positive_finite(value, field_name=f"bandit.{key}", allow_zero=True)

    variants = config.get("source_action_variants")
    if variants is not None and (
        not isinstance(variants, list)
        or not variants
        or any(not str(item).strip() or str(item) == CASH_EXPERT_ID for item in variants)
    ):
        raise DynamicEnsembleError("source_action_variants must be non-empty Phase-E variant names, excluding cash.")


# Short aliases parallel the Phase-C/D/E naming style.
load_contextual_bandit_config = load_dynamic_ensemble_bandit_config
validate_contextual_bandit_config = validate_dynamic_ensemble_bandit_config


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


def _load_phase_e_input(
    config: dict[str, Any], *, repo_root: Path, panel_dir: Path
) -> tuple[Path, dict[str, Any], pd.DataFrame, pd.DataFrame]:
    target = (repo_root / _relative_path(config["phase_e_output_dir"], field_name="phase_e_output_dir")).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise DynamicEnsembleError("phase_e_output_dir must remain inside the repository.") from exc
    manifest_path = target / "moe_online_manifest.json"
    if not manifest_path.is_file():
        raise DynamicEnsembleError("Phase F requires a ready Phase-E manifest.")
    manifest = _json_object(manifest_path)
    if manifest.get("phase") != "E" or manifest.get("status") != "ready":
        raise DynamicEnsembleError("Phase F requires a ready Phase-E source.")
    if _canonical_market(manifest.get("market")) != _canonical_market(config["market"]):
        raise DynamicEnsembleError("Phase E source and config markets must match.")
    if int(manifest.get("primary_horizon_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise DynamicEnsembleError("Phase E source horizon does not match the frozen 20-day horizon.")
    if manifest.get("return_field") != "strategy_return" or manifest.get("cost_treatment") != "source_net_no_recharge":
        raise DynamicEnsembleError("Phase E source return/cost contract is incompatible.")
    expected_panel = panel_dir.relative_to(repo_root).as_posix()
    if str(manifest.get("phase_b_panel_dir")) != expected_panel:
        raise DynamicEnsembleError("Phase E source was built from a different Phase-B panel directory.")
    if str(manifest.get("phase_a_manifest_sha256") or "") != _sha256_file(panel_dir / "data_manifest.json"):
        raise DynamicEnsembleError("Phase E source Phase-A manifest hash no longer matches the panel.")
    if str(manifest.get("phase_b_manifest_sha256") or "") != _sha256_file(panel_dir / "expert_panel_manifest.json"):
        raise DynamicEnsembleError("Phase E source Phase-B manifest hash no longer matches the panel.")
    weights_path = _verify_artifact(target, manifest, "online_weights", phase="Phase-E")
    summary_path = _verify_artifact(target, manifest, "summary", phase="Phase-E")
    try:
        weights = pd.read_parquet(weights_path)
        summary = pd.read_csv(summary_path)
    except (OSError, ValueError, ImportError) as exc:
        raise DynamicEnsembleError("Phase F could not read verified Phase-E artifacts.") from exc
    required = {
        "split_id", "variant", "algorithm", "date", "symbol", "expert_id", "expert_weight",
        "portfolio_return", "portfolio_turnover", "evaluation_status",
    }
    if missing := required - set(weights.columns):
        raise DynamicEnsembleError(f"Phase-E weights are missing required columns: {sorted(missing)}")
    if weights.empty or summary.empty:
        raise DynamicEnsembleError("Phase F requires non-empty Phase-E weights and summary artifacts.")
    return target, manifest, weights, summary


def _validate_source_allocation(group: pd.DataFrame, *, cap: float) -> None:
    weights = pd.to_numeric(group["expert_weight"], errors="coerce")
    if weights.isna().any() or (weights < -1e-10).any():
        raise DynamicEnsembleError("Phase E source has invalid expert weights for a contextual-bandit action.")
    if not math.isclose(float(weights.sum()), 1.0, rel_tol=0.0, abs_tol=1e-8):
        raise DynamicEnsembleError("Phase E source allocation must remain on the simplex.")
    risk = group.loc[group["expert_id"].astype(str).ne(CASH_EXPERT_ID), "expert_weight"]
    if (pd.to_numeric(risk, errors="coerce") > float(cap) + 1e-8).any():
        raise DynamicEnsembleError("Phase E source allocation exceeds the configured risk-expert cap.")


def _context_map(panel: pd.DataFrame, feature_columns: list[str]) -> dict[tuple[str, str], np.ndarray]:
    missing = set(feature_columns) - set(panel.columns)
    if missing:
        raise DynamicEnsembleError(f"Phase-B panel is missing requested Phase-F context columns: {sorted(missing)}")
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date.astype(str)
    frame["symbol"] = frame["symbol"].astype(str)
    if "expert_status" in frame:
        frame = frame.loc[frame["expert_status"].astype(str).eq("available")].copy()
    contexts: dict[tuple[str, str], np.ndarray] = {}
    for (date, symbol), group in frame.groupby(["date", "symbol"], sort=True):
        values: list[float] = [1.0]  # Intercept; no global normalization can leak future rows.
        for column in feature_columns:
            numeric = pd.to_numeric(group[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            values.append(float(numeric.mean()) if not numeric.empty else 0.0)
        contexts[(str(date), str(symbol))] = np.asarray(values, dtype=float)
    return contexts


def _build_action_frame(
    weights: pd.DataFrame,
    *,
    panel_contexts: dict[tuple[str, str], np.ndarray],
    requested_variants: set[str] | None,
    cap: float,
) -> tuple[pd.DataFrame, list[str]]:
    frame = weights.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date.astype(str)
    frame["symbol"] = frame["symbol"].astype(str)
    frame["variant"] = frame["variant"].astype(str)
    frame["expert_id"] = frame["expert_id"].astype(str)
    if requested_variants is not None:
        frame = frame.loc[frame["variant"].isin(requested_variants)].copy()
    if frame.empty:
        raise DynamicEnsembleError("No requested Phase-E source action variants are present.")

    records: list[dict[str, Any]] = []
    for (split_id, date, symbol, variant), group in frame.groupby(["split_id", "date", "symbol", "variant"], sort=True):
        if not group["evaluation_status"].astype(str).eq("ready").all():
            continue
        returns = pd.to_numeric(group["portfolio_return"], errors="coerce").dropna()
        if returns.empty:
            continue
        if not np.allclose(returns.to_numpy(), float(returns.iloc[0]), rtol=0.0, atol=1e-12):
            raise DynamicEnsembleError("Phase-E action rows disagree on a portfolio return.")
        turnover = pd.to_numeric(group["portfolio_turnover"], errors="coerce").dropna()
        if turnover.empty or not np.allclose(turnover.to_numpy(), float(turnover.iloc[0]), rtol=0.0, atol=1e-12):
            raise DynamicEnsembleError("Phase-E action rows disagree on portfolio turnover.")
        _validate_source_allocation(group, cap=cap)
        context = panel_contexts.get((str(date), str(symbol)))
        if context is None:
            raise DynamicEnsembleError(f"Phase-E action has no point-in-time Phase-B context: {date}/{symbol}.")
        records.append(
            {
                "split_id": str(split_id), "date": str(date), "symbol": str(symbol), "action_id": str(variant),
                "source_portfolio_return": float(returns.iloc[0]),
                "source_portfolio_turnover": float(turnover.iloc[0]),
                "context": context,
            }
        )
    actions = pd.DataFrame(records)
    if actions.empty:
        raise DynamicEnsembleError("Phase F found no Phase-E decisions with an observable source reward.")
    action_ids = sorted(actions["action_id"].unique().tolist())
    return actions, action_ids


class _LinearContextualBandit:
    """Independent linear posteriors per allocation action, updated only on action reward."""

    def __init__(
        self,
        action_ids: Iterable[str],
        *,
        dimension: int,
        ridge_lambda: float,
        observation_variance: float,
        rng: np.random.Generator,
    ) -> None:
        self.action_ids = tuple(sorted(str(item) for item in action_ids))
        self.dimension = int(dimension)
        self.observation_variance = float(observation_variance)
        self.rng = rng
        self.a = {action: np.eye(self.dimension, dtype=float) * float(ridge_lambda) for action in self.action_ids}
        self.b = {action: np.zeros(self.dimension, dtype=float) for action in self.action_ids}
        self.observation_count = {action: 0 for action in self.action_ids}

    def _mean_and_variance(self, action: str, context: np.ndarray) -> tuple[float, float, np.ndarray]:
        inverse = np.linalg.pinv(self.a[action])
        theta = inverse @ self.b[action]
        mean = float(theta @ context)
        variance = max(0.0, float(context @ inverse @ context))
        return mean, variance, inverse

    def select(
        self,
        available_actions: list[str],
        context: np.ndarray,
        *,
        algorithm: str,
        exploration_parameter: float,
    ) -> tuple[str, float, float, str]:
        if not available_actions:
            raise DynamicEnsembleError("Contextual bandit decision has no available action, including cash.")
        if algorithm == "linucb":
            scored: list[tuple[str, float, float]] = []
            for action in available_actions:
                mean, variance, _inverse = self._mean_and_variance(action, context)
                scored.append((action, mean + float(exploration_parameter) * math.sqrt(variance), mean))
            maximum = max(item[1] for item in scored)
            ties = [item for item in scored if math.isclose(item[1], maximum, rel_tol=0.0, abs_tol=1e-12)]
            chosen = ties[int(self.rng.integers(0, len(ties)))]
            return chosen[0], float(chosen[1]), float(chosen[2]), "upper_confidence_bound"
        if algorithm == "contextual_thompson":
            scored = []
            for action in available_actions:
                mean, _variance, inverse = self._mean_and_variance(action, context)
                covariance = inverse * self.observation_variance * float(exploration_parameter) ** 2
                sampled_theta = self.rng.multivariate_normal(inverse @ self.b[action], covariance, check_valid="ignore")
                scored.append((action, float(sampled_theta @ context), mean))
            maximum = max(item[1] for item in scored)
            ties = [item for item in scored if math.isclose(item[1], maximum, rel_tol=0.0, abs_tol=1e-12)]
            chosen = ties[int(self.rng.integers(0, len(ties)))]
            return chosen[0], float(chosen[1]), float(chosen[2]), "posterior_sample"
        raise DynamicEnsembleError(f"Unsupported contextual-bandit algorithm: {algorithm}")

    def update(self, action: str, context: np.ndarray, reward: float, *, reward_clip: float) -> None:
        if action not in self.a:
            raise DynamicEnsembleError(f"Unknown contextual-bandit action: {action}")
        observed = float(np.clip(float(reward), -float(reward_clip), float(reward_clip)))
        precision = 1.0 / self.observation_variance
        self.a[action] += precision * np.outer(context, context)
        self.b[action] += precision * context * observed
        self.observation_count[action] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "observation_count": dict(self.observation_count),
            "posterior": {
                action: {"a": self.a[action].tolist(), "b": self.b[action].tolist()}
                for action in self.action_ids
            },
        }


def _policy_cells(config: dict[str, Any]) -> list[tuple[str, float, str]]:
    bandit = config["bandit"]
    cells: list[tuple[str, float, str]] = []
    if "linucb" in bandit.get("algorithms", []):
        for alpha in bandit.get("linucb_alphas", [0.5]):
            value = float(alpha)
            cells.append(("linucb", value, f"linucb_alpha_{value:.3f}"))
    if "contextual_thompson" in bandit.get("algorithms", []):
        for scale in bandit.get("thompson_scales", [0.5]):
            value = float(scale)
            cells.append(("contextual_thompson", value, f"contextual_thompson_scale_{value:.3f}"))
    return cells


def _cash_action(date: str, symbol: str, split_id: str, context: np.ndarray) -> dict[str, Any]:
    return {
        "split_id": split_id, "date": date, "symbol": symbol, "action_id": CASH_EXPERT_ID,
        "source_portfolio_return": 0.0, "source_portfolio_turnover": 0.0, "context": context,
    }


def _simulate_policy(
    actions: pd.DataFrame,
    *,
    split_id: str,
    action_ids: list[str],
    algorithm: str,
    exploration_parameter: float,
    policy_variant: str,
    config: dict[str, Any],
    seed_offset: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bandit_config = config["bandit"]
    dimension = len(actions.iloc[0]["context"])
    policy = _LinearContextualBandit(
        [*action_ids, CASH_EXPERT_ID],
        dimension=dimension,
        ridge_lambda=float(bandit_config.get("ridge_lambda", 1.0)),
        observation_variance=float(bandit_config.get("observation_variance", 0.0004)),
        rng=np.random.default_rng(int(config["random_seed"]) + int(seed_offset)),
    )
    switch_cost_rate = float(bandit_config.get("incremental_action_switch_cost_bps", 0.0)) / 10_000.0
    previous_action_by_symbol: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    grouped = actions.loc[actions["split_id"].astype(str).eq(str(split_id))].copy()
    for date, day in grouped.sort_values(["date", "symbol", "action_id"]).groupby("date", sort=True):
        pending_updates: list[tuple[str, np.ndarray, float]] = []
        # All choices for this date share the preceding posterior.  Rewards are
        # applied only after the batch, so one symbol cannot leak same-date
        # next-period information into another symbol's choice.
        for symbol, group in day.groupby("symbol", sort=True):
            context = np.asarray(group.iloc[0]["context"], dtype=float)
            available = sorted(group["action_id"].astype(str).unique().tolist())
            action_rows = {str(row.action_id): row for row in group.itertuples(index=False)}
            if CASH_EXPERT_ID not in action_rows:
                action_rows[CASH_EXPERT_ID] = SimpleNamespace(**_cash_action(str(date), str(symbol), str(split_id), context))
                available.append(CASH_EXPERT_ID)
                available.sort()
            selected, score, posterior_mean, selection_mode = policy.select(
                available, context, algorithm=algorithm, exploration_parameter=float(exploration_parameter)
            )
            selected_row = action_rows[selected]
            source_return = float(selected_row.source_portfolio_return)
            previous = previous_action_by_symbol.get(str(symbol))
            switched = previous is not None and previous != selected
            incremental_cost = switch_cost_rate if switched else 0.0
            realized = source_return - incremental_cost
            pending_updates.append((selected, context, realized))
            previous_action_by_symbol[str(symbol)] = selected
            record = {
                "schema_version": PHASE_F_SCHEMA_VERSION,
                "market": str(config["market"]), "split_id": str(split_id), "date": str(date), "symbol": str(symbol),
                "policy_variant": policy_variant, "algorithm": algorithm,
                "exploration_parameter": float(exploration_parameter), "feedback_mode": FEEDBACK_MODE,
                "selected_action": selected, "selection_mode": selection_mode, "policy_score": float(score),
                "posterior_mean": float(posterior_mean), "available_action_count": int(len(available)),
                "source_portfolio_return": source_return,
                "source_portfolio_turnover": float(selected_row.source_portfolio_turnover),
                "previous_action": previous, "action_switched": bool(switched),
                "incremental_exploration_cost": float(incremental_cost), "net_policy_return": float(realized),
                "observed_feedback_return": float(realized), "evaluation_status": "ready",
            }
            for index, value in enumerate(context[1:]):
                record[f"context_{index}"] = float(value)
            records.append(record)
        for selected, context, reward in pending_updates:
            policy.update(selected, context, reward, reward_clip=float(bandit_config.get("reward_clip", 0.05)))
    return records, policy.snapshot()


def _daily_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in decisions.groupby(["market", "split_id", "policy_variant", "algorithm", "exploration_parameter", "date"], sort=True):
        market, split_id, policy_variant, algorithm, parameter, date = keys
        action_share = group["selected_action"].value_counts(normalize=True)
        entropy = -sum(float(value) * math.log(float(value)) for value in action_share if value > 0)
        rows.append(
            {
                "market": market, "split_id": split_id, "policy_variant": policy_variant, "algorithm": algorithm,
                "exploration_parameter": float(parameter), "date": str(date), "decision_count": int(len(group)),
                "mean_net_policy_return": float(group["net_policy_return"].mean()),
                "mean_source_return": float(group["source_portfolio_return"].mean()),
                "mean_incremental_exploration_cost": float(group["incremental_exploration_cost"].mean()),
                "action_switch_rate": float(group["action_switched"].mean()), "selected_action_entropy": float(entropy),
            }
        )
    daily = pd.DataFrame(rows)
    if daily.empty:
        return daily
    daily = daily.sort_values(["market", "split_id", "policy_variant", "date"], kind="mergesort").copy()
    grouped = daily.groupby(["market", "split_id", "policy_variant"], sort=False)
    daily["cumulative_net_return"] = grouped["mean_net_policy_return"].transform(lambda values: (1.0 + values).cumprod() - 1.0)
    daily["cumulative_incremental_exploration_cost"] = grouped["mean_incremental_exploration_cost"].cumsum()
    return daily


def _summary(decisions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in decisions.groupby(["market", "split_id", "policy_variant", "algorithm", "exploration_parameter"], sort=True):
        market, split_id, policy_variant, algorithm, parameter = keys
        daily = group.groupby("date", sort=True)["net_policy_return"].mean().dropna()
        metrics = _performance_metrics(daily)
        rows.append(
            {
                "market": market, "split_id": split_id, "policy_variant": policy_variant, "algorithm": algorithm,
                "exploration_parameter": float(parameter), "status": "ready" if not daily.empty else "unavailable",
                "decision_count": int(len(group)), "daily_return_count": int(len(daily)),
                "total_return": metrics.get("total_return"), "annualized_return": metrics.get("annualized_return"),
                "sharpe": metrics.get("sharpe"), "max_drawdown": metrics.get("max_drawdown"),
                "worst_daily_return": float(daily.min()) if not daily.empty else None,
                "mean_source_portfolio_turnover": float(group["source_portfolio_turnover"].mean()),
                "action_switch_rate": float(group["action_switched"].mean()),
                "total_incremental_exploration_cost": float(group["incremental_exploration_cost"].sum()),
                "cash_action_share": float(group["selected_action"].eq(CASH_EXPERT_ID).mean()),
            }
        )
    return pd.DataFrame(rows)


def _drift_response(decisions: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    """Measure recovery with counterfactual action returns kept evaluation-only."""

    rows: list[dict[str, Any]] = []
    for keys, decision_group in decisions.groupby(["market", "split_id", "policy_variant", "algorithm", "exploration_parameter"], sort=True):
        market, split_id, policy_variant, algorithm, parameter = keys
        source = actions.loc[actions["split_id"].astype(str).eq(str(split_id))].copy()
        dates = sorted(source["date"].unique().tolist())
        if len(dates) < 2:
            continue
        midpoint = len(dates) // 2
        break_date = str(dates[midpoint])
        source_returns = source.pivot_table(index="date", columns="action_id", values="source_portfolio_return", aggfunc="mean")
        post = source_returns.loc[source_returns.index >= break_date].mean(numeric_only=True)
        non_cash = post.drop(labels=[CASH_EXPERT_ID], errors="ignore")
        post_best = str(non_cash.idxmax()) if not non_cash.empty else CASH_EXPERT_ID
        selected_share = (
            decision_group.loc[decision_group["date"].astype(str) >= break_date]
            .groupby("date", sort=True)["selected_action"].apply(lambda values: float(values.eq(post_best).mean()))
        )
        recovery = next((str(date) for date, share in selected_share.items() if float(share) >= 0.5), None)
        delay = None if recovery is None else max(0, (pd.Timestamp(recovery) - pd.Timestamp(break_date)).days)
        rows.append(
            {
                "market": market, "split_id": split_id, "policy_variant": policy_variant, "algorithm": algorithm,
                "exploration_parameter": float(parameter), "break_date": break_date,
                "post_break_best_action": post_best, "recovery_date": recovery, "recovery_delay_days": delay,
                "post_break_best_mean_return": _finite_float(post.get(post_best)), "status": "ready",
                "evaluation_only": True,
            }
        )
    return pd.DataFrame(rows)


def _comparison(bandit_summary: pd.DataFrame, phase_e_summary: pd.DataFrame) -> pd.DataFrame:
    reference = phase_e_summary.copy()
    reference["comparison_type"] = "phase_e_full_feedback_reference"
    reference["policy_variant"] = reference.get("variant", "phase_e")
    reference["exploration_parameter"] = np.nan
    reference["total_incremental_exploration_cost"] = 0.0
    bandit = bandit_summary.copy()
    bandit["comparison_type"] = "phase_f_selected_action_bandit"
    columns = [
        "comparison_type", "market", "split_id", "policy_variant", "algorithm", "exploration_parameter",
        "status", "decision_count", "total_return", "annualized_return", "sharpe", "max_drawdown",
        "mean_source_portfolio_turnover", "action_switch_rate", "total_incremental_exploration_cost",
    ]
    for frame in (reference, bandit):
        for column in columns:
            if column not in frame:
                frame[column] = np.nan
    return pd.concat([reference[columns], bandit[columns]], ignore_index=True, sort=False)


def _report(summary: pd.DataFrame, drift: pd.DataFrame, *, config: dict[str, Any], action_ids: list[str]) -> str:
    lines = [
        "# Phase-F Contextual Bandit Comparison",
        "",
        f"- Market: `{config['market']}`; primary horizon: `{config['primary_horizon_days']}` trading days",
        "- Source: market-matched, hash-verified ready Phase-E actions",
        f"- Feedback: `{FEEDBACK_MODE}`; each decision updates from its selected action only",
        f"- Candidate Phase-E actions: `{', '.join(action_ids)}` plus mandatory `{CASH_EXPERT_ID}`",
        f"- Return semantics: `{config['return_field']}` / `{config['cost_treatment']}`",
        "",
        "## Partial-feedback comparison",
        "",
        "| Split | Policy | Algorithm | Parameter | Total return | Sharpe | Max drawdown | Switch rate | Extra exploration cost |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        def fmt(value: Any) -> str:
            value = _finite_float(value)
            return "—" if value is None else f"{value:.4f}"
        lines.append(
            f"| {row.split_id} | {row.policy_variant} | {row.algorithm} | {row.exploration_parameter:.3f} | "
            f"{fmt(row.total_return)} | {fmt(row.sharpe)} | {fmt(row.max_drawdown)} | {fmt(row.action_switch_rate)} | "
            f"{fmt(row.total_incremental_exploration_cost)} |"
        )
    lines.extend(
        [
            "", "## Boundaries", "",
            f"The drift artifact contains `{len(drift)}` fixed-midpoint recovery measurements. It reads all action outcomes only after the replay as evaluation-only data and never feeds a bandit update.",
            "- The Phase-B source `strategy_return` is already net of expert execution costs and is never charged again.",
            "- `incremental_action_switch_cost_bps` is an optional separately disclosed deployment-layer action-transition cost; the shipped configs set it to zero until a measured execution model exists.",
            "- Cash is always an available action. A selected Phase-E allocation is hash-verified to retain its original simplex and risk-expert cap before it can enter the action set.",
            "- This is a research ablation. It is not imported by Streamlit and cannot promote a product default.",
            "",
        ]
    )
    return "\n".join(lines)


def materialize_dynamic_ensemble_bandit(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Replay ready Phase-E decisions as selected-action-only LinUCB/CTS experiments."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_dynamic_ensemble_bandit_config(config_file)
    panel_dir, panel, splits, panel_manifest, _baselines = _load_phase_b_input(config, repo_root=root)
    phase_e_dir, phase_e_manifest, phase_e_weights, phase_e_summary = _load_phase_e_input(
        config, repo_root=root, panel_dir=panel_dir
    )
    feature_columns = [str(item) for item in config["context"]["feature_columns"]]
    contexts = _context_map(panel, feature_columns)
    cap = float(phase_e_manifest.get("gating", {}).get("max_risk_expert_weight", 0.4))
    requested = config.get("source_action_variants")
    actions, action_ids = _build_action_frame(
        phase_e_weights,
        panel_contexts=contexts,
        requested_variants=set(str(item) for item in requested) if requested is not None else None,
        cap=cap,
    )
    expected_split_ids = set(splits["split_id"].astype(str))
    found_split_ids = set(actions["split_id"].astype(str))
    if not expected_split_ids.intersection(found_split_ids):
        raise DynamicEnsembleError("Phase F source actions have no overlap with Phase-B test splits.")

    records: list[dict[str, Any]] = []
    final_state: dict[str, Any] = {}
    for split_index, split_id in enumerate(sorted(found_split_ids)):
        for cell_index, (algorithm, parameter, policy_variant) in enumerate(_policy_cells(config)):
            policy_records, state = _simulate_policy(
                actions,
                split_id=split_id,
                action_ids=action_ids,
                algorithm=algorithm,
                exploration_parameter=parameter,
                policy_variant=policy_variant,
                config=config,
                seed_offset=split_index * 1000 + cell_index,
            )
            records.extend(policy_records)
            final_state[f"{split_id}/{policy_variant}"] = state
    decisions = pd.DataFrame(records)
    if decisions.empty:
        raise DynamicEnsembleError("Phase F did not produce selected-action decisions.")
    summary = _summary(decisions)
    convergence = _daily_decisions(decisions)
    drift = _drift_response(decisions, actions)
    comparison = _comparison(summary, phase_e_summary)

    target = Path(output_dir) if output_dir is not None else root / "model-test" / "outputs" / str(config["output_subdir"])
    target.mkdir(parents=True, exist_ok=True)
    decisions_path = target / "moe_bandit_decisions.parquet"
    summary_path = target / "moe_bandit_summary.csv"
    convergence_path = target / "moe_bandit_convergence.csv"
    drift_path = target / "moe_bandit_drift_response.csv"
    comparison_path = target / "moe_bandit_comparison.csv"
    state_path = target / "moe_bandit_final_state.json"
    report_path = target / "moe_bandit_report.md"
    manifest_path = target / "moe_bandit_manifest.json"
    decisions.to_parquet(decisions_path, index=False)
    summary.to_csv(summary_path, index=False)
    convergence.to_csv(convergence_path, index=False)
    drift.to_csv(drift_path, index=False)
    comparison.to_csv(comparison_path, index=False)
    state_path.write_text(json.dumps(final_state, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_report(summary, drift, config=config, action_ids=action_ids), encoding="utf-8")
    artifact_paths = {
        "decisions": decisions_path, "summary": summary_path, "convergence": convergence_path,
        "drift_response": drift_path, "comparison": comparison_path, "final_state": state_path, "report": report_path,
    }
    manifest = {
        "schema_version": PHASE_F_SCHEMA_VERSION,
        "phase": "F", "status": "ready", "name": config.get("name"), "market": config["market"],
        "generated_at": datetime.now(timezone.utc).isoformat(), "generator_code_version": _git_code_version(root),
        "config_path": config_file.relative_to(root).as_posix(), "config_sha256": _sha256_file(config_file),
        "phase_b_panel_dir": panel_dir.relative_to(root).as_posix(),
        "phase_a_manifest_sha256": _sha256_file(panel_dir / "data_manifest.json"),
        "phase_b_manifest_sha256": _sha256_file(panel_dir / "expert_panel_manifest.json"),
        "phase_e_output_dir": phase_e_dir.relative_to(root).as_posix(),
        "phase_e_manifest_sha256": _sha256_file(phase_e_dir / "moe_online_manifest.json"),
        "phase_e_source_lock": {
            "initial_source_phase": phase_e_manifest.get("initial_source_phase"),
            "initial_source_manifest_sha256": phase_e_manifest.get("initial_source_manifest_sha256"),
        },
        "random_seed": config["random_seed"], "primary_horizon_days": config["primary_horizon_days"],
        "return_field": config["return_field"], "cost_treatment": config["cost_treatment"],
        "feedback_mode": FEEDBACK_MODE, "research_only": True, "context_feature_columns": feature_columns,
        "candidate_action_variants": action_ids, "cash_action_id": CASH_EXPERT_ID,
        "source_risk_expert_cap": cap, "bandit": config["bandit"],
        "artifacts": {
            name: {"path": path.name, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
            for name, path in artifact_paths.items()
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**artifact_paths, "manifest": manifest_path}


materialize_contextual_bandit = materialize_dynamic_ensemble_bandit


__all__ = [
    "BANDIT_ALGORITHMS", "FEEDBACK_MODE", "PHASE_F_SCHEMA_VERSION",
    "load_contextual_bandit_config", "load_dynamic_ensemble_bandit_config",
    "materialize_contextual_bandit", "materialize_dynamic_ensemble_bandit",
    "validate_contextual_bandit_config", "validate_dynamic_ensemble_bandit_config",
]
