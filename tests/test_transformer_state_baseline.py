"""Tests for transformer_state_baseline module."""

import json

import numpy as np
import pandas as pd
import pytest

from model_test.transformer_state_baseline import (
    BaselineConfig,
    BaselineError,
    DEFAULT_EXPERT_IDS,
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
from run_baseline_phase1 import REPO_ROOT, _sha256_file, load_baseline_inputs


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


def test_summary_trend_and_half_difference_match_protocol():
    """Trend is a slope; diff_half is second-half mean minus first-half mean."""

    sequence = np.repeat(np.arange(20, dtype=float)[:, None], 28, axis=1)
    panel = pd.DataFrame({"sequence": [sequence]})
    summaries = _compute_summary_features(
        panel,
        list(range(28)),
        summary_ops=("trend", "diff_half"),
    )

    assert np.allclose(summaries[0, :28], 1.0)
    assert np.allclose(summaries[0, 28:], 10.0)


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


def test_real_panel_contract_uses_sequence_values_and_full_utility_vector():
    """The baseline must consume the frozen v2 panel schema, not only fixtures."""

    rng = np.random.default_rng(7)
    rows = []
    for index in range(40):
        sequence = rng.normal(size=(20, 28))
        signal = float(sequence[-1, 0])
        utilities = {expert: -0.01 for expert in DEFAULT_EXPERT_IDS}
        utilities["naive"] = signal * 0.01
        utilities["cash"] = 0.0
        rows.append(
            {
                "sequence_values": np.asarray(
                    [np.asarray(day, dtype=float) for day in sequence], dtype=object
                ),
                "expert_utilities_json": json.dumps(utilities, sort_keys=True),
                "sequence_end_date": pd.Timestamp("2025-01-01")
                + pd.Timedelta(days=index),
                "symbol": f"S{index % 5}",
            }
        )
    panel = pd.DataFrame(rows)
    result = run_pca_baseline(
        config=BaselineConfig(method="pca_single_day", top_k=5),
        panel_train=panel.iloc[:30].reset_index(drop=True),
        panel_query=panel.iloc[30:].reset_index(drop=True),
        feature_columns=list(range(28)),
        fold_id="wf_01",
    )

    assert len(result.query_metrics) == 10
    assert {
        "utility_consistency",
        "query_selected_utility",
        "query_oracle_utility",
        "regret",
    }.issubset(result.query_metrics.columns)
    assert np.isfinite(result.query_metrics["regret"]).all()


def test_load_baseline_inputs_verifies_frozen_panel_manifest(tmp_path):
    """CLI integration loads the real artifact names and rejects hash drift."""

    source_dir = tmp_path / "frozen_panel"
    source_dir.mkdir()
    utilities = json.dumps({expert: 0.0 for expert in DEFAULT_EXPERT_IDS})
    panel = pd.DataFrame(
        {
            "sequence_end_date": [pd.Timestamp("2025-01-01")],
            "sequence_values": [np.zeros((20, 28)).tolist()],
            "expert_utilities_json": [utilities],
            "split_memberships_json": ['[{"split_id":"wf_01","role":"train"}]'],
            "symbol": ["AAPL"],
            "market": ["US"],
        }
    )
    sequence_path = source_dir / "state_sequence_panel.parquet"
    schema_path = source_dir / "state_feature_schema.json"
    splits_path = source_dir / "transformer_state_walk_forward_splits.csv"
    panel.to_parquet(sequence_path, index=False)
    schema_path.write_text(
        json.dumps({"feature_columns": [f"f{i}" for i in range(28)]}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [{"split_id": "wf_01", "train_start": "2020-01-01", "train_end": "2024-01-01", "validation_start": "2025-01-01", "validation_end": "2025-02-01"}]
    ).to_csv(splits_path, index=False)
    manifest = {
        "status": "ready",
        "market": "US",
        "artifacts": {
            "state_sequence_panel": {"path": sequence_path.name, "sha256": _sha256_file(sequence_path)},
            "feature_schema": {"path": schema_path.name, "sha256": _sha256_file(schema_path)},
            "walk_forward_splits": {"path": splits_path.name, "sha256": _sha256_file(splits_path)},
        },
    }
    manifest_path = source_dir / "state_panel_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config = {
        "market": "US",
        "baseline": {
            "source_panel_output_dir": str(source_dir.relative_to(REPO_ROOT)),
            "source_panel_manifest_sha256": _sha256_file(manifest_path),
        },
    }

    loaded_panel, schema, splits, _, loaded_manifest_path = load_baseline_inputs(config)

    assert len(loaded_panel) == 1
    assert len(schema["feature_columns"]) == 28
    assert splits.iloc[0]["split_id"] == "wf_01"
    assert loaded_manifest_path == manifest_path
