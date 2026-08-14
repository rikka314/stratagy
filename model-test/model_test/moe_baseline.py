from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCHEMA_VERSION = "1.0"
PRIMARY_HORIZON_DAYS = 20
ABLATION_HORIZON_DAYS = (5, 60)
BASELINE_CONTROL_IDS = (
    "best_single_expert",
    "equal_weight_experts",
    "adaptive_router_v1",
)
READY_STATUSES = {"success", "degraded"}
REQUIRED_SOURCE_FILES = (
    "config_snapshot.json",
    "data_manifest.json",
    "report.json",
    "runs.csv",
    "model_summary.csv",
    "stocks.csv",
)


class MoEBaselineError(ValueError):
    """Raised when a Phase-A baseline contract or frozen source is invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MoEBaselineError(f"Unreadable JSON file: {path}") from exc
    if not isinstance(payload, dict):
        raise MoEBaselineError(f"Expected a JSON object: {path}")
    return payload


def _clean_relative_path(value: Any, *, field_name: str) -> Path:
    raw_value = str(value or "").strip()
    if not raw_value:
        raise MoEBaselineError(f"{field_name} must be a non-empty repository-relative path.")
    path = Path(raw_value)
    if path.is_absolute() or ".." in path.parts:
        raise MoEBaselineError(f"{field_name} must be a non-empty repository-relative path.")
    return path


def _canonical_market(value: Any) -> str:
    market = str(value or "").strip().upper()
    aliases = {"US": "US", "CN_A": "CN_A", "CN": "CN_A", "A": "CN_A"}
    try:
        return aliases[market]
    except KeyError as exc:
        raise MoEBaselineError(f"Unsupported market {value!r}; expected US or CN_A.") from exc


def _git_code_version(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        dirty_check = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    version = completed.stdout.strip()
    if not version:
        return "unavailable"
    return f"{version}-dirty" if dirty_check.stdout.strip() else version


def load_moe_baseline_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    config = _json_object(config_path)
    validate_moe_baseline_config(config)
    return config


def validate_moe_baseline_config(config: dict[str, Any]) -> None:
    if str(config.get("schema_version")) != SCHEMA_VERSION:
        raise MoEBaselineError(f"schema_version must be {SCHEMA_VERSION!r}.")
    if str(config.get("phase") or "").upper() != "A":
        raise MoEBaselineError("phase must be 'A'.")
    _canonical_market(config.get("market"))

    if int(config.get("random_seed", -1)) != 42:
        raise MoEBaselineError("Phase A freezes random_seed at 42.")
    if config.get("training_scope") != "market_specific":
        raise MoEBaselineError("training_scope must be 'market_specific'.")
    if config.get("cross_market_policy") != "ablation_only":
        raise MoEBaselineError("cross_market_policy must be 'ablation_only'.")

    horizons = config.get("horizons")
    if not isinstance(horizons, dict):
        raise MoEBaselineError("horizons must be an object.")
    if int(horizons.get("primary_days", -1)) != PRIMARY_HORIZON_DAYS:
        raise MoEBaselineError("The primary prediction horizon must be 20 trading days.")
    ablations = tuple(int(value) for value in horizons.get("ablation_days", []))
    if ablations != ABLATION_HORIZON_DAYS:
        raise MoEBaselineError("Ablation horizons must be exactly [5, 60].")

    returns = config.get("returns")
    if not isinstance(returns, dict):
        raise MoEBaselineError("returns must be an object.")
    if returns.get("net_return_field") != "strategy_return":
        raise MoEBaselineError("strategy_return is the frozen net-return field.")
    if returns.get("gross_return_field") != "gross_strategy_return":
        raise MoEBaselineError("gross_strategy_return is the frozen gross-return field.")
    if returns.get("cost_treatment") != "source_net_no_recharge":
        raise MoEBaselineError("cost_treatment must prevent charging source costs twice.")

    execution = config.get("execution")
    if not isinstance(execution, dict):
        raise MoEBaselineError("execution must be an object.")
    for key in ("commission_bps", "slippage_bps"):
        try:
            numeric = float(execution[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise MoEBaselineError(f"execution.{key} must be numeric.") from exc
        if not math.isfinite(numeric) or numeric < 0:
            raise MoEBaselineError(f"execution.{key} must be finite and non-negative.")

    sources = config.get("source_runs")
    if not isinstance(sources, dict) or set(sources) != {"window3b", "full_run"}:
        raise MoEBaselineError("source_runs must contain exactly window3b and full_run.")
    for source_name, source in sources.items():
        if not isinstance(source, dict):
            raise MoEBaselineError(f"source_runs.{source_name} must be an object.")
        _clean_relative_path(source.get("output_dir"), field_name=f"source_runs.{source_name}.output_dir")
        _clean_relative_path(source.get("config_path"), field_name=f"source_runs.{source_name}.config_path")

    experts = config.get("experts")
    if not isinstance(experts, list) or not 6 <= len(experts) <= 8:
        raise MoEBaselineError("experts must freeze 6 to 8 representative entries, including Cash.")
    expert_ids = [str(entry.get("expert_id") or "") for entry in experts if isinstance(entry, dict)]
    if len(expert_ids) != len(experts) or any(not expert_id for expert_id in expert_ids):
        raise MoEBaselineError("Every expert requires a non-empty expert_id.")
    if len(set(expert_ids)) != len(expert_ids):
        raise MoEBaselineError("expert_id values must be unique.")
    cash_entries = [entry for entry in experts if entry.get("expert_id") == "cash"]
    if len(cash_entries) != 1 or cash_entries[0].get("source_model_id") is not None:
        raise MoEBaselineError("The frozen pool must contain one synthetic cash expert.")
    for entry in experts:
        availability = entry.get("availability", "required")
        if availability not in {"required", "known_unavailable"}:
            raise MoEBaselineError("expert availability must be required or known_unavailable.")
        if entry.get("expert_id") != "cash" and availability == "required" and not entry.get("source_model_id"):
            raise MoEBaselineError("Required non-cash experts need a source_model_id.")

    controls = config.get("baseline_controls")
    if not isinstance(controls, list):
        raise MoEBaselineError("baseline_controls must be a list.")
    control_ids = tuple(str(item.get("control_id") or "") for item in controls if isinstance(item, dict))
    if control_ids != BASELINE_CONTROL_IDS:
        raise MoEBaselineError(
            "baseline_controls must freeze best_single_expert, equal_weight_experts, and adaptive_router_v1 in order."
        )

    selection = config.get("train_selection")
    if not isinstance(selection, dict) or selection.get("scope") != "market_train_only":
        raise MoEBaselineError("train_selection.scope must be market_train_only.")
    if selection.get("forbid_test_columns") is not True:
        raise MoEBaselineError("train_selection must explicitly forbid test columns.")
    weights = selection.get("score_weights")
    if not isinstance(weights, dict) or set(weights) != {"train_sharpe", "train_annret", "train_maxdd_penalty"}:
        raise MoEBaselineError("train_selection.score_weights has an invalid schema.")
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in weights.values()):
        raise MoEBaselineError("train_selection score weights must be finite and non-negative.")


def _source_validation(
    *,
    repo_root: Path,
    source_name: str,
    source: dict[str, Any],
    market: str,
    random_seed: int,
    execution: dict[str, Any],
) -> dict[str, Any]:
    output_rel = _clean_relative_path(source["output_dir"], field_name=f"source_runs.{source_name}.output_dir")
    config_rel = _clean_relative_path(source["config_path"], field_name=f"source_runs.{source_name}.config_path")
    output_dir = repo_root / output_rel
    config_path = repo_root / config_rel
    missing_files = [name for name in REQUIRED_SOURCE_FILES if not (output_dir / name).is_file()]
    issues: list[str] = []
    tracked_config: dict[str, Any] = {}
    if not config_path.is_file():
        issues.append(f"tracked source config is missing: {config_rel.as_posix()}")
    else:
        try:
            tracked_config = _json_object(config_path)
        except MoEBaselineError as exc:
            issues.append(str(exc))
    if missing_files:
        issues.append("missing source artifacts: " + ", ".join(missing_files))

    manifest: dict[str, Any] = {}
    snapshot: dict[str, Any] = {}
    if not missing_files:
        try:
            manifest = _json_object(output_dir / "data_manifest.json")
            snapshot = _json_object(output_dir / "config_snapshot.json")
        except MoEBaselineError as exc:
            issues.append(str(exc))

    if manifest:
        try:
            if _canonical_market(manifest.get("market")) != market:
                issues.append(f"source manifest market is {manifest.get('market')!r}, expected {market!r}")
            if int(manifest.get("random_seed", -1)) != random_seed:
                issues.append(f"source manifest random_seed is not {random_seed}")
            if not str(manifest.get("code_version") or "").strip():
                issues.append("source manifest code_version is missing")
            if not str((manifest.get("data") or {}).get("snapshot_sha256") or "").strip():
                issues.append("source manifest data.snapshot_sha256 is missing")
            manifest_execution = manifest.get("execution") or {}
            for key in ("commission_bps", "slippage_bps"):
                if float(manifest_execution.get(key, -1)) != float(execution[key]):
                    issues.append(f"source manifest execution.{key} does not match the Phase-A contract")
        except (MoEBaselineError, TypeError, ValueError) as exc:
            issues.append(f"invalid source manifest metadata: {exc}")

    if snapshot:
        try:
            if _canonical_market(snapshot.get("market")) != market:
                issues.append(f"source config snapshot market is {snapshot.get('market')!r}, expected {market!r}")
            for key in ("commission_bps", "slippage_bps"):
                if float(snapshot.get(key, -1)) != float(execution[key]):
                    issues.append(f"source config snapshot {key} does not match the Phase-A contract")
        except (MoEBaselineError, TypeError, ValueError) as exc:
            issues.append(f"invalid source config snapshot metadata: {exc}")

    if snapshot and tracked_config:
        for key, expected in tracked_config.items():
            if key == "parallelism" and (expected == 0 or str(expected).lower() == "auto"):
                continue
            if key not in snapshot:
                issues.append(f"source config snapshot is missing tracked field {key}")
                continue
            if snapshot[key] != expected:
                issues.append(f"source config snapshot field {key} does not match the tracked config")

    hashed_files = []
    if not missing_files:
        for name in REQUIRED_SOURCE_FILES:
            path = output_dir / name
            hashed_files.append({"name": name, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size})

    return {
        "source_name": source_name,
        "status": "ready" if not issues else "pending",
        "output_dir": output_rel.as_posix(),
        "tracked_config_path": config_rel.as_posix(),
        "tracked_config_sha256": _sha256_file(config_path) if config_path.is_file() else None,
        "run_id": manifest.get("run_id"),
        "code_version": manifest.get("code_version"),
        "random_seed": manifest.get("random_seed"),
        "data_snapshot_sha256": (manifest.get("data") or {}).get("snapshot_sha256"),
        "source_manifest_sha256": _sha256_file(output_dir / "data_manifest.json") if manifest else None,
        "source_files": hashed_files,
        "issues": issues,
    }


def build_phase_a_manifest(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config_file = Path(config_path)
    config = load_moe_baseline_config(config_file)
    root = Path(repo_root).resolve()
    market = _canonical_market(config["market"])
    sources = [
        _source_validation(
            repo_root=root,
            source_name=source_name,
            source=source,
            market=market,
            random_seed=int(config["random_seed"]),
            execution=config["execution"],
        )
        for source_name, source in config["source_runs"].items()
    ]
    source_fingerprint_rows = [
        {
            "source_name": source["source_name"],
            "source_manifest_sha256": source["source_manifest_sha256"],
            "tracked_config_sha256": source["tracked_config_sha256"],
            "data_snapshot_sha256": source["data_snapshot_sha256"],
            "code_version": source["code_version"],
        }
        for source in sources
    ]
    source_fingerprint = hashlib.sha256(
        json.dumps(source_fingerprint_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "A",
        "status": "ready" if all(source["status"] == "ready" for source in sources) else "pending",
        "name": config["name"],
        "market": market,
        "generated_at": timestamp,
        "generator_code_version": _git_code_version(root),
        "phase_a_config_path": config_file.resolve().relative_to(root).as_posix(),
        "phase_a_config_sha256": _sha256_file(config_file),
        "source_fingerprint_sha256": source_fingerprint,
        "random_seed": int(config["random_seed"]),
        "training_scope": config["training_scope"],
        "cross_market_policy": config["cross_market_policy"],
        "horizons": config["horizons"],
        "returns": config["returns"],
        "execution": config["execution"],
        "train_selection": config["train_selection"],
        "experts": config["experts"],
        "baseline_controls": config["baseline_controls"],
        "sources": sources,
    }


def _required_source_model_ids(config: dict[str, Any], *, equal_weight_only: bool = False) -> list[str]:
    result: list[str] = []
    for expert in config["experts"]:
        if expert.get("availability", "required") != "required":
            continue
        if expert.get("expert_id") == "cash":
            continue
        if equal_weight_only and not bool(expert.get("include_in_equal_weight", False)):
            continue
        model_id = str(expert.get("source_model_id") or "")
        if model_id and model_id not in result:
            result.append(model_id)
    return result


def select_best_single_expert(records_df: pd.DataFrame, config: dict[str, Any]) -> tuple[str, pd.DataFrame]:
    """Select one market-level expert using train metrics only."""
    required_columns = {"model_id", "window_kind", "status", "train_sharpe", "train_annret", "train_maxdd"}
    missing = required_columns - set(records_df.columns)
    if missing:
        raise MoEBaselineError(f"runs.csv is missing train-selection columns: {sorted(missing)}")
    candidate_ids = _required_source_model_ids(config)
    frame = records_df.loc[
        records_df["model_id"].astype(str).isin(candidate_ids)
        & (records_df["window_kind"].astype(str) == "main")
        & records_df["status"].astype(str).isin(READY_STATUSES)
    ].copy()
    if frame.empty:
        raise MoEBaselineError("No ready main-window expert rows are available for train-only selection.")
    for column in ("train_sharpe", "train_annret", "train_maxdd"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    summary = (
        frame.groupby("model_id", sort=True)
        .agg(
            record_count=("model_id", "size"),
            valid_train_count=("train_sharpe", "count"),
            median_train_sharpe=("train_sharpe", "median"),
            median_train_annret=("train_annret", "median"),
            median_train_maxdd=("train_maxdd", "median"),
        )
        .reset_index()
    )
    expected_models = set(candidate_ids)
    present_models = set(summary["model_id"].astype(str))
    if present_models != expected_models:
        missing_models = sorted(expected_models - present_models)
        raise MoEBaselineError("Required expert rows are missing from the frozen full run: " + ", ".join(missing_models))
    if summary[["median_train_sharpe", "median_train_annret", "median_train_maxdd"]].isna().any(axis=None):
        raise MoEBaselineError("At least one required expert has incomplete train-only metrics.")

    weights = config["train_selection"]["score_weights"]
    summary["train_selection_score"] = (
        float(weights["train_sharpe"]) * summary["median_train_sharpe"]
        + float(weights["train_annret"]) * summary["median_train_annret"]
        - float(weights["train_maxdd_penalty"]) * summary["median_train_maxdd"].abs()
    )
    summary["coverage_rate"] = summary["valid_train_count"] / summary["record_count"].clip(lower=1)
    summary = summary.sort_values(
        ["train_selection_score", "coverage_rate", "median_train_annret", "model_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    summary["train_selection_rank"] = summary.index + 1
    return str(summary.iloc[0]["model_id"]), summary


def _resolve_artifact_path(path_value: Any, source_dir: Path) -> Path:
    raw = Path(str(path_value or ""))
    if raw.is_file():
        return raw
    parts = list(raw.parts)
    if "artifacts" in parts:
        candidate = source_dir / Path(*parts[parts.index("artifacts") :])
        if candidate.is_file():
            return candidate
    raise MoEBaselineError(f"Missing returns artifact: {path_value}")


def _read_net_returns(path_value: Any, source_dir: Path) -> pd.Series:
    path = _resolve_artifact_path(path_value, source_dir)
    frame = pd.read_csv(path)
    required = {"date", "strategy_return"}
    if not required.issubset(frame.columns):
        raise MoEBaselineError(f"{path} must contain date and strategy_return.")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    values = pd.to_numeric(frame["strategy_return"], errors="coerce")
    valid = dates.notna() & values.notna()
    if not valid.any():
        raise MoEBaselineError(f"{path} contains no valid net-return rows.")
    return pd.Series(values.loc[valid].to_numpy(), index=dates.loc[valid], dtype="float64").groupby(level=0).mean()


def _portfolio_net_returns(
    records_df: pd.DataFrame,
    *,
    source_dir: Path,
    model_ids: Iterable[str],
) -> tuple[pd.Series, pd.DataFrame]:
    selected_ids = list(dict.fromkeys(str(model_id) for model_id in model_ids))
    required = {"symbol", "model_id", "window_kind", "status", "returns_path"}
    missing = required - set(records_df.columns)
    if missing:
        raise MoEBaselineError(f"runs.csv is missing return-artifact columns: {sorted(missing)}")
    selected = records_df.loc[
        records_df["model_id"].astype(str).isin(selected_ids)
        & (records_df["window_kind"].astype(str) == "main")
        & records_df["status"].astype(str).isin(READY_STATUSES)
    ].copy()
    present_ids = set(selected["model_id"].astype(str))
    missing_ids = sorted(set(selected_ids) - present_ids)
    if missing_ids:
        raise MoEBaselineError("Required source models have no ready main-window returns: " + ", ".join(missing_ids))
    duplicate_mask = selected.duplicated(subset=["symbol", "model_id"], keep=False)
    if duplicate_mask.any():
        duplicate_keys = sorted(
            {
                f"{row.symbol}/{row.model_id}"
                for row in selected.loc[duplicate_mask, ["symbol", "model_id"]].itertuples(index=False)
            }
        )
        raise MoEBaselineError("Duplicate main-window expert rows: " + ", ".join(duplicate_keys))

    symbol_sets = {
        model_id: set(selected.loc[selected["model_id"].astype(str) == model_id, "symbol"].astype(str))
        for model_id in selected_ids
    }
    if any(symbols != next(iter(symbol_sets.values())) for symbols in symbol_sets.values()):
        raise MoEBaselineError("Expert symbol coverage differs; equal-weight re-normalization is forbidden in Phase A.")

    symbol_portfolios: list[pd.Series] = []
    for symbol, symbol_rows in selected.groupby("symbol", sort=True):
        expert_series = []
        for row in symbol_rows.sort_values("model_id").itertuples(index=False):
            expert_series.append(_read_net_returns(row.returns_path, source_dir).rename(str(row.model_id)))
        aligned_experts = pd.concat(expert_series, axis=1, join="inner").dropna()
        if aligned_experts.empty:
            raise MoEBaselineError(f"No common net-return dates for {symbol}.")
        symbol_portfolios.append(aligned_experts.mean(axis=1).rename(str(symbol)))
    aligned_symbols = pd.concat(symbol_portfolios, axis=1, join="inner").dropna().sort_index()
    portfolio = aligned_symbols.mean(axis=1).dropna()
    if portfolio.empty:
        raise MoEBaselineError("The baseline portfolio contains no daily returns.")
    portfolio.name = "strategy_return"
    return portfolio, selected


def _return_metrics(returns: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        raise MoEBaselineError("Cannot evaluate an empty return series.")
    equity = (1.0 + clean).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    annualized_return = float((1.0 + total_return) ** (252.0 / len(clean)) - 1.0)
    wealth_with_initial = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)], ignore_index=True)
    drawdown = wealth_with_initial / wealth_with_initial.cummax() - 1.0
    std = float(clean.std(ddof=1))
    sharpe = float(clean.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
    }


def _numeric_mean(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _result_row(
    *,
    market: str,
    control_id: str,
    selected_model_ids: list[str],
    returns: pd.Series,
    records: pd.DataFrame,
) -> dict[str, Any]:
    metrics = _return_metrics(returns)
    return {
        "market": market,
        "control_id": control_id,
        "status": "ready",
        "selected_model_ids": json.dumps(selected_model_ids, ensure_ascii=False),
        "selection_scope": "market_train_only" if control_id == "best_single_expert" else "frozen",
        "return_field": "strategy_return",
        "cost_treatment": "source_net_no_recharge",
        "record_count": int(len(records)),
        "symbol_count": int(records["symbol"].astype(str).nunique()),
        "start": returns.index.min().date().isoformat(),
        "end": returns.index.max().date().isoformat(),
        **metrics,
        "source_total_turnover_mean": _numeric_mean(records, "total_turnover"),
        "source_total_transaction_cost_mean": _numeric_mean(records, "total_transaction_cost"),
        "reason": None,
    }


def _pending_rows(config: dict[str, Any], reason: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": _canonical_market(config["market"]),
                "control_id": control_id,
                "status": "unavailable",
                "selected_model_ids": "[]",
                "selection_scope": "market_train_only" if control_id == "best_single_expert" else "frozen",
                "return_field": "strategy_return",
                "cost_treatment": "source_net_no_recharge",
                "record_count": 0,
                "symbol_count": 0,
                "start": None,
                "end": None,
                "total_return": None,
                "annualized_return": None,
                "sharpe": None,
                "max_drawdown": None,
                "source_total_turnover_mean": None,
                "source_total_transaction_cost_mean": None,
                "reason": reason,
            }
            for control_id in BASELINE_CONTROL_IDS
        ]
    )


def _unavailable_control_row(config: dict[str, Any], control_id: str, reason: str) -> dict[str, Any]:
    return _pending_rows(config, reason).loc[
        lambda frame: frame["control_id"] == control_id
    ].iloc[0].to_dict()


def build_baseline_outputs(
    config: dict[str, Any],
    *,
    source_dir: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build frozen control summaries and daily net returns from a complete full run."""
    source = Path(source_dir)
    records_df = pd.read_csv(source / "runs.csv")
    best_model_id, selection_summary = select_best_single_expert(records_df, config)
    equal_weight_model_ids = _required_source_model_ids(config, equal_weight_only=True)
    adaptive_control = next(
        control for control in config["baseline_controls"] if control["control_id"] == "adaptive_router_v1"
    )
    adaptive_model_id = str(adaptive_control["source_model_id"])

    controls = [
        ("best_single_expert", [best_model_id], "required", None),
        ("equal_weight_experts", equal_weight_model_ids, "required", None),
        (
            "adaptive_router_v1",
            [adaptive_model_id],
            str(adaptive_control.get("availability", "required")),
            adaptive_control.get("unavailable_reason"),
        ),
    ]
    result_rows: list[dict[str, Any]] = []
    daily_frames: list[pd.DataFrame] = []
    market = _canonical_market(config["market"])
    for control_id, model_ids, availability, unavailable_reason in controls:
        if availability == "known_unavailable":
            result_rows.append(
                _unavailable_control_row(
                    config,
                    control_id,
                    str(unavailable_reason or "The frozen source does not support this control."),
                )
            )
            continue
        portfolio, selected_records = _portfolio_net_returns(
            records_df,
            source_dir=source,
            model_ids=model_ids,
        )
        result_rows.append(
            _result_row(
                market=market,
                control_id=control_id,
                selected_model_ids=model_ids,
                returns=portfolio,
                records=selected_records,
            )
        )
        daily_frames.append(
            pd.DataFrame(
                {
                    "date": portfolio.index.strftime("%Y-%m-%d"),
                    "market": market,
                    "control_id": control_id,
                    "strategy_return": portfolio.to_numpy(),
                }
            )
        )
    daily_df = (
        pd.concat(daily_frames, ignore_index=True)
        if daily_frames
        else pd.DataFrame(columns=["date", "market", "control_id", "strategy_return"])
    )
    return pd.DataFrame(result_rows), daily_df, selection_summary


