"""CN_A Composite-only baseline runner.

Phase 4: Train CN_A Composite weights, run composite_only, compare with baselines.

Usage:
    python model-test/run_cn_a_composite.py --config model-test/configs/composite_cn_a.json
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

from core.composite_cn_a import (
    CNCompositeWeights,
    build_cn_composite_decisions,
    fit_cn_composite_weights,
)
from model_test.cn_a_factor_panel import build_cn_a_factor_panel, validate_panel_quality


def load_config(config_path: Path) -> dict:
    """Load and validate config."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["market", "universe", "output_subdir", "horizon_days"]
    for key in required:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")

    if config["market"] != "CN_A":
        raise ValueError(f"This runner only supports CN_A, got: {config['market']}")

    return config


def create_folds(dates: pd.DatetimeIndex, n_folds: int = 4) -> list[dict]:
    """Create purged walk-forward folds.

    Args:
        dates: All available dates
        n_folds: Number of folds

    Returns:
        List of fold dicts with train/val/test date ranges
    """
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
            # First fold: no train, only test
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


def run_baseline_strategy(
    stock_data: pd.DataFrame,
    strategy_name: str,
    horizon_days: int,
) -> pd.DataFrame:
    """Run a baseline strategy (SM or FSM).

    Args:
        stock_data: OHLCV data
        strategy_name: "sm" or "fsm"
        horizon_days: Prediction horizon

    Returns:
        DataFrame with daily positions and returns
    """
    # Simplified baseline: return mock results
    # In production, would use actual strategy implementation
    n_days = len(stock_data)

    daily_df = pd.DataFrame({
        "date": stock_data.index if isinstance(stock_data.index, pd.DatetimeIndex) else pd.to_datetime(stock_data["date"]),
        "position": np.random.uniform(0, 1, n_days),  # Random positions for mock
        "strategy_return": np.random.randn(n_days) * 0.01,  # Random returns for mock
        "strategy": strategy_name,
    })

    return daily_df


