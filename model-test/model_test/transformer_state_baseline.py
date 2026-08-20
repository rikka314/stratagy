"""Non-deep-learning baselines for Transformer State v3 - Phase 1.

This module implements three baseline methods for state similarity retrieval:
- B01: PCA on single-day features
- B02: PCA on 20-day statistical summary features
- B03: Random neighbor selection (null hypothesis)

All baselines use Train-only fitting and strictly-prior memory retrieval,
matching the Transformer research protocol but without deep learning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


class BaselineError(ValueError):
    """Raised when baseline inputs violate the v3 research contract."""


BaselineMethod = Literal["pca_single_day", "pca_summary_20d", "random_neighbor"]

DEFAULT_EXPERT_IDS = (
    "naive",
    "drift",
    "sm",
    "fsm",
    "best_search",
    "ml_filter",
    "adaptive_router",
    "cash",
)


@dataclass(frozen=True)
class BaselineConfig:
    """Configuration for baseline experiments."""

    method: BaselineMethod
    top_k: int = 15
    pca_variance_threshold: float = 0.95
    random_seed: int = 42
    expert_ids: tuple[str, ...] = DEFAULT_EXPERT_IDS

    def __post_init__(self) -> None:
        if self.method not in {"pca_single_day", "pca_summary_20d", "random_neighbor"}:
            raise BaselineError(f"Unknown baseline method: {self.method}")
        if self.top_k < 1:
            raise BaselineError("top_k must be positive")
        if not 0.0 < self.pca_variance_threshold <= 1.0:
            raise BaselineError("pca_variance_threshold must be in (0, 1]")
        if not self.expert_ids or len(set(self.expert_ids)) != len(self.expert_ids):
            raise BaselineError("expert_ids must be non-empty and unique")


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
    query_metrics: pd.DataFrame
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


def _sequence_matrix(panel: pd.DataFrame) -> np.ndarray:
    """Return the canonical 3-D sequence tensor from v2 or test fixtures."""

    sequence_column = next(
        (column for column in ("sequence_values", "sequence") if column in panel.columns),
        None,
    )
    if sequence_column is None:
        raise BaselineError("panel must have 'sequence_values' or 'sequence' column")

    rows: list[np.ndarray] = []
    for raw in panel[sequence_column]:
        value = raw.tolist() if isinstance(raw, np.ndarray) and raw.dtype == object else raw
        array = np.asarray(value, dtype=float)
        if array.ndim != 2:
            raise BaselineError("each sequence must have shape (sequence_length, n_features)")
        rows.append(array)

    if not rows:
        raise BaselineError("sequence panel must not be empty")
    sequences = np.stack(rows)
    if np.isinf(sequences).any():
        raise BaselineError("sequence panel contains infinite feature values")
    return sequences


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
    sequences = _sequence_matrix(panel)
    last_day_features = sequences[:, -1, :]  # (n_samples, n_features)

    if last_day_features.shape[1] != len(feature_columns):
        raise BaselineError(
            f"Feature count mismatch: got {last_day_features.shape[1]}, "
            f"expected {len(feature_columns)}"
        )

    return last_day_features


def _nan_linear_trend(sequences: np.ndarray) -> np.ndarray:
    """Return the per-sequence, per-feature least-squares time slope."""

    time = np.arange(sequences.shape[1], dtype=float)[None, :, None]
    finite = np.isfinite(sequences)
    count = finite.sum(axis=1)
    safe_values = np.where(finite, sequences, 0.0)
    safe_time = np.where(finite, time, 0.0)
    sum_x = safe_time.sum(axis=1)
    sum_y = safe_values.sum(axis=1)
    sum_xx = np.square(safe_time).sum(axis=1)
    sum_xy = (safe_time * safe_values).sum(axis=1)
    denominator = count * sum_xx - np.square(sum_x)
    numerator = count * sum_xy - sum_x * sum_y
    return np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan, dtype=float),
        where=denominator > 0,
    )


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
    sequences = _sequence_matrix(panel)
    n_samples, seq_len, n_features = sequences.shape

    summaries = []

    for op in summary_ops:
        if op == "last":
            summaries.append(sequences[:, -1, :])
        elif op == "mean":
            summaries.append(np.nanmean(sequences, axis=1))
        elif op == "std":
            summaries.append(np.nanstd(sequences, axis=1))
        elif op == "min":
            summaries.append(np.nanmin(sequences, axis=1))
        elif op == "max":
            summaries.append(np.nanmax(sequences, axis=1))
        elif op == "trend":
            summaries.append(_nan_linear_trend(sequences))
        elif op == "diff_half":
            first_half = np.nanmean(sequences[:, :seq_len//2, :], axis=1)
            second_half = np.nanmean(sequences[:, seq_len//2:, :], axis=1)
            summaries.append(second_half - first_half)
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
    if features_train.ndim != 2 or len(features_train) < 2:
        raise BaselineError("PCA Train features must be a non-trivial 2-D matrix")
    finite = np.isfinite(features_train)
    counts = finite.sum(axis=0)
    if np.any(counts == 0):
        raise BaselineError(
            f"PCA Train features contain all-missing columns: {np.flatnonzero(counts == 0).tolist()}"
        )
    train_means = np.where(finite, features_train, 0.0).sum(axis=0) / counts
    features_train_filled = np.where(finite, features_train, train_means)

    # Fit scaler on Train only after Train-mean imputation.
    scaler = StandardScaler()
    features_train_scaled = scaler.fit_transform(features_train_filled)

    # Fit PCA on Train only
    pca = PCA(n_components=variance_threshold, random_state=random_seed, svd_solver="full")
    pca.fit(features_train_scaled)

    pca_metadata = {
        "n_components": int(pca.n_components_),
        "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "cumulative_variance": float(np.sum(pca.explained_variance_ratio_)),
        "singular_values": pca.singular_values_.tolist(),
        "missing_fill": "train_mean",
        "train_missing_rate": (1.0 - finite.mean(axis=0)).tolist(),
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
    if features.ndim != 2 or features.shape[1] != len(scaler.mean_):
        raise BaselineError("PCA transform features do not match the Train feature width")
    features_filled = np.where(np.isfinite(features), features, scaler.mean_)
    features_scaled = scaler.transform(features_filled)
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


def _utility_matrix(
    panel: pd.DataFrame,
    expert_ids: Sequence[str],
) -> tuple[np.ndarray, tuple[str, ...]]:
    """Parse the complete expert utility vector, with scalar-fixture compatibility."""

    if "expert_utilities_json" in panel.columns:
        rows: list[list[float]] = []
        for raw in panel["expert_utilities_json"]:
            if isinstance(raw, str):
                try:
                    utilities = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise BaselineError("expert_utilities_json is invalid") from exc
            elif isinstance(raw, Mapping):
                utilities = raw
            else:
                raise BaselineError("expert_utilities_json must contain JSON objects")
            try:
                row = [float(utilities[expert_id]) for expert_id in expert_ids]
            except (KeyError, TypeError, ValueError) as exc:
                raise BaselineError("expert utility vector is incomplete or non-numeric") from exc
            rows.append(row)
        matrix = np.asarray(rows, dtype=float)
        resolved_experts = tuple(expert_ids)
    elif "future_5d_utility" in panel.columns:
        matrix = panel[["future_5d_utility"]].to_numpy(dtype=float)
        resolved_experts = ("utility",)
    else:
        raise BaselineError(
            "panel must have 'expert_utilities_json' or 'future_5d_utility'"
        )

    if not np.isfinite(matrix).all():
        raise BaselineError("utility labels must be finite")
    return matrix, resolved_experts


def _compute_neighbor_utility_stats(
    neighbors_df: pd.DataFrame,
    memory_panel: pd.DataFrame,
    query_panel: pd.DataFrame,
    expert_ids: Sequence[str],
    top_k: int,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Evaluate full-vector neighbor agreement and out-of-memory query regret."""

    if memory_panel.empty or query_panel.empty or neighbors_df.empty:
        raise BaselineError("memory, query, and neighbor inputs must not be empty")

    memory_utilities, resolved_experts = _utility_matrix(memory_panel, expert_ids)
    query_utilities, query_experts = _utility_matrix(query_panel, expert_ids)
    if resolved_experts != query_experts:
        raise BaselineError("memory and query utility schemas differ")

    ordered = neighbors_df.sort_values(["query_idx", "neighbor_rank"]).reset_index(drop=True)
    counts = ordered.groupby("query_idx", sort=True).size()
    if len(counts) != len(query_panel) or not (counts == top_k).all():
        raise BaselineError("each query must have exactly top_k neighbors")

    neighbor_indices = ordered["train_idx"].to_numpy(dtype=int).reshape(len(query_panel), top_k)
    similarities = ordered["similarity"].to_numpy(dtype=float).reshape(len(query_panel), top_k)
    neighbor_utilities = memory_utilities[neighbor_indices]

    predicted_utilities = neighbor_utilities.mean(axis=1)
    utility_dispersion = neighbor_utilities.std(axis=1).mean(axis=1)
    selected_index = np.argmax(predicted_utilities, axis=1)
    query_best_index = np.argmax(query_utilities, axis=1)
    row_index = np.arange(len(query_panel))
    selected_query_utility = query_utilities[row_index, selected_index]
    oracle_query_utility = query_utilities[row_index, query_best_index]
    regret = oracle_query_utility - selected_query_utility
    top5_width = min(5, top_k)
    query_dates = query_panel.get("sequence_end_date", query_panel.get("date"))
    if query_dates is None:
        query_dates = pd.Series(pd.NaT, index=query_panel.index)

    query_metrics = pd.DataFrame(
        {
            "query_idx": row_index,
            "query_date": pd.to_datetime(query_dates, errors="coerce").to_numpy(),
            "symbol": query_panel.get(
                "symbol", pd.Series([""] * len(query_panel), index=query_panel.index)
            ).astype(str).to_numpy(),
            "match_score": similarities[:, :top5_width].mean(axis=1),
            "mean_similarity": similarities.mean(axis=1),
            "neighbor_utility_dispersion": utility_dispersion,
            "utility_consistency": -utility_dispersion,
            "predicted_selected_expert": [resolved_experts[index] for index in selected_index],
            "query_best_expert": [resolved_experts[index] for index in query_best_index],
            "predicted_neighbor_utility": predicted_utilities[row_index, selected_index],
            "query_selected_utility": selected_query_utility,
            "query_oracle_utility": oracle_query_utility,
            "regret": regret,
            "expert_match": selected_index == query_best_index,
        }
    )

    stats = {
        "mean_neighbor_utility": float(query_metrics["predicted_neighbor_utility"].mean()),
        "std_neighbor_utility": float(query_metrics["neighbor_utility_dispersion"].mean()),
        "mean_similarity": float(query_metrics["mean_similarity"].mean()),
        "mean_top5_similarity": float(query_metrics["match_score"].mean()),
        "utility_consistency": float(query_metrics["utility_consistency"].mean()),
        "mean_query_selected_utility": float(query_metrics["query_selected_utility"].mean()),
        "mean_query_oracle_utility": float(query_metrics["query_oracle_utility"].mean()),
        "mean_regret": float(query_metrics["regret"].mean()),
        "expert_match_rate": float(query_metrics["expert_match"].mean()),
    }
    return stats, query_metrics


