"""Phase 2 diagnostic for Transformer State v3.

This module analyzes Phase 1 baseline results to diagnose why neighbor
consistency improved but query utility degraded. The diagnostic includes:
- Multi-expert decomposition (which experts drove the patterns)
- Sampling bias analysis (stride=1 clustering effects)
- Decision recommendation (continue/stop/refactor)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class DiagnosticError(ValueError):
    """Raised when diagnostic inputs are invalid."""


@dataclass(frozen=True)
class DiagnosticConfig:
    """Configuration for Phase 2 diagnostic."""

    baseline_output_dir: Path
    source_panel_path: Path
    expert_ids: tuple[str, ...]
    top_k: int = 15
    min_neighbor_support: int = 5

    def __post_init__(self) -> None:
        if not self.baseline_output_dir.exists():
            raise DiagnosticError(
                f"Baseline output not found: {self.baseline_output_dir}"
            )
        if not self.source_panel_path.exists():
            raise DiagnosticError(f"Source panel not found: {self.source_panel_path}")
        if len(self.expert_ids) < 2:
            raise DiagnosticError("At least 2 experts required")


@dataclass(frozen=True)
class ExpertDecomposition:
    """Per-expert decomposition of neighbor utility patterns."""

    expert_id: str
    method: str
    fold_id: str
    neighbor_utility_mean: float
    neighbor_utility_std: float
    query_selected_utility_mean: float
    query_oracle_utility_mean: float
    regret: float
    availability_rate: float
    consistency_relative_to_random: float
    utility_relative_to_random: float


@dataclass(frozen=True)
class SamplingBiasAnalysis:
    """Analysis of temporal clustering in Train memory."""

    method: str
    fold_id: str
    n_train_rows: int
    n_unique_dates: int
    rows_per_date_mean: float
    rows_per_date_std: float
    rows_per_date_max: int
    consecutive_day_clusters: int
    max_consecutive_days: int
    date_coverage_span_days: int
    temporal_concentration_entropy: float


@dataclass(frozen=True)
class DiagnosticResult:
    """Complete Phase 2 diagnostic result."""

    expert_decompositions: list[ExpertDecomposition]
    sampling_bias_analyses: list[SamplingBiasAnalysis]
    decision_recommendation: str  # "continue", "stop", or "refactor"
    decision_rationale: str
    summary_stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "expert_decompositions": [
                {
                    "expert_id": ed.expert_id,
                    "method": ed.method,
                    "fold_id": ed.fold_id,
                    "neighbor_utility_mean": ed.neighbor_utility_mean,
                    "neighbor_utility_std": ed.neighbor_utility_std,
                    "query_selected_utility_mean": ed.query_selected_utility_mean,
                    "query_oracle_utility_mean": ed.query_oracle_utility_mean,
                    "regret": ed.regret,
                    "availability_rate": ed.availability_rate,
                    "consistency_relative_to_random": ed.consistency_relative_to_random,
                    "utility_relative_to_random": ed.utility_relative_to_random,
                }
                for ed in self.expert_decompositions
            ],
            "sampling_bias_analyses": [
                {
                    "method": sba.method,
                    "fold_id": sba.fold_id,
                    "n_train_rows": sba.n_train_rows,
                    "n_unique_dates": sba.n_unique_dates,
                    "rows_per_date_mean": sba.rows_per_date_mean,
                    "rows_per_date_std": sba.rows_per_date_std,
                    "rows_per_date_max": sba.rows_per_date_max,
                    "consecutive_day_clusters": sba.consecutive_day_clusters,
                    "max_consecutive_days": sba.max_consecutive_days,
                    "date_coverage_span_days": sba.date_coverage_span_days,
                    "temporal_concentration_entropy": sba.temporal_concentration_entropy,
                }
                for sba in self.sampling_bias_analyses
            ],
            "decision_recommendation": self.decision_recommendation,
            "decision_rationale": self.decision_rationale,
            "summary_stats": self.summary_stats,
        }


def _load_neighbors_and_panel(
    method_dir: Path, fold_id: str, panel: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load neighbor results and join with panel utilities."""
    fold_dir = method_dir / fold_id
    neighbors_path = fold_dir / "neighbors.parquet"
    if not neighbors_path.exists():
        raise DiagnosticError(f"Neighbors file not found: {neighbors_path}")

    neighbors = pd.read_parquet(neighbors_path)

    # Join with panel to get expert utilities
    neighbors = neighbors.merge(
        panel[["date", "symbol", "expert_utilities_json"]],
        left_on="train_idx",
        right_index=True,
        how="left",
    )

    query_panel = panel.iloc[neighbors["query_idx"].unique()]

    return neighbors, query_panel


