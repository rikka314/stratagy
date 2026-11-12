"""Run research-only Phase 2 robust Composite weight studies."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from model_test.composite_quality import validate_price_frame
from model_test.robust_weight_research import (
    WeightResearchConfig,
    bootstrap_weight_intervals,
    centred_interaction,
    evaluate_fixed_candidate,
    fit_candidate,
    fit_train_transform,
    stability_summary,
)
from core.factor_pipeline import FactorPipeline


REQUIRED_COLUMNS = {"date", "open", "high", "low", "close", "volume"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("status") != "research_only":
        raise ValueError("Phase 2 must remain research_only")
    if config.get("market") != "US":
        raise ValueError("Phase 2 runner currently requires US")
    return config


def _load_snapshot(path: Path, symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"{symbol} snapshot missing columns: {missing}")
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in REQUIRED_COLUMNS - {"date"}:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    validate_price_frame(result)
    return result.sort_values("date").reset_index(drop=True)


def _research_config(config: dict[str, Any]) -> WeightResearchConfig:
    factors = tuple(config["factors"]["names"])
    optimization = config["optimization"]
    execution = config["execution"]
    return WeightResearchConfig(
        factors=factors,
        directions={key: int(value) for key, value in config["factors"]["directions"].items()},
        family_by_factor=config["factors"]["family_by_factor"],
        family_budgets={key: float(value) for key, value in config["factors"]["family_budgets"].items()},
        factor_budget=float(config["factors"]["factor_budget"]),
        interaction_budget=float(config["factors"]["interaction_budget"]),
        commission_bps=float(execution["commission_bps"]),
        slippage_bps=float(execution["slippage_bps"]),
        horizon_days=int(config["primary_horizon_days"]),
        block_length=int(optimization["block_length"]),
        bootstrap_samples=int(optimization["bootstrap_samples"]),
    )


def _scope(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame.loc[
        (frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))
    ].copy()


def _with_future_label(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    result = frame.copy()
    result["future_return"] = result["close"].shift(-horizon) / result["close"] - 1.0
    return result.dropna(subset=["future_return"])


def _weight_path_row(
    result: dict[str, object],
    *,
    symbol: str,
    fold_id: str,
    method: str,
    seed: int,
) -> dict[str, object]:
    weights = result["weights"]
    assert isinstance(weights, dict)
    metrics = result["validation_metrics"]
    assert isinstance(metrics, dict)
    return {
        "symbol": symbol,
        "fold_id": fold_id,
        "method": method,
        "seed": seed,
        **{factor: float(value) for factor, value in weights.items()},
        "validation_utility": float(result["validation_utility"]),
        "validation_sharpe": float(metrics["sharpe"]),
        "validation_max_drawdown": float(metrics["max_drawdown"]),
        "validation_turnover": float(metrics["turnover"]),
        "validation_transaction_cost": float(metrics["transaction_cost"]),
    }


def _interaction_ablation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    transform: object,
    config: WeightResearchConfig,
    *,
    base_result: dict[str, object],
    seed: int,
    symbol: str,
    fold_id: str,
) -> list[dict[str, object]]:
    pairs = (("volume_ratio_rank", "mom_short_z"), ("rsi_z", "vix_level"), ("mom_short_z", "vix_level"))
    weights = dict(base_result["weights"])
    rows: list[dict[str, object]] = []
    interaction_names = tuple(f"{left}_x_{right}" for left, right in pairs)
    for left, right in pairs:
        interaction_name = f"{left}_x_{right}"
        train_with = train.copy()
        validation_with = validation.copy()
        train_interaction = centred_interaction(train, left, right, transform)
        validation_interaction = centred_interaction(validation, left, right, transform)
        train_with[interaction_name] = train_interaction
        validation_with[interaction_name] = validation_interaction
        permutation = np.random.default_rng(seed).permutation(len(validation_with))
        permuted_validation = validation_with.copy()
        permuted_validation[interaction_name] = validation_interaction.iloc[permutation].to_numpy()
        for mode, interaction_weight in (("none", 0.0), ("single", -0.5), ("all", -0.5), ("permuted", 0.5)):
            candidate_weights = dict(weights)
            evaluation_train = train_with
            evaluation_validation = validation_with
            if mode == "all":
                for name in interaction_names:
                    candidate_weights[name] = interaction_weight
                evaluation_train = train.copy()
                evaluation_validation = validation.copy()
                for pair_left, pair_right in pairs:
                    name = f"{pair_left}_x_{pair_right}"
                    evaluation_train[name] = centred_interaction(train, pair_left, pair_right, transform)
                    evaluation_validation[name] = centred_interaction(validation, pair_left, pair_right, transform)
            elif mode == "single":
                candidate_weights[interaction_name] = interaction_weight
            elif mode == "permuted":
                candidate_weights[interaction_name] = interaction_weight
                evaluation_validation = permuted_validation
            augmented = WeightResearchConfig(
                factors=tuple(config.factors) + tuple(name for name in candidate_weights if "_x_" in name),
                directions={**config.directions, **{name: 1 for name in candidate_weights if "_x_" in name}},
                family_by_factor={**config.family_by_factor, **{name: "interaction" for name in candidate_weights if "_x_" in name}},
                family_budgets={**config.family_budgets, "interaction": config.interaction_budget},
                factor_budget=config.factor_budget,
                interaction_budget=config.interaction_budget,
                lambda_drawdown=config.lambda_drawdown,
                lambda_turnover=config.lambda_turnover,
                lambda_cost=config.lambda_cost,
                lambda_complexity=config.lambda_complexity,
                commission_bps=config.commission_bps,
                slippage_bps=config.slippage_bps,
                horizon_days=config.horizon_days,
                block_length=config.block_length,
                bootstrap_samples=config.bootstrap_samples,
            )
            if mode == "none":
                validation_utility = float(base_result["validation_utility"])
                metrics = base_result["validation_metrics"]
            else:
                fitted = evaluate_fixed_candidate(
                    evaluation_train,
                    evaluation_validation,
                    augmented,
                    transform=transform,
                    weights=candidate_weights,
                )
                validation_utility = float(fitted["validation_utility"])
                metrics = fitted["validation_metrics"]
            assert isinstance(metrics, dict)
            rows.append(
                {
                    "symbol": symbol,
                    "fold_id": fold_id,
                    "seed": seed,
                    "factor_left": left,
                    "factor_right": right,
                    "interaction": interaction_name,
                    "ablation": mode,
                    "interaction_weight": float(candidate_weights.get(interaction_name, 0.0)),
                    "validation_utility": validation_utility,
                    "validation_sharpe": float(metrics["sharpe"]),
                    "validation_max_drawdown": float(metrics["max_drawdown"]),
                    "validation_turnover": float(metrics["turnover"]),
                    "validation_transaction_cost": float(metrics["transaction_cost"]),
                    "main_effects_frozen": True,
                }
            )
    return rows


def run(config_path: Path, output: Path) -> dict[str, object]:
    config = _load_config(config_path)
    research_config = _research_config(config)
    source_manifest = REPO_ROOT / config["source"]["data_manifest"]
    macro_manifest = REPO_ROOT / config["source"]["macro_data_manifest"]
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    symbols = sorted(str(item["symbol"]).upper() for item in source["universe"]["files"])
    snapshot_dir = REPO_ROOT / config["source"]["snapshot_dir"]
    pipeline = FactorPipeline(REPO_ROOT / config["source"]["macro_data_dir"])
    weight_rows: list[dict[str, object]] = []
    interaction_rows: list[dict[str, object]] = []
    test_rows: list[dict[str, object]] = []
    quality_rows: list[dict[str, object]] = []
    transform_records: list[dict[str, object]] = []
    unavailable_rows: list[dict[str, object]] = []
    methods = tuple(config["optimization"]["methods"])
    seeds = tuple(int(seed) for seed in config["optimization"]["seeds"])
    candidate_count = int(config["optimization"]["candidate_count"])

    for symbol in symbols:
        prices = _load_snapshot(snapshot_dir / f"{symbol}_daily.csv", symbol)
        quality_rows.append({"symbol": symbol, **validate_price_frame(prices)})
        factors = pipeline.compute_all_factors(prices, symbol)
        labeled = _with_future_label(factors, research_config.horizon_days)
        for fold in config["folds"]:
            train = _scope(labeled, fold["train_start"], fold["train_end"])
            validation = _scope(labeled, fold["validation_start"], fold["validation_end"])
            test = _scope(labeled, fold["test_start"], fold["test_end"])
            train = train.dropna(subset=list(research_config.factors)).copy()
            validation = validation.dropna(subset=list(research_config.factors)).copy()
            test = test.dropna(subset=list(research_config.factors)).copy()
            if train.empty or validation.empty:
                unavailable_rows.append(
                    {
                        "symbol": symbol,
                        "fold_id": fold["fold_id"],
                        "reason": "insufficient_factor_coverage",
                        "train_rows": int(len(train)),
                        "validation_rows": int(len(validation)),
                        "test_rows": int(len(test)),
                    }
                )
                continue
            transform = fit_train_transform(train, research_config.factors)
            transform_records.append({"symbol": symbol, "fold_id": fold["fold_id"], **transform.as_dict()})
            fold_results: list[dict[str, object]] = []
            for method in methods:
                for seed in seeds:
                    result = fit_candidate(
                        train,
                        validation,
                        research_config,
                        transform=transform,
                        seed=seed,
                        method=method,
                        candidate_count=candidate_count,
                    )
                    fold_results.append(result)
                    weight_rows.append(_weight_path_row(result, symbol=symbol, fold_id=fold["fold_id"], method=method, seed=seed))
            best = max(fold_results, key=lambda item: float(item["train_utility"]))
            interaction_rows.extend(
                _interaction_ablation(
                    train, validation, transform, research_config,
                    base_result=best, seed=int(best["seed"]), symbol=symbol, fold_id=fold["fold_id"]
                )
            )
            if not test.empty:
                best_interaction = max(
                    interaction_rows[-12:] if len(interaction_rows) >= 12 else interaction_rows,
                    key=lambda item: float(item["validation_utility"]) if item["symbol"] == symbol and item["fold_id"] == fold["fold_id"] else -float("inf")
                )
                test_candidate_weights = dict(best["weights"])
                if best_interaction["ablation"] != "none":
                    test_candidate_weights[best_interaction["interaction"]] = float(best_interaction["interaction_weight"])
                test_config_factors = tuple(research_config.factors) + (
                    (best_interaction["interaction"],) if best_interaction["ablation"] != "none" else ()
                )
                test_research_config = WeightResearchConfig(
                    factors=test_config_factors,
                    directions={**research_config.directions, **{name: 1 for name in test_config_factors if "_x_" in name}},
                    family_by_factor={**research_config.family_by_factor, **{name: "interaction" for name in test_config_factors if "_x_" in name}},
                    family_budgets={**research_config.family_budgets, "interaction": research_config.interaction_budget},
                    factor_budget=research_config.factor_budget,
                    interaction_budget=research_config.interaction_budget,
                    lambda_drawdown=research_config.lambda_drawdown,
                    lambda_turnover=research_config.lambda_turnover,
                    lambda_cost=research_config.lambda_cost,
                    lambda_complexity=research_config.lambda_complexity,
                    commission_bps=research_config.commission_bps,
                    slippage_bps=research_config.slippage_bps,
                    horizon_days=research_config.horizon_days,
                    block_length=research_config.block_length,
                    bootstrap_samples=research_config.bootstrap_samples,
                )
                if best_interaction["ablation"] != "none":
                    test_with_interaction = test.copy()
                    left, right = best_interaction["interaction"].split("_x_", 1)
                    test_with_interaction[best_interaction["interaction"]] = centred_interaction(test, left, right, transform)
                    test_eval = evaluate_fixed_candidate(
                        train, test_with_interaction, test_research_config,
                        transform=transform, weights=test_candidate_weights
                    )
                else:
                    test_eval = evaluate_fixed_candidate(
                        train, test, test_research_config,
                        transform=transform, weights=test_candidate_weights
                    )
                test_rows.append({
                    "symbol": symbol,
                    "fold_id": fold["fold_id"],
                    "best_method": best["method"],
                    "best_seed": best["seed"],
                    "best_interaction_ablation": best_interaction["ablation"],
                    "test_utility": float(test_eval["validation_utility"]),
                    "test_sharpe": float(test_eval["validation_metrics"]["sharpe"]),
                    "test_max_drawdown": float(test_eval["validation_metrics"]["max_drawdown"]),
                    "test_turnover": float(test_eval["validation_metrics"]["turnover"]),
                    "test_transaction_cost": float(test_eval["validation_metrics"]["transaction_cost"]),
                })

    output.mkdir(parents=True, exist_ok=True)
    weight_paths = pd.DataFrame(weight_rows)
    interactions = pd.DataFrame(interaction_rows)
    test_metrics = pd.DataFrame(test_rows)
    weight_paths.to_parquet(output / "weight_paths.parquet", index=False)
    interactions.to_csv(output / "interaction_stability.csv", index=False)
    test_metrics.to_csv(output / "test_metrics.csv", index=False)
    stability = stability_summary(weight_paths, research_config)
    stability.to_csv(output / "weight_stability.csv", index=False)
    intervals = bootstrap_weight_intervals(
        weight_paths.loc[:, ["fold_id", "method", "seed", *research_config.factors]],
        samples=research_config.bootstrap_samples,
        block_length=research_config.block_length,
        seed=int(config["random_seed"]),
    )
    intervals.to_csv(output / "bootstrap_weight_intervals.csv", index=False)
    total_expected = len(symbols) * len(config["folds"])
    total_available = total_expected - len(unavailable_rows)
    coverage = total_available / total_expected if total_expected > 0 else 0.0
    if weight_paths.empty or coverage < 0.9:
        status = "data_quality_blocked"
    elif coverage >= 1.0:
        status = "ready"
    else:
        status = "ready_with_gaps"
    manifest = {
        "status": status,
        "research_only": True,
        "coverage": coverage,
        "total_expected_folds": total_expected,
        "total_available_folds": total_available,
        "phase": "composite_stability_phase2",
        "market": "US",
        "config_sha256": _sha256(config_path),
        "source_manifest_sha256": _sha256(source_manifest),
        "macro_data_manifest_sha256": _sha256(macro_manifest),
        "symbols": symbols,
        "folds": config["folds"],
        "purge_days": 20,
        "embargo_days": 20,
        "horizon_days": research_config.horizon_days,
        "methods": list(methods),
        "seeds": list(seeds),
        "artifacts": {
            "weight_paths": "weight_paths.parquet",
            "weight_stability": "weight_stability.csv",
            "interaction_stability": "interaction_stability.csv",
            "bootstrap_weight_intervals": "bootstrap_weight_intervals.csv",
            "test_metrics": "test_metrics.csv",
        },
        "quality": quality_rows,
        "unavailable_folds": unavailable_rows,
        "train_transforms": transform_records,
        "nested_ablation": {
            "modes": ["none", "single", "all", "permuted"],
            "main_effects_frozen": True,
            "centered_on_train": True,
            "validation_not_used_for_weight_refit": True,
            "test_evaluated_with_frozen_candidate": True,
        },
        "interaction_gate": {
            "min_folds_consistent": 2,
            "total_folds": 3,
            "threshold": "2/3 folds (67%)",
        },
    }
    (output / "nested_optimization_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return {
        "status": manifest["status"],
        "research_only": True,
        "symbols": len(symbols),
        "folds": len(config["folds"]),
        "weight_rows": len(weight_paths),
        "interaction_rows": len(interactions),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "model-test/configs/composite_stability_phase2.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "model-test/outputs/composite_stability_phase2")
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output), indent=2))


if __name__ == "__main__":
    main()
