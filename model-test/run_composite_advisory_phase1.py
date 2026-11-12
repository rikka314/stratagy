"""Run the research-only Composite-Centric Advisory Phase 1 ablation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.composite_advisory import (
    AdvisoryConfig,
    CompositeAdvisory,
    POLICIES,
    decide_frame,
)
from core.composite_advisory_config import load_advisory_config, source_lock
from core.factor_pipeline import FactorPipeline
from model_test.composite_mapping import PositionMap, ScoreTransform
from model_test.composite_quality import audit_factor_directions, redundancy_matrix, validate_price_frame


REQUIRED_PRICE_COLUMNS = {"date", "open", "high", "low", "close", "volume"}
AUDIT_COLUMNS = (
    "date",
    "symbol",
    "market",
    "policy",
    "decision_timestamp",
    "feature_cutoff",
    "execution_timestamp",
    "return_start",
    "return_end",
    "composite_score",
    "composite_base_position",
    "composite_transformed_score",
    "trend_confirmation",
    "reversion_warning",
    "relative_strength_confirmation",
    "macro_risk_level",
    "macro_risk_cap",
    "advisory_multiplier",
    "final_position",
    "previous_position",
    "turnover",
    "close_return",
    "gross_strategy_return",
    "transaction_cost",
    "strategy_return",
    "fallback_used",
    "fallback_reason",
    "policy_version",
    "config_sha256",
    "source_manifest_sha256",
    "macro_data_manifest_sha256",
    "snapshot_artifacts_sha256",
    "macro_artifacts_sha256",
    "code_sha256",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("market") != "US":
        raise ValueError("source manifest market must be US")
    data = manifest.get("data", {})
    if data.get("source") != "frozen_csv":
        raise ValueError("Phase 1 requires frozen_csv source")
    if not data.get("snapshot_sha256"):
        raise ValueError("source manifest lacks snapshot hash")
    return manifest


def _load_snapshot(path: Path, symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED_PRICE_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{symbol} snapshot missing columns: {sorted(missing)}")
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    numeric = result.loc[:, ["open", "high", "low", "close", "volume"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if result["date"].isna().any() or result["date"].duplicated().any():
        raise ValueError(f"{symbol} snapshot dates are invalid or duplicated")
    if not result["date"].is_monotonic_increasing:
        raise ValueError(f"{symbol} snapshot dates are not sorted")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"{symbol} snapshot contains non-finite OHLCV")
    if (numeric.loc[:, ["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"{symbol} snapshot contains non-positive prices")
    return result.assign(**{column: numeric[column] for column in numeric.columns})


def _policy_rebalance_days(policy: str) -> int:
    return {
        "composite_only": 1,
        "composite_plus_trend": 5,
        "composite_plus_reversion": 2,
        "composite_plus_macro_cap": 1,
        "composite_plus_relative_strength": 5,
        "composite_plus_all_advisories": 1,
        "cash": 1,
    }[policy]


def _apply_rebalance_cadence(
    position: pd.Series,
    cadence: int,
    max_delta: float,
) -> pd.Series:
    """Hold execution position and cap each actual rebalance change."""
    if cadence <= 0 or max_delta < 0 or not np.isfinite(max_delta):
        raise ValueError("cadence must be positive and max_delta must be finite and non-negative")
    values = position.to_numpy(dtype=float)
    executed = np.empty_like(values)
    previous = 0.0
    for index, target in enumerate(values):
        if index == 0 or index % cadence == 0:
            previous = float(
                np.clip(target, previous - max_delta, previous + max_delta)
            )
        executed[index] = previous
    return pd.Series(executed, index=position.index, name=position.name)


def _metrics(
    frame: pd.DataFrame,
    policy: str,
    fold_id: str,
    *,
    expected_symbols: int,
) -> dict[str, Any]:
    """Calculate equal-weight metrics only on complete cross-sectional dates."""
    if frame.empty:
        daily = pd.DataFrame(
            columns=["strategy_return", "turnover", "transaction_cost", "fallback_used"]
        )
        incomplete_dates = 0
        min_symbols = 0
    else:
        counts = frame.groupby("date")["symbol"].nunique()
        complete_dates = counts.index[counts == expected_symbols]
        incomplete_dates = int((counts != expected_symbols).sum())
        min_symbols = int(counts.min())
        complete_frame = frame.loc[frame["date"].isin(complete_dates)]
        daily = (
            complete_frame.groupby("date", sort=True)
            .agg(
                strategy_return=("strategy_return", "mean"),
                turnover=("turnover", "mean"),
                transaction_cost=("transaction_cost", "mean"),
                fallback_used=("fallback_used", "mean"),
            )
            .reset_index()
        )
    returns = daily["strategy_return"].to_numpy(dtype=float)
    equity = np.cumprod(1.0 + returns)
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    running_max = np.maximum.accumulate(equity)
    drawdown = equity / running_max - 1.0
    downside = returns[returns < 0.0]
    return {
        "fold_id": fold_id,
        "policy": policy,
        "coverage": int(len(daily)),
        "incomplete_dates": incomplete_dates,
        "min_symbols_on_any_date": min_symbols,
        "total_return": float(equity[-1] - 1.0) if len(equity) else 0.0,
        "sharpe": float(np.mean(returns) / std * np.sqrt(252.0)) if std > 1e-12 else 0.0,
        "max_drawdown": float(np.min(drawdown)) if len(drawdown) else 0.0,
        "downside_return": float(np.mean(downside)) if len(downside) else 0.0,
        "daily_win_rate": float(np.mean(returns > 0)) if len(returns) else 0.0,
        "turnover": float(daily["turnover"].sum()),
        "transaction_cost": float(daily["transaction_cost"].sum()),
        "fallback_rate": float(daily["fallback_used"].mean()) if len(daily) else 0.0,
        "trigger_rate": float((frame["advisory_multiplier"] < 1.0).mean()) if len(frame) else 0.0,
        "mean_position": float(frame["final_position"].mean()) if len(frame) else 0.0,
    }


def _folds(config: dict[str, Any]) -> list[dict[str, str]]:
    return list(config["folds"])


def _fold_frame(frame: pd.DataFrame, fold: dict[str, str]) -> pd.DataFrame:
    return frame.loc[
        (frame["date"] >= pd.Timestamp(fold["test_start"]))
        & (frame["date"] <= pd.Timestamp(fold["test_end"]))
    ].copy()


def _admission(
    metrics: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Apply frozen admission gates against composite-only per fold."""
    gates = config["admission"]
    baseline = metrics.loc[metrics["policy"] == "composite_only"].set_index("fold_id")
    evaluations: dict[str, Any] = {}
    admitted: list[str] = []
    for policy in POLICIES:
        if policy in {"composite_only", "cash"}:
            continue
        rows: list[dict[str, Any]] = []
        for fold_id, candidate in metrics.loc[
            metrics["policy"] == policy
        ].set_index("fold_id").iterrows():
            reference = baseline.loc[fold_id]
            denominator = max(abs(float(reference["total_return"])), 1e-12)
            total_return_drop = (
                float(reference["total_return"]) - float(candidate["total_return"])
            ) / denominator
            sharpe_drop = float(reference["sharpe"]) - float(candidate["sharpe"])
            reference_turnover = max(float(reference["turnover"]), 1e-12)
            turnover_multiple = float(candidate["turnover"]) / reference_turnover
            risk_improved = (
                float(candidate["max_drawdown"])
                > float(reference["max_drawdown"])
                or float(candidate["downside_return"])
                > float(reference["downside_return"])
            )
            checks = {
                "sharpe": sharpe_drop <= gates["max_sharpe_drop_vs_composite_only"],
                "total_return": total_return_drop
                <= gates["max_total_return_drop_vs_composite_only"],
                "risk_improvement": risk_improved,
                "fallback_rate": float(candidate["fallback_rate"])
                <= gates["max_fallback_rate"],
                "trigger_rate": float(candidate["trigger_rate"])
                <= gates["max_trigger_rate"],
                "turnover": turnover_multiple
                <= gates["max_turnover_multiple_vs_composite_only"],
            }
            rows.append(
                {
                    "fold_id": fold_id,
                    "sharpe_drop": sharpe_drop,
                    "total_return_drop_fraction": total_return_drop,
                    "max_drawdown_delta": float(candidate["max_drawdown"])
                    - float(reference["max_drawdown"]),
                    "downside_return_delta": float(candidate["downside_return"])
                - float(reference["downside_return"]),
                "turnover_multiple": turnover_multiple,
                "checks": checks,
                "passed": all(checks.values()),
                }
            )
        policy_passed = all(row["passed"] for row in rows)
        evaluations[policy] = {
            "status": "admitted" if policy_passed else "rejected",
            "cross_fold": rows,
            "cross_fold_risk_improvement": all(
                row["checks"]["risk_improvement"] for row in rows
            ),
        }
        if policy_passed:
            admitted.append(policy)
    return {
        "status": "admitted" if admitted else "composite_only",
        "admitted_policies": admitted,
        "baseline_policy": "composite_only",
        "gates": gates,
        "policies": evaluations,
    }


