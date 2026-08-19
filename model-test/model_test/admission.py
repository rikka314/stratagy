"""Source-locked W11 admission evidence helpers.

The module stays outside the product workflow: it reads persisted research
artifacts and compares execution positions in the same 0..1 target-position
unit.  It never retrains a model or mutates an upstream artifact.
"""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class AdmissionEvidenceError(ValueError):
    """Raised when a W11 comparison cannot be built from auditable artifacts."""


def calculate_execution_turnover(
    frame: pd.DataFrame,
    *,
    position_column: str = "final_target_position",
    group_columns: Iterable[str] = ("symbol",),
    date_column: str = "date",
) -> pd.DataFrame:
    """Add abs(position_t - position_t-1) with an initial position of zero.

    The calculation intentionally does not consume any return, cost, or
    source turnover fields.  That makes MoE allocations and the hard router
    comparable even when the older source only retained reconstructed target
    positions.
    """

    groups = tuple(group_columns)
    required = {date_column, position_column, *groups}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise AdmissionEvidenceError(f"turnover frame is missing required columns: {missing}")

    out = frame.copy()
    out[date_column] = pd.to_datetime(out[date_column], errors="coerce")
    if out[date_column].isna().any():
        raise AdmissionEvidenceError("turnover frame contains an invalid date")
    out[position_column] = pd.to_numeric(out[position_column], errors="coerce")
    if out[position_column].isna().any():
        raise AdmissionEvidenceError(f"turnover frame contains a missing {position_column}")
    out = out.sort_values([*groups, date_column], kind="stable").reset_index(drop=True)
    previous = out.groupby(list(groups), sort=False)[position_column].shift(1).fillna(0.0)
    out["execution_turnover"] = (out[position_column] - previous).abs()
    return out


