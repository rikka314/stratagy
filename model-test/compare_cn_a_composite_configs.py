"""Compare CN_A Composite with different configurations.

This script compares:
1. Baseline (60 stocks, alpha=1.0)
2. Lower regularization (60 stocks, alpha=0.1)
3. Higher regularization (60 stocks, alpha=10.0)
4. More factors (60 stocks, 10 factors instead of 5)

Usage:
    python model-test/compare_cn_a_composite_configs.py
"""

from __future__ import annotations

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


def load_factor_panel(output_dir: Path) -> pd.DataFrame:
    """Load existing factor panel."""
    panel_path = output_dir / "cn_a_factor_panel.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(f"Factor panel not found: {panel_path}")
    return pd.read_parquet(panel_path)


def create_folds(dates: pd.DatetimeIndex, n_folds: int = 4) -> list[dict]:
    """Create purged walk-forward folds."""
    dates_sorted = sorted(dates)
    total_days = len(dates_sorted)
    fold_size = total_days // n_folds

    folds = []
    for i in range(n_folds):
        test_start_idx = i * fold_size
        test_end_idx = min((i + 1) * fold_size, total_days)

        if i == 0:
            train_dates = []
        else:
            train_end_idx = test_start_idx - 20
            train_dates = dates_sorted[:train_end_idx]

        test_dates = dates_sorted[test_start_idx:test_end_idx]

        fold = {
            "fold_id": f"fold_{i:02d}",
            "train_dates": train_dates,
            "test_dates": test_dates,
        }
        folds.append(fold)

    return folds


def compute_forward_returns(group, horizon=20):
    """Compute forward returns for a symbol."""
    group = group.sort_values("date").copy()
    group["target_return"] = group["close"].pct_change(horizon).shift(-horizon)
    return group


def evaluate_config(
    config_name: str,
    factor_panel: pd.DataFrame,
    folds: list[dict],
    factor_cols: list[str],
    alpha: float,
    method: str = "ridge",
) -> dict:
    """Evaluate a configuration."""
    print(f"\n{'='*60}")
    print(f"Evaluating: {config_name}")
    print(f"  Factors: {len(factor_cols)}")
    print(f"  Alpha: {alpha}")
    print(f"  Method: {method}")
    print(f"{'='*60}")

    results = []

    for fold in folds:
        fold_id = fold["fold_id"]

        if not fold["train_dates"]:
            continue

        # Split data
        train_panel = factor_panel[factor_panel["date"].isin(fold["train_dates"])]
        test_panel = factor_panel[factor_panel["date"].isin(fold["test_dates"])]

        # Compute forward returns
        train_panel_copy = train_panel.copy()
        train_panel_copy = train_panel_copy.groupby("symbol", group_keys=False).apply(
            lambda g: compute_forward_returns(g, horizon=20)
        )
        train_panel_copy = train_panel_copy.dropna(subset=["target_return"])

        # Fit weights
        weights_dict = fit_cn_composite_weights(
            train_panel_copy,
            train_panel_copy["target_return"],
            factor_cols=factor_cols,
            method=method,
            alpha=alpha,
        )

        # Evaluate on test (simplified: just compute score statistics)
        weights_obj = CNCompositeWeights(
            factors=weights_dict,
            interaction_terms=None,
            fit_method=method,
            train_folds=[fold_id],
            market="CN_A",
            position_policy="long_only",
            version=f"{config_name}_v1",
        )

        # Compute scores on test
        decisions = build_cn_composite_decisions(
            test_panel[:1000],  # Sample for speed
            weights_obj,
            risk_budget=1.0,
            position_method="linear_clip",
        )

        scores = [d.composite_score for d in decisions]
        positions = [d.final_position for d in decisions]

        results.append({
            "config": config_name,
            "fold_id": fold_id,
            "n_factors": len(factor_cols),
            "alpha": alpha,
            "method": method,
            "weight_mean": np.mean(list(weights_dict.values())),
            "weight_std": np.std(list(weights_dict.values())),
            "weight_max": np.max(np.abs(list(weights_dict.values()))),
            "score_mean": np.mean(scores),
            "score_std": np.std(scores),
            "position_mean": np.mean(positions),
            "position_std": np.std(positions),
        })

        print(f"{fold_id}: weight_max={results[-1]['weight_max']:.4f}, score_std={results[-1]['score_std']:.6f}")

    return results


def main():
    print("Loading factor panel...")
    output_dir = Path("model-test/outputs/composite_cn_a")
    factor_panel = load_factor_panel(output_dir)

    print(f"Factor panel: {len(factor_panel)} rows")

    # Create folds
    all_dates = factor_panel["date"].unique()
    folds = create_folds(pd.DatetimeIndex(all_dates), n_folds=4)

    # Define configurations to test
    all_results = []

    # Config 1: Baseline (current best)
    results = evaluate_config(
        "baseline_60stocks_5factors_alpha1",
        factor_panel,
        folds,
        factor_cols=["mom_short_z", "mom_long_z", "macd_z", "rsi_z", "bb_position_rank"],
        alpha=1.0,
    )
    all_results.extend(results)

    # Config 2: Lower regularization
    results = evaluate_config(
        "lower_reg_60stocks_5factors_alpha0.1",
        factor_panel,
        folds,
        factor_cols=["mom_short_z", "mom_long_z", "macd_z", "rsi_z", "bb_position_rank"],
        alpha=0.1,
    )
    all_results.extend(results)

    # Config 3: Higher regularization
    results = evaluate_config(
        "higher_reg_60stocks_5factors_alpha10",
        factor_panel,
        folds,
        factor_cols=["mom_short_z", "mom_long_z", "macd_z", "rsi_z", "bb_position_rank"],
        alpha=10.0,
    )
    all_results.extend(results)

    # Config 4: More factors
    results = evaluate_config(
        "more_factors_60stocks_10factors_alpha1",
        factor_panel,
        folds,
        factor_cols=[
            "mom_short_z", "mom_long_z", "macd_z", "rsi_z", "bb_position_rank",
            "price_position_rank", "vol_z", "drawdown_rank", "obv_trend_rank", "volume_ratio_rank"
        ],
        alpha=1.0,
    )
    all_results.extend(results)

    # Save results
    results_df = pd.DataFrame(all_results)
    output_path = output_dir / "config_comparison.csv"
    results_df.to_csv(output_path, index=False)
    print(f"\nSaved results to: {output_path}")

    # Summary
    print(f"\n{'='*60}")
    print("Configuration Comparison Summary")
    print(f"{'='*60}")

    summary = results_df.groupby("config").agg({
        "weight_max": "mean",
        "score_std": "mean",
        "position_std": "mean",
    }).round(4)

    print(summary)

    # Recommendation
    print(f"\n{'='*60}")
    print("Recommendation:")
    print(f"{'='*60}")

    best_config = summary.sort_values("score_std", ascending=False).index[0]
    print(f"Best config (highest score variance): {best_config}")
    print(f"\nHigher score_std means better differentiation between stocks.")
    print(f"This is a proxy for better stock selection ability.")


if __name__ == "__main__":
    main()
