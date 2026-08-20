"""Tests for transformer_state_baseline module."""

import numpy as np
import pandas as pd
import pytest

from model_test.transformer_state_baseline import (
    BaselineConfig,
    BaselineError,
    _compute_summary_features,
    _cosine_similarity_topk,
    _extract_single_day_features,
    _fit_pca_baseline,
    _transform_and_normalize,
    compare_baselines,
    run_baseline_experiment,
    run_pca_baseline,
    run_random_baseline,
)


@pytest.fixture
def sample_panel():
    """Create sample sequence panel."""
    n_samples = 50
    seq_len = 20
    n_features = 28

    sequences = np.random.randn(n_samples, seq_len, n_features)
    utilities = np.random.randn(n_samples) * 0.02

    panel = pd.DataFrame({
        "sequence": [seq for seq in sequences],
        "future_5d_utility": utilities,
    })

    return panel, list(range(n_features))


def test_baseline_config():
    """Test BaselineConfig validation."""
    # Valid configs
    config = BaselineConfig(method="pca_single_day")
    assert config.method == "pca_single_day"
    assert config.top_k == 15

    # Invalid method
    with pytest.raises(BaselineError, match="Unknown baseline method"):
        BaselineConfig(method="invalid_method")

    # Invalid top_k
    with pytest.raises(BaselineError, match="top_k must be positive"):
        BaselineConfig(method="pca_single_day", top_k=0)

    # Invalid variance threshold
    with pytest.raises(BaselineError, match="pca_variance_threshold"):
        BaselineConfig(method="pca_single_day", pca_variance_threshold=1.5)


def test_extract_single_day_features(sample_panel):
    """Test single-day feature extraction."""
    panel, feature_columns = sample_panel

    features = _extract_single_day_features(panel, feature_columns)

    assert features.shape == (len(panel), len(feature_columns))
    assert not np.any(np.isnan(features))

    # Verify it's the last day
    first_seq = np.array(panel["sequence"].iloc[0])
    assert np.allclose(features[0], first_seq[-1])


def test_compute_summary_features(sample_panel):
    """Test summary feature computation."""
    panel, feature_columns = sample_panel

    # Default summary ops: 7 operations
    features = _compute_summary_features(panel, feature_columns)
    assert features.shape == (len(panel), len(feature_columns) * 7)

    # Custom summary ops
    features_custom = _compute_summary_features(
        panel, feature_columns, summary_ops=("mean", "std")
    )
    assert features_custom.shape == (len(panel), len(feature_columns) * 2)


def test_fit_pca_baseline():
    """Test PCA fitting."""
    features_train = np.random.randn(100, 28)

    scaler, pca, metadata = _fit_pca_baseline(features_train, variance_threshold=0.95)

    assert scaler is not None
    assert pca is not None
    assert metadata["n_components"] > 0
    assert metadata["n_components"] <= 28
    assert metadata["cumulative_variance"] >= 0.95
    assert len(metadata["explained_variance_ratio"]) == metadata["n_components"]


