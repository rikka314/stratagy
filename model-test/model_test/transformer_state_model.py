"""Fold-local Transformer state encoder used by the W15 research pipeline.

PyTorch is deliberately optional at import time.  Schema validation, fold-local
normalisation, payload construction, and dependency preflight remain usable on
machines where the research runtime has not been installed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import io
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

try:  # pragma: no cover - availability is environment-specific
    import torch
    from torch import nn
except (ImportError, OSError) as exc:  # pragma: no cover - exercised via preflight
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: BaseException | None = exc
else:  # pragma: no cover - covered only when the optional dependency is present
    _TORCH_IMPORT_ERROR = None


class TransformerStateError(ValueError):
    """Raised when a W15 model or leakage boundary is invalid."""


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Mapping):
        return {str(key): _json_scalar(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_scalar(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def torch_dependency_preflight() -> dict[str, Any]:
    """Return a serialisable fail-closed PyTorch dependency report."""

    if torch is None:
        return {
            "status": "unavailable",
            "dependency": "torch",
            "version": None,
            "reason": "pytorch_not_installed",
            "error": None if _TORCH_IMPORT_ERROR is None else str(_TORCH_IMPORT_ERROR),
        }
    return {
        "status": "ready",
        "dependency": "torch",
        "version": str(torch.__version__),
        "reason": None,
        "error": None,
    }


_FORBIDDEN_FEATURE_TOKENS = (
    "future_",
    "label_end",
    "best_expert",
    "utility_margin",
    "label_margin",
)


def validate_model_feature_schema(
    feature_schema: Mapping[str, Any],
    feature_columns: Sequence[str] | None = None,
) -> list[str]:
    """Validate ordered point-in-time features and reject future/label inputs."""

    columns = list(feature_columns or feature_schema.get("feature_columns", []))
    entries = feature_schema.get("features", feature_schema.get("columns", []))
    by_name: dict[str, Mapping[str, Any]] = {}
    if isinstance(entries, Mapping):
        by_name = {str(name): value for name, value in entries.items() if isinstance(value, Mapping)}
        if not columns:
            columns = list(by_name)
    elif isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)):
        by_name = {
            str(entry.get("name", entry.get("column"))): entry
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("name", entry.get("column")) is not None
        }
        if not columns:
            columns = list(by_name)
    if not columns or len(columns) != len(set(columns)):
        raise TransformerStateError("feature schema requires unique ordered feature_columns")

    for column in columns:
        lowered = str(column).lower()
        if str(column) not in by_name:
            raise TransformerStateError(f"feature schema has no timing metadata for {column}")
        entry = by_name[str(column)]
        required_metadata = {"source", "shift", "missing_strategy", "model_input"}
        missing_metadata = required_metadata - set(entry)
        if "lookback" not in entry and "lookback_trading_days" not in entry:
            missing_metadata.add("lookback")
        if missing_metadata:
            raise TransformerStateError(
                f"feature schema has incomplete timing metadata for {column}: "
                f"{sorted(missing_metadata)}"
            )
        if entry["model_input"] is not True:
            raise TransformerStateError(f"feature is not explicitly enabled for W15 model input: {column}")
        forbidden_name = lowered.endswith("_label") or any(token in lowered for token in _FORBIDDEN_FEATURE_TOKENS)
        lookahead = entry.get("lookahead", entry.get("lookahead_days", 0))
        shift = entry["shift"]
        lookback = entry.get("lookback", entry.get("lookback_trading_days"))
        source_value = entry["source"]
        missing_strategy = entry["missing_strategy"]
        if not isinstance(source_value, str) or not source_value.strip():
            raise TransformerStateError(f"feature schema has invalid source metadata for {column}")
        if not isinstance(missing_strategy, str) or not missing_strategy.strip():
            raise TransformerStateError(
                f"feature schema has invalid missing_strategy metadata for {column}"
            )
        source = source_value.lower()
        try:
            lookback_value = float(lookback)
            future_metadata = float(lookahead or 0) > 0 or float(shift) < 0
        except (TypeError, ValueError) as exc:
            raise TransformerStateError(f"invalid feature timing metadata for {column}") from exc
        if not np.isfinite(lookback_value) or lookback_value < 0:
            raise TransformerStateError(f"invalid feature lookback metadata for {column}")
        if forbidden_name or future_metadata or "future" in source:
            raise TransformerStateError(f"future or label feature cannot be used by W15 model: {column}")
    return [str(column) for column in columns]


@dataclass
class FoldLocalSequenceScaler:
    """NaN-aware scaler whose fit boundary is explicitly train-only."""

    epsilon: float = 1e-8
    mean_: np.ndarray | None = field(default=None, init=False, repr=False)
    scale_: np.ndarray | None = field(default=None, init=False, repr=False)
    missing_rate_: np.ndarray | None = field(default=None, init=False, repr=False)
    fit_sample_count_: int = field(default=0, init=False)

    def fit(self, sequences: np.ndarray, *, role: str = "train") -> "FoldLocalSequenceScaler":
        if role != "train":
            raise TransformerStateError("fold-local scaler may only fit role='train'")
        array = _validate_sequences(sequences)
        finite = np.isfinite(array)
        counts = finite.sum(axis=(0, 1))
        if np.any(counts == 0):
            missing = np.flatnonzero(counts == 0).tolist()
            raise TransformerStateError(f"train fold has all-missing features: {missing}")
        safe = np.where(finite, array, 0.0)
        mean = safe.sum(axis=(0, 1)) / counts
        centered = np.where(finite, array - mean, 0.0)
        variance = np.square(centered).sum(axis=(0, 1)) / counts
        scale = np.sqrt(variance)
        scale[scale < self.epsilon] = 1.0
        self.mean_ = mean.astype(np.float64)
        self.scale_ = scale.astype(np.float64)
        self.missing_rate_ = (1.0 - finite.mean(axis=(0, 1))).astype(np.float64)
        self.fit_sample_count_ = int(array.shape[0])
        return self

    def transform(self, sequences: np.ndarray, *, append_missing_mask: bool = True) -> np.ndarray:
        if self.mean_ is None or self.scale_ is None:
            raise TransformerStateError("fold-local scaler is not fitted")
        array = _validate_sequences(sequences, expected_features=len(self.mean_))
        missing = ~np.isfinite(array)
        scaled = (np.where(missing, self.mean_, array) - self.mean_) / self.scale_
        scaled = scaled.astype(np.float32)
        if append_missing_mask:
            scaled = np.concatenate([scaled, missing.astype(np.float32)], axis=-1)
        return scaled

    def fit_transform(self, sequences: np.ndarray, *, role: str = "train") -> np.ndarray:
        return self.fit(sequences, role=role).transform(sequences)

    def to_payload(self, feature_columns: Sequence[str]) -> dict[str, Any]:
        if self.mean_ is None or self.scale_ is None or self.missing_rate_ is None:
            raise TransformerStateError("fold-local scaler is not fitted")
        if len(feature_columns) != len(self.mean_):
            raise TransformerStateError("feature columns do not match scaler width")
        return {
            "fit_role": "train",
            "fit_sample_count": self.fit_sample_count_,
            "feature_columns": list(feature_columns),
            "mean": self.mean_.tolist(),
            "scale": self.scale_.tolist(),
            "missing_rate": self.missing_rate_.tolist(),
            "missing_fill": "train_mean_then_zero_after_scaling",
            "missing_mask_appended": True,
        }


def _validate_sequences(sequences: np.ndarray, expected_features: int | None = None) -> np.ndarray:
    array = np.asarray(sequences, dtype=np.float64)
    if array.ndim != 3 or any(size <= 0 for size in array.shape):
        raise TransformerStateError("sequences must have shape [samples, length, features]")
    if expected_features is not None and array.shape[-1] != expected_features:
        raise TransformerStateError("sequence feature width does not match train fold")
    return array


@dataclass(frozen=True)
class TransformerCandidate:
    embedding_dim: int = 32
    num_layers: int = 1
    num_heads: int = 4
    feedforward_dim: int = 64
    dropout: float = 0.1
    sequence_length: int | None = None

    def validate(self) -> None:
        if min(self.embedding_dim, self.num_layers, self.num_heads, self.feedforward_dim) <= 0:
            raise TransformerStateError("Transformer dimensions and layer counts must be positive")
        if self.embedding_dim % self.num_heads:
            raise TransformerStateError("embedding_dim must be divisible by num_heads")
        if not 0.0 <= self.dropout < 1.0:
            raise TransformerStateError("dropout must be in [0, 1)")
        if self.sequence_length is not None and self.sequence_length <= 0:
            raise TransformerStateError("candidate sequence_length must be positive")


@dataclass(frozen=True)
class TransformerStateConfig:
    candidates: tuple[TransformerCandidate, ...] = (TransformerCandidate(),)
    epochs: int = 30
    patience: int = 5
    min_delta: float = 1e-4
    batch_size: int = 32
    learning_rate: float = 1e-3
    margin_loss_weight: float = 0.25
    seed: int = 1902
    cosine_variance_floor: float = 1e-6
    calibration_bins: int = 10
    minimum_train_rows: int = 1
    model_size_upper_bound: int = 100_000

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TransformerStateConfig":
        outer = raw
        raw = raw.get("transformer", raw)
        candidates_raw = raw.get("candidates", raw.get("model_candidates"))
        if candidates_raw is None:
            layer_counts = raw.get("num_layers_candidates", [raw.get("num_layers", 1)])
            panel = outer.get("panel", {}) if isinstance(outer.get("panel", {}), Mapping) else {}
            sequence_lengths = panel.get("sequence_length_candidates", [None])
            candidates_raw = [
                {
                    "embedding_dim": raw.get("embedding_dimension", raw.get("embedding_dim", 32)),
                    "num_layers": layer_count,
                    "num_heads": raw.get("attention_heads", raw.get("num_heads", 4)),
                    "feedforward_dim": raw.get("feedforward_dimension", raw.get("feedforward_dim", 64)),
                    "dropout": raw.get("dropout", 0.1),
                    "sequence_length": sequence_length,
                }
                for layer_count in layer_counts
                for sequence_length in sequence_lengths
            ]
        candidates = tuple(TransformerCandidate(**dict(item)) for item in candidates_raw)
        aliases = {
            "epoch_upper_bound": "epochs",
            "early_stopping_patience": "patience",
            "random_seed": "seed",
            "minimum_embedding_similarity_variance": "cosine_variance_floor",
        }
        normalized = {aliases.get(key, key): value for key, value in raw.items()}
        if "seed" not in normalized and "random_seed" in outer:
            normalized["seed"] = outer["random_seed"]
        if "cosine_variance_floor" not in normalized and "minimum_embedding_similarity_std" in raw:
            normalized["cosine_variance_floor"] = float(raw["minimum_embedding_similarity_std"]) ** 2
        values = {
            key: value for key, value in normalized.items() if key in cls.__dataclass_fields__ and key != "candidates"
        }
        return cls(candidates=candidates, **values)

    def validate(self) -> None:
        if not self.candidates:
            raise TransformerStateError("at least one pre-registered model candidate is required")
        for candidate in self.candidates:
            candidate.validate()
        if min(
            self.epochs,
            self.patience,
            self.batch_size,
            self.calibration_bins,
            self.minimum_train_rows,
            self.model_size_upper_bound,
        ) <= 0:
            raise TransformerStateError("training limits must be positive")
        if self.learning_rate <= 0 or self.margin_loss_weight < 0:
            raise TransformerStateError("learning rate and margin loss weight are invalid")


if nn is not None:  # pragma: no branch - definition depends on optional dependency

    class TransformerStateEncoder(nn.Module):
        def __init__(self, input_dim: int, class_count: int, candidate: TransformerCandidate, max_length: int):
            super().__init__()
            self.input_projection = nn.Linear(input_dim, candidate.embedding_dim)
            positions = torch.arange(max_length, dtype=torch.float32).unsqueeze(1)
            div = torch.exp(
                torch.arange(0, candidate.embedding_dim, 2, dtype=torch.float32)
                * (-math.log(10_000.0) / candidate.embedding_dim)
            )
            encoding = torch.zeros(max_length, candidate.embedding_dim, dtype=torch.float32)
            encoding[:, 0::2] = torch.sin(positions * div)
            encoding[:, 1::2] = torch.cos(positions * div[: encoding[:, 1::2].shape[1]])
            self.register_buffer("positional_encoding", encoding.unsqueeze(0), persistent=True)
            layer = nn.TransformerEncoderLayer(
                d_model=candidate.embedding_dim,
                nhead=candidate.num_heads,
                dim_feedforward=candidate.feedforward_dim,
                dropout=candidate.dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=candidate.num_layers)
            self.output_norm = nn.LayerNorm(candidate.embedding_dim)
            self.classifier = nn.Linear(candidate.embedding_dim, class_count)
            self.utility_margin_head = nn.Linear(candidate.embedding_dim, 1)

        def forward(self, values: Any) -> tuple[Any, Any, Any]:
            projected = self.input_projection(values)
            encoded = self.encoder(projected + self.positional_encoding[:, : values.shape[1]])
            embedding = self.output_norm(encoded.mean(dim=1))
            return embedding, self.classifier(embedding), self.utility_margin_head(embedding).squeeze(-1)

else:

    class TransformerStateEncoder:  # type: ignore[no-redef]
        def __init__(self, *_: Any, **__: Any):
            raise TransformerStateError("PyTorch is unavailable; run torch_dependency_preflight()")


def _set_seed(seed: int) -> None:
    np.random.seed(seed)
    if torch is not None:
        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)


def _classification_metrics(
    labels: np.ndarray,
    logits: np.ndarray,
    predicted_margins: np.ndarray,
    true_margins: np.ndarray,
    vocabulary: Sequence[str],
    *,
    calibration_bins: int,
    expert_utilities: np.ndarray | None = None,
    regime_values: Sequence[float] | None = None,
) -> dict[str, Any]:
    labels = np.asarray(labels, dtype=np.int64)
    logits = np.asarray(logits, dtype=np.float64)
    probabilities = np.exp(logits - logits.max(axis=1, keepdims=True))
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    order = np.argsort(-probabilities, axis=1)
    predicted = order[:, 0]
    top_k = min(2, probabilities.shape[1])
    recalls: dict[str, float | None] = {}
    for index, expert in enumerate(vocabulary):
        relevant = labels == index
        recalls[str(expert)] = float(np.mean(predicted[relevant] == index)) if relevant.any() else None
    valid_recalls = [value for value in recalls.values() if value is not None]
    confidence = probabilities[np.arange(len(labels)), predicted]
    correct = (predicted == labels).astype(float)
    ece = 0.0
    boundaries = np.linspace(0.0, 1.0, calibration_bins + 1)
    for lower, upper in zip(boundaries[:-1], boundaries[1:]):
        member = (confidence >= lower) & (confidence < upper if upper < 1.0 else confidence <= upper)
        if member.any():
            ece += float(member.mean() * abs(correct[member].mean() - confidence[member].mean()))
    true_margin_values = np.asarray(true_margins, dtype=np.float64)
    margin_error = np.abs(np.asarray(predicted_margins) - true_margin_values)
    utility_regret: float | None = None
    utility_regret_coverage = 0.0
    if expert_utilities is not None:
        utilities = np.asarray(expert_utilities, dtype=np.float64)
        if utilities.shape != logits.shape:
            raise TransformerStateError("expert utility matrix must align with logits and vocabulary")
        row_indexes = np.arange(len(labels))
        best_utility = utilities[row_indexes, labels]
        predicted_utility = utilities[row_indexes, predicted]
        valid_utility = np.isfinite(best_utility) & np.isfinite(predicted_utility)
        utility_regret_coverage = float(valid_utility.mean()) if len(valid_utility) else 0.0
        if valid_utility.any():
            realized_regret = np.maximum(
                best_utility[valid_utility] - predicted_utility[valid_utility], 0.0
            )
            utility_regret = float(realized_regret.mean())
    regime_coverage: dict[str, Any] = {
        "sample_count": int(len(labels)),
        "observed_count": 0,
        "observed_rate": 0.0,
        "by_regime": {},
    }
    if regime_values is not None:
        regimes = np.asarray(regime_values, dtype=np.float64)
        if regimes.shape != labels.shape:
            raise TransformerStateError("regime values must align with classification labels")
        observed = np.isfinite(regimes)
        regime_coverage["observed_count"] = int(observed.sum())
        regime_coverage["observed_rate"] = float(observed.mean()) if len(observed) else 0.0
        by_regime: dict[str, Any] = {}
        for regime in sorted(set(regimes[observed].tolist())):
            members = observed & np.isclose(regimes, regime)
            key = str(int(regime)) if float(regime).is_integer() else str(float(regime))
            by_regime[key] = {
                "sample_count": int(members.sum()),
                "top_1_accuracy": float(correct[members].mean()),
            }
        regime_coverage["by_regime"] = by_regime
    return {
        "sample_count": int(len(labels)),
        "top_1_accuracy": float(correct.mean()),
        "top_2_accuracy": float(np.mean(np.any(order[:, :top_k] == labels[:, None], axis=1))),
        "macro_f1": _macro_f1(labels, predicted, len(vocabulary)),
        "per_expert_recall": recalls,
        "utility_regret": utility_regret,
        "utility_regret_coverage": utility_regret_coverage,
        "utility_regret_definition": "realized utility(best_expert) - utility(predicted_expert)",
        "margin_mae": float(margin_error.mean()),
        "calibration_error": float(ece),
        "regime_coverage": regime_coverage,
    }


def _expert_utility_matrix(
    values: Sequence[Mapping[str, Any]] | None,
    *,
    vocabulary: Sequence[str],
    mask: np.ndarray,
    expected_rows: int,
    role: str,
) -> np.ndarray | None:
    if values is None:
        return None
    if len(values) != expected_rows:
        raise TransformerStateError(f"{role} expert utilities must align before masking")
    selected = np.asarray(list(values), dtype=object)[mask]
    matrix = np.full((len(selected), len(vocabulary)), np.nan, dtype=np.float64)
    for row_index, mapping in enumerate(selected):
        if not isinstance(mapping, Mapping):
            raise TransformerStateError(f"{role} expert utilities must be mappings")
        for column_index, expert in enumerate(vocabulary):
            raw = mapping.get(str(expert))
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value):
                matrix[row_index, column_index] = value
    return matrix


def _macro_f1(labels: np.ndarray, predicted: np.ndarray, class_count: int) -> float:
    scores: list[float] = []
    for index in range(class_count):
        tp = np.sum((labels == index) & (predicted == index))
        fp = np.sum((labels != index) & (predicted == index))
        fn = np.sum((labels == index) & (predicted != index))
        denominator = 2 * tp + fp + fn
        if denominator:
            scores.append(float(2 * tp / denominator))
    return float(np.mean(scores)) if scores else 0.0


def evaluate_embedding_availability(
    train_embeddings: np.ndarray,
    validation_metrics: Mapping[str, Any],
    train_labels: Sequence[str],
    label_vocabulary: Sequence[str],
    *,
    cosine_variance_floor: float = 1e-6,
    evaluation_labels: Sequence[str] | None = None,
    max_similarity_samples: int = 1024,
) -> dict[str, Any]:
    """Fail closed on collapsed embeddings or no classifier baseline lift."""

    embeddings = np.asarray(train_embeddings, dtype=np.float64)
    if embeddings.ndim != 2 or len(embeddings) < 2:
        return {"status": "unavailable", "reason": "insufficient_embeddings", "cosine_variance": 0.0}
    sample_count = min(len(embeddings), max(2, int(max_similarity_samples)))
    sample_indexes = np.linspace(0, len(embeddings) - 1, sample_count, dtype=int)
    sampled = embeddings[sample_indexes]
    norms = np.linalg.norm(sampled, axis=1)
    normalised = sampled / np.maximum(norms[:, None], 1e-12)
    similarities = normalised @ normalised.T
    upper = similarities[np.triu_indices(len(sampled), k=1)]
    cosine_variance = float(np.var(upper)) if upper.size else 0.0
    labels = [str(label) for label in train_labels]
    counts = {label: labels.count(label) for label in set(labels)}
    majority_label = max(sorted(counts), key=counts.get) if counts else None
    evaluated = [str(label) for label in (evaluation_labels if evaluation_labels is not None else labels)]
    majority_accuracy = evaluated.count(majority_label) / len(evaluated) if evaluated and majority_label else 1.0
    cash_accuracy = (
        sum(label.lower() == "cash" for label in evaluated) / len(evaluated)
        if evaluated
        else 1.0
    )
    classifier_accuracy = float(validation_metrics.get("top_1_accuracy", 0.0) or 0.0)
    baseline = max(majority_accuracy, cash_accuracy)
    reason = None
    if cosine_variance <= cosine_variance_floor:
        reason = "embedding_cosine_collapse"
    elif classifier_accuracy <= baseline:
        reason = "classifier_not_above_majority_or_cash_baseline"
    return {
        "status": "unavailable" if reason else "ready",
        "reason": reason,
        "cosine_variance": cosine_variance,
        "cosine_variance_floor": float(cosine_variance_floor),
        "cosine_similarity_sample_count": int(sample_count),
        "classifier_top_1_accuracy": classifier_accuracy,
        "majority_baseline_accuracy": float(majority_accuracy),
        "cash_baseline_accuracy": float(cash_accuracy),
        "label_vocabulary": list(label_vocabulary),
    }


def build_embedding_schema(
    *,
    feature_columns: Sequence[str],
    sequence_length: int,
    embedding_dim: int,
    scaler: FoldLocalSequenceScaler,
    label_vocabulary: Sequence[str],
    feature_schema_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "sequence_shape": [int(sequence_length), len(feature_columns)],
        "model_input_shape": [int(sequence_length), len(feature_columns) * 2],
        "embedding_dimension": int(embedding_dim),
        "pooling": "mean",
        "positional_encoding": "sinusoidal",
        "label_vocabulary": list(label_vocabulary),
        "feature_schema_sha256": feature_schema_sha256,
        "normalization": scaler.to_payload(feature_columns),
    }


def build_model_payload(
    *,
    status: str,
    config: TransformerStateConfig,
    selected_candidate: TransformerCandidate | None,
    label_vocabulary: Sequence[str],
    train_metrics: Mapping[str, Any] | None,
    validation_metrics: Mapping[str, Any] | None,
    availability: Mapping[str, Any],
    model_sha256: str | None,
    training_log: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the JSON-safe manifest fragment consumed by later W16 runners."""

    return _json_scalar(
        {
            "status": status,
            "fit_roles": ["train"],
            "selection_roles": ["validation"],
            "forbidden_selection_roles": ["test"],
            "config": asdict(config),
            "selected_candidate": None if selected_candidate is None else asdict(selected_candidate),
            "label_vocabulary": list(label_vocabulary),
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "availability": availability,
            "model_sha256": model_sha256,
            "training_log": list(training_log),
        }
    )


