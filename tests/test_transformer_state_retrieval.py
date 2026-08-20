from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from model_test.transformer_state_retrieval import (
    FallbackAudit,
    RetrievalConfig,
    StateRetrievalError,
    _frame_sha256,
    build_state_memory_bank,
    derive_train_similarity_thresholds,
    retrieve_state_matches,
    run_state_retrieval,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _train_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]),
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "market": ["US"] * 4,
            "split_id": ["wf_01"] * 4,
            "role": ["train"] * 4,
            "best_expert_5d": ["alpha", "beta", "alpha", "beta"],
            "future_5d_utility": [0.4, 0.2, 0.1, 0.3],
            "future_5d_net_return": [0.05, 0.02, 0.01, 0.04],
            "future_5d_drawdown": [-0.01, -0.02, -0.03, -0.01],
            "label_margin": [0.2, 0.1, 0.05, 0.1],
            "label_status": ["available"] * 4,
            "source_manifest_sha256": [HASH_A] * 4,
            "encoder_sha256": [HASH_B] * 4,
            "feature_schema_sha256": [HASH_C] * 4,
        }
    )


def _fallback() -> FallbackAudit:
    return FallbackAudit(
        fallback_policy="full_run_best_guard",
        fallback_source_run="full_us_deans_60",
        fallback_source_model_id="sm_bayesian",
        fallback_expert_id="best_search",
        fallback_summary_sha256="d" * 64,
        fallback_source_manifest_sha256="e" * 64,
    )


def test_memory_bank_is_train_only_normalized_and_contract_complete() -> None:
    rows = _train_rows()
    rows.loc[3, "role"] = "test"
    embeddings = np.array([[3.0, 4.0], [0.0, 2.0], [1.0, 1.0], [9.0, 9.0]])

    memory = build_state_memory_bank(rows, embeddings)

    assert memory["symbol"].tolist() == ["AAA", "BBB", "CCC"]
    assert np.stack(memory["embedding"]).shape == (3, 2)
    assert memory["embedding_norm"].tolist() == pytest.approx([5.0, 2.0, np.sqrt(2.0)])
    assert np.linalg.norm(np.stack(memory["embedding"]), axis=1).tolist() == pytest.approx([1.0] * 3)
    assert "role" not in memory.columns


def test_memory_bank_rejects_non_train_only_mode_and_incomplete_labels() -> None:
    rows = _train_rows()
    rows.loc[0, "role"] = "validation"
    with pytest.raises(StateRetrievalError, match="train-only"):
        build_state_memory_bank(rows, np.ones((4, 2)), strict_train_only=True)

    rows = _train_rows()
    rows.loc[0, "label_status"] = "incomplete"
    memory = build_state_memory_bank(rows, np.ones((4, 2)))
    assert memory["symbol"].tolist() == ["BBB", "CCC", "DDD"]

    rows = _train_rows()
    rows.loc[0, "future_5d_net_return"] = np.inf
    memory = build_state_memory_bank(rows, np.ones((4, 2)))
    assert memory["symbol"].tolist() == ["BBB", "CCC", "DDD"]


def test_thresholds_are_train_derived_strictly_prior_and_fixed_quantiles() -> None:
    rows = _train_rows()
    embeddings = np.array([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0], [-0.8, 0.6]])
    memory = build_state_memory_bank(rows, embeddings)

    thresholds, distribution = derive_train_similarity_thresholds(
        memory,
        {"state_match_loose": 0.5, "state_match_balanced": 0.75, "state_match_strict": 0.9},
    )

    # Strictly-prior maxima: 0.8, 0.6, 0.6. No self/same-day/future row is eligible.
    assert distribution["max_similarity"].tolist() == pytest.approx([0.8, 0.6, 0.6])
    assert (pd.to_datetime(distribution["neighbor_max_date"]) < pd.to_datetime(distribution["date"])).all()
    assert thresholds["state_match_loose"] == pytest.approx(np.quantile([0.8, 0.6, 0.6], 0.5))
    assert thresholds["state_match_balanced"] == pytest.approx(np.quantile([0.8, 0.6, 0.6], 0.75))
    assert thresholds["state_match_strict"] == pytest.approx(np.quantile([0.8, 0.6, 0.6], 0.9))


