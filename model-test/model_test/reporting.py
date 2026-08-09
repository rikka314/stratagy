from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from model_test.config import build_config_search_budget_summary
from model_test.models import ResearchConfig


def _format_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.2f}%"


def _format_num(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.3f}"


def _family_summary(model_summary_df: pd.DataFrame) -> list[dict[str, Any]]:
    if model_summary_df.empty:
        return []
    summary_rows: list[dict[str, Any]] = []
    for family_name, frame in model_summary_df.groupby("family_group", sort=False):
        top = frame.sort_values("total_score", ascending=False).iloc[0]
        summary_rows.append(
            {
                "family_group": family_name,
                "model_count": int(len(frame)),
                "avg_total_score": float(frame["total_score"].mean()),
                "top_model_id": top["model_id"],
                "top_display_name": top["display_name"],
                "top_total_score": float(top["total_score"]),
            }
        )
    return summary_rows


def _search_method_summary(model_summary_df: pd.DataFrame) -> list[dict[str, Any]]:
    if model_summary_df.empty:
        return []
    methods = []
    for method in ("bayesian", "random", "genetic"):
        frame = model_summary_df[model_summary_df["model_id"].str.endswith(method, na=False)].copy()
        if frame.empty:
            continue
        top = frame.sort_values("total_score", ascending=False).iloc[0]
        methods.append(
            {
                "method": method,
                "model_count": int(len(frame)),
                "avg_total_score": float(frame["total_score"].mean()),
                "top_model_id": top["model_id"],
                "top_display_name": top["display_name"],
                "top_total_score": float(top["total_score"]),
            }
        )
    return methods


def _ml_gain_summary(model_summary_df: pd.DataFrame) -> list[dict[str, Any]]:
    if model_summary_df.empty:
        return []
    lookup = model_summary_df.set_index("model_id")
    gains: list[dict[str, Any]] = []
    for row in model_summary_df.itertuples(index=False):
        model_id = str(row.model_id)
        if "_ml_" not in model_id:
            continue
        parent_id = model_id.split("_ml_", 1)[0]
        if parent_id not in lookup.index:
            continue
        parent = lookup.loc[parent_id]
        gains.append(
            {
                "model_id": model_id,
                "display_name": row.display_name,
                "parent_model_id": parent_id,
                "parent_display_name": parent["display_name"],
                "score_delta": float(row.total_score - parent["total_score"]),
                "excess_return_delta": float((row.median_excess_return or 0.0) - (parent["median_excess_return"] or 0.0)),
                "sharpe_delta": float((row.median_sharpe or 0.0) - (parent["median_sharpe"] or 0.0)),
            }
        )
    return gains


