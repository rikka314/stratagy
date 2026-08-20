"""Run Phase 1 baseline experiments for Transformer State v3.

This script runs B01 (PCA single-day), B02 (PCA summary), and B03 (random)
baselines on all walk-forward folds and generates a comparison report.

Usage:
    python model-test/run_baseline_phase1.py --config model-test/configs/transformer_state_v3_us.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add model-test to path
sys.path.insert(0, str(Path(__file__).parent))

from model_test.transformer_state_baseline import (
    BaselineConfig,
    BaselineResult,
    compare_baselines,
    run_baseline_experiment,
    save_baseline_artifacts,
)
from model_test.transformer_state_panel import (
    load_transformer_state_panel,
    load_walk_forward_splits,
)


def load_config(config_path: Path) -> dict:
    """Load v3 configuration."""
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_fold_baseline(
    config: BaselineConfig,
    panel: pd.DataFrame,
    feature_columns: list[str],
    split_row: pd.Series,
    output_dir: Path,
) -> BaselineResult:
    """Run baseline for a single fold.

    Args:
        config: Baseline configuration
        panel: Full state sequence panel
        feature_columns: Ordered feature names
        split_row: Row from walk_forward_splits with train/val indices
        output_dir: Output directory for this fold

    Returns:
        BaselineResult
    """
    fold_id = split_row["split_id"]
    train_start = split_row["train_start_idx"]
    train_end = split_row["train_end_idx"]
    val_start = split_row["validation_start_idx"]
    val_end = split_row["validation_end_idx"]

    print(f"  Fold {fold_id}: Train [{train_start}:{train_end}], Val [{val_start}:{val_end}]")

    panel_train = panel.iloc[train_start:train_end].copy()
    panel_val = panel.iloc[val_start:val_end].copy()

    print(f"    Train samples: {len(panel_train)}, Val samples: {len(panel_val)}")

    result = run_baseline_experiment(
        config=config,
        panel_train=panel_train,
        panel_query=panel_val,
        feature_columns=feature_columns,
        fold_id=fold_id,
    )

    # Save artifacts
    fold_output_dir = output_dir / fold_id
    saved_files = save_baseline_artifacts(result, fold_output_dir)
    print(f"    Saved artifacts to {fold_output_dir}")
    print(f"    Neighbor utility: {result.neighbor_utility_stats['mean_neighbor_utility']:.6f} "
          f"± {result.neighbor_utility_stats['std_neighbor_utility']:.6f}")
    print(f"    Utility consistency: {result.neighbor_utility_stats['utility_consistency']:.6f}")

    return result


def run_all_baselines(
    v3_config: dict,
    panel: pd.DataFrame,
    feature_columns: list[str],
    splits: pd.DataFrame,
    output_base_dir: Path,
) -> dict[str, list[BaselineResult]]:
    """Run all three baselines on all folds.

    Returns:
        Dictionary mapping method name to list of fold results
    """
    baseline_configs = {
        "pca_single_day": BaselineConfig(
            method="pca_single_day",
            top_k=v3_config.get("retrieval", {}).get("top_k", 15),
            pca_variance_threshold=v3_config.get("baseline", {}).get("pca_variance_threshold", 0.95),
            random_seed=v3_config.get("random_seed", 42),
        ),
        "pca_summary_20d": BaselineConfig(
            method="pca_summary_20d",
            top_k=v3_config.get("retrieval", {}).get("top_k", 15),
            pca_variance_threshold=v3_config.get("baseline", ).get("pca_variance_threshold", 0.95),
            random_seed=v3_config.get("random_seed", 42),
        ),
        "random_neighbor": BaselineConfig(
            method="random_neighbor",
            top_k=v3_config.get("retrieval", {}).get("top_k", 15),
            random_seed=v3_config.get("random_seed", 42),
        ),
    }

    all_results = {}

    for method_name, config in baseline_configs.items():
        print(f"\n{'='*60}")
        print(f"Running baseline: {method_name.upper()}")
        print(f"{'='*60}")

        method_results = []
        output_dir = output_base_dir / method_name

        for _, split_row in splits.iterrows():
            result = run_fold_baseline(
                config=config,
                panel=panel,
                feature_columns=feature_columns,
                split_row=split_row,
                output_dir=output_dir,
            )
            method_results.append(result)

        all_results[method_name] = method_results

    return all_results


def generate_comparison_report(
    all_results: dict[str, list[BaselineResult]],
    output_dir: Path,
) -> None:
    """Generate baseline comparison report.

    Args:
        all_results: Dictionary of method -> list of fold results
        output_dir: Output directory for report
    """
    print(f"\n{'='*60}")
    print("GENERATING COMPARISON REPORT")
    print(f"{'='*60}")

    # Flatten all results
    all_baseline_results = []
    for method_results in all_results.values():
        all_baseline_results.extend(method_results)

    # Generate comparison DataFrame
    comparison_df = compare_baselines(all_baseline_results)

    # Save comparison CSV
    comparison_path = output_dir / "baseline_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False)
    print(f"\nSaved comparison to {comparison_path}")

    # Compute summary statistics by method
    summary_stats = comparison_df.groupby("method").agg({
        "mean_neighbor_utility": ["mean", "std"],
        "utility_consistency": ["mean", "std"],
        "mean_similarity": ["mean", "std"],
    })

    print("\n" + "="*60)
    print("BASELINE SUMMARY STATISTICS")
    print("="*60)
    print(summary_stats.to_string())

    # Generate markdown report
    report_lines = [
        "# Transformer State v3 - Phase 1 Baseline Comparison",
        f"\n**Generated:** {datetime.now().isoformat()}",
        "\n## Summary Statistics\n",
        "| Method | Mean Utility | Utility Consistency | Mean Similarity |",
        "|--------|--------------|---------------------|-----------------|",
    ]

    for method in ["pca_single_day", "pca_summary_20d", "random_neighbor"]:
        method_data = comparison_df[comparison_df["method"] == method]
        if not method_data.empty:
            mean_util = method_data["mean_neighbor_utility"].mean()
            util_std = method_data["mean_neighbor_utility"].std()
            consistency = method_data["utility_consistency"].mean()
            consistency_std = method_data["utility_consistency"].std()
            similarity = method_data["mean_similarity"].mean()

            report_lines.append(
                f"| **{method}** | {mean_util:.6f} ± {util_std:.6f} | "
                f"{consistency:.6f} ± {consistency_std:.6f} | {similarity:.4f} |"
            )

    report_lines.extend([
        "\n## Interpretation\n",
        "- **Mean Utility**: Average 5-day future utility of retrieved neighbors (higher is better)",
        "- **Utility Consistency**: Negative std of neighbor utilities (higher = more consistent)",
        "- **Mean Similarity**: Average cosine similarity to neighbors (PCA only)",
        "\n## Per-Fold Results\n",
    ])

    for method in ["pca_single_day", "pca_summary_20d", "random_neighbor"]:
        method_data = comparison_df[comparison_df["method"] == method]
        if not method_data.empty:
            report_lines.append(f"\n### {method.upper()}\n")
            report_lines.append(method_data.to_markdown(index=False))

    report_lines.extend([
        "\n## Decision Criteria\n",
        "### ✅ Continue to Transformer Development IF:\n",
        "- B01 OR B02 utility consistency > B03 (p < 0.05, bootstrap test)",
        "- Bootstrap 95% CI does not include zero improvement",
        "- Evidence that state similarity retrieval is better than random",
        "\n### ⚠️ Downgrade to PCA Baseline IF:",
        "- PCA (B01/B02) is effective BUT Transformer shows <10% improvement",
        "- PCA is simpler and sufficient for production",
        "\n### 🛑 STOP Research IF:",
        "- Neither B01 nor B02 outperforms B03 (random)",
        "- No evidence that state similarity helps",
        "- Re-evaluate the core product hypothesis",
    ])

    report_md = "\n".join(report_lines)
    report_path = output_dir / "baseline_comparison_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\nSaved markdown report to {report_path}")

    # Statistical test: PCA vs Random
    print("\n" + "="*60)
    print("STATISTICAL COMPARISON: PCA vs RANDOM")
    print("="*60)

    random_utility = comparison_df[comparison_df["method"] == "random_neighbor"]["mean_neighbor_utility"].values
    pca_single_utility = comparison_df[comparison_df["method"] == "pca_single_day"]["mean_neighbor_utility"].values
    pca_summary_utility = comparison_df[comparison_df["method"] == "pca_summary_20d"]["mean_neighbor_utility"].values

    if len(random_utility) > 0 and len(pca_single_utility) > 0:
        diff_single = pca_single_utility.mean() - random_utility.mean()
        print(f"\nPCA Single Day vs Random:")
        print(f"  Difference: {diff_single:.6f}")
        print(f"  PCA Single: {pca_single_utility.mean():.6f} ± {pca_single_utility.std():.6f}")
        print(f"  Random:     {random_utility.mean():.6f} ± {random_utility.std():.6f}")

    if len(random_utility) > 0 and len(pca_summary_utility) > 0:
        diff_summary = pca_summary_utility.mean() - random_utility.mean()
        print(f"\nPCA Summary vs Random:")
        print(f"  Difference: {diff_summary:.6f}")
        print(f"  PCA Summary: {pca_summary_utility.mean():.6f} ± {pca_summary_utility.std():.6f}")
        print(f"  Random:      {random_utility.mean():.6f} ± {random_utility.std():.6f}")

    # Save full report JSON
    report_json = {
        "generated_at": datetime.now().isoformat(),
        "comparison_table": comparison_df.to_dict(orient="records"),
        "summary_statistics": summary_stats.to_dict(),
    }

    report_json_path = output_dir / "baseline_comparison_report.json"
    with report_json_path.open("w", encoding="utf-8") as f:
        json.dump(report_json, f, indent=2, ensure_ascii=False)
    print(f"\nSaved JSON report to {report_json_path}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run Phase 1 baseline experiments")
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to v3 config JSON (e.g., transformer_state_v3_us.json)",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(1)

    print("="*60)
    print("TRANSFORMER STATE V3 - PHASE 1 BASELINE EXPERIMENTS")
    print("="*60)
    print(f"Config: {args.config}")

    # Load configuration
    v3_config = load_config(args.config)
    output_subdir = v3_config.get("output_subdir", "transformer_state_v3_us")
    output_base_dir = Path("model-test/outputs") / output_subdir / "baseline_artifacts"

    print(f"Output directory: {output_base_dir}")

    # Load panel and splits
    print("\nLoading state panel and splits...")
    source_output_dir = Path(v3_config["sources"]["phase_b_output_dir"])

    try:
        panel_data = load_transformer_state_panel(source_output_dir)
        panel = panel_data["sequence_panel"]
        feature_schema = panel_data["feature_schema"]
        feature_columns = feature_schema.get("feature_columns", [])

        splits = load_walk_forward_splits(source_output_dir)

        print(f"  Loaded {len(panel)} sequences")
        print(f"  Feature columns: {len(feature_columns)}")
        print(f"  Walk-forward folds: {len(splits)}")

    except Exception as e:
        print(f"\nERROR loading panel: {e}")
        print("\nMake sure Phase-B artifacts exist at:")
        print(f"  {source_output_dir}")
        sys.exit(1)

    # Run all baselines
    all_results = run_all_baselines(
        v3_config=v3_config,
        panel=panel,
        feature_columns=feature_columns,
        splits=splits,
        output_base_dir=output_base_dir,
    )

    # Generate comparison report
    generate_comparison_report(all_results, output_base_dir)

    print("\n" + "="*60)
    print("✅ PHASE 1 BASELINE EXPERIMENTS COMPLETE")
    print("="*60)
    print(f"\nNext steps:")
    print(f"  1. Review: {output_base_dir / 'baseline_comparison_report.md'}")
    print(f"  2. Decision: Continue to Transformer / Downgrade to PCA / Stop research")
    print(f"  3. If continuing: Proceed to Phase 2 (Label reconstruction)")


if __name__ == "__main__":
    main()
