"""Run the expert-system reconstruction Phase 1 experiment.

The formal run compares three otherwise aligned retrieval baselines on the
frozen US Validation folds:

- B01: frozen 28-state-feature panel, 5-day future utility labels.
- B04: the same 28 features, 20-day future utility labels.
- B05: the same 20-day labels plus exactly five observed macro dimensions.

All expert utilities are rebuilt from the frozen, already-costed
``strategy_return`` series. No mock experts or synthetic market data are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))

from core.macro_factors import MACRO_FEATURE_COLUMNS, MacroFactors
from model_test.expert_system_phase1 import (
    ExpertSystemPhase1Error,
    append_macro_sequences,
    build_horizon_sequence_panel,
)
from model_test.transformer_state_baseline import (
    BaselineConfig,
    BaselineResult,
    compare_baselines,
    run_baseline_experiment,
    save_baseline_artifacts,
)


DEFAULT_CONFIG = REPO_ROOT / "model-test" / "configs" / "expert_system_phase1_us.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _repo_path(value: str, *, field: str) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise ExpertSystemPhase1Error(f"{field} escapes the repository: {resolved}")
    return resolved


def _verify_file(path: Path, expected_hash: str, *, label: str) -> None:
    if not path.is_file():
        raise ExpertSystemPhase1Error(f"missing {label}: {path}")
    if _sha256_file(path) != str(expected_hash):
        raise ExpertSystemPhase1Error(f"{label} SHA-256 drifted: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExpertSystemPhase1Error(f"unable to read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExpertSystemPhase1Error(f"expected JSON object: {path}")
    return value


def _git_code_version() -> str:
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return f"{commit}-dirty" if dirty else commit


def _phase1_code_lock() -> dict[str, Any]:
    """Hash every implementation file that can change the formal result."""

    relative_paths = (
        "core/macro_factors.py",
        "model-test/model_test/expert_panel.py",
        "model-test/model_test/expert_system_phase1.py",
        "model-test/model_test/transformer_state_baseline.py",
        "model-test/run_phase1_baseline.py",
    )
    artifacts = []
    for relative_path in relative_paths:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            raise ExpertSystemPhase1Error(f"missing Phase 1 code-lock file: {path}")
        artifacts.append(
            {
                "path": relative_path,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "artifacts": artifacts,
        "aggregate_sha256": _json_hash(artifacts),
    }


def load_config(path: Path) -> dict[str, Any]:
    config = _read_json(path)
    if config.get("schema_version") != "1.0" or config.get("market") != "US":
        raise ExpertSystemPhase1Error("Phase 1 config must be schema 1.0 for market US")
    if int(config.get("random_seed", -1)) != 42:
        raise ExpertSystemPhase1Error("Phase 1 random seed is frozen at 42")
    experts = [str(value) for value in config.get("experts") or []]
    if len(experts) != 8 or len(set(experts)) != 8 or "cash" not in experts:
        raise ExpertSystemPhase1Error("Phase 1 requires the frozen eight-expert panel")
    feature_config = config.get("features") or {}
    if int(feature_config.get("base_feature_count", -1)) != 28:
        raise ExpertSystemPhase1Error("B01/B04 base feature count must remain 28")
    if tuple(feature_config.get("macro_feature_columns") or ()) != MACRO_FEATURE_COLUMNS:
        raise ExpertSystemPhase1Error("B05 macro feature schema differs from the core contract")
    if int(feature_config.get("macro_feature_count", -1)) != len(MACRO_FEATURE_COLUMNS):
        raise ExpertSystemPhase1Error("B05 must add exactly five macro features")
    labels = config.get("labels") or {}
    if labels.get("return_field") != "strategy_return":
        raise ExpertSystemPhase1Error("strategy_return is the only allowed label return field")
    if labels.get("cost_treatment") != "source_net_no_recharge":
        raise ExpertSystemPhase1Error("source execution costs must not be charged twice")
    return config


def _load_sequence_source(
    config: dict[str, Any],
) -> tuple[pd.DataFrame, list[str], dict[str, Any], Path]:
    sources = config["sources"]
    source_dir = _repo_path(sources["sequence_panel_dir"], field="sequence_panel_dir")
    manifest_path = source_dir / "state_panel_manifest.json"
    _verify_file(
        manifest_path,
        sources["sequence_panel_manifest_sha256"],
        label="frozen state panel manifest",
    )
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "ready" or manifest.get("market") != "US":
        raise ExpertSystemPhase1Error("frozen state panel is not ready for US")
    artifact_map = {
        "state_sequence_panel": "state_sequence_panel.parquet",
        "feature_schema": "state_feature_schema.json",
    }
    verified: dict[str, Path] = {}
    for key, expected_name in artifact_map.items():
        descriptor = (manifest.get("artifacts") or {}).get(key) or {}
        if descriptor.get("path") != expected_name:
            raise ExpertSystemPhase1Error(f"state panel manifest lacks fixed artifact {key}")
        path = source_dir / expected_name
        _verify_file(path, descriptor.get("sha256"), label=f"state panel {key}")
        verified[key] = path
    panel = pd.read_parquet(verified["state_sequence_panel"])
    schema = _read_json(verified["feature_schema"])
    feature_columns = [str(value) for value in schema.get("feature_columns") or []]
    if len(feature_columns) != 28:
        raise ExpertSystemPhase1Error("frozen state feature schema must contain 28 columns")
    return panel, feature_columns, manifest, manifest_path


def _load_phase_b_source(
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], Path]:
    sources = config["sources"]
    source_dir = _repo_path(sources["phase_b_dir"], field="phase_b_dir")
    manifest_path = source_dir / "expert_panel_manifest.json"
    panel_path = source_dir / "expert_day_panel.parquet"
    splits_path = source_dir / "expert_panel_walk_forward_splits.csv"
    _verify_file(manifest_path, sources["phase_b_manifest_sha256"], label="Phase-B manifest")
    _verify_file(panel_path, sources["phase_b_panel_sha256"], label="Phase-B expert panel")
    _verify_file(splits_path, sources["phase_b_splits_sha256"], label="Phase-B split file")
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "ready" or manifest.get("market") != "US":
        raise ExpertSystemPhase1Error("Phase-B source is not ready for US")
    panel = pd.read_parquet(panel_path)
    if set(pd.to_numeric(panel["label_horizon_days"], errors="coerce").dropna().astype(int)) != {20}:
        raise ExpertSystemPhase1Error("Phase-B source is not the frozen 20-day panel")
    if set(panel["cost_treatment"].dropna().astype(str)) != {"source_net_no_recharge"}:
        raise ExpertSystemPhase1Error("Phase-B source cost treatment drifted")
    splits = pd.read_csv(splits_path)
    configured_folds = set(config["validation"]["folds"])
    if set(splits["split_id"].astype(str)) != configured_folds or not splits["status"].eq("ready").all():
        raise ExpertSystemPhase1Error("Phase-B split set differs from the configured four folds")
    return panel, splits, manifest, manifest_path


def _load_snapshot_universe(
    config: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    sources = config["sources"]
    full_dir = _repo_path(sources["full_run_dir"], field="full_run_dir")
    manifest_path = full_dir / "data_manifest.json"
    _verify_file(
        manifest_path,
        sources["full_run_data_manifest_sha256"],
        label="full-run data manifest",
    )
    manifest = _read_json(manifest_path)
    if (manifest.get("data") or {}).get("snapshot_sha256") != sources["data_snapshot_sha256"]:
        raise ExpertSystemPhase1Error("full-run snapshot aggregate hash differs from config")
    records = (manifest.get("universe") or {}).get("files") or []
    if len(records) != 60:
        raise ExpertSystemPhase1Error("Phase 1 requires the frozen 60-symbol US universe")
    snapshot_dir = full_dir / "data_snapshot"
    universe: dict[str, pd.DataFrame] = {}
    for record in records:
        symbol = str(record.get("symbol") or "").upper()
        path = snapshot_dir / f"{symbol}_daily.csv"
        _verify_file(path, record.get("sha256"), label=f"snapshot {symbol}")
        universe[symbol] = pd.read_csv(path)
    return universe


def _load_macro_inputs(config: dict[str, Any]) -> tuple[MacroFactors, dict[str, str], Path]:
    sources = config["sources"]
    macro_dir = _repo_path(sources["macro_data_dir"], field="macro_data_dir")
    manifest_path = macro_dir / "macro_data_manifest.json"
    _verify_file(
        manifest_path,
        sources["macro_data_manifest_sha256"],
        label="observed macro data manifest",
    )
    manifest = _read_json(manifest_path)
    if manifest.get("data_kind") != "observed" or manifest.get("synthetic_fallback") is not False:
        raise ExpertSystemPhase1Error("Phase 1 macro source must be observed and fail-closed")
    sector_descriptor = (manifest.get("artifacts") or {}).get("us_sector_map") or {}
    sector_path = macro_dir / str(sector_descriptor.get("path") or "")
    _verify_file(sector_path, sector_descriptor.get("sha256"), label="US sector map")
    sector_frame = pd.read_csv(sector_path, dtype={"symbol": str})
    sector_map = dict(zip(sector_frame["symbol"].str.upper(), sector_frame["sector"].astype(str)))
    return MacroFactors(macro_data_dir=macro_dir), sector_map, manifest_path


def _membership_mask(panel: pd.DataFrame, split_id: str, role: str) -> np.ndarray:
    values: list[bool] = []
    for raw in panel["split_memberships_json"].fillna("[]"):
        try:
            memberships = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ExpertSystemPhase1Error("split_memberships_json is invalid") from exc
        values.append(
            any(
                str(item.get("split_id")) == split_id and str(item.get("role")) == role
                for item in memberships
            )
        )
    return np.asarray(values, dtype=bool)


def _aligned_panels(
    sequence_panel: pd.DataFrame,
    expert_panel: pd.DataFrame,
    macro_panel: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    def sequence_width(value: Any) -> int:
        raw = value.tolist() if isinstance(value, np.ndarray) and value.dtype == object else value
        matrix = np.asarray(raw, dtype=float)
        if matrix.ndim != 2:
            raise ExpertSystemPhase1Error("sequence values must be two-dimensional")
        return int(matrix.shape[1])

    labels = config["labels"]
    experts = tuple(config["experts"])
    common = {
        "expert_ids": experts,
        "lambda_downside": float(labels["lambda_downside"]),
        "lambda_turnover": float(labels["lambda_turnover"]),
    }
    panel_5d = build_horizon_sequence_panel(
        sequence_panel,
        expert_panel,
        horizon_days=int(labels["b01_horizon_days"]),
        **common,
    )
    panel_20d = build_horizon_sequence_panel(
        sequence_panel,
        expert_panel,
        horizon_days=int(labels["phase1_horizon_days"]),
        **common,
    )
    key_columns = ["sequence_end_date", "symbol"]
    common_keys = panel_20d[key_columns].drop_duplicates()
    panel_5d = panel_5d.merge(common_keys, on=key_columns, how="inner", validate="one_to_one")
    panel_20d = panel_20d.merge(common_keys, on=key_columns, how="inner", validate="one_to_one")
    ordered_keys = panel_20d[key_columns]
    if not panel_5d[key_columns].reset_index(drop=True).equals(ordered_keys.reset_index(drop=True)):
        panel_5d = ordered_keys.merge(panel_5d, on=key_columns, how="left", validate="one_to_one")
    panel_33d = append_macro_sequences(panel_20d, macro_panel)
    base_widths = {sequence_width(value) for value in panel_20d["sequence_values"]}
    macro_widths = {sequence_width(value) for value in panel_33d["sequence_values"]}
    if base_widths != {28} or macro_widths != {33}:
        raise ExpertSystemPhase1Error(
            f"feature width contract failed: base={sorted(base_widths)}, macro={sorted(macro_widths)}"
        )
    return {"B01": panel_5d, "B04": panel_20d, "B05": panel_33d}


def _run_fold(
    *,
    method_id: str,
    panel: pd.DataFrame,
    feature_columns: list[str],
    split_row: pd.Series,
    config: dict[str, Any],
    output_dir: Path,
) -> BaselineResult:
    split_id = str(split_row["split_id"])
    train = panel.loc[_membership_mask(panel, split_id, "train")].reset_index(drop=True)
    validation = panel.loc[_membership_mask(panel, split_id, "validation")].reset_index(drop=True)
    if train.empty or validation.empty:
        raise ExpertSystemPhase1Error(f"{method_id}/{split_id} has an empty role")
    if pd.Timestamp(train["sequence_end_date"].max()) >= pd.Timestamp(
        validation["sequence_end_date"].min()
    ):
        raise ExpertSystemPhase1Error(f"{method_id}/{split_id} violates strictly-prior memory")
    baseline = BaselineConfig(
        method="pca_single_day",
        top_k=int(config["retrieval"]["top_k"]),
        pca_variance_threshold=float(config["retrieval"]["pca_variance_threshold"]),
        random_seed=int(config["random_seed"]),
        expert_ids=tuple(config["experts"]),
    )
    result = run_baseline_experiment(
        config=baseline,
        panel_train=train,
        panel_query=validation,
        feature_columns=feature_columns,
        fold_id=split_id,
    )
    result = replace(result, method=method_id)
    horizon = int(train["label_horizon_days"].iloc[0])
    signature = "|".join(
        str(split_row[column])
        for column in ("train_start", "train_end", "validation_start", "validation_end")
    )
    result.query_metrics.insert(0, "method", method_id)
    result.query_metrics.insert(1, "fold_id", split_id)
    result.query_metrics.insert(2, "split_signature", signature)
    result.query_metrics.insert(3, "label_horizon_days", horizon)
    result.query_metrics["query_selected_utility_per_day"] = (
        result.query_metrics["query_selected_utility"] / float(horizon)
    )
    result.query_metrics["query_oracle_utility_per_day"] = (
        result.query_metrics["query_oracle_utility"] / float(horizon)
    )
    save_baseline_artifacts(result, output_dir / method_id / split_id)
    print(
        f"{method_id}/{split_id}: train={len(train)}, validation={len(validation)}, "
        f"query_utility={result.neighbor_utility_stats['mean_query_selected_utility']:.6f}, "
        f"match={result.neighbor_utility_stats['expert_match_rate']:.2%}"
    )
    return result


def _bootstrap_delta(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    metric: str,
    iterations: int,
    random_seed: int,
) -> dict[str, Any]:
    keys = ["fold_id", "query_date", "symbol"]
    paired = left[keys + [metric]].merge(
        right[keys + [metric]],
        on=keys,
        how="inner",
        suffixes=("_candidate", "_reference"),
        validate="one_to_one",
    )
    if len(paired) != len(left) or len(paired) != len(right):
        raise ExpertSystemPhase1Error(f"paired comparison alignment failed for {metric}")
    candidate_values = pd.to_numeric(
        paired[f"{metric}_candidate"], errors="raise"
    ).astype(float)
    reference_values = pd.to_numeric(
        paired[f"{metric}_reference"], errors="raise"
    ).astype(float)
    paired["difference"] = candidate_values - reference_values
    clusters = (
        paired.assign(
            cluster=paired["fold_id"].astype(str)
            + "|"
            + pd.to_datetime(paired["query_date"]).dt.strftime("%Y-%m-%d")
        )
        .groupby("cluster", sort=True)["difference"]
        .mean()
        .to_numpy(dtype=float)
    )
    if len(clusters) < 2:
        raise ExpertSystemPhase1Error("paired bootstrap requires at least two date clusters")
    rng = np.random.default_rng(random_seed)
    draws = np.empty(int(iterations), dtype=float)
    for index in range(int(iterations)):
        draws[index] = float(rng.choice(clusters, size=len(clusters), replace=True).mean())
    lower, upper = np.quantile(draws, [0.025, 0.975])
    observed = float(clusters.mean())
    return {
        "metric": metric,
        "observed_difference": observed,
        "ci_95_lower": float(lower),
        "ci_95_upper": float(upper),
        "one_sided_p_value": float((1 + np.count_nonzero(draws <= 0.0)) / (len(draws) + 1)),
        "date_clusters": int(len(clusters)),
        "paired_queries": int(len(paired)),
        "bootstrap_iterations": int(iterations),
    }


def _comparisons(
    query_metrics: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    comparisons = (("B04", "B01"), ("B05", "B04"))
    metrics = (
        "query_selected_utility",
        "query_selected_utility_per_day",
        "expert_match",
        "query_oracle_utility",
        "regret",
    )
    rows: list[dict[str, Any]] = []
    iterations = int(config["validation"]["bootstrap_iterations"])
    for pair_offset, (candidate, reference) in enumerate(comparisons):
        left = query_metrics.loc[query_metrics["method"].eq(candidate)].copy()
        right = query_metrics.loc[query_metrics["method"].eq(reference)].copy()
        for metric_offset, metric in enumerate(metrics):
            row = _bootstrap_delta(
                left,
                right,
                metric=metric,
                iterations=iterations,
                random_seed=int(config["random_seed"]) + pair_offset * 20 + metric_offset,
            )
            row["candidate"] = candidate
            row["reference"] = reference
            rows.append(row)
    return pd.DataFrame(rows)


def _decision(comparisons: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    acceptance = config["acceptance"]

    def delta(candidate: str, reference: str, metric: str) -> float:
        row = comparisons.loc[
            comparisons["candidate"].eq(candidate)
            & comparisons["reference"].eq(reference)
            & comparisons["metric"].eq(metric)
        ]
        if len(row) != 1:
            raise ExpertSystemPhase1Error(f"missing comparison {candidate}/{reference}/{metric}")
        return float(row.iloc[0]["observed_difference"])

    b04_raw_utility = delta("B04", "B01", "query_selected_utility")
    b04_utility_per_day = delta("B04", "B01", "query_selected_utility_per_day")
    b04_match = delta("B04", "B01", "expert_match")
    b05_utility = delta("B05", "B04", "query_selected_utility")
    b05_regret = delta("B05", "B04", "regret")
    horizon_pass = (
        b04_utility_per_day
        > float(acceptance["b04_query_utility_per_day_delta_min"])
        and b04_match > float(acceptance["b04_match_rate_delta_min"])
    )
    macro_pass = (
        b05_utility > float(acceptance["b05_query_utility_delta_min"])
        and b05_regret < float(acceptance["b05_regret_delta_max"])
    )
    if horizon_pass and macro_pass:
        branch = "enter_phase2"
    elif horizon_pass:
        branch = "horizon_only_phase2_simplified"
    else:
        branch = "stop_phase1_gate_failed"
    return {
        "horizon_pass": bool(horizon_pass),
        "macro_pass": bool(macro_pass),
        "branch": branch,
        "observed": {
            "b04_vs_b01_raw_query_utility_delta": b04_raw_utility,
            "b04_vs_b01_query_utility_per_day_delta": b04_utility_per_day,
            "b04_vs_b01_match_rate_delta": b04_match,
            "b05_vs_b04_query_utility_delta": b05_utility,
            "b05_vs_b04_regret_delta": b05_regret,
        },
        "note": (
            "B01/B04 use different horizons, so the admission gate uses per-day "
            "normalized utility. Raw accumulated utility remains diagnostic only."
        ),
    }


def _write_report(
    output_dir: Path,
    method_summary: pd.DataFrame,
    comparisons: pd.DataFrame,
    decision: dict[str, Any],
    source_summary: dict[str, Any],
) -> Path:
    report = [
        "# Expert System Reconstruction — Phase 1",
        "",
        f"> Generated: {datetime.now(timezone.utc).isoformat()}",
        "> Scope: frozen US 60-symbol universe, four Validation folds, eight real experts.",
        "",
        "## Method summary",
        "",
        method_summary.to_markdown(index=False),
        "",
        "## Paired comparisons",
        "",
        comparisons.to_markdown(index=False),
        "",
        "## Admission decision",
        "",
        f"- Horizon gate: `{decision['horizon_pass']}`",
        f"- Macro gate: `{decision['macro_pass']}`",
        f"- Branch: `{decision['branch']}`",
        f"- Observed deltas: `{json.dumps(decision['observed'], ensure_ascii=False)}`",
        f"- Methodology note: {decision['note']}",
        "",
        "The B05 oracle utility is expected to equal B04 because both methods use the same",
        "query rows and 20-day labels; feature value is therefore assessed through selected",
        "query utility and regret, not by claiming that features can change the oracle.",
        "",
        "## Source lock",
        "",
        "```json",
        json.dumps(source_summary, indent=2, ensure_ascii=False, sort_keys=True),
        "```",
    ]
    path = output_dir / "phase1_comparison_report.md"
    path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return path


def _artifact_inventory(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "phase1_evidence_manifest.json":
            rows.append(
                {
                    "path": path.relative_to(output_dir).as_posix(),
                    "sha256": _sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    return rows


def run_phase1(config: dict[str, Any], output_dir: Path, config_path: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sequence_panel, base_features, sequence_manifest, sequence_manifest_path = _load_sequence_source(
        config
    )
    expert_panel, splits, phase_b_manifest, phase_b_manifest_path = _load_phase_b_source(config)
    universe = _load_snapshot_universe(config)
    macro_factors, sector_map, macro_manifest_path = _load_macro_inputs(config)
    print("Computing observed VIX/SPY/breadth/beta/sector features...")
    macro_panel = macro_factors.compute_universe_panel(universe, sector_map=sector_map)
    macro_panel.to_parquet(output_dir / "macro_feature_panel.parquet", index=False)

    panels = _aligned_panels(sequence_panel, expert_panel, macro_panel, config)
    feature_columns = {
        "B01": base_features,
        "B04": base_features,
        "B05": [*base_features, *MACRO_FEATURE_COLUMNS],
    }
    results: list[BaselineResult] = []
    for _, split_row in splits.sort_values("split_id").iterrows():
        for method_id in ("B01", "B04", "B05"):
            results.append(
                _run_fold(
                    method_id=method_id,
                    panel=panels[method_id],
                    feature_columns=feature_columns[method_id],
                    split_row=split_row,
                    config=config,
                    output_dir=output_dir,
                )
            )

    method_summary = compare_baselines(results)
    method_summary["label_horizon_days"] = method_summary["method"].map(
        {"B01": 5, "B04": 20, "B05": 20}
    )
    method_summary["feature_count"] = method_summary["method"].map(
        {"B01": 28, "B04": 28, "B05": 33}
    )
    method_summary.to_csv(output_dir / "phase1_method_fold_summary.csv", index=False)
    query_metrics = pd.concat([result.query_metrics for result in results], ignore_index=True)
    query_metrics.to_parquet(output_dir / "phase1_query_metrics.parquet", index=False)
    comparisons = _comparisons(query_metrics, config)
    comparisons.to_csv(output_dir / "phase1_statistical_tests.csv", index=False)
    decision = _decision(comparisons, config)
    source_summary = {
        "config_path": config_path.relative_to(REPO_ROOT).as_posix(),
        "config_sha256": _sha256_file(config_path),
        "sequence_panel_manifest_sha256": _sha256_file(sequence_manifest_path),
        "sequence_panel_artifact_sha256": (
            (sequence_manifest.get("artifacts") or {}).get("state_sequence_panel") or {}
        ).get("sha256"),
        "phase_b_manifest_sha256": _sha256_file(phase_b_manifest_path),
        "phase_b_panel_sha256": config["sources"]["phase_b_panel_sha256"],
        "macro_data_manifest_sha256": _sha256_file(macro_manifest_path),
        "data_snapshot_sha256": config["sources"]["data_snapshot_sha256"],
        "phase_b_source_run_id": phase_b_manifest.get("source_run_id"),
    }
    _write_report(output_dir, method_summary, comparisons, decision, source_summary)
    summary = {
        "schema_version": "1.0",
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": "US",
        "methods": ["B01", "B04", "B05"],
        "folds": config["validation"]["folds"],
        "decision": decision,
        "source_lock": source_summary,
        "row_counts": {
            method: int(len(panel)) for method, panel in panels.items()
        },
        "macro_rows": int(len(macro_panel)),
    }
    summary_path = output_dir / "phase1_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    artifacts = _artifact_inventory(output_dir)
    code_lock = _phase1_code_lock()
    evidence = {
        "schema_version": "1.0",
        "status": "ready",
        "market": "US",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": _git_code_version(),
        "code_lock": code_lock,
        "code_lock_sha256": code_lock["aggregate_sha256"],
        "source_lock": source_summary,
        "decision": decision,
        "artifacts": artifacts,
        "artifact_aggregate_sha256": _json_hash(artifacts),
    }
    evidence_path = output_dir / "phase1_evidence_manifest.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG.relative_to(REPO_ROOT)))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    config_path = _repo_path(args.config, field="config")
    config = load_config(config_path)
    output_dir = (
        _repo_path(args.output, field="output")
        if args.output
        else REPO_ROOT / "model-test" / "outputs" / str(config["output_subdir"])
    )
    summary = run_phase1(config, output_dir.resolve(), config_path)
    print(json.dumps(summary["decision"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
