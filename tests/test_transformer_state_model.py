from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

import model_test.transformer_state_model as transformer_model
from model_test.transformer_state_model import (
    FoldLocalSequenceScaler,
    TransformerCandidate,
    TransformerStateConfig,
    TransformerStateError,
    build_embedding_schema,
    build_model_payload,
    evaluate_embedding_availability,
    fit_transformer_fold,
    torch_dependency_preflight,
    validate_model_feature_schema,
)


def _feature_schema() -> dict[str, object]:
    return {
        "feature_columns": ["asset_return_1", "market_volatility_20"],
        "features": [
            {
                "name": "asset_return_1",
                "source": "test.same_day",
                "lookback": 1,
                "shift": 0,
                "missing_strategy": "train_median",
                "model_input": True,
            },
            {
                "name": "market_volatility_20",
                "source": "test.trailing",
                "lookback": 20,
                "shift": 0,
                "missing_strategy": "train_median",
                "model_input": True,
            },
        ],
    }


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "future_5d_utility", "lookahead": 5},
        {"name": "innocent_name", "lookahead_days": 1},
        {"name": "best_expert_5d", "lookahead": 0},
        {"name": "shifted_close", "shift": -1},
        {"name": "blocked_by_w14_schema", "model_input": False},
    ],
)
def test_feature_schema_rejects_future_or_label_features(entry: dict[str, object]) -> None:
    complete_entry = {
        "source": "test.same_or_trailing",
        "lookback": 1,
        "shift": 0,
        "missing_strategy": "train_median",
        "model_input": True,
        **entry,
    }
    schema = {"feature_columns": [entry["name"]], "features": [complete_entry]}

    with pytest.raises(TransformerStateError):
        validate_model_feature_schema(schema)


def test_fold_local_scaler_uses_only_train_statistics_and_appends_missing_mask() -> None:
    train = np.array([[[1.0, np.nan], [3.0, 10.0]], [[5.0, 14.0], [7.0, 18.0]]])
    validation = np.array([[[101.0, np.nan], [103.0, 1000.0]]])
    scaler = FoldLocalSequenceScaler().fit(train, role="train")

    transformed = scaler.transform(validation)

    assert scaler.mean_.tolist() == pytest.approx([4.0, 14.0])
    assert scaler.fit_sample_count_ == 2
    assert transformed.shape == (1, 2, 4)
    assert transformed[0, 0, 1] == pytest.approx(0.0)
    assert transformed[0, 0, 3] == pytest.approx(1.0)
    assert scaler.mean_[0] != pytest.approx(validation[..., 0].mean())
    with pytest.raises(TransformerStateError, match="role='train'"):
        FoldLocalSequenceScaler().fit(validation, role="test")


def test_feature_schema_requires_timing_metadata_for_every_ordered_column() -> None:
    with pytest.raises(TransformerStateError, match="no timing metadata"):
        validate_model_feature_schema({"feature_columns": ["asset_return_1"], "columns": []})


@pytest.mark.parametrize("model_input", [None, "false", 0, False])
def test_feature_schema_requires_literal_true_model_input(model_input: object) -> None:
    entry = {
        "name": "asset_return_1",
        "source": "test.same_day",
        "lookback": 1,
        "shift": 0,
        "missing_strategy": "train_median",
    }
    if model_input is not None:
        entry["model_input"] = model_input
    schema = {"feature_columns": ["asset_return_1"], "features": [entry]}

    with pytest.raises(TransformerStateError, match="metadata|explicitly enabled"):
        validate_model_feature_schema(schema)


def test_utility_regret_uses_predicted_expert_realized_utility() -> None:
    metrics = transformer_model._classification_metrics(
        np.array([0]),
        np.array([[0.0, 0.0, 10.0]]),
        np.array([0.1]),
        np.array([0.1]),
        ["best", "second", "third"],
        calibration_bins=5,
        expert_utilities=np.array([[0.5, 0.4, -0.2]]),
    )

    assert metrics["utility_regret"] == pytest.approx(0.7)
    assert metrics["utility_regret_coverage"] == pytest.approx(1.0)


def test_classification_metrics_report_regime_coverage() -> None:
    metrics = transformer_model._classification_metrics(
        np.array([0, 1, 0]),
        np.array([[2.0, 0.0], [0.0, 2.0], [0.0, 2.0]]),
        np.array([0.1, 0.1, 0.1]),
        np.array([0.1, 0.1, 0.1]),
        ["cash", "sm"],
        calibration_bins=5,
        expert_utilities=np.array([[0.2, 0.1], [0.1, 0.2], [0.2, 0.1]]),
        regime_values=np.array([0.0, 1.0, np.nan]),
    )

    assert metrics["regime_coverage"]["observed_count"] == 2
    assert metrics["regime_coverage"]["observed_rate"] == pytest.approx(2 / 3)
    assert metrics["regime_coverage"]["by_regime"]["0"]["top_1_accuracy"] == 1.0


def test_fit_api_cannot_receive_test_data_or_use_test_for_selection() -> None:
    parameters = inspect.signature(fit_transformer_fold).parameters

    assert not any("test" in name for name in parameters)
    config = TransformerStateConfig(epochs=1, patience=1, batch_size=2)
    payload = build_model_payload(
        status="unavailable",
        config=config,
        selected_candidate=None,
        label_vocabulary=["Cash", "sm"],
        train_metrics=None,
        validation_metrics=None,
        availability={"status": "unavailable", "reason": "test_fixture"},
        model_sha256=None,
    )
    assert payload["fit_roles"] == ["train"]
    assert payload["selection_roles"] == ["validation"]
    assert payload["forbidden_selection_roles"] == ["test"]
    json.dumps(payload)