def build_report_payload(
    *,
    config: ResearchConfig,
    stocks_df: pd.DataFrame,
    model_summary_df: pd.DataFrame,
    segment_summary_df: pd.DataFrame,
    robustness_df: pd.DataFrame,
    records_df: pd.DataFrame,
    stage_winners: dict[str, str],
    quantstats_entries: list[dict[str, Any]] | None = None,
    adaptive_router_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    failure_mask = records_df["status"].isin(["failed", "degraded", "SKIPPED"]) if not records_df.empty else pd.Series([], dtype=bool)
    failures_df = records_df.loc[failure_mask].copy() if not records_df.empty else pd.DataFrame()

    highlighted_segments = pd.DataFrame()
    if not segment_summary_df.empty:
        highlighted_segments = segment_summary_df[
            segment_summary_df["suitability"].isin(["suitable", "not_suitable"])
        ].sort_values(["suitability", "total_score"], ascending=[True, False])

    robustness_in_total = bool(
        config.robustness_weight > 0
        and not robustness_df.empty
        and "robustness_total_score" in model_summary_df.columns
        and model_summary_df["robustness_total_score"].notna().any()
    )
    robustness_model_count = int(model_summary_df["robustness_total_score"].notna().sum()) if "robustness_total_score" in model_summary_df.columns else 0
    total_model_count = int(len(model_summary_df))
    search_budget = build_config_search_budget_summary(config)

    payload = {
        "generated_at": generated_at,
        "config": config.to_dict(),
        "search_budget": search_budget,
        "score_policy": {
            "robustness_in_total_score": robustness_in_total,
            "main_weight": float(1.0 - config.robustness_weight) if robustness_in_total else 1.0,
            "robustness_weight": float(config.robustness_weight) if robustness_in_total else 0.0,
            "robustness_model_count": robustness_model_count,
            "total_model_count": total_model_count,
        },
        "pool": {
            "stock_count": int(len(stocks_df)),
            "segment_counts": stocks_df["segment_key"].value_counts(dropna=False).to_dict() if not stocks_df.empty else {},
            "symbols": stocks_df["symbol"].tolist() if not stocks_df.empty else [],
        },
        "stage_winners": stage_winners,
        "top_models": model_summary_df.head(5).to_dict("records"),
        "model_summary": model_summary_df.to_dict("records"),
        "family_summary": _family_summary(model_summary_df),
        "search_method_summary": _search_method_summary(model_summary_df),
        "ml_gain": _ml_gain_summary(model_summary_df),
        "segment_highlights": highlighted_segments.head(20).to_dict("records") if not highlighted_segments.empty else [],
        "quantstats": list(quantstats_entries or []),
        "robustness_summary": robustness_df.to_dict("records"),
        "failures": failures_df.head(50).to_dict("records") if not failures_df.empty else [],
        "adaptive_router": dict(adaptive_router_summary or {}),
    }
    return payload


def build_market_strategy_payload(
    *,
    config: ResearchConfig,
    run_id: str,
    matrix_df: pd.DataFrame,
    recommendations: dict[str, Any],
    source_manifests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Create a traceable comparison payload without changing single-market reports."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": config.to_dict(),
        "run_id": run_id,
        "market_strategy": {
            "matrix": matrix_df.to_dict("records"),
            "recommendations": recommendations,
            "source_manifests": source_manifests,
        },
    }


def render_market_strategy_markdown(payload: dict[str, Any]) -> str:
    strategy = dict(payload.get("market_strategy") or {})
    recommendations = dict(strategy.get("recommendations") or {})
    markets = dict(recommendations.get("markets") or {})
    shared_benchmark = dict(recommendations.get("shared_benchmark") or {})
    manifests = dict(strategy.get("source_manifests") or {})
    lines = [
        "# Market Strategy Research Report",
        "",
        f"- Comparison run ID: `{payload.get('run_id', 'unknown')}`",
        f"- Generated at: `{payload.get('generated_at', 'unknown')}`",
        "",
        "## Source Manifests",
    ]
    for market in ("US", "CN_A"):
        source = dict(manifests.get(market) or {})
        lines.append(
            f"- `{market}`: `{source.get('path', 'unavailable')}` "
            f"(source run `{source.get('run_id', 'unavailable')}`, "
            f"cost `{_format_num(source.get('commission_bps'))} + "
            f"{_format_num(source.get('slippage_bps'))} bps`)"
        )

    lines.extend(
        [
            "",
            "## Decision Rule",
            "- Each market selects from every strategy validated for that market; a strategy does not need to be supported by the other market.",
            "- The separate shared benchmark uses only common candidates for method-level US/CN_A comparison.",
            "- Candidates must beat Naive after costs, meet coverage and degradation gates, and have positive rolling-window direction consistency.",
            "- Near-ties are reported as insufficient evidence instead of forcing a winner.",
            "",
            "## Market-Specific Recommendations",
        ]
    )
    for market in ("US", "CN_A"):
        entry = dict(markets.get(market) or {})
        recommendation = entry.get("recommendation") or "none"
        confidence = entry.get("confidence") or "insufficient_evidence"
        lines.append(f"### {market}")
        lines.append(f"- Recommendation: `{recommendation}`")
        lines.append(f"- Confidence: `{confidence}`")
        evidence = dict(entry.get("evidence") or {})
        matrix_rows = evidence.get("matrix_rows") or []
        if matrix_rows:
            row_references = [
                f"{item.get('market')}/{item.get('strategy_id')}/{item.get('evaluation_window')}"
                if isinstance(item, dict) else str(item)
                for item in matrix_rows
            ]
            lines.append(f"- Matrix rows used: `{', '.join(row_references)}`")
        else:
            lines.append("- Matrix rows used: none; insufficient evidence.")
        metrics = dict(evidence.get("metrics") or {})
        if metrics:
            lines.append(
                f"- Evidence: {int(metrics.get('valid_symbol_count', 0))} valid symbols, "
                f"coverage {_format_pct(metrics.get('coverage_rate'))}, "
                f"median excess return {_format_pct(metrics.get('median_excess_return'))}, "
                f"Naive win rate {_format_pct(metrics.get('naive_win_rate'))}, "
                f"rolling consistency {_format_pct(metrics.get('rolling_direction_consistency'))}."
            )
        for limitation in entry.get("limitations") or []:
            lines.append(f"- Limitation: {limitation}")

    lines.extend(["", "## Shared-Candidate Benchmark"])
    eligible = shared_benchmark.get("eligible_strategy_ids") or []
    lines.append(f"- Common candidate set: `{', '.join(eligible) if eligible else 'none'}`")
    shared_markets = dict(shared_benchmark.get("markets") or {})
    for market in ("US", "CN_A"):
        entry = dict(shared_markets.get(market) or {})
        lines.append(
            f"- `{market}` common-set result: `{entry.get('recommendation') or 'none'}` "
            f"({entry.get('confidence') or 'insufficient_evidence'})."
        )

    lines.extend(["", "## Strategy Matrix"])
    matrix_rows = strategy.get("matrix") or []
    if matrix_rows:
        for row in matrix_rows:
            lines.append(
                f"- `{row.get('market')}` / `{row.get('strategy_id')}` / "
                f"`{row.get('evaluation_window')}`: coverage {_format_pct(row.get('coverage_rate'))}, "
                f"net return {_format_pct(row.get('net_total_return'))}, Sharpe {_format_num(row.get('sharpe'))}."
            )
    else:
        lines.append("- No strategy matrix rows were available.")
    return "\n".join(lines) + "\n"


def render_report_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    config = payload["config"]
    search_budget = payload.get("search_budget", {})
    score_policy = payload.get("score_policy", {})
    top_models = payload.get("top_models", [])
    family_summary = payload.get("family_summary", [])
    search_method_summary = payload.get("search_method_summary", [])
    ml_gain = payload.get("ml_gain", [])
    segment_highlights = payload.get("segment_highlights", [])
    quantstats_entries = payload.get("quantstats", [])
    robustness_summary = payload.get("robustness_summary", [])
    failures = payload.get("failures", [])
    adaptive_router = payload.get("adaptive_router", {})

    lines.append(f"# {config['name']} Research Report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Market: `{config['market']}`")
    lines.append(f"- Pool size: `{payload['pool']['stock_count']}`")
    if search_budget:
        lines.append(
            f"- Search budget: random/bayesian `{int(search_budget['random_trials'])}` trials; "
            f"genetic `{int(search_budget['ga_population_size'])} x "
            f"({int(search_budget['ga_generations'])} + 1) = {int(search_budget['ga_total_evals'])}` "
            f"objective evals; fixed seed `{int(search_budget['search_seed'])}`."
        )
        if search_budget.get("uniform_objective_budget"):
            lines.append(
                f"- Effective search budget: `{int(search_budget['effective_search_budget'])}` objective evals "
                "for all search methods."
            )
    if score_policy.get("robustness_in_total_score"):
        lines.append(
            f"- Final score rule: `{score_policy['main_weight']:.0%}` main-window score + "
            f"`{score_policy['robustness_weight']:.0%}` rolling robustness score "
            "for models with robustness runs."
        )
        if score_policy.get("robustness_model_count", 0) < score_policy.get("total_model_count", 0):
            lines.append(
                f"- Current robustness coverage: `{score_policy['robustness_model_count']}` / "
                f"`{score_policy['total_model_count']}` models already have rolling-window records."
            )
    lines.append("")
    lines.append("## 1. Overall Ranking And Top 5 Conclusions")
    if top_models:
        for row in top_models:
            score_note = f"score {_format_num(row['total_score'])}"
            main_total_score = row.get("main_total_score")
            robustness_total_score = row.get("robustness_total_score")
            if main_total_score is not None and not pd.isna(main_total_score):
                score_note += f" (main {_format_num(main_total_score)}"
                if robustness_total_score is not None and not pd.isna(robustness_total_score):
                    score_note += f", robustness {_format_num(robustness_total_score)})"
                else:
                    score_note += ", no rolling robustness)"
            lines.append(
                f"- `{row['display_name']}`: {score_note}, "
                f"beat naive {_format_pct(row['beat_naive_rate'])}, "
                f"median sharpe {_format_num(row['median_sharpe'])}, "
                f"median excess return {_format_pct(row['median_excess_return'])}."
            )
    else:
        lines.append("- No main-window model summary was generated.")
    if robustness_summary:
        best_robust = robustness_summary[0]
        lines.append(
            f"- Rolling-window review: `{best_robust['display_name']}` leads with "
            f"robustness score {_format_num(best_robust.get('robustness_total_score'))}, "
            f"median sharpe {_format_num(best_robust['median_sharpe'])} across robustness windows."
        )
    else:
        lines.append("- Rolling-window review was not run or produced no valid records.")

    lines.append("")
    lines.append("## 2. Baseline Vs Search Family Conclusions")
    if family_summary:
        for row in family_summary:
            lines.append(
                f"- `{row['family_group']}`: {row['model_count']} models, "
                f"avg score {_format_num(row['avg_total_score'])}, "
                f"best `{row['top_display_name']}` at {_format_num(row['top_total_score'])}."
            )
    else:
        lines.append("- No family-level comparison was available.")

    lines.append("")
    lines.append("## 3. Search Method Horizontal Review")
    if search_method_summary:
        winners = payload.get("stage_winners", {})
        for row in search_method_summary:
            winner_note = ""
            if row["top_model_id"] in winners.values():
                winner_note = " Selected for Stage B."
            lines.append(
                f"- `{row['method']}`: avg score {_format_num(row['avg_total_score'])}, "
                f"best `{row['top_display_name']}` at {_format_num(row['top_total_score'])}.{winner_note}"
            )
    else:
        lines.append("- Search-method comparison was not available.")

    lines.append("")
    lines.append("## 4. ML Gain Conclusions")
    if ml_gain:
        for row in ml_gain:
            lines.append(
                f"- `{row['display_name']}` vs `{row['parent_display_name']}`: "
                f"score delta {_format_num(row['score_delta'])}, "
                f"excess return delta {_format_pct(row['excess_return_delta'])}, "
                f"sharpe delta {_format_num(row['sharpe_delta'])}."
            )
    else:
        lines.append("- Stage B ML expansion was not run or yielded no comparable models.")

    lines.append("")
    lines.append("## 5. Adaptive Regime State Summary")
    if adaptive_router.get("state_summary"):
        for row in adaptive_router["state_summary"]:
            top_features = ", ".join(row.get("top_features") or [])
            lines.append(
                f"- `state_{int(row['state_id'])}`: sample ratio {_format_pct(row.get('sample_ratio'))}, "
                f"dominant global model `{row.get('dominant_global_model_id') or 'n/a'}`, "
                f"top features `{top_features}`."
            )
    else:
        lines.append("- Adaptive regime artifacts were not generated in this run.")

    lines.append("")
    lines.append("## 6. Adaptive Routing Summary")
    if adaptive_router.get("routing_summary"):
        for row in adaptive_router["routing_summary"]:
            lines.append(
                f"- `state_{int(row['state_id'])}`: dominant symbol model `{row.get('dominant_symbol_model_id') or 'n/a'}`, "
                f"symbol coverage {_format_pct(row.get('symbol_policy_coverage'))}, "
                f"global fallback `{row.get('global_model_id') or 'n/a'}`."
            )
    else:
        lines.append("- Adaptive routing summary was not available.")

    lines.append("")
    lines.append("## 7. Segment Suitability Conclusions")
    if segment_highlights:
        for row in segment_highlights[:12]:
            lines.append(
                f"- `{row['display_name']}` in `{row['segment_key']}`: `{row['suitability']}`, "
                f"score {_format_num(row['total_score'])}, sample `{int(row['valid_count'])}`, "
                f"beat naive {_format_pct(row['beat_naive_rate'])}."
            )
    else:
        lines.append("- No segment reached the threshold for explicit suitability conclusions.")

    lines.append("")
    lines.append("## 8. QuantStats Tear Sheets")
    if quantstats_entries:
        for row in quantstats_entries[:10]:
            score_note = _format_num(row.get("total_score"))
            lines.append(
                f"- `{row['display_name']}`: rank `{int(row['rank'])}`, pooled `{int(row['selected_record_count'])}` "
                f"main-window runs, score {score_note}, tear sheet `{row['quantstats_html_path']}`."
            )
    else:
        lines.append("- QuantStats tear sheets were not generated.")

    lines.append("")
    lines.append("## 9. Failed Degraded And Abnormal Samples Appendix")
    if failures:
        for row in failures[:20]:
            message = row.get("error_message") or row.get("warnings_json") or "n/a"
            lines.append(
                f"- `{row['model_id']}` / `{row['symbol']}` / `{row['window_id']}` -> `{row['status']}`: {message}"
            )
    else:
        lines.append("- No failed, degraded, or skipped records were captured.")

    lines.append("")
    return "\n".join(lines)