def materialize_phase_a_baseline(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
    allow_pending: bool = False,
) -> dict[str, Path]:
    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_moe_baseline_config(config_file)
    manifest = build_phase_a_manifest(config_file, repo_root=root)
    target = Path(output_dir) if output_dir is not None else root / "model-test" / "outputs" / config["output_subdir"]

    issues = [issue for source in manifest["sources"] for issue in source["issues"]]
    if issues and not allow_pending:
        raise MoEBaselineError("Phase-A source validation failed: " + "; ".join(issues))

    if issues:
        results_df = _pending_rows(config, "; ".join(issues))
        daily_df = pd.DataFrame(columns=["date", "market", "control_id", "strategy_return"])
        selection_df = pd.DataFrame()
    else:
        full_source = next(source for source in manifest["sources"] if source["source_name"] == "full_run")
        results_df, daily_df, selection_df = build_baseline_outputs(
            config,
            source_dir=root / full_source["output_dir"],
        )

    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "data_manifest": target / "data_manifest.json",
        "baseline_results": target / "baseline_results.csv",
        "baseline_daily_returns": target / "baseline_daily_returns.csv",
        "train_selection_summary": target / "train_selection_summary.csv",
    }
    paths["data_manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    results_df.to_csv(paths["baseline_results"], index=False)
    daily_df.to_csv(paths["baseline_daily_returns"], index=False)
    selection_df.to_csv(paths["train_selection_summary"], index=False)
    return paths
