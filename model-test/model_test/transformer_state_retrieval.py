"""Leakage-safe state memory and cosine retrieval for Transformer-state v2.

The module is deliberately independent from model training and execution.  It
accepts/returns pandas frames plus JSON-serializable metadata so the runner can
write the W16 artifacts without embedding research policy in file I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


class StateRetrievalError(ValueError):
    """Raised when retrieval inputs violate a frozen W16 contract."""


MEMORY_COLUMNS = (
    "date",
    "symbol",
    "market",
    "split_id",
    "embedding",
    "embedding_norm",
    "best_expert_5d",
    "future_5d_utility",
    "future_5d_net_return",
    "future_5d_drawdown",
    "label_margin",
    "label_status",
    "source_manifest_sha256",
    "encoder_sha256",
    "feature_schema_sha256",
)
LINEAGE_COLUMNS = (
    "source_manifest_sha256",
    "encoder_sha256",
    "feature_schema_sha256",
)
DEFAULT_THRESHOLD_QUANTILES = {
    "state_match_loose": 0.50,
    "state_match_balanced": 0.75,
    "state_match_strict": 0.90,
}
VALID_LABEL_STATUSES = frozenset({"available", "complete", "ready", "valid"})


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 15
    minimum_support: int = 5
    threshold_quantiles: Mapping[str, float] | None = None
    minimum_vote_confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise StateRetrievalError("top_k must be positive")
        if self.minimum_support < 1:
            raise StateRetrievalError("minimum_support must be positive")
        if not 0.0 <= self.minimum_vote_confidence <= 1.0:
            raise StateRetrievalError("minimum_vote_confidence must be in [0, 1]")
        quantiles = dict(self.threshold_quantiles or DEFAULT_THRESHOLD_QUANTILES)
        if not quantiles or any(not 0.0 <= float(value) <= 1.0 for value in quantiles.values()):
            raise StateRetrievalError("threshold quantiles must be in [0, 1]")
        object.__setattr__(self, "threshold_quantiles", quantiles)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RetrievalConfig":
        retrieval = payload.get("retrieval", payload)
        return cls(
            top_k=int(retrieval.get("top_k", 15)),
            minimum_support=int(retrieval.get("minimum_support", 5)),
            threshold_quantiles=retrieval.get("threshold_quantiles", DEFAULT_THRESHOLD_QUANTILES),
            minimum_vote_confidence=float(retrieval.get("minimum_vote_confidence", 0.0)),
        )


@dataclass(frozen=True)
class FallbackAudit:
    fallback_policy: str
    fallback_source_run: str
    fallback_source_model_id: str
    fallback_expert_id: str
    fallback_summary_sha256: str
    fallback_source_manifest_sha256: str

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or not value:
                raise StateRetrievalError(f"{name} must be a non-empty string")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FallbackAudit":
        return cls(**{name: str(payload[name]) for name in cls.field_names()})

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(cls.__dataclass_fields__)

    def payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalArtifacts:
    memory_bank: pd.DataFrame
    similarity_distribution: pd.DataFrame
    thresholds: dict[str, float]
    decisions: pd.DataFrame
    manifest: dict[str, Any]


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, name: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise StateRetrievalError(f"{name} is missing required columns: {missing}")


def _as_embedding_matrix(values: Any, *, expected_rows: int | None = None) -> np.ndarray:
    try:
        if isinstance(values, pd.Series):
            matrix = np.asarray([np.asarray(value, dtype=float) for value in values], dtype=float)
        else:
            matrix = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise StateRetrievalError("embeddings must form a rectangular numeric matrix") from exc
    if matrix.ndim != 2 or matrix.shape[1] < 1:
        raise StateRetrievalError("embeddings must have shape [rows, dimensions]")
    if expected_rows is not None and matrix.shape[0] != expected_rows:
        raise StateRetrievalError("embedding row count does not match input rows")
    return matrix


def _normalized_embeddings(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    norms = np.linalg.norm(matrix, axis=1)
    if not np.isfinite(matrix).all() or not np.isfinite(norms).all() or np.any(norms <= 0.0):
        raise StateRetrievalError("memory embeddings must be finite and have positive norm")
    return matrix / norms[:, None], norms


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def build_state_memory_bank(
    rows: pd.DataFrame,
    embeddings: Any,
    *,
    role_column: str = "role",
    strict_train_only: bool = False,
) -> pd.DataFrame:
    """Build an L2-normalized memory bank from complete train labels only.

    ``strict_train_only`` is useful at a runner boundary: it rejects a mixed-role
    frame.  The default filters train rows, which is convenient when consuming a
    complete fold panel while still making it impossible to persist non-train rows.
    """

    required = [column for column in MEMORY_COLUMNS if column not in {"embedding", "embedding_norm"}]
    _require_columns(rows, [*required, role_column], name="training rows")
    matrix = _as_embedding_matrix(embeddings, expected_rows=len(rows))
    role_values = rows[role_column].astype(str).str.lower()
    if strict_train_only and not role_values.eq("train").all():
        raise StateRetrievalError("memory bank input must be train-only")
    numeric_columns = (
        "future_5d_utility",
        "future_5d_net_return",
        "future_5d_drawdown",
        "label_margin",
    )
    numeric = {column: pd.to_numeric(rows[column], errors="coerce") for column in numeric_columns}
    finite_numeric = np.logical_and.reduce(
        [np.isfinite(values.to_numpy(dtype=float)) for values in numeric.values()]
    )
    valid = (
        role_values.eq("train")
        & rows["label_status"].astype(str).str.lower().isin(VALID_LABEL_STATUSES)
        & rows["best_expert_5d"].notna()
        & finite_numeric
    )
    retained_columns = [*required, *(["segment"] if "segment" in rows.columns else [])]
    selected = rows.loc[valid, retained_columns].copy()
    if selected.empty:
        raise StateRetrievalError("memory bank has no complete train labels")
    normalized, norms = _normalized_embeddings(matrix[valid.to_numpy()])
    selected["date"] = pd.to_datetime(selected["date"], errors="raise")
    selected["embedding"] = [row.tolist() for row in normalized]
    selected["embedding_norm"] = norms.astype(float)
    for column, values in numeric.items():
        selected[column] = values.loc[valid].astype(float).to_numpy()
    output_columns = [*MEMORY_COLUMNS, *(["segment"] if "segment" in selected.columns else [])]
    selected = selected.loc[:, output_columns].sort_values(["date", "symbol"], kind="stable")
    return selected.reset_index(drop=True)


def _unique_scope(memory_bank: pd.DataFrame) -> tuple[str, str]:
    markets = memory_bank["market"].astype(str).unique().tolist()
    splits = memory_bank["split_id"].astype(str).unique().tolist()
    if len(markets) != 1 or len(splits) != 1:
        raise StateRetrievalError("retrieval operates on exactly one market and split at a time")
    return markets[0], splits[0]


def _lineage(memory_bank: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    for column in LINEAGE_COLUMNS:
        values = memory_bank[column].dropna().astype(str).unique().tolist()
        if len(values) != 1:
            raise StateRetrievalError(f"memory lineage drift in {column}")
        result[column] = values[0]
    return result


def derive_train_similarity_thresholds(
    memory_bank: pd.DataFrame,
    quantiles: Mapping[str, float] | None = None,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Derive q50/q75/q90-style thresholds from strictly-prior train matches."""

    _require_columns(memory_bank, MEMORY_COLUMNS, name="memory bank")
    _unique_scope(memory_bank)
    _lineage(memory_bank)
    quantile_map = dict(quantiles or DEFAULT_THRESHOLD_QUANTILES)
    if any(not 0.0 <= float(value) <= 1.0 for value in quantile_map.values()):
        raise StateRetrievalError("threshold quantiles must be in [0, 1]")
    ordered = memory_bank.copy()
    ordered["date"] = pd.to_datetime(ordered["date"], errors="raise")
    ordered = ordered.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    matrix = _as_embedding_matrix(ordered["embedding"], expected_rows=len(ordered))
    normalized, _ = _normalized_embeddings(matrix)
    records: list[dict[str, Any]] = []
    date_values = ordered["date"].to_numpy(dtype="datetime64[ns]")
    for current_date in np.unique(date_values):
        current_positions = np.flatnonzero(date_values == current_date)
        prior_positions = np.flatnonzero(date_values < current_date)
        if not prior_positions.size:
            continue
        similarities = normalized[current_positions] @ normalized[prior_positions].T
        max_offsets = np.argmax(similarities, axis=1)
        neighbor_max_date = ordered.iloc[prior_positions]["date"].max()
        for local_index, row_position in enumerate(current_positions):
            row = ordered.iloc[row_position]
            records.append(
                {
                    "date": row["date"],
                    "symbol": row["symbol"],
                    "market": row["market"],
                    "split_id": row["split_id"],
                    "max_similarity": float(similarities[local_index, max_offsets[local_index]]),
                    "prior_neighbor_count": int(len(prior_positions)),
                    "neighbor_max_date": neighbor_max_date,
                }
            )
    distribution = pd.DataFrame.from_records(records)
    if distribution.empty:
        raise StateRetrievalError("not enough strictly-prior train rows to derive thresholds")
    values = distribution["max_similarity"].to_numpy(dtype=float)
    thresholds = {name: float(np.quantile(values, float(q))) for name, q in quantile_map.items()}
    return thresholds, distribution