def _decompose_expert_utilities(
    neighbors: pd.DataFrame,
    query_panel: pd.DataFrame,
    expert_ids: tuple[str, ...],
    method: str,
    fold_id: str,
    random_baseline: dict[str, float],
) -> list[ExpertDecomposition]:
    """Decompose neighbor utility patterns by expert."""
    decompositions = []

    for expert_id in expert_ids:
        # Extract expert utilities from JSON
        neighbor_utilities = []
        query_selected_utilities = []
        query_oracle_utilities = []
        available_count = 0

        for query_idx in query_panel.index:
            query_experts = json.loads(query_panel.loc[query_idx, "expert_utilities_json"])

            if expert_id not in query_experts or query_experts[expert_id] is None:
                continue

            available_count += 1
            query_oracle = query_experts[expert_id]
            query_oracle_utilities.append(query_oracle)

            # Get neighbors for this query
            query_neighbors = neighbors[neighbors["query_idx"] == query_idx].head(15)

            expert_neighbor_utils = []
            for _, row in query_neighbors.iterrows():
                neighbor_experts = json.loads(row["expert_utilities_json"])
                if expert_id in neighbor_experts and neighbor_experts[expert_id] is not None:
                    expert_neighbor_utils.append(neighbor_experts[expert_id])

            if expert_neighbor_utils:
                neighbor_utilities.extend(expert_neighbor_utils)
                # Query selected = mean of top-k neighbors
                query_selected_utilities.append(np.mean(expert_neighbor_utils))

        if not neighbor_utilities:
            continue

        neighbor_mean = np.mean(neighbor_utilities)
        neighbor_std = np.std(neighbor_utilities)
        query_selected_mean = np.mean(query_selected_utilities) if query_selected_utilities else 0.0
        query_oracle_mean = np.mean(query_oracle_utilities) if query_oracle_utilities else 0.0
        regret = query_oracle_mean - query_selected_mean
        availability = available_count / len(query_panel)

        # Consistency = -std (lower is better)
        consistency = -neighbor_std
        consistency_vs_random = consistency - random_baseline.get("consistency", 0.0)
        utility_vs_random = query_selected_mean - random_baseline.get("query_selected_utility", 0.0)

        decompositions.append(
            ExpertDecomposition(
                expert_id=expert_id,
                method=method,
                fold_id=fold_id,
                neighbor_utility_mean=neighbor_mean,
                neighbor_utility_std=neighbor_std,
                query_selected_utility_mean=query_selected_mean,
                query_oracle_utility_mean=query_oracle_mean,
                regret=regret,
                availability_rate=availability,
                consistency_relative_to_random=consistency_vs_random,
                utility_relative_to_random=utility_vs_random,
            )
        )

    return decompositions


def _analyze_sampling_bias(
    panel: pd.DataFrame, method: str, fold_id: str, split_membership: dict
) -> SamplingBiasAnalysis:
    """Analyze temporal clustering in Train memory."""
    train_mask = panel.index.isin(
        [idx for idx, role in split_membership.items() if role == "train"]
    )
    train_panel = panel[train_mask].copy()

    if len(train_panel) == 0:
        raise DiagnosticError(f"No train samples found for {method}/{fold_id}")

    dates = pd.to_datetime(train_panel["date"])
    unique_dates = dates.unique()
    n_unique = len(unique_dates)
    n_rows = len(train_panel)

    # Rows per date statistics
    date_counts = dates.value_counts()
    rows_per_date_mean = date_counts.mean()
    rows_per_date_std = date_counts.std()
    rows_per_date_max = date_counts.max()

    # Consecutive day clustering
    sorted_dates = pd.Series(unique_dates).sort_values()
    date_diffs = sorted_dates.diff().dt.days.fillna(0)
    consecutive_starts = (date_diffs > 1).sum()

    # Find max consecutive sequence
    max_consecutive = 1
    current_consecutive = 1
    for diff in date_diffs[1:]:
        if diff == 1:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 1

    # Date coverage span
    date_span = (sorted_dates.max() - sorted_dates.min()).days

    # Temporal concentration entropy (higher = more uniform)
    date_probs = date_counts / date_counts.sum()
    entropy = -np.sum(date_probs * np.log(date_probs + 1e-10))

    return SamplingBiasAnalysis(
        method=method,
        fold_id=fold_id,
        n_train_rows=n_rows,
        n_unique_dates=n_unique,
        rows_per_date_mean=rows_per_date_mean,
        rows_per_date_std=rows_per_date_std,
        rows_per_date_max=int(rows_per_date_max),
        consecutive_day_clusters=int(consecutive_starts) + 1,
        max_consecutive_days=int(max_consecutive),
        date_coverage_span_days=int(date_span),
        temporal_concentration_entropy=float(entropy),
    )


