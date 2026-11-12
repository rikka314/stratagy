"""Framework-neutral calculation and serialization services."""

from __future__ import annotations

import html
import json
import math
import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.config import STRATEGY_PRESETS
from core.data import load_uploaded_bytes
from core.portfolio import bayesian_optimize_portfolio, run_portfolio_simulation
from core.utils import get_available_stocks, load_or_fetch_stock
from ui.single_stock_workflow import (
    StrategyArtifact,
    StrategyRequest,
    build_strategy_context_key,
    freeze_params_snapshot,
    run_strategy_pipeline,
)

from .session import request_session_state


REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_DATASET_ROWS = 10_000
ALLOWED_PARAM_KEYS = {
    "strategy_preset", "ema_fast", "ema_slow", "macd_fast", "macd_slow", "macd_signal",
    "rsi_period", "rsi_lower", "rsi_upper", "adx_period", "adx_threshold", "atr_period",
    "bb_period", "bb_std", "indicator_period", "stop_loss_mult", "take_profit_mult",
    "momentum_short", "momentum_long", "score_lookback", "score_mid_pct", "score_high_pct",
    "weight_mom_short", "weight_mom_long", "weight_macd", "weight_rsi", "weight_vol",
    "weight_bb", "weight_obv", "weight_volume", "weight_price", "weight_drawdown",
    "entry_threshold", "exit_threshold", "entry_min_signals", "exit_min_signals",
    "use_trend_filter", "use_strength_filter", "use_rsi_filter", "use_macd_filter",
    "use_voting_entry", "entry_vote_threshold", "hold_until_exit", "hold_min_position",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_params() -> dict[str, Any]:
    preset = dict(STRATEGY_PRESETS["均衡策略（默认）"])
    preset.pop("description", None)
    preset.update({
        "strategy_preset": "均衡策略（默认）", "use_trend_filter": True,
        "use_strength_filter": True, "use_rsi_filter": True, "use_macd_filter": True,
        "use_voting_entry": False, "entry_vote_threshold": 2.5,
        "hold_until_exit": False, "hold_min_position": 0.2,
    })
    return preset


def validated_params(overrides: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(overrides) - ALLOWED_PARAM_KEYS)
    if unknown:
        raise ValueError(f"unsupported strategy params: {', '.join(unknown)}")
    params = default_params()
    params.update(overrides)
    numeric_ranges = {
        "ema_fast": (2, 200), "ema_slow": (3, 500), "macd_fast": (2, 100),
        "macd_slow": (3, 200), "macd_signal": (2, 100), "rsi_period": (2, 100),
        "rsi_lower": (0, 100), "rsi_upper": (0, 100), "adx_period": (2, 100),
        "adx_threshold": (0, 100), "atr_period": (2, 100), "bb_period": (2, 200),
        "bb_std": (0.1, 10), "indicator_period": (2, 250), "stop_loss_mult": (0, 20),
        "take_profit_mult": (0, 30), "momentum_short": (1, 100), "momentum_long": (2, 500),
        "score_lookback": (2, 500), "score_mid_pct": (0, 1), "score_high_pct": (0, 1),
        "entry_threshold": (-20, 20), "exit_threshold": (-20, 20), "entry_min_signals": (1, 10),
        "exit_min_signals": (1, 10), "entry_vote_threshold": (0, 10), "hold_min_position": (0, 1),
    }
    for key in ("weight_mom_short", "weight_mom_long", "weight_macd", "weight_rsi", "weight_vol", "weight_bb", "weight_obv", "weight_volume", "weight_price", "weight_drawdown"):
        numeric_ranges[key] = (0, 10)
    for key, (lower, upper) in numeric_ranges.items():
        value = params.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{key} must be a finite number")
        if not lower <= float(value) <= upper:
            raise ValueError(f"{key} must be between {lower} and {upper}")
    for key in ("use_trend_filter", "use_strength_filter", "use_rsi_filter", "use_macd_filter", "use_voting_entry", "hold_until_exit"):
        if not isinstance(params.get(key), bool):
            raise ValueError(f"{key} must be boolean")
    if float(params["ema_fast"]) >= float(params["ema_slow"]):
        raise ValueError("ema_fast must be less than ema_slow")
    if float(params["macd_fast"]) >= float(params["macd_slow"]):
        raise ValueError("macd_fast must be less than macd_slow")
    if float(params["rsi_lower"]) >= float(params["rsi_upper"]):
        raise ValueError("rsi_lower must be less than rsi_upper")
    if float(params["momentum_short"]) >= float(params["momentum_long"]):
        raise ValueError("momentum_short must be less than momentum_long")
    if float(params["score_mid_pct"]) >= float(params["score_high_pct"]):
        raise ValueError("score_mid_pct must be less than score_high_pct")
    return params


def normalize_market(value: str) -> str:
    return "CN_A" if str(value).upper() in {"A", "CN", "CN_A"} else "US"


def prepare_dataframe(df: pd.DataFrame, *, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("no valid market data returned")
    out = df.copy()
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in out.columns]
    if missing:
        raise ValueError(f"dataset is missing required columns: {', '.join(missing)}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in required[1:]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    if start_date:
        out = out[out["date"] >= pd.Timestamp(start_date)]
    if end_date:
        out = out[out["date"] <= pd.Timestamp(end_date)]
    if len(out) > MAX_DATASET_ROWS:
        raise ValueError(f"dataset exceeds {MAX_DATASET_ROWS} rows")
    if len(out) < 51:
        raise ValueError("dataset must contain at least 51 valid daily rows")
    if (out[["open", "high", "low", "close"]] <= 0).any().any() or (out["volume"] < 0).any():
        raise ValueError("OHLC prices must be positive and volume must be non-negative")
    if (out["high"] < out[["open", "low", "close"]].max(axis=1)).any() or (out["low"] > out[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("dataset contains inconsistent OHLC ranges")
    return out.reset_index(drop=True)


def json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.DataFrame):
        return records(value)
    if isinstance(value, pd.Series):
        return [json_value(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    return value


def records(df: pd.DataFrame | None, columns: list[str] | None = None, limit: int = 10_000) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    selected = df if columns is None else df[[col for col in columns if col in df.columns]]
    return [json_value(row) for row in selected.tail(limit).to_dict(orient="records")]


def series_points(series: pd.Series | None, *, value_key: str = "value", limit: int = 10_000) -> list[dict[str, Any]]:
    if series is None or series.empty:
        return []
    view = series.tail(limit)
    return [{"date": json_value(index), value_key: json_value(value)} for index, value in view.items()]


def dataset_summary(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    df = payload["dataframe"]
    return {
        "dataset_id": dataset_id, "symbol": payload["symbol"], "market": payload["market"],
        "adjust": payload["adjust"], "rows": len(df),
        "date_range": {"start": json_value(df["date"].min()), "end": json_value(df["date"].max())},
        "preview": records(df, ["date", "open", "high", "low", "close", "volume"], limit=8),
    }


def serialize_artifact(artifact: StrategyArtifact) -> dict[str, Any]:
    lineage = [{
        "stage_key": stage.stage_key, "display_label": stage.display_label, "short_label": stage.short_label,
        "metrics": json_value(stage.eval), "metadata": json_value(stage.metadata),
        "equity": series_points(stage.equity_series, value_key="equity"),
    } for stage in artifact.pipeline_lineage]
    return {
        "id": artifact.id, "context_key": artifact.context_key, "display_label": artifact.display_label,
        "request_signature": artifact.request_signature, "params": json_value(artifact.params_snapshot),
        "metrics": json_value(artifact.eval), "ml_quality": json_value(artifact.ml_quality),
        "equity": series_points(artifact.equity_series, value_key="equity"),
        "returns": series_points(artifact.returns_series, value_key="return"),
        "trades": records(artifact.trades_df), "signals": records(artifact.full_signal_df),
        "train": records(artifact.train_sim_df, ["date", "strategy_equity", "buy_hold_equity", "position"]),
        "test": records(artifact.test_sim_df, ["date", "strategy_equity", "buy_hold_equity", "position"]),
        "lineage": lineage,
    }


def run_single_calculation(dataset: dict[str, Any], request_payload: dict[str, Any], params_payload: dict[str, Any], train_ratio: float) -> dict[str, Any]:
    df = dataset["dataframe"].copy()
    params = validated_params(params_payload)
    request_data = dict(request_payload)
    # News files are server-owned. Clients cannot choose arbitrary filesystem paths.
    request_data["news_factor_path"] = None
    request = StrategyRequest(**request_data)
    split_idx = max(1, min(len(df) - 1, int(len(df) * train_ratio)))
    context_key = build_strategy_context_key(
        market=dataset["market"], symbol=dataset["symbol"], adjust=dataset["adjust"],
        df_raw=df, train_ratio=train_ratio, uploaded_file=object() if dataset.get("source") == "upload" else None,
    )
    with request_session_state():
        result = run_strategy_pipeline(
            context_key=context_key, request=request, request_params_snapshot=freeze_params_snapshot(params),
            df_raw=df, split_idx=split_idx, symbol=dataset["symbol"], market=dataset["market"], adjust=dataset["adjust"],
        )
    if result.artifact is None:
        raise ValueError(result.error_message or "strategy calculation failed")
    serialized = serialize_artifact(result.artifact)
    try:
        from .diagnostics import build_artifact_diagnostics
        serialized["diagnostics"] = json_value(build_artifact_diagnostics(result.artifact))
    except (ImportError, AttributeError):
        pass
    return {"status": result.status, "warnings": result.warnings, "info_messages": result.info_messages, "artifact": serialized}


def serialize_portfolio(result: dict[str, Any]) -> dict[str, Any]:
    from .portfolio_presentation import build_portfolio_presentation

    individual = {}
    for symbol, item in result["individual_results"].items():
        individual[symbol] = {
            "total_return": json_value(item["total_return"]), "sharpe": json_value(item["sharpe"]),
            "max_drawdown": json_value(item["max_dd"]),
            "returns": series_points(item["strategy_return"], value_key="return"),
        }
    return {
        "metrics": {
            "total_return": json_value(result["port_total_return"]), "sharpe": json_value(result["port_sharpe"]),
            "max_drawdown": json_value(result["port_max_dd"]), "benchmark_total_return": json_value(result["bh_total_return"]),
            "benchmark_sharpe": json_value(result["bh_sharpe"]), "benchmark_max_drawdown": json_value(result["bh_max_dd"]),
        },
        "weights": json_value(result["weights"]), "equity": series_points(result["portfolio_equity"], value_key="equity"),
        "benchmark": series_points(result["bh_equity"], value_key="equity"), "individual": individual,
        "presentation": build_portfolio_presentation(result),
    }


def run_portfolio_calculation(datasets: list[dict[str, Any]], params_payload: dict[str, Any], weights: dict[str, float] | None) -> dict[str, Any]:
    params = validated_params(params_payload)
    stock_data = {item["symbol"]: item["dataframe"].copy() for item in datasets}
    if len(stock_data) != len(datasets):
        raise ValueError("portfolio datasets must use distinct symbols")
    normalized_weights = None
    if weights is not None:
        normalized_weights = {}
        for item in datasets:
            dataset_id = item.get("dataset_id")
            symbol = item["symbol"]
            if dataset_id in weights:
                normalized_weights[symbol] = weights[dataset_id]
            elif symbol in weights:
                normalized_weights[symbol] = weights[symbol]
            else:
                normalized_weights[symbol] = 0.0
        if not math.isfinite(sum(normalized_weights.values())) or sum(normalized_weights.values()) <= 0:
            raise ValueError("weights do not match the requested dataset IDs or symbols")
    result = run_portfolio_simulation(stock_data, weights=normalized_weights, **params)
    if result is None:
        raise ValueError("portfolio calculation requires at least two usable datasets with overlapping dates")
    missing = set(stock_data) - set(result.get("individual_results", {}))
    if missing:
        raise ValueError(f"portfolio calculation failed for: {', '.join(sorted(missing))}")
    return serialize_portfolio(result)


def optimize_portfolio(datasets: list[dict[str, Any]], params_payload: dict[str, Any], n_trials: int) -> dict[str, Any]:
    params = validated_params(params_payload)
    stock_data = {item["symbol"]: item["dataframe"].copy() for item in datasets}
    if len(stock_data) != len(datasets):
        raise ValueError("portfolio datasets must use distinct symbols")
    result = bayesian_optimize_portfolio(stock_data, n_trials=n_trials, **params)
    if result is None:
        raise ValueError("portfolio optimization failed")
    # Verify the selected parameters against the whole requested universe: the
    # legacy optimizer can otherwise score a subset after an individual failure.
    selected_params = {**params, **{key: value for key, value in result.items() if key in ALLOWED_PARAM_KEYS}}
    verified = run_portfolio_simulation(stock_data, **selected_params)
    if verified is None or set(verified.get("individual_results", {})) != set(stock_data):
        raise ValueError("optimized portfolio could not evaluate every requested symbol")
    return json_value(result)


def research_catalog(query: str = "") -> dict[str, Any]:
    from ui.research_browser import ZH_RESEARCH_COPY
    payload = json.loads((REPO_ROOT / "research" / "RESEARCH_CATALOG.json").read_text(encoding="utf-8"))
    experiments = [{**item, 'localized_zh': ZH_RESEARCH_COPY.get(item.get('id'), {})}
                   for item in payload.get("experiments", [])]
    needle = " ".join(query.lower().split())
    if needle:
        experiments = [item for item in experiments if needle in json.dumps(item, ensure_ascii=False).lower()]
    return {"schema_version": payload.get("schema_version"), "experiments": experiments, "count": len(experiments)}


def research_report(experiment_id: str) -> dict[str, Any] | None:
    from .research_presentation import research_chart

    for item in research_catalog()["experiments"]:
        if item.get("id") != experiment_id:
            continue
        archive = (REPO_ROOT / str(item.get("archive_path", ""))).resolve()
        if REPO_ROOT not in archive.parents:
            return None
        readme = archive / "README.md"
        evidence = [{**entry, "available": (REPO_ROOT / entry["path"]).is_file()} for entry in item.get("evidence", [])]
        return {**item, "readme": readme.read_text(encoding="utf-8") if readme.is_file() else "", "evidence": evidence, "chart": research_chart(experiment_id)}
    return None


def simple_report_html(title: str, body: str, metadata: dict[str, Any] | None = None) -> str:
    meta = "".join(f"<dt>{html.escape(str(k))}</dt><dd>{html.escape(str(v))}</dd>" for k, v in (metadata or {}).items())
    return f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>{html.escape(title)}</title><style>body{{max-width:980px;margin:auto;padding:48px 24px;font:16px/1.7 system-ui;color:#201a17;background:#f5f0e8}}article{{background:#fff;padding:36px;border:1px solid #d8cbbb}}h1{{font-family:Georgia,serif}}pre{{white-space:pre-wrap}}dt{{font-weight:700}}dd{{margin:0 0 8px}}</style><article><h1>{html.escape(title)}</h1><dl>{meta}</dl><pre>{html.escape(body)}</pre></article></html>"""


def single_export_html(job: dict[str, Any], language: str = "zh") -> str:
    from .exporting import build_single_export

    return build_single_export(job, language)


def final_report(language: str) -> tuple[str, str]:
    lang = "zh" if language.lower().startswith("zh") else "en"
    path = REPO_ROOT / "reports" / ("Final_Report_zh.html" if lang == "zh" else "Final_Report.html")
    if not path.is_file():
        raise FileNotFoundError("final report is unavailable")
    return path.name, path.read_text(encoding="utf-8")


def experiment_snapshots() -> dict[str, Any]:
    if os.getenv("STRATAGY_RESEARCH_CONTROL") != "1":
        return {"enabled": False, "campaigns": []}
    model_test_root = REPO_ROOT / "model-test"
    if str(model_test_root) not in sys.path:
        sys.path.insert(0, str(model_test_root))
    from model_test.campaign import list_campaign_ids, load_campaign_snapshot
    campaigns = []
    for campaign_id in list_campaign_ids():
        snapshot = load_campaign_snapshot(campaign_id)
        campaigns.append(json_value(snapshot.to_dict() if hasattr(snapshot, "to_dict") else asdict(snapshot)))
    return {"enabled": True, "campaigns": campaigns}


def control_experiment(action: str, campaign_id: str | None = None) -> dict[str, Any]:
    if os.getenv("STRATAGY_RESEARCH_CONTROL") != "1":
        raise PermissionError("research control is disabled")
    model_test_root = REPO_ROOT / "model-test"
    if str(model_test_root) not in sys.path:
        sys.path.insert(0, str(model_test_root))
    from model_test.campaign import request_pause, resume_campaign, start_campaign
    if action == "start":
        snapshot = start_campaign(campaign_id)
    elif action == "pause" and campaign_id:
        snapshot = request_pause(campaign_id)
    elif action == "resume" and campaign_id:
        snapshot = resume_campaign(campaign_id)
    else:
        raise ValueError("invalid experiment control action")
    return json_value(snapshot.to_dict() if hasattr(snapshot, "to_dict") else asdict(snapshot))