def _write_admission_report(
    output: Path,
    summary: dict[str, Any],
    admission: dict[str, Any],
) -> None:
    lines = [
        "# Composite-Centric Advisory Admission",
        "",
        "- Status: `" + admission["status"] + "`",
        "- Research-only: `true`",
        "- Baseline: `composite_only`",
        "- Replay summary: `" + summary["symbols"].__str__() + "` symbols, `"
        + summary["audit_rows"].__str__() + "` audit rows",
        "",
        "`status=admitted` requires every registered gate to pass in every test fold. "
        "No admission authorizes production or Streamlit integration.",
        "",
        "## Policy Results",
        "",
        "| Policy | Status | Cross-fold risk improvement |",
        "|---|---|---|",
    ]
    for policy, result in admission["policies"].items():
        lines.append(
            f"| `{policy}` | `{result['status']}` | "
            f"`{result['cross_fold_risk_improvement']}` |"
        )
    lines.extend(["", "## Gate Details", ""])
    for policy, result in admission["policies"].items():
        lines.extend([f"### `{policy}`", ""])
        for fold in result["cross_fold"]:
            lines.append(
                f"- `{fold['fold_id']}`: "
                f"passed=`{fold['passed']}`, checks=`{fold['checks']}`"
            )
        lines.append("")
    (output / "admission_report.md").write_text("\n".join(lines), encoding="utf-8")