def run_phase2_diagnostic(config: DiagnosticConfig) -> DiagnosticResult:
    """Execute Phase 2 diagnostic analysis.

    Returns:
        DiagnosticResult with expert decomposition, sampling bias analysis,
        and decision recommendation.
    """
    # Load source panel
    panel = pd.read_parquet(config.source_panel_path)

    # Load baseline comparison
    baseline_dir = config.baseline_output_dir
    comparison_path = baseline_dir / "baseline_comparison.csv"
    if not comparison_path.exists():
        raise DiagnosticError(f"Baseline comparison not found: {comparison_path}")

    comparison = pd.read_csv(comparison_path)

    # Get random baseline stats
    random_stats = comparison[comparison["method"] == "random_neighbor"].iloc[0].to_dict()
    random_baseline = {
        "consistency": -random_stats["std_neighbor_utility"],
        "query_selected_utility": random_stats["mean_query_selected_utility"],
    }

    # Process each method and fold
    all_decompositions = []
    all_sampling = []

    methods = ["pca_single_day", "pca_summary_20d"]
    fold_ids = ["wf_01", "wf_02", "wf_03", "wf_04"]

    for method in methods:
        method_dir = baseline_dir / method
        if not method_dir.exists():
            continue

        for fold_id in fold_ids:
            fold_dir = method_dir / fold_id
            if not fold_dir.exists():
                continue

            # Load split membership
            metadata_path = fold_dir / "baseline_metadata.json"
            if not metadata_path.exists():
                continue

            with open(metadata_path) as f:
                metadata = json.load(f)

            split_membership = metadata.get("split_membership", {})

            # Load neighbors and decompose
            neighbors, query_panel = _load_neighbors_and_panel(
                method_dir, fold_id, panel
            )

            decompositions = _decompose_expert_utilities(
                neighbors, query_panel, config.expert_ids, method, fold_id, random_baseline
            )
            all_decompositions.extend(decompositions)

            # Analyze sampling bias
            sampling = _analyze_sampling_bias(panel, method, fold_id, split_membership)
            all_sampling.append(sampling)

    # Make decision
    decision, rationale, summary = _make_decision(
        all_decompositions, all_sampling, comparison
    )

    return DiagnosticResult(
        expert_decompositions=all_decompositions,
        sampling_bias_analyses=all_sampling,
        decision_recommendation=decision,
        decision_rationale=rationale,
        summary_stats=summary,
    )


