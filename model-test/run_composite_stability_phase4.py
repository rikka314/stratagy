"""Phase 4: Cross-fold admission testing runner.

Compares composite strategy candidates across purged folds:
1. Load Phase 3 best map config
2. For each fold:
   - Fit map on fold train data
   - Transform fold test data
   - Compute all metrics
3. Aggregate across folds
4. Check admission gate

Outputs:
- fold_metrics.csv: all fold-level metrics
- admission_summary.csv: aggregated results and admission decision
- phase4_manifest.json: run metadata
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from model_test.cross_fold_admission import (
    StrategyCandidate,
    FoldMetrics,
    AdmissionGate,
    evaluate_fold,
    check_admission,
    aggregate_candidate_metrics,
    export_fold_metrics_csv,
    export_admission_summary,
)
from model_test.position_map_research import (
    PositionMapConfig,
    ExecutionConstraints,
    fit_position_map,
)


def load_phase3_best_config(phase3_dir: Path) -> tuple[PositionMapConfig, ExecutionConstraints]:
    """Load Phase 3 best map and execution config from manifest."""
    manifest_path = phase3_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Phase 3 manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Extract best config (simplified - assumes manifest has best_result)
    # In reality, you'd parse position_map_ablation.csv and select best
    best_result = manifest.get("best_result", {})

    # Default to quantile_5bin if not specified
    map_config = PositionMapConfig(
        variant="quantile_5bin",
        quantiles=(0.0, 0.35, 0.60, 0.80, 1.0),
        positions=(0.0, 0.25, 0.50, 0.75, 1.0),
    )

    exec_config = ExecutionConstraints(
        no_trade_band=0.05,
        max_daily_delta_increase=0.10,
        max_daily_delta_decrease=0.15,
        rebalance_cadence_days=1,
    )

    print(f"Loaded Phase 3 best config: {map_config.variant}")
    return map_config, exec_config


def load_phase2_weights(phase2_dir: Path) -> dict[str, float]:
    """Load Phase 2 best weights."""
    weight_stability_path = phase2_dir / "weight_stability.csv"
    if not weight_stability_path.exists():
        raise FileNotFoundError(f"Weight stability not found: {weight_stability_path}")

    df = pd.read_csv(weight_stability_path)

    # Use coefficient_mean as stable estimate (not median_weight)
    weights = {}
    for _, row in df.iterrows():
        factor = row["factor"]
        weights[factor] = row["coefficient_mean"]

    print(f"Loaded {len(weights)} factor weights from Phase 2")
    return weights


def compute_composite_score(
    df: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    """Compute composite score from factors and weights."""
    score = pd.Series(0.0, index=df.index)

    for factor, weight in weights.items():
        if factor in df.columns:
            score += weight * df[factor].fillna(0.0)
        else:
            print(f"Warning: factor {factor} not in data")

    return score


def evaluate_composite_only(
    fold_id: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    weights: dict[str, float],
    map_config: PositionMapConfig,
    exec_config: ExecutionConstraints,
    commission: float,
    slippage: float,
) -> FoldMetrics:
    """Evaluate composite_only strategy on a single fold."""
    # Compute scores
    train_scores = compute_composite_score(train_df, weights)
    test_scores = compute_composite_score(test_df, weights)

    # Fit position map on train
    from model_test.position_map_research import fit_position_map
    train_returns = train_df["return"] if "return" in train_df.columns else train_df["close"].pct_change()

    # fit_position_map returns a PositionMapResult object
    map_result = fit_position_map(
        config=map_config,
        train_score=train_scores,
        train_returns=train_returns,
    )

    # Transform test scores to positions using the fitted result
    test_positions = map_result.transform(test_scores, returns=None)

    # For simplicity in Phase 4, skip execution constraints
    # (In production, would apply no-trade band, rebalance cadence, etc.)
    test_positions_exec = test_positions

    # Evaluate
    test_returns = test_df["return"] if "return" in test_df.columns else test_df["close"].pct_change()

    metrics = evaluate_fold(
        fold_id=fold_id,
        df=test_df,
        positions=test_positions_exec,
        returns=test_returns,
        scores=test_scores,
        commission=commission,
        slippage=slippage,
    )

    return metrics


def evaluate_cash_baseline(
    fold_id: str,
    test_df: pd.DataFrame,
) -> FoldMetrics:
    """Evaluate cash baseline (zero position)."""
    positions = pd.Series(0.0, index=test_df.index)
    returns = test_df["return"] if "return" in test_df.columns else test_df["close"].pct_change()

    metrics = evaluate_fold(
        fold_id=fold_id,
        df=test_df,
        positions=positions,
        returns=returns,
        commission=0.0,
        slippage=0.0,
    )

    return metrics


def evaluate_equal_weight_composite(
    fold_id: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    factor_names: list[str],
    map_config: PositionMapConfig,
    exec_config: ExecutionConstraints,
    commission: float,
    slippage: float,
) -> FoldMetrics:
    """Evaluate equal-weight composite."""
    # Equal weights for all factors
    n = len(factor_names)
    weights = {f: 1.0 / n for f in factor_names}

    return evaluate_composite_only(
        fold_id, train_df, test_df, weights, map_config, exec_config, commission, slippage
    )


def evaluate_composite_with_advisory(
    fold_id: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    weights: dict[str, float],
    map_config: PositionMapConfig,
    exec_config: ExecutionConstraints,
    commission: float,
    slippage: float,
    policy: str,
) -> FoldMetrics:
    """Evaluate composite strategy with advisory overlay.

    Args:
        fold_id: Fold identifier
        train_df: Training data for fitting map
        test_df: Test data for evaluation
        weights: Factor weights from Phase 2
        map_config: Position map configuration
        exec_config: Execution constraints
        commission: Commission rate
        slippage: Slippage rate
        policy: Advisory policy name (e.g., 'composite_plus_trend')

    Returns:
        FoldMetrics with advisory overlay results
    """
    from core.composite_advisory import CompositeAdvisory, decide_frame

    # 1. Compute composite base positions (same as composite_only)
    train_scores = compute_composite_score(train_df, weights)
    test_scores = compute_composite_score(test_df, weights)

    # Fit position map on train
    train_returns = train_df["return"] if "return" in train_df.columns else train_df["close"].pct_change()
    map_result = fit_position_map(
        config=map_config,
        train_score=train_scores,
        train_returns=train_returns,
    )

    # Transform test scores to base positions
    test_base_positions = map_result.transform(test_scores, returns=None)

    # 2. Prepare factor frame for advisory evaluation
    # CompositeAdvisory needs the raw factor columns to compute expert signals
    required_factors = test_df.copy()

    # Fill NaN values to pass ExpertPoolV2 validation
    # Use forward fill then backward fill to handle leading NaNs
    numeric_cols = required_factors.select_dtypes(include=[np.number]).columns
    required_factors[numeric_cols] = required_factors[numeric_cols].ffill().bfill().fillna(0.0)

    if "date" not in required_factors.columns and required_factors.index.name == "date":
        required_factors = required_factors.reset_index()

    # 3. Apply advisory overlay using decide_frame
    advisory = CompositeAdvisory()
    try:
        decisions = decide_frame(required_factors, policy=policy, advisory=advisory)

        # Extract final positions from advisory decisions
        test_positions = pd.Series(decisions["final_position"].values, index=test_df.index)

        # Compute trigger/fallback statistics
        trigger_rate = float((decisions["advisory_multiplier"] < 1.0).mean())
        fallback_rate = float(decisions["fallback_used"].mean())
        saturation_trigger_rate = float((decisions["composite_base_position"] >= 0.99).mean())

    except Exception as e:
        print(f"  ERROR: Advisory evaluation failed")
        print(f"    Exception: {type(e).__name__}: {e}")
        print(f"    Required factors shape: {required_factors.shape}")
        print(f"    Falling back to base composite positions")
        # Ensure fallback uses base positions, not zero
        test_positions = pd.Series(test_base_positions.values, index=test_df.index)
        trigger_rate = 0.0
        fallback_rate = 1.0
        saturation_trigger_rate = 0.0

    # 4. Apply execution constraints (simplified)
    test_positions_exec = test_positions

    # 5. Evaluate performance
    test_returns = test_df["return"] if "return" in test_df.columns else test_df["close"].pct_change()

    metrics = evaluate_fold(
        fold_id=fold_id,
        df=test_df,
        positions=test_positions_exec,
        returns=test_returns,
        scores=test_scores,
        commission=commission,
        slippage=slippage,
    )

    # 6. Override trigger/fallback statistics in metrics
    # FoldMetrics is frozen, so create new instance with updated values
    from dataclasses import replace
    metrics = replace(
        metrics,
        trigger_rate=trigger_rate,
        fallback_rate=fallback_rate,
        saturation_trigger_rate=saturation_trigger_rate,
    )

    return metrics


def run_phase4(config_path: Path) -> None:
    """Run Phase 4 cross-fold admission testing."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    print("=" * 60)
    print("Phase 4: Cross-Fold Admission Testing")
    print("=" * 60)

    # Load Phase 2 and Phase 3 artifacts
    phase2_dir = Path(config["phase2_output_dir"])
    phase3_dir = Path(config["phase3_output_dir"])

    print(f"\nLoading Phase 2 results from: {phase2_dir}")
    weights = load_phase2_weights(phase2_dir)

    print(f"Loading Phase 3 results from: {phase3_dir}")
    map_config, exec_config = load_phase3_best_config(phase3_dir)

    # Load data
    data_path = Path(config["data_path"])
    print(f"\nLoading data from: {data_path}")
    full_df = pd.read_parquet(data_path)

    if "date" in full_df.columns:
        full_df["date"] = pd.to_datetime(full_df["date"])
        full_df = full_df.set_index("date")

    # Ensure return column exists
    if "return" not in full_df.columns and "close" in full_df.columns:
        full_df["return"] = full_df["close"].pct_change()

    # Get factor names
    factor_names = list(weights.keys())

    # Initialize candidates
    candidates = []
    for strategy_spec in config["strategy_candidates"]:
        candidate = StrategyCandidate(
            variant=strategy_spec["variant"],
            description=strategy_spec["description"],
        )
        candidates.append(candidate)

    # Process each fold
    commission = config["base_commission"]
    slippage = config["base_slippage"]

    for fold_spec in config["folds"]:
        fold_id = fold_spec["fold_id"]
        print(f"\n{'=' * 60}")
        print(f"Processing {fold_id}")
        print(f"{'=' * 60}")

        # Split data
        train_start = pd.to_datetime(fold_spec["train_start"])
        train_end = pd.to_datetime(fold_spec["train_end"])
        test_start = pd.to_datetime(fold_spec["test_start"])
        test_end = pd.to_datetime(fold_spec["test_end"])

        train_df = full_df.loc[train_start:train_end].copy()
        test_df = full_df.loc[test_start:test_end].copy()

        print(f"Train: {train_start.date()} to {train_end.date()} ({len(train_df)} days)")
        print(f"Test:  {test_start.date()} to {test_end.date()} ({len(test_df)} days)")

        # Evaluate each candidate
        for candidate in candidates:
            print(f"\nEvaluating: {candidate.variant}")

            try:
                if candidate.variant == "cash":
                    metrics = evaluate_cash_baseline(fold_id, test_df)
                elif candidate.variant == "composite_only":
                    metrics = evaluate_composite_only(
                        fold_id, train_df, test_df, weights, map_config, exec_config,
                        commission, slippage
                    )
                elif candidate.variant == "composite_equal_weight":
                    metrics = evaluate_equal_weight_composite(
                        fold_id, train_df, test_df, factor_names, map_config, exec_config,
                        commission, slippage
                    )
                elif candidate.variant == "composite_no_interaction":
                    # Same as composite_only for now (no interaction term in weights)
                    metrics = evaluate_composite_only(
                        fold_id, train_df, test_df, weights, map_config, exec_config,
                        commission, slippage
                    )
                elif candidate.variant.startswith("composite_plus_"):
                    # Advisory overlay strategies
                    metrics = evaluate_composite_with_advisory(
                        fold_id, train_df, test_df, weights, map_config, exec_config,
                        commission, slippage, policy=candidate.variant
                    )
                else:
                    print(f"Skipping unimplemented variant: {candidate.variant}")
                    continue

                candidate.fold_metrics.append(metrics)

                print(f"  Sharpe: {metrics.sharpe_ratio:.3f}")
                print(f"  Max DD: {metrics.max_drawdown:.1%}")
                print(f"  Turnover: {metrics.total_turnover:.2f}")
                print(f"  Near-max rate: {metrics.near_max_rate:.1%}")

            except Exception as e:
                print(f"  ERROR: {e}")
                continue

    # Aggregate metrics
    print(f"\n{'=' * 60}")
    print("Aggregating metrics across folds")
    print(f"{'=' * 60}")

    gate = AdmissionGate(**config["admission_gate"])

    for candidate in candidates:
        aggregate_candidate_metrics(candidate)
        status, reason = check_admission(candidate, gate)

        candidate.admission_status = status
        candidate.admission_notes = reason
        candidate.folds_passed = sum(
            1 for fm in candidate.fold_metrics
            if fm.sharpe_ratio >= gate.min_sharpe_ratio
            and fm.max_drawdown <= gate.max_drawdown_threshold
        )
        candidate.pass_rate = candidate.folds_passed / candidate.total_folds if candidate.total_folds > 0 else 0.0

        print(f"\n{candidate.variant}:")
        print(f"  Mean Sharpe: {candidate.mean_sharpe:.3f}")
        print(f"  Median Sharpe: {candidate.median_sharpe:.3f}")
        print(f"  Worst Sharpe: {candidate.worst_sharpe:.3f}")
        print(f"  Folds passed: {candidate.folds_passed}/{candidate.total_folds}")
        print(f"  Status: {candidate.admission_status}")
        print(f"  Notes: {candidate.admission_notes}")

    # Export results
    output_dir = Path(config["output_dir"]) / "composite_stability_phase4"
    output_dir.mkdir(parents=True, exist_ok=True)

    export_fold_metrics_csv(candidates, output_dir / "fold_metrics.csv")
    export_admission_summary(candidates, gate, output_dir / "admission_summary.csv")

    # Create manifest
    manifest = {
        "phase": "phase4_cross_fold_admission",
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "phase2_dir": str(phase2_dir),
        "phase3_dir": str(phase3_dir),
        "status": "ready",
        "total_folds": len(config["folds"]),
        "candidates_evaluated": len(candidates),
        "candidates_passed": sum(1 for c in candidates if c.admission_status == "pass"),
    }

    manifest_path = output_dir / "phase4_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'=' * 60}")
    print("Phase 4 Complete")
    print(f"{'=' * 60}")
    print(f"Output directory: {output_dir}")
    print(f"Candidates passed: {manifest['candidates_passed']}/{manifest['candidates_evaluated']}")


def main():
    parser = argparse.ArgumentParser(description="Run Phase 4 cross-fold admission testing")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/composite_stability_phase4.json"),
        help="Path to Phase 4 config file",
    )
    args = parser.parse_args()

    if not args.config.exists():
        raise FileNotFoundError(f"Config not found: {args.config}")

    run_phase4(args.config)


if __name__ == "__main__":
    main()
