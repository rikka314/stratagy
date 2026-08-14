"""Phase-B expert-day panel materialization for the dynamic ensemble research line.

The module deliberately stays independent from Streamlit and from the Phase-C
gating model.  It consumes the frozen Phase-A configuration plus the source
runner artifacts and produces a point-in-time panel that can be audited back to
one source run, symbol, model and artifact file.

The source runner stores ``strategy_return`` after execution costs.  Phase B
therefore carries that field through unchanged and never recharges costs.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from model_test.moe_baseline import (
    READY_STATUSES,
    MoEBaselineError,
    _canonical_market,
    _resolve_artifact_path,
    _sha256_file,
    build_phase_a_manifest,
    load_moe_baseline_config,
)


PHASE_B_SCHEMA_VERSION = "1.0"
PRIMARY_HORIZON_DAYS = 20
DEFAULT_N_SPLITS = 3
DEFAULT_EMBARGO_DAYS = PRIMARY_HORIZON_DAYS
DEFAULT_LAMBDA_DOWNSIDE = 1.0
DEFAULT_LAMBDA_TURNOVER = 0.1
DEFAULT_FEATURE_WINDOWS = (5, 20)
PANEL_KEY_COLUMNS = ("date", "symbol", "market", "expert_id")
LABEL_COLUMNS = (
    "future_net_return",
    "future_downside",
    "future_turnover_penalty",
    "future_utility",
)
LINEAGE_COLUMNS = (
    "source_run_id",
    "source_code_version",
    "source_data_snapshot_sha256",
    "source_manifest_sha256",
    "source_model_id",
    "source_window_id",
    "source_artifact_path",
    "source_artifact_sha256",
)


class ExpertPanelError(ValueError):
    """Raised when a Phase-B input or leakage contract is invalid."""


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _git_code_version(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    commit = completed.stdout.strip()
    if not commit:
        return "unavailable"
    return f"{commit}-dirty" if dirty.stdout.strip() else commit


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _clean_dates(values: Iterable[Any]) -> pd.DatetimeIndex:
    parsed = pd.to_datetime(pd.Index(list(values)), errors="coerce")
    parsed = parsed[~parsed.isna()]
    if len(parsed) == 0:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(parsed.normalize()).drop_duplicates().sort_values()


def _read_csv(path: Path, *, required: Iterable[str] = ()) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise ExpertPanelError(f"Unable to read source artifact: {path}") from exc
    missing = set(required) - set(frame.columns)
    if missing:
        raise ExpertPanelError(f"{path} is missing required columns: {sorted(missing)}")
    return frame


def _resolve_optional_path(value: Any, source_dir: Path) -> Path | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    raw = Path(str(value))
    if raw.is_file():
        return raw
    if raw.is_absolute():
        return None
    candidate = source_dir / raw
    if candidate.is_file():
        return candidate
    if "artifacts" in raw.parts:
        candidate = source_dir / Path(*raw.parts[raw.parts.index("artifacts") :])
        if candidate.is_file():
            return candidate
    return None


def _coerce_artifact_dates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "date" not in out.columns:
        raise ExpertPanelError("Expert artifact must contain a date column.")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out = out.loc[out["date"].notna()].copy()
    if out.empty:
        raise ExpertPanelError("Expert artifact contains no valid dates.")
    return out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _read_expert_artifact(record: pd.Series, source_dir: Path) -> tuple[pd.DataFrame, Path]:
    """Read the return artifact and optional daily simulation columns.

    Older runs only have ``returns.csv`` and ``benchmark_returns.csv``.  Newer
    runs may also expose ``daily.csv``.  The merge is intentionally additive:
    no missing position or turnover values are filled from a different expert.
    """

    returns_path = _resolve_artifact_path(record.get("returns_path"), source_dir)
    returns = _coerce_artifact_dates(_read_csv(returns_path, required=("date", "strategy_return")))
    returns["strategy_return"] = _numeric(returns, "strategy_return")

    candidates = [
        returns_path.with_name("daily.csv"),
        returns_path.with_name("simulation.csv"),
        returns_path.with_name("test_sim.csv"),
    ]
    daily_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if daily_path is not None:
        daily = _coerce_artifact_dates(_read_csv(daily_path))
        value_columns = [
            "target_position",
            "position",
            "turnover",
            "transaction_cost",
            "gross_strategy_return",
            "benchmark_return",
        ]
        keep = ["date", *[column for column in value_columns if column in daily.columns]]
        returns = returns.merge(daily[keep], on="date", how="left", suffixes=("", "_daily"))

    benchmark_path = _resolve_optional_path(record.get("benchmark_returns_path"), source_dir)
    if benchmark_path is not None:
        benchmark = _coerce_artifact_dates(_read_csv(benchmark_path, required=("date",)))
        benchmark_column = "benchmark_return" if "benchmark_return" in benchmark.columns else None
        if benchmark_column is not None:
            benchmark = benchmark[["date", benchmark_column]].rename(columns={benchmark_column: "benchmark_return"})
            returns = returns.merge(benchmark, on="date", how="left", suffixes=("", "_benchmark"))

    if "target_position" not in returns.columns and "position" not in returns.columns:
        # This is a valid return-only legacy artifact.  The panel keeps the
        # expert available while explicitly marking target position missing.
        returns["target_position"] = np.nan
        position_source = None
    elif "target_position" not in returns.columns:
        returns["target_position"] = _numeric(returns, "position")
        position_source = "source_position"
    else:
        returns["target_position"] = _numeric(returns, "target_position")
        position_source = "source_target_position"
        if returns["target_position"].isna().all() and "position" in returns.columns:
            returns["target_position"] = _numeric(returns, "position")
            position_source = "source_position" if returns["target_position"].notna().any() else None
    if not returns["target_position"].notna().any():
        position_source = None
    if position_source is None:
        trades_path = _resolve_optional_path(record.get("trades_path"), source_dir)
        if trades_path is None:
            candidate = returns_path.with_name("trades.csv")
            trades_path = candidate if candidate.is_file() else None
        if trades_path is not None:
            try:
                trades = _read_csv(trades_path, required=("entry_date", "exit_date"))
                position = pd.Series(0.0, index=returns.index, dtype="float64")
                dates = returns["date"]
                for trade in trades.to_dict("records"):
                    entry = pd.to_datetime(trade.get("entry_date"), errors="coerce")
                    exit_date = pd.to_datetime(trade.get("exit_date"), errors="coerce")
                    if pd.isna(entry) or pd.isna(exit_date):
                        continue
                    position.loc[(dates >= entry.normalize()) & (dates <= exit_date.normalize())] = 1.0
                if position.any():
                    returns["target_position"] = position
                    position_source = "trades_reconstructed"
            except ExpertPanelError:
                pass
    for column in ("turnover", "transaction_cost", "gross_strategy_return", "benchmark_return"):
        returns[column] = _numeric(returns, column)

    if returns["turnover"].isna().all() and returns["target_position"].notna().any():
        previous = returns["target_position"].shift(1).fillna(0.0)
        returns["turnover"] = (returns["target_position"] - previous).abs()
        returns["turnover_source"] = "derived_from_target_position"
    else:
        returns["turnover_source"] = "source_artifact"
    returns["position_source"] = position_source

    # Retain point-in-time state/regime columns when a richer artifact already
    # contains them.  They are copied as-is and never shifted into the future.
    passthrough = [
        column
        for column in returns.columns
        if str(column).startswith(("regime_", "state_", "adaptive_"))
    ]
    for column in passthrough:
        returns[column] = returns[column]
    return returns, daily_path or returns_path


def _rolling_compound(series: pd.Series, window: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return (1.0 + values).rolling(window, min_periods=1).apply(np.prod, raw=True) - 1.0


def _rolling_future_sum(series: pd.Series, window: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    reversed_values = values.iloc[::-1]
    result = reversed_values.rolling(window, min_periods=window).sum().iloc[::-1]
    return result


def _rolling_future_compound(series: pd.Series, window: int) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    reversed_values = (1.0 + values).iloc[::-1]
    result = reversed_values.rolling(window, min_periods=window).apply(np.prod, raw=True).iloc[::-1]
    return result - 1.0


def _compute_expert_features(frame: pd.DataFrame, windows: tuple[int, ...]) -> pd.DataFrame:
    out = frame.sort_values("date").copy()
    returns = _numeric(out, "strategy_return")
    positions = _numeric(out, "target_position")
    turnover = _numeric(out, "turnover")
    if turnover.isna().all() and positions.notna().any():
        turnover = positions.diff().abs().fillna(positions.abs())
    out["target_position"] = positions
    out["turnover"] = turnover
    out["position_change"] = positions.diff().abs().fillna(positions.abs())
    out["expert_return_observation"] = returns.notna().astype("int8")

    wealth = (1.0 + returns).cumprod()
    for window in windows:
        suffix = int(window)
        out[f"expert_recent_net_return_{suffix}"] = _rolling_compound(returns, suffix)
        out[f"expert_return_volatility_{suffix}"] = returns.rolling(suffix, min_periods=1).std(ddof=0)
        rolling_max = wealth.rolling(suffix, min_periods=1).max()
        out[f"expert_drawdown_{suffix}"] = wealth / rolling_max - 1.0
        out[f"expert_turnover_{suffix}"] = turnover.rolling(suffix, min_periods=1).sum()
        out[f"expert_stability_{suffix}"] = (returns > 0).astype(float).rolling(suffix, min_periods=1).mean()
        out[f"expert_observation_count_{suffix}"] = returns.rolling(suffix, min_periods=1).count()
    return out


def compute_future_utility(
    frame: pd.DataFrame,
    *,
    horizon_days: int = PRIMARY_HORIZON_DAYS,
    lambda_downside: float = DEFAULT_LAMBDA_DOWNSIDE,
    lambda_turnover: float = DEFAULT_LAMBDA_TURNOVER,
) -> pd.DataFrame:
    """Add the frozen Phase-B future label without charging costs twice.

    ``future_net_return`` compounds the next ``horizon_days`` source
    ``strategy_return`` values.  ``future_downside`` is the cumulative absolute
    negative-return component and ``future_turnover_penalty`` is cumulative
    future turnover.  All three require a complete horizon; partial windows
    remain NaN rather than being silently truncated.
    """

    horizon = int(horizon_days)
    if horizon <= 0:
        raise ExpertPanelError("horizon_days must be positive")
    downside_weight = _finite_float(lambda_downside)
    turnover_weight = _finite_float(lambda_turnover)
    if downside_weight is None or downside_weight < 0 or turnover_weight is None or turnover_weight < 0:
        raise ExpertPanelError("label penalty weights must be finite and non-negative")

    out = frame.sort_values("date").copy()
    returns = _numeric(out, "strategy_return")
    turnover = _numeric(out, "turnover")
    future_returns = returns.shift(-1)
    out["future_net_return"] = _rolling_future_compound(future_returns, horizon)
    downside = future_returns.clip(upper=0.0).abs()
    out["future_downside"] = _rolling_future_sum(downside, horizon)
    out["future_turnover_penalty"] = _rolling_future_sum(turnover.shift(-1), horizon)
    complete = (
        _rolling_future_sum(future_returns.notna().astype(float), horizon).eq(float(horizon))
        & _rolling_future_sum(downside.notna().astype(float), horizon).eq(float(horizon))
        & _rolling_future_sum(turnover.shift(-1).notna().astype(float), horizon).eq(float(horizon))
    )
    for column in LABEL_COLUMNS:
        out.loc[~complete, column] = np.nan
    out["future_utility"] = (
        out["future_net_return"]
        - float(downside_weight) * out["future_downside"]
        - float(turnover_weight) * out["future_turnover_penalty"]
    )
    out["label_horizon_days"] = horizon
    return out


def build_purged_walk_forward_splits(
    dates: Iterable[Any],
    *,
    primary_horizon_days: int = PRIMARY_HORIZON_DAYS,
    n_splits: int = DEFAULT_N_SPLITS,
    min_train_days: int | None = None,
    validation_days: int | None = None,
    test_days: int | None = None,
    step_days: int | None = None,
    embargo_days: int | None = None,
) -> pd.DataFrame:
    """Build expanding purged walk-forward splits on trading-date positions.

    The purge removes one full label horizon before validation/test.  A second
    independent embargo gap of at least one horizon is then inserted between
    adjacent partitions.  Position arithmetic is used so weekends and market
    holidays cannot shorten the protection window.
    """

    horizon = int(primary_horizon_days)
    count = int(n_splits)
    if horizon <= 0 or count <= 0:
        raise ExpertPanelError("primary_horizon_days and n_splits must be positive")
    unique_dates = _clean_dates(dates)
    if len(unique_dates) == 0:
        return pd.DataFrame(
            columns=[
                "split_id",
                "train_start",
                "train_end",
                "validation_start",
                "validation_end",
                "test_start",
                "test_end",
                "purge_days",
                "embargo_days",
                "status",
                "reason",
            ]
        )
    validation = max(1, int(validation_days or horizon))
    test = max(1, int(test_days or horizon))
    step = max(1, int(step_days or test))
    embargo = max(horizon, int(embargo_days if embargo_days is not None else horizon))
    minimum_train = max(1, int(min_train_days or max(horizon * 3, validation)))

    rows: list[dict[str, Any]] = []
    total = len(unique_dates)
    # Construct from the end so every emitted test interval is strictly in the
    # future of its train/validation interval and the result is chronological.
    for offset in range(count - 1, -1, -1):
        test_end_idx = total - 1 - offset * step
        test_start_idx = test_end_idx - test + 1
        validation_end_idx = test_start_idx - embargo - horizon - 1
        validation_start_idx = validation_end_idx - validation + 1
        train_end_idx = validation_start_idx - embargo - horizon - 1
        train_start_idx = 0
        if min(test_start_idx, validation_start_idx, train_end_idx) < 0:
            continue
        if train_end_idx - train_start_idx + 1 < minimum_train:
            continue
        rows.append(
            {
                "split_id": f"wf_{len(rows) + 1:02d}",
                "train_start": unique_dates[train_start_idx].date().isoformat(),
                "train_end": unique_dates[train_end_idx].date().isoformat(),
                "validation_start": unique_dates[validation_start_idx].date().isoformat(),
                "validation_end": unique_dates[validation_end_idx].date().isoformat(),
                "test_start": unique_dates[test_start_idx].date().isoformat(),
                "test_end": unique_dates[test_end_idx].date().isoformat(),
                "purge_days": horizon,
                "embargo_days": embargo,
                "status": "ready",
                "reason": None,
            }
        )
    columns = [
        "split_id",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
        "purge_days",
        "embargo_days",
        "status",
        "reason",
    ]
    return pd.DataFrame(rows, columns=columns)


def validate_purged_walk_forward_splits(
    splits: pd.DataFrame,
    *,
    primary_horizon_days: int = PRIMARY_HORIZON_DAYS,
) -> None:
    """Raise when a split violates temporal ordering, purge or embargo rules."""

    required = {
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
        "purge_days",
        "embargo_days",
    }
    missing = required - set(splits.columns)
    if missing:
        raise ExpertPanelError(f"walk-forward splits are missing columns: {sorted(missing)}")
    horizon = int(primary_horizon_days)
    for row in splits.to_dict("records"):
        dates = {key: pd.Timestamp(row[key]) for key in required if key.endswith(("start", "end"))}
        ordered = (
            dates["train_start"]
            <= dates["train_end"]
            < dates["validation_start"]
            <= dates["validation_end"]
            < dates["test_start"]
            <= dates["test_end"]
        )
        if not ordered:
            raise ExpertPanelError(f"invalid temporal order in split {row.get('split_id')}")
        if int(row["purge_days"]) < horizon or int(row["embargo_days"]) < horizon:
            raise ExpertPanelError(f"split {row.get('split_id')} has insufficient purge or embargo")


def _future_feature_columns(columns: Iterable[str]) -> list[str]:
    return [column for column in columns if str(column).startswith("future_")]


def validate_panel_no_leakage(
    panel: pd.DataFrame,
    *,
    splits: pd.DataFrame | None = None,
    primary_horizon_days: int = PRIMARY_HORIZON_DAYS,
) -> None:
    """Validate key point-in-time and split invariants for a panel."""

    missing = set(PANEL_KEY_COLUMNS) - set(panel.columns)
    if missing:
        raise ExpertPanelError(f"expert panel is missing key columns: {sorted(missing)}")
    dates = pd.to_datetime(panel["date"], errors="coerce")
    if dates.isna().any():
        raise ExpertPanelError("expert panel contains invalid dates")
    duplicate = panel.duplicated(list(PANEL_KEY_COLUMNS), keep=False)
    if duplicate.any():
        raise ExpertPanelError("expert panel contains duplicate date/symbol/market/expert rows")
    if "feature_columns_json" in panel.columns:
        for value in panel["feature_columns_json"].dropna():
            if isinstance(value, (list, tuple)):
                features = list(value)
            else:
                try:
                    features = json.loads(str(value))
                except json.JSONDecodeError as exc:
                    raise ExpertPanelError("feature_columns_json is not valid JSON") from exc
            if _future_feature_columns(features):
                raise ExpertPanelError("future label columns cannot be listed as features")
    if splits is not None and not splits.empty:
        validate_purged_walk_forward_splits(splits, primary_horizon_days=primary_horizon_days)
        split_lookup = {
            str(row["split_id"]): row for row in splits.to_dict("records") if row.get("split_id") is not None
        }
        if {"split_memberships_json", "label_end_date"}.issubset(panel.columns):
            for row in panel.to_dict("records"):
                try:
                    memberships = json.loads(str(row.get("split_memberships_json") or "[]"))
                except json.JSONDecodeError as exc:
                    raise ExpertPanelError("split_memberships_json is not valid JSON") from exc
                if not memberships:
                    continue
                label_end = pd.Timestamp(row["label_end_date"])
                date = pd.Timestamp(row["date"])
                for membership in memberships:
                    split = split_lookup.get(str(membership.get("split_id")))
                    role = str(membership.get("role") or "")
                    if split is None or role not in {"train", "validation", "test"}:
                        raise ExpertPanelError("split membership references an unknown split or role")
                    start = pd.Timestamp(split[f"{role}_start"])
                    end = pd.Timestamp(split[f"{role}_end"])
                    if not (start <= date <= end and label_end <= end):
                        raise ExpertPanelError("split membership crosses its label boundary")
        for split in splits.to_dict("records"):
            train_end = pd.Timestamp(split["train_end"])
            validation_start = pd.Timestamp(split["validation_start"])
            test_start = pd.Timestamp(split["test_start"])
            if not (validation_start > train_end and test_start > validation_start):
                raise ExpertPanelError(f"split {split.get('split_id')} leaks across boundaries")


def _attach_split_memberships(
    panel: pd.DataFrame,
    splits: pd.DataFrame,
    *,
    horizon_days: int,
) -> pd.DataFrame:
    out = panel.copy()
    out["label_end_date"] = (
        out.sort_values(["symbol", "expert_id", "date"])
        .groupby(["symbol", "expert_id"], sort=False)["date"]
        .shift(-int(horizon_days))
    )
    memberships: list[str] = []
    for row in out.itertuples(index=False):
        roles: list[dict[str, str]] = []
        date = pd.Timestamp(row.date)
        label_end = getattr(row, "label_end_date")
        label_valid = pd.notna(getattr(row, "future_utility")) and pd.notna(label_end)
        if label_valid:
            label_end = pd.Timestamp(label_end)
            for split in splits.to_dict("records"):
                for role, start_key, end_key in (
                    ("train", "train_start", "train_end"),
                    ("validation", "validation_start", "validation_end"),
                    ("test", "test_start", "test_end"),
                ):
                    start = pd.Timestamp(split[start_key])
                    end = pd.Timestamp(split[end_key])
                    if start <= date <= end and label_end <= end:
                        roles.append({"split_id": str(split["split_id"]), "role": role})
        memberships.append(_json_dump(roles))
    out["split_memberships_json"] = memberships
    return out


def _load_price_context(path_value: Any, dates: pd.DatetimeIndex) -> pd.DataFrame:
    if path_value is None:
        return pd.DataFrame(columns=["date"])
    path = Path(str(path_value))
    if not path.is_file():
        return pd.DataFrame(columns=["date"])
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError):
        return pd.DataFrame(columns=["date"])
    if "date" not in frame.columns:
        return pd.DataFrame(columns=["date"])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.loc[frame["date"].notna()].sort_values("date").drop_duplicates("date", keep="last")
    if frame.empty:
        return pd.DataFrame(columns=["date"])
    close_column = next((column for column in ("close", "adj_close", "收盘") if column in frame.columns), None)
    volume_column = next((column for column in ("volume", "成交量") if column in frame.columns), None)
    if close_column is not None:
        close = pd.to_numeric(frame[close_column], errors="coerce")
        returns = close.pct_change()
        frame["asset_return_1"] = returns
        frame["asset_trend_20"] = close.pct_change(20)
        frame["asset_volatility_20"] = returns.rolling(20, min_periods=1).std(ddof=0)
        if volume_column is not None:
            volume = pd.to_numeric(frame[volume_column], errors="coerce")
            frame["liquidity_20"] = (close * volume).rolling(20, min_periods=1).mean()
    keep = [
        "date",
        "asset_return_1",
        "asset_trend_20",
        "asset_volatility_20",
        "liquidity_20",
    ]
    keep = [column for column in keep if column in frame.columns]
    return frame[keep].loc[frame["date"].isin(dates)].copy()


def _load_news_context(path_value: str | Path | None, panel_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Load news only from a strictly earlier completed trading date."""

    if path_value is None:
        return pd.DataFrame(columns=["date", "symbol"])
    path = Path(path_value)
    if not path.is_file():
        raise ExpertPanelError(f"news factor file does not exist: {path}")
    frame = _read_csv(path, required=("date",))
    frame["news_source_date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.loc[frame["news_source_date"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["date", "symbol"])
    if "symbol" not in frame.columns:
        frame["symbol"] = "__MARKET__"
    frame["symbol"] = frame["symbol"].astype(str)
    feature_columns = [
        column
        for column in ("factor_score", "fused_factor_score", "news_delta", "news_gate", "news_residual")
        if column in frame.columns
    ]
    if not feature_columns:
        raise ExpertPanelError("news factor file contains no supported factor columns")
    # ``searchsorted(..., side='left')`` guarantees source_date < panel date.
    panel_date_values = np.asarray(panel_dates.view("int64"))
    output_rows: list[pd.DataFrame] = []
    for symbol, group in frame.groupby("symbol", sort=False):
        group = group.sort_values("news_source_date").drop_duplicates("news_source_date", keep="last")
        source_values = np.asarray(group["news_source_date"].array.view("int64"))
        positions = np.searchsorted(source_values, panel_date_values, side="left") - 1
        valid = positions >= 0
        if not valid.any():
            continue
        selected = group.iloc[np.maximum(positions, 0)].copy()
        selected["date"] = panel_dates
        selected.loc[~valid, feature_columns] = np.nan
        selected.loc[~valid, "news_source_date"] = pd.NaT
        selected["symbol"] = symbol
        selected = selected[["date", "symbol", "news_source_date", *feature_columns]]
        output_rows.append(selected)
    if not output_rows:
        return pd.DataFrame(columns=["date", "symbol"])
    result = pd.concat(output_rows, ignore_index=True)
    for column in feature_columns:
        result[f"news_{column}_lag1"] = pd.to_numeric(result[column], errors="coerce")
    return result[["date", "symbol", "news_source_date", *[f"news_{column}_lag1" for column in feature_columns]]]


def _available_records(source_dir: Path, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    runs_path = source_dir / "runs.csv"
    if not runs_path.is_file():
        raise ExpertPanelError(f"full-run runs.csv is missing: {runs_path}")
    records = _read_csv(runs_path)
    required = {"symbol", "model_id", "window_kind", "status"}
    missing = required - set(records.columns)
    if missing:
        raise ExpertPanelError(f"runs.csv is missing Phase-B columns: {sorted(missing)}")
    main = records.loc[records["window_kind"].astype(str).eq("main")].copy()
    stocks_path = source_dir / "stocks.csv"
    stocks = _read_csv(stocks_path) if stocks_path.is_file() else pd.DataFrame()
    if "symbol" in stocks.columns:
        symbols = stocks["symbol"].astype(str).str.strip()
    else:
        symbols = main["symbol"].astype(str).str.strip()
    symbols = pd.DataFrame({"symbol": sorted({value for value in symbols if value})})
    if symbols.empty:
        raise ExpertPanelError("full-run has no main-window symbols")
    return main, symbols


def _expert_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    specs = []
    for raw in config.get("experts", []):
        if not isinstance(raw, dict):
            continue
        specs.append(
            {
                "expert_id": str(raw.get("expert_id") or ""),
                "source_model_id": raw.get("source_model_id"),
                "availability": str(raw.get("availability", "required")),
                "unavailable_reason": raw.get("unavailable_reason"),
            }
        )
    if not specs:
        raise ExpertPanelError("Phase-A config contains no experts")
    return specs


def _main_dates_for_symbols(
    records: pd.DataFrame,
    *,
    source_dir: Path,
    symbols: list[str],
    specs: list[dict[str, Any]],
) -> tuple[dict[str, pd.DatetimeIndex], dict[tuple[str, str], tuple[pd.DataFrame, Path]]]:
    dates: dict[str, set[pd.Timestamp]] = {symbol: set() for symbol in symbols}
    loaded: dict[tuple[str, str], tuple[pd.DataFrame, Path]] = {}
    for spec in specs:
        expert_id = spec["expert_id"]
        source_model_id = spec.get("source_model_id")
        if expert_id == "cash" or spec["availability"] != "required" or not source_model_id:
            continue
        selected = records.loc[
            records["model_id"].astype(str).eq(str(source_model_id))
            & records["symbol"].astype(str).isin(symbols)
        ]
        for symbol in symbols:
            rows = selected.loc[selected["symbol"].astype(str).eq(symbol)]
            if len(rows) > 1:
                raise ExpertPanelError(f"duplicate main-window records for {symbol}/{source_model_id}")
            if rows.empty or str(rows.iloc[0].get("status")) not in READY_STATUSES:
                continue
            record = rows.iloc[0]
            try:
                artifact, artifact_path = _read_expert_artifact(record, source_dir)
            except (ExpertPanelError, MoEBaselineError):
                continue
            loaded[(symbol, expert_id)] = (artifact, artifact_path)
            dates[symbol].update(pd.Timestamp(value) for value in artifact["date"].tolist())
    return {symbol: _clean_dates(values) for symbol, values in dates.items()}, loaded


def _base_market_context(
    panel: pd.DataFrame,
    *,
    records: pd.DataFrame,
    source_dir: Path,
) -> pd.DataFrame:
    """Build context using only same-date or trailing source data."""

    rows: list[pd.DataFrame] = []
    for symbol, symbol_panel in panel.groupby("symbol", sort=False):
        dates = _clean_dates(symbol_panel["date"])
        if dates.empty:
            continue
        symbol_records = records.loc[records["symbol"].astype(str).eq(str(symbol))]
        context = pd.DataFrame({"date": dates})
        benchmark_frames: list[pd.DataFrame] = []
        price_contexts: list[pd.DataFrame] = []
        for record in symbol_records.itertuples(index=False):
            record_series = pd.Series(record._asdict())
            path_value = record_series.get("benchmark_returns_path")
            benchmark_path = _resolve_optional_path(path_value, source_dir)
            if benchmark_path is not None:
                benchmark = _coerce_artifact_dates(_read_csv(benchmark_path, required=("date",)))
                if "benchmark_return" in benchmark.columns:
                    benchmark_frames.append(benchmark[["date", "benchmark_return"]])
            price_context = _load_price_context(record_series.get("data_path"), dates)
            if not price_context.empty:
                price_contexts.append(price_context)
        if benchmark_frames:
            benchmark = pd.concat(benchmark_frames, ignore_index=True).groupby("date", as_index=False).first()
            context = context.merge(benchmark, on="date", how="left")
        if price_contexts:
            price = pd.concat(price_contexts, ignore_index=True).groupby("date", as_index=False).first()
            context = context.merge(price, on="date", how="left")
        if "benchmark_return" in context.columns:
            market_return = pd.to_numeric(context["benchmark_return"], errors="coerce")
            context["market_return_1"] = market_return
            context["market_return_5"] = _rolling_compound(market_return, 5)
            context["market_return_20"] = _rolling_compound(market_return, 20)
            context["market_volatility_20"] = market_return.rolling(20, min_periods=1).std(ddof=0)
            context["market_trend_20"] = market_return.rolling(20, min_periods=1).mean()
        context["symbol"] = str(symbol)
        rows.append(context)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "symbol"])