def run(config_path: Path, output: Path) -> dict[str, Any]:
    config = load_advisory_config(config_path)
    manifest_path = REPO_ROOT / config["source"]["data_manifest"]
    manifest = _read_manifest(manifest_path)
    locks = source_lock(config, config_path)
    if locks["source_manifest_sha256"] != _sha256(manifest_path):
        raise ValueError("source manifest hash changed during lock")

    snapshot_dir = REPO_ROOT / config["source"]["snapshot_dir"]
    symbols = [str(item["symbol"]).upper() for item in manifest["universe"]["files"]]
    advisory = CompositeAdvisory(config=AdvisoryConfig(**config["bounds"]))
    pipeline = FactorPipeline(REPO_ROOT / config["source"]["macro_data_dir"])
    audit_frames: list[pd.DataFrame] = []
    quality_reports: list[dict[str, Any]] = []
    direction_frames: list[pd.DataFrame] = []
    redundancy_frames: list[pd.DataFrame] = []
    factor_columns = ["mom_short_z", "rsi_z", "macd_z", "vix_level", "volume_ratio_rank"]
    pool_columns = list(advisory.pool.required_columns())
    train_end = pd.Timestamp(config["folds"][0]["test_start"])

    for symbol in symbols:
        prices = _load_snapshot(snapshot_dir / f"{symbol}_daily.csv", symbol)
        quality_reports.append({"symbol": symbol, **validate_price_frame(prices)})
        factors = pipeline.compute_all_factors(prices, symbol)
        factor_view = factors.loc[factors["date"] >= pd.Timestamp(config["source"]["required_data_end"]) - pd.Timedelta(days=3650)].copy()
        # The source lock is US-only; keep rows with complete research factors and
        # record the dropped warm-up rows rather than failing a valid long history.
        finite = factor_view.dropna(subset=pool_columns).reset_index(drop=True)
        train_scores = advisory.pool.compute_scores(
            finite.loc[finite["date"] < train_end]
        )["composite_optimized"]
        if train_scores.empty:
            raise ValueError(f"{symbol} has no pre-fold training scores")
        if len(finite) < 2:
            raise ValueError(f"{symbol} has insufficient finite factor rows")
        direction = audit_factor_directions(finite, factor_columns, horizon=config["primary_horizon_days"])
        direction.insert(0, "symbol", symbol)
        direction_frames.append(direction)
        redundancy = redundancy_matrix(finite, factor_columns)
        redundancy.insert(0, "symbol", symbol)
        redundancy_frames.append(redundancy)
        transform = ScoreTransform.fit(train_scores)
        mapped_pool = type(advisory.pool)(score_transform=transform)
        mapped_advisory = CompositeAdvisory(pool=mapped_pool, config=advisory.config)
        for policy in POLICIES:
            decision_frame = decide_frame(finite, policy=policy, advisory=mapped_advisory)
            target_positions = decision_frame["final_position"].rename("target_position")
            executed_positions = _apply_rebalance_cadence(
                target_positions, _policy_rebalance_days(policy), advisory.config.max_single_decision_change
            )
            previous_positions = executed_positions.shift(1).fillna(0.0)
            next_close = finite["close"].shift(-1)
            close_return = next_close / finite["close"] - 1.0
            turnover = (executed_positions - previous_positions).abs()
            cost = turnover * (
                config["execution"]["commission_bps"]
                + config["execution"]["slippage_bps"]
            ) / 10000.0
            valid = decision_frame.index < len(finite) - 1
            decision_frame = decision_frame.loc[valid].copy()
            decision_frame["final_position"] = executed_positions.loc[valid].to_numpy()
            decision_frame["previous_position"] = previous_positions.loc[valid]
            decision_frame["turnover"] = turnover.loc[valid]
            decision_frame["close_return"] = close_return.loc[valid]
            decision_frame["gross_strategy_return"] = (
                executed_positions.loc[valid] * decision_frame["close_return"]
            )
            decision_frame["transaction_cost"] = cost.loc[valid]
            decision_frame["strategy_return"] = (
                decision_frame["gross_strategy_return"] - decision_frame["transaction_cost"]
            )
            decision_frame["date"] = finite.loc[valid, "date"].to_numpy()
            decision_frame["decision_timestamp"] = decision_frame["date"]
            decision_frame["feature_cutoff"] = decision_frame["date"]
            decision_frame["execution_timestamp"] = decision_frame["date"]
            decision_frame["return_start"] = decision_frame["date"]
            decision_frame["return_end"] = finite["date"].shift(-1).loc[valid].to_numpy()
            raw_scores = mapped_pool.compute_scores(finite)["composite_optimized"]
            transformed_scores = transform.transform(raw_scores)
            decision_frame["composite_transformed_score"] = transformed_scores.loc[valid].to_numpy()
            decision_frame["symbol"] = symbol
            decision_frame["market"] = "US"
            decision_frame["policy"] = policy
            decision_frame["config_sha256"] = locks["config_sha256"]
            decision_frame["source_manifest_sha256"] = locks["source_manifest_sha256"]
            decision_frame["macro_data_manifest_sha256"] = locks["macro_data_manifest_sha256"]
            decision_frame["snapshot_artifacts_sha256"] = locks["snapshot_artifacts_sha256"]
            decision_frame["macro_artifacts_sha256"] = locks["macro_artifacts_sha256"]
            decision_frame["code_sha256"] = _sha256(Path(__file__))
            audit_frames.append(decision_frame.loc[:, AUDIT_COLUMNS])

    audit = pd.concat(audit_frames, ignore_index=True).loc[:, AUDIT_COLUMNS]
    output.mkdir(parents=True, exist_ok=True)
    audit.to_parquet(output / "decision_audit.parquet", index=False)
    pd.DataFrame(quality_reports).to_json(output / "quality_report.json", orient="records", indent=2)
    pd.concat(direction_frames, ignore_index=True).to_csv(output / "factor_direction_report.csv", index=False)
    pd.concat(redundancy_frames, ignore_index=True).to_parquet(output / "factor_redundancy_matrix.parquet", index=False)
    factor_registry = {
        "status": "research_only",
        "market": "US",
        "factors": {
            name: {"role": "alpha" if name != "vix_level" else "risk_cap", "direction": "registered_pending_fold_vote"}
            for name in factor_columns
        },
    }
    (output / "factor_registry.json").write_text(json.dumps(factor_registry, indent=2), encoding="utf-8")
    expected_symbols = len(symbols)
    for fold in _folds(config):
        fold_symbols = audit.loc[
            (audit["date"] >= pd.Timestamp(fold["test_start"]))
            & (audit["date"] <= pd.Timestamp(fold["test_end"]))
        ].groupby("date")["symbol"].nunique()
        if len(fold_symbols) == 0:
            raise ValueError(f"{fold['fold_id']} has no audit rows")
        expected_symbols = min(expected_symbols, int(fold_symbols.max()))
    if expected_symbols <= 0:
        raise ValueError("no complete cross-sectional symbol count available")

    complete_date_symbols = [
        set(group["symbol"])
        for _, group in audit.groupby("date")
        if len(group["symbol"].unique()) == expected_symbols
    ]
    effective_symbols = sorted(set.intersection(*complete_date_symbols))
    if len(effective_symbols) != expected_symbols:
        raise ValueError("effective cross-section symbol set is not stable")

    metrics = []
    for fold in _folds(config):
        for policy in POLICIES:
            scoped = audit.loc[audit["policy"] == policy]
            scoped = _fold_frame(scoped, fold)
            metrics.append(
                _metrics(scoped, policy, fold["fold_id"], expected_symbols=expected_symbols)
            )
    metrics_frame = pd.DataFrame(metrics)
    metrics_frame.to_csv(output / "ablation_metrics.csv", index=False)
    status = "passed" if not audit.empty else "failed"
    summary = {
        "status": status,
        "research_only": True,
        "market": "US",
        "policy_version": config["policy_version"],
        "config_sha256": locks["config_sha256"],
        "source_manifest_sha256": locks["source_manifest_sha256"],
        "macro_data_manifest_sha256": locks["macro_data_manifest_sha256"],
        "snapshot_artifacts_sha256": locks["snapshot_artifacts_sha256"],
        "macro_artifacts_sha256": locks["macro_artifacts_sha256"],
        "cost_treatment": config["execution"]["cost_treatment"],
        "symbols": len(symbols),
        "audit_rows": len(audit),
        "policies": list(POLICIES),
    }
    admission = _admission(metrics_frame, config)
    summary["admission_status"] = admission["status"]
    summary["admitted_policies"] = admission["admitted_policies"]
    (output / "admission_summary.json").write_text(
        json.dumps(admission, indent=2), encoding="utf-8"
    )
    _write_admission_report(output, summary, admission)
    (output / "phase1_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "model-test/configs/composite_advisory_phase0_1.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "model-test/outputs/composite_advisory_phase1")
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output), indent=2))


if __name__ == "__main__":
    main()