def assess_w11_admission(
    split_summary: pd.DataFrame,
    *,
    required_splits: int = 4,
    minimum_not_worse_windows: int = 3,
    turnover_limit: float = 1.25,
) -> dict[str, Any]:
    """Apply the frozen W11 gate to already-computed split evidence."""

    required = {"split_id", "not_worse_than_adaptive", "drawdown_not_worse", "turnover_ratio"}
    missing = sorted(required - set(split_summary.columns))
    if missing:
        raise AdmissionEvidenceError(f"split summary is missing required columns: {missing}")
    if int(required_splits) <= 0 or int(minimum_not_worse_windows) <= 0:
        raise AdmissionEvidenceError("W11 required_splits and minimum_not_worse_windows must be positive.")

    frame = split_summary.drop_duplicates("split_id", keep="last").copy()
    frame["not_worse_than_adaptive"] = frame["not_worse_than_adaptive"].fillna(False).astype(bool)
    frame["drawdown_not_worse"] = frame["drawdown_not_worse"].fillna(False).astype(bool)
    ratios = pd.to_numeric(frame["turnover_ratio"], errors="coerce")
    frame["turnover_within_limit"] = ratios.notna() & (ratios <= float(turnover_limit))

    split_count = int(len(frame))
    not_worse_count = int(frame["not_worse_than_adaptive"].sum())
    reasons: list[str] = []
    if split_count != int(required_splits):
        reasons.append(f"requires exactly {required_splits} comparable test splits; found {split_count}")
    if not_worse_count < int(minimum_not_worse_windows):
        reasons.append(
            f"requires at least {minimum_not_worse_windows}/{required_splits} non-inferior windows; "
            f"found {not_worse_count}/{split_count}"
        )
    if not bool(frame["drawdown_not_worse"].all()):
        reasons.append("maximum drawdown is worse than adaptive router in at least one split")
    if not bool(frame["turnover_within_limit"].all()):
        reasons.append(f"execution turnover exceeds {turnover_limit:.2f}x adaptive router in at least one split")
    return {
        "status": "admitted" if not reasons else "not_admitted",
        "split_count": split_count,
        "required_splits": int(required_splits),
        "not_worse_window_count": not_worse_count,
        "minimum_not_worse_windows": int(minimum_not_worse_windows),
        "turnover_limit": float(turnover_limit),
        "reasons": reasons,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_ready_manifest(root: Path, *, phase: str) -> dict[str, Any]:
    path = root / ("expert_panel_manifest.json" if phase == "B" else "moe_v2_manifest.json")
    if not path.is_file():
        raise AdmissionEvidenceError(f"{phase} manifest is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdmissionEvidenceError(f"{phase} manifest is unreadable: {path}") from exc
    if payload.get("phase") != phase or payload.get("status") != "ready":
        raise AdmissionEvidenceError(f"{phase} manifest must be phase={phase!r} and status='ready'.")
    return payload


def _verified_artifact(root: Path, manifest: dict[str, Any], key: str) -> Path:
    descriptor = (manifest.get("artifacts") or {}).get(key)
    if not isinstance(descriptor, dict) or not descriptor.get("path") or not descriptor.get("sha256"):
        raise AdmissionEvidenceError(f"manifest has no verifiable artifact descriptor for {key!r}")
    path = root / str(descriptor["path"])
    if not path.is_file() or _sha256_file(path) != str(descriptor["sha256"]):
        raise AdmissionEvidenceError(f"manifest artifact verification failed for {path}")
    return path


def _test_memberships(value: object) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    try:
        memberships = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AdmissionEvidenceError("panel split_memberships_json is invalid JSON") from exc
    if not isinstance(memberships, list):
        raise AdmissionEvidenceError("panel split_memberships_json must be a list")
    return {
        str(item.get("split_id"))
        for item in memberships
        if isinstance(item, dict) and item.get("role") == "test" and item.get("split_id")
    }


def _portfolio_metrics(daily_returns: pd.Series) -> dict[str, float]:
    returns = pd.to_numeric(daily_returns, errors="coerce").dropna()
    if returns.empty:
        raise AdmissionEvidenceError("no valid daily returns are available for a W11 split")
    equity = (1.0 + returns).cumprod()
    max_drawdown = float((equity / equity.cummax() - 1.0).min())
    return {"total_return": float(equity.iloc[-1] - 1.0), "max_drawdown": max_drawdown}


def _phase_d_decisions(weights: pd.DataFrame, *, variant: str) -> pd.DataFrame:
    frame = weights.loc[weights["variant"].astype(str).eq(variant)].copy()
    if "is_test_label" in frame.columns:
        frame = frame.loc[frame["is_test_label"].fillna(False).astype(bool)]
    frame = frame.loc[frame["evaluation_status"].isin(["ready", "fallback"])]
    required = {
        "split_id", "date", "symbol", "expert_weight", "realized_next_net_return", "final_target_position"
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise AdmissionEvidenceError(f"Phase-D daily weights are missing required columns: {missing}")
    rows: list[dict[str, Any]] = []
    for (split_id, date, symbol), group in frame.groupby(["split_id", "date", "symbol"], sort=True):
        positions = pd.to_numeric(group["final_target_position"], errors="coerce").dropna().unique()
        if len(positions) != 1:
            raise AdmissionEvidenceError("Phase-D final_target_position is not unique per split/date/symbol")
        selected = group.loc[pd.to_numeric(group["expert_weight"], errors="coerce").fillna(0.0) > 0].copy()
        returns = pd.to_numeric(selected["realized_next_net_return"], errors="coerce")
        if selected.empty or returns.isna().any():
            raise AdmissionEvidenceError("Phase-D decision lacks realized return for a selected expert")
        portfolio_return = float(
            (pd.to_numeric(selected["expert_weight"], errors="coerce") * returns).sum()
        )
        rows.append(
            {
                "split_id": str(split_id),
                "date": pd.Timestamp(date),
                "symbol": str(symbol),
                "candidate_target_position": float(positions[0]),
                "candidate_return": portfolio_return,
            }
        )
    if not rows:
        raise AdmissionEvidenceError(f"Phase-D has no ready test decisions for variant {variant!r}")
    return pd.DataFrame(rows)


def _adaptive_control_rows(panel: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "symbol", "expert_id", "expert_status", "strategy_return", "target_position", "split_memberships_json"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise AdmissionEvidenceError(f"Phase-B panel is missing adaptive-control columns: {missing}")
    adaptive = panel.loc[
        panel["expert_id"].astype(str).eq("adaptive_router")
        & panel["expert_status"].astype(str).eq("available")
    ].copy()
    rows: list[dict[str, Any]] = []
    for row in adaptive.itertuples(index=False):
        for split_id in _test_memberships(getattr(row, "split_memberships_json")):
            target = pd.to_numeric(pd.Series([getattr(row, "target_position")]), errors="coerce").iloc[0]
            daily_return = pd.to_numeric(pd.Series([getattr(row, "strategy_return")]), errors="coerce").iloc[0]
            if pd.isna(target) or pd.isna(daily_return):
                raise AdmissionEvidenceError("adaptive-router test row has missing target position or net return")
            rows.append(
                {
                    "split_id": split_id,
                    "date": pd.Timestamp(getattr(row, "date")),
                    "symbol": str(getattr(row, "symbol")),
                    "adaptive_target_position": float(target),
                    "adaptive_return": float(daily_return),
                }
            )
    if not rows:
        raise AdmissionEvidenceError("Phase-B panel has no available adaptive-router test rows")
    output = pd.DataFrame(rows)
    if output.duplicated(["split_id", "date", "symbol"]).any():
        raise AdmissionEvidenceError("adaptive-router test rows are not unique per split/date/symbol")
    return output


def build_w11_admission_evidence(
    *,
    panel_dir: str | Path,
    phase_d_dir: str | Path,
    candidate_variant: str = "moe_v2_regime_aware",
    required_splits: int = 4,
    minimum_not_worse_windows: int = 3,
    turnover_limit: float = 1.25,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build a strict W11 comparison from ready, hash-verified B/D artifacts."""

    panel_root = Path(panel_dir)
    phase_d_root = Path(phase_d_dir)
    panel_manifest = _load_ready_manifest(panel_root, phase="B")
    phase_d_manifest = _load_ready_manifest(phase_d_root, phase="D")
    if panel_manifest.get("market") != phase_d_manifest.get("market"):
        raise AdmissionEvidenceError("Phase-B and Phase-D market values do not match")
    if phase_d_manifest.get("phase_b_manifest_sha256") != _sha256_file(panel_root / "expert_panel_manifest.json"):
        raise AdmissionEvidenceError("Phase-D does not source-lock the supplied Phase-B manifest")

    panel_path = _verified_artifact(panel_root, panel_manifest, "expert_day_panel")
    weights_path = _verified_artifact(phase_d_root, phase_d_manifest, "daily_weights")
    panel = pd.read_parquet(panel_path)
    weights = pd.read_parquet(weights_path)
    candidate = _phase_d_decisions(weights, variant=candidate_variant)
    adaptive = _adaptive_control_rows(panel)
    merged = candidate.merge(adaptive, on=["split_id", "date", "symbol"], how="inner", validate="one_to_one")
    if len(merged) != len(candidate) or len(merged) != len(adaptive):
        raise AdmissionEvidenceError("candidate and adaptive-router test decision keys do not match exactly")

    candidate_turnover = calculate_execution_turnover(
        candidate.rename(columns={"candidate_target_position": "final_target_position"}),
        group_columns=("split_id", "symbol"),
    )[["split_id", "date", "symbol", "execution_turnover"]].rename(
        columns={"execution_turnover": "candidate_execution_turnover"}
    )
    adaptive_turnover = calculate_execution_turnover(
        adaptive.rename(columns={"adaptive_target_position": "final_target_position"}),
        group_columns=("split_id", "symbol"),
    )[["split_id", "date", "symbol", "execution_turnover"]].rename(
        columns={"execution_turnover": "adaptive_execution_turnover"}
    )
    merged = merged.merge(candidate_turnover, on=["split_id", "date", "symbol"], validate="one_to_one")
    merged = merged.merge(adaptive_turnover, on=["split_id", "date", "symbol"], validate="one_to_one")

    split_rows: list[dict[str, Any]] = []
    breadth_rows: list[dict[str, Any]] = []
    for split_id, group in merged.groupby("split_id", sort=True):
        candidate_daily = group.groupby("date", sort=True)["candidate_return"].mean()
        adaptive_daily = group.groupby("date", sort=True)["adaptive_return"].mean()
        candidate_metrics = _portfolio_metrics(candidate_daily)
        adaptive_metrics = _portfolio_metrics(adaptive_daily)
        candidate_turnover_mean = float(group.groupby("date")["candidate_execution_turnover"].mean().mean())
        adaptive_turnover_mean = float(group.groupby("date")["adaptive_execution_turnover"].mean().mean())
        turnover_ratio = (
            1.0 if candidate_turnover_mean == adaptive_turnover_mean == 0.0
            else np.inf if adaptive_turnover_mean == 0.0
            else candidate_turnover_mean / adaptive_turnover_mean
        )
        split_rows.append(
            {
                "split_id": str(split_id),
                "candidate_total_return": candidate_metrics["total_return"],
                "adaptive_total_return": adaptive_metrics["total_return"],
                "not_worse_than_adaptive": candidate_metrics["total_return"] >= adaptive_metrics["total_return"],
                "candidate_max_drawdown": candidate_metrics["max_drawdown"],
                "adaptive_max_drawdown": adaptive_metrics["max_drawdown"],
                "drawdown_not_worse": candidate_metrics["max_drawdown"] >= adaptive_metrics["max_drawdown"],
                "candidate_execution_turnover": candidate_turnover_mean,
                "adaptive_execution_turnover": adaptive_turnover_mean,
                "turnover_ratio": turnover_ratio,
            }
        )
        for symbol, symbol_group in group.groupby("symbol", sort=True):
            candidate_total = float((1.0 + symbol_group["candidate_return"]).prod() - 1.0)
            adaptive_total = float((1.0 + symbol_group["adaptive_return"]).prod() - 1.0)
            breadth_rows.append(
                {
                    "split_id": str(split_id),
                    "symbol": str(symbol),
                    "candidate_total_return": candidate_total,
                    "adaptive_total_return": adaptive_total,
                    "return_difference": candidate_total - adaptive_total,
                    "improved_or_equal": candidate_total >= adaptive_total,
                }
            )

    split_summary = pd.DataFrame(split_rows)
    breadth = pd.DataFrame(breadth_rows)
    decision = assess_w11_admission(
        split_summary,
        required_splits=required_splits,
        minimum_not_worse_windows=minimum_not_worse_windows,
        turnover_limit=turnover_limit,
    )
    decision.update(
        {
            "market": str(panel_manifest.get("market")),
            "candidate_variant": candidate_variant,
            "phase_b_manifest_sha256": _sha256_file(panel_root / "expert_panel_manifest.json"),
            "phase_d_manifest_sha256": _sha256_file(phase_d_root / "moe_v2_manifest.json"),
            "symbol_return_difference_median": float(breadth["return_difference"].median()) if not breadth.empty else None,
            "symbol_improvement_ratio": float(breadth["improved_or_equal"].mean()) if not breadth.empty else None,
        }
    )
    return split_summary, breadth, decision


def write_w11_admission_evidence(
    output_dir: str | Path,
    *,
    split_summary: pd.DataFrame,
    breadth: pd.DataFrame,
    decision: dict[str, Any],
) -> dict[str, Path]:
    """Persist W11 evidence without modifying source Phase-B/D directories."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    split_path = target / "w11_split_summary.csv"
    breadth_path = target / "w11_symbol_breadth.csv"
    decision_path = target / "w11_decision.json"
    split_summary.to_csv(split_path, index=False)
    breadth.to_csv(breadth_path, index=False)
    decision_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"split_summary": split_path, "breadth": breadth_path, "decision": decision_path}


__all__ = [
    "AdmissionEvidenceError",
    "assess_w11_admission",
    "build_w11_admission_evidence",
    "calculate_execution_turnover",
    "write_w11_admission_evidence",
]
