"""Run CN_A baseline strategies for comparison with Composite.

This script runs SM and FSM baselines on the same CN_A universe and folds
used in Phase 4 Composite evaluation.

Usage:
    python model-test/run_cn_a_baseline.py --config model-test/configs/composite_cn_a.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_config(config_path: Path) -> dict:
    """Load and validate config."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if config["market"] != "CN_A":
        raise ValueError(f"This runner only supports CN_A, got: {config['market']}")

    return config


def create_folds(dates: pd.DatetimeIndex, n_folds: int = 4) -> list[dict]:
    """Create purged walk-forward folds (same as Phase 4)."""
    if len(dates) < 100:
        raise ValueError(f"Insufficient data: only {len(dates)} dates")

    dates_sorted = sorted(dates)
    total_days = len(dates_sorted)
    fold_size = total_days // n_folds

    folds = []
    for i in range(n_folds):
        test_start_idx = i * fold_size
        test_end_idx = min((i + 1) * fold_size, total_days)

        if i == 0:
            train_dates = []
            val_dates = []
        else:
            train_end_idx = test_start_idx - 20  # 20-day purge
            train_dates = dates_sorted[:train_end_idx]
            val_dates = dates_sorted[train_end_idx:test_start_idx]

        test_dates = dates_sorted[test_start_idx:test_end_idx]

        fold = {
            "fold_id": f"fold_{i:02d}",
            "train_dates": train_dates,
            "val_dates": val_dates,
            "test_dates": test_dates,
        }
        folds.append(fold)

    return folds


def run_sm_baseline(panel_df: pd.DataFrame) -> pd.DataFrame:
    """Run Simple Momentum (SM) baseline.

    SM uses short-term momentum (5-day) with simple thresholding.
    """
    results = []

    for (date, symbol), group in panel_df.groupby(["date", "symbol"]):
        if len(group) == 0:
            continue

        row = group.iloc[0]

        # SM logic: long if mom_short_z > 0
        mom_short = row.get("mom_short_z", 0.0)
        if pd.isna(mom_short):
            position = 0.0
        else:
            position = 1.0 if mom_short > 0 else 0.0

        results.append({
            "date": date,
            "symbol": symbol,
            "position": position,
            "strategy": "sm",
        })

    return pd.DataFrame(results)


def run_fsm_baseline(panel_df: pd.DataFrame) -> pd.DataFrame:
    """Run Filtered Simple Momentum (FSM) baseline.

    FSM adds volume filter to SM: only trade if volume is above average.
    """
    results = []

    for (date, symbol), group in panel_df.groupby(["date", "symbol"]):
        if len(group) == 0:
            continue

        row = group.iloc[0]

        # FSM logic: SM + volume filter
        mom_short = row.get("mom_short_z", 0.0)
        volume_ratio = row.get("volume_ratio_rank", 0.5)

        if pd.isna(mom_short) or pd.isna(volume_ratio):
            position = 0.0
        else:
            # Long if positive momentum AND above-average volume
            if mom_short > 0 and volume_ratio > 0.5:
                position = 1.0
            else:
                position = 0.0

        results.append({
            "date": date,
            "symbol": symbol,
            "position": position,
            "strategy": "fsm",
        })

    return pd.DataFrame(results)