def _peer_correlations(panel: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for symbol, group in panel.groupby("symbol", sort=False):
        pivot = group.pivot(index="date", columns="expert_id", values="strategy_return").sort_index()
        result = []
        for expert_id in pivot.columns:
            peers = pivot.drop(columns=[expert_id]).mean(axis=1)
            correlation = pivot[expert_id].rolling(window, min_periods=3).corr(peers)
            result.append(
                pd.DataFrame(
                    {
                        "date": correlation.index,
                        "symbol": str(symbol),
                        "expert_id": str(expert_id),
                        "expert_peer_correlation_20": correlation.to_numpy(),
                    }
                )
            )
        if result:
            rows.append(pd.concat(result, ignore_index=True))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_expert_day_panel(
    config: dict[str, Any] | str | Path,
    *,
    repo_root: str | Path,
    source_dir: str | Path | None = None,
    news_factor_path: str | Path | None = None,
    market_context_path: str | Path | None = None,
    primary_horizon_days: int = PRIMARY_HORIZON_DAYS,
    lambda_downside: float = DEFAULT_LAMBDA_DOWNSIDE,
    lambda_turnover: float = DEFAULT_LAMBDA_TURNOVER,
    n_splits: int = DEFAULT_N_SPLITS,
    min_train_days: int | None = None,
    validation_days: int | None = None,
    test_days: int | None = None,
    step_days: int | None = None,
    embargo_days: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Build ``date × symbol × market × expert_id`` and its split/quality data."""

    root = Path(repo_root).resolve()
    if isinstance(config, (str, Path)):
        config = load_moe_baseline_config(config)
    market = _canonical_market(config.get("market"))
    source = Path(source_dir) if source_dir is not None else root / str(config["source_runs"]["full_run"]["output_dir"])
    source = source.resolve()
    records, symbols_frame = _available_records(source, config)
    symbols = symbols_frame["symbol"].astype(str).tolist()
    specs = _expert_specs(config)
    symbol_dates, loaded = _main_dates_for_symbols(records, source_dir=source, symbols=symbols, specs=specs)
    if not any(len(values) for values in symbol_dates.values()):
        raise ExpertPanelError("full-run contains no readable expert return artifacts")

    source_manifest_path = source / "data_manifest.json"
    source_manifest_sha = _sha256_file(source_manifest_path) if source_manifest_path.is_file() else None
    source_manifest: dict[str, Any] = {}
    if source_manifest_path.is_file():
        try:
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExpertPanelError(f"invalid full-run data_manifest.json: {source_manifest_path}") from exc
    source_run_id = source_manifest.get("run_id")
    source_code_version = source_manifest.get("code_version")
    source_data_sha = (source_manifest.get("data") or {}).get("snapshot_sha256")

    rows: list[pd.DataFrame] = []
    for spec in specs:
        expert_id = spec["expert_id"]
        model_id = spec.get("source_model_id")
        availability = spec["availability"]
        explicit_reason = str(spec.get("unavailable_reason") or "").strip() or None
        for symbol in symbols:
            dates = symbol_dates.get(symbol, pd.DatetimeIndex([]))
            if len(dates) == 0:
                continue
            key = (symbol, expert_id)
            artifact_entry = loaded.get(key)
            if expert_id == "cash":
                frame = pd.DataFrame({"date": dates, "strategy_return": 0.0, "target_position": 0.0, "turnover": 0.0})
                artifact_path = None
                status = "available"
                unavailable_reason = None
            elif availability != "required":
                frame = pd.DataFrame({"date": dates})
                artifact_path = None
                status = "unavailable"
                unavailable_reason = explicit_reason or "expert is marked known_unavailable in the Phase-A contract"
            elif artifact_entry is None:
                frame = pd.DataFrame({"date": dates})
                artifact_path = None
                status = "unavailable"
                unavailable_reason = "required expert artifact missing, failed, or has no valid returns"
            else:
                frame, artifact_path = artifact_entry
                status = "available"
                unavailable_reason = None

            # Reindex every expert to the symbol's union trading calendar.
            # Missing dates remain explicit unavailable rows; labels must not
            # jump over a missing observation and accidentally shorten a
            # future window.
            if status == "available":
                source_frame = frame.copy()
                frame = pd.DataFrame({"date": dates}).merge(
                    source_frame,
                    on="date",
                    how="left",
                    suffixes=("", "_source"),
                )
            else:
                frame = pd.DataFrame({"date": dates})
            frame = _compute_expert_features(frame, tuple(sorted(set(DEFAULT_FEATURE_WINDOWS))))
            frame = compute_future_utility(
                frame,
                horizon_days=primary_horizon_days,
                lambda_downside=lambda_downside,
                lambda_turnover=lambda_turnover,
            )
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
            row_available = (
                frame["strategy_return"].notna()
                if status == "available"
                else pd.Series(False, index=frame.index)
            )
            if expert_id != "cash" and (~row_available).any():
                invalid_columns = [
                    column
                    for column in frame.columns
                    if column not in {"date"}
                ]
                frame.loc[~row_available, invalid_columns] = np.nan
            if status == "unavailable":
                # Keep an auditable identity row for every date, but never make
                # a failed expert look like a zero-return or winning expert.
                for column in [column for column in frame.columns if column not in {"date"}]:
                    if column not in {"strategy_return", "target_position", "turnover"}:
                        frame[column] = np.nan
                frame["strategy_return"] = np.nan
                frame["target_position"] = np.nan
                frame["turnover"] = np.nan
            frame["symbol"] = symbol
            frame["market"] = market
            frame["expert_id"] = expert_id
            frame["source_model_id"] = model_id
            frame["expert_status"] = (
                "available"
                if expert_id == "cash"
                else np.where(row_available, "available", "unavailable")
            )
            frame["unavailable_reason"] = (
                None
                if expert_id == "cash"
                else np.where(
                    row_available,
                    None,
                    unavailable_reason or "required expert artifact is missing for this trading date",
                )
            )
            frame["position_source"] = (
                "cash"
                if expert_id == "cash"
                else np.where(
                    frame["target_position"].notna(),
                    frame.get("position_source", pd.Series("source_target_position", index=frame.index)).fillna(
                        "source_target_position"
                    ),
                    None,
                )
            )
            frame["source_run_id"] = source_run_id
            frame["source_code_version"] = source_code_version
            frame["source_data_snapshot_sha256"] = source_data_sha
            frame["source_manifest_sha256"] = source_manifest_sha
            frame["source_window_id"] = "main"
            frame["source_artifact_path"] = str(artifact_path) if artifact_path is not None else None
            frame["source_artifact_sha256"] = (
                _sha256_file(artifact_path)
                if artifact_path is not None and artifact_path.is_file()
                else None
            )
            frame["return_field"] = "strategy_return"
            frame["cost_treatment"] = "source_net_no_recharge"
            rows.append(frame)

    panel = pd.concat(rows, ignore_index=True, sort=False)
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    panel = panel.sort_values(["date", "symbol", "expert_id"]).reset_index(drop=True)

    context = _base_market_context(panel, records=records, source_dir=source)
    if not context.empty:
        panel = panel.merge(context, on=["symbol", "date"], how="left")
    if market_context_path is not None:
        context_path = Path(market_context_path)
        if not context_path.is_file():
            raise ExpertPanelError(f"market context file does not exist: {context_path}")
        external = _read_csv(context_path, required=("date",))
        external["date"] = pd.to_datetime(external["date"], errors="coerce").dt.normalize()
        if "symbol" not in external.columns:
            external["symbol"] = "__MARKET__"
        external = external.loc[external["date"].notna()].copy()
        external = external.drop_duplicates(["date", "symbol"], keep="last")
        external_columns = [column for column in external.columns if column not in {"date", "symbol"}]
        panel = panel.merge(
            external[["date", "symbol", *external_columns]],
            on=["date", "symbol"],
            how="left",
            suffixes=("", "_external"),
        )

    correlations = _peer_correlations(panel)
    if not correlations.empty:
        panel = panel.merge(correlations, on=["date", "symbol", "expert_id"], how="left")

    if news_factor_path is not None:
        news = _load_news_context(news_factor_path, _clean_dates(panel["date"]))
        if not news.empty:
            panel = panel.merge(news, on=["date", "symbol"], how="left")

    # A compact feature list is persisted per row so downstream training code
    # cannot accidentally include future labels or lineage metadata.
    excluded = set(PANEL_KEY_COLUMNS) | set(LABEL_COLUMNS) | set(LINEAGE_COLUMNS) | {
        "market",
        "expert_status",
        "unavailable_reason",
        "position_source",
        "source_model_id",
        "source_window_id",
        "source_artifact_path",
        "source_artifact_sha256",
        "news_source_date",
        "return_field",
        "cost_treatment",
        "label_horizon_days",
        "label_end_date",
        "split_memberships_json",
    }
    feature_columns = [
        column
        for column in panel.columns
        if column not in excluded and not str(column).startswith("future_") and column != "feature_columns_json"
    ]
    panel["feature_columns_json"] = _json_dump(feature_columns)
    panel["label_columns_json"] = _json_dump(list(LABEL_COLUMNS))

    dates = _clean_dates(panel["date"])
    splits = build_purged_walk_forward_splits(
        dates,
        primary_horizon_days=primary_horizon_days,
        n_splits=n_splits,
        min_train_days=min_train_days,
        validation_days=validation_days,
        test_days=test_days,
        step_days=step_days,
        embargo_days=embargo_days,
    )
    panel = _attach_split_memberships(panel, splits, horizon_days=primary_horizon_days)
    panel["feature_columns_json"] = _json_dump(feature_columns)
    validate_panel_no_leakage(panel, splits=splits, primary_horizon_days=primary_horizon_days)

    status_counts = panel["expert_status"].value_counts(dropna=False).to_dict()
    coverage = (
        panel.groupby("expert_id", sort=True)
        .agg(
            row_count=("expert_id", "size"),
            available_rows=("expert_status", lambda values: int((values == "available").sum())),
            valid_label_rows=(
                "future_utility",
                lambda values: int(pd.to_numeric(values, errors="coerce").notna().sum()),
            ),
            symbol_count=("symbol", "nunique"),
        )
        .reset_index()
    )
    coverage["coverage_rate"] = coverage["available_rows"] / coverage["row_count"].clip(lower=1)
    quality = {
        "row_count": int(len(panel)),
        "symbol_count": int(panel["symbol"].nunique()),
        "expert_count": int(panel["expert_id"].nunique()),
        "date_count": int(panel["date"].nunique()),
        "available_row_count": int((panel["expert_status"] == "available").sum()),
        "unavailable_row_count": int((panel["expert_status"] == "unavailable").sum()),
        "status_counts": {str(key): int(value) for key, value in status_counts.items()},
        "market_distribution": {
            str(key): int(value) for key, value in panel["market"].value_counts(dropna=False).items()
        },
        "state_distribution": {
            str(column): {
                str(key): int(value)
                for key, value in panel[column].value_counts(dropna=False).items()
            }
            for column in panel.columns
            if str(column).startswith(("state_", "regime_", "adaptive_"))
        },
        "label_valid_rate": float(panel["future_utility"].notna().mean()) if len(panel) else 0.0,
        "label_distribution": {
            column: {
                "count": int(pd.to_numeric(panel[column], errors="coerce").notna().sum()),
                "mean": _finite_float(pd.to_numeric(panel[column], errors="coerce").mean()),
                "std": _finite_float(pd.to_numeric(panel[column], errors="coerce").std(ddof=0)),
                "min": _finite_float(pd.to_numeric(panel[column], errors="coerce").min()),
                "max": _finite_float(pd.to_numeric(panel[column], errors="coerce").max()),
            }
            for column in LABEL_COLUMNS
        },
        "expert_coverage": coverage.to_dict("records"),
        "split_count": int(len(splits)),
        "missing_feature_rate": {
            column: float(panel[column].isna().mean())
            for column in feature_columns
            if column in panel.columns
        },
    }
    metadata = {
        "schema_version": PHASE_B_SCHEMA_VERSION,
        "phase": "B",
        "status": "ready" if len(splits) else "degraded",
        "market": market,
        "source_run_id": source_run_id,
        "source_manifest_sha256": source_manifest_sha,
        "feature_columns": feature_columns,
        "label_columns": list(LABEL_COLUMNS),
        "lineage_columns": list(LINEAGE_COLUMNS),
        "primary_horizon_days": int(primary_horizon_days),
        "lambda_downside": float(lambda_downside),
        "lambda_turnover": float(lambda_turnover),
        "cost_treatment": "source_net_no_recharge",
        "quality": quality,
    }
    return panel, splits, metadata, quality


def _pending_panel(
    config: dict[str, Any],
    reason: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    market = _canonical_market(config.get("market"))
    panel = pd.DataFrame(columns=[*PANEL_KEY_COLUMNS, "expert_status", "unavailable_reason", *LABEL_COLUMNS])
    splits = pd.DataFrame()
    quality = {
        "row_count": 0,
        "symbol_count": 0,
        "expert_count": len(config.get("experts", [])),
        "date_count": 0,
        "available_row_count": 0,
        "unavailable_row_count": 0,
        "status_counts": {"unavailable": 0},
        "label_valid_rate": 0.0,
        "reason": reason,
    }
    metadata = {
        "schema_version": PHASE_B_SCHEMA_VERSION,
        "phase": "B",
        "status": "pending",
        "market": market,
        "reason": reason,
        "cost_treatment": "source_net_no_recharge",
        "feature_columns": [],
        "label_columns": list(LABEL_COLUMNS),
        "lineage_columns": list(LINEAGE_COLUMNS),
        "quality": quality,
    }
    return panel, splits, metadata, quality


def materialize_expert_panel(
    config_path: str | Path,
    *,
    repo_root: str | Path,
    output_dir: str | Path | None = None,
    allow_pending: bool = False,
    news_factor_path: str | Path | None = None,
    market_context_path: str | Path | None = None,
    primary_horizon_days: int = PRIMARY_HORIZON_DAYS,
    lambda_downside: float = DEFAULT_LAMBDA_DOWNSIDE,
    lambda_turnover: float = DEFAULT_LAMBDA_TURNOVER,
    n_splits: int = DEFAULT_N_SPLITS,
    min_train_days: int | None = None,
    validation_days: int | None = None,
    test_days: int | None = None,
    step_days: int | None = None,
    embargo_days: int | None = None,
) -> dict[str, Path]:
    """Materialize Phase-B artifacts for one market-specific Phase-A config."""

    root = Path(repo_root).resolve()
    config_file = Path(config_path).resolve()
    config = load_moe_baseline_config(config_file)
    frozen_primary_horizon = int(config.get("horizons", {}).get("primary_days", PRIMARY_HORIZON_DAYS))
    if int(primary_horizon_days) != frozen_primary_horizon:
        raise ExpertPanelError(
            f"Phase-B primary horizon is frozen at {frozen_primary_horizon} trading days; "
            "use the direct builder for isolated horizon ablations."
        )
    phase_a_manifest = build_phase_a_manifest(config_file, repo_root=root)
    source_issues = [issue for source in phase_a_manifest["sources"] for issue in source["issues"]]
    target = (
        Path(output_dir)
        if output_dir is not None
        else root / "model-test" / "outputs" / str(config["output_subdir"])
    )
    existing_phase_a_manifest = target / "data_manifest.json"
    if existing_phase_a_manifest.is_file():
        try:
            previous = json.loads(existing_phase_a_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            source_issues.append(f"existing Phase-A manifest is unreadable: {existing_phase_a_manifest}")
        else:
            if previous.get("phase") == "A":
                if previous.get("phase_a_config_sha256") != _sha256_file(config_file):
                    source_issues.append("existing Phase-A manifest config fingerprint differs from the requested config")
                if previous.get("source_fingerprint_sha256") != phase_a_manifest.get("source_fingerprint_sha256"):
                    source_issues.append("existing Phase-A manifest source fingerprint differs from current source outputs")
    if source_issues and not allow_pending:
        raise ExpertPanelError("Phase-B source validation failed: " + "; ".join(source_issues))

    if source_issues:
        panel, splits, metadata, quality = _pending_panel(config, "; ".join(source_issues))
    else:
        source = next(item for item in phase_a_manifest["sources"] if item["source_name"] == "full_run")
        try:
            panel, splits, metadata, quality = build_expert_day_panel(
                config,
                repo_root=root,
                source_dir=root / source["output_dir"],
                news_factor_path=news_factor_path,
                market_context_path=market_context_path,
                primary_horizon_days=primary_horizon_days,
                lambda_downside=lambda_downside,
                lambda_turnover=lambda_turnover,
                n_splits=n_splits,
                min_train_days=min_train_days,
                validation_days=validation_days,
                test_days=test_days,
                step_days=step_days,
                embargo_days=embargo_days,
            )
        except ExpertPanelError as exc:
            if not allow_pending:
                raise
            panel, splits, metadata, quality = _pending_panel(config, str(exc))

    target.mkdir(parents=True, exist_ok=True)
    panel_path = target / "expert_day_panel.parquet"
    splits_path = target / "expert_panel_walk_forward_splits.csv"
    quality_path = target / "expert_panel_quality.json"
    quality_md_path = target / "expert_panel_quality.md"
    manifest_path = target / "expert_panel_manifest.json"
    panel.to_parquet(panel_path, index=False)
    splits.to_csv(splits_path, index=False)
    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        "# Phase-B Expert Panel Quality Report",
        "",
        f"- Status: `{metadata.get('status', 'unknown')}`",
        f"- Market: `{metadata.get('market', config.get('market'))}`",
        f"- Rows: `{quality.get('row_count', 0)}`; "
        f"symbols: `{quality.get('symbol_count', 0)}`; "
        f"experts: `{quality.get('expert_count', 0)}`",
        f"- Valid future labels: `{float(quality.get('label_valid_rate', 0.0)):.2%}`",
        f"- Purged walk-forward splits: `{quality.get('split_count', 0)}`",
        "",
        "## Expert coverage",
        "",
    ]
    for row in quality.get("expert_coverage", []):
        lines.append(
            f"- `{row.get('expert_id')}`: {row.get('available_rows', 0)}/{row.get('row_count', 0)} available "
            f"({float(row.get('coverage_rate', 0.0)):.2%}), valid labels `{row.get('valid_label_rows', 0)}`"
        )
    if quality.get("reason"):
        lines.extend(["", f"Reason: {quality['reason']}"])
    quality_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    full_source_lock = next(
        (item for item in phase_a_manifest.get("sources", []) if item.get("source_name") == "full_run"),
        {},
    )
    manifest = {
        "schema_version": PHASE_B_SCHEMA_VERSION,
        "phase": "B",
        "status": metadata.get("status", "ready"),
        "name": config.get("name"),
        "market": _canonical_market(config.get("market")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_code_version": _git_code_version(root),
        "phase_a_config_path": config_file.relative_to(root).as_posix(),
        "phase_a_config_sha256": _sha256_file(config_file),
        "phase_a_source_fingerprint_sha256": phase_a_manifest.get("source_fingerprint_sha256"),
        "source_fingerprint_sha256": phase_a_manifest.get("source_fingerprint_sha256"),
        "phase_a_manifest_status": phase_a_manifest.get("status"),
        "source_runs": phase_a_manifest.get("sources", []),
        "random_seed": int(config.get("random_seed", 42)),
        "source_run_id": metadata.get("source_run_id"),
        "source_code_version": full_source_lock.get("code_version"),
        "data_snapshot_sha256": full_source_lock.get("data_snapshot_sha256"),
        "source_manifest_sha256": metadata.get("source_manifest_sha256"),
        "primary_horizon_days": int(primary_horizon_days),
        "ablation_horizons": config.get("horizons", {}).get("ablation_days", [5, 60]),
        "lambda_downside": float(lambda_downside),
        "lambda_turnover": float(lambda_turnover),
        "returns": config.get("returns", {}),
        "execution": config.get("execution", {}),
        "cost_treatment": "source_net_no_recharge",
        "split_policy": {
            "method": "purged_walk_forward",
            "purge_days": int(primary_horizon_days),
            "embargo_days": max(
                int(primary_horizon_days),
                int(embargo_days if embargo_days is not None else primary_horizon_days),
            ),
            "n_splits_requested": int(n_splits),
            "n_splits_emitted": int(len(splits)),
            "min_train_days": min_train_days,
            "validation_days": validation_days or primary_horizon_days,
            "test_days": test_days or primary_horizon_days,
            "step_days": step_days or test_days or primary_horizon_days,
        },
        "feature_columns": metadata.get("feature_columns", []),
        "label_columns": metadata.get("label_columns", list(LABEL_COLUMNS)),
        "lineage_columns": metadata.get("lineage_columns", list(LINEAGE_COLUMNS)),
        "expert_pool": config.get("experts", []),
        "quality": quality,
        "artifacts": {
            "expert_day_panel": {
                "path": panel_path.name,
                "sha256": _sha256_file(panel_path),
                "size_bytes": panel_path.stat().st_size,
            },
            "walk_forward_splits": {
                "path": splits_path.name,
                "sha256": _sha256_file(splits_path),
                "size_bytes": splits_path.stat().st_size,
            },
            "quality_json": {"path": quality_path.name, "sha256": _sha256_file(quality_path)},
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "expert_day_panel": panel_path,
        "walk_forward_splits": splits_path,
        "quality": quality_path,
        "quality_markdown": quality_md_path,
        "manifest": manifest_path,
    }


# Friendly aliases for callers that used the Phase-B language in notebooks.
build_panel = build_expert_day_panel
build_walk_forward_splits = build_purged_walk_forward_splits
prepare_expert_panel = materialize_expert_panel


__all__ = [
    "ExpertPanelError",
    "LABEL_COLUMNS",
    "LINEAGE_COLUMNS",
    "PANEL_KEY_COLUMNS",
    "build_expert_day_panel",
    "build_panel",
    "build_purged_walk_forward_splits",
    "build_walk_forward_splits",
    "compute_future_utility",
    "materialize_expert_panel",
    "prepare_expert_panel",
    "validate_panel_no_leakage",
    "validate_purged_walk_forward_splits",
]
