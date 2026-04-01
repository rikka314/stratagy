from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.adaptive_regime import (
    ADAPTIVE_MIN_STATE_DAYS,
    ADAPTIVE_MODEL_ID,
    ADAPTIVE_OFFLINE_CANDIDATE_MODEL_IDS,
    ADAPTIVE_STATE_FEATURE_COLUMNS,
    aggregate_candidate_state_day_rows,
    build_adaptive_feature_frame,
    normalize_distribution,
    predict_adaptive_states,
    save_adaptive_regime_artifacts,
    score_candidate_state_metrics,
    select_routing_policy,
    train_adaptive_state_model,
)
from core.data import ensure_date_column, standardize_columns
from ui.single_stock_workflow import StrategyRequest, build_strategy_context_key, run_strategy_pipeline

from model_test.config import build_main_window
from model_test.models import ResearchConfig, StockProfile


def _clear_streamlit_state() -> None:
    import streamlit as st

    try:
        st.session_state.clear()
    except Exception:
        pass


def _load_window_frame(profile: StockProfile, config: ResearchConfig) -> tuple[pd.DataFrame, int]:
    frame = pd.read_csv(profile.data_path)
    frame = ensure_date_column(standardize_columns(frame))
    window = build_main_window(config, len(frame))
    if not window.available:
        raise ValueError(f"Adaptive router training skipped {profile.symbol}: {window.reason}")
    df_window = frame.iloc[window.start_idx : window.end_idx].reset_index(drop=True).copy()
    split_idx = int(len(df_window) * window.train_ratio)
    split_idx = max(1, min(split_idx, len(df_window) - 1))
    return df_window, split_idx


def _build_candidate_request_payload(model_id: str) -> dict[str, Any]:
    if model_id in {"naive", "mean", "drift"}:
        return {"family": "baseline", "baseline_kind": model_id}
    if model_id == "sm":
        return {"family": "search", "search_base": "sm"}
    if model_id == "fsm":
        return {"family": "search", "search_base": "fsm"}

    payload_map = {
        "sm_bayesian": {"family": "search", "search_base": "sm", "use_search": True, "search_method": "bayesian"},
        "sm_random": {"family": "search", "search_base": "sm", "use_search": True, "search_method": "random"},
        "sm_genetic": {"family": "search", "search_base": "sm", "use_search": True, "search_method": "genetic"},
        "fsm_bayesian": {"family": "search", "search_base": "fsm", "use_search": True, "search_method": "bayesian"},
        "fsm_random": {"family": "search", "search_base": "fsm", "use_search": True, "search_method": "random"},
        "fsm_genetic": {"family": "search", "search_base": "fsm", "use_search": True, "search_method": "genetic"},
    }
    if model_id not in payload_map:
        raise ValueError(f"Unsupported adaptive candidate model_id: {model_id}")
    return dict(payload_map[model_id])


def _is_candidate_result_usable(model_id: str, result) -> bool:
    if result.artifact is None or not result.artifact.pipeline_lineage:
        return False
    final_stage = result.artifact.pipeline_lineage[-1]
    if model_id in {"naive", "mean", "drift"}:
        return final_stage.stage_key == "baseline"
    if model_id in {"sm", "fsm"}:
        return final_stage.stage_key in {"sm_base", "fsm_base"}
    return final_stage.stage_key == "search"


