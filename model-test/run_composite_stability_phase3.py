"""Phase 3: Position mapping and execution constraint research.

Consumes Phase 2 frozen weights and compares:
- Position maps: quantile, dead-zone softsign, vol-target, monotone calibrated
- Execution constraints: no-trade band, rebalance cadence, delta limits
- Cost sensitivity: base, 2x, 4x

All maps fit on train-only data; validation/test only transform.
Outputs:
- position_map_ablation.csv
- execution_constraint_ablation.csv
- daily_position_audit.parquet
- cost_sensitivity.csv
- mapping_decision.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from model_test.position_map_research import (
    PositionMapConfig,
    ExecutionConstraints,
    fit_position_map,
    compute_diagnostics,
    run_position_map_ablation,
)


def load_phase2_weights(phase2_dir: Path) -> tuple[dict, pd.DataFrame]:
    """Load Phase 2 manifest and weight paths."""
    # Try nested_optimization_manifest.json first, then fallback to manifest.json
    manifest_path = phase2_dir / "nested_optimization_manifest.json"
    if not manifest_path.exists():
        manifest_path = phase2_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Phase 2 manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    status = manifest.get("status", "")
    if status not in ("ready", "ready_with_gaps"):
        raise ValueError(f"Phase 2 status is {status}, expected 'ready' or 'ready_with_gaps'")

    weight_paths_file = phase2_dir / "weight_paths.parquet"
    if not weight_paths_file.exists():
        raise FileNotFoundError(f"Weight paths not found: {weight_paths_file}")

    weight_paths = pd.read_parquet(weight_paths_file)
    return manifest, weight_paths


def compute_composite_score(
    df: pd.DataFrame,
    weights: dict[str, float],
    interaction_weight: float = 0.0,
) -> pd.Series:
    """Compute composite score from factors and weights."""
    score = pd.Series(0.0, index=df.index)

    for factor, weight in weights.items():
        if factor in df.columns:
            score += weight * df[factor].fillna(0.0)

    # Add interaction term if present
    if interaction_weight != 0.0 and "volume_ratio_rank" in df.columns and "mom_short_z" in df.columns:
        interaction = df["volume_ratio_rank"] * df["mom_short_z"]
        score += interaction_weight * interaction.fillna(0.0)

    return score


def run_phase3(config_path: Path) -> None:
    """Run Phase 3 position mapping research."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    print("=" * 60)
    print("Phase 3: Position Mapping and Execution Constraints")
    print("=" * 60)

    # Load Phase 2 results
    phase2_dir = Path(config["phase2_output_dir"])
    print(f"\nLoading Phase 2 results from: {phase2_dir}")
    phase2_manifest, weight_paths = load_phase2_weights(phase2_dir)

    # Select best weights from Phase 2
    # Weight columns are the factors themselves
    factor_columns = ['mom_short_z', 'rsi_z', 'macd_z', 'vix_level', 'volume_ratio_rank']

    # Filter to only available factor columns
    available_factors = [col for col in factor_columns if col in weight_paths.columns]

    if not available_factors:
        raise ValueError(f"No factor columns found in weight_paths. Available: {weight_paths.columns.tolist()}")

    # Use median weights across all runs
    best_weights = {}
    for factor in available_factors:
        factor_weights = weight_paths[factor]
        best_weights[factor] = float(factor_weights.median())

    # Check for interaction term (not in this format)
    interaction_weight = 0.0

    print(f"\nBest weights from Phase 2 (median across {len(weight_paths)} runs):")
    for factor, weight in best_weights.items():
        print(f"  {factor}: {weight:.4f}")

    # Load data (reuse Phase 2 data or load fresh)
    data_path = Path(config.get("data_path", "data/demo_factors_output.parquet"))
    if not data_path.exists():
        raise FileNotFoundError(f"Data not found: {data_path}")

    df = pd.read_parquet(data_path)
    print(f"\nLoaded data: {len(df)} rows, {len(df.columns)} columns")

    # Add symbol column if not present (single-stock data)
    if "symbol" not in df.columns:
        df["symbol"] = "DEMO"
        print("Added default symbol 'DEMO' for single-stock data")

    # Ensure required columns
    required = ["date", "close"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Add future_return_20d if not present
    if "future_return_20d" not in df.columns:
        print("Computing future_return_20d...")
        df = df.sort_values("date").reset_index(drop=True)
        df["future_return_20d"] = df["close"].pct_change(20).shift(-20)

    # Compute composite scores
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    df["composite_score"] = compute_composite_score(
        df, best_weights, interaction_weight
    )

    # Compute daily returns
    df["daily_return"] = df.groupby("symbol")["close"].pct_change()

    # Split train/test (use same split as Phase 2)
    split_date = pd.to_datetime(config.get("test_start_date", "2025-01-01"))
    train_df = df[df["date"] < split_date].copy()
    test_df = df[df["date"] >= split_date].copy()

    print(f"\nTrain: {len(train_df)} rows ({train_df['date'].min()} to {train_df['date'].max()})")
    print(f"Test:  {len(test_df)} rows ({test_df['date'].min()} to {test_df['date'].max()})")

    # Aggregate to daily (simple average across symbols for now)
    train_daily = (
        train_df.groupby("date")
        .agg(
            {
                "composite_score": "mean",
                "daily_return": "mean",
                "future_return_20d": "mean",
            }
        )
        .reset_index()
    )
    test_daily = (
        test_df.groupby("date")
        .agg(
            {
                "composite_score": "mean",
                "daily_return": "mean",
                "future_return_20d": "mean",
            }
        )
        .reset_index()
    )

    train_score = train_daily["composite_score"]
    train_returns = train_daily["daily_return"]
    train_future = train_daily["future_return_20d"]

    test_score = test_daily["composite_score"]
    test_returns = test_daily["daily_return"]

    # Define position map configurations
    map_configs = [
        PositionMapConfig(
            variant="quantile_5bin",
            p_max=1.0,
            positions=(0.0, 0.25, 0.50, 0.75, 1.0),
        ),
        PositionMapConfig(
            variant="dead_zone_softsign",
            p_max=1.0,
            threshold=0.25,
            scale=1.0,
        ),
        PositionMapConfig(
            variant="dead_zone_softsign",
            p_max=1.0,
            threshold=0.5,
            scale=1.5,
        ),
        PositionMapConfig(
            variant="vol_target",
            p_max=1.0,
            target_vol=0.15,
            vol_window=20,
        ),
        PositionMapConfig(
            variant="monotone_calibrated",
            p_max=1.0,
            increasing=True,
            calibration_clip=(-0.5, 0.5),
        ),
    ]

    # Define execution constraints
    execution_configs = [
        ExecutionConstraints(
            no_trade_band=0.02,
            max_daily_delta_increase=0.20,
            max_daily_delta_decrease=0.20,
            rebalance_cadence_days=1,
        ),
        ExecutionConstraints(
            no_trade_band=0.05,
            max_daily_delta_increase=0.10,
            max_daily_delta_decrease=0.15,
            rebalance_cadence_days=1,
        ),
        ExecutionConstraints(
            no_trade_band=0.02,
            max_daily_delta_increase=0.20,
            max_daily_delta_decrease=0.20,
            rebalance_cadence_days=3,
        ),
        ExecutionConstraints(
            no_trade_band=0.05,
            max_daily_delta_increase=0.10,
            max_daily_delta_decrease=0.15,
            rebalance_cadence_days=5,
        ),
    ]

    # Cost multipliers
    cost_multipliers = [1.0, 2.0, 4.0]

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(config["output_dir"]) / f"phase3_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nRunning position map ablation...")
    print(f"Maps: {len(map_configs)}")
    print(f"Execution configs: {len(execution_configs)}")
    print(f"Cost multipliers: {cost_multipliers}")
    print(f"Total combinations: {len(map_configs) * len(execution_configs) * len(cost_multipliers)}")

    # Run ablation
    ablation_df = run_position_map_ablation(
        train_score=train_score,
        train_returns=train_returns,
        train_future_return=train_future,
        test_score=test_score,
        test_returns=test_returns,
        map_configs=map_configs,
        execution_configs=execution_configs,
        cost_multipliers=cost_multipliers,
        output_dir=output_dir,
    )

    # Generate summary report
    print("\n" + "=" * 60)
    print("Phase 3 Results Summary")
    print("=" * 60)

    # Best by Sharpe at base cost
    base_cost = ablation_df[ablation_df["cost_multiplier"] == 1.0]
    best_sharpe = base_cost.nlargest(5, "sharpe_ratio")
    print("\nTop 5 by Sharpe Ratio (base cost):")
    print(best_sharpe[["variant", "execution_label", "sharpe_ratio", "net_return", "max_drawdown", "total_turnover"]])

    # Check saturation rates
    print("\nSaturation diagnostics:")
    saturation_check = ablation_df[["variant", "execution_label", "near_zero_rate", "near_max_rate"]].drop_duplicates()
    print(saturation_check)

    # Cost sensitivity
    print("\nCost sensitivity (best map at different costs):")
    best_map_variant = best_sharpe.iloc[0]["variant"]
    best_exec = best_sharpe.iloc[0]["execution_label"]
    cost_sens = ablation_df[
        (ablation_df["variant"] == best_map_variant) & (ablation_df["execution_label"] == best_exec)
    ][["cost_multiplier", "sharpe_ratio", "net_return", "transaction_cost", "cost_to_gross_ratio"]]
    print(cost_sens)

    # Save manifest
    manifest = {
        "phase": "phase3_position_mapping",
        "timestamp": timestamp,
        "status": "ready",
        "phase2_manifest_hash": hashlib.sha256(
            json.dumps(phase2_manifest, sort_keys=True).encode()
        ).hexdigest()[:16],
        "config": config,
        "best_weights": best_weights,
        "interaction_weight": interaction_weight,
        "train_period": {
            "start": str(train_daily["date"].min()),
            "end": str(train_daily["date"].max()),
            "n_days": len(train_daily),
        },
        "test_period": {
            "start": str(test_daily["date"].min()),
            "end": str(test_daily["date"].max()),
            "n_days": len(test_daily),
        },
        "ablation_stats": {
            "n_maps": len(map_configs),
            "n_execution_configs": len(execution_configs),
            "n_cost_multipliers": len(cost_multipliers),
            "total_combinations": len(ablation_df),
        },
        "best_result": {
            "variant": best_sharpe.iloc[0]["variant"],
            "execution_label": best_sharpe.iloc[0]["execution_label"],
            "sharpe_ratio": float(best_sharpe.iloc[0]["sharpe_ratio"]),
            "net_return": float(best_sharpe.iloc[0]["net_return"]),
            "max_drawdown": float(best_sharpe.iloc[0]["max_drawdown"]),
            "near_max_rate": float(best_sharpe.iloc[0]["near_max_rate"]),
        },
    }

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Generate markdown decision report
    with open(output_dir / "mapping_decision.md", "w", encoding="utf-8") as f:
        f.write("# Phase 3: Position Mapping Decision Report\n\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write("## Objective\n\n")
        f.write("Resolve saturation, turnover, and cost erosion by comparing position maps and execution constraints.\n\n")
        f.write("## Best Configuration (Base Cost)\n\n")
        f.write(f"- **Map**: {manifest['best_result']['variant']}\n")
        f.write(f"- **Execution**: {manifest['best_result']['execution_label']}\n")
        f.write(f"- **Sharpe Ratio**: {manifest['best_result']['sharpe_ratio']:.3f}\n")
        f.write(f"- **Net Return**: {manifest['best_result']['net_return']:.3%}\n")
        f.write(f"- **Max Drawdown**: {manifest['best_result']['max_drawdown']:.3%}\n")
        f.write(f"- **Near-Max Position Rate**: {manifest['best_result']['near_max_rate']:.3%}\n\n")
        f.write("## Saturation Gate\n\n")
        f.write(f"Threshold: near_max_position_rate <= 90%\n")
        f.write(f"Result: {'PASS' if manifest['best_result']['near_max_rate'] <= 0.90 else 'FAIL'}\n\n")
        f.write("## Cost Sensitivity\n\n")
        f.write("See cost_sensitivity.csv for full analysis.\n\n")
        f.write("## Next Steps\n\n")
        f.write("- If saturation gate passes: proceed to Phase 4 cross-fold validation\n")
        f.write("- If saturation gate fails: adjust map parameters or refactor composite score\n")

    # Save cost sensitivity as separate CSV
    cost_sens.to_csv(output_dir / "cost_sensitivity.csv", index=False)

    print(f"\n[OK] Phase 3 complete. Results saved to: {output_dir}")
    print(f"  - manifest.json")
    print(f"  - position_map_ablation.csv")
    print(f"  - cost_sensitivity.csv")
    print(f"  - mapping_decision.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3: Position mapping research")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("model-test/configs/composite_stability_phase3.json"),
        help="Path to Phase 3 config file",
    )
    args = parser.parse_args()

    run_phase3(args.config)