def run_composite_only(
    factor_panel: pd.DataFrame,
    weights: CNCompositeWeights,
    stock_data: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Run composite_only strategy.

    Args:
        factor_panel: Factor panel with all features
        weights: Fitted composite weights
        stock_data: OHLCV data for return calculation
        config: Config dict

    Returns:
        DataFrame with daily positions and returns
    """
    # Build decisions
    decisions = build_cn_composite_decisions(
        factor_panel,
        weights,
        risk_budget=1.0,
        position_method="linear_clip",
    )

    # Convert to DataFrame
    decisions_df = pd.DataFrame([
        {
            "date": d.date,
            "symbol": d.symbol,
            "position": d.final_position,
            "score": d.composite_score,
        }
        for d in decisions
    ])

    # Align with stock data - stock_data is already indexed by date
    stock_data_reset = stock_data.reset_index()

    # Merge decisions with stock data
    merged = decisions_df.merge(stock_data_reset, on="date", how="left")

    # Calculate returns
    merged["return_1d"] = merged["close"].pct_change()
    merged["strategy_return"] = merged["position"].shift(1) * merged["return_1d"]

    # Apply costs
    commission_bps = config["execution"]["commission_bps"]
    slippage_bps = config["execution"]["slippage_bps"]
    total_cost_bps = commission_bps + slippage_bps

    merged["turnover"] = merged["position"].diff().abs()
    merged["transaction_cost"] = merged["turnover"] * (total_cost_bps / 10000.0)
    merged["strategy_return"] = merged["strategy_return"] - merged["transaction_cost"]

    # Keep only relevant columns
    result_cols = ["date", "position", "score", "strategy_return", "turnover"]
    if "symbol" in merged.columns:
        result_cols.insert(1, "symbol")

    return merged[result_cols]


def compute_metrics(daily_returns: pd.Series) -> dict:
    """Compute performance metrics.

    Args:
        daily_returns: Series of daily returns

    Returns:
        Dict of metrics
    """
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
    parser = argparse.ArgumentParser(description="Run CN_A Composite-only baseline")
    parser.add_argument("--config", required=True, help="Path to config JSON")
    args = parser.parse_args()

    config_path = Path(args.config)
    print(f"Loading config: {config_path}")
    config = load_config(config_path)

    # Create output directory
    output_dir = Path("model-test/outputs") / config["output_subdir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Load source data (using admission source)
    source_name = config["universe"]
    source_dir = Path("model-test/outputs") / source_name

    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    print(f"Loading data from: {source_dir}")

    # Check if factor panel exists
    factor_panel_path = output_dir / "cn_a_factor_panel.parquet"

    if factor_panel_path.exists():
        print(f"Loading existing factor panel: {factor_panel_path}")
        factor_panel = pd.read_parquet(factor_panel_path)
    else:
        print("Factor panel not found, please run Phase 3 first")
        print(f"Expected: {factor_panel_path}")
        sys.exit(1)

    print(f"Factor panel loaded: {len(factor_panel)} rows, {len(factor_panel.columns)} columns")

    # Create folds
    all_dates = factor_panel["date"].unique()
    folds = create_folds(pd.DatetimeIndex(all_dates), n_folds=4)
    print(f"Created {len(folds)} folds")

    # Results storage
    all_fold_results = []
    all_weights = []
    all_daily_decisions = []  # Store all daily composite decisions

    # Process each fold
    for fold in folds:
        fold_id = fold["fold_id"]
        print(f"\n{'='*60}")
        print(f"Processing {fold_id}")
        print(f"{'='*60}")

        if not fold["train_dates"]:
            print(f"Skipping {fold_id}: no training data")
            continue

        # Split data
        train_panel = factor_panel[factor_panel["date"].isin(fold["train_dates"])]
        test_panel = factor_panel[factor_panel["date"].isin(fold["test_dates"])]

        print(f"Train: {len(train_panel)} rows, Test: {len(test_panel)} rows")

        # Fit weights on train
        print("Fitting composite weights...")
        # Use all 10 technical factors instead of just 5
        factor_cols = config["factor_panel"]["technical_factors"]  # All 10 factors

        # Compute real 20-day forward returns
        print("Computing 20-day forward returns...")
        train_panel_copy = train_panel.copy()

        # For each symbol, compute forward returns
        def compute_forward_returns(group, horizon=20):
            """Compute forward returns for a symbol."""
            group = group.sort_values("date").copy()
            group["target_return"] = group["close"].pct_change(horizon).shift(-horizon)
            return group

        train_panel_copy = train_panel_copy.groupby("symbol", group_keys=False).apply(
            lambda g: compute_forward_returns(g, horizon=config["horizon_days"])
        )

        # Drop rows with missing target (last horizon days per symbol)
        train_panel_copy = train_panel_copy.dropna(subset=["target_return"])

        print(f"Training samples after forward return computation: {len(train_panel_copy)}")

        weights_dict = fit_cn_composite_weights(
            train_panel_copy,
            train_panel_copy["target_return"],
            factor_cols=factor_cols,
            method="ridge",
            alpha=1.0,
        )

        weights_obj = CNCompositeWeights(
            factors=weights_dict,
            interaction_terms=None,
            fit_method="ridge",
            train_folds=[fold_id],
            market="CN_A",
            position_policy="long_only",
            version="phase4_v1",
        )

        all_weights.append({
            "fold_id": fold_id,
            "weights": weights_dict,
        })

        print(f"Fitted weights: {weights_dict}")

        # Run composite_only on test
        print("Running composite_only on test fold...")

        # Get unique symbols (use all available, not just 5)
        symbols = sorted(test_panel["symbol"].unique())
        max_symbols = 20  # Increase from 5 to 20 for better statistics
        if len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]

        fold_metrics = []

        for symbol in symbols:
            symbol_test = test_panel[test_panel["symbol"] == symbol]

            # Load real stock data from snapshot
            snapshot_dir = Path("model-test/outputs") / config["universe"] / "data_snapshot"
            csv_path = snapshot_dir / f"{symbol}_daily.csv"

            if not csv_path.exists():
                print(f"Warning: No data for {symbol}, skipping")
                continue

            # Load real price data
            stock_df = pd.read_csv(csv_path, parse_dates=["date"])
            stock_df = stock_df.set_index("date").sort_index()
            stock_df.columns = [c.lower() for c in stock_df.columns]

            # Filter to test dates
            test_dates = symbol_test["date"].unique()
            stock_data = stock_df[stock_df.index.isin(pd.DatetimeIndex(test_dates))]

            if len(stock_data) == 0:
                print(f"Warning: No stock data for {symbol} in test period, skipping")
                continue

            # Run composite
            composite_daily = run_composite_only(
                symbol_test,
                weights_obj,
                stock_data,
                config,
            )

            # Add fold_id and symbol to daily decisions
            composite_daily["fold_id"] = fold_id
            composite_daily["symbol"] = symbol
            all_daily_decisions.append(composite_daily)

            # Compute metrics
            metrics = compute_metrics(composite_daily["strategy_return"])
            metrics["fold_id"] = fold_id
            metrics["symbol"] = symbol
            metrics["strategy"] = "composite_only"

            fold_metrics.append(metrics)

        all_fold_results.extend(fold_metrics)
        print(f"Completed {fold_id}: {len(fold_metrics)} symbol results")

    # Save results
    print(f"\n{'='*60}")
    print("Saving results...")
    print(f"{'='*60}")

    # Composite weights by fold
    weights_output = output_dir / "composite_weights_by_fold.json"
    with open(weights_output, "w") as f:
        json.dump(all_weights, f, indent=2)
    print(f"Saved: {weights_output}")

    # Composite daily decisions (for Phase 5 advisory)
    if all_daily_decisions:
        composite_daily_all = pd.concat(all_daily_decisions, ignore_index=True)
        composite_daily_path = output_dir / "composite_daily.parquet"
        composite_daily_all.to_parquet(composite_daily_path, index=False)
        print(f"Saved: {composite_daily_path}")
        print(f"  {len(composite_daily_all)} daily decisions across {composite_daily_all['fold_id'].nunique()} folds")

    # Fold summary
    fold_summary = pd.DataFrame(all_fold_results)
    fold_summary_path = output_dir / "composite_fold_summary.csv"
    fold_summary.to_csv(fold_summary_path, index=False)
    print(f"Saved: {fold_summary_path}")

    # Aggregate metrics
    agg_metrics = fold_summary.groupby("strategy").agg({
        "sharpe_ratio": ["mean", "std"],
        "max_drawdown": "mean",
        "win_rate": "mean",
    }).round(4)

    print(f"\nAggregate Metrics:")
    print(agg_metrics)

    # Manifest
    manifest_output = {
        "schema_version": "1.0",
        "phase": "phase4_cn_a_composite_only",
        "market": "CN_A",
        "n_folds": len(folds),
        "n_results": len(all_fold_results),
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest(),
        "status": "ready",
    }

    manifest_path = output_dir / "composite_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_output, f, indent=2)
    print(f"Saved: {manifest_path}")

    print(f"\nPhase 4 CN_A Composite-only completed successfully")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
