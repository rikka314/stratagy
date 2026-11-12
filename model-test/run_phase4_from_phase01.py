"""Phase 4: Advisory evaluation using Phase 0/1 decision_audit data.

This script extracts already-computed advisory decisions from Phase 0/1's
decision_audit.parquet and aggregates them into Phase 4 fold-level metrics.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from model_test.cross_fold_admission import (
    StrategyCandidate,
    FoldMetrics,
    AdmissionGate,
    compute_returns_and_equity,
    compute_drawdown_stats,
    compute_sharpe_sortino,
    check_admission,
    aggregate_candidate_metrics,
    export_fold_metrics_csv,
    export_admission_summary,
)


def compute_strategy_metrics(
    strategy_df: pd.DataFrame,
    fold_id: str,
    start_date: str,
    end_date: str,
    return_col: str = 'strategy_return',
    commission: float = 0.001,
    slippage: float = 0.0005,
    costs_already_included: bool = False,
) -> FoldMetrics:
    """Compute fold metrics from Phase 0/1 decision audit data.

    Args:
        strategy_df: DataFrame with columns [date, symbol, final_position, return_col]
        fold_id: Fold identifier
        start_date: Test start date
        end_date: Test end date
        return_col: Name of return column to use
        commission: Commission rate
        slippage: Slippage rate
        costs_already_included: If True, returns already include transaction costs

    Returns:
        FoldMetrics for this strategy and fold
    """
    # Aggregate across symbols: equal-weight portfolio
    agg_dict = {
        'final_position': 'mean',
        return_col: 'mean',
    }

    # Add optional columns if they exist
    if 'composite_base_position' in strategy_df.columns:
        agg_dict['composite_base_position'] = 'mean'
    if 'advisory_multiplier' in strategy_df.columns:
        agg_dict['advisory_multiplier'] = 'mean'
    if 'fallback_used' in strategy_df.columns:
        agg_dict['fallback_used'] = 'mean'
    if 'turnover' in strategy_df.columns:
        agg_dict['turnover'] = 'sum'
    if 'transaction_cost' in strategy_df.columns:
        agg_dict['transaction_cost'] = 'sum'

    daily_agg = strategy_df.groupby('date').agg(agg_dict).sort_index()

    positions = daily_agg['final_position']
    returns = daily_agg[return_col]

    # If costs are already included in returns, use them directly
    if costs_already_included:
        net_returns = returns
        net_equity = (1 + net_returns).cumprod()
        total_return = float(net_equity.iloc[-1] - 1)
        gross_return = total_return  # Approximate

        # Estimate costs from turnover if available
        if 'turnover' in daily_agg.columns:
            total_cost = float(daily_agg['turnover'].sum() * (commission + slippage))
        elif 'transaction_cost' in daily_agg.columns:
            total_cost = float(daily_agg['transaction_cost'].sum())
        else:
            position_changes = positions.diff().abs()
            position_changes.iloc[0] = positions.iloc[0]
            total_cost = float(position_changes.sum() * (commission + slippage))

        gross_return = total_return + total_cost
    else:
        # Compute returns and costs
        gross_returns, costs, net_returns, total_cost = compute_returns_and_equity(
            positions, returns, commission, slippage
        )

        # Equity curves
        gross_equity = (1 + gross_returns).cumprod()
        net_equity = (1 + net_returns).cumprod()

        # Returns
        total_return = float(net_equity.iloc[-1] - 1)
        gross_return = float(gross_equity.iloc[-1] - 1)

    # Risk metrics
    sharpe, sortino, volatility = compute_sharpe_sortino(net_returns)

    # Drawdown
    max_dd, dd_duration, recovery_time = compute_drawdown_stats(net_equity)

    # Win rate
    daily_win_rate = float((net_returns > 0).mean())

    # Exposure
    mean_exposure = float(positions.mean())
    median_exposure = float(positions.median())
    max_exposure = float(positions.max())
    near_zero_rate = float((positions <= 0.01).mean())
    near_max_rate = float((positions >= 0.99).mean())

    # Turnover
    if 'turnover' in daily_agg.columns:
        total_turnover = float(daily_agg['turnover'].sum())
        daily_avg_turnover = float(daily_agg['turnover'].mean())
        trade_count = int((daily_agg['turnover'] > 0.001).sum())
        rebalance_count = trade_count
    else:
        position_changes = positions.diff().abs()
        position_changes.iloc[0] = positions.iloc[0]
        total_turnover = float(position_changes.sum())
        daily_avg_turnover = float(position_changes.mean())
        trade_count = int((position_changes > 0.001).sum())
        rebalance_count = trade_count

    # Cost ratio
    cost_to_gross_ratio = float(total_cost / gross_return) if gross_return > 0 else 0.0

    # Advisory-specific metrics
    trigger_rate = float(daily_agg['advisory_multiplier'].lt(1.0).mean()) if 'advisory_multiplier' in daily_agg else 0.0
    fallback_rate = float(daily_agg['fallback_used'].mean()) if 'fallback_used' in daily_agg else 0.0
    saturation_trigger_rate = float(daily_agg['composite_base_position'].ge(0.99).mean()) if 'composite_base_position' in daily_agg else 0.0

    return FoldMetrics(
        fold_id=fold_id,
        start_date=start_date,
        end_date=end_date,
        trading_days=len(daily_agg),
        total_return=total_return,
        net_return=total_return,
        gross_return=gross_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        annualized_volatility=volatility,
        max_drawdown=max_dd,
        max_drawdown_duration_days=dd_duration,
        recovery_time_days=recovery_time,
        daily_win_rate=daily_win_rate,
        monthly_win_rate=None,
        mean_exposure=mean_exposure,
        median_exposure=median_exposure,
        max_exposure=max_exposure,
        near_zero_rate=near_zero_rate,
        near_max_rate=near_max_rate,
        total_turnover=total_turnover,
        daily_avg_turnover=daily_avg_turnover,
        trade_count=trade_count,
        rebalance_count=rebalance_count,
        transaction_cost=total_cost,
        cost_to_gross_ratio=cost_to_gross_ratio,
        trigger_rate=trigger_rate,
        fallback_rate=fallback_rate,
        saturation_trigger_rate=saturation_trigger_rate,
        has_data_quality_issue=False,
        has_pit_violation=False,
        has_audit_failure=False,
        quality_notes="",
    )


def run_phase4_from_phase01(phase01_dir: Path, output_dir: Path, config: dict) -> None:
    """Run Phase 4 analysis using Phase 0/1 decision audit data."""
    print("=" * 60)
    print("Phase 4: Advisory Evaluation (from Phase 0/1 data)")
    print("=" * 60)

    # Load decision audit
    audit_path = phase01_dir / "decision_audit.parquet"
    print(f"\nLoading decision audit from: {audit_path}")
    df = pd.read_parquet(audit_path)
    print(f"Loaded {len(df):,} decision rows")
    print(f"Policies: {df['policy'].unique().tolist()}")
    print(f"Symbols: {df['symbol'].nunique()}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")

    # Determine which return column to use
    if 'strategy_return' in df.columns:
        return_col = 'strategy_return'
        print(f"Using 'strategy_return' column (already includes costs)")
    elif 'return_1d' in df.columns:
        return_col = 'return_1d'
        print(f"Using 'return_1d' column")
    else:
        print("\nERROR: No return column found in decision_audit")
        print("Available columns:", df.columns.tolist())
        return

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
        test_start = pd.to_datetime(fold_spec["test_start"])
        test_end = pd.to_datetime(fold_spec["test_end"])

        print(f"\n{'=' * 60}")
        print(f"Processing {fold_id}")
        print(f"{'=' * 60}")
        print(f"Test: {test_start.date()} to {test_end.date()}")

        # Filter to test period
        fold_df = df[(df['date'] >= test_start) & (df['date'] <= test_end)].copy()
        print(f"Test rows: {len(fold_df):,}")

        if len(fold_df) == 0:
            print(f"WARNING: No data in test period for {fold_id}")
            continue

        # Evaluate each candidate
        for candidate in candidates:
            variant = candidate.variant
            print(f"\nEvaluating: {variant}")

            # Filter to this policy
            strategy_df = fold_df[fold_df['policy'] == variant].copy()

            if len(strategy_df) == 0:
                print(f"  WARNING: No data for policy '{variant}'")
                continue

            try:
                metrics = compute_strategy_metrics(
                    strategy_df,
                    fold_id,
                    test_start.strftime('%Y-%m-%d'),
                    test_end.strftime('%Y-%m-%d'),
                    return_col=return_col,
                    commission=commission,
                    slippage=slippage,
                    costs_already_included=(return_col == 'strategy_return'),
                )

                candidate.fold_metrics.append(metrics)

                print(f"  Sharpe: {metrics.sharpe_ratio:.3f}")
                print(f"  Total return: {metrics.total_return:.2%}")
                print(f"  Max DD: {metrics.max_drawdown:.1%}")
                print(f"  Turnover: {metrics.total_turnover:.2f}")
                print(f"  Mean exposure: {metrics.mean_exposure:.2%}")
                print(f"  Near-max rate: {metrics.near_max_rate:.1%}")
                if variant.startswith('composite_plus_'):
                    print(f"  Trigger rate: {metrics.trigger_rate:.1%}")
                    print(f"  Fallback rate: {metrics.fallback_rate:.1%}")

            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                continue

    # Aggregate metrics
    print(f"\n{'=' * 60}")
    print("Aggregating metrics across folds")
    print(f"{'=' * 60}")

    gate = AdmissionGate(**config["admission_gate"])

    for candidate in candidates:
        if len(candidate.fold_metrics) == 0:
            print(f"\n{candidate.variant}: No folds evaluated")
            continue

        aggregate_candidate_metrics(candidate)
        status, reason = check_admission(candidate, gate)

        candidate.admission_status = status
        candidate.admission_notes = reason

        print(f"\n{candidate.variant}:")
        print(f"  Mean Sharpe: {candidate.mean_sharpe:.3f}")
        print(f"  Median Sharpe: {candidate.median_sharpe:.3f}")
        print(f"  Worst Sharpe: {candidate.worst_sharpe:.3f}")
        print(f"  Folds passed: {candidate.folds_passed}/{candidate.total_folds}")
        print(f"  Status: {candidate.admission_status}")
        print(f"  Notes: {candidate.admission_notes}")

    # Export results
    output_dir.mkdir(parents=True, exist_ok=True)

    export_fold_metrics_csv(candidates, output_dir / "fold_metrics.csv")
    export_admission_summary(candidates, gate, output_dir / "admission_summary.csv")

    # Create manifest
    manifest = {
        "phase": "phase4_advisory_from_phase01",
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "phase01_dir": str(phase01_dir),
        "status": "ready",
        "total_folds": len(config["folds"]),
        "candidates_evaluated": len([c for c in candidates if len(c.fold_metrics) > 0]),
        "candidates_passed": sum(1 for c in candidates if c.admission_status == "pass"),
    }

    manifest_path = output_dir / "phase4_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'=' * 60}")
    print("Phase 4 Complete")
    print(f"{'=' * 60}")
    print(f"Output directory: {output_dir}")
    print(f"Candidates evaluated: {manifest['candidates_evaluated']}")
    print(f"Candidates passed: {manifest['candidates_passed']}")


def main():
    parser = argparse.ArgumentParser(description="Run Phase 4 advisory evaluation from Phase 0/1 data")
    parser.add_argument(
        "--phase01-dir",
        type=Path,
        default=Path("outputs/composite_advisory_phase1"),
        help="Path to Phase 0/1 output directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/composite_stability_phase4_advisory"),
        help="Output directory for Phase 4 results",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/composite_stability_phase4_from_phase01.json"),
        help="Path to Phase 4 config file",
    )
    args = parser.parse_args()

    if not args.phase01_dir.exists():
        raise FileNotFoundError(f"Phase 0/1 directory not found: {args.phase01_dir}")

    if not args.config.exists():
        raise FileNotFoundError(f"Config not found: {args.config}")

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    run_phase4_from_phase01(args.phase01_dir, args.output_dir, config)


if __name__ == "__main__":
    main()