def _make_decision(
    decompositions: list[ExpertDecomposition],
    sampling_analyses: list[SamplingBiasAnalysis],
    comparison: pd.DataFrame,
) -> tuple[str, str, dict[str, Any]]:
    """Make Phase 2 decision based on diagnostic findings.

    Returns:
        (decision, rationale, summary_stats)
        decision: "continue", "stop", or "refactor"
    """
    if not decompositions:
        return "stop", "No valid expert decompositions found", {}

    # Convert to DataFrame for analysis
    df = pd.DataFrame([
        {
            "expert_id": d.expert_id,
            "method": d.method,
            "consistency_vs_random": d.consistency_relative_to_random,
            "utility_vs_random": d.utility_relative_to_random,
            "availability": d.availability_rate,
            "regret": d.regret,
        }
        for d in decompositions
    ])

    # Aggregate by expert across methods
    expert_summary = df.groupby("expert_id").agg({
        "consistency_vs_random": "mean",
        "utility_vs_random": "mean",
        "availability": "mean",
        "regret": "mean",
    }).reset_index()

    # Sampling bias summary
    sampling_df = pd.DataFrame([
        {
            "method": s.method,
            "rows_per_date_mean": s.rows_per_date_mean,
            "rows_per_date_max": s.rows_per_date_max,
            "max_consecutive_days": s.max_consecutive_days,
            "temporal_concentration_entropy": s.temporal_concentration_entropy,
        }
        for s in sampling_analyses
    ])

    # Decision logic
    rationale_parts = []
    summary_stats = {}

    # Check 1: Do any experts show positive utility improvement?
    positive_utility_experts = expert_summary[
        expert_summary["utility_vs_random"] > 0.001
    ]
    n_positive = len(positive_utility_experts)
    summary_stats["n_experts_with_positive_utility"] = n_positive
    summary_stats["max_utility_improvement"] = float(expert_summary["utility_vs_random"].max())

    if n_positive > 0:
        rationale_parts.append(
            f"Found {n_positive} expert(s) with positive utility vs random: "
            f"{', '.join(positive_utility_experts['expert_id'].tolist())}"
        )

    # Check 2: Sampling bias severity
    avg_entropy = sampling_df["temporal_concentration_entropy"].mean()
    max_consecutive = sampling_df["max_consecutive_days"].max()
    max_rows_per_date = sampling_df["rows_per_date_max"].max()

    summary_stats["avg_temporal_entropy"] = float(avg_entropy)
    summary_stats["max_consecutive_days"] = int(max_consecutive)
    summary_stats["max_rows_per_date"] = int(max_rows_per_date)

    severe_clustering = max_consecutive > 10 or max_rows_per_date > 50
    if severe_clustering:
        rationale_parts.append(
            f"Severe temporal clustering detected: {max_consecutive} max consecutive days, "
            f"{max_rows_per_date} max rows per date"
        )

    # Check 3: Consistency vs utility divergence pattern
    consistency_improved = df["consistency_vs_random"].mean() > 0.01
    utility_degraded = df["utility_vs_random"].mean() < -0.001

    summary_stats["avg_consistency_improvement"] = float(df["consistency_vs_random"].mean())
    summary_stats["avg_utility_change"] = float(df["utility_vs_random"].mean())

    if consistency_improved and utility_degraded:
        rationale_parts.append(
            "Consistency improved but utility degraded across methods - "
            "neighbors are more similar but less useful"
        )

    # Decision tree
    if n_positive >= 2 and not utility_degraded:
        decision = "continue"
        rationale_parts.insert(
            0,
            "CONTINUE: Multiple experts show retrieval value. Proceed with "
            "full utility vector labels (L01) and Transformer training (Phase 3).",
        )

    elif severe_clustering and utility_degraded:
        decision = "refactor"
        rationale_parts.insert(
            0,
            "REFACTOR: Severe sampling bias detected with negative utility. "
            "Implement stride=5 sampling (S01) before Phase 3.",
        )

    elif consistency_improved and utility_degraded:
        decision = "stop"
        rationale_parts.insert(
            0,
            "STOP: Neighbors are more consistent but consistently worse than random. "
            "State similarity does not predict expert utility. Do not proceed to Phase 3.",
        )

    else:
        decision = "stop"
        rationale_parts.insert(
            0,
            "STOP: No evidence of retrieval value. State matching hypothesis not supported.",
        )

    rationale = "\n\n".join(rationale_parts)

    # Add expert-level details to summary
    summary_stats["expert_details"] = expert_summary.to_dict(orient="records")
    summary_stats["sampling_details"] = sampling_df.to_dict(orient="records")

    return decision, rationale, summary_stats


def save_diagnostic_report(result: DiagnosticResult, output_dir: Path) -> None:
    """Save diagnostic report to JSON and markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = output_dir / "phase2_diagnostic_report.json"
    with open(json_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    # Save markdown
    md_path = output_dir / "phase2_diagnostic_report.md"
    with open(md_path, "w") as f:
        f.write("# Transformer State v3 Phase 2 Diagnostic Report\n\n")
        f.write(f"**Decision:** {result.decision_recommendation.upper()}\n\n")
        f.write("## Rationale\n\n")
        f.write(result.decision_rationale)
        f.write("\n\n")

        f.write("## Summary Statistics\n\n")
        for key, value in result.summary_stats.items():
            if key not in ["expert_details", "sampling_details"]:
                f.write(f"- **{key}**: {value}\n")
        f.write("\n")

        f.write("## Expert Decomposition\n\n")
        if result.expert_decompositions:
            df = pd.DataFrame([
                {
                    "expert_id": d.expert_id,
                    "method": d.method,
                    "fold": d.fold_id,
                    "neighbor_util_mean": f"{d.neighbor_utility_mean:.6f}",
                    "consistency_vs_rand": f"{d.consistency_relative_to_random:.6f}",
                    "utility_vs_rand": f"{d.utility_relative_to_random:.6f}",
                    "regret": f"{d.regret:.6f}",
                    "availability": f"{d.availability_rate:.2%}",
                }
                for d in result.expert_decompositions
            ])
            f.write(df.to_markdown(index=False))
            f.write("\n\n")

        f.write("## Sampling Bias Analysis\n\n")
        if result.sampling_bias_analyses:
            df = pd.DataFrame([
                {
                    "method": s.method,
                    "fold": s.fold_id,
                    "n_train": s.n_train_rows,
                    "n_dates": s.n_unique_dates,
                    "rows_per_date_max": s.rows_per_date_max,
                    "max_consecutive_days": s.max_consecutive_days,
                    "temporal_entropy": f"{s.temporal_concentration_entropy:.4f}",
                }
                for s in result.sampling_bias_analyses
            ])
            f.write(df.to_markdown(index=False))
            f.write("\n")

    print(f"Diagnostic report saved to {output_dir}")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")