def compute_strategy_returns(
    positions_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Compute strategy returns from positions."""
    # Merge positions with panel to get price data
    merged = positions_df.merge(
        panel_df[["date", "symbol", "close"]],
        on=["date", "symbol"],
        how="left"
    )

    # Sort by symbol and date
    merged = merged.sort_values(["symbol", "date"]).reset_index(drop=True)

    # Compute returns for each symbol
    symbol_groups = []
    for symbol, group in merged.groupby("symbol"):
        group = group.copy()

        # Compute 1-day return
        group["return_1d"] = group["close"].pct_change()

        # Strategy return = position (lagged 1 day) * return
        group["strategy_return"] = group["position"].shift(1) * group["return_1d"]

        # Compute turnover
        group["turnover"] = group["position"].diff().abs()

        # Apply transaction costs
        commission_bps = config["execution"]["commission_bps"]
        slippage_bps = config["execution"]["slippage_bps"]
        total_cost_bps = commission_bps + slippage_bps

        group["transaction_cost"] = group["turnover"] * (total_cost_bps / 10000.0)
        group["strategy_return"] = group["strategy_return"] - group["transaction_cost"]

        symbol_groups.append(group)

    return pd.concat(symbol_groups, ignore_index=True)


def compute_metrics(daily_returns: pd.Series) -> dict:
    """Compute performance metrics."""
    daily_returns = daily_returns.fillna(0.0)

    total_return = (1 + daily_returns).prod() - 1
    n_days = len(daily_returns)
    annual_return = (1 + total_return) ** (252 / n_days) - 1 if n_days > 0 else 0.0

    std = daily_returns.std()
    sharpe = (daily_returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0

    cumulative = (1 + daily_returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    win_rate = (daily_returns > 0).sum() / len(daily_returns) if len(daily_returns) > 0 else 0.0

    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "win_rate": float(win_rate),
        "n_days": int(n_days),
    }


def main():
    parser = argparse.ArgumentParser(description="Run CN_A baseline strategies")
    parser.add_argument("--config", required=True, help="Path to config JSON")
    args = parser.parse_args()

    config_path = Path(args.config)
    print(f"Loading config: {config_path}")
    config = load_config(config_path)

    # Load factor panel
    output_dir = Path("model-test/outputs") / config["output_subdir"]
    factor_panel_path = output_dir / "cn_a_factor_panel.parquet"

    if not factor_panel_path.exists():
        print(f"ERROR: Factor panel not found: {factor_panel_path}")
        print("Please run Phase 3 first")
        sys.exit(1)

    print(f"Loading factor panel: {factor_panel_path}")
    factor_panel = pd.read_parquet(factor_panel_path)
    print(f"Factor panel: {len(factor_panel)} rows")

    # Create folds
    all_dates = factor_panel["date"].unique()
    folds = create_folds(pd.DatetimeIndex(all_dates), n_folds=4)
    print(f"Created {len(folds)} folds")

    # Results storage
    all_results = []

    # Process each fold
    for fold in folds:
        fold_id = fold["fold_id"]
        print(f"\n{'='*60}")
        print(f"Processing {fold_id}")
        print(f"{'='*60}")

        if not fold["test_dates"]:
            print(f"Skipping {fold_id}: no test data")
            continue

        # Get test data
        test_panel = factor_panel[factor_panel["date"].isin(fold["test_dates"])]
        print(f"Test: {len(test_panel)} rows")

        # Get unique symbols (limit to first 5 for consistency with Phase 4)
        symbols = sorted(test_panel["symbol"].unique())[:5]
        test_panel = test_panel[test_panel["symbol"].isin(symbols)]

        print(f"Testing on {len(symbols)} symbols: {symbols}")

        # Run SM baseline
        print("Running SM baseline...")
        sm_positions = run_sm_baseline(test_panel)
        sm_results = compute_strategy_returns(sm_positions, test_panel, config)

        for symbol in symbols:
            symbol_data = sm_results[sm_results["symbol"] == symbol]
            metrics = compute_metrics(symbol_data["strategy_return"])
            metrics["fold_id"] = fold_id
            metrics["symbol"] = symbol
            metrics["strategy"] = "sm"
            all_results.append(metrics)

        # Run FSM baseline
        print("Running FSM baseline...")
        fsm_positions = run_fsm_baseline(test_panel)
        fsm_results = compute_strategy_returns(fsm_positions, test_panel, config)

        for symbol in symbols:
            symbol_data = fsm_results[fsm_results["symbol"] == symbol]
            metrics = compute_metrics(symbol_data["strategy_return"])
            metrics["fold_id"] = fold_id
            metrics["symbol"] = symbol
            metrics["strategy"] = "fsm"
            all_results.append(metrics)

        print(f"Completed {fold_id}: {len(symbols)*2} baseline results")

    # Save results
    print(f"\n{'='*60}")
    print("Saving baseline results...")
    print(f"{'='*60}")

    results_df = pd.DataFrame(all_results)
    baseline_summary_path = output_dir / "baseline_fold_summary.csv"
    results_df.to_csv(baseline_summary_path, index=False)
    print(f"Saved: {baseline_summary_path}")

    # Aggregate metrics
    agg_metrics = results_df.groupby("strategy").agg({
        "sharpe_ratio": ["mean", "std"],
        "max_drawdown": "mean",
        "win_rate": "mean",
    }).round(4)

    print(f"\nBaseline Aggregate Metrics:")
    print(agg_metrics)

    # Compare with Composite
    composite_summary_path = output_dir / "composite_fold_summary.csv"
    if composite_summary_path.exists():
        composite_df = pd.read_csv(composite_summary_path)

        print(f"\n{'='*60}")
        print("Comparison: Composite vs Baselines")
        print(f"{'='*60}")

        all_strategies = pd.concat([results_df, composite_df], ignore_index=True)
        comparison = all_strategies.groupby("strategy").agg({
            "sharpe_ratio": ["mean", "std", "count"],
            "max_drawdown": "mean",
            "win_rate": "mean",
        }).round(4)

        print(comparison)

        # Save comparison
        comparison_path = output_dir / "baseline_composite_comparison.csv"
        comparison.to_csv(comparison_path)
        print(f"\nSaved comparison: {comparison_path}")

    # Manifest
    manifest = {
        "schema_version": "1.0",
        "phase": "phase4_cn_a_baseline",
        "market": "CN_A",
        "n_folds": len([f for f in folds if f["test_dates"]]),
        "n_results": len(all_results),
        "strategies": ["sm", "fsm"],
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest(),
        "status": "ready",
    }

    manifest_path = output_dir / "baseline_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved: {manifest_path}")

    print(f"\nCN_A baseline comparison completed successfully")


if __name__ == "__main__":
    main()
