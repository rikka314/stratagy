"""Leak-free source lock and five-day state panel for Transformer research.

This module implements W13 and W14 of the post-Gate-2 Transformer-state
research plan.  It consumes the already-frozen, market-specific Phase-A/B
artifacts and the authoritative full-run evidence without modifying either.
Source execution costs are already present in ``strategy_return`` and are
never charged again here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from model_test.expert_panel import compute_future_utility
from model_test.moe_baseline import build_phase_a_manifest


TRANSFORMER_STATE_SCHEMA_VERSION = "1.0"
LABEL_HORIZON_DAYS = 5
SOURCE_MANIFEST_NAME = "transformer_state_source_manifest.json"
PANEL_MANIFEST_NAME = "state_panel_manifest.json"
FEATURE_SCHEMA_NAME = "state_feature_schema.json"
SEQUENCE_PANEL_NAME = "state_sequence_panel.parquet"
LABEL_PANEL_NAME = "state_label_panel.parquet"
SPLITS_NAME = "transformer_state_walk_forward_splits.csv"
QUALITY_JSON_NAME = "state_panel_quality.json"
QUALITY_MD_NAME = "state_panel_quality.md"

FORBIDDEN_FEATURE_TOKENS = (
    "future_",
    "label",
    "best_expert",
    "outcome",
    "realized_next",
    "test_result",
)

STATE_FEATURE_COLUMNS = (
    "asset_return_1",
    "asset_trend_5",
    "asset_trend_20",
    "asset_volatility_5",
    "asset_volatility_20",
    "asset_atr_pct_14",
    "asset_liquidity_20",
    "asset_drawdown_60",
    "asset_volume_ratio_20",
    "market_return_1",
    "market_return_5",
    "market_return_20",
    "market_volatility_20",
    "market_trend_20",
    "market_drawdown_60",
    "market_constituent_count",
    "state_market_trend_up_20",
    "state_market_high_volatility_20",
    "state_market_regime_id_20",
    "state_duration_days",
    "state_switch_1",
    "asset_relative_strength_20",
    "asset_market_beta_20",
    "asset_market_correlation_20",
    "expert_active_fraction",
    "expert_recent_net_return_5_mean",
    "expert_turnover_5_mean",
    "expert_peer_correlation_20_mean",
)


class TransformerStatePanelError(ValueError):
    """Raised when W13/W14 source, chronology, or schema contracts fail."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransformerStatePanelError(f"Unable to read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise TransformerStatePanelError(f"Expected a JSON object: {path}")
    return value


def _git_code_version(repo_root: Path) -> str:
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return f"{commit}-dirty" if commit and dirty else (commit or "unavailable")