@dataclass
class FoldTrainingResult:
    status: str
    model: Any | None
    scaler: FoldLocalSequenceScaler
    selected_candidate: TransformerCandidate | None
    label_vocabulary: list[str]
    train_metrics: dict[str, Any] | None
    validation_metrics: dict[str, Any] | None
    availability: dict[str, Any]
    training_log: list[dict[str, Any]]
    model_sha256: str | None

    def payload(self, config: TransformerStateConfig) -> dict[str, Any]:
        return build_model_payload(
            status=self.status,
            config=config,
            selected_candidate=self.selected_candidate,
            label_vocabulary=self.label_vocabulary,
            train_metrics=self.train_metrics,
            validation_metrics=self.validation_metrics,
            availability=self.availability,
            model_sha256=self.model_sha256,
            training_log=self.training_log,
        )


def fit_transformer_fold(
    *,
    train_sequences: np.ndarray,
    train_labels: Sequence[str],
    train_margins: Sequence[float],
    validation_sequences: np.ndarray,
    validation_labels: Sequence[str],
    validation_margins: Sequence[float],
    train_expert_utilities: Sequence[Mapping[str, Any]] | None = None,
    validation_expert_utilities: Sequence[Mapping[str, Any]] | None = None,
    feature_columns: Sequence[str],
    feature_schema: Mapping[str, Any],
    config: TransformerStateConfig | Mapping[str, Any],
    train_supervision_mask: Sequence[bool] | None = None,
    validation_supervision_mask: Sequence[bool] | None = None,
) -> FoldTrainingResult:
    """Fit and select a fold model using train and validation only.

    There is intentionally no test argument: test sequences may only be passed to
    :func:`encode_sequences` after checkpoint selection is complete.
    """

    resolved = config if isinstance(config, TransformerStateConfig) else TransformerStateConfig.from_mapping(config)
    resolved.validate()
    columns = validate_model_feature_schema(feature_schema, feature_columns)
    train_raw = _validate_sequences(train_sequences)
    validation_raw = _validate_sequences(validation_sequences, expected_features=train_raw.shape[-1])
    if train_raw.shape[-1] != len(columns):
        raise TransformerStateError("sequence feature width does not match ordered feature_columns")
    scaler = FoldLocalSequenceScaler()
    scaler.fit(train_raw, role="train")
    if len(train_labels) != len(train_raw) or len(train_margins) != len(train_raw):
        raise TransformerStateError("train sequences, labels, and margins must align before masking")
    if len(validation_labels) != len(validation_raw) or len(validation_margins) != len(validation_raw):
        raise TransformerStateError("validation sequences, labels, and margins must align before masking")
    train_mask = _supervision_mask(train_supervision_mask, len(train_raw), "train")
    validation_mask = _supervision_mask(validation_supervision_mask, len(validation_raw), "validation")
    train_label_values = np.asarray(list(map(str, train_labels)), dtype=object)[train_mask]
    validation_label_values = np.asarray(list(map(str, validation_labels)), dtype=object)[validation_mask]
    train_margin_values = np.asarray(train_margins, dtype=np.float32)[train_mask]
    validation_margin_values = np.asarray(validation_margins, dtype=np.float32)[validation_mask]
    if int(train_mask.sum()) < resolved.minimum_train_rows:
        raise TransformerStateError(
            f"eligible train supervision rows {int(train_mask.sum())} are below "
            f"minimum_train_rows={resolved.minimum_train_rows}"
        )
    preflight = torch_dependency_preflight()
    vocabulary = sorted(set(train_label_values.tolist()))
    if preflight["status"] != "ready":
        return FoldTrainingResult(
            status="unavailable",
            model=None,
            scaler=scaler,
            selected_candidate=None,
            label_vocabulary=vocabulary,
            train_metrics=None,
            validation_metrics=None,
            availability=preflight,
            training_log=[],
            model_sha256=None,
        )
    if len(vocabulary) < 2:
        raise TransformerStateError("train fold requires at least two available expert labels")
    unknown = sorted(set(validation_label_values.tolist()) - set(vocabulary))
    if unknown:
        raise TransformerStateError(f"validation contains labels absent from train fold: {unknown}")
    train_y = np.asarray([vocabulary.index(str(label)) for label in train_label_values], dtype=np.int64)
    validation_y = np.asarray([vocabulary.index(str(label)) for label in validation_label_values], dtype=np.int64)
    if train_expert_utilities is None or validation_expert_utilities is None:
        raise TransformerStateError("ready W15 training requires complete train/validation expert utilities")
    train_utility_matrix = _expert_utility_matrix(
        train_expert_utilities,
        vocabulary=vocabulary,
        mask=train_mask,
        expected_rows=len(train_raw),
        role="train",
    )
    validation_utility_matrix = _expert_utility_matrix(
        validation_expert_utilities,
        vocabulary=vocabulary,
        mask=validation_mask,
        expected_rows=len(validation_raw),
        role="validation",
    )
    train_margin = train_margin_values
    validation_margin = validation_margin_values
    _validate_supervision(train_raw[train_mask], train_y, train_margin, "train")
    _validate_supervision(validation_raw[validation_mask], validation_y, validation_margin, "validation")
    train_regimes: np.ndarray | None = None
    validation_regimes: np.ndarray | None = None
    if "state_market_regime_id_20" in columns:
        regime_index = columns.index("state_market_regime_id_20")
        train_regimes = train_raw[train_mask, -1, regime_index]
        validation_regimes = validation_raw[validation_mask, -1, regime_index]

    best: dict[str, Any] | None = None
    all_logs: list[dict[str, Any]] = []
    for candidate_index, candidate in enumerate(resolved.candidates):
        sequence_length = candidate.sequence_length or train_raw.shape[1]
        if sequence_length > train_raw.shape[1] or sequence_length > validation_raw.shape[1]:
            raise TransformerStateError(
                f"candidate sequence_length={sequence_length} exceeds available sequence history"
            )
        candidate_scaler = FoldLocalSequenceScaler().fit(train_raw[:, -sequence_length:, :], role="train")
        candidate_train_x = candidate_scaler.transform(train_raw[:, -sequence_length:, :])[train_mask]
        candidate_validation_x = candidate_scaler.transform(validation_raw[:, -sequence_length:, :])[validation_mask]
        outcome = _fit_candidate(
            candidate_train_x,
            train_y,
            train_margin,
            candidate_validation_x,
            validation_y,
            validation_margin,
            vocabulary,
            candidate,
            resolved,
            candidate_index,
        )
        all_logs.extend(outcome["log"])
        selection_key = (outcome["best_validation_loss"], candidate_index)
        if best is None or selection_key < best["selection_key"]:
            best = {
                **outcome,
                "selection_key": selection_key,
                "candidate": candidate,
                "scaler": candidate_scaler,
                "train_x": candidate_train_x,
                "validation_x": candidate_validation_x,
            }
    assert best is not None
    model = best["model"]
    scaler = best["scaler"]
    train_embeddings, train_logits, train_margin_pred = _predict(model, best["train_x"])
    _, validation_logits, validation_margin_pred = _predict(model, best["validation_x"])
    train_metrics = _classification_metrics(
        train_y,
        train_logits,
        train_margin_pred,
        train_margin,
        vocabulary,
        calibration_bins=resolved.calibration_bins,
        expert_utilities=train_utility_matrix,
        regime_values=train_regimes,
    )
    validation_metrics = _classification_metrics(
        validation_y,
        validation_logits,
        validation_margin_pred,
        validation_margin,
        vocabulary,
        calibration_bins=resolved.calibration_bins,
        expert_utilities=validation_utility_matrix,
        regime_values=validation_regimes,
    )
    availability = evaluate_embedding_availability(
        train_embeddings,
        validation_metrics,
        train_label_values.tolist(),
        vocabulary,
        cosine_variance_floor=resolved.cosine_variance_floor,
        evaluation_labels=validation_label_values.tolist(),
    )
    model_bytes = io.BytesIO()
    torch.save(model.state_dict(), model_bytes)
    model_sha256 = hashlib.sha256(model_bytes.getvalue()).hexdigest()
    return FoldTrainingResult(
        status=str(availability["status"]),
        model=model,
        scaler=scaler,
        selected_candidate=best["candidate"],
        label_vocabulary=vocabulary,
        train_metrics=train_metrics,
        validation_metrics=validation_metrics,
        availability=availability,
        training_log=all_logs,
        model_sha256=model_sha256,
    )


