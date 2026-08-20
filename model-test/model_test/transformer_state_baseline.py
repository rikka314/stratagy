"""Non-deep-learning baselines for Transformer State v3 - Phase 1.

This module implements three baseline methods for state similarity retrieval:
- B01: PCA on single-day features
- B02: PCA on 20-day statistical summary features
- B03: Random neighbor selection (null hypothesis)

All baselines use Train-only fitting and strictly-prior memory retrieval,
matching the Transformer research protocol but without deep learning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


class BaselineError(ValueError):
    """Raised when baseline inputs violate the v3 research contract."""


BaselineMethod = Literal["pca_single_day", "pca_summary_20d", "random_neighbor"]


@dataclass(frozen=True)
class BaselineConfig:
    """Configuration for baseline experiments."""

    method: BaselineMethod
    top_k: int = 15
    pca_variance_threshold: float = 0.95
    random_seed: int = 42

    def __post_init__(self) -> None:
        if self.method not in {"pca_single_day", "pca_summary_20d", "random_neighbor"}:
            raise BaselineError(f"Unknown baseline method: {self.method}")
        if self.top_k < 1:
            raise BaselineError("top_k must be positive")
        if not 0.0 < self.pca_variance_threshold <= 1.0:
            raise BaselineError("pca_variance_threshold must be in (0, 1]")


@dataclass(frozen=True)
class BaselineResult:
    """Result of a baseline retrieval experiment."""

    method: str
    fold_id: str
    n_train: int
    n_query: int
    n_components: int | None
    embeddings_train: np.ndarray  # shape: (n_train, n_components)
    embeddings_query: np.ndarray  # shape: (n_query, n_components)
    neighbors: pd.DataFrame  # columns: query_idx, neighbor_rank, train_idx, similarity
    neighbor_utility_stats: dict[str, float]
    scaler_params: dict[str, Any] | None
    pca_params: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict (excluding large arrays)."""
        return {
            "method": self.method,
            "fold_id": self.fold_id,
            "n_train": self.n_train,
            "n_query": self.n_query,
            "n_components": self.n_components,
            "neighbor_utility_stats": self.neighbor_utility_stats,
            "scaler_params": self.scaler_params,
            "pca_params": self.pca_params,
        }


def _extract_single_day_features(
    panel: pd.DataFrame,
    feature_columns: Sequence[str],
) -> np.ndarray:
    """Extract last-day features from sequence panel.

    Args:
        panel: state_sequence_panel with shape (n_samples, sequence_length, n_features)
        feature_columns: ordered feature names

    Returns:
        Array of shape (n_samples, n_features) with last-day observations
    """
    if "sequence" not in panel.columns:
        raise BaselineError("panel must have 'sequence' column containing feature arrays")

    sequences = np.stack(panel["sequence"].values)  # (n_samples, seq_len, n_features)
    last_day_features = sequences[:, -1, :]  # (n_samples, n_features)

    if last_day_features.shape[1] != len(feature_columns):
        raise BaselineError(
            f"Feature count mismatch: got {last_day_features.shape[1]}, "
            f"expected {len(feature_columns)}"
        )

    return last_day_features