def transformer_code_lock(repo_root: str | Path) -> dict[str, Any]:
    """Hash the exact W13-W15 implementation even in a dirty worktree."""

    root = Path(repo_root).resolve()
    relative_paths = (
        Path("model-test/model_test/expert_panel.py"),
        Path("model-test/model_test/moe_baseline.py"),
        Path("model-test/model_test/transformer_state_panel.py"),
        Path("model-test/model_test/transformer_state_model.py"),
        Path("model-test/run_transformer_state.py"),
    )
    artifacts: list[dict[str, Any]] = []
    for relative in relative_paths:
        path = root / relative
        if not path.is_file():
            raise TransformerStatePanelError(f"Transformer implementation file is missing: {relative}")
        artifacts.append(
            {
                "path": relative.as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {"artifacts": artifacts, "aggregate_sha256": _json_sha256(artifacts)}


def _canonical_market(value: Any) -> str:
    market = str(value or "").strip().upper().replace("-", "_")
    if market in {"CN", "A", "CN_A"}:
        return "CN_A"
    if market == "US":
        return market
    raise TransformerStatePanelError(f"Unsupported market: {value!r}")


def _relative_path(value: Any, *, field_name: str) -> Path:
    path = Path(str(value or ""))
    if not str(value or "").strip() or path.is_absolute() or ".." in path.parts:
        raise TransformerStatePanelError(f"{field_name} must be a repository-relative path")
    return path


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_symbol(value: Any, market: str) -> str:
    symbol = str(value or "").strip()
    if symbol.endswith(".0") and symbol[:-2].isdigit():
        symbol = symbol[:-2]
    return symbol.zfill(6) if market == "CN_A" and symbol.isdigit() else symbol.upper()


def _resolve_repo_path(repo_root: Path, value: Any, *, field_name: str) -> Path:
    path = (repo_root / _relative_path(value, field_name=field_name)).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise TransformerStatePanelError(f"{field_name} resolves outside the repository") from exc
    return path


def _verify_hash(path: Path, expected: Any, *, label: str) -> str:
    if not path.is_file():
        raise TransformerStatePanelError(f"Missing {label}: {path}")
    actual = _sha256_file(path)
    if actual != str(expected or ""):
        raise TransformerStatePanelError(f"{label} SHA-256 drift: {path}")
    return actual


def load_transformer_state_config(path: str | Path) -> dict[str, Any]:
    config = _json_object(Path(path))
    validate_transformer_state_config(config)
    return config


def validate_transformer_state_config(config: dict[str, Any]) -> None:
    if str(config.get("schema_version")) != TRANSFORMER_STATE_SCHEMA_VERSION:
        raise TransformerStatePanelError(
            f"schema_version must be {TRANSFORMER_STATE_SCHEMA_VERSION!r}"
        )
    if config.get("phase") != "transformer_state_v2":
        raise TransformerStatePanelError("phase must be transformer_state_v2")
    _canonical_market(config.get("market"))
    if int(config.get("random_seed", -1)) != 42:
        raise TransformerStatePanelError("random_seed is frozen at 42")
    if config.get("training_scope") != "market_specific":
        raise TransformerStatePanelError("training_scope must remain market_specific")
    if config.get("cross_market_policy") != "forbidden":
        raise TransformerStatePanelError("cross_market_policy must remain forbidden")
    _relative_path(config.get("output_subdir"), field_name="output_subdir")

    sources = config.get("sources")
    if not isinstance(sources, dict):
        raise TransformerStatePanelError("sources must be an object")
    path_fields = (
        "phase_a_config_path",
        "phase_a_output_dir",
        "phase_b_output_dir",
        "full_run_config_path",
        "full_run_output_dir",
    )
    hash_fields = (
        "phase_a_manifest_sha256",
        "phase_b_manifest_sha256",
        "phase_b_panel_sha256",
        "phase_b_splits_sha256",
        "full_run_config_sha256",
        "full_run_config_snapshot_sha256",
        "full_run_source_manifest_sha256",
        "full_run_model_summary_sha256",
        "data_snapshot_sha256",
    )
    for field in path_fields:
        _relative_path(sources.get(field), field_name=f"sources.{field}")
    for field in hash_fields:
        value = str(sources.get(field) or "")
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise TransformerStatePanelError(f"sources.{field} must be a lowercase SHA-256")

    returns = config.get("returns") or {}
    if returns.get("net_return_field") != "strategy_return":
        raise TransformerStatePanelError("strategy_return is the only allowed net return field")
    if returns.get("cost_treatment") != "source_net_no_recharge":
        raise TransformerStatePanelError("source execution costs must not be charged twice")
    source_execution = config.get("source_execution") or {}
    for field in ("commission_bps", "slippage_bps"):
        value = _finite(source_execution.get(field))
        if value is None or value < 0:
            raise TransformerStatePanelError(f"source_execution.{field} must be finite and non-negative")

    experts = [str(value) for value in config.get("experts") or []]
    if len(experts) < 2 or len(set(experts)) != len(experts) or "cash" not in experts:
        raise TransformerStatePanelError("experts must be unique and include cash")
    guard = config.get("full_run_best_guard") or {}
    if int(guard.get("rank", -1)) != 1 or not guard.get("source_model_id") or not guard.get("expert_id"):
        raise TransformerStatePanelError("full_run_best_guard must freeze one rank-1 model mapping")
    if guard.get("expert_id") not in experts or guard.get("target_position_required") is not True:
        raise TransformerStatePanelError("full_run_best_guard expert and target-position policy are invalid")

    benchmark = config.get("benchmark") or {}
    if benchmark.get("method") != "frozen_universe_equal_weight_close_return":
        raise TransformerStatePanelError("benchmark method must be the frozen market-universe return")
    if int(benchmark.get("minimum_constituents", 0)) <= 0:
        raise TransformerStatePanelError("benchmark.minimum_constituents must be positive")

    panel = config.get("panel") or {}
    if int(panel.get("label_horizon_days", -1)) != LABEL_HORIZON_DAYS:
        raise TransformerStatePanelError("the primary label horizon is frozen at five trading days")
    lengths = [int(value) for value in panel.get("sequence_length_candidates") or []]
    if not lengths or any(value <= 1 for value in lengths) or int(panel.get("primary_sequence_length", 0)) not in lengths:
        raise TransformerStatePanelError("sequence length candidates/primary selection are invalid")
    protection = int(panel.get("protection_days", 0))
    if protection < max(max(lengths), LABEL_HORIZON_DAYS):
        raise TransformerStatePanelError("protection_days must cover the longest sequence and label horizon")
    if int(panel.get("n_splits", 0)) != 4:
        raise TransformerStatePanelError("formal transformer-state research requires four splits")

    retrieval = config.get("retrieval") or {}
    expected_quantiles = {
        "state_match_loose": 0.5,
        "state_match_balanced": 0.75,
        "state_match_strict": 0.9,
    }
    if retrieval.get("threshold_quantiles") != expected_quantiles:
        raise TransformerStatePanelError("retrieval thresholds must remain train-derived q50/q75/q90")
    if retrieval.get("primary_variant") != "state_match_balanced":
        raise TransformerStatePanelError("the preregistered primary retrieval variant is balanced/q75")


def _load_verified_phase_b(
    config: dict[str, Any], *, repo_root: Path
) -> tuple[Path, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    sources = config["sources"]
    market = _canonical_market(config["market"])
    phase_dir = _resolve_repo_path(repo_root, sources["phase_b_output_dir"], field_name="phase_b_output_dir")
    phase_a_manifest_path = phase_dir / "data_manifest.json"
    phase_b_manifest_path = phase_dir / "expert_panel_manifest.json"
    panel_path = phase_dir / "expert_day_panel.parquet"
    splits_path = phase_dir / "expert_panel_walk_forward_splits.csv"
    _verify_hash(
        phase_a_manifest_path,
        sources["phase_a_manifest_sha256"],
        label="Phase-A source manifest",
    )
    _verify_hash(
        phase_b_manifest_path,
        sources["phase_b_manifest_sha256"],
        label="Phase-B panel manifest",
    )
    _verify_hash(panel_path, sources["phase_b_panel_sha256"], label="Phase-B expert panel")
    _verify_hash(splits_path, sources["phase_b_splits_sha256"], label="Phase-B split file")
    phase_a_manifest = _json_object(phase_a_manifest_path)
    phase_b_manifest = _json_object(phase_b_manifest_path)
    if phase_a_manifest.get("status") != "ready" or phase_b_manifest.get("status") != "ready":
        raise TransformerStatePanelError("W13 requires ready Phase-A and Phase-B source locks")
    if _canonical_market(phase_a_manifest.get("market")) != market or _canonical_market(
        phase_b_manifest.get("market")
    ) != market:
        raise TransformerStatePanelError("Phase-A/B market differs from the Transformer config")
    artifacts = phase_b_manifest.get("artifacts") or {}
    expected_panel_hash = str((artifacts.get("expert_day_panel") or {}).get("sha256") or "")
    expected_split_hash = str((artifacts.get("walk_forward_splits") or {}).get("sha256") or "")
    if expected_panel_hash != sources["phase_b_panel_sha256"] or expected_split_hash != sources[
        "phase_b_splits_sha256"
    ]:
        raise TransformerStatePanelError("Phase-B manifest artifact hashes differ from the v2 source lock")
    try:
        panel = pd.read_parquet(panel_path)
        splits = pd.read_csv(splits_path)
    except (OSError, ValueError, ImportError) as exc:
        raise TransformerStatePanelError("Unable to read the frozen Phase-B panel") from exc
    if panel.empty or splits.empty:
        raise TransformerStatePanelError("Frozen Phase-B panel/splits are empty")
    required = {
        "date",
        "symbol",
        "market",
        "expert_id",
        "expert_status",
        "strategy_return",
        "target_position",
        "turnover",
        "source_artifact_path",
    }
    missing = required - set(panel.columns)
    if missing:
        raise TransformerStatePanelError(f"Phase-B panel is missing required columns: {sorted(missing)}")
    if {_canonical_market(value) for value in panel["market"].dropna().unique()} != {market}:
        raise TransformerStatePanelError("Phase-B panel contains cross-market rows")
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    panel["symbol"] = panel["symbol"].map(lambda value: _normalize_symbol(value, market))
    return phase_dir, panel, splits, phase_a_manifest, phase_b_manifest


def _full_run_paths(config: dict[str, Any], repo_root: Path) -> tuple[Path, Path, Path]:
    sources = config["sources"]
    full_dir = _resolve_repo_path(repo_root, sources["full_run_output_dir"], field_name="full_run_output_dir")
    full_config_path = _resolve_repo_path(
        repo_root, sources["full_run_config_path"], field_name="full_run_config_path"
    )
    _verify_hash(full_config_path, sources["full_run_config_sha256"], label="full-run tracked config")
    _verify_hash(
        full_dir / "config_snapshot.json",
        sources["full_run_config_snapshot_sha256"],
        label="full-run config snapshot",
    )
    manifest_path = full_dir / "data_manifest.json"
    summary_path = full_dir / "model_summary.csv"
    _verify_hash(
        manifest_path,
        sources["full_run_source_manifest_sha256"],
        label="full-run source manifest",
    )
    _verify_hash(
        summary_path,
        sources["full_run_model_summary_sha256"],
        label="full-run model summary",
    )
    return full_dir, manifest_path, summary_path


def _resolve_full_run_artifact_dir(full_dir: Path, symbol: str, model_id: str) -> Path:
    direct = full_dir / "artifacts" / symbol / "main" / model_id
    if direct.is_dir():
        return direct
    market = _canonical_market(_json_object(full_dir / "data_manifest.json").get("market"))
    normalized = _normalize_symbol(symbol, market)
    for candidate in (full_dir / "artifacts").glob(f"*/main/{model_id}"):
        if _normalize_symbol(candidate.parents[1].name, market) == normalized:
            return candidate
    raise TransformerStatePanelError(f"Missing rank-1 artifact directory for {symbol}/{model_id}")


def _position_proof(artifact_dir: Path) -> dict[str, Any]:
    returns_path = artifact_dir / "returns.csv"
    metadata_path = artifact_dir / "metadata.json"
    if not returns_path.is_file() or not metadata_path.is_file():
        raise TransformerStatePanelError(f"Rank-1 artifact lacks returns/metadata: {artifact_dir}")
    returns = pd.read_csv(returns_path)
    if not {"date", "strategy_return"}.issubset(returns.columns) or returns.empty:
        raise TransformerStatePanelError(f"Rank-1 returns artifact is invalid: {returns_path}")
    returns["date"] = pd.to_datetime(returns["date"], errors="coerce").dt.normalize()
    if returns["date"].isna().any() or returns["date"].duplicated().any():
        raise TransformerStatePanelError(f"Rank-1 returns contain invalid dates: {returns_path}")
    daily_path = artifact_dir / "daily.csv"
    if daily_path.is_file():
        daily = pd.read_csv(daily_path)
        position_column = next(
            (column for column in ("target_position", "position") if column in daily.columns),
            None,
        )
        if position_column is None:
            raise TransformerStatePanelError(f"daily.csv has no target position: {daily_path}")
        if "date" not in daily.columns:
            raise TransformerStatePanelError(f"daily.csv has no date column: {daily_path}")
        daily_dates = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
        positions = pd.to_numeric(daily[position_column], errors="coerce")
        if (
            len(daily) != len(returns)
            or daily_dates.isna().any()
            or daily_dates.duplicated().any()
            or not np.array_equal(daily_dates.to_numpy(), returns["date"].to_numpy())
            or positions.isna().any()
        ):
            raise TransformerStatePanelError(f"daily target position is incomplete: {daily_path}")
        return {
            "method": "source_target_position" if position_column == "target_position" else "source_position",
            "path": daily_path.as_posix(),
            "sha256": _sha256_file(daily_path),
            "row_count": int(len(daily)),
        }

    metadata = _json_object(metadata_path)
    equity_path = artifact_dir / "equity.csv"
    equity = pd.read_csv(equity_path) if equity_path.is_file() else pd.DataFrame()
    strategy_return = pd.to_numeric(returns["strategy_return"], errors="coerce")
    turnover = _finite((metadata.get("eval") or {}).get("turnover"))
    equity_values = (
        pd.to_numeric(equity.get("strategy_equity"), errors="coerce")
        if "strategy_equity" in equity.columns
        else pd.Series(dtype="float64")
    )
    provable_zero = (
        metadata.get("status") == "success"
        and turnover == 0.0
        and strategy_return.notna().all()
        and bool(strategy_return.eq(0.0).all())
        and len(equity_values) == len(returns)
        and equity_values.notna().all()
        and equity_values.nunique(dropna=True) == 1
    )
    if not provable_zero:
        trades_note = (
            " trades.csv exists but interval trades cannot reconstruct exact daily target_position/turnover."
            if (artifact_dir / "trades.csv").is_file()
            else ""
        )
        raise TransformerStatePanelError(
            f"Rank-1 daily target position is unavailable and cannot be proven zero: {artifact_dir}.{trades_note}"
        )
    return {
        "method": "provable_zero_position",
        "path": metadata_path.as_posix(),
        "sha256": _json_sha256(
            {
                "returns_sha256": _sha256_file(returns_path),
                "metadata_sha256": _sha256_file(metadata_path),
                "equity_sha256": _sha256_file(equity_path),
            }
        ),
        "row_count": int(len(returns)),
        "proof": "success + zero turnover + all-zero net returns + constant equity",
    }


def _verify_rank_one_guard(
    config: dict[str, Any], *, full_dir: Path, summary_path: Path
) -> dict[str, Any]:
    market = _canonical_market(config["market"])
    guard = config["full_run_best_guard"]
    try:
        summary = pd.read_csv(summary_path)
        runs = pd.read_csv(full_dir / "runs.csv")
    except (OSError, pd.errors.ParserError) as exc:
        raise TransformerStatePanelError("Unable to read full-run rank/source artifacts") from exc
    required_summary = {"rank", "model_id", "total_score", "valid_count"}
    if not required_summary.issubset(summary.columns):
        raise TransformerStatePanelError("model_summary.csv lacks rank-1 evidence columns")
    rank_one = summary.loc[pd.to_numeric(summary["rank"], errors="coerce").eq(1)]
    if len(rank_one) != 1:
        raise TransformerStatePanelError("full-run model summary must contain exactly one rank-1 row")
    row = rank_one.iloc[0]
    if str(row["model_id"]) != str(guard["source_model_id"]):
        raise TransformerStatePanelError("frozen full-run-best source_model_id differs from rank 1")
    if _finite(row["total_score"]) != _finite(guard["total_score"]) or int(row["valid_count"]) != int(
        guard["valid_count"]
    ):
        raise TransformerStatePanelError("frozen full-run-best score/coverage evidence drifted")

    required_runs = {"symbol", "model_id", "window_kind", "status"}
    if not required_runs.issubset(runs.columns):
        raise TransformerStatePanelError("full-run runs.csv lacks main-window lineage fields")
    selected = runs.loc[
        runs["model_id"].astype(str).eq(str(guard["source_model_id"]))
        & runs["window_kind"].astype(str).eq("main")
    ].copy()
    if len(selected) != int(guard["valid_count"]) or not selected["status"].astype(str).isin(
        {"success", "ok", "ready", "completed"}
    ).all():
        raise TransformerStatePanelError("rank-1 main-window runs do not match frozen valid_count/status")
    proofs: list[dict[str, Any]] = []
    for record in selected.sort_values("symbol").to_dict("records"):
        symbol = _normalize_symbol(record["symbol"], market)
        artifact_dir = _resolve_full_run_artifact_dir(full_dir, symbol, str(guard["source_model_id"]))
        proof = _position_proof(artifact_dir)
        proofs.append({"symbol": symbol, **proof})
    allowed = set(guard.get("allowed_position_sources") or [])
    methods = Counter(str(proof["method"]) for proof in proofs)
    if not methods or not set(methods).issubset(allowed):
        raise TransformerStatePanelError("rank-1 target-position source violates the frozen policy")
    return {
        "selection_rule": guard["selection_rule"],
        "source_model_id": str(guard["source_model_id"]),
        "expert_id": str(guard["expert_id"]),
        "rank": 1,
        "total_score": float(row["total_score"]),
        "valid_count": int(row["valid_count"]),
        "position_source_counts": dict(sorted(methods.items())),
        "position_proofs": proofs,
    }


def _snapshot_inventory(
    config: dict[str, Any], *, full_dir: Path, full_manifest: dict[str, Any]
) -> dict[str, Any]:
    market = _canonical_market(config["market"])
    snapshot_dir = full_dir / "data_snapshot"
    if not snapshot_dir.is_dir():
        raise TransformerStatePanelError("full-run data_snapshot directory is missing")
    recorded = str((full_manifest.get("data") or {}).get("snapshot_sha256") or "")
    if recorded != config["sources"]["data_snapshot_sha256"]:
        raise TransformerStatePanelError("full-run snapshot hash differs from the v2 config")
    manifest_entries = (full_manifest.get("universe") or {}).get("files")
    if not isinstance(manifest_entries, list) or not manifest_entries:
        raise TransformerStatePanelError("full-run manifest has no snapshot file inventory")
    expected_names: set[str] = set()
    portable_entries: list[dict[str, Any]] = []
    files: list[Path] = []
    for index, entry in enumerate(manifest_entries):
        if not isinstance(entry, dict) or not str(entry.get("symbol") or "").strip():
            raise TransformerStatePanelError(f"invalid snapshot manifest entry at index {index}")
        symbol = _normalize_symbol(entry["symbol"], market)
        filename = f"{symbol}_daily.csv"
        if filename in expected_names:
            raise TransformerStatePanelError(f"duplicate snapshot manifest symbol: {symbol}")
        expected_names.add(filename)
        path = snapshot_dir / filename
        if not path.is_file():
            raise TransformerStatePanelError(f"snapshot manifest file is missing: {filename}")
        actual_sha256 = _sha256_file(path)
        actual_size = int(path.stat().st_size)
        if actual_sha256 != str(entry.get("sha256") or "") or actual_size != int(
            entry.get("size_bytes", -1)
        ):
            raise TransformerStatePanelError(f"snapshot manifest file drifted: {filename}")
        portable_entries.append(
            {"symbol": symbol, "sha256": actual_sha256, "size_bytes": actual_size}
        )
        files.append(path)
    actual_names = {path.name for path in snapshot_dir.glob("*.csv") if path.is_file()}
    if actual_names != expected_names:
        raise TransformerStatePanelError("snapshot directory differs from the manifest inventory")
    actual_aggregate = hashlib.sha256(
        json.dumps(portable_entries, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if actual_aggregate != recorded:
        raise TransformerStatePanelError("snapshot file aggregate differs from the source manifest")
    minimum = int(config["benchmark"]["minimum_constituents"])
    if len(files) < minimum:
        raise TransformerStatePanelError("market-native snapshot has too few constituents")
    symbols: list[str] = []
    for path in files:
        try:
            header = pd.read_csv(path, nrows=1)
        except (OSError, pd.errors.ParserError) as exc:
            raise TransformerStatePanelError(f"Unable to inspect snapshot file: {path}") from exc
        if not {"date", "open", "high", "low", "close", "volume"}.issubset(header.columns):
            raise TransformerStatePanelError(f"Snapshot lacks daily OHLCV columns: {path}")
        if "market" in header.columns and not header.empty and _canonical_market(header.iloc[0]["market"]) != market:
            raise TransformerStatePanelError(f"Snapshot contains the wrong market: {path}")
        symbols.append(_normalize_symbol(path.stem.removesuffix("_daily"), market))
    if len(symbols) != len(set(symbols)):
        raise TransformerStatePanelError("snapshot contains duplicate normalized symbols")
    return {
        "directory": snapshot_dir.as_posix(),
        "aggregate_sha256": actual_aggregate,
        "file_count": len(files),
        "symbols": symbols,
        "benchmark_method": config["benchmark"]["method"],
    }


def build_transformer_source_manifest(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Verify and persist the W13 market-specific source lock."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    market = _canonical_market(config["market"])
    sources = config["sources"]
    target = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / "model-test" / "outputs" / str(config["output_subdir"])).resolve()
    )
    target.mkdir(parents=True, exist_ok=True)

    phase_a_config = _resolve_repo_path(root, sources["phase_a_config_path"], field_name="phase_a_config_path")
    current_phase_a = build_phase_a_manifest(phase_a_config, repo_root=root)
    if current_phase_a.get("status") != "ready":
        issues = [issue for source in current_phase_a.get("sources", []) for issue in source.get("issues", [])]
        raise TransformerStatePanelError("Phase-A source revalidation failed: " + "; ".join(issues))
    phase_dir, panel, phase_b_splits, phase_a_manifest, phase_b_manifest = _load_verified_phase_b(
        config, repo_root=root
    )
    for field in ("phase_a_config_sha256", "source_fingerprint_sha256"):
        if current_phase_a.get(field) != phase_a_manifest.get(field):
            raise TransformerStatePanelError(
                f"current Phase-A {field} differs from the frozen Phase-A source manifest"
            )
    expected_experts = set(str(value) for value in config["experts"])
    actual_experts = set(str(value) for value in panel["expert_id"].dropna().unique())
    if actual_experts != expected_experts or "cash" not in actual_experts:
        raise TransformerStatePanelError("Phase-B expert pool differs from the v2 config or lost Cash")
    if not panel.loc[panel["expert_id"].eq("cash"), "expert_status"].eq("available").all():
        raise TransformerStatePanelError("Cash must be available for every source row")
    adaptive = panel.loc[panel["expert_id"].eq("adaptive_router")]
    if adaptive.empty or not adaptive["expert_status"].eq("available").all():
        raise TransformerStatePanelError("market-native adaptive control is unavailable")
    market_columns = {"market_return_1", "market_return_5", "market_return_20", "market_volatility_20"}
    if not market_columns.issubset(panel.columns):
        raise TransformerStatePanelError("Phase-B panel lacks point-in-time market context columns")
    risk_rows = panel.loc[~panel["expert_id"].astype(str).eq("cash")].copy()
    exact_position_sources = {"source_target_position", "source_position"}
    observed_position_sources = set(str(value) for value in risk_rows["position_source"].dropna().unique())
    if (
        risk_rows["target_position"].isna().any()
        or risk_rows["turnover"].isna().any()
        or not observed_position_sources
        or not observed_position_sources.issubset(exact_position_sources)
    ):
        raise TransformerStatePanelError(
            "Phase-B daily target_position/turnover is incomplete or reconstructed from interval trades; "
            "W14 labels require exact source daily execution artifacts"
        )

    full_dir, full_manifest_path, summary_path = _full_run_paths(config, root)
    full_manifest = _json_object(full_manifest_path)
    if _canonical_market(full_manifest.get("market")) != market:
        raise TransformerStatePanelError("authoritative full-run market differs from the v2 config")
    if int(full_manifest.get("random_seed", -1)) != int(config["random_seed"]):
        raise TransformerStatePanelError("authoritative full-run seed differs from the v2 config")
    for manifest_name, source_value in (
        ("Phase-A", phase_a_manifest.get("execution") or {}),
        ("full-run", full_manifest.get("execution") or {}),
    ):
        for field in ("commission_bps", "slippage_bps"):
            if _finite(source_value.get(field)) != _finite(config["source_execution"][field]):
                raise TransformerStatePanelError(
                    f"{manifest_name} execution.{field} differs from the frozen v2 cost contract"
                )
    guard_evidence = _verify_rank_one_guard(config, full_dir=full_dir, summary_path=summary_path)
    snapshot = _snapshot_inventory(config, full_dir=full_dir, full_manifest=full_manifest)
    runtime_available = importlib.util.find_spec("torch") is not None

    manifest = {
        "schema_version": TRANSFORMER_STATE_SCHEMA_VERSION,
        "phase": "W13",
        "status": "ready",
        "created_at": _utc_now(),
        "market": market,
        "random_seed": int(config["random_seed"]),
        "training_scope": "market_specific",
        "cross_market_policy": "forbidden",
        "config_path": config_file.as_posix(),
        "config_sha256": _sha256_file(config_file),
        "config_snapshot_sha256": _json_sha256(config),
        "code_version": _git_code_version(root),
        "code_lock": transformer_code_lock(root),
        "returns": config["returns"],
        "source_execution": config["source_execution"],
        "source_lock": {
            "phase_a_output_dir": phase_dir.as_posix(),
            "phase_a_manifest_sha256": sources["phase_a_manifest_sha256"],
            "phase_a_source_fingerprint_sha256": phase_a_manifest.get("source_fingerprint_sha256"),
            "phase_b_manifest_sha256": sources["phase_b_manifest_sha256"],
            "phase_b_panel_sha256": sources["phase_b_panel_sha256"],
            "phase_b_splits_sha256": sources["phase_b_splits_sha256"],
            "phase_b_split_count": int(len(phase_b_splits)),
            "full_run_output_dir": full_dir.as_posix(),
            "full_run_config_sha256": sources["full_run_config_sha256"],
            "full_run_config_snapshot_sha256": sources["full_run_config_snapshot_sha256"],
            "full_run_source_manifest_sha256": sources["full_run_source_manifest_sha256"],
            "full_run_model_summary_sha256": sources["full_run_model_summary_sha256"],
            "data_snapshot_sha256": sources["data_snapshot_sha256"],
        },
        "expert_pool": list(config["experts"]),
        "cash_available": True,
        "adaptive_control_available": True,
        "full_run_best_guard": guard_evidence,
        "market_snapshot": snapshot,
        "runtime": {
            "requested": config["transformer"]["runtime"],
            "device": config["transformer"]["device"],
            "available": runtime_available,
            "status": "ready" if runtime_available else "missing_dependency",
            "reason": None if runtime_available else "PyTorch is not installed; W15 fit must fail closed",
        },
    }
    snapshot_path = target / "config_snapshot.json"
    source_manifest_path = target / SOURCE_MANIFEST_NAME
    snapshot_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["config_snapshot_file_sha256"] = _sha256_file(snapshot_path)
    source_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return manifest, source_manifest_path


def write_blocked_transformer_manifests(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    reason: str,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Invalidate stale downstream evidence after a fail-closed source audit."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / "model-test" / "outputs" / str(config["output_subdir"])).resolve()
    )
    target.mkdir(parents=True, exist_ok=True)
    runtime_available = importlib.util.find_spec("torch") is not None
    common = {
        "schema_version": TRANSFORMER_STATE_SCHEMA_VERSION,
        "status": "blocked",
        "created_at": _utc_now(),
        "market": _canonical_market(config["market"]),
        "reason": str(reason),
        "config_sha256": _sha256_file(config_file),
        "code_version": _git_code_version(root),
        "code_lock": transformer_code_lock(root),
        "stale_artifacts_retained_but_invalidated": True,
    }
    source_path = target / SOURCE_MANIFEST_NAME
    panel_path = target / PANEL_MANIFEST_NAME
    model_path = target / "transformer_state_model_manifest.json"
    source = {
        **common,
        "phase": "W13",
        "runtime": {
            "requested": config["transformer"]["runtime"],
            "available": runtime_available,
            "status": "ready" if runtime_available else "missing_dependency",
        },
    }
    source_path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    panel = {
        **common,
        "phase": "W14",
        "source_manifest_sha256": _sha256_file(source_path),
        "artifacts": {},
    }
    panel_path.write_text(json.dumps(panel, ensure_ascii=False, indent=2), encoding="utf-8")
    model = {
        **common,
        "phase": "W15",
        "upstream_source_status": "blocked",
        "next_stage_allowed": False,
        "fold_count": 0,
        "folds": [],
    }
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"source_manifest": source_path, "panel_manifest": panel_path, "model_manifest": model_path}


def validate_feature_columns(feature_columns: Sequence[str]) -> None:
    invalid = [
        str(column)
        for column in feature_columns
        if any(token in str(column).lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    if invalid:
        raise TransformerStatePanelError(f"future/outcome columns cannot be model features: {invalid}")


def eligible_historical_memory(query_date: Any, memory_dates: Iterable[Any]) -> np.ndarray:
    """Return the only W14-permitted future retrieval mask: memory date < query."""

    query = pd.Timestamp(query_date)
    dates = pd.to_datetime(pd.Index(list(memory_dates)), errors="coerce")
    if pd.isna(query) or dates.isna().any():
        raise TransformerStatePanelError("memory/query dates must be valid")
    return np.asarray(dates < query, dtype=bool)


def build_transformer_walk_forward_splits(
    phase_b_splits: pd.DataFrame,
    dates: Iterable[Any],
    *,
    protection_days: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reuse W11 test windows without ever reusing them for v2 fit/selection.

    W11 test intervals are preserved as the four formal v2 evaluation windows,
    but their union is a global forbidden set for v2 train and validation.  If
    a later W11 validation interval overlaps an earlier W11 test, the latest
    earlier clean train/validation pair is frozen instead.  Insufficient clean
    history fails closed.
    """

    required = {
        "split_id",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
    }
    missing = required - set(phase_b_splits.columns)
    if missing:
        raise TransformerStatePanelError(f"Phase-B splits lack fields: {sorted(missing)}")
    trading_dates = pd.DatetimeIndex(pd.to_datetime(pd.Index(list(dates)), errors="coerce"))
    trading_dates = trading_dates[~trading_dates.isna()].normalize().drop_duplicates().sort_values()
    if trading_dates.empty:
        raise TransformerStatePanelError("cannot isolate W11 tests without trading dates")

    source_rows = phase_b_splits.sort_values("test_start").to_dict("records")
    legacy_test_dates: set[pd.Timestamp] = set()
    for row in source_rows:
        start, end = pd.Timestamp(row["test_start"]), pd.Timestamp(row["test_end"])
        legacy_test_dates.update(pd.Timestamp(value) for value in trading_dates[(trading_dates >= start) & (trading_dates <= end)])
    if not legacy_test_dates:
        raise TransformerStatePanelError("Phase-B split file contains no test trading dates")

    def interval_dates(row: dict[str, Any], role: str) -> set[pd.Timestamp]:
        start = pd.Timestamp(row[f"{role}_start"])
        end = pd.Timestamp(row[f"{role}_end"])
        return set(pd.Timestamp(value) for value in trading_dates[(trading_dates >= start) & (trading_dates <= end)])

    def trading_gap_days(left_end: Any, right_start: Any) -> int:
        left = pd.Timestamp(left_end)
        right = pd.Timestamp(right_start)
        return int(((trading_dates > left) & (trading_dates < right)).sum())

    clean_pairs = [
        row
        for row in source_rows
        if interval_dates(row, "train").isdisjoint(legacy_test_dates)
        and interval_dates(row, "validation").isdisjoint(legacy_test_dates)
        and trading_gap_days(row["train_end"], row["validation_start"])
        >= protection_days
    ]
    rows: list[dict[str, Any]] = []
    for target in source_rows:
        test_start = pd.Timestamp(target["test_start"])
        candidates = [
            row
            for row in clean_pairs
            if pd.Timestamp(row["validation_end"]) < test_start
            and trading_gap_days(row["validation_end"], test_start) >= protection_days
        ]
        if not candidates:
            raise TransformerStatePanelError(
                f"No legacy-test-free train/validation pair exists for {target['split_id']}"
            )
        source = max(candidates, key=lambda row: pd.Timestamp(row["validation_end"]))
        if not interval_dates(source, "train").isdisjoint(legacy_test_dates) or not interval_dates(
            source, "validation"
        ).isdisjoint(legacy_test_dates):
            raise TransformerStatePanelError("legacy W11 test dates entered v2 fit/selection roles")
        rows.append(
            {
                "split_id": str(target["split_id"]),
                "train_start": str(source["train_start"]),
                "train_end": str(source["train_end"]),
                "validation_start": str(source["validation_start"]),
                "validation_end": str(source["validation_end"]),
                "test_start": str(target["test_start"]),
                "test_end": str(target["test_end"]),
                "purge_days": int(protection_days),
                "embargo_days": int(protection_days),
                "source_train_validation_split_id": str(source["split_id"]),
                "legacy_w11_test_isolated": True,
                "status": "ready",
                "reason": None,
            }
        )
    splits = pd.DataFrame(rows)
    if len(splits) != len(source_rows):
        raise TransformerStatePanelError("not all four W11 test windows received isolated v2 roles")
    isolation = {
        "policy": "W11 test union forbidden in every v2 train/validation membership",
        "legacy_test_date_count": len(legacy_test_dates),
        "legacy_test_dates_sha256": _json_sha256(
            [value.date().isoformat() for value in sorted(legacy_test_dates)]
        ),
        "source_train_validation_split_ids": {
            str(row["split_id"]): str(row["source_train_validation_split_id"])
            for row in rows
        },
    }
    return splits, isolation


def _compute_five_day_labels(
    panel: pd.DataFrame, *, config: dict[str, Any]
) -> pd.DataFrame:
    panel_config = config["panel"]
    experts = [str(value) for value in config["experts"]]
    order = {expert_id: index for index, expert_id in enumerate(sorted(experts))}
    frames: list[pd.DataFrame] = []
    for (_, _), group in panel.groupby(["symbol", "expert_id"], sort=False):
        labeled = compute_future_utility(
            group[[
                "date",
                "strategy_return",
                "turnover",
            ]],
            horizon_days=LABEL_HORIZON_DAYS,
            lambda_downside=float(panel_config["lambda_downside"]),
            lambda_turnover=float(panel_config["lambda_turnover"]),
        )
        base = group.drop(
            columns=[
                column
                for column in (
                    "future_net_return",
                    "future_downside",
                    "future_turnover_penalty",
                    "future_utility",
                    "label_horizon_days",
                    "label_end_date",
                    "split_memberships_json",
                )
                if column in group.columns
            ]
        ).sort_values("date")
        for column in (
            "future_net_return",
            "future_downside",
            "future_turnover_penalty",
            "future_utility",
            "label_horizon_days",
        ):
            base[column] = labeled[column].to_numpy()
        base["label_end_date"] = base["date"].shift(-LABEL_HORIZON_DAYS)
        frames.append(base)
    labels = pd.concat(frames, ignore_index=True)
    margin_floor = float(panel_config["label_margin"])
    valid = labels.loc[
        labels["expert_status"].eq("available")
        & pd.to_numeric(labels["future_utility"], errors="coerce").notna()
    ].copy()
    valid["_utility"] = pd.to_numeric(valid["future_utility"], errors="coerce")
    valid["_order"] = valid["expert_id"].astype(str).map(order).fillna(len(order))
    valid = valid.sort_values(
        ["date", "symbol", "_utility", "_order"],
        ascending=[True, True, False, True],
    )
    valid["_rank"] = valid.groupby(["date", "symbol"], sort=False).cumcount()
    best = valid.loc[valid["_rank"].eq(0), ["date", "symbol", "expert_id", "_utility"]].rename(
        columns={"expert_id": "best_expert_5d", "_utility": "_best_utility"}
    )
    second = valid.loc[valid["_rank"].eq(1), ["date", "symbol", "expert_id", "_utility"]].rename(
        columns={"expert_id": "second_expert_5d", "_utility": "_second_utility"}
    )
    winners = best.merge(second, on=["date", "symbol"], how="left")
    winners["label_margin"] = winners["_best_utility"] - winners["_second_utility"]
    winners.loc[winners["_second_utility"].isna(), "label_margin"] = math.inf
    winners["utility_margin"] = winners["label_margin"]
    winners["label_status"] = np.where(
        winners["label_margin"].lt(margin_floor), "ambiguous", "ready"
    )
    winners = winners.drop(columns=["_best_utility", "_second_utility"])
    labels = labels.merge(winners, on=["date", "symbol"], how="left")
    labels["label_status"] = labels["label_status"].fillna("unavailable")
    labels["is_best_expert_5d"] = labels["expert_id"].astype(str).eq(
        labels["best_expert_5d"].astype(str)
    ) & labels["best_expert_5d"].notna()
    labels["label_horizon_days"] = LABEL_HORIZON_DAYS
    return labels.sort_values(["date", "symbol", "expert_id"]).reset_index(drop=True)


def _read_snapshot_features(
    config: dict[str, Any], *, repo_root: Path, required_dates: pd.DatetimeIndex
) -> tuple[pd.DataFrame, dict[str, Any]]:
    market = _canonical_market(config["market"])
    full_dir = _resolve_repo_path(
        repo_root,
        config["sources"]["full_run_output_dir"],
        field_name="full_run_output_dir",
    )
    snapshot_dir = full_dir / "data_snapshot"
    earliest = required_dates.min() - pd.Timedelta(days=180)
    latest = required_dates.max()
    rows: list[pd.DataFrame] = []
    for path in sorted(snapshot_dir.glob("*.csv")):
        frame = pd.read_csv(path)
        if not {"date", "high", "low", "close", "volume"}.issubset(frame.columns):
            raise TransformerStatePanelError(f"Snapshot feature source lacks OHLCV: {path}")
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        frame = frame.loc[frame["date"].between(earliest, latest)].copy()
        if frame.empty:
            continue
        symbol_value = frame["symbol"].iloc[0] if "symbol" in frame.columns else path.stem.removesuffix("_daily")
        frame["symbol"] = _normalize_symbol(symbol_value, market)
        for column in ("high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.sort_values("date").drop_duplicates("date", keep="last")
        close = frame["close"]
        returns = close.pct_change(fill_method=None)
        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous_close).abs(),
                (frame["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        rolling_high = close.rolling(60, min_periods=20).max()
        volume_mean = frame["volume"].rolling(20, min_periods=5).mean()
        frame["asset_return_1"] = returns
        frame["asset_trend_5"] = close.pct_change(5, fill_method=None)
        frame["asset_trend_20"] = close.pct_change(20, fill_method=None)
        frame["asset_volatility_5"] = returns.rolling(5, min_periods=3).std(ddof=0)
        frame["asset_volatility_20"] = returns.rolling(20, min_periods=10).std(ddof=0)
        frame["asset_atr_pct_14"] = true_range.rolling(14, min_periods=7).mean() / close.replace(0.0, np.nan)
        frame["asset_liquidity_20"] = np.log1p(
            (close * frame["volume"]).rolling(20, min_periods=5).mean()
        )
        frame["asset_drawdown_60"] = close / rolling_high - 1.0
        frame["asset_volume_ratio_20"] = frame["volume"] / volume_mean.replace(0.0, np.nan)
        rows.append(frame[["date", "symbol", *STATE_FEATURE_COLUMNS[:9]]])
    if not rows:
        raise TransformerStatePanelError("No market-native snapshot rows are available for W14")
    assets = pd.concat(rows, ignore_index=True)
    assets = assets.loc[assets["date"].isin(required_dates)].copy()
    pivot = assets.pivot(index="date", columns="symbol", values="asset_return_1").sort_index()
    market_return = pivot.mean(axis=1, skipna=True)
    constituent_count = pivot.notna().sum(axis=1)
    market = pd.DataFrame(
        {
            "date": market_return.index,
            "market_return_1": market_return.to_numpy(),
            "market_constituent_count": constituent_count.to_numpy(dtype=float),
        }
    )
    market["market_return_5"] = (1.0 + market["market_return_1"]).rolling(5, min_periods=3).apply(
        np.prod, raw=True
    ) - 1.0
    market["market_return_20"] = (1.0 + market["market_return_1"]).rolling(20, min_periods=10).apply(
        np.prod, raw=True
    ) - 1.0
    market["market_volatility_20"] = market["market_return_1"].rolling(20, min_periods=10).std(ddof=0)
    market["market_trend_20"] = market["market_return_20"]
    market_equity = (1.0 + market["market_return_1"].fillna(0.0)).cumprod()
    market["market_drawdown_60"] = market_equity / market_equity.rolling(60, min_periods=20).max() - 1.0
    minimum = int(config["benchmark"]["minimum_constituents"])
    if market["market_constituent_count"].dropna().lt(minimum).any():
        raise TransformerStatePanelError("market-native benchmark falls below minimum constituent coverage")

    context = assets.merge(market, on="date", how="left")
    parts: list[pd.DataFrame] = []
    for _, group in context.groupby("symbol", sort=False):
        group = group.sort_values("date").copy()
        asset_return = pd.to_numeric(group["asset_return_1"], errors="coerce")
        market_daily = pd.to_numeric(group["market_return_1"], errors="coerce")
        covariance = asset_return.rolling(20, min_periods=10).cov(market_daily)
        variance = market_daily.rolling(20, min_periods=10).var(ddof=0)
        group["asset_relative_strength_20"] = group["asset_trend_20"] - group["market_return_20"]
        group["asset_market_beta_20"] = covariance / variance.replace(0.0, np.nan)
        group["asset_market_correlation_20"] = asset_return.rolling(20, min_periods=10).corr(market_daily)
        parts.append(group)
    context = pd.concat(parts, ignore_index=True)

    volatility_reference = market["market_volatility_20"].rolling(60, min_periods=20).median().shift(1)
    market_state = market[["date", "market_trend_20", "market_volatility_20"]].copy()
    market_state["state_market_trend_up_20"] = np.where(
        market_state["market_trend_20"].notna(),
        market_state["market_trend_20"].ge(0.0).astype(float),
        np.nan,
    )
    valid_volatility = market_state["market_volatility_20"].notna() & volatility_reference.notna()
    market_state["state_market_high_volatility_20"] = np.nan
    market_state.loc[valid_volatility, "state_market_high_volatility_20"] = market_state.loc[
        valid_volatility, "market_volatility_20"
    ].gt(volatility_reference.loc[valid_volatility]).astype(float)
    market_state["state_market_regime_id_20"] = np.where(
        market_state["state_market_trend_up_20"].notna()
        & market_state["state_market_high_volatility_20"].notna(),
        market_state["state_market_trend_up_20"] * 2.0
        + market_state["state_market_high_volatility_20"],
        np.nan,
    )
    regime = market_state["state_market_regime_id_20"]
    market_state["state_switch_1"] = regime.ne(regime.shift(1)).where(regime.notna() & regime.shift(1).notna()).astype(float)
    duration: list[float] = []
    previous: float | None = None
    run_length = 0
    for value in regime:
        numeric = _finite(value)
        if numeric is None:
            duration.append(np.nan)
            previous = None
            run_length = 0
        else:
            run_length = run_length + 1 if previous == numeric else 1
            duration.append(float(run_length))
            previous = numeric
    market_state["state_duration_days"] = duration
    state_columns = [
        "date",
        "state_market_trend_up_20",
        "state_market_high_volatility_20",
        "state_market_regime_id_20",
        "state_duration_days",
        "state_switch_1",
    ]
    context = context.merge(market_state[state_columns], on="date", how="left")
    return context, {
        "benchmark_method": config["benchmark"]["method"],
        "constituent_count_min": int(market["market_constituent_count"].min()),
        "constituent_count_max": int(market["market_constituent_count"].max()),
        "date_start": market["date"].min().date().isoformat(),
        "date_end": market["date"].max().date().isoformat(),
    }


def _execution_context(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    positions = pd.to_numeric(work["target_position"], errors="coerce")
    work["_active"] = positions.abs().gt(1e-12).where(positions.notna())
    aggregations: dict[str, tuple[str, str]] = {
        "expert_active_fraction": ("_active", "mean"),
    }
    optional = {
        "expert_recent_net_return_5_mean": "expert_recent_net_return_5",
        "expert_turnover_5_mean": "expert_turnover_5",
        "expert_peer_correlation_20_mean": "expert_peer_correlation_20",
    }
    for output, source in optional.items():
        if source in work.columns:
            work[source] = pd.to_numeric(work[source], errors="coerce")
            aggregations[output] = (source, "mean")
    result = work.groupby(["date", "symbol"], as_index=False).agg(**aggregations)
    for output in optional:
        if output not in result.columns:
            result[output] = np.nan
    return result


def _feature_schema(config: dict[str, Any]) -> dict[str, Any]:
    validate_feature_columns(STATE_FEATURE_COLUMNS)
    price_features = set(STATE_FEATURE_COLUMNS[:9])
    market_features = {
        "market_return_1",
        "market_return_5",
        "market_return_20",
        "market_volatility_20",
        "market_trend_20",
        "market_drawdown_60",
        "market_constituent_count",
    }
    regime_features = {
        "state_market_trend_up_20",
        "state_market_high_volatility_20",
        "state_market_regime_id_20",
        "state_duration_days",
        "state_switch_1",
    }
    relative_features = {
        "asset_relative_strength_20",
        "asset_market_beta_20",
        "asset_market_correlation_20",
    }
    columns = []
    for column in STATE_FEATURE_COLUMNS:
        if column in price_features:
            source = "full_run_data_snapshot.same_or_trailing_daily_ohlcv"
        elif column in market_features or column in regime_features:
            source = "full_run_data_snapshot.market_equal_weight_same_or_trailing"
        elif column in relative_features:
            source = "asset_and_market_same_or_trailing_rolling_context"
        else:
            source = "phase_b_expert_panel.same_or_trailing_expert_context"
        lookback = 60 if "60" in column else 20 if "20" in column else 14 if "14" in column else 5 if "5" in column else 1
        columns.append(
            {
                "name": column,
                "dtype": "float64",
                "source": source,
                "lookback_trading_days": lookback,
                "shift": 0,
                "availability": "decision_day_close",
                "missing_strategy": "fold_train_median_plus_missingness_mask",
                "model_input": True,
            }
        )
    return {
        "schema_version": TRANSFORMER_STATE_SCHEMA_VERSION,
        "market": _canonical_market(config["market"]),
        "feature_columns": list(STATE_FEATURE_COLUMNS),
        "columns": columns,
        "forbidden_feature_tokens": list(FORBIDDEN_FEATURE_TOKENS),
        "sequence_length_candidates": list(config["panel"]["sequence_length_candidates"]),
        "primary_sequence_length": int(config["panel"]["primary_sequence_length"]),
    }


def _attach_sequence_memberships(
    sequences: pd.DataFrame, splits: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    memberships: list[str] = []
    counts: dict[str, Counter[str]] = {str(row["split_id"]): Counter() for row in splits.to_dict("records")}
    for row in sequences.itertuples(index=False):
        roles: list[dict[str, str]] = []
        decision_date = pd.Timestamp(row.date)
        sequence_start = pd.Timestamp(row.sequence_start_date)
        label_end = pd.Timestamp(row.label_end_date) if pd.notna(row.label_end_date) else None
        if label_end is not None and str(row.label_status) in {"ready", "ambiguous"}:
            for split in splits.to_dict("records"):
                split_id = str(split["split_id"])
                for role in ("train", "validation", "test"):
                    start = pd.Timestamp(split[f"{role}_start"])
                    end = pd.Timestamp(split[f"{role}_end"])
                    if start <= sequence_start <= decision_date <= end and label_end <= end:
                        roles.append({"split_id": split_id, "role": role})
                        counts[split_id][role] += 1
        memberships.append(json.dumps(roles, ensure_ascii=False, sort_keys=True))
    out = sequences.copy()
    out["split_memberships_json"] = memberships
    return out, {split_id: dict(counter) for split_id, counter in counts.items()}


def validate_sequence_panel(
    sequences: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    expected_length: int,
) -> None:
    validate_feature_columns(feature_columns)
    required = {
        "date",
        "symbol",
        "market",
        "sequence_start_date",
        "sequence_end_date",
        "sequence_dates",
        "sequence_values",
        "sequence_missing_mask",
        "label_end_date",
        "expert_utilities_json",
        "split_memberships_json",
    }
    missing = required - set(sequences.columns)
    if missing:
        raise TransformerStatePanelError(f"sequence panel is missing columns: {sorted(missing)}")
    if sequences.duplicated(["date", "symbol", "market"]).any():
        raise TransformerStatePanelError("sequence panel contains duplicate decision keys")
    for row in sequences.itertuples(index=False):
        dates = pd.to_datetime(pd.Index(list(row.sequence_dates)), errors="coerce")
        values = np.asarray(row.sequence_values, dtype=float)
        missing_mask = np.asarray(row.sequence_missing_mask, dtype=bool)
        if len(dates) != expected_length or dates.isna().any() or not dates.is_monotonic_increasing:
            raise TransformerStatePanelError("sequence dates are incomplete or non-chronological")
        if dates.duplicated().any() or pd.Timestamp(dates[-1]) != pd.Timestamp(row.date):
            raise TransformerStatePanelError("sequence must end exactly on its decision date")
        if pd.Timestamp(dates[0]) != pd.Timestamp(row.sequence_start_date):
            raise TransformerStatePanelError("sequence_start_date differs from the stored sequence")
        if pd.Timestamp(row.sequence_end_date) != pd.Timestamp(row.date):
            raise TransformerStatePanelError("sequence_end_date differs from the decision date")
        expected_shape = (expected_length, len(feature_columns))
        if values.shape != expected_shape or missing_mask.shape != expected_shape:
            raise TransformerStatePanelError("sequence values/missingness mask shape differs from schema")
        if not np.array_equal(~np.isfinite(values), missing_mask):
            raise TransformerStatePanelError("sequence missingness mask does not match numeric values")
        try:
            utilities = json.loads(str(row.expert_utilities_json))
        except json.JSONDecodeError as exc:
            raise TransformerStatePanelError("expert_utilities_json is invalid") from exc
        if not isinstance(utilities, dict) or not utilities:
            raise TransformerStatePanelError("expert_utilities_json must contain expert utilities")


def _build_sequences(
    state: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    config: dict[str, Any],
    feature_schema_sha256: str,
) -> pd.DataFrame:
    max_length = max(int(value) for value in config["panel"]["sequence_length_candidates"])
    decisions = labels[
        [
            "date",
            "symbol",
            "market",
            "best_expert_5d",
            "second_expert_5d",
            "label_margin",
            "utility_margin",
            "label_status",
            "label_end_date",
        ]
    ].drop_duplicates(["date", "symbol", "market"])
    utility_records: list[dict[str, Any]] = []
    for keys, group in labels.groupby(["date", "symbol", "market"], sort=False):
        utilities = {
            str(row.expert_id): _finite(row.future_utility)
            for row in group[["expert_id", "future_utility"]].itertuples(index=False)
        }
        utility_records.append(
            {
                "date": keys[0],
                "symbol": keys[1],
                "market": keys[2],
                "expert_utilities_json": json.dumps(
                    utilities, ensure_ascii=False, sort_keys=True, allow_nan=False
                ),
            }
        )
    decisions = decisions.merge(
        pd.DataFrame(utility_records), on=["date", "symbol", "market"], how="left", validate="one_to_one"
    )
    state = state.merge(decisions, on=["date", "symbol", "market"], how="left")
    rows: list[dict[str, Any]] = []
    for (symbol, market), group in state.groupby(["symbol", "market"], sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        values = group[list(STATE_FEATURE_COLUMNS)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        dates = pd.to_datetime(group["date"], errors="coerce")
        for index in range(max_length - 1, len(group)):
            start = index - max_length + 1
            sequence_values = values[start : index + 1]
            row = group.iloc[index]
            rows.append(
                {
                    "date": pd.Timestamp(row["date"]),
                    "symbol": str(symbol),
                    "market": str(market),
                    "sequence_start_date": pd.Timestamp(dates.iloc[start]),
                    "sequence_end_date": pd.Timestamp(dates.iloc[index]),
                    "sequence_length": max_length,
                    "sequence_dates": [pd.Timestamp(value).date().isoformat() for value in dates.iloc[start : index + 1]],
                    "sequence_values": sequence_values.tolist(),
                    "sequence_missing_mask": (~np.isfinite(sequence_values)).tolist(),
                    "feature_schema_sha256": feature_schema_sha256,
                    "best_expert_5d": row.get("best_expert_5d"),
                    "second_expert_5d": row.get("second_expert_5d"),
                    "label_margin": _finite(row.get("label_margin")),
                    "utility_margin": _finite(row.get("utility_margin")),
                    "expert_utilities_json": str(row.get("expert_utilities_json") or "{}"),
                    "label_status": str(row.get("label_status") or "unavailable"),
                    "label_end_date": row.get("label_end_date"),
                }
            )
    return pd.DataFrame(rows)


def materialize_transformer_state_panel(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Materialize the W13/W14 source lock, five-day labels and sequences."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_transformer_state_config(config_file)
    target = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / "model-test" / "outputs" / str(config["output_subdir"])).resolve()
    )
    target.mkdir(parents=True, exist_ok=True)
    source_manifest, source_manifest_path = build_transformer_source_manifest(
        config_file, repo_root=root, output_dir=target
    )
    _, panel, phase_b_splits, _, _ = _load_verified_phase_b(config, repo_root=root)
    market = _canonical_market(config["market"])
    panel = panel.loc[panel["expert_id"].astype(str).isin(config["experts"])].copy()
    labels = _compute_five_day_labels(panel, config=config)

    required_dates = pd.DatetimeIndex(sorted(labels["date"].dropna().unique()))
    state, benchmark_quality = _read_snapshot_features(config, repo_root=root, required_dates=required_dates)
    state["market"] = market
    execution = _execution_context(panel)
    state = state.merge(execution, on=["date", "symbol"], how="left")
    for column in STATE_FEATURE_COLUMNS:
        if column not in state.columns:
            state[column] = np.nan
    state = state[["date", "symbol", "market", *STATE_FEATURE_COLUMNS]].sort_values(
        ["symbol", "date"]
    )

    feature_schema = _feature_schema(config)
    feature_schema_path = target / FEATURE_SCHEMA_NAME
    feature_schema_path.write_text(
        json.dumps(feature_schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    feature_schema_sha256 = _sha256_file(feature_schema_path)
    sequences = _build_sequences(
        state,
        labels,
        config=config,
        feature_schema_sha256=feature_schema_sha256,
    )
    panel_config = config["panel"]
    splits, legacy_test_isolation = build_transformer_walk_forward_splits(
        phase_b_splits,
        sorted(state["date"].unique()),
        protection_days=int(panel_config["protection_days"]),
    )
    if len(splits) != int(panel_config["n_splits"]):
        raise TransformerStatePanelError("W14 cannot emit all four protected walk-forward splits")
    sequences, split_counts = _attach_sequence_memberships(sequences, splits)
    minimum_samples = int(panel_config["minimum_role_samples"])
    for split in splits["split_id"].astype(str):
        for role in ("train", "validation", "test"):
            if int(split_counts.get(split, {}).get(role, 0)) < minimum_samples:
                raise TransformerStatePanelError(
                    f"{split}/{role} has fewer than {minimum_samples} complete sequence-label samples"
                )
    validate_sequence_panel(
        sequences,
        feature_columns=STATE_FEATURE_COLUMNS,
        expected_length=max(int(value) for value in panel_config["sequence_length_candidates"]),
    )

    label_path = target / LABEL_PANEL_NAME
    sequence_path = target / SEQUENCE_PANEL_NAME
    splits_path = target / SPLITS_NAME
    quality_path = target / QUALITY_JSON_NAME
    quality_md_path = target / QUALITY_MD_NAME
    panel_manifest_path = target / PANEL_MANIFEST_NAME
    labels.to_parquet(label_path, index=False)
    sequences.to_parquet(sequence_path, index=False)
    splits.to_csv(splits_path, index=False)

    label_status_counts = {
        str(key): int(value)
        for key, value in labels.drop_duplicates(["date", "symbol"])["label_status"].value_counts().items()
    }
    best_counts = {
        str(key): int(value)
        for key, value in labels.drop_duplicates(["date", "symbol"])["best_expert_5d"].value_counts().items()
    }
    missing_rates = {
        column: float(pd.to_numeric(state[column], errors="coerce").isna().mean())
        for column in STATE_FEATURE_COLUMNS
    }
    quality = {
        "schema_version": TRANSFORMER_STATE_SCHEMA_VERSION,
        "phase": "W14",
        "status": "ready",
        "market": market,
        "label_horizon_days": LABEL_HORIZON_DAYS,
        "state_row_count": int(len(state)),
        "label_row_count": int(len(labels)),
        "sequence_row_count": int(len(sequences)),
        "sequence_length": int(sequences["sequence_length"].iloc[0]),
        "feature_count": len(STATE_FEATURE_COLUMNS),
        "split_count": int(len(splits)),
        "split_role_sample_counts": split_counts,
        "label_status_counts": label_status_counts,
        "best_expert_counts": best_counts,
        "feature_missing_rate": missing_rates,
        "benchmark": benchmark_quality,
        "legacy_w11_test_isolation": legacy_test_isolation,
        "source_manifest_status": source_manifest["status"],
        "runtime_status": source_manifest["runtime"]["status"],
    }
    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    quality_md_path.write_text(
        "\n".join(
            [
                f"# Transformer State Panel — {market}",
                "",
                "- W14 status: `ready`",
                f"- State rows: `{len(state)}`",
                f"- Five-day expert-label rows: `{len(labels)}`",
                f"- Complete max-length sequences: `{len(sequences)}`",
                f"- Protected walk-forward splits: `{len(splits)}`",
                f"- Label status: `{json.dumps(label_status_counts, ensure_ascii=False, sort_keys=True)}`",
                f"- Market benchmark: `{config['benchmark']['method']}`",
                "- Costs: source `strategy_return` is already net; no source cost was recharged.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": TRANSFORMER_STATE_SCHEMA_VERSION,
        "phase": "W14",
        "status": "ready",
        "created_at": _utc_now(),
        "market": market,
        "config_sha256": _sha256_file(config_file),
        "code_version": _git_code_version(root),
        "code_lock": transformer_code_lock(root),
        "source_manifest_sha256": _sha256_file(source_manifest_path),
        "phase_a_manifest_sha256": config["sources"]["phase_a_manifest_sha256"],
        "phase_b_manifest_sha256": config["sources"]["phase_b_manifest_sha256"],
        "phase_b_panel_sha256": config["sources"]["phase_b_panel_sha256"],
        "full_run_source_manifest_sha256": config["sources"]["full_run_source_manifest_sha256"],
        "data_snapshot_sha256": config["sources"]["data_snapshot_sha256"],
        "returns": config["returns"],
        "source_execution": config["source_execution"],
        "label_policy": {
            "horizon_days": LABEL_HORIZON_DAYS,
            "formula": "compound(next 5 strategy_return) - downside - 0.1 * turnover",
            "lambda_downside": float(panel_config["lambda_downside"]),
            "lambda_turnover": float(panel_config["lambda_turnover"]),
            "label_margin": float(panel_config["label_margin"]),
            "partial_horizon": "NaN",
            "ambiguous_training_policy": "exclude from primary classifier fit",
        },
        "sequence_policy": {
            "candidate_lengths": list(panel_config["sequence_length_candidates"]),
            "stored_max_length": max(int(value) for value in panel_config["sequence_length_candidates"]),
            "same_symbol_only": True,
            "future_fill_forbidden": True,
        },
        "split_policy": {
            "method": "four_fold_expanding_purged_walk_forward",
            "protection_days": int(panel_config["protection_days"]),
            "label_horizon_days": LABEL_HORIZON_DAYS,
            "sequence_must_start_inside_role": True,
            "label_must_end_inside_role": True,
            "split_role_sample_counts": split_counts,
            "legacy_w11_test_isolation": legacy_test_isolation,
        },
        "feature_schema_sha256": feature_schema_sha256,
        "feature_columns": list(STATE_FEATURE_COLUMNS),
        "artifacts": {
            "state_sequence_panel": {
                "path": sequence_path.name,
                "sha256": _sha256_file(sequence_path),
                "size_bytes": sequence_path.stat().st_size,
            },
            "state_label_panel": {
                "path": label_path.name,
                "sha256": _sha256_file(label_path),
                "size_bytes": label_path.stat().st_size,
            },
            "walk_forward_splits": {
                "path": splits_path.name,
                "sha256": _sha256_file(splits_path),
                "size_bytes": splits_path.stat().st_size,
            },
            "feature_schema": {
                "path": feature_schema_path.name,
                "sha256": feature_schema_sha256,
                "size_bytes": feature_schema_path.stat().st_size,
            },
            "quality_json": {
                "path": quality_path.name,
                "sha256": _sha256_file(quality_path),
                "size_bytes": quality_path.stat().st_size,
            },
            "quality_markdown": {
                "path": quality_md_path.name,
                "sha256": _sha256_file(quality_md_path),
                "size_bytes": quality_md_path.stat().st_size,
            },
        },
    }
    panel_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return {
        "source_manifest": source_manifest_path,
        "feature_schema": feature_schema_path,
        "state_sequence_panel": sequence_path,
        "state_label_panel": label_path,
        "walk_forward_splits": splits_path,
        "quality_json": quality_path,
        "quality_markdown": quality_md_path,
        "panel_manifest": panel_manifest_path,
    }


__all__ = [
    "FEATURE_SCHEMA_NAME",
    "LABEL_HORIZON_DAYS",
    "PANEL_MANIFEST_NAME",
    "SOURCE_MANIFEST_NAME",
    "STATE_FEATURE_COLUMNS",
    "TransformerStatePanelError",
    "build_transformer_source_manifest",
    "build_transformer_walk_forward_splits",
    "eligible_historical_memory",
    "load_transformer_state_config",
    "materialize_transformer_state_panel",
    "transformer_code_lock",
    "validate_feature_columns",
    "validate_sequence_panel",
    "validate_transformer_state_config",
    "write_blocked_transformer_manifests",
]