def _validate_supervision(values: np.ndarray, labels: np.ndarray, margins: np.ndarray, role: str) -> None:
    if not (len(values) == len(labels) == len(margins)) or len(values) == 0:
        raise TransformerStateError(f"{role} sequences, labels, and margins must be non-empty and aligned")
    if not np.isfinite(margins).all():
        raise TransformerStateError(f"{role} margins must be finite; filter unavailable/ambiguous labels before fit")


def _supervision_mask(mask: Sequence[bool] | None, sample_count: int, role: str) -> np.ndarray:
    if mask is None:
        return np.ones(sample_count, dtype=bool)
    resolved = np.asarray(mask, dtype=bool)
    if resolved.ndim != 1 or len(resolved) != sample_count:
        raise TransformerStateError(f"{role} supervision mask must align with sequences")
    if not resolved.any():
        raise TransformerStateError(f"{role} supervision mask contains no eligible rows")
    return resolved


def _fit_candidate(
    train_x: np.ndarray,
    train_y: np.ndarray,
    train_margin: np.ndarray,
    validation_x: np.ndarray,
    validation_y: np.ndarray,
    validation_margin: np.ndarray,
    vocabulary: Sequence[str],
    candidate: TransformerCandidate,
    config: TransformerStateConfig,
    candidate_index: int,
) -> dict[str, Any]:
    _set_seed(config.seed + candidate_index)
    model = TransformerStateEncoder(train_x.shape[-1], len(vocabulary), candidate, train_x.shape[1])
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count > config.model_size_upper_bound:
        raise TransformerStateError(
            f"candidate parameter count {parameter_count} exceeds model_size_upper_bound={config.model_size_upper_bound}"
        )
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    train_tensor = torch.as_tensor(train_x, dtype=torch.float32)
    labels_tensor = torch.as_tensor(train_y, dtype=torch.long)
    margins_tensor = torch.as_tensor(train_margin, dtype=torch.float32)
    validation_tensor = torch.as_tensor(validation_x, dtype=torch.float32)
    validation_labels_tensor = torch.as_tensor(validation_y, dtype=torch.long)
    validation_margins_tensor = torch.as_tensor(validation_margin, dtype=torch.float32)
    generator = torch.Generator().manual_seed(config.seed + candidate_index)
    best_loss = math.inf
    best_state: dict[str, Any] | None = None
    stale_epochs = 0
    log: list[dict[str, Any]] = []
    for epoch in range(config.epochs):
        model.train()
        permutation = torch.randperm(len(train_tensor), generator=generator)
        batch_losses: list[float] = []
        for start in range(0, len(permutation), config.batch_size):
            indices = permutation[start : start + config.batch_size]
            optimizer.zero_grad(set_to_none=True)
            _, logits, predicted_margin = model(train_tensor[indices])
            loss = nn.functional.cross_entropy(logits, labels_tensor[indices])
            loss = loss + config.margin_loss_weight * nn.functional.smooth_l1_loss(
                predicted_margin, margins_tensor[indices]
            )
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            _, validation_logits, validation_predicted_margin = model(validation_tensor)
            validation_loss = nn.functional.cross_entropy(validation_logits, validation_labels_tensor)
            validation_loss = validation_loss + config.margin_loss_weight * nn.functional.smooth_l1_loss(
                validation_predicted_margin, validation_margins_tensor
            )
            validation_value = float(validation_loss)
        improved = validation_value < best_loss - config.min_delta
        log.append(
            {
                "candidate_index": candidate_index,
                "epoch": epoch + 1,
                "train_loss": float(np.mean(batch_losses)),
                "validation_loss": validation_value,
                "checkpoint_selected": improved,
                "selection_role": "validation",
            }
        )
        if improved:
            best_loss = validation_value
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
                break
    if best_state is None:
        raise TransformerStateError("candidate training did not produce a validation checkpoint")
    model.load_state_dict(best_state)
    model.eval()
    return {"model": model, "best_validation_loss": best_loss, "log": log}