def test_retrieval_excludes_self_same_day_and_future_and_audits_neighbors() -> None:
    rows = _train_rows()
    memory = build_state_memory_bank(rows, np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]))
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-03"]),
            "symbol": ["CCC"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )

    decisions = retrieve_state_matches(
        query,
        memory,
        thresholds={"state_match_balanced": 0.5},
        config=RetrievalConfig(top_k=10, minimum_support=2),
        fallback=_fallback(),
    )

    audit = json.loads(decisions.loc[0, "neighbors_json"])
    assert decisions.loc[0, "decision_status"] == "matched"
    assert [row["date"] for row in audit] == ["2025-01-01", "2025-01-02"]
    assert {row["symbol"] for row in audit} == {"AAA", "BBB"}
    assert all(pd.Timestamp(row["date"]) < query.loc[0, "date"] for row in audit)


def test_weighted_utility_then_vote_then_stable_expert_id_breaks_ties() -> None:
    rows = _train_rows().iloc[:3].copy()
    rows["best_expert_5d"] = ["zeta", "alpha", "beta"]
    rows["future_5d_utility"] = [0.5, 0.5, 0.5]
    memory = build_state_memory_bank(rows, np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]))
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01"]),
            "symbol": ["QUERY"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )

    decision = retrieve_state_matches(
        query,
        memory,
        thresholds={"state_match_balanced": 0.5},
        config=RetrievalConfig(top_k=3, minimum_support=3),
        fallback=_fallback(),
    ).iloc[0]

    assert decision["selected_expert_id"] == "alpha"
    scores = json.loads(decision["expert_scores_json"])
    assert scores["alpha"]["weighted_mean_utility"] == pytest.approx(0.5)
    assert scores["alpha"]["weighted_vote"] == pytest.approx(1 / 3)


def test_minimum_support_and_similarity_fallback_have_complete_audit() -> None:
    memory = build_state_memory_bank(_train_rows().iloc[:2], np.array([[1.0, 0.0], [0.0, 1.0]]))
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01"]),
            "symbol": ["QUERY"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )

    decisions = retrieve_state_matches(
        query,
        memory,
        thresholds={"state_match_loose": 0.1, "state_match_strict": 1.1},
        config=RetrievalConfig(top_k=2, minimum_support=3),
        fallback=_fallback(),
    )

    assert decisions["decision_status"].tolist() == ["fallback", "fallback"]
    assert decisions["unmatched_reason"].tolist() == ["insufficient_support", "insufficient_support"]
    for field in FallbackAudit.field_names():
        assert decisions[field].notna().all()
    assert decisions["selected_expert_id"].tolist() == ["best_search", "best_search"]


def test_unavailable_selected_expert_falls_back_and_invalid_embedding_is_audited() -> None:
    memory = build_state_memory_bank(_train_rows().iloc[:2], np.array([[1.0, 0.0], [1.0, 0.0]]))
    base = {
        "date": pd.to_datetime(["2025-02-01", "2025-02-02"]),
        "symbol": ["Q1", "Q2"],
        "market": ["US", "US"],
        "split_id": ["wf_01", "wf_01"],
        "embedding": [[1.0, 0.0], [1.0, 0.0, 0.0]],
        "source_manifest_sha256": [HASH_A, HASH_A],
        "encoder_sha256": [HASH_B, HASH_B],
        "feature_schema_sha256": [HASH_C, HASH_C],
    }
    decisions = retrieve_state_matches(
        pd.DataFrame(base),
        memory,
        thresholds={"state_match_balanced": 0.5},
        config=RetrievalConfig(top_k=2, minimum_support=2),
        fallback=_fallback(),
        available_experts={"beta"},
    )

    assert decisions.loc[0, "expert_unavailable_reason"] == "selected_expert_unavailable:alpha"
    assert decisions.loc[0, "selected_expert_id"] == "best_search"
    assert decisions.loc[1, "embedding_failure_reason"] == "embedding_dimension_mismatch"