def build_coverage_quality_curve(query_metrics: pd.DataFrame) -> pd.DataFrame:
    """Build a deterministic score-ranked coverage/quality curve."""

    required = {
        "match_score",
        "query_selected_utility",
        "utility_consistency",
        "regret",
        "symbol",
    }
    missing = required - set(query_metrics.columns)
    if missing:
        raise BaselineError(f"query metrics missing coverage fields: {sorted(missing)}")

    ranked = query_metrics.sort_values(
        ["match_score", "query_idx"], ascending=[False, True]
    ).reset_index(drop=True)
    rows: list[dict[str, float | int]] = []
    for coverage in np.linspace(0.1, 1.0, 10):
        count = max(1, int(np.ceil(len(ranked) * coverage)))
        selected = ranked.iloc[:count]
        rows.append(
            {
                "coverage": float(count / len(ranked)),
                "query_count": int(count),
                "score_threshold": float(selected["match_score"].iloc[-1]),
                "mean_query_selected_utility": float(
                    selected["query_selected_utility"].mean()
                ),
                "utility_consistency": float(selected["utility_consistency"].mean()),
                "mean_regret": float(selected["regret"].mean()),
                "symbol_breadth": int(selected["symbol"].nunique()),
            }
        )
    return pd.DataFrame(rows)


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
    utility_stats, query_metrics = _compute_neighbor_utility_stats(
        neighbors_df,
        panel_train,
        panel_query,
        config.expert_ids,
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
        query_metrics=query_metrics,
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
    utility_stats, query_metrics = _compute_neighbor_utility_stats(
        neighbors_df,
        panel_train,
        panel_query,
        config.expert_ids,
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
        query_metrics=query_metrics,
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

    query_metrics_path = output_dir / "query_metrics.parquet"
    result.query_metrics.to_parquet(query_metrics_path, index=False)
    saved_files["query_metrics"] = str(query_metrics_path)

    coverage_path = output_dir / "coverage_quality.csv"
    build_coverage_quality_curve(result.query_metrics).to_csv(coverage_path, index=False)
    saved_files["coverage_quality"] = str(coverage_path)

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
            "mean_query_selected_utility": stats["mean_query_selected_utility"],
            "mean_query_oracle_utility": stats["mean_query_oracle_utility"],
            "mean_regret": stats["mean_regret"],
            "expert_match_rate": stats["expert_match_rate"],
        })

    return pd.DataFrame(comparison_rows)