def test_dependency_preflight_is_explicit_and_fit_fails_closed_without_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transformer_model, "torch", None)
    monkeypatch.setattr(transformer_model, "_TORCH_IMPORT_ERROR", ImportError("missing test dependency"))

    preflight = torch_dependency_preflight()
    result = fit_transformer_fold(
        train_sequences=np.arange(24, dtype=float).reshape(4, 3, 2),
        train_labels=["Cash", "sm", "Cash", "sm"],
        train_margins=[0.1, 0.2, 0.1, 0.3],
        validation_sequences=np.arange(12, dtype=float).reshape(2, 3, 2),
        validation_labels=["Cash", "sm"],
        validation_margins=[0.1, 0.2],
        feature_columns=["asset_return_1", "market_volatility_20"],
        feature_schema=_feature_schema(),
        config=TransformerStateConfig(epochs=1, patience=1, batch_size=2),
    )

    assert preflight == {
        "status": "unavailable",
        "dependency": "torch",
        "version": None,
        "reason": "pytorch_not_installed",
        "error": "missing test dependency",
    }
    assert result.status == "unavailable"
    assert result.model is None
    assert result.availability["reason"] == "pytorch_not_installed"
    assert result.scaler.fit_sample_count_ == 4


def test_embedding_collapse_and_baseline_failure_are_unavailable() -> None:
    collapsed = evaluate_embedding_availability(
        np.ones((4, 3)),
        {"top_1_accuracy": 1.0},
        ["Cash", "sm", "Cash", "sm"],
        ["Cash", "sm"],
    )
    baseline_failure = evaluate_embedding_availability(
        np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [-1.0, 1.0]]),
        {"top_1_accuracy": 0.5},
        ["Cash", "Cash", "Cash", "sm"],
        ["Cash", "sm"],
    )

    assert collapsed["status"] == "unavailable"
    assert collapsed["reason"] == "embedding_cosine_collapse"
    assert baseline_failure["status"] == "unavailable"
    assert baseline_failure["reason"] == "classifier_not_above_majority_or_cash_baseline"


def test_embedding_schema_and_scaler_payload_are_json_serializable() -> None:
    scaler = FoldLocalSequenceScaler().fit(np.arange(24, dtype=float).reshape(4, 3, 2))

    schema = build_embedding_schema(
        feature_columns=["asset_return_1", "market_volatility_20"],
        sequence_length=3,
        embedding_dim=8,
        scaler=scaler,
        label_vocabulary=["Cash", "sm"],
        feature_schema_sha256="a" * 64,
    )

    assert schema["model_input_shape"] == [3, 4]
    assert schema["normalization"]["fit_role"] == "train"
    json.dumps(schema)


def test_frozen_transformer_config_maps_to_pre_registered_candidates() -> None:
    config = TransformerStateConfig.from_mapping(
        {
            "random_seed": 42,
            "transformer": {
                "embedding_dimension": 16,
                "num_layers_candidates": [1, 2],
                "attention_heads": 2,
                "feedforward_dimension": 32,
                "dropout": 0.1,
                "epoch_upper_bound": 20,
                "early_stopping_patience": 3,
                "batch_size": 256,
                "minimum_train_rows": 1000,
                "minimum_embedding_similarity_std": 0.0001,
            },
        }
    )

    config.validate()
    assert [candidate.num_layers for candidate in config.candidates] == [1, 2]
    assert all(candidate.embedding_dim == 16 for candidate in config.candidates)
    assert config.epochs == 20
    assert config.patience == 3
    assert config.seed == 42
    assert config.cosine_variance_floor == pytest.approx(1e-8)


@pytest.mark.skipif(transformer_model.torch is None, reason="optional PyTorch runtime is not installed")
def test_tiny_fit_uses_validation_checkpoint_when_torch_is_available() -> None:
    rng = np.random.default_rng(1902)
    train = rng.normal(size=(12, 4, 2))
    validation = rng.normal(size=(6, 4, 2))
    result = fit_transformer_fold(
        train_sequences=train,
        train_labels=["Cash", "sm"] * 6,
        train_margins=np.linspace(0.1, 0.5, 12),
        validation_sequences=validation,
        validation_labels=["Cash", "sm"] * 3,
        validation_margins=np.linspace(0.1, 0.3, 6),
        train_expert_utilities=[{"Cash": 0.2, "sm": 0.1}] * 12,
        validation_expert_utilities=[{"Cash": 0.2, "sm": 0.1}] * 6,
        feature_columns=["asset_return_1", "market_volatility_20"],
        feature_schema=_feature_schema(),
        config=TransformerStateConfig(
            candidates=(TransformerCandidate(embedding_dim=8, num_heads=2, feedforward_dim=16, dropout=0.0),),
            epochs=2,
            patience=1,
            batch_size=4,
            seed=1902,
        ),
    )

    assert result.model is not None
    assert result.model_sha256 is not None and len(result.model_sha256) == 64
    assert result.training_log
    assert {entry["selection_role"] for entry in result.training_log} == {"validation"}
    json.dumps(result.payload(TransformerStateConfig(epochs=1, patience=1)))
