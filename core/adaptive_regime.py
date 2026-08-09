"""
Adaptive regime router helpers
==============================
Shared offline/online utilities for the adaptive state classifier and
state-conditioned routing policy used by ``adaptive_router_v1`` /
``rsm_adaptive_v1``.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import pickle
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from core.regime_model import (
    DEFAULT_MARKET_PROXY_SYMBOL,
    _EFFICIENCY_WINDOW,
    _REGIME_LOOKBACK,
    _REALIZED_VOL_WINDOW,
    _build_feature_frame,
    build_market_proxy_frame,
)


ADAPTIVE_REGIME_KIND = "adaptive_router_v1"
ADAPTIVE_MODEL_ID = "rsm_adaptive_v1"
ADAPTIVE_ARTIFACT_DIRNAME = "regime_artifacts"
ADAPTIVE_ARTIFACT_ENV_VAR = "STRATAGY_ADAPTIVE_REGIME_ARTIFACT_DIR"
ADAPTIVE_STATE_COUNT = 6
ADAPTIVE_MIN_STATE_DAYS = 20
ADAPTIVE_LOOKBACK_DAYS = 252
ADAPTIVE_RANDOM_STATE = 42

ADAPTIVE_OFFLINE_CANDIDATE_MODEL_IDS = (
    "naive",
    "mean",
    "drift",
    "sm",
    "fsm",
    "sm_bayesian",
    "sm_random",
    "sm_genetic",
    "fsm_bayesian",
    "fsm_random",
    "fsm_genetic",
)

ADAPTIVE_ONLINE_DEFAULT_CANDIDATE_ALIASES = (
    "naive",
    "mean",
    "drift",
    "sm",
    "fsm",
    "sm_best_search",
    "fsm_best_search",
)

ADAPTIVE_ONLINE_FULL_CANDIDATE_ALIASES = (
    "naive",
    "mean",
    "drift",
    "sm",
    "fsm",
    "sm_bayesian",
    "sm_random",
    "sm_genetic",
    "fsm_bayesian",
    "fsm_random",
    "fsm_genetic",
)

ADAPTIVE_STATE_FEATURE_COLUMNS = (
    "ret_5",
    "ret_20",
    "ret_60",
    "spy_ret_5",
    "spy_ret_20",
    "spy_ret_60",
    "realized_vol_20",
    "realized_vol_60",
    "atr_pct",
    "ema_spread_pct",
    "adx",
    "rsi",
    "drawdown_rank",
    "bb_width_rank",
    "volume_ratio_rank",
    "efficiency_ratio_20",
    "relative_strength_vs_spy_20",
    "beta_60",
    "corr_60",
)

_ADAPTIVE_REQUIRED_ARTIFACTS = (
    "state_feature_schema.json",
    "state_cluster_centroids.csv",
    "state_classifier.pkl",
    "routing_policy.csv",
    "routing_policy_summary.json",
    "candidate_state_metrics.csv",
)

_ADAPTIVE_ARTIFACT_CACHE: dict[str, dict[str, Any]] = {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return float(default)
    return float(numeric)


def _compute_recent_profile(df: pd.DataFrame, lookback_days: int = ADAPTIVE_LOOKBACK_DAYS) -> dict[str, float | int | None]:
    numeric = df.copy()
    for column in ("close", "volume"):
        if column not in numeric.columns:
            return {
                "recent_days": 0,
                "total_return_1y": None,
                "annualized_vol_1y": None,
                "max_drawdown_1y": None,
                "avg_dollar_volume_1y": None,
            }
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    numeric = numeric.dropna(subset=["close", "volume"])
    if numeric.empty:
        return {
            "recent_days": 0,
            "total_return_1y": None,
            "annualized_vol_1y": None,
            "max_drawdown_1y": None,
            "avg_dollar_volume_1y": None,
        }

    recent = numeric.tail(int(lookback_days)).copy()
    if recent.empty:
        return {
            "recent_days": 0,
            "total_return_1y": None,
            "annualized_vol_1y": None,
            "max_drawdown_1y": None,
            "avg_dollar_volume_1y": None,
        }

    equity = recent["close"] / recent["close"].iloc[0]
    drawdown = (equity / equity.cummax()) - 1.0
    daily_return = recent["close"].pct_change().fillna(0.0)
    avg_dollar_volume = float((recent["close"] * recent["volume"]).mean())
    return {
        "recent_days": int(len(recent)),
        "total_return_1y": float(recent["close"].iloc[-1] / recent["close"].iloc[0] - 1.0),
        "annualized_vol_1y": float(daily_return.std(ddof=0) * math.sqrt(252.0)) if len(recent) > 1 else 0.0,
        "max_drawdown_1y": float(drawdown.min()) if not drawdown.empty else 0.0,
        "avg_dollar_volume_1y": avg_dollar_volume,
    }


def classify_segment_key(
    df: pd.DataFrame,
    bucket_rules: dict[str, Any] | None,
    *,
    lookback_days: int = ADAPTIVE_LOOKBACK_DAYS,
) -> str:
    if not bucket_rules:
        return "Unknown__Unknown"

    metrics = _compute_recent_profile(df, lookback_days=lookback_days)
    total_return = metrics.get("total_return_1y")
    annualized_vol = metrics.get("annualized_vol_1y")

    if total_return is None:
        trend_bucket = "Unknown"
    elif float(total_return) > float(bucket_rules.get("up_return_gt", 0.20)):
        trend_bucket = "Up"
    elif float(total_return) < float(bucket_rules.get("down_return_lt", -0.10)):
        trend_bucket = "Down"
    else:
        trend_bucket = "Flat"

    vol_q1 = bucket_rules.get("vol_q1")
    vol_q2 = bucket_rules.get("vol_q2")
    if annualized_vol is None or vol_q1 is None or vol_q2 is None:
        volatility_bucket = "Unknown"
    elif float(annualized_vol) <= float(vol_q1):
        volatility_bucket = "Low"
    elif float(annualized_vol) <= float(vol_q2):
        volatility_bucket = "Mid"
    else:
        volatility_bucket = "High"
    return f"{trend_bucket}__{volatility_bucket}"


def _rolling_beta(stock_returns: pd.Series, market_returns: pd.Series, window: int) -> pd.Series:
    covariance = stock_returns.rolling(window=window, min_periods=window).cov(market_returns)
    variance = market_returns.rolling(window=window, min_periods=window).var()
    return covariance / variance.replace(0, np.nan)


def build_adaptive_feature_frame(
    df: pd.DataFrame,
    *,
    adjust: str = "qfq",
    market_proxy_symbol: str = DEFAULT_MARKET_PROXY_SYMBOL,
    fetcher: Callable[[str, str, str], pd.DataFrame | None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    feature_df = _build_feature_frame(df)
    close = pd.to_numeric(feature_df["close"], errors="coerce")
    daily_return = close.pct_change()

    feature_df["ret_5"] = close.pct_change(5)
    feature_df["realized_vol_60"] = daily_return.rolling(window=_REGIME_LOOKBACK, min_periods=_REGIME_LOOKBACK).std() * np.sqrt(20.0)
    feature_df["relative_strength_vs_spy_20"] = 0.0
    feature_df["beta_60"] = 0.0
    feature_df["corr_60"] = 0.0

    metadata: dict[str, Any] = {
        "market_proxy_symbol": market_proxy_symbol,
        "market_proxy_mode": "enabled",
        "market_proxy_unavailable": False,
        "market_proxy_warning": None,
        "warning_messages": [],
    }

    market_proxy_df, proxy_metadata = build_market_proxy_frame(
        feature_df,
        adjust=adjust,
        market_proxy_symbol=market_proxy_symbol,
        fetcher=fetcher,
    )
    metadata.update(proxy_metadata)
    if market_proxy_df is None:
        feature_df["spy_ret_5"] = 0.0
        feature_df["spy_ret_20"] = 0.0
        feature_df["spy_ret_60"] = 0.0
        if proxy_metadata.get("market_proxy_warning"):
            metadata["warning_messages"].append(str(proxy_metadata["market_proxy_warning"]))
        return feature_df, metadata

    proxy_feature_df = _build_feature_frame(market_proxy_df, prefix="spy_")
    spy_close = pd.to_numeric(proxy_feature_df["close"], errors="coerce")
    proxy_feature_df["spy_ret_5"] = spy_close.pct_change(5)
    proxy_feature_df["spy_realized_vol_60"] = (
        spy_close.pct_change().rolling(window=_REGIME_LOOKBACK, min_periods=_REGIME_LOOKBACK).std() * np.sqrt(20.0)
    )
    proxy_feature_df["spy_daily_return"] = spy_close.pct_change()
    merge_columns = [
        "date",
        "spy_ret_5",
        "spy_ret_20",
        "spy_ret_60",
        "spy_daily_return",
    ]
    aligned_proxy = (
        proxy_feature_df[merge_columns]
        .set_index("date")
        .reindex(feature_df["date"])
        .ffill()
        .reset_index()
        .rename(columns={"index": "date"})
    )
    feature_df = feature_df.merge(aligned_proxy, on="date", how="left")
    feature_df["spy_ret_5"] = pd.to_numeric(feature_df["spy_ret_5"], errors="coerce").fillna(0.0)
    feature_df["spy_ret_20"] = pd.to_numeric(feature_df["spy_ret_20"], errors="coerce").fillna(0.0)
    feature_df["spy_ret_60"] = pd.to_numeric(feature_df["spy_ret_60"], errors="coerce").fillna(0.0)
    spy_daily_return = pd.to_numeric(feature_df["spy_daily_return"], errors="coerce")
    feature_df["relative_strength_vs_spy_20"] = (
        pd.to_numeric(feature_df["ret_20"], errors="coerce").fillna(0.0)
        - pd.to_numeric(feature_df["spy_ret_20"], errors="coerce").fillna(0.0)
    )
    feature_df["beta_60"] = _rolling_beta(daily_return, spy_daily_return, _REGIME_LOOKBACK)
    feature_df["corr_60"] = daily_return.rolling(window=_REGIME_LOOKBACK, min_periods=_REGIME_LOOKBACK).corr(spy_daily_return)
    feature_df = feature_df.drop(columns=["spy_daily_return"], errors="ignore")
    return feature_df, metadata


def get_adaptive_state_feature_columns() -> tuple[str, ...]:
    return ADAPTIVE_STATE_FEATURE_COLUMNS


def _prefer_lightgbm(sample_count: int, state_count: int) -> bool:
    return sample_count >= max(60, state_count * 12)


def _fit_state_classifier(features: pd.DataFrame, state_ids: np.ndarray) -> tuple[Any, str]:
    unique_state_count = int(len(np.unique(state_ids)))
    if unique_state_count <= 1:
        classifier = DummyClassifier(strategy="most_frequent")
        classifier.fit(features, state_ids)
        return classifier, "dummy"

    if _prefer_lightgbm(len(features), unique_state_count) and importlib.util.find_spec("lightgbm") is not None:
        try:
            from lightgbm import LGBMClassifier
            from core.lightgbm_runtime import lightgbm_runtime_params

            classifier = LGBMClassifier(
                objective="multiclass",
                num_class=unique_state_count,
                n_estimators=160,
                learning_rate=0.05,
                min_child_samples=10,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=ADAPTIVE_RANDOM_STATE,
                n_jobs=1,
                verbosity=-1,
                **lightgbm_runtime_params(),
            )
            classifier.fit(features, state_ids)
            return classifier, "lightgbm"
        except Exception:
            pass

    classifier = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1200,
                    random_state=ADAPTIVE_RANDOM_STATE,
                ),
            ),
        ]
    )
    classifier.fit(features, state_ids)
    return classifier, "logistic_regression"


def train_adaptive_state_model(
    feature_df: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...] = ADAPTIVE_STATE_FEATURE_COLUMNS,
    requested_state_count: int = ADAPTIVE_STATE_COUNT,
) -> dict[str, Any]:
    clean = feature_df[["date", *feature_columns]].dropna().reset_index(drop=True)
    if clean.empty:
        raise ValueError("Adaptive regime state model requires non-empty historical features.")
    if len(clean) < 12:
        raise ValueError("Adaptive regime state model requires at least 12 valid feature rows.")

    state_count = max(2, min(int(requested_state_count), int(len(clean))))
    kmeans = MiniBatchKMeans(
        n_clusters=state_count,
        batch_size=max(64, state_count * 16),
        random_state=ADAPTIVE_RANDOM_STATE,
        n_init=10,
    )
    feature_matrix = clean[list(feature_columns)]
    state_ids = kmeans.fit_predict(feature_matrix)
    classifier, classifier_type = _fit_state_classifier(feature_matrix, state_ids)

    labeled_feature_df = clean.copy()
    labeled_feature_df["state_id"] = state_ids.astype(int)
    state_counts = labeled_feature_df["state_id"].value_counts().sort_index()

    centroids_df = pd.DataFrame(kmeans.cluster_centers_, columns=feature_columns)
    centroids_df.insert(0, "state_id", range(state_count))
    centroids_df["sample_count"] = centroids_df["state_id"].map(state_counts).fillna(0).astype(int)
    centroids_df["sample_ratio"] = centroids_df["sample_count"] / max(int(state_counts.sum()), 1)

    classifier_bundle = {
        "classifier": classifier,
        "classifier_type": classifier_type,
        "feature_columns": list(feature_columns),
        "state_count": int(state_count),
        "random_state": ADAPTIVE_RANDOM_STATE,
    }
    return {
        "classifier_bundle": classifier_bundle,
        "labeled_feature_df": labeled_feature_df,
        "centroids_df": centroids_df,
    }


def predict_adaptive_states(feature_df: pd.DataFrame, classifier_bundle: dict[str, Any]) -> pd.Series:
    feature_columns = [str(column) for column in classifier_bundle.get("feature_columns", ADAPTIVE_STATE_FEATURE_COLUMNS)]
    classifier = classifier_bundle["classifier"]
    working = feature_df.copy()
    valid_mask = working[feature_columns].notna().all(axis=1)
    predicted = pd.Series(pd.NA, index=working.index, dtype="Int64")
    if not valid_mask.any():
        return predicted
    predicted.loc[valid_mask] = pd.Series(
        classifier.predict(working.loc[valid_mask, feature_columns]),
        index=working.index[valid_mask],
        dtype="int64",
    ).astype("Int64")
    return predicted


def _annualized_sharpe(returns: pd.Series) -> float:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    std = float(clean.std(ddof=0))
    if std <= 0:
        return 0.0
    return float(clean.mean() / std * math.sqrt(252.0))


def _max_drawdown_from_returns(returns: pd.Series) -> float:
    clean = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    if clean.empty:
        return 0.0
    equity = (1.0 + clean).cumprod()
    drawdown = (equity / equity.cummax()) - 1.0
    return float(drawdown.min()) if not drawdown.empty else 0.0


def aggregate_candidate_state_day_rows(
    day_rows: pd.DataFrame,
    *,
    scope_level: str,
    scope_key_column: str | None,
) -> pd.DataFrame:
    if day_rows.empty:
        return pd.DataFrame(
            columns=[
                "scope_level",
                "scope_key",
                "state_id",
                "model_id",
                "state_day_count",
                "excess_return",
                "sharpe",
                "max_drawdown",
            ]
        )

    working = day_rows.copy()
    if scope_key_column is None:
        working["scope_key"] = "global"
    else:
        working["scope_key"] = working[scope_key_column].astype(str)

    rows: list[dict[str, Any]] = []
    group_columns = ["scope_key", "state_id", "model_id"]
    for (scope_key, state_id, model_id), group in working.groupby(group_columns, dropna=False):
        strategy_returns = pd.to_numeric(group["strategy_return"], errors="coerce").fillna(0.0)
        benchmark_raw = (
            group["benchmark_return"]
            if "benchmark_return" in group.columns
            else pd.Series(0.0, index=group.index, dtype="float64")
        )
        benchmark_returns = pd.to_numeric(benchmark_raw, errors="coerce").fillna(0.0)
        rows.append(
            {
                "scope_level": scope_level,
                "scope_key": str(scope_key),
                "state_id": int(state_id),
                "model_id": str(model_id),
                "state_day_count": int(len(group)),
                "excess_return": float((strategy_returns - benchmark_returns).sum()),
                "sharpe": _annualized_sharpe(strategy_returns),
                "max_drawdown": _max_drawdown_from_returns(strategy_returns),
            }
        )
    return pd.DataFrame(rows)


def _rank_desc(series: pd.Series) -> pd.Series:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    output = pd.Series(0.0, index=series.index, dtype="float64")
    if valid.empty:
        return output
    ranked = valid.rank(method="average", pct=True, ascending=True) * 100.0
    output.loc[ranked.index] = ranked
    return output


def score_candidate_state_metrics(metrics_df: pd.DataFrame) -> pd.DataFrame:
    if metrics_df.empty:
        return metrics_df.copy()
    scored = metrics_df.copy()
    scored["excess_return_rank"] = 0.0
    scored["sharpe_rank"] = 0.0
    scored["drawdown_rank"] = 0.0
    scored["policy_score"] = 0.0

    for _, group_index in scored.groupby(["scope_level", "scope_key", "state_id"]).groups.items():
        partition = scored.loc[group_index]
        scored.loc[group_index, "excess_return_rank"] = _rank_desc(partition["excess_return"])
        scored.loc[group_index, "sharpe_rank"] = _rank_desc(partition["sharpe"])
        scored.loc[group_index, "drawdown_rank"] = _rank_desc(partition["max_drawdown"])

    scored["policy_score"] = (
        0.5 * scored["excess_return_rank"]
        + 0.3 * scored["sharpe_rank"]
        + 0.2 * scored["drawdown_rank"]
    )
    return scored


def select_routing_policy(
    metrics_df: pd.DataFrame,
    *,
    min_state_days: int = ADAPTIVE_MIN_STATE_DAYS,
) -> pd.DataFrame:
    if metrics_df.empty:
        return pd.DataFrame(
            columns=[
                "scope_level",
                "scope_key",
                "state_id",
                "selected_model_id",
                "state_day_count",
                "policy_score",
                "excess_return",
                "sharpe",
                "max_drawdown",
            ]
        )

    eligible = metrics_df[pd.to_numeric(metrics_df["state_day_count"], errors="coerce") >= int(min_state_days)].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "scope_level",
                "scope_key",
                "state_id",
                "selected_model_id",
                "state_day_count",
                "policy_score",
                "excess_return",
                "sharpe",
                "max_drawdown",
            ]
        )

    selected_rows: list[dict[str, Any]] = []
    for _, partition in eligible.groupby(["scope_level", "scope_key", "state_id"], dropna=False):
        top = partition.sort_values(
            ["policy_score", "excess_return", "sharpe", "max_drawdown", "model_id"],
            ascending=[False, False, False, False, True],
        ).iloc[0]
        selected_rows.append(
            {
                "scope_level": str(top["scope_level"]),
                "scope_key": str(top["scope_key"]),
                "state_id": int(top["state_id"]),
                "selected_model_id": str(top["model_id"]),
                "state_day_count": int(top["state_day_count"]),
                "policy_score": float(top["policy_score"]),
                "excess_return": float(top["excess_return"]),
                "sharpe": float(top["sharpe"]),
                "max_drawdown": float(top["max_drawdown"]),
            }
        )
    return pd.DataFrame(selected_rows)


def normalize_distribution(series: pd.Series, *, prefix: str | None = None) -> dict[str, float]:
    if series.empty:
        return {}
    normalized = series.astype("string").fillna("unknown").value_counts(normalize=True).sort_index()
    if prefix:
        return {f"{prefix}{key}": float(value) for key, value in normalized.items()}
    return {str(key): float(value) for key, value in normalized.items()}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _artifact_signature(artifact_dir: Path) -> str:
    summary_path = artifact_dir / "routing_policy_summary.json"
    if not summary_path.exists():
        return str(artifact_dir.resolve())
    stat = summary_path.stat()
    return f"{artifact_dir.resolve()}::{int(stat.st_mtime_ns)}::{int(stat.st_size)}"


def resolve_adaptive_artifact_dir(preferred_dir: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if preferred_dir is not None:
        path = Path(preferred_dir)
        if path.exists():
            candidates.append(path)

    env_path = os.environ.get(ADAPTIVE_ARTIFACT_ENV_VAR)
    if env_path:
        env_dir = Path(env_path)
        if env_dir.exists():
            candidates.append(env_dir)

    outputs_root = _repo_root() / "model-test" / "outputs"
    if outputs_root.exists():
        for summary_path in outputs_root.glob(f"*/{ADAPTIVE_ARTIFACT_DIRNAME}/routing_policy_summary.json"):
            candidates.append(summary_path.parent)

    if not candidates:
        return None
    unique_candidates = {
        candidate.resolve(): candidate.resolve()
        for candidate in candidates
        if candidate.exists()
    }
    if not unique_candidates:
        return None
    return max(
        unique_candidates.values(),
        key=lambda candidate: (candidate / "routing_policy_summary.json").stat().st_mtime_ns
        if (candidate / "routing_policy_summary.json").exists()
        else 0,
    )


def save_adaptive_regime_artifacts(
    output_dir: str | Path,
    *,
    classifier_bundle: dict[str, Any],
    centroids_df: pd.DataFrame,
    routing_policy_df: pd.DataFrame,
    routing_policy_summary: dict[str, Any],
    candidate_state_metrics_df: pd.DataFrame,
    state_feature_schema: dict[str, Any],
) -> dict[str, Path]:
    artifact_dir = Path(output_dir) / ADAPTIVE_ARTIFACT_DIRNAME
    artifact_dir.mkdir(parents=True, exist_ok=True)

    schema_path = artifact_dir / "state_feature_schema.json"
    centroids_path = artifact_dir / "state_cluster_centroids.csv"
    classifier_path = artifact_dir / "state_classifier.pkl"
    routing_policy_path = artifact_dir / "routing_policy.csv"
    summary_path = artifact_dir / "routing_policy_summary.json"
    metrics_path = artifact_dir / "candidate_state_metrics.csv"

    schema_path.write_text(json.dumps(state_feature_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    centroids_df.to_csv(centroids_path, index=False)
    with classifier_path.open("wb") as fh:
        pickle.dump(classifier_bundle, fh)
    routing_policy_df.to_csv(routing_policy_path, index=False)
    summary_path.write_text(json.dumps(routing_policy_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    candidate_state_metrics_df.to_csv(metrics_path, index=False)

    cache_key = _artifact_signature(artifact_dir)
    _ADAPTIVE_ARTIFACT_CACHE[cache_key] = {
        "artifact_dir": artifact_dir,
        "state_feature_schema": dict(state_feature_schema),
        "state_cluster_centroids": centroids_df.copy(),
        "state_classifier_bundle": dict(classifier_bundle),
        "routing_policy": routing_policy_df.copy(),
        "routing_policy_summary": dict(routing_policy_summary),
        "candidate_state_metrics": candidate_state_metrics_df.copy(),
    }
    return {
        "artifact_dir": artifact_dir,
        "state_feature_schema": schema_path,
        "state_cluster_centroids": centroids_path,
        "state_classifier": classifier_path,
        "routing_policy": routing_policy_path,
        "routing_policy_summary": summary_path,
        "candidate_state_metrics": metrics_path,
    }


def load_adaptive_regime_artifacts(preferred_dir: str | Path | None = None) -> dict[str, Any]:
    artifact_dir = resolve_adaptive_artifact_dir(preferred_dir)
    if artifact_dir is None:
        raise FileNotFoundError("Adaptive regime artifacts were not found.")

    missing = [name for name in _ADAPTIVE_REQUIRED_ARTIFACTS if not (artifact_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Adaptive regime artifacts are incomplete: " + ", ".join(sorted(missing))
        )

    cache_key = _artifact_signature(artifact_dir)
    cached = _ADAPTIVE_ARTIFACT_CACHE.get(cache_key)
    if cached is not None:
        return {
            "artifact_dir": cached["artifact_dir"],
            "state_feature_schema": dict(cached["state_feature_schema"]),
            "state_cluster_centroids": cached["state_cluster_centroids"].copy(),
            "state_classifier_bundle": dict(cached["state_classifier_bundle"]),
            "routing_policy": cached["routing_policy"].copy(),
            "routing_policy_summary": dict(cached["routing_policy_summary"]),
            "candidate_state_metrics": cached["candidate_state_metrics"].copy(),
        }

    schema = json.loads((artifact_dir / "state_feature_schema.json").read_text(encoding="utf-8"))
    summary = json.loads((artifact_dir / "routing_policy_summary.json").read_text(encoding="utf-8"))
    with (artifact_dir / "state_classifier.pkl").open("rb") as fh:
        classifier_bundle = pickle.load(fh)
    payload = {
        "artifact_dir": artifact_dir,
        "state_feature_schema": schema,
        "state_cluster_centroids": pd.read_csv(artifact_dir / "state_cluster_centroids.csv"),
        "state_classifier_bundle": classifier_bundle,
        "routing_policy": pd.read_csv(artifact_dir / "routing_policy.csv"),
        "routing_policy_summary": summary,
        "candidate_state_metrics": pd.read_csv(artifact_dir / "candidate_state_metrics.csv"),
    }
    _ADAPTIVE_ARTIFACT_CACHE[cache_key] = {
        "artifact_dir": artifact_dir,
        "state_feature_schema": dict(schema),
        "state_cluster_centroids": payload["state_cluster_centroids"].copy(),
        "state_classifier_bundle": dict(classifier_bundle),
        "routing_policy": payload["routing_policy"].copy(),
        "routing_policy_summary": dict(summary),
        "candidate_state_metrics": payload["candidate_state_metrics"].copy(),
    }
    return payload


__all__ = [
    "ADAPTIVE_ARTIFACT_DIRNAME",
    "ADAPTIVE_ARTIFACT_ENV_VAR",
    "ADAPTIVE_MIN_STATE_DAYS",
    "ADAPTIVE_MODEL_ID",
    "ADAPTIVE_OFFLINE_CANDIDATE_MODEL_IDS",
    "ADAPTIVE_ONLINE_DEFAULT_CANDIDATE_ALIASES",
    "ADAPTIVE_ONLINE_FULL_CANDIDATE_ALIASES",
    "ADAPTIVE_REGIME_KIND",
    "ADAPTIVE_STATE_COUNT",
    "ADAPTIVE_STATE_FEATURE_COLUMNS",
    "aggregate_candidate_state_day_rows",
    "build_adaptive_feature_frame",
    "classify_segment_key",
    "get_adaptive_state_feature_columns",
    "load_adaptive_regime_artifacts",
    "normalize_distribution",
    "predict_adaptive_states",
    "save_adaptive_regime_artifacts",
    "score_candidate_state_metrics",
    "select_routing_policy",
    "train_adaptive_state_model",
]