def _collect_stock_payload(
    *,
    profile: StockProfile,
    config: ResearchConfig,
    params_snapshot: dict[str, Any],
) -> dict[str, Any]:
    _clear_streamlit_state()
    df_window, split_idx = _load_window_frame(profile, config)
    context_key = build_strategy_context_key(
        market=config.market,
        symbol=profile.symbol,
        adjust=config.adjust,
        df_raw=df_window,
        train_ratio=config.train_ratio,
    )
    feature_df, feature_metadata = build_adaptive_feature_frame(
        df_window,
        adjust=config.adjust,
    )

    candidate_results: dict[str, Any] = {}
    warnings: list[str] = []
    for model_id in ADAPTIVE_OFFLINE_CANDIDATE_MODEL_IDS:
        request_payload = _build_candidate_request_payload(model_id)
        result = run_strategy_pipeline(
            context_key=context_key,
            request=StrategyRequest(**request_payload),
            request_params_snapshot=params_snapshot,
            df_raw=df_window,
            split_idx=split_idx,
        )
        if not _is_candidate_result_usable(model_id, result):
            warnings.append(f"{profile.symbol}:{model_id}:{result.status}")
            continue
        candidate_results[model_id] = result.artifact.pipeline_lineage[-1]

    if not candidate_results:
        raise ValueError(f"Adaptive router training found no usable candidates for {profile.symbol}.")

    return {
        "profile": profile,
        "df_window": df_window,
        "split_idx": split_idx,
        "feature_df": feature_df,
        "feature_metadata": feature_metadata,
        "candidate_results": candidate_results,
        "warnings": warnings,
    }


def _segment_bucket_rules(stock_profiles: list[StockProfile], config: ResearchConfig) -> dict[str, Any]:
    vol_series = pd.Series([profile.annualized_vol_1y for profile in stock_profiles], dtype="float64").dropna()
    return {
        "up_return_gt": 0.20,
        "down_return_lt": -0.10,
        "vol_q1": float(vol_series.quantile(1.0 / 3.0)) if not vol_series.empty else None,
        "vol_q2": float(vol_series.quantile(2.0 / 3.0)) if not vol_series.empty else None,
        "lookback_days": int(config.profile_lookback_days),
    }