def _validate_query_lineage(query_rows: pd.DataFrame, memory_bank: pd.DataFrame) -> tuple[str, str]:
    _require_columns(
        query_rows,
        ["date", "symbol", "market", "split_id", "embedding", *LINEAGE_COLUMNS],
        name="query rows",
    )
    market, split_id = _unique_scope(memory_bank)
    expected = _lineage(memory_bank)
    if not query_rows["market"].astype(str).eq(market).all() or not query_rows["split_id"].astype(str).eq(split_id).all():
        raise StateRetrievalError("query market/split lineage drift")
    for column, expected_value in expected.items():
        if not query_rows[column].astype(str).eq(expected_value).all():
            raise StateRetrievalError(f"query lineage drift in {column}")
    return market, split_id


def _neighbor_audit(neighbors: pd.DataFrame) -> str:
    fields = ["date", "symbol", "market"]
    if "segment" in neighbors.columns:
        fields.append("segment")
    fields.extend(["best_expert_5d", "future_5d_utility", "similarity"])
    payload = [
        {field: _json_value(row[field]) for field in fields}
        for _, row in neighbors.iterrows()
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _expert_scores(neighbors: pd.DataFrame) -> tuple[str | None, dict[str, dict[str, float]]]:
    weights = np.clip(neighbors["similarity"].to_numpy(dtype=float), 0.0, None)
    if float(weights.sum()) <= 0.0:
        return None, {}
    working = neighbors.assign(_weight=weights)
    total_weight = float(weights.sum())
    scores: dict[str, dict[str, float]] = {}
    for expert_id, group in working.groupby("best_expert_5d", sort=True):
        expert_weights = group["_weight"].to_numpy(dtype=float)
        utility = group["future_5d_utility"].to_numpy(dtype=float)
        weight_sum = float(expert_weights.sum())
        if weight_sum <= 0.0:
            continue
        scores[str(expert_id)] = {
            "weighted_mean_utility": float(np.average(utility, weights=expert_weights)),
            "weighted_vote": weight_sum / total_weight,
            "support": int(len(group)),
        }
    if not scores:
        return None, {}
    selected = sorted(
        scores,
        key=lambda expert: (
            -scores[expert]["weighted_mean_utility"],
            -scores[expert]["weighted_vote"],
            expert,
        ),
    )[0]
    return selected, scores


def _base_decision(row: pd.Series, threshold_name: str, threshold: float) -> dict[str, Any]:
    return {
        "date": row["date"],
        "symbol": row["symbol"],
        "market": row["market"],
        "split_id": row["split_id"],
        "threshold_variant": threshold_name,
        "similarity_threshold": float(threshold),
        "decision_status": "fallback",
        "selected_expert_id": None,
        "matched_expert_id": None,
        "max_similarity": np.nan,
        "top_k_mean_similarity": np.nan,
        "support_count": 0,
        "neighbor_min_date": pd.NaT,
        "neighbor_max_date": pd.NaT,
        "neighbor_symbol_count": 0,
        "neighbor_segment_count": 0,
        "neighbor_segments_json": "[]",
        "neighbors_json": "[]",
        "expert_scores_json": "{}",
        "unmatched_reason": None,
        "embedding_failure_reason": None,
        "expert_unavailable_reason": None,
        "fallback_reason": None,
        "fallback_model_id": None,
    }


def _apply_fallback(
    decision: dict[str, Any],
    fallback: FallbackAudit,
    *,
    reason: str,
    fallback_available: bool,
) -> None:
    decision.update(fallback.payload())
    decision["decision_status"] = "fallback"
    decision["fallback_reason"] = reason
    decision["selected_expert_id"] = fallback.fallback_expert_id if fallback_available else "cash"
    decision["fallback_model_id"] = fallback.fallback_source_model_id if fallback_available else "cash"
    if not fallback_available:
        decision["fallback_reason"] = f"{reason};full_run_best_unavailable_cash"


def retrieve_state_matches(
    query_rows: pd.DataFrame,
    memory_bank: pd.DataFrame,
    *,
    thresholds: Mapping[str, float],
    config: RetrievalConfig,
    fallback: FallbackAudit,
    available_experts: set[str] | None = None,
    fallback_available: bool = True,
    expected_memory_sha256: str | None = None,
    expected_lineage: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Retrieve independent decisions for every query and frozen threshold."""

    _require_columns(memory_bank, MEMORY_COLUMNS, name="memory bank")
    if expected_memory_sha256 is not None and _frame_sha256(memory_bank) != expected_memory_sha256:
        raise StateRetrievalError("memory hash drift")
    actual_lineage = _lineage(memory_bank)
    if expected_lineage is not None:
        for column in LINEAGE_COLUMNS:
            if column in expected_lineage and actual_lineage[column] != str(expected_lineage[column]):
                raise StateRetrievalError(f"memory lineage drift in {column}")
    _validate_query_lineage(query_rows, memory_bank)
    if not thresholds or any(not np.isfinite(float(value)) for value in thresholds.values()):
        raise StateRetrievalError("thresholds must be finite")
    memory = memory_bank.copy()
    memory["date"] = pd.to_datetime(memory["date"], errors="raise")
    memory_matrix, _ = _normalized_embeddings(_as_embedding_matrix(memory["embedding"], expected_rows=len(memory)))
    embedding_dim = memory_matrix.shape[1]
    results: list[dict[str, Any]] = []
    for _, raw_query in query_rows.iterrows():
        query = raw_query.copy()
        query["date"] = pd.to_datetime(query["date"], errors="raise")
        embedding_failure_reason: str | None = None
        try:
            query_embedding = np.asarray(query["embedding"], dtype=float)
            if query_embedding.ndim != 1 or query_embedding.shape[0] != embedding_dim:
                embedding_failure_reason = "embedding_dimension_mismatch"
            elif not np.isfinite(query_embedding).all() or float(np.linalg.norm(query_embedding)) <= 0.0:
                embedding_failure_reason = "embedding_invalid"
        except (TypeError, ValueError):
            query_embedding = np.empty(0)
            embedding_failure_reason = "embedding_invalid"
        eligible_mask = memory["date"].lt(query["date"]).to_numpy()
        query_available = available_experts
        row_available: set[str] | None = None
        if "available_experts_json" in query and pd.notna(query["available_experts_json"]):
            try:
                payload = json.loads(str(query["available_experts_json"]))
            except json.JSONDecodeError as exc:
                raise StateRetrievalError("available_experts_json is invalid") from exc
            if not isinstance(payload, list):
                raise StateRetrievalError("available_experts_json must contain a list")
            row_available = {str(value) for value in payload}
            query_available = (
                row_available if available_experts is None else row_available.intersection(available_experts)
            )
        query_fallback_available = fallback_available and (
            row_available is None or fallback.fallback_expert_id in row_available
        )
        for threshold_name, threshold_value in thresholds.items():
            decision = _base_decision(query, str(threshold_name), float(threshold_value))
            decision["full_run_best_available"] = bool(query_fallback_available)
            decision["full_run_best_execution_expert_id"] = (
                fallback.fallback_expert_id if query_fallback_available else "cash"
            )
            decision["full_run_best_fallback_reason"] = (
                None if query_fallback_available else "full_run_best_unavailable_cash"
            )
            decision["full_run_best_expert_unavailable_reason"] = (
                None
                if query_fallback_available
                else f"full_run_best_unavailable:{fallback.fallback_expert_id}"
            )
            if embedding_failure_reason is not None:
                reason = embedding_failure_reason
                decision["embedding_failure_reason"] = reason
                _apply_fallback(
                    decision, fallback, reason=reason, fallback_available=query_fallback_available
                )
                results.append(decision)
                continue
            eligible_positions = np.flatnonzero(eligible_mask)
            if eligible_positions.size:
                normalized_query = query_embedding / np.linalg.norm(query_embedding)
                similarities = memory_matrix[eligible_positions] @ normalized_query
                order = np.argsort(-similarities, kind="stable")[: config.top_k]
                chosen_positions = eligible_positions[order]
                neighbors = memory.iloc[chosen_positions].copy()
                neighbors["similarity"] = similarities[order]
            else:
                neighbors = memory.iloc[0:0].copy().assign(similarity=pd.Series(dtype=float))
            support = len(neighbors)
            decision.update(
                {
                    "support_count": support,
                    "neighbors_json": _neighbor_audit(neighbors),
                    "neighbor_min_date": neighbors["date"].min() if support else pd.NaT,
                    "neighbor_max_date": neighbors["date"].max() if support else pd.NaT,
                    "neighbor_symbol_count": int(neighbors["symbol"].nunique()) if support else 0,
                    "neighbor_segment_count": int(neighbors["segment"].nunique())
                    if support and "segment" in neighbors.columns
                    else 0,
                    "neighbor_segments_json": json.dumps(
                        sorted(neighbors["segment"].dropna().astype(str).unique().tolist())
                        if support and "segment" in neighbors.columns
                        else []
                    ),
                    "max_similarity": float(neighbors["similarity"].max()) if support else np.nan,
                    "top_k_mean_similarity": float(neighbors["similarity"].mean()) if support else np.nan,
                }
            )
            if support < config.minimum_support:
                decision["unmatched_reason"] = "insufficient_support"
                _apply_fallback(
                    decision,
                    fallback,
                    reason="insufficient_support",
                    fallback_available=query_fallback_available,
                )
                results.append(decision)
                continue
            if decision["max_similarity"] < float(threshold_value):
                decision["unmatched_reason"] = "similarity_below_threshold"
                _apply_fallback(
                    decision,
                    fallback,
                    reason="similarity_below_threshold",
                    fallback_available=query_fallback_available,
                )
                results.append(decision)
                continue
            selected, scores = _expert_scores(neighbors)
            decision["expert_scores_json"] = json.dumps(scores, sort_keys=True, separators=(",", ":"))
            if selected is None or scores[selected]["weighted_vote"] < config.minimum_vote_confidence:
                decision["unmatched_reason"] = "insufficient_vote_confidence"
                _apply_fallback(
                    decision,
                    fallback,
                    reason="insufficient_vote_confidence",
                    fallback_available=query_fallback_available,
                )
                results.append(decision)
                continue
            decision["matched_expert_id"] = selected
            if query_available is not None and selected not in query_available:
                reason = f"selected_expert_unavailable:{selected}"
                decision["expert_unavailable_reason"] = reason
                _apply_fallback(
                    decision, fallback, reason=reason, fallback_available=query_fallback_available
                )
                results.append(decision)
                continue
            decision.update(
                {
                    "decision_status": "matched",
                    "selected_expert_id": selected,
                    "unmatched_reason": None,
                    "fallback_model_id": None,
                    **{field: None for field in FallbackAudit.field_names()},
                }
            )
            results.append(decision)
    decisions = pd.DataFrame.from_records(results)
    if decisions.empty:
        raise StateRetrievalError("query rows are empty")
    return decisions


def _frame_sha256(frame: pd.DataFrame) -> str:
    payload = frame.copy()

    def normalized(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return json.dumps(value.tolist(), sort_keys=True, separators=(",", ":"))
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value), sort_keys=True, separators=(",", ":"))
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        if isinstance(value, np.generic):
            return value.item()
        return value

    for column in payload.columns:
        payload[column] = payload[column].map(normalized)
    return hashlib.sha256(pd.util.hash_pandas_object(payload, index=True).values.tobytes()).hexdigest()


def run_state_retrieval(
    *,
    train_rows: pd.DataFrame,
    train_embeddings: Any,
    query_rows: pd.DataFrame,
    config: RetrievalConfig,
    fallback: FallbackAudit,
    available_experts: set[str] | None = None,
    fallback_available: bool = True,
    expected_memory_sha256: str | None = None,
    expected_lineage: Mapping[str, str] | None = None,
) -> RetrievalArtifacts:
    """Build all W16 in-memory artifacts for one market/split."""

    memory = build_state_memory_bank(train_rows, train_embeddings)
    thresholds, distribution = derive_train_similarity_thresholds(memory, config.threshold_quantiles)
    decisions = retrieve_state_matches(
        query_rows,
        memory,
        thresholds=thresholds,
        config=config,
        fallback=fallback,
        available_experts=available_experts,
        fallback_available=fallback_available,
        expected_memory_sha256=expected_memory_sha256,
        expected_lineage=expected_lineage,
    )
    market, split_id = _unique_scope(memory)
    manifest = {
        "schema_version": "1.0",
        "status": "ready",
        "market": market,
        "split_id": split_id,
        "memory_scope": "split_train_only",
        "similarity": "cosine_l2_normalized",
        "threshold_source": "strictly_prior_train_max_similarity",
        "threshold_quantiles": dict(config.threshold_quantiles or {}),
        "thresholds": thresholds,
        "top_k": config.top_k,
        "minimum_support": config.minimum_support,
        "tie_break": ["weighted_mean_utility", "weighted_vote", "expert_id_ascending"],
        "lineage": _lineage(memory),
        "memory_rows": len(memory),
        "query_rows": len(query_rows),
        "decision_rows": len(decisions),
        "memory_sha256": _frame_sha256(memory),
        "decisions_sha256": _frame_sha256(decisions),
        "full_run_best_only": {
            "policy": fallback.fallback_policy,
            "expert_id": fallback.fallback_expert_id if fallback_available else "cash",
            **fallback.payload(),
        },
    }
    return RetrievalArtifacts(memory, distribution, thresholds, decisions, manifest)


__all__ = [
    "FallbackAudit",
    "RetrievalArtifacts",
    "RetrievalConfig",
    "StateRetrievalError",
    "build_state_memory_bank",
    "derive_train_similarity_thresholds",
    "retrieve_state_matches",
    "run_state_retrieval",
]