def test_transform_and_normalize():
    """Test transformation and normalization."""
    features_train = np.random.randn(100, 28)
    features_test = np.random.randn(20, 28)

    scaler, pca, _ = _fit_pca_baseline(features_train)

    embeddings = _transform_and_normalize(features_test, scaler, pca)

    assert embeddings.shape[0] == len(features_test)
    assert embeddings.shape[1] == pca.n_components_

    # Check L2 normalization
    norms = np.linalg.norm(embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_cosine_similarity_topk():
    """Test top-k cosine similarity retrieval."""
    n_query = 10
    n_memory = 50
    n_dim = 16
    top_k = 5

    # Create L2-normalized embeddings
    query_embeddings = np.random.randn(n_query, n_dim)
    query_embeddings /= np.linalg.norm(query_embeddings, axis=1, keepdims=True)

    memory_embeddings = np.random.randn(n_memory, n_dim)
    memory_embeddings /= np.linalg.norm(memory_embeddings, axis=1, keepdims=True)

    top_k_indices, top_k_similarities = _cosine_similarity_topk(
        query_embeddings, memory_embeddings, top_k
    )

    assert top_k_indices.shape == (n_query, top_k)
    assert top_k_similarities.shape == (n_query, top_k)

    # Check that similarities are in descending order
    for i in range(n_query):
        assert np.all(np.diff(top_k_similarities[i]) <= 0)

    # Check similarity range [-1, 1]
    assert np.all(top_k_similarities >= -1.0)
    assert np.all(top_k_similarities <= 1.0)


def test_run_pca_baseline(sample_panel):
    """Test full PCA baseline pipeline."""
    panel, feature_columns = sample_panel

    # Split into train/query
    n_train = 30
    panel_train = panel.iloc[:n_train].copy()
    panel_query = panel.iloc[n_train:].copy()

    config = BaselineConfig(method="pca_single_day", top_k=10)

    result = run_pca_baseline(
        config=config,
        panel_train=panel_train,
        panel_query=panel_query,
        feature_columns=feature_columns,
        fold_id="fold_01",
    )

    assert result.method == "pca_single_day"
    assert result.fold_id == "fold_01"
    assert result.n_train == n_train
    assert result.n_query == len(panel_query)
    assert result.n_components is not None
    assert result.embeddings_train.shape[0] == n_train
    assert result.embeddings_query.shape[0] == len(panel_query)
    assert len(result.neighbors) == len(panel_query) * config.top_k
    assert "mean_neighbor_utility" in result.neighbor_utility_stats


def test_run_random_baseline(sample_panel):
    """Test random baseline."""
    panel, _ = sample_panel

    n_train = 30
    panel_train = panel.iloc[:n_train].copy()
    panel_query = panel.iloc[n_train:].copy()

    config = BaselineConfig(method="random_neighbor", top_k=10)

    result = run_random_baseline(
        config=config,
        panel_train=panel_train,
        panel_query=panel_query,
        fold_id="fold_01",
    )

    assert result.method == "random_neighbor"
    assert result.n_train == n_train
    assert result.n_query == len(panel_query)
    assert result.n_components is None
    assert len(result.neighbors) == len(panel_query) * config.top_k
    assert all(result.neighbors["similarity"] == 0.0)


def test_run_baseline_experiment(sample_panel):
    """Test unified baseline experiment runner."""
    panel, feature_columns = sample_panel

    n_train = 30
    panel_train = panel.iloc[:n_train].copy()
    panel_query = panel.iloc[n_train:].copy()

    # Test PCA single day
    config_pca = BaselineConfig(method="pca_single_day")
    result_pca = run_baseline_experiment(
        config=config_pca,
        panel_train=panel_train,
        panel_query=panel_query,
        feature_columns=feature_columns,
        fold_id="fold_01",
    )
    assert result_pca.method == "pca_single_day"

    # Test random
    config_random = BaselineConfig(method="random_neighbor")
    result_random = run_baseline_experiment(
        config=config_random,
        panel_train=panel_train,
        panel_query=panel_query,
        feature_columns=feature_columns,
        fold_id="fold_01",
    )
    assert result_random.method == "random_neighbor"


def test_compare_baselines(sample_panel):
    """Test baseline comparison."""
    panel, feature_columns = sample_panel

    n_train = 30
    panel_train = panel.iloc[:n_train].copy()
    panel_query = panel.iloc[n_train:].copy()

    results = []

    for method in ["pca_single_day", "random_neighbor"]:
        config = BaselineConfig(method=method)
        result = run_baseline_experiment(
            config=config,
            panel_train=panel_train,
            panel_query=panel_query,
            feature_columns=feature_columns,
            fold_id="fold_01",
        )
        results.append(result)

    comparison_df = compare_baselines(results)

    assert len(comparison_df) == 2
    assert "method" in comparison_df.columns
    assert "mean_neighbor_utility" in comparison_df.columns
    assert "utility_consistency" in comparison_df.columns


def test_baseline_result_to_dict(sample_panel):
    """Test BaselineResult serialization."""
    panel, feature_columns = sample_panel

    n_train = 30
    panel_train = panel.iloc[:n_train].copy()
    panel_query = panel.iloc[n_train:].copy()

    config = BaselineConfig(method="pca_single_day")
    result = run_pca_baseline(
        config=config,
        panel_train=panel_train,
        panel_query=panel_query,
        feature_columns=feature_columns,
        fold_id="fold_01",
    )

    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["method"] == "pca_single_day"
    assert result_dict["fold_id"] == "fold_01"
    assert "neighbor_utility_stats" in result_dict
    assert "pca_params" in result_dict

    # Large arrays should not be in the dict
    assert "embeddings_train" not in result_dict
    assert "embeddings_query" not in result_dict