def _compute_summary_features(
    panel: pd.DataFrame,
    feature_columns: Sequence[str],
    summary_ops: Sequence[str] = ("last", "mean", "std", "min", "max", "trend", "diff_half"),
) -> np.ndarray:
    """Compute statistical summary features over 20-day sequences.

    Args:
        panel: state_sequence_panel
        feature_columns: ordered feature names
        summary_ops: summary operations to apply

    Returns:
        Array of shape (n_samples, n_features * n_ops)
    """
    if "sequence" not in panel.columns:
        raise BaselineError("panel must have 'sequence' column")

    sequences = np.stack(panel["sequence"].values)  # (n_samples, seq_len, n_features)
    n_samples, seq_len, n_features = sequences.shape

    summaries = []

    for op in summary_ops:
        if op == "last":
            summaries.append(sequences[:, -1, :])
        elif op == "mean":
            summaries.append(np.mean(sequences, axis=1))
        elif op == "std":
            summaries.append(np.std(sequences, axis=1))
        elif op == "min":
            summaries.append(np.min(sequences, axis=1))
        elif op == "max":
            summaries.append(np.max(sequences, axis=1))
        elif op == "trend":
            # Linear trend: difference between last 5 and first 5 days
            first_half = np.mean(sequences[:, :seq_len//2, :], axis=1)
            second_half = np.mean(sequences[:, seq_len//2:, :], axis=1)
            summaries.append(second_half - first_half)
        elif op == "diff_half":
            # Difference between last and first observation
            summaries.append(sequences[:, -1, :] - sequences[:, 0, :])
        else:
            raise BaselineError(f"Unknown summary operation: {op}")

    summary_matrix = np.concatenate(summaries, axis=1)
    return summary_matrix


def _fit_pca_baseline(
    features_train: np.ndarray,
    variance_threshold: float = 0.95,
    random_seed: int = 42,
) -> tuple[StandardScaler, PCA, dict[str, Any]]:
    """Fit Train-only scaler and PCA.

    Args:
        features_train: Training features (n_train, n_features)
        variance_threshold: Cumulative variance threshold for PCA
        random_seed: Random seed for reproducibility

    Returns:
        Tuple of (fitted_scaler, fitted_pca, pca_metadata)
    """
    # Fit scaler on Train only
    scaler = StandardScaler()
    features_train_scaled = scaler.fit_transform(features_train)

    # Fit PCA on Train only
    pca = PCA(n_components=variance_threshold, random_state=random_seed, svd_solver="full")
    pca.fit(features_train_scaled)

    pca_metadata = {
        "n_components": int(pca.n_components_),
        "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "cumulative_variance": float(np.sum(pca.explained_variance_ratio_)),
        "singular_values": pca.singular_values_.tolist(),
    }

    return scaler, pca, pca_metadata


def _transform_and_normalize(
    features: np.ndarray,
    scaler: StandardScaler,
    pca: PCA,
) -> np.ndarray:
    """Apply fitted scaler, PCA, and L2 normalization.

    Args:
        features: Input features (n_samples, n_features)
        scaler: Fitted StandardScaler
        pca: Fitted PCA

    Returns:
        L2-normalized embeddings (n_samples, n_components)
    """
    features_scaled = scaler.transform(features)
    embeddings = pca.transform(features_scaled)

    # L2 normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # Avoid division by zero
    embeddings_normalized = embeddings / norms

    return embeddings_normalized


def _cosine_similarity_topk(
    query_embeddings: np.ndarray,
    memory_embeddings: np.ndarray,
    top_k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute top-k cosine similarities via matrix multiplication.

    Args:
        query_embeddings: Query embeddings (n_query, n_dim), L2-normalized
        memory_embeddings: Memory embeddings (n_memory, n_dim), L2-normalized
        top_k: Number of nearest neighbors

    Returns:
        Tuple of (top_k_indices, top_k_similarities)
        - top_k_indices: shape (n_query, top_k), memory indices
        - top_k_similarities: shape (n_query, top_k), cosine similarities
    """
    # Cosine similarity = dot product when both are L2-normalized
    similarity_matrix = query_embeddings @ memory_embeddings.T  # (n_query, n_memory)

    # Get top-k for each query
    top_k_indices = np.argsort(-similarity_matrix, axis=1)[:, :top_k]
    top_k_similarities = np.take_along_axis(similarity_matrix, top_k_indices, axis=1)

    return top_k_indices, top_k_similarities


def _compute_neighbor_utility_stats(
    neighbors_df: pd.DataFrame,
    memory_panel: pd.DataFrame,
    top_k: int,
) -> dict[str, float]:
    """Compute neighbor utility consistency statistics.

    Args:
        neighbors_df: DataFrame with query_idx, neighbor_rank, train_idx, similarity
        memory_panel: Training panel with utility labels
        top_k: Number of neighbors per query

    Returns:
        Dictionary of utility statistics
    """
    if memory_panel.empty or neighbors_df.empty:
        return {
            "mean_neighbor_utility": 0.0,
            "std_neighbor_utility": 0.0,
            "mean_similarity": 0.0,
            "utility_consistency": 0.0,
        }

    # Join neighbors with memory utility
    neighbors_with_utility = neighbors_df.merge(
        memory_panel[["future_5d_utility"]].reset_index(),
        left_on="train_idx",
        right_on="index",
        how="left",
    )

    if "future_5d_utility" not in neighbors_with_utility.columns:
        return {
            "mean_neighbor_utility": 0.0,
            "std_neighbor_utility": 0.0,
            "mean_similarity": float(neighbors_df["similarity"].mean()),
            "utility_consistency": 0.0,
        }

    # Compute per-query utility consistency
    query_utility_stats = neighbors_with_utility.groupby("query_idx").agg({
        "future_5d_utility": ["mean", "std"],
        "similarity": "mean",
    })

    mean_utility = float(query_utility_stats[("future_5d_utility", "mean")].mean())
    std_utility = float(query_utility_stats[("future_5d_utility", "std")].mean())
    mean_similarity = float(query_utility_stats[("similarity", "mean")].mean())

    # Utility consistency: negative std is better (neighbors agree)
    utility_consistency = -std_utility if not np.isnan(std_utility) else 0.0

    return {
        "mean_neighbor_utility": mean_utility,
        "std_neighbor_utility": std_utility,
        "mean_similarity": mean_similarity,
        "utility_consistency": utility_consistency,
    }


def run_pca_baseline(
    config: BaselineConfig,
    panel_train: pd.DataFrame,
    panel_query: pd.DataFrame,
    feature_columns: Sequence[str],
    fold_id: str,
) -> BaselineResult:
    """Run PCA baseline (single-day or summary features).

    Args:
        config: Baseline configuration
        panel_train: Training panel with sequences and labels
        panel_query: Query panel (Validation or Test)
        feature_columns: Ordered feature column names
        fold_id: Fold identifier

    Returns:
        BaselineResult with embeddings, neighbors, and statistics
    """
    if config.method == "pca_single_day":
        features_train = _extract_single_day_features(panel_train, feature_columns)
        features_query = _extract_single_day_features(panel_query, feature_columns)
    elif config.method == "pca_summary_20d":
        features_train = _compute_summary_features(panel_train, feature_columns)
        features_query = _compute_summary_features(panel_query, feature_columns)
    else:
        raise BaselineError(f"PCA baseline does not support method: {config.method}")

    # Fit scaler and PCA on Train only
    scaler, pca, pca_metadata = _fit_pca_baseline(
        features_train,
        variance_threshold=config.pca_variance_threshold,
        random_seed=config.random_seed,
    )

    # Transform and normalize
    embeddings_train = _transform_and_normalize(features_train, scaler, pca)
    embeddings_query = _transform_and_normalize(features_query, scaler, pca)

    # Retrieve top-k neighbors
    top_k_indices, top_k_similarities = _cosine_similarity_topk(
        embeddings_query,
        embeddings_train,
        top_k=config.top_k,
    )

    # Build neighbors DataFrame
    neighbors_rows = []
    for query_idx in range(len(embeddings_query)):
        for rank, (train_idx, similarity) in enumerate(
            zip(top_k_indices[query_idx], top_k_similarities[query_idx])
        ):
            neighbors_rows.append({
                "query_idx": query_idx,
                "neighbor_rank": rank + 1,
                "train_idx": int(train_idx),
                "similarity": float(similarity),
            })

    neighbors_df = pd.DataFrame(neighbors_rows)

    # Compute utility statistics
    utility_stats = _compute_neighbor_utility_stats(
        neighbors_df,
        panel_train,
        top_k=config.top_k,
    )

    scaler_params = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
    }

    return BaselineResult(
        method=config.method,
        fold_id=fold_id,
        n_train=len(panel_train),
        n_query=len(panel_query),
        n_components=pca_metadata["n_components"],
        embeddings_train=embeddings_train,
        embeddings_query=embeddings_query,
        neighbors=neighbors_df,
        neighbor_utility_stats=utility_stats,
        scaler_params=scaler_params,
        pca_params=pca_metadata,
    )


def run_random_baseline(
    config: BaselineConfig,
    panel_train: pd.DataFrame,
    panel_query: pd.DataFrame,
    fold_id: str,
) -> BaselineResult:
    """Run random neighbor baseline (null hypothesis).

    Args:
        config: Baseline configuration
        panel_train: Training panel with labels
        panel_query: Query panel
        fold_id: Fold identifier

    Returns:
        BaselineResult with random neighbors
    """
    rng = np.random.RandomState(config.random_seed)
    n_train = len(panel_train)
    n_query = len(panel_query)

    # Random embeddings (not used for retrieval, just for consistency)
    embeddings_train = np.zeros((n_train, 1))
    embeddings_query = np.zeros((n_query, 1))

    # Random neighbor selection
    neighbors_rows = []
    for query_idx in range(n_query):
        random_indices = rng.choice(n_train, size=config.top_k, replace=False)
        for rank, train_idx in enumerate(random_indices):
            neighbors_rows.append({
                "query_idx": query_idx,
                "neighbor_rank": rank + 1,
                "train_idx": int(train_idx),
                "similarity": 0.0,  # No meaningful similarity
            })

    neighbors_df = pd.DataFrame(neighbors_rows)

    # Compute utility statistics
    utility_stats = _compute_neighbor_utility_stats(
        neighbors_df,
        panel_train,
        top_k=config.top_k,
    )

    return BaselineResult(
        method=config.method,
        fold_id=fold_id,
        n_train=n_train,
        n_query=n_query,
        n_components=None,
        embeddings_train=embeddings_train,
        embeddings_query=embeddings_query,
        neighbors=neighbors_df,
        neighbor_utility_stats=utility_stats,
        scaler_params=None,
        pca_params=None,
    )


def run_baseline_experiment(
    config: BaselineConfig,
    panel_train: pd.DataFrame,
    panel_query: pd.DataFrame,
    feature_columns: Sequence[str],
    fold_id: str,
) -> BaselineResult:
    """Run a baseline experiment based on the specified method.

    Args:
        config: Baseline configuration
        panel_train: Training panel
        panel_query: Query panel (Validation or Test)
        feature_columns: Ordered feature column names
        fold_id: Fold identifier

    Returns:
        BaselineResult
    """
    if config.method in {"pca_single_day", "pca_summary_20d"}:
        return run_pca_baseline(config, panel_train, panel_query, feature_columns, fold_id)
    elif config.method == "random_neighbor":
        return run_random_baseline(config, panel_train, panel_query, fold_id)
    else:
        raise BaselineError(f"Unknown baseline method: {config.method}")


def save_baseline_artifacts(
    result: BaselineResult,
    output_dir: Path,
) -> dict[str, str]:
    """Save baseline artifacts to disk.

    Args:
        result: BaselineResult to save
        output_dir: Output directory

    Returns:
        Dictionary of saved file paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = {}

    # Save embeddings
    embeddings_train_path = output_dir / "embeddings_train.npy"
    np.save(embeddings_train_path, result.embeddings_train)
    saved_files["embeddings_train"] = str(embeddings_train_path)

    embeddings_query_path = output_dir / "embeddings_query.npy"
    np.save(embeddings_query_path, result.embeddings_query)
    saved_files["embeddings_query"] = str(embeddings_query_path)

    # Save neighbors
    neighbors_path = output_dir / "neighbors.parquet"
    result.neighbors.to_parquet(neighbors_path, index=False)
    saved_files["neighbors"] = str(neighbors_path)

    # Save metadata
    metadata = result.to_dict()
    metadata_path = output_dir / "baseline_metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    saved_files["metadata"] = str(metadata_path)

    return saved_files


def compare_baselines(
    results: Sequence[BaselineResult],
) -> pd.DataFrame:
    """Compare multiple baseline results.

    Args:
        results: List of BaselineResult objects

    Returns:
        DataFrame with comparison statistics
    """
    comparison_rows = []
    for result in results:
        stats = result.neighbor_utility_stats
        comparison_rows.append({
            "method": result.method,
            "fold_id": result.fold_id,
            "n_train": result.n_train,
            "n_query": result.n_query,
            "n_components": result.n_components,
            "mean_neighbor_utility": stats["mean_neighbor_utility"],
            "std_neighbor_utility": stats["std_neighbor_utility"],
            "mean_similarity": stats["mean_similarity"],
            "utility_consistency": stats["utility_consistency"],
        })

    return pd.DataFrame(comparison_rows)