def test_query_local_availability_controls_selected_and_fallback_experts() -> None:
    memory = build_state_memory_bank(_train_rows().iloc[:2], np.array([[1.0, 0.0], [1.0, 0.0]]))
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01"]),
            "symbol": ["QUERY"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "available_experts_json": [json.dumps(["cash"])],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )

    decision = retrieve_state_matches(
        query,
        memory,
        thresholds={"state_match_balanced": 0.5},
        config=RetrievalConfig(top_k=2, minimum_support=2),
        fallback=_fallback(),
    ).iloc[0]

    assert decision["expert_unavailable_reason"] == "selected_expert_unavailable:alpha"
    assert decision["selected_expert_id"] == "cash"
    assert "full_run_best_unavailable_cash" in decision["fallback_reason"]
    assert not bool(decision["full_run_best_available"])
    assert decision["full_run_best_execution_expert_id"] == "cash"
    assert decision["full_run_best_fallback_reason"] == "full_run_best_unavailable_cash"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("source_manifest_sha256", "f" * 64),
        ("encoder_sha256", "f" * 64),
        ("feature_schema_sha256", "f" * 64),
    ],
)
def test_lineage_hash_or_schema_drift_fails_closed(column: str, value: str) -> None:
    memory = build_state_memory_bank(_train_rows(), np.ones((4, 2)))
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01"]),
            "symbol": ["QUERY"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )
    query.loc[0, column] = value

    with pytest.raises(StateRetrievalError, match="lineage drift"):
        retrieve_state_matches(
            query,
            memory,
            thresholds={"state_match_balanced": 0.5},
            config=RetrievalConfig(top_k=2, minimum_support=1),
            fallback=_fallback(),
        )


def test_expected_memory_hash_drift_fails_closed() -> None:
    memory = build_state_memory_bank(_train_rows(), np.ones((4, 2)))
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01"]),
            "symbol": ["QUERY"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )

    with pytest.raises(StateRetrievalError, match="memory hash drift"):
        retrieve_state_matches(
            query,
            memory,
            thresholds={"state_match_balanced": 0.5},
            config=RetrievalConfig(top_k=2, minimum_support=1),
            fallback=_fallback(),
            expected_memory_sha256="f" * 64,
        )


def test_main_api_returns_artifact_friendly_frames_and_json_payload(tmp_path) -> None:
    rows = _train_rows()
    query = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01"]),
            "symbol": ["QUERY"],
            "market": ["US"],
            "split_id": ["wf_01"],
            "embedding": [[1.0, 0.0]],
            "source_manifest_sha256": [HASH_A],
            "encoder_sha256": [HASH_B],
            "feature_schema_sha256": [HASH_C],
        }
    )
    artifacts = run_state_retrieval(
        train_rows=rows,
        train_embeddings=np.array([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0], [-0.8, 0.6]]),
        query_rows=query,
        config=RetrievalConfig(top_k=3, minimum_support=2),
        fallback=_fallback(),
    )

    assert set(artifacts.thresholds) == {
        "state_match_loose",
        "state_match_balanced",
        "state_match_strict",
    }
    assert len(artifacts.decisions) == 3
    assert artifacts.manifest["memory_scope"] == "split_train_only"
    assert artifacts.manifest["full_run_best_only"]["expert_id"] == "best_search"
    artifacts.memory_bank.to_parquet(tmp_path / "state_memory_bank.parquet", index=False)
    artifacts.decisions.to_parquet(tmp_path / "state_match_decisions.parquet", index=False)
    artifacts.similarity_distribution.to_csv(tmp_path / "state_similarity_distribution.csv", index=False)
    json.dumps(artifacts.thresholds)
    json.dumps(artifacts.manifest)

    roundtrip = pd.read_parquet(tmp_path / "state_memory_bank.parquet")
    assert _frame_sha256(roundtrip) == _frame_sha256(artifacts.memory_bank)