def _build_candidate_state_day_rows(stock_payloads: list[dict[str, Any]], classifier_bundle: dict[str, Any]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for payload in stock_payloads:
        feature_df = payload["feature_df"].copy()
        predicted_state_ids = predict_adaptive_states(feature_df, classifier_bundle)
        split_idx = int(payload["split_idx"])
        state_frame = pd.DataFrame(
            {
                "date": pd.to_datetime(feature_df["date"], errors="coerce"),
                "state_id": predicted_state_ids,
                "benchmark_return": pd.to_numeric(feature_df["close"], errors="coerce").pct_change().fillna(0.0),
                "symbol": payload["profile"].symbol,
                "segment_key": payload["profile"].segment_key,
            }
        ).iloc[:split_idx].copy()
        state_frame = state_frame.dropna(subset=["date"])
        state_frame = state_frame[pd.to_numeric(state_frame["state_id"], errors="coerce").notna()].copy()
        if state_frame.empty:
            continue
        state_frame["state_id"] = state_frame["state_id"].astype(int)

        for model_id, stage in payload["candidate_results"].items():
            train_returns = stage.train_sim_df.copy()
            if "date" not in train_returns.columns or "strategy_return" not in train_returns.columns:
                continue
            train_returns = train_returns[["date", "strategy_return"]].copy()
            train_returns["date"] = pd.to_datetime(train_returns["date"], errors="coerce")
            train_returns = train_returns.dropna(subset=["date"])
            merged = state_frame.merge(train_returns, on="date", how="left")
            merged["strategy_return"] = pd.to_numeric(merged["strategy_return"], errors="coerce").fillna(0.0)
            merged["model_id"] = model_id
            rows.append(
                merged[
                    ["date", "state_id", "benchmark_return", "symbol", "segment_key", "model_id", "strategy_return"]
                ]
            )
    if not rows:
        return pd.DataFrame(
            columns=["date", "state_id", "benchmark_return", "symbol", "segment_key", "model_id", "strategy_return"]
        )
    return pd.concat(rows, ignore_index=True)


def _build_state_summary_rows(
    *,
    labeled_feature_df: pd.DataFrame,
    centroids_df: pd.DataFrame,
    routing_policy_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    if labeled_feature_df.empty or centroids_df.empty:
        return []
    overall_means = labeled_feature_df[list(ADAPTIVE_STATE_FEATURE_COLUMNS)].mean()
    global_policy = routing_policy_df[routing_policy_df["scope_level"] == "global"].copy()
    global_lookup = {
        int(row["state_id"]): str(row["selected_model_id"])
        for row in global_policy.to_dict("records")
    }

    rows: list[dict[str, Any]] = []
    for row in centroids_df.to_dict("records"):
        state_id = int(row["state_id"])
        deltas = {
            feature: abs(float(row.get(feature, 0.0)) - float(overall_means.get(feature, 0.0)))
            for feature in ADAPTIVE_STATE_FEATURE_COLUMNS
        }
        top_features = [feature for feature, _ in sorted(deltas.items(), key=lambda item: item[1], reverse=True)[:3]]
        rows.append(
            {
                "state_id": state_id,
                "sample_count": int(row.get("sample_count", 0)),
                "sample_ratio": float(row.get("sample_ratio", 0.0)),
                "top_features": top_features,
                "dominant_global_model_id": global_lookup.get(state_id),
            }
        )
    return rows


def _build_routing_summary_rows(routing_policy_df: pd.DataFrame, stock_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if routing_policy_df.empty:
        return []
    symbol_policy = routing_policy_df[routing_policy_df["scope_level"] == "symbol"].copy()
    segment_policy = routing_policy_df[routing_policy_df["scope_level"] == "segment"].copy()
    global_policy = routing_policy_df[routing_policy_df["scope_level"] == "global"].copy()
    symbol_count = max(len(stock_payloads), 1)

    rows: list[dict[str, Any]] = []
    for state_id in sorted(pd.to_numeric(routing_policy_df["state_id"], errors="coerce").dropna().astype(int).unique()):
        symbol_rows = symbol_policy[pd.to_numeric(symbol_policy["state_id"], errors="coerce") == state_id]
        segment_rows = segment_policy[pd.to_numeric(segment_policy["state_id"], errors="coerce") == state_id]
        global_rows = global_policy[pd.to_numeric(global_policy["state_id"], errors="coerce") == state_id]
        dominant_symbol_model_id = None
        if not symbol_rows.empty:
            dominant_symbol_model_id = (
                symbol_rows["selected_model_id"].astype(str).value_counts().sort_values(ascending=False).index[0]
            )
        rows.append(
            {
                "state_id": int(state_id),
                "dominant_symbol_model_id": dominant_symbol_model_id,
                "symbol_policy_coverage": float(len(symbol_rows) / symbol_count),
                "segment_model_ids": segment_rows["selected_model_id"].astype(str).tolist(),
                "global_model_id": str(global_rows.iloc[0]["selected_model_id"]) if not global_rows.empty else None,
                "fallback_model_id": "mean",
            }
        )
    return rows


def train_adaptive_router_artifacts(
    *,
    config: ResearchConfig,
    output_dir: str | Path,
    stock_profiles: list[StockProfile],
    params_snapshot: dict[str, Any],
    search_winners: dict[str, str] | None = None,
) -> dict[str, Any]:
    stock_payloads: list[dict[str, Any]] = []
    skipped_profiles: list[str] = []
    candidate_warnings: list[str] = []
    for profile in stock_profiles:
        try:
            payload = _collect_stock_payload(
                profile=profile,
                config=config,
                params_snapshot=params_snapshot,
            )
            stock_payloads.append(payload)
            candidate_warnings.extend(payload["warnings"])
        except Exception as exc:
            skipped_profiles.append(f"{profile.symbol}:{exc}")

    if not stock_payloads:
        raise ValueError("Adaptive router training could not collect any valid stock payloads.")

    train_feature_frames = [
        payload["feature_df"].iloc[: int(payload["split_idx"])][["date", *ADAPTIVE_STATE_FEATURE_COLUMNS]].copy()
        for payload in stock_payloads
    ]
    combined_train_features = pd.concat(train_feature_frames, ignore_index=True)
    training_bundle = train_adaptive_state_model(combined_train_features)
    classifier_bundle = training_bundle["classifier_bundle"]
    centroids_df = training_bundle["centroids_df"]
    labeled_feature_df = training_bundle["labeled_feature_df"]

    candidate_state_day_rows = _build_candidate_state_day_rows(stock_payloads, classifier_bundle)
    if candidate_state_day_rows.empty:
        raise ValueError("Adaptive router training could not build candidate state-day rows.")

    symbol_metrics_df = score_candidate_state_metrics(
        aggregate_candidate_state_day_rows(
            candidate_state_day_rows,
            scope_level="symbol",
            scope_key_column="symbol",
        )
    )
    segment_metrics_df = score_candidate_state_metrics(
        aggregate_candidate_state_day_rows(
            candidate_state_day_rows,
            scope_level="segment",
            scope_key_column="segment_key",
        )
    )
    global_metrics_df = score_candidate_state_metrics(
        aggregate_candidate_state_day_rows(
            candidate_state_day_rows,
            scope_level="global",
            scope_key_column=None,
        )
    )
    candidate_state_metrics_df = pd.concat(
        [symbol_metrics_df, segment_metrics_df, global_metrics_df],
        ignore_index=True,
    )

    routing_policy_df = select_routing_policy(
        candidate_state_metrics_df,
        min_state_days=ADAPTIVE_MIN_STATE_DAYS,
    )
    state_summary_rows = _build_state_summary_rows(
        labeled_feature_df=labeled_feature_df,
        centroids_df=centroids_df,
        routing_policy_df=routing_policy_df,
    )
    routing_summary_rows = _build_routing_summary_rows(routing_policy_df, stock_payloads)
    segment_bucket_rules = _segment_bucket_rules(stock_profiles, config)
    global_search_winners = {
        "sm_best_search": str((search_winners or {}).get("sm") or "sm"),
        "fsm_best_search": str((search_winners or {}).get("fsm") or "fsm"),
    }

    state_feature_schema = {
        "generated_from": config.name,
        "feature_columns": list(ADAPTIVE_STATE_FEATURE_COLUMNS),
        "state_count": int(classifier_bundle["state_count"]),
        "classifier_type": str(classifier_bundle["classifier_type"]),
        "market_proxy_symbol": "SPY",
        "min_state_days": int(ADAPTIVE_MIN_STATE_DAYS),
    }
    routing_policy_summary = {
        "generated_from": config.name,
        "feature_columns": list(ADAPTIVE_STATE_FEATURE_COLUMNS),
        "classifier_type": str(classifier_bundle["classifier_type"]),
        "state_count": int(classifier_bundle["state_count"]),
        "candidate_model_ids": list(ADAPTIVE_OFFLINE_CANDIDATE_MODEL_IDS),
        "segment_bucket_rules": segment_bucket_rules,
        "global_search_winners": global_search_winners,
        "state_summary": state_summary_rows,
        "routing_summary": routing_summary_rows,
        "routing_policy_scope_counts": normalize_distribution(routing_policy_df["scope_level"]) if not routing_policy_df.empty else {},
        "skipped_profiles": skipped_profiles,
        "candidate_warnings": candidate_warnings,
    }
    artifact_paths = save_adaptive_regime_artifacts(
        output_dir,
        classifier_bundle=classifier_bundle,
        centroids_df=centroids_df,
        routing_policy_df=routing_policy_df,
        routing_policy_summary=routing_policy_summary,
        candidate_state_metrics_df=candidate_state_metrics_df,
        state_feature_schema=state_feature_schema,
    )
    return {
        "artifact_paths": artifact_paths,
        "routing_policy_summary": routing_policy_summary,
        "candidate_state_metrics_df": candidate_state_metrics_df,
        "routing_policy_df": routing_policy_df,
    }


__all__ = [
    "ADAPTIVE_MODEL_ID",
    "train_adaptive_router_artifacts",
]