def _predict(model: Any, transformed_sequences: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    with torch.no_grad():
        embedding, logits, margins = model(torch.as_tensor(transformed_sequences, dtype=torch.float32))
    return embedding.cpu().numpy(), logits.cpu().numpy(), margins.cpu().numpy()


def encode_sequences(model: Any, scaler: FoldLocalSequenceScaler, sequences: np.ndarray) -> np.ndarray:
    """Transform unseen validation/test sequences without fitting any state."""

    if torch is None:
        raise TransformerStateError("PyTorch is unavailable; cannot encode sequences")
    transformed = scaler.transform(sequences)
    max_length = int(model.positional_encoding.shape[1])
    if transformed.shape[1] < max_length:
        raise TransformerStateError("unseen sequence is shorter than the selected candidate sequence_length")
    embeddings, _, _ = _predict(model, transformed[:, -max_length:, :])
    return embeddings


__all__ = [
    "FoldLocalSequenceScaler",
    "FoldTrainingResult",
    "TransformerCandidate",
    "TransformerStateConfig",
    "TransformerStateEncoder",
    "TransformerStateError",
    "build_embedding_schema",
    "build_model_payload",
    "encode_sequences",
    "evaluate_embedding_availability",
    "fit_transformer_fold",
    "torch_dependency_preflight",
    "validate_model_feature_schema",
]
