"""Run Phase 1 baseline experiments for Transformer State v3.

This script runs B01 (PCA single-day), B02 (PCA summary), and B03 (random)
baselines on all walk-forward folds and generates a comparison report.

Usage:
    python model-test/run_baseline_phase1.py --config model-test/configs/transformer_state_v3_us.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    FEATURE_SCHEMA_NAME,
    PANEL_MANIFEST_NAME,
    SEQUENCE_PANEL_NAME,
    SPLITS_NAME,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(value: str, *, field_name: str) -> Path:
    path = Path(value)
    resolved = (REPO_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise ValueError(f"{field_name} escapes the repository: {resolved}")
    return resolved


def _verify_manifest_artifact(
    source_dir: Path,
    manifest: dict[str, Any],
    artifact_key: str,
    expected_name: str,
) -> Path:
    descriptor = (manifest.get("artifacts") or {}).get(artifact_key)
    if not isinstance(descriptor, dict) or descriptor.get("path") != expected_name:
        raise ValueError(f"panel manifest lacks fixed artifact {artifact_key}")
    path = (source_dir / expected_name).resolve()
    if not path.is_relative_to(source_dir.resolve()) or not path.is_file():
        raise ValueError(f"panel artifact is missing: {path}")
    if _sha256_file(path) != str(descriptor.get("sha256") or ""):
        raise ValueError(f"panel artifact hash drifted: {path}")
    return path


def load_baseline_inputs(
    v3_config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any], Path]:
    """Load and hash-verify the immutable v2 panel used by Phase 1."""

    baseline_config = v3_config.get("baseline") or {}
    source_value = baseline_config.get("source_panel_output_dir")
    if not source_value:
        raise ValueError("baseline.source_panel_output_dir is required")
    source_dir = _resolve_repo_path(
        str(source_value), field_name="baseline.source_panel_output_dir"
    )
    manifest_path = source_dir / PANEL_MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"panel manifest is missing: {manifest_path}")
    expected_manifest_hash = str(baseline_config.get("source_panel_manifest_sha256") or "")
    actual_manifest_hash = _sha256_file(manifest_path)
    if expected_manifest_hash and actual_manifest_hash != expected_manifest_hash:
        raise ValueError("frozen source panel manifest hash drifted")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "ready" or manifest.get("market") != v3_config.get("market"):
        raise ValueError("source panel manifest is not ready for the configured market")

    sequence_path = _verify_manifest_artifact(
        source_dir, manifest, "state_sequence_panel", SEQUENCE_PANEL_NAME
    )
    schema_path = _verify_manifest_artifact(
        source_dir, manifest, "feature_schema", FEATURE_SCHEMA_NAME
    )
    splits_path = _verify_manifest_artifact(
        source_dir, manifest, "walk_forward_splits", SPLITS_NAME
    )
    panel = pd.read_parquet(sequence_path)
    feature_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    splits = pd.read_csv(splits_path)

    required_panel = {
        "sequence_end_date",
        "sequence_values",
        "expert_utilities_json",
        "split_memberships_json",
        "symbol",
        "market",
    }
    missing_panel = required_panel - set(panel.columns)
    if missing_panel:
        raise ValueError(f"source sequence panel is missing columns: {sorted(missing_panel)}")
    if not feature_schema.get("feature_columns"):
        raise ValueError("source feature schema has no feature_columns")
    if not set(panel["market"].astype(str)) == {str(v3_config.get("market"))}:
        raise ValueError("source sequence panel market does not match v3 config")
    return panel, feature_schema, splits, manifest, manifest_path


def _membership_mask(panel: pd.DataFrame, split_id: str, role: str) -> np.ndarray:
    values: list[bool] = []
    for raw in panel["split_memberships_json"].fillna("[]"):
        try:
            memberships = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError("split_memberships_json is invalid") from exc
        values.append(
            any(
                str(item.get("split_id")) == split_id and str(item.get("role")) == role
                for item in memberships
            )
        )
    return np.asarray(values, dtype=bool)


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
        split_row: Row from walk_forward_splits with train/validation bounds
        output_dir: Output directory for this fold

    Returns:
        BaselineResult
    """
    fold_id = split_row["split_id"]
    train_mask = _membership_mask(panel, str(fold_id), "train")
    validation_mask = _membership_mask(panel, str(fold_id), "validation")
    panel_train = panel.loc[train_mask].reset_index(drop=True)
    panel_val = panel.loc[validation_mask].reset_index(drop=True)
    if panel_train.empty or panel_val.empty:
        raise ValueError(f"fold {fold_id} has empty train or validation membership")
    train_max = pd.Timestamp(panel_train["sequence_end_date"].max())
    validation_min = pd.Timestamp(panel_val["sequence_end_date"].min())
    if train_max >= validation_min:
        raise ValueError(f"fold {fold_id} violates strictly-prior memory isolation")
    split_signature = "|".join(
        str(split_row[column])
        for column in ("train_start", "train_end", "validation_start", "validation_end")
    )

    print(
        f"  Fold {fold_id}: Train through {train_max.date()}, "
        f"Validation from {validation_min.date()}"
    )

    print(f"    Train samples: {len(panel_train)}, Val samples: {len(panel_val)}")

    result = run_baseline_experiment(
        config=config,
        panel_train=panel_train,
        panel_query=panel_val,
        feature_columns=feature_columns,
        fold_id=fold_id,
    )
    result.query_metrics.insert(0, "fold_id", str(fold_id))
    result.query_metrics.insert(1, "split_signature", split_signature)

    # Save artifacts
    fold_output_dir = output_dir / fold_id
    save_baseline_artifacts(result, fold_output_dir)
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
    expert_ids = tuple(v3_config.get("experts") or ())
    baseline_configs = {
        "pca_single_day": BaselineConfig(
            method="pca_single_day",
            top_k=v3_config.get("retrieval", {}).get("top_k", 15),
            pca_variance_threshold=v3_config.get("baseline", {}).get("pca_variance_threshold", 0.95),
            random_seed=v3_config.get("random_seed", 42),
            expert_ids=expert_ids,
        ),
        "pca_summary_20d": BaselineConfig(
            method="pca_summary_20d",
            top_k=v3_config.get("retrieval", {}).get("top_k", 15),
            pca_variance_threshold=v3_config.get("baseline", {}).get("pca_variance_threshold", 0.95),
            random_seed=v3_config.get("random_seed", 42),
            expert_ids=expert_ids,
        ),
        "random_neighbor": BaselineConfig(
            method="random_neighbor",
            top_k=v3_config.get("retrieval", {}).get("top_k", 15),
            random_seed=v3_config.get("random_seed", 42),
            expert_ids=expert_ids,
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


def _paired_date_bootstrap(
    method_metrics: pd.DataFrame,
    random_metrics: pd.DataFrame,
    *,
    metric: str,
    iterations: int,
    random_seed: int,
) -> dict[str, float | int]:
    """Run a paired one-sided cluster bootstrap over validation dates."""

    join_keys = ["split_signature", "query_date", "symbol"]
    left = method_metrics[join_keys + [metric]].rename(columns={metric: "method_value"})
    right = random_metrics[join_keys + [metric]].rename(columns={metric: "random_value"})
    paired = left.merge(right, on=join_keys, how="inner", validate="one_to_one")
    if paired.empty or len(paired) != len(left) or len(paired) != len(right):
        raise ValueError(f"paired bootstrap alignment failed for {metric}")

    paired["cluster"] = (
        paired["split_signature"].astype(str)
        + "|"
        + pd.to_datetime(paired["query_date"]).dt.strftime("%Y-%m-%d")
    )
    cluster_differences = (
        paired.assign(difference=paired["method_value"] - paired["random_value"])
        .groupby("cluster", sort=True)["difference"]
        .mean()
        .to_numpy(dtype=float)
    )
    if len(cluster_differences) < 2:
        raise ValueError("paired bootstrap requires at least two validation-date clusters")

    rng = np.random.default_rng(random_seed)
    draws = np.empty(iterations, dtype=float)
    for index in range(iterations):
        sampled = rng.choice(cluster_differences, size=len(cluster_differences), replace=True)
        draws[index] = float(sampled.mean())

    observed = float(cluster_differences.mean())
    ci_lower, ci_upper = np.quantile(draws, [0.025, 0.975])
    one_sided_p = float((1 + np.count_nonzero(draws <= 0.0)) / (iterations + 1))
    return {
        "metric": metric,
        "observed_difference": observed,
        "ci_95_lower": float(ci_lower),
        "ci_95_upper": float(ci_upper),
        "one_sided_p_value": one_sided_p,
        "bootstrap_iterations": int(iterations),
        "date_clusters": int(len(cluster_differences)),
        "paired_queries": int(len(paired)),
    }


def _statistical_comparisons(
    all_results: dict[str, list[BaselineResult]],
    *,
    random_seed: int,
    iterations: int = 1000,
) -> pd.DataFrame:
    """Compare each PCA baseline with B03 without duplicating identical folds."""

    query_metrics = {
        method: pd.concat([result.query_metrics for result in results], ignore_index=True)
        for method, results in all_results.items()
    }
    dedupe_keys = ["split_signature", "query_date", "symbol"]
    query_metrics = {
        method: frame.drop_duplicates(dedupe_keys, keep="first").reset_index(drop=True)
        for method, frame in query_metrics.items()
    }
    random_metrics = query_metrics["random_neighbor"]
    rows: list[dict[str, Any]] = []
    for offset, method in enumerate(("pca_single_day", "pca_summary_20d")):
        for metric in ("utility_consistency", "query_selected_utility"):
            comparison = _paired_date_bootstrap(
                query_metrics[method],
                random_metrics,
                metric=metric,
                iterations=iterations,
                random_seed=random_seed + offset,
            )
            comparison["method"] = method
            comparison["reference"] = "random_neighbor"
            rows.append(comparison)
    return pd.DataFrame(rows)


def generate_comparison_report(
    all_results: dict[str, list[BaselineResult]],
    output_dir: Path,
    *,
    random_seed: int,
) -> dict[str, Any]:
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

    statistical_df = _statistical_comparisons(
        all_results, random_seed=random_seed, iterations=1000
    )
    statistical_path = output_dir / "baseline_statistical_tests.csv"
    statistical_df.to_csv(statistical_path, index=False)
    print(f"Saved statistical tests to {statistical_path}")

    consistency_tests = statistical_df[
        statistical_df["metric"] == "utility_consistency"
    ].copy()
    passing_methods = consistency_tests.loc[
        (consistency_tests["observed_difference"] > 0.0)
        & (consistency_tests["ci_95_lower"] > 0.0)
        & (consistency_tests["one_sided_p_value"] < 0.05),
        "method",
    ].tolist()
    decision = {
        "status": "continue_transformer" if passing_methods else "stop_and_reassess",
        "passing_methods": passing_methods,
        "criterion": (
            "utility_consistency improvement vs random has one-sided p < 0.05 "
            "and bootstrap 95% CI lower bound > 0"
        ),
        "bootstrap_unit": "unique split signature x validation date",
    }

    # Compute summary statistics by method
    summary_stats = comparison_df.groupby("method").agg({
        "mean_neighbor_utility": ["mean", "std"],
        "utility_consistency": ["mean", "std"],
        "mean_similarity": ["mean", "std"],
        "mean_query_selected_utility": ["mean", "std"],
        "mean_regret": ["mean", "std"],
    })

    print("\n" + "="*60)
    print("BASELINE SUMMARY STATISTICS")
    print("="*60)
    print(summary_stats.to_string())

    # Generate markdown report
    report_lines = [
        "# Transformer State v3 - Phase 1 Baseline Comparison",
        f"\n**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "\n## Summary Statistics\n",
        "| Method | Neighbor Utility | Utility Consistency | Query Utility | Regret | Mean Similarity |",
        "|--------|------------------|---------------------|---------------|--------|-----------------|",
    ]

    for method in ["pca_single_day", "pca_summary_20d", "random_neighbor"]:
        method_data = comparison_df[comparison_df["method"] == method]
        if not method_data.empty:
            mean_util = method_data["mean_neighbor_utility"].mean()
            util_std = method_data["mean_neighbor_utility"].std()
            consistency = method_data["utility_consistency"].mean()
            consistency_std = method_data["utility_consistency"].std()
            query_utility = method_data["mean_query_selected_utility"].mean()
            regret = method_data["mean_regret"].mean()
            similarity = method_data["mean_similarity"].mean()

            report_lines.append(
                f"| **{method}** | {mean_util:.6f} ± {util_std:.6f} | "
                f"{consistency:.6f} ± {consistency_std:.6f} | "
                f"{query_utility:.6f} | {regret:.6f} | {similarity:.4f} |"
            )

    report_lines.extend([
        "\n## Interpretation\n",
        "- **Neighbor Utility**: Utility predicted by the retrieved neighbors for their selected expert",
        "- **Utility Consistency**: Negative mean dispersion across the complete 8-expert utility vector (higher is more consistent)",
        "- **Query Utility**: Realized source-net utility on the Validation query for the neighbor-selected expert",
        "- **Regret**: Query oracle utility minus selected-expert query utility (lower is better)",
        "- **Mean Similarity**: Average cosine similarity to neighbors (PCA only)",
        "\n## Paired Date-Cluster Bootstrap (1,000 iterations)\n",
        statistical_df.to_markdown(index=False),
        "\nDuplicate fold definitions are de-duplicated by their train/validation signature before bootstrap.",
        "\n## Phase 1 Decision\n",
        f"- **Status:** `{decision['status']}`",
        f"- **Passing methods:** {', '.join(passing_methods) if passing_methods else 'none'}",
        f"- **Criterion:** {decision['criterion']}",
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
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_table": comparison_df.to_dict(orient="records"),
        "summary_statistics": {
            str(method): {
                "mean_neighbor_utility": float(group["mean_neighbor_utility"].mean()),
                "utility_consistency": float(group["utility_consistency"].mean()),
                "mean_query_selected_utility": float(
                    group["mean_query_selected_utility"].mean()
                ),
                "mean_regret": float(group["mean_regret"].mean()),
                "mean_similarity": float(group["mean_similarity"].mean()),
            }
            for method, group in comparison_df.groupby("method")
        },
        "statistical_tests": statistical_df.to_dict(orient="records"),
        "decision": decision,
    }

    report_json_path = output_dir / "baseline_comparison_report.json"
    with report_json_path.open("w", encoding="utf-8") as f:
        json.dump(report_json, f, indent=2, ensure_ascii=False)
    print(f"\nSaved JSON report to {report_json_path}")
    return decision


def _write_evidence_manifest(
    *,
    config_path: Path,
    source_manifest_path: Path,
    output_dir: Path,
    decision: dict[str, Any],
) -> Path:
    """Seal the Phase 1 run inputs, implementation, outputs, and decision."""

    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    implementation_paths = [
        Path(__file__).resolve(),
        REPO_ROOT / "model-test" / "model_test" / "transformer_state_baseline.py",
    ]
    manifest_path = output_dir / "baseline_evidence_manifest.json"
    artifacts = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path != manifest_path:
            artifacts[str(path.relative_to(output_dir)).replace("\\", "/")] = {
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
    manifest = {
        "schema_version": "3.0.0-phase1",
        "status": "experiment_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head,
        "config": {
            "path": str(config_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": _sha256_file(config_path),
        },
        "source_panel_manifest": {
            "path": str(source_manifest_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": _sha256_file(source_manifest_path),
        },
        "implementation": {
            str(path.relative_to(REPO_ROOT)).replace("\\", "/"): _sha256_file(path)
            for path in implementation_paths
        },
        "decision": decision,
        "artifacts": artifacts,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest_path


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
    config_path = args.config.resolve()
    v3_config = load_config(config_path)
    output_subdir = v3_config.get("output_subdir", "transformer_state_v3_us")
    output_base_dir = REPO_ROOT / "model-test" / "outputs" / output_subdir / "baseline_artifacts"

    print(f"Output directory: {output_base_dir}")

    # Load panel and splits
    print("\nLoading state panel and splits...")
    try:
        panel, feature_schema, splits, _, source_manifest_path = load_baseline_inputs(
            v3_config
        )
        feature_columns = feature_schema.get("feature_columns", [])

        print(f"  Loaded {len(panel)} sequences")
        print(f"  Feature columns: {len(feature_columns)}")
        print(f"  Walk-forward folds: {len(splits)}")

    except Exception as e:
        print(f"\nERROR loading panel: {e}")
        print("\nCheck baseline.source_panel_output_dir and its frozen manifest hash.")
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
    decision = generate_comparison_report(
        all_results,
        output_base_dir,
        random_seed=int(v3_config.get("random_seed", 42)),
    )
    evidence_path = _write_evidence_manifest(
        config_path=config_path,
        source_manifest_path=source_manifest_path,
        output_dir=output_base_dir,
        decision=decision,
    )

    print("\n" + "="*60)
    print("✅ PHASE 1 BASELINE EXPERIMENTS COMPLETE")
    print("="*60)
    print(f"\nNext steps:")
    print(f"  1. Review: {output_base_dir / 'baseline_comparison_report.md'}")
    print(f"  2. Evidence: {evidence_path}")
    print(f"  3. Decision: {decision['status']}")


if __name__ == "__main__":
    main()
