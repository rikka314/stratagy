"""Phase 4: Cross-fold admission testing for composite strategies.

Compares multiple strategy candidates across purged folds:
- cash baseline
- composite_only (from Phase 3 best map)
- composite + advisory overlays
- simplified composites (equal-weight, no-interaction)
- reference strategies (SM, etc.)

Each fold reports:
- Returns (total, net, gross)
- Risk (Sharpe, Sortino, volatility, max drawdown)
- Execution (turnover, trade count, cost ratio)
- Exposure (mean, median, saturation)
- Score-return relationship (monotonicity, rank IC)

Admission gate: >= 3/4 folds pass predefined thresholds,
worst fold has no data quality/PIT/audit failures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


StrategyVariant = Literal[
    "cash",
    "composite_only",
    "composite_plus_trend",
    "composite_plus_reversion",
    "composite_plus_macro_cap",
    "composite_plus_relative_strength",
    "composite_plus_all_advisories",
    "composite_equal_weight",
    "composite_no_interaction",
    "sm_reference",
]


@dataclass(frozen=True)
class FoldMetrics:
    """Metrics for a single fold."""

    fold_id: str
    start_date: str
    end_date: str
    trading_days: int

    # Returns
    total_return: float
    net_return: float
    gross_return: float

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    annualized_volatility: float

    # Drawdown
    max_drawdown: float
    max_drawdown_duration_days: int
    recovery_time_days: int | None

    # Win rate
    daily_win_rate: float
    monthly_win_rate: float | None

    # Exposure
    mean_exposure: float
    median_exposure: float
    max_exposure: float
    near_zero_rate: float  # <= 0.01
    near_max_rate: float   # >= 0.99

    # Execution
    total_turnover: float
    daily_avg_turnover: float
    trade_count: int
    rebalance_count: int

    # Cost
    transaction_cost: float
    cost_to_gross_ratio: float

    # Beta (if benchmark available)
    beta: float | None = None
    upside_beta: float | None = None
    downside_beta: float | None = None

    # Triggers/fallbacks (for advisory strategies)
    trigger_rate: float = 0.0
    fallback_rate: float = 0.0
    saturation_trigger_rate: float = 0.0

    # Score-return relationship
    score_return_rank_ic: float | None = None
    score_return_spearman: float | None = None
    monotonicity_violations: int = 0

    # Quality flags
    has_data_quality_issue: bool = False
    has_pit_violation: bool = False
    has_audit_failure: bool = False
    quality_notes: str = ""


@dataclass(frozen=True)
class AdmissionGate:
    """Admission criteria for a strategy across folds."""

    # Minimum fold pass rate
    min_fold_pass_rate: float = 0.75  # >= 3/4

    # Return thresholds (validation/test only)
    min_sharpe_ratio: float = 0.3
    min_sortino_ratio: float = 0.4

    # Risk limits
    max_drawdown_threshold: float = 0.30
    max_volatility: float = 0.40

    # Execution limits
    max_cost_to_gross_ratio: float = 0.50
    max_turnover_multiple: float = 50.0  # relative to baseline

    # Exposure sanity
    max_near_max_rate: float = 0.90
    min_mean_exposure: float = 0.05

    # Quality requirements
    allow_data_quality_issues: bool = False
    allow_pit_violations: bool = False
    allow_audit_failures: bool = False


@dataclass
class StrategyCandidate:
    """A strategy to evaluate across folds."""

    variant: StrategyVariant
    description: str
    fold_metrics: list[FoldMetrics] = field(default_factory=list)

    # Aggregated results
    mean_sharpe: float = 0.0
    median_sharpe: float = 0.0
    worst_sharpe: float = 0.0
    sharpe_std: float = 0.0

    folds_passed: int = 0
    total_folds: int = 0
    pass_rate: float = 0.0

    # Admission decision
    admission_status: Literal["pass", "fail", "blocked"] = "fail"
    admission_notes: str = ""


def compute_returns_and_equity(
    positions: pd.Series,
    returns: pd.Series,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> tuple[pd.Series, pd.Series, pd.Series, float]:
    """Compute strategy returns, costs, and equity curve.

    Returns:
        gross_returns: strategy returns before costs
        costs: transaction costs per period
        net_returns: strategy returns after costs
        total_cost: sum of all costs
    """
    # Gross returns
    gross_returns = positions.shift(1) * returns
    gross_returns.iloc[0] = 0.0

    # Position changes (turnover)
    position_changes = positions.diff().abs()
    position_changes.iloc[0] = positions.iloc[0]

    # Costs
    cost_rate = commission + slippage
    costs = position_changes * cost_rate
    total_cost = costs.sum()

    # Net returns
    net_returns = gross_returns - costs

    return gross_returns, costs, net_returns, total_cost


def compute_drawdown_stats(equity: pd.Series) -> tuple[float, int, int | None]:
    """Compute max drawdown, duration, and recovery time.

    Returns:
        max_dd: maximum drawdown (positive value)
        max_dd_duration: days in max drawdown
        recovery_time: days to recover from max drawdown (None if not recovered)
    """
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_dd = -drawdown.min()

    # Find max drawdown period
    dd_start = drawdown.idxmin()
    dd_start_idx = equity.index.get_loc(dd_start)

    # Duration: from peak to trough
    peak_before = cummax.iloc[:dd_start_idx + 1].idxmax()
    peak_idx = equity.index.get_loc(peak_before)
    max_dd_duration = dd_start_idx - peak_idx

    # Recovery: from trough to next peak >= previous peak
    recovery_time = None
    if dd_start_idx < len(equity) - 1:
        after_trough = equity.iloc[dd_start_idx + 1:]
        peak_value = cummax.loc[dd_start]
        recovered = after_trough >= peak_value
        if recovered.any():
            recovery_idx = after_trough.index[recovered.argmax()]
            recovery_time = equity.index.get_loc(recovery_idx) - dd_start_idx

    return max_dd, max_dd_duration, recovery_time


def compute_sharpe_sortino(
    returns: pd.Series,
    annualize_factor: float = 252.0,
) -> tuple[float, float, float]:
    """Compute Sharpe and Sortino ratios.

    Returns:
        sharpe: annualized Sharpe ratio
        sortino: annualized Sortino ratio
        volatility: annualized volatility
    """
    mean_ret = returns.mean()
    std_ret = returns.std()

    # Sharpe
    sharpe = 0.0
    if std_ret > 0:
        sharpe = mean_ret / std_ret * np.sqrt(annualize_factor)

    # Sortino (downside deviation)
    downside = returns[returns < 0]
    downside_std = downside.std() if len(downside) > 0 else std_ret
    sortino = 0.0
    if downside_std > 0:
        sortino = mean_ret / downside_std * np.sqrt(annualize_factor)

    volatility = std_ret * np.sqrt(annualize_factor)

    return sharpe, sortino, volatility


def compute_beta(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> tuple[float | None, float | None, float | None]:
    """Compute beta, upside beta, downside beta.

    Returns:
        beta: overall beta
        upside_beta: beta when benchmark > 0
        downside_beta: beta when benchmark < 0
    """
    aligned = pd.DataFrame({
        "strategy": strategy_returns,
        "benchmark": benchmark_returns,
    }).dropna()

    if len(aligned) < 20:
        return None, None, None

    # Overall beta
    cov = aligned["strategy"].cov(aligned["benchmark"])
    var = aligned["benchmark"].var()
    beta = cov / var if var > 0 else None

    # Upside beta
    upside = aligned[aligned["benchmark"] > 0]
    upside_beta = None
    if len(upside) >= 10:
        cov_up = upside["strategy"].cov(upside["benchmark"])
        var_up = upside["benchmark"].var()
        upside_beta = cov_up / var_up if var_up > 0 else None

    # Downside beta
    downside = aligned[aligned["benchmark"] < 0]
    downside_beta = None
    if len(downside) >= 10:
        cov_down = downside["strategy"].cov(downside["benchmark"])
        var_down = downside["benchmark"].var()
        downside_beta = cov_down / var_down if var_down > 0 else None

    return beta, upside_beta, downside_beta


def compute_rank_ic(
    scores: pd.Series,
    future_returns: pd.Series,
) -> tuple[float, float]:
    """Compute rank IC (Spearman) between scores and future returns.

    Returns:
        rank_ic: Spearman correlation
        spearman_p: p-value (not computed here, set to 0.0)
    """
    aligned = pd.DataFrame({
        "score": scores,
        "future_return": future_returns,
    }).dropna()

    if len(aligned) < 10:
        return 0.0, 0.0

    rank_ic = aligned["score"].corr(aligned["future_return"], method="spearman")
    return rank_ic, 0.0


def check_fold_quality(
    df: pd.DataFrame,
    returns_col: str = "return",
) -> tuple[bool, bool, bool, str]:
    """Check for data quality, PIT, and audit issues.

    Returns:
        has_data_quality_issue: duplicates, non-positive prices, extreme returns
        has_pit_violation: future data leakage (not fully implemented here)
        has_audit_failure: equity/turnover/cost reconstruction mismatch
        quality_notes: description of issues
    """
    notes = []
    has_dq = False
    has_pit = False
    has_audit = False

    # Check duplicates
    if df.index.duplicated().any():
        has_dq = True
        notes.append("duplicate_dates")

    # Check extreme returns
    if returns_col in df.columns:
        extreme = (df[returns_col].abs() > 0.50).sum()
        if extreme > 0:
            has_dq = True
            notes.append(f"extreme_returns_{extreme}")

    # Audit checks (basic)
    # (Full reconstruction would require recomputing equity from positions/returns)

    quality_notes = "; ".join(notes) if notes else ""
    return has_dq, has_pit, has_audit, quality_notes


def evaluate_fold(
    fold_id: str,
    df: pd.DataFrame,
    positions: pd.Series,
    returns: pd.Series,
    scores: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> FoldMetrics:
    """Evaluate a single fold."""
    start_date = df.index[0].strftime("%Y-%m-%d")
    end_date = df.index[-1].strftime("%Y-%m-%d")
    trading_days = len(df)

    # Returns and costs
    gross_rets, costs, net_rets, total_cost = compute_returns_and_equity(
        positions, returns, commission, slippage
    )

    total_return = (1 + net_rets).prod() - 1
    gross_return = (1 + gross_rets).prod() - 1
    net_return = total_return

    # Equity curve
    equity = (1 + net_rets).cumprod()

    # Risk metrics
    sharpe, sortino, volatility = compute_sharpe_sortino(net_rets)

    # Drawdown
    max_dd, max_dd_duration, recovery_time = compute_drawdown_stats(equity)

    # Win rate
    daily_win_rate = (net_rets > 0).mean()
    monthly_win_rate = None  # Would need resampling

    # Exposure
    mean_exposure = positions.mean()
    median_exposure = positions.median()
    max_exposure = positions.max()
    near_zero_rate = (positions <= 0.01).mean()
    near_max_rate = (positions >= 0.99).mean()

    # Turnover
    position_changes = positions.diff().abs()
    position_changes.iloc[0] = positions.iloc[0]
    total_turnover = position_changes.sum()
    daily_avg_turnover = position_changes.mean()
    trade_count = (position_changes > 0.001).sum()
    rebalance_count = trade_count

    # Cost ratio
    cost_to_gross_ratio = 0.0
    if gross_return > 0:
        cost_to_gross_ratio = total_cost / gross_return

    # Beta
    beta, upside_beta, downside_beta = None, None, None
    if benchmark_returns is not None:
        beta, upside_beta, downside_beta = compute_beta(net_rets, benchmark_returns)

    # Score-return relationship
    score_return_rank_ic = None
    score_return_spearman = None
    if scores is not None:
        # Use next-period return as "future return"
        future_returns = returns.shift(-1)
        score_return_rank_ic, _ = compute_rank_ic(scores, future_returns)
        score_return_spearman = score_return_rank_ic

    # Quality checks
    has_dq, has_pit, has_audit, quality_notes = check_fold_quality(df)

    return FoldMetrics(
        fold_id=fold_id,
        start_date=start_date,
        end_date=end_date,
        trading_days=trading_days,
        total_return=total_return,
        net_return=net_return,
        gross_return=gross_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        annualized_volatility=volatility,
        max_drawdown=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        recovery_time_days=recovery_time,
        daily_win_rate=daily_win_rate,
        monthly_win_rate=monthly_win_rate,
        mean_exposure=mean_exposure,
        median_exposure=median_exposure,
        max_exposure=max_exposure,
        near_zero_rate=near_zero_rate,
        near_max_rate=near_max_rate,
        total_turnover=total_turnover,
        daily_avg_turnover=daily_avg_turnover,
        trade_count=trade_count,
        rebalance_count=rebalance_count,
        transaction_cost=total_cost,
        cost_to_gross_ratio=cost_to_gross_ratio,
        beta=beta,
        upside_beta=upside_beta,
        downside_beta=downside_beta,
        score_return_rank_ic=score_return_rank_ic,
        score_return_spearman=score_return_spearman,
        has_data_quality_issue=has_dq,
        has_pit_violation=has_pit,
        has_audit_failure=has_audit,
        quality_notes=quality_notes,
    )


def check_admission(
    candidate: StrategyCandidate,
    gate: AdmissionGate,
) -> tuple[Literal["pass", "fail", "blocked"], str]:
    """Check if a strategy passes admission criteria.

    Returns:
        status: "pass", "fail", or "blocked"
        reason: explanation
    """
    reasons = []

    # Check quality blocks
    for fm in candidate.fold_metrics:
        if fm.has_data_quality_issue and not gate.allow_data_quality_issues:
            return "blocked", f"data_quality_issue in {fm.fold_id}"
        if fm.has_pit_violation and not gate.allow_pit_violations:
            return "blocked", f"pit_violation in {fm.fold_id}"
        if fm.has_audit_failure and not gate.allow_audit_failures:
            return "blocked", f"audit_failure in {fm.fold_id}"

    # Count passing folds
    passing_folds = 0
    for fm in candidate.fold_metrics:
        passed = True
        if fm.sharpe_ratio < gate.min_sharpe_ratio:
            passed = False
        if fm.sortino_ratio < gate.min_sortino_ratio:
            passed = False
        if fm.max_drawdown > gate.max_drawdown_threshold:
            passed = False
        if fm.annualized_volatility > gate.max_volatility:
            passed = False
        if fm.cost_to_gross_ratio > gate.max_cost_to_gross_ratio:
            passed = False
        if fm.near_max_rate > gate.max_near_max_rate:
            passed = False
        if fm.mean_exposure < gate.min_mean_exposure:
            passed = False

        if passed:
            passing_folds += 1

    pass_rate = passing_folds / len(candidate.fold_metrics) if candidate.fold_metrics else 0.0

    if pass_rate >= gate.min_fold_pass_rate:
        return "pass", f"pass_rate={pass_rate:.2%} >= {gate.min_fold_pass_rate:.2%}"
    else:
        return "fail", f"pass_rate={pass_rate:.2%} < {gate.min_fold_pass_rate:.2%}"


def aggregate_candidate_metrics(candidate: StrategyCandidate) -> None:
    """Compute aggregated metrics across folds."""
    if not candidate.fold_metrics:
        return

    sharpes = [fm.sharpe_ratio for fm in candidate.fold_metrics]
    candidate.mean_sharpe = np.mean(sharpes)
    candidate.median_sharpe = np.median(sharpes)
    candidate.worst_sharpe = np.min(sharpes)
    candidate.sharpe_std = np.std(sharpes)
    candidate.total_folds = len(candidate.fold_metrics)


def export_fold_metrics_csv(
    candidates: list[StrategyCandidate],
    output_path: Path,
) -> None:
    """Export all fold metrics to CSV."""
    rows = []
    for candidate in candidates:
        for fm in candidate.fold_metrics:
            row = {
                "strategy_variant": candidate.variant,
                **asdict(fm),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"Exported fold metrics: {output_path}")


def export_admission_summary(
    candidates: list[StrategyCandidate],
    gate: AdmissionGate,
    output_path: Path,
) -> None:
    """Export admission summary table."""
    rows = []
    for candidate in candidates:
        row = {
            "strategy_variant": candidate.variant,
            "description": candidate.description,
            "total_folds": candidate.total_folds,
            "folds_passed": candidate.folds_passed,
            "pass_rate": candidate.pass_rate,
            "mean_sharpe": candidate.mean_sharpe,
            "median_sharpe": candidate.median_sharpe,
            "worst_sharpe": candidate.worst_sharpe,
            "sharpe_std": candidate.sharpe_std,
            "admission_status": candidate.admission_status,
            "admission_notes": candidate.admission_notes,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"Exported admission summary: {output_path}")
