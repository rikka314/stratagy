"""Pure W17 five-day execution and attribution for Transformer-state decisions.

The module consumes W16 decision rows and the source-locked expert daily
panel.  It deliberately has no artifact or runner I/O.  Expert
``strategy_return`` is already net of source execution costs; the W17
turnover calculation is an audit metric and never recharges those costs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


class TransformerStateExecutionError(ValueError):
    """Raised when W17 cannot produce exact, auditable execution evidence."""


@dataclass(frozen=True)
class ExecutionConfig:
    holding_days: int
    matching_frequency_days: int
    jump_down_atr_multiple: float
    entry_drawdown_atr_multiple: float
    market_crash_return: float
    fallback_expert_ids: Mapping[str, str]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionConfig":
        execution = payload.get("execution", payload)
        guard = payload.get("selected_jump_guard", execution.get("selected_jump_guard", {}))
        fallbacks = payload.get("fallback_expert_ids", execution.get("fallback_expert_ids", {}))
        required_fallbacks = {"full_run_best_guard", "adaptive_guard", "cash_on_unmatched"}
        missing_fallbacks = sorted(required_fallbacks - set(fallbacks))
        if missing_fallbacks:
            raise TransformerStateExecutionError(
                f"execution config is missing fallback expert ids: {missing_fallbacks}"
            )
        if execution.get("jump_guard_selection") != "validation_only":
            raise TransformerStateExecutionError("jump guard selection must be frozen on validation_only")
        try:
            config = cls(
                holding_days=int(execution["holding_days"]),
                matching_frequency_days=int(execution["matching_frequency_days"]),
                jump_down_atr_multiple=float(guard["single_day_jump_down_atr_multiple"]),
                entry_drawdown_atr_multiple=float(guard["entry_drawdown_atr_multiple"]),
                market_crash_return=float(guard["market_crash_return"]),
                fallback_expert_ids={key: str(value) for key, value in fallbacks.items()},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TransformerStateExecutionError("execution config has incomplete frozen W17 values") from exc
        if config.holding_days <= 0 or config.matching_frequency_days <= 0:
            raise TransformerStateExecutionError("holding and matching frequency days must be positive")
        guard_values = np.asarray(
            [
                config.jump_down_atr_multiple,
                config.entry_drawdown_atr_multiple,
                config.market_crash_return,
            ],
            dtype=float,
        )
        if not np.isfinite(guard_values).all():
            raise TransformerStateExecutionError("jump guard values must be finite")
        if config.jump_down_atr_multiple <= 0 or config.entry_drawdown_atr_multiple <= 0:
            raise TransformerStateExecutionError("jump guard ATR multiples must be positive")
        if config.market_crash_return >= 0:
            raise TransformerStateExecutionError("market crash return must be negative")
        return config


@dataclass(frozen=True)
class ExecutionResult:
    daily_audit: pd.DataFrame
    summary: pd.DataFrame
    skipped_decisions: pd.DataFrame


_DECISION_KEYS = ["split_id", "date", "symbol", "market", "threshold"]
_PANEL_KEYS = ["date", "symbol", "market", "expert_id"]
_VARIANTS = ("full_run_best_guard", "adaptive_guard", "cash_on_unmatched", "full_run_best_only")
_SUMMARY_KEYS = ["split_id", "market", "symbol", "regime", "threshold", "variant"]


def execute_state_decisions(
    decisions: pd.DataFrame,
    expert_daily_panel: pd.DataFrame,
    *,
    config: Mapping[str, Any] | ExecutionConfig,
) -> ExecutionResult:
    """Execute non-overlapping future five-day windows for every W17 variant."""

    resolved = config if isinstance(config, ExecutionConfig) else ExecutionConfig.from_mapping(config)
    decision_frame = _validate_decisions(decisions)
    panel = _validate_panel(expert_daily_panel)
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for keys, group in decision_frame.groupby(
        ["split_id", "symbol", "market", "threshold"], sort=True, dropna=False
    ):
        split_id, symbol, market, threshold = keys
        symbol_panel = panel.loc[
            panel["symbol"].eq(symbol) & panel["market"].eq(market)
        ].copy()
        calendar = pd.Index(symbol_panel["date"].drop_duplicates().sort_values())
        date_to_index = {date: index for index, date in enumerate(calendar)}
        if not all(date in date_to_index for date in group["date"]):
            raise TransformerStateExecutionError("every decision date must exist in the expert daily panel")
        for variant in _VARIANTS:
            next_eligible_index = -1
            for decision in group.sort_values("date", kind="stable").itertuples(index=False):
                decision_index = date_to_index[pd.Timestamp(decision.date)]
                if decision_index < next_eligible_index:
                    skipped.append(
                        {
                            "split_id": str(split_id),
                            "date": pd.Timestamp(decision.date),
                            "symbol": str(symbol),
                            "market": str(market),
                            "threshold": str(threshold),
                            "variant": variant,
                            "skip_reason": "holding_window_active",
                        }
                    )
                    continue
                effective_dates = list(calendar[decision_index + 1 : decision_index + 1 + resolved.holding_days])
                if len(effective_dates) != resolved.holding_days:
                    skipped.append(
                        {
                            "split_id": str(split_id),
                            "date": pd.Timestamp(decision.date),
                            "symbol": str(symbol),
                            "market": str(market),
                            "threshold": str(threshold),
                            "variant": variant,
                            "skip_reason": "insufficient_future_days",
                        }
                    )
                    continue
                # Frequency is measured on the symbol's own trading calendar.  A
                # new decision may be observed at the close of the fifth holding
                # day and becomes effective on the following trading day.
                next_eligible_index = decision_index + max(
                    resolved.matching_frequency_days, len(effective_dates)
                )
                rows.extend(
                    _execute_window(
                        decision,
                        effective_dates,
                        symbol_panel,
                        resolved,
                        variant=variant,
                    )
                )

    daily = pd.DataFrame(rows)
    if daily.empty:
        raise TransformerStateExecutionError("no executable five-day decision window was produced")
    daily = daily.sort_values(
        ["split_id", "threshold", "variant", "symbol", "date"], kind="stable"
    ).reset_index(drop=True)
    previous = daily.groupby(["split_id", "threshold", "variant", "symbol"], sort=False)[
        "target_position"
    ].shift(1).fillna(0.0)
    daily["execution_turnover"] = (daily["target_position"] - previous).abs()
    with np.errstate(over="ignore", invalid="ignore"):
        daily["equity_before"] = daily.groupby(
            ["split_id", "threshold", "variant", "symbol"], sort=False
        )["strategy_return"].transform(
            lambda values: (1.0 + values).cumprod().shift(1).fillna(1.0)
        )
        daily["geometric_return_contribution"] = daily["equity_before"] * daily["strategy_return"]
    control = daily.loc[daily["variant"].eq("full_run_best_only"), [
        "split_id", "date", "symbol", "market", "threshold", "strategy_return"
    ]].rename(columns={"strategy_return": "full_run_best_only_return"})
    daily = daily.merge(
        control,
        on=["split_id", "date", "symbol", "market", "threshold"],
        how="left",
        validate="many_to_one",
    )
    if daily["full_run_best_only_return"].isna().any():
        raise TransformerStateExecutionError("full_run_best_only daily control could not be reconstructed")
    operational_columns = [
        "strategy_return",
        "target_position",
        "decision_target_position",
        "source_expert_strategy_return",
        "source_expert_target_position",
        "counterfactual_no_guard_return",
        "adaptive_return",
        "execution_turnover",
        "equity_before",
        "geometric_return_contribution",
        "full_run_best_only_return",
    ]
    operational = daily[operational_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(operational.to_numpy(dtype=np.float64)).all():
        raise TransformerStateExecutionError("daily execution outputs must be finite")
    summary = reconstruct_execution_summary(daily)
    assert_summary_reconstructs(daily, summary)
    skipped_frame = pd.DataFrame(
        skipped,
        columns=["split_id", "date", "symbol", "market", "threshold", "variant", "skip_reason"],
    )
    return ExecutionResult(daily_audit=daily, summary=summary, skipped_decisions=skipped_frame)


def _validate_decisions(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    if "threshold" not in frame:
        for alias in ("threshold_variant", "threshold_name", "variant"):
            if alias in frame:
                frame["threshold"] = frame[alias]
                break
    if "match_status" not in frame and "decision_status" in frame:
        frame["match_status"] = np.where(
            frame["decision_status"].astype(str).eq("matched"), "matched", "unmatched"
        )
    required = set(_DECISION_KEYS) | {"match_status", "selected_expert_id"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise TransformerStateExecutionError(f"W16 decisions are missing required columns: {missing}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if out.empty or out["date"].isna().any():
        raise TransformerStateExecutionError("W16 decisions contain no rows or an invalid date")
    if out.duplicated(_DECISION_KEYS).any():
        raise TransformerStateExecutionError("W16 decision keys must be unique")
    statuses = out["match_status"].astype(str)
    if not statuses.isin(["matched", "unmatched"]).all():
        raise TransformerStateExecutionError("match_status must be matched or unmatched")
    matched = statuses.eq("matched")
    if out.loc[matched, "selected_expert_id"].isna().any():
        raise TransformerStateExecutionError("matched decisions require selected_expert_id")
    return out.sort_values(_DECISION_KEYS, kind="stable").reset_index(drop=True)


def _validate_panel(frame: pd.DataFrame) -> pd.DataFrame:
    required = set(_PANEL_KEYS) | {
        "expert_status",
        "strategy_return",
        "target_position",
        "close",
        "asset_return_1",
        "atr_pct",
        "benchmark_return",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise TransformerStateExecutionError(f"expert daily panel is missing required columns: {missing}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if out.empty or out["date"].isna().any():
        raise TransformerStateExecutionError("expert daily panel contains no rows or an invalid date")
    if out.duplicated(_PANEL_KEYS).any():
        raise TransformerStateExecutionError("expert daily panel keys must be unique")
    for column in ("strategy_return", "target_position", "close", "asset_return_1", "atr_pct", "benchmark_return"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if "future_utility" in out:
        out["future_utility"] = pd.to_numeric(out["future_utility"], errors="coerce")
    if "regime" not in out:
        out["regime"] = "unknown"
    return out.sort_values(_PANEL_KEYS, kind="stable").reset_index(drop=True)


def _execute_window(
    decision: Any,
    effective_dates: Sequence[pd.Timestamp],
    panel: pd.DataFrame,
    config: ExecutionConfig,
    *,
    variant: str,
) -> list[dict[str, Any]]:
    matched = str(decision.match_status) == "matched"
    full_run_best_expert = getattr(decision, "full_run_best_execution_expert_id", None)
    if (
        full_run_best_expert is None
        or pd.isna(full_run_best_expert)
        or not str(full_run_best_expert).strip()
    ):
        full_run_best_expert = config.fallback_expert_ids["full_run_best_guard"]
    else:
        full_run_best_expert = str(full_run_best_expert)
    if variant == "full_run_best_only":
        selected_expert = full_run_best_expert
        source = "full_run_best_only"
    elif matched:
        selected_expert = str(decision.selected_expert_id)
        source = "match"
    else:
        if variant == "full_run_best_guard":
            decision_selected = getattr(decision, "selected_expert_id", None)
            selected_expert = (
                full_run_best_expert
                if decision_selected is None
                or pd.isna(decision_selected)
                or not str(decision_selected).strip()
                else str(decision_selected)
            )
        else:
            selected_expert = config.fallback_expert_ids[variant]
        source = "cash" if variant == "cash_on_unmatched" else variant
    if selected_expert.lower() == "cash" and (not matched or variant == "full_run_best_only"):
        source = "cash"

    decision_context = _context_row(panel, pd.Timestamp(decision.date))
    actual_best_expert, selected_realized_utility, realized_best_utility = _realized_label_context(
        panel,
        pd.Timestamp(decision.date),
        selected_expert,
    )
    entry_close = _finite_required(decision_context["close"], "decision-date close")
    entry_atr_pct = _finite_required(decision_context["atr_pct"], "decision-date atr_pct")
    if selected_expert.lower() == "cash":
        decision_target_position = 0.0
    else:
        decision_source_row = _expert_row(panel, pd.Timestamp(decision.date), selected_expert)
        decision_target_position = _finite_required(
            decision_source_row["target_position"], "decision-date target_position"
        )
    fallback_audit = _fallback_audit_fields(decision, variant, matched, selected_expert)
    guard_pending = False
    guard_reason: str | None = None
    guard_trigger_date: pd.Timestamp | None = None
    risk_exit_effective_date: pd.Timestamp | None = None
    rows: list[dict[str, Any]] = []
    for hold_day, date in enumerate(effective_dates, start=1):
        source_row = _expert_row(panel, date, selected_expert)
        if selected_expert.lower() == "cash":
            source_return = 0.0
            source_position = 0.0
        else:
            source_return = _finite_required(source_row["strategy_return"], "source-net strategy_return")
            source_position = _finite_required(source_row["target_position"], "source target_position")
        executed_expert = "Cash" if guard_pending else selected_expert
        strategy_return = 0.0 if guard_pending else source_return
        target_position = 0.0 if guard_pending else decision_target_position
        context = _context_row(panel, date)
        trigger = None
        if not guard_pending and selected_expert.lower() != "cash" and decision_target_position != 0.0:
            trigger = _jump_guard_trigger(context, entry_close, entry_atr_pct, config)
            if trigger is not None and hold_day < len(effective_dates):
                guard_reason = trigger
                guard_trigger_date = pd.Timestamp(date)
                risk_exit_effective_date = pd.Timestamp(effective_dates[hold_day])
        decision_marker = hold_day == 1
        row = {
            "split_id": str(decision.split_id),
            "date": pd.Timestamp(date),
            "symbol": str(decision.symbol),
            "market": str(decision.market),
            "regime": str(getattr(decision_context, "regime", decision_context.get("regime", "unknown"))),
            "threshold": str(decision.threshold),
            "variant": variant,
            "decision_date": pd.Timestamp(decision.date),
            "effective_date": pd.Timestamp(effective_dates[0]),
            "holding_window_end_date": pd.Timestamp(effective_dates[-1]),
            "holding_day": hold_day,
            "decision_marker": decision_marker,
            "match_status": str(decision.match_status),
            "is_matched_decision": matched,
            "selected_expert_id": selected_expert,
            "executed_expert_id": executed_expert,
            "attribution_source": source,
            "unmatched_reason": getattr(decision, "unmatched_reason", None),
            "strategy_return": strategy_return,
            "target_position": target_position,
            "decision_target_position": decision_target_position,
            "source_expert_strategy_return": source_return,
            "source_expert_target_position": source_position,
            "counterfactual_no_guard_return": source_return,
            "jump_guard_trigger": trigger,
            "jump_guard_trigger_date": guard_trigger_date,
            "risk_exit_effective_date": risk_exit_effective_date,
            "risk_exit_reason": guard_reason if guard_pending else None,
            "jump_guard_cash": guard_pending,
            "actual_best_expert_5d": (
                actual_best_expert
                if actual_best_expert is not None
                else getattr(decision, "actual_best_expert_5d", None)
            ) if decision_marker else None,
            "selected_realized_5d_utility": (
                selected_realized_utility
                if np.isfinite(selected_realized_utility)
                else _optional_float(getattr(decision, "selected_realized_5d_utility", None))
            ) if decision_marker else np.nan,
            "realized_best_5d_utility": (
                realized_best_utility
                if np.isfinite(realized_best_utility)
                else _optional_float(getattr(decision, "realized_best_5d_utility", None))
            ) if decision_marker else np.nan,
            "top_k_retrieval_consistent": _top_k_consistent(decision, selected_expert) if decision_marker else np.nan,
            "neighbors_json": getattr(decision, "neighbors_json", None) if decision_marker else None,
            "expert_scores_json": getattr(decision, "expert_scores_json", None) if decision_marker else None,
            "selection_reason": getattr(decision, "selection_reason", None) if decision_marker else None,
            "max_similarity": _optional_float(getattr(decision, "max_similarity", None)) if decision_marker else np.nan,
        }
        for audit_field in (
            "fallback_policy",
            "fallback_source_run",
            "fallback_source_model_id",
            "fallback_expert_id",
            "fallback_summary_sha256",
            "fallback_source_manifest_sha256",
            "embedding_failure_reason",
            "expert_unavailable_reason",
            "fallback_reason",
        ):
            row[audit_field] = fallback_audit.get(audit_field) if decision_marker else None
        adaptive = _expert_row(panel, date, config.fallback_expert_ids["adaptive_guard"])
        row["adaptive_return"] = (
            0.0 if config.fallback_expert_ids["adaptive_guard"].lower() == "cash"
            else _finite_required(adaptive["strategy_return"], "adaptive source-net strategy_return")
        )
        rows.append(row)
        if trigger is not None and hold_day < len(effective_dates):
            guard_pending = True
    return rows


def _fallback_audit_fields(
    decision: Any,
    variant: str,
    matched: bool,
    selected_expert: str,
) -> dict[str, Any]:
    fields = (
        "fallback_policy",
        "fallback_source_run",
        "fallback_source_model_id",
        "fallback_expert_id",
        "fallback_summary_sha256",
        "fallback_source_manifest_sha256",
        "embedding_failure_reason",
        "expert_unavailable_reason",
        "fallback_reason",
    )
    if matched and variant != "full_run_best_only":
        return {field: None for field in fields}
    if variant in {"full_run_best_guard", "full_run_best_only"}:
        values = {
            field: getattr(decision, f"full_run_best_{field}", getattr(decision, field, None))
            for field in fields
        }
        values["fallback_policy"] = (
            "full_run_best_only" if variant == "full_run_best_only" else "full_run_best_guard"
        )
        values["fallback_expert_id"] = selected_expert
        return values
    if variant == "adaptive_guard":
        return {
            "fallback_policy": "adaptive_guard",
            "fallback_source_run": getattr(decision, "adaptive_fallback_source_run", "phase_b_source_lock"),
            "fallback_source_model_id": getattr(
                decision, "adaptive_fallback_source_model_id", selected_expert
            ),
            "fallback_expert_id": selected_expert,
            "fallback_summary_sha256": getattr(
                decision, "adaptive_fallback_summary_sha256", None
            ),
            "fallback_source_manifest_sha256": getattr(
                decision, "adaptive_fallback_source_manifest_sha256", None
            ),
            "embedding_failure_reason": getattr(decision, "embedding_failure_reason", None),
            "expert_unavailable_reason": getattr(decision, "expert_unavailable_reason", None),
            "fallback_reason": "adaptive_guard_on_unmatched",
        }
    return {
        "fallback_policy": "cash_on_unmatched",
        "fallback_source_run": "cash",
        "fallback_source_model_id": "cash",
        "fallback_expert_id": selected_expert,
        "fallback_summary_sha256": "not_applicable_cash",
        "fallback_source_manifest_sha256": "not_applicable_cash",
        "embedding_failure_reason": getattr(decision, "embedding_failure_reason", None),
        "expert_unavailable_reason": getattr(decision, "expert_unavailable_reason", None),
        "fallback_reason": "cash_on_unmatched",
    }


def _expert_row(panel: pd.DataFrame, date: pd.Timestamp, expert_id: str) -> pd.Series:
    if expert_id.lower() == "cash":
        return pd.Series(dtype=object)
    matches = panel.loc[panel["date"].eq(date) & panel["expert_id"].astype(str).eq(expert_id)]
    if len(matches) != 1 or str(matches.iloc[0]["expert_status"]) != "available":
        raise TransformerStateExecutionError(
            f"selected expert {expert_id!r} is unavailable on {pd.Timestamp(date).date()}"
        )
    return matches.iloc[0]


def _context_row(panel: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    matches = panel.loc[panel["date"].eq(date)]
    if matches.empty:
        raise TransformerStateExecutionError(f"market context is missing on {date.date()}")
    columns = ["close", "asset_return_1", "atr_pct", "benchmark_return", "regime"]
    first = matches.iloc[0]
    for column in columns[:-1]:
        values = pd.to_numeric(matches[column], errors="coerce").dropna().unique()
        if len(values) != 1:
            raise TransformerStateExecutionError(f"daily context column {column!r} must be unique per symbol/date")
    return first


def _realized_label_context(
    panel: pd.DataFrame,
    date: pd.Timestamp,
    selected_expert: str,
) -> tuple[str | None, float, float]:
    """Read evaluation-only five-day labels after the execution choice is frozen."""

    if "future_utility" not in panel:
        return None, np.nan, np.nan
    rows = panel.loc[panel["date"].eq(date)].copy()
    utilities = pd.to_numeric(rows["future_utility"], errors="coerce")
    valid = utilities.notna()
    if not valid.any():
        return None, np.nan, np.nan
    rows = rows.loc[valid].assign(_future_utility=utilities.loc[valid].astype(float))
    rows = rows.sort_values(["_future_utility", "expert_id"], ascending=[False, True], kind="stable")
    actual_best = str(rows.iloc[0]["expert_id"])
    if "best_expert_5d" in rows:
        frozen = rows["best_expert_5d"].dropna().astype(str).unique().tolist()
        if len(frozen) == 1:
            actual_best = frozen[0]
    best_rows = rows.loc[rows["expert_id"].astype(str).eq(actual_best)]
    realized_best = float(best_rows.iloc[0]["_future_utility"]) if not best_rows.empty else float(
        rows.iloc[0]["_future_utility"]
    )
    selected_rows = rows.loc[
        rows["expert_id"].astype(str).str.lower().eq(str(selected_expert).lower())
    ]
    selected_utility = (
        float(selected_rows.iloc[0]["_future_utility"]) if not selected_rows.empty else np.nan
    )
    return actual_best, selected_utility, realized_best


def _jump_guard_trigger(
    context: pd.Series,
    entry_close: float,
    entry_atr_pct: float,
    config: ExecutionConfig,
) -> str | None:
    asset_return = _finite_required(context["asset_return_1"], "asset_return_1")
    atr_pct = _finite_required(context["atr_pct"], "atr_pct")
    close = _finite_required(context["close"], "close")
    benchmark_return = _finite_required(context["benchmark_return"], "benchmark_return")
    if asset_return <= -config.jump_down_atr_multiple * atr_pct:
        return "single_day_jump_down"
    if close / entry_close - 1.0 <= -config.entry_drawdown_atr_multiple * entry_atr_pct:
        return "entry_drawdown_stop"
    if benchmark_return <= config.market_crash_return:
        return "market_crash_guard"
    return None


def _top_k_consistent(decision: Any, selected_expert: str) -> float:
    raw = getattr(decision, "top_k_expert_ids_json", None)
    neighbor_mode = False
    if not isinstance(raw, str) or not raw.strip():
        raw = getattr(decision, "neighbors_json", None)
        neighbor_mode = True
    if not isinstance(raw, str) or not raw.strip():
        return np.nan
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TransformerStateExecutionError("top_k_expert_ids_json is invalid JSON") from exc
    if not isinstance(values, list):
        raise TransformerStateExecutionError("top_k_expert_ids_json must contain a list")
    if neighbor_mode:
        experts = {
            str(value.get("best_expert_5d"))
            for value in values
            if isinstance(value, dict) and value.get("best_expert_5d") is not None
        }
    else:
        experts = {str(value) for value in values}
    return float(selected_expert in experts)


def reconstruct_execution_summary(daily_audit: pd.DataFrame) -> pd.DataFrame:
    """Rebuild every summary metric exclusively from W17 daily audit rows."""

    required = set(_SUMMARY_KEYS) | {
        "date",
        "strategy_return",
        "execution_turnover",
        "decision_marker",
        "is_matched_decision",
        "attribution_source",
        "geometric_return_contribution",
        "adaptive_return",
        "full_run_best_only_return",
    }
    missing = sorted(required - set(daily_audit.columns))
    if missing:
        raise TransformerStateExecutionError(f"daily audit is missing reconstruction columns: {missing}")
    rows: list[dict[str, Any]] = []
    for keys, group in daily_audit.groupby(_SUMMARY_KEYS, sort=True, dropna=False):
        ordered = group.sort_values("date", kind="stable")
        returns = pd.to_numeric(ordered["strategy_return"], errors="coerce")
        turnover = pd.to_numeric(ordered["execution_turnover"], errors="coerce")
        if not np.isfinite(returns.to_numpy(dtype=np.float64)).all() or not np.isfinite(
            turnover.to_numpy(dtype=np.float64)
        ).all():
            raise TransformerStateExecutionError("daily reconstruction inputs must be finite")
        with np.errstate(over="ignore", invalid="ignore"):
            equity = (1.0 + returns).cumprod()
        if not np.isfinite(equity.to_numpy(dtype=np.float64)).all():
            raise TransformerStateExecutionError("daily compounded equity must be finite")
        running_peak = equity.cummax().clip(lower=1.0)
        max_drawdown = float((equity / running_peak - 1.0).min())
        decisions = ordered.loc[ordered["decision_marker"].astype(bool)]
        decision_count = len(decisions)
        matched = decisions["is_matched_decision"].astype(bool)
        source_counts = decisions["attribution_source"].value_counts()
        hit_rows = decisions.dropna(subset=["actual_best_expert_5d"])
        actual_hit = (
            float((hit_rows["selected_expert_id"].astype(str) == hit_rows["actual_best_expert_5d"].astype(str)).mean())
            if not hit_rows.empty else np.nan
        )
        regrets = pd.to_numeric(decisions.get("realized_best_5d_utility"), errors="coerce") - pd.to_numeric(
            decisions.get("selected_realized_5d_utility"), errors="coerce"
        )
        selected_frequency = (
            decisions["selected_expert_id"].astype(str).value_counts(normalize=True).sort_index().to_dict()
            if decision_count else {}
        )
        with np.errstate(over="ignore", invalid="ignore"):
            local_equity_before = (1.0 + returns).cumprod().shift(1).fillna(1.0)
            local_contributions = local_equity_before * returns
        if not np.isfinite(local_contributions.to_numpy(dtype=np.float64)).all():
            raise TransformerStateExecutionError("daily return attribution must be finite")
        contributions = local_contributions.groupby(ordered["attribution_source"]).sum()
        adaptive_returns = pd.to_numeric(ordered["adaptive_return"], errors="coerce")
        full_best_returns = pd.to_numeric(ordered["full_run_best_only_return"], errors="coerce")
        if not np.isfinite(adaptive_returns.to_numpy(dtype=np.float64)).all() or not np.isfinite(
            full_best_returns.to_numpy(dtype=np.float64)
        ).all():
            raise TransformerStateExecutionError("daily control returns must be finite")
        adaptive_total_return = float((1.0 + adaptive_returns).prod() - 1.0)
        full_best_total_return = float((1.0 + full_best_returns).prod() - 1.0)
        if not np.isfinite([adaptive_total_return, full_best_total_return]).all():
            raise TransformerStateExecutionError("compounded control returns must be finite")
        row = dict(zip(_SUMMARY_KEYS, keys, strict=True))
        row.update(
            {
                "daily_row_count": int(len(ordered)),
                "decision_count": int(decision_count),
                "total_return": float(equity.iloc[-1] - 1.0),
                "max_drawdown": max_drawdown,
                "execution_turnover": float(turnover.sum()),
                "adaptive_total_return": adaptive_total_return,
                "full_run_best_only_total_return": full_best_total_return,
                "active_return_vs_adaptive": float(equity.iloc[-1] - 1.0) - adaptive_total_return,
                "active_return_vs_full_run_best_only": float(equity.iloc[-1] - 1.0) - full_best_total_return,
                "matched_decision_coverage": _coverage(int(matched.sum()), decision_count),
                "matched_active_coverage": _coverage(
                    int((matched & decisions["selected_expert_id"].astype(str).str.lower().ne("cash")).sum()),
                    decision_count,
                ),
                "fallback_full_run_best_coverage": _coverage(
                    int(source_counts.get("full_run_best_guard", 0)), decision_count
                ),
                "fallback_adaptive_coverage": _coverage(int(source_counts.get("adaptive_guard", 0)), decision_count),
                "fallback_cash_coverage": _coverage(int(source_counts.get("cash", 0)), decision_count),
                "jump_exit_rate": _coverage(
                    int(decisions["decision_date"].isin(ordered.loc[ordered["jump_guard_trigger"].notna(), "decision_date"]).sum()),
                    decision_count,
                ),
                "selected_expert_frequency_json": json.dumps(
                    selected_frequency, sort_keys=True, separators=(",", ":")
                ),
                "actual_best_expert_hit_rate": actual_hit,
                "top_k_retrieval_consistency": _numeric_mean(decisions.get("top_k_retrieval_consistent")),
                "predicted_vs_realized_5d_utility_regret": _numeric_mean(regrets),
                "match_return_contribution": float(contributions.get("match", 0.0)),
                "full_run_best_guard_return_contribution": float(
                    contributions.get("full_run_best_guard", 0.0)
                    + contributions.get("full_run_best_only", 0.0)
                ),
                "adaptive_guard_return_contribution": float(contributions.get("adaptive_guard", 0.0)),
                "cash_return_contribution": float(contributions.get("cash", 0.0)),
            }
        )
        required_finite_summary = (
            "total_return",
            "max_drawdown",
            "execution_turnover",
            "adaptive_total_return",
            "full_run_best_only_total_return",
            "active_return_vs_adaptive",
            "active_return_vs_full_run_best_only",
            "matched_decision_coverage",
            "matched_active_coverage",
            "fallback_full_run_best_coverage",
            "fallback_adaptive_coverage",
            "fallback_cash_coverage",
            "jump_exit_rate",
            "match_return_contribution",
            "full_run_best_guard_return_contribution",
            "adaptive_guard_return_contribution",
            "cash_return_contribution",
        )
        if not np.isfinite([row[column] for column in required_finite_summary]).all():
            raise TransformerStateExecutionError("execution summary outputs must be finite")
        rows.append(row)
    return pd.DataFrame(rows).sort_values(_SUMMARY_KEYS, kind="stable").reset_index(drop=True)


def assert_summary_reconstructs(
    daily_audit: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    tolerance: float = 1e-12,
) -> None:
    """Fail closed unless persisted summary equals a fresh daily reconstruction."""

    rebuilt = reconstruct_execution_summary(daily_audit)
    if list(summary.columns) != list(rebuilt.columns) or len(summary) != len(rebuilt):
        raise TransformerStateExecutionError("summary does not exactly reconstruct from daily audit")
    left = summary.sort_values(_SUMMARY_KEYS, kind="stable").reset_index(drop=True)
    for column in rebuilt.columns:
        expected = rebuilt[column]
        actual = left[column]
        if pd.api.types.is_numeric_dtype(expected):
            if not np.allclose(
                pd.to_numeric(actual, errors="coerce"),
                pd.to_numeric(expected, errors="coerce"),
                rtol=0.0,
                atol=tolerance,
                equal_nan=True,
            ):
                raise TransformerStateExecutionError("summary does not exactly reconstruct from daily audit")
        elif not actual.fillna("<NA>").equals(expected.fillna("<NA>")):
            raise TransformerStateExecutionError("summary does not exactly reconstruct from daily audit")


def _finite_required(value: Any, label: str) -> float:
    resolved = _optional_float(value)
    if not np.isfinite(resolved):
        raise TransformerStateExecutionError(f"{label} must be finite")
    return float(resolved)


def _optional_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _coverage(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else np.nan


def _numeric_mean(values: Any) -> float:
    if values is None:
        return np.nan
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.mean()) if not numeric.empty else np.nan


__all__ = [
    "ExecutionConfig",
    "ExecutionResult",
    "TransformerStateExecutionError",
    "assert_summary_reconstructs",
    "execute_state_decisions",
    "reconstruct_execution_summary",
]
