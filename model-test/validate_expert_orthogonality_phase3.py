"""Run the research-only Phase 3 heterogeneous expert-pool validation."""

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

from core.expert_pool_v2 import ExpertPoolV2
from core.factor_pipeline import FactorPipeline
from core.macro_factors import MacroFactors


def _semantic_source_fingerprint(source: dict[str, Any]) -> str:
    data = source.get("data") or {}
    universe = source.get("universe") or {}
    payload = {
        "market": source.get("market"),
        "start": data.get("start"),
        "end": data.get("end"),
        "adjustment": data.get("adjustment"),
        "symbols": universe.get("symbols"),
        "selection_rationale": universe.get("selection_rationale"),
        "replaced_symbols": universe.get("replaced_symbols", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _universe_fingerprint(symbols: list[str]) -> str:
    payload = json.dumps(symbols, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(value: str) -> Path:
    path = Path(value)
    resolved = path if path.is_absolute() else REPO_ROOT / path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise ValueError(f"path escapes repository: {resolved}")
    return resolved


def _validate_snapshot_lock(
    snapshot_dir: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Verify every frozen CSV against the source manifest before reading it."""
    entries = (manifest.get("universe") or {}).get("files")
    recorded = str((manifest.get("data") or {}).get("snapshot_sha256") or "")
    if not recorded or not isinstance(entries, list) or not entries:
        raise ValueError("frozen data manifest lacks snapshot hash or file entries")
    expected_names: set[str] = set()
    portable: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not str(entry.get("symbol") or "").strip():
            raise ValueError("invalid frozen snapshot manifest entry")
        symbol = str(entry["symbol"]).strip().upper()
        filename = f"{symbol}_daily.csv"
        if filename in expected_names:
            raise ValueError(f"duplicate frozen snapshot symbol: {symbol}")
        expected_names.add(filename)
        path = snapshot_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"frozen snapshot file not found: {path}")
        frame = pd.read_csv(path)
        required_columns = {"date", "open", "high", "low", "close", "volume"}
        missing_columns = required_columns - set(frame.columns)
        if missing_columns:
            raise ValueError(
                f"frozen snapshot missing columns for {symbol}: {', '.join(sorted(missing_columns))}"
            )
        dates = pd.to_datetime(frame["date"], errors="coerce")
        if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
            raise ValueError(f"frozen snapshot dates must be valid, unique, and sorted: {filename}")
        numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]].apply(
            pd.to_numeric, errors="coerce"
        )
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValueError(f"frozen snapshot contains non-finite OHLCV values: {filename}")
        if "symbol" in frame.columns and frame["symbol"].astype(str).ne(symbol).any():
            raise ValueError(f"frozen snapshot symbol column mismatch: {filename}")
        digest = _sha256(path)
        size = int(path.stat().st_size)
        if digest != str(entry.get("sha256") or "") or size != int(entry.get("size_bytes", -1)):
            raise ValueError(f"frozen snapshot hash/size mismatch: {filename}")
        portable.append({"symbol": symbol, "sha256": digest, "size_bytes": size})
    actual_names = {path.name for path in snapshot_dir.glob("*.csv") if path.is_file()}
    if actual_names != expected_names:
        raise ValueError("frozen snapshot contains missing or unmanifested CSV files")
    aggregate = hashlib.sha256(
        json.dumps(portable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if aggregate != recorded:
        raise ValueError("frozen snapshot aggregate SHA-256 mismatch")
    return {"snapshot_sha256": aggregate, "files": portable}


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("status") != "research_only" or config.get("market") != "US":
        raise ValueError("Phase 3 config must be US research_only")
    if int(config.get("random_seed", -1)) != 42:
        raise ValueError("random_seed must be 42")
    if config.get("execution", {}).get("cost_treatment") != "ohlcv_gross_charge_once":
        raise ValueError("Phase 3 requires ohlcv_gross_charge_once for OHLCV input")
    configured_experts = config.get("experts")
    expected_experts = [item.expert_id for item in ExpertPoolV2.definitions()]
    if configured_experts != expected_experts or len(set(configured_experts or [])) != len(expected_experts):
        raise ValueError(f"experts must exactly match ExpertPoolV2 definitions: {expected_experts}")
    acceptance = config.get("acceptance", {})
    required_acceptance = {
        "max_average_pairwise_spearman",
        "min_experts_sharpe_above",
        "min_experts_sharpe_count",
        "min_distinct_fold_winners",
        "composite_sharpe_improvement_over_phase2",
    }
    if not required_acceptance.issubset(acceptance):
        missing = sorted(required_acceptance - set(acceptance))
        raise ValueError(f"missing acceptance fields: {', '.join(missing)}")
    for key in required_acceptance:
        if not np.isfinite(float(acceptance[key])):
            raise ValueError(f"acceptance field must be finite: {key}")
    for key in ("min_experts_sharpe_count", "min_distinct_fold_winners"):
        if int(acceptance[key]) < 1:
            raise ValueError(f"acceptance field must be positive: {key}")
    source = config.get("source", {})
    date_start = pd.Timestamp(source.get("date_start", ""))
    date_end = pd.Timestamp(source.get("date_end", ""))
    if not date_start < date_end:
        raise ValueError("source date_start must be before date_end")
    if float(config.get("data_quality", {}).get("max_abs_close_return", 0.0)) <= 0:
        raise ValueError("data_quality.max_abs_close_return must be positive")
    data_manifest = _repo_path(source["data_manifest"])
    if not data_manifest.is_file():
        raise FileNotFoundError(f"data manifest not found: {data_manifest}")
    manifest = json.loads(data_manifest.read_text(encoding="utf-8"))
    source_manifest = _repo_path(source["source_manifest"])
    if not source_manifest.is_file():
        raise FileNotFoundError(f"source manifest not found: {source_manifest}")
    source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    expected_source_fingerprint = _semantic_source_fingerprint(source_payload)
    if (manifest.get("data") or {}).get("source_semantic_fingerprint") != expected_source_fingerprint:
        raise ValueError("frozen data manifest source semantic fingerprint mismatch")
    source_symbols = (source_payload.get("universe") or {}).get("symbols")
    manifest_universe = manifest.get("universe") or {}
    manifest_symbols = manifest_universe.get("symbols")
    if not isinstance(source_symbols, list) or manifest_symbols != source_symbols:
        raise ValueError("frozen data manifest universe does not match source manifest")
    if manifest_universe.get("fingerprint") != _universe_fingerprint(source_symbols):
        raise ValueError("frozen data manifest universe fingerprint mismatch")
    if (manifest.get("data") or {}).get("source_manifest_sha256") != _sha256(source_manifest):
        raise ValueError("frozen data manifest source hash mismatch")
    manifest_data = manifest.get("data", {})
    if manifest.get("market") != config.get("market"):
        raise ValueError("Phase 3 market must match the frozen data manifest")
    manifest_symbols = (manifest.get("universe") or {}).get("symbols")
    manifest_files = (manifest.get("universe") or {}).get("files")
    if not isinstance(manifest_symbols, list) or not isinstance(manifest_files, list):
        raise ValueError("frozen data manifest must contain universe symbols and files")
    if len(manifest_symbols) != int(source.get("required_universe", 0)) or len(manifest_files) != len(manifest_symbols):
        raise ValueError("frozen data manifest universe size does not match Phase 3 config")
    if manifest_data.get("start") != date_start.strftime("%Y-%m-%d") or manifest_data.get("end") != date_end.strftime("%Y-%m-%d"):
        raise ValueError("Phase 3 date window must match the frozen data manifest")
    if manifest_data.get("adjustment") != source.get("adjustment"):
        raise ValueError("Phase 3 adjustment must match the frozen data manifest")
    factor_source = _repo_path(config["factor_source"])
    if not factor_source.is_file():
        raise FileNotFoundError(f"factor source not found: {factor_source}")
    factor_payload = json.loads(factor_source.read_text(encoding="utf-8"))
    source_weights = factor_payload.get("bayesian_opt", {}).get("best_weights")
    expected_weights = {
        "mom_short_z": 1.1927024077349668,
        "rsi_z": 0.6774335748746589,
        "macd_z": -1.848279896441191,
        "vix_level": 0.4923060643659716,
        "volume_ratio_rank": 0.7149782039599426,
    }
    if source_weights != expected_weights:
        raise ValueError("factor source weights do not match the frozen Phase 2.5 values")
    interaction = factor_payload.get("interaction_test", {}).get("best_interaction", {})
    if (
        interaction.get("factor1") != "volume_ratio_rank"
        or interaction.get("factor2") != "mom_short_z"
        or float(interaction.get("best_weight", np.nan)) != -0.5
    ):
        raise ValueError("factor source interaction does not match the frozen Phase 2.5 value")
    macro_dir = _repo_path(config["source"]["macro_data_dir"])
    macro_manifest_path = _repo_path(config["source"]["macro_data_manifest"])
    if _sha256(macro_manifest_path) != config["source"]["macro_data_manifest_sha256"]:
        raise ValueError("macro data manifest hash does not match Phase 3 config")
    macro_manifest = json.loads(macro_manifest_path.read_text(encoding="utf-8"))
    if macro_manifest.get("data_kind") != "observed" or macro_manifest.get("synthetic_fallback") is not False:
        raise ValueError("Phase 3 requires observed macro data without synthetic fallback")
    artifacts = macro_manifest.get("artifacts") or {}
    for filename in ("vix_daily.parquet", "spy_daily.parquet"):
        artifact = artifacts.get(filename.removesuffix(".parquet"))
        path = macro_dir / filename
        if not path.is_file() or not isinstance(artifact, dict):
            raise FileNotFoundError(f"macro source not found or unmanifested: {path}")
        if _sha256(path) != artifact.get("sha256") or path.stat().st_size != int(artifact.get("size_bytes", -1)):
            raise ValueError(f"macro source hash/size mismatch: {filename}")
        macro_frame = pd.read_parquet(path)
        if "date" not in macro_frame.columns or macro_frame.empty:
            raise ValueError(f"macro source lacks usable dates: {filename}")
        macro_dates = pd.to_datetime(macro_frame["date"], errors="coerce")
        if macro_dates.isna().any() or macro_dates.duplicated().any():
            raise ValueError(f"macro source dates are invalid or duplicated: {filename}")
        actual_start = macro_dates.min().strftime("%Y-%m-%d")
        actual_end = macro_dates.max().strftime("%Y-%m-%d")
        if actual_start != artifact.get("date_start") or actual_end != artifact.get("date_end"):
            raise ValueError(f"macro source date range does not match manifest: {filename}")
        if pd.Timestamp(actual_start) > date_start or pd.Timestamp(actual_end) < date_end:
            raise ValueError(f"macro source does not cover Phase 3 window: {filename}")
    if config.get("data_quality", {}).get("fail_on_anomalies") is not True:
        raise ValueError("Phase 3 requires data_quality.fail_on_anomalies=true")
    return config


def _load_universe(config: dict[str, Any], symbols: list[str] | None) -> dict[str, pd.DataFrame]:
    directory = _repo_path(config["source"]["snapshot_dir"])
    if not directory.is_dir():
        raise FileNotFoundError(f"frozen snapshot directory not found: {directory}")
    data_manifest_path = _repo_path(config["source"]["data_manifest"])
    manifest = json.loads(data_manifest_path.read_text(encoding="utf-8"))
    snapshot_lock = _validate_snapshot_lock(directory, manifest)
    manifest_symbols = {entry["symbol"] for entry in snapshot_lock["files"]}
    if set(manifest_symbols) != {str(symbol).upper() for symbol in (manifest.get("universe") or {}).get("symbols", [])}:
        raise ValueError("snapshot files do not match frozen universe symbols")
    paths = sorted(directory.glob("*_daily.csv"))
    if symbols:
        wanted = {symbol.upper() for symbol in symbols}
        paths = [path for path in paths if path.stem.removesuffix("_daily").upper() in wanted]
        missing = wanted - {path.stem.removesuffix("_daily").upper() for path in paths}
        missing |= wanted - manifest_symbols
        if missing:
            raise ValueError(f"requested symbols not found: {', '.join(sorted(missing))}")
    required = int(config["source"]["required_universe"])
    if not symbols and len(paths) != required:
        raise ValueError(f"expected {required} frozen symbols, found {len(paths)}")
    universe: dict[str, pd.DataFrame] = {}
    required_columns = {"date", "open", "high", "low", "close", "volume"}
    for path in paths:
        symbol = path.stem.removesuffix("_daily").upper()
        frame = pd.read_csv(path)
        missing_columns = required_columns - set(frame.columns)
        if missing_columns:
            raise ValueError(f"missing columns for {symbol}: {', '.join(sorted(missing_columns))}")
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        date_start = pd.Timestamp(config["source"]["date_start"])
        date_end = pd.Timestamp(config["source"]["date_end"])
        frame = frame.loc[frame["date"].between(date_start, date_end)].copy()
        if frame.empty:
            raise ValueError(f"no rows inside configured date window for {symbol}")
        if frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
            raise ValueError(f"dates must be unique and sorted for {symbol}")
        numeric = frame.loc[:, ["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValueError(f"invalid OHLCV data for {symbol}")
        if (numeric.loc[:, ["open", "high", "low", "close"]] <= 0).any().any() or (numeric["volume"] < 0).any():
            raise ValueError(f"OHLCV values out of range for {symbol}")
        universe[symbol] = frame
    if not universe:
        raise ValueError("no symbols selected")
    return universe


def _audit_price_data(
    universe: dict[str, pd.DataFrame], config: dict[str, Any]
) -> pd.DataFrame:
    """Audit raw prices before factors or returns can turn bad data into evidence."""
    threshold = float(config["data_quality"]["max_abs_close_return"])
    rows: list[pd.DataFrame] = []
    for symbol, frame in universe.items():
        prices = pd.to_numeric(frame["close"], errors="coerce")
        close_return = prices.pct_change(fill_method=None)
        suspicious_scale = bool(
            prices.max() / prices.min() > 100_000.0
            or prices.max() > 100_000.0
        )
        anomaly = (
            (close_return <= -1.0)
            | (close_return > 1.0)
            | (close_return.abs() > threshold)
        )
        if suspicious_scale:
            anomaly = anomaly | True
        if not anomaly.any():
            continue
        previous = prices.shift(1)
        result = pd.DataFrame(
            {
                "symbol": symbol,
                "expert_id": pd.NA,
                "date": frame.loc[anomaly, "date"].to_numpy(),
                "close": prices.loc[anomaly].to_numpy(),
                "prev_close": previous.loc[anomaly].to_numpy(),
                "close_return": close_return.loc[anomaly].to_numpy(),
                "position": np.nan,
                "previous_position": np.nan,
                "turnover": np.nan,
                "gross_strategy_return": np.nan,
                "transaction_cost": np.nan,
                "strategy_return": np.nan,
                "price_scale_suspect": suspicious_scale,
            }
        )
        rows.append(result)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _apply_rebalance_cadence(
    position: pd.Series, dates: pd.Series, days: int, calendar: pd.DatetimeIndex
) -> pd.Series:
    """Hold targets on a shared date-based rebalance calendar."""
    if days < 1:
        raise ValueError("rebalance days must be positive")
    date_values = pd.to_datetime(dates, errors="raise")
    calendar = pd.DatetimeIndex(calendar).sort_values().unique()
    if len(calendar) == 0:
        raise ValueError("rebalance calendar must not be empty")
    date_positions = pd.Series(np.arange(len(calendar)), index=calendar)
    ordinal = date_values.map(date_positions)
    if ordinal.isna().any():
        raise ValueError("position dates must belong to the rebalance calendar")
    sampled = position.where((ordinal.to_numpy(dtype=int) % days) == 0)
    return sampled.ffill().fillna(0.0).rename(position.name)


def _strategy_returns(
    frame: pd.DataFrame, positions: pd.Series, config: dict[str, Any]
) -> pd.DataFrame:
    """Return point-in-time audit fields with explicit signed-position support."""
    close_returns = frame["close"].pct_change(fill_method=None).fillna(0.0)
    previous = positions.shift(1).fillna(0.0)
    turnover = positions.diff().abs().fillna(positions.abs())
    cost_treatment = config["execution"]["cost_treatment"]
    if cost_treatment != "ohlcv_gross_charge_once":
        raise ValueError(
            "OHLCV-derived returns require cost_treatment=ohlcv_gross_charge_once"
        )
    rate = (
        float(config["execution"]["commission_bps"])
        + float(config["execution"]["slippage_bps"])
    ) / 10000.0
    gross = previous * close_returns
    transaction_cost = turnover * rate
    net = gross - transaction_cost
    return pd.DataFrame(
        {
            "close": frame["close"].to_numpy(),
            "prev_close": frame["close"].shift(1).to_numpy(),
            "close_return": close_returns.to_numpy(),
            "position": positions.to_numpy(),
            "previous_position": previous.to_numpy(),
            "turnover": turnover.to_numpy(),
            "gross_strategy_return": gross.to_numpy(),
            "transaction_cost": transaction_cost.to_numpy(),
            "strategy_return": net.to_numpy(),
        },
        index=frame.index,
    )


def _build_oos_folds(dates: list[pd.Timestamp], embargo: int = 20) -> pd.DataFrame:
    """Build expanding train/validation/test folds with purge and embargo."""
    n_dates = len(dates)
    rows: list[dict[str, Any]] = []
    test_width = max(1, n_dates // 10)
    for fold_id, train_end_fraction in enumerate((0.5, 0.6, 0.7, 0.8), start=1):
        train_end = int(n_dates * train_end_fraction)
        validation_start = train_end + embargo
        validation_end = validation_start + test_width
        test_start = validation_end + embargo
        test_end = test_start + test_width
        if test_end > n_dates:
            continue
        rows.append(
            {
                "fold_id": f"fold_{fold_id:02d}",
                "train_start": dates[0],
                "train_end": dates[train_end - 1],
                "validation_start": dates[validation_start],
                "validation_end": dates[validation_end - 1],
                "test_start": dates[test_start],
                "test_end": dates[test_end - 1],
                "purge_days": embargo,
                "embargo_days": embargo,
            }
        )
    if len(rows) < 3:
        raise ValueError("insufficient dates to build three valid OOS folds")
    return pd.DataFrame(rows)


def _metrics(returns: pd.Series) -> dict[str, float]:
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "win_rate": 0.0}
    equity = np.cumprod(1.0 + values)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    std = float(values.std(ddof=1))
    return {
        "sharpe": float(values.mean() / std * np.sqrt(252.0)) if std > 1e-12 else 0.0,
        "total_return": float(equity[-1] - 1.0),
        "max_drawdown": float(drawdown.min()),
        "win_rate": float(np.mean(values > 0.0)),
    }


def aggregate_expert_returns(
    universe: dict[str, pd.DataFrame], config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pool = ExpertPoolV2(temperature=float(config.get("temperature", 1.0)))
    macro_dir = _repo_path(config["source"]["macro_data_dir"])
    pipeline = FactorPipeline(data_dir=macro_dir)
    warmed: dict[str, pd.DataFrame] = {}
    for symbol, raw in universe.items():
        frame = pipeline.compute_all_factors(raw.copy(), symbol)
        valid_mask = frame.loc[:, list(pool.required_columns())].apply(
            pd.to_numeric, errors="coerce"
        ).notna().all(axis=1)
        frame = frame.loc[valid_mask].reset_index(drop=True)
        if frame.empty:
            raise ValueError(f"no fully warmed factor rows for {symbol}")
        warmed[symbol] = frame

    relative_rows = pd.concat(
        [
            frame[["date", "rel_strength_spy"]].assign(symbol=symbol)
            for symbol, frame in warmed.items()
        ],
        ignore_index=True,
    )
    relative_rows["relative_rank"] = relative_rows.groupby("date")[
        "rel_strength_spy"
    ].rank(pct=True, method="average")
    relative_ranks = {
        symbol: group.set_index("date")["relative_rank"]
        for symbol, group in relative_rows.groupby("symbol")
    }

    shared_calendar = pd.DatetimeIndex(
        sorted({date for frame in warmed.values() for date in frame["date"]})
    )
    if len(shared_calendar) == 0:
        raise ValueError("no dates available for rebalance calendar")

    return_rows: list[pd.DataFrame] = []
    position_rows: list[pd.DataFrame] = []
    audit_rows: list[pd.DataFrame] = []
    definitions = {item.expert_id: item for item in pool.definitions()}
    for symbol, frame in warmed.items():
        signals = pool.get_all_expert_signals(
            frame, relative_rank=relative_ranks[symbol].reindex(frame["date"]).set_axis(frame.index)
        )
        for expert_id, raw_positions in signals.items():
            positions = _apply_rebalance_cadence(
                raw_positions, frame["date"], definitions[expert_id].rebalance_days, shared_calendar
            )
            execution = _strategy_returns(frame, positions, config)
            common = pd.DataFrame(
                {"date": frame["date"], "symbol": symbol, "expert_id": expert_id}
            )
            return_rows.append(
                common.assign(strategy_return=execution["strategy_return"].to_numpy())
            )
            position_rows.append(
                common.assign(
                    position=execution["position"].to_numpy(),
                    turnover=execution["turnover"].to_numpy(),
                )
            )
            audit_rows.append(common.join(execution.reset_index(drop=True)))
    daily = pd.concat(return_rows, ignore_index=True)
    positions = pd.concat(position_rows, ignore_index=True)
    audit = pd.concat(audit_rows, ignore_index=True)
    aggregate = daily.groupby(["date", "expert_id"], as_index=False)["strategy_return"].mean()
    return daily, aggregate, positions, audit


def _market_neutral_diagnostics(
    aggregate: pd.DataFrame, config: dict[str, Any], output: Path
) -> dict[str, Any]:
    """Measure shared SPY beta and residual returns without changing gates."""
    macro_path = _repo_path(config["source"]["macro_data_dir"]) / "spy_daily.parquet"
    spy = pd.read_parquet(macro_path)
    spy["date"] = pd.to_datetime(spy["date"], errors="raise")
    spy = spy.sort_values("date").drop_duplicates("date")
    market = spy.set_index("date")["close"].pct_change(fill_method=None).rename("market_return")
    pivot = aggregate.pivot(index="date", columns="expert_id", values="strategy_return")
    pivot.index = pd.to_datetime(pivot.index)
    aligned = pivot.join(market, how="inner").dropna(subset=["market_return"])
    market_values = aligned["market_return"]
    crisis_cutoff = float(market_values.quantile(0.05))
    rows: list[dict[str, Any]] = []
    residuals: dict[str, pd.Series] = {}
    for expert in config["experts"]:
        if expert not in aligned:
            continue
        pair = aligned[[expert, "market_return"]].dropna()
        expert_values = pair[expert]
        market_values_pair = pair["market_return"]
        variance = float(market_values_pair.var(ddof=1))
        beta = (
            float(expert_values.cov(market_values_pair) / variance)
            if variance > 1e-15
            else 0.0
        )
        up = pair[market_values_pair > 0.0]
        down = pair[market_values_pair < 0.0]
        crisis = pair[market_values_pair <= crisis_cutoff]
        alpha = float(expert_values.mean() - beta * market_values_pair.mean())
        residual = expert_values - (alpha + beta * market_values_pair)
        residuals[expert] = residual.rename(expert)
        rows.append(
            {
                "expert_id": expert,
                "observations": int(len(pair)),
                "alpha": alpha,
                "spy_beta": beta,
                "upside_beta": float(up[expert].cov(up["market_return"]) / up["market_return"].var(ddof=1)) if len(up) > 1 and up["market_return"].var(ddof=1) > 1e-15 else 0.0,
                "downside_beta": float(down[expert].cov(down["market_return"]) / down["market_return"].var(ddof=1)) if len(down) > 1 and down["market_return"].var(ddof=1) > 1e-15 else 0.0,
                "crisis_threshold": crisis_cutoff,
                "crisis_observations": int(len(crisis)),
                "crisis_mean_return": float(crisis[expert].mean()) if not crisis.empty else 0.0,
                "crisis_total_return": float(np.prod(1.0 + crisis[expert].to_numpy()) - 1.0) if not crisis.empty else 0.0,
                "residual_sharpe": _metrics(residual)["sharpe"],
            }
        )
    diagnostics = pd.DataFrame(rows)
    diagnostics.to_csv(output / "market_neutral_diagnostics.csv", index=False)
    residual_frame = pd.concat(residuals, axis=1) if residuals else pd.DataFrame()
    residual_corr = residual_frame.corr(method="spearman")
    residual_corr.to_csv(output / "residual_return_correlation.csv")
    residual_pairs = residual_corr.where(
        np.triu(np.ones(residual_corr.shape), k=1).astype(bool)
    ).stack()
    return {
        "average_residual_spearman": float(residual_pairs.mean()) if not residual_pairs.empty else 0.0,
        "max_abs_spy_beta": float(diagnostics["spy_beta"].abs().max()) if not diagnostics.empty else 0.0,
        "diagnostics": diagnostics.to_dict(orient="records"),
    }
def summarize(
    daily: pd.DataFrame,
    config: dict[str, Any],
    output: Path,
    positions: pd.DataFrame | None = None,
    audit: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    pivot = daily.pivot_table(index="date", columns="expert_id", values="strategy_return", aggfunc="mean")
    experts = [str(value) for value in config["experts"]]
    pivot = pivot.reindex(columns=experts)
    correlation = pivot.corr(method="spearman", min_periods=2)
    correlation.to_csv(output / "expert_orthogonality_matrix.csv")
    pairs = correlation.where(np.triu(np.ones(correlation.shape), k=1).astype(bool)).stack()
    metrics_rows = []
    for expert in experts:
        values = pivot[expert].dropna()
        metrics_rows.append({"expert_id": expert, "coverage": int(values.size), **_metrics(values)})
    metrics = pd.DataFrame(metrics_rows)
    if positions is not None:
        position_metrics = []
        for expert, group in positions.groupby("expert_id"):
            values = group["position"].to_numpy(dtype=float)
            position_metrics.append(
                {
                    "expert_id": expert,
                    "position_mean": float(values.mean()),
                    "position_median": float(np.median(values)),
                    "position_std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                    "position_min": float(values.min()),
                    "position_max": float(values.max()),
                    "long_exposure": float(np.mean(values > 0.0)),
                    "short_exposure": float(np.mean(values < 0.0)),
                    "near_saturated": float(np.mean(np.abs(values) > 0.9)),
                    "turnover": float(group["turnover"].sum()),
                    "mean_daily_turnover": float(group["turnover"].mean()),
                }
            )
        pd.DataFrame(position_metrics).to_csv(output / "expert_position_audit.csv", index=False)
    if audit is not None:
        returns = pd.to_numeric(audit["close_return"], errors="coerce")
        threshold = float(config["data_quality"]["max_abs_close_return"])
        abnormal = audit.loc[
            (returns <= -1.0)
            | (returns > 1.0)
            | (returns.abs() > threshold)
            | ((1.0 + pd.to_numeric(audit["strategy_return"], errors="coerce")) <= 0.0)
        ].copy()
        abnormal.to_csv(output / "data_return_anomalies.csv", index=False)
        audit.to_parquet(output / "expert_return_audit.parquet", index=False)
    dates = sorted(pd.to_datetime(pivot.index).unique())
    fold_manifest = _build_oos_folds(dates)
    fold_manifest.to_csv(output / "expert_oos_fold_manifest.csv", index=False)
    fold_rows = []
    for _, fold in fold_manifest.iterrows():
        test_dates = (pivot.index >= fold["test_start"]) & (pivot.index <= fold["test_end"])
        fold_metrics = pivot.loc[test_dates]
        valid_scores = {
            expert: _metrics(fold_metrics[expert].dropna())["sharpe"]
            for expert in experts
            if int(fold_metrics[expert].notna().sum()) >= 20
        }
        if not valid_scores:
            continue
        fold_rows.append(
            {
                "fold_id": fold["fold_id"],
                "best_expert": max(valid_scores, key=valid_scores.get),
                "test_start": fold["test_start"],
                "test_end": fold["test_end"],
                **{expert: valid_scores.get(expert, np.nan) for expert in experts},
            }
        )
    fold_summary = pd.DataFrame(fold_rows)
    acceptance = config["acceptance"]
    average_corr = float(pairs.mean()) if not pairs.empty else 0.0
    distinct_winners = int(fold_summary["best_expert"].nunique()) if not fold_summary.empty else 0
    eligible = metrics.loc[metrics["expert_id"] != "cash"]
    sharpe_threshold = float(acceptance["min_experts_sharpe_above"])
    sharpe_count_threshold = int(acceptance["min_experts_sharpe_count"])
    experts_sharpe_above = int((eligible["sharpe"] > sharpe_threshold).sum())
    baseline_path = _repo_path(config["phase2_baseline"])
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_sharpe = baseline_payload.get("sharpe")
    if baseline_sharpe is None:
        baseline_sharpe = baseline_payload.get("best_score")
    if baseline_sharpe is None:
        baseline_sharpe = baseline_payload.get("bayesian_opt", {}).get("best_score")
    if baseline_sharpe is None or not np.isfinite(float(baseline_sharpe)):
        raise ValueError("Phase 2 baseline must contain a finite sharpe or best_score")
    composite_sharpe = float(metrics.loc[metrics["expert_id"] == "composite_optimized", "sharpe"].iloc[0])
    composite_improvement = composite_sharpe - float(baseline_sharpe)
    composite_gate = composite_improvement >= float(acceptance["composite_sharpe_improvement_over_phase2"])
    decision = {
        "status": "passed" if average_corr < float(acceptance["max_average_pairwise_spearman"]) and experts_sharpe_above >= sharpe_count_threshold and distinct_winners >= int(acceptance["min_distinct_fold_winners"]) and composite_gate else "failed",
        "average_pairwise_spearman": average_corr,
        "distinct_fold_winners": distinct_winners,
        "experts_sharpe_above_threshold": experts_sharpe_above,
        "phase2_baseline_sharpe": float(baseline_sharpe),
        "composite_sharpe": composite_sharpe,
        "composite_sharpe_improvement": composite_improvement,
        "composite_sharpe_gate": composite_gate,
        "position_semantics": "mixed_by_expert",
        "oos_fold_count": int(len(fold_summary)),
        "abnormal_return_count": int(len(abnormal)) if audit is not None else None,
    }
    return correlation, fold_summary, {"metrics": metrics.to_dict(orient="records"), "decision": decision}


def run(config: dict[str, Any], config_path: Path, symbols: list[str] | None, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    universe = _load_universe(config, symbols)
    price_anomalies = _audit_price_data(universe, config)
    price_anomalies.to_csv(output / "raw_price_anomalies.csv", index=False)
    if not price_anomalies.empty and config["data_quality"].get("fail_on_anomalies", True):
        blocked = {
            "status": "failed",
            "research_only": True,
            "reason": "data_quality_blocked",
            "raw_price_anomaly_count": int(len(price_anomalies)),
            "raw_price_anomaly_symbols": sorted(
                price_anomalies["symbol"].dropna().unique().tolist()
            ),
            "date_start": config["source"]["date_start"],
            "date_end": config["source"]["date_end"],
            "adjustment": config["source"]["adjustment"],
            "message": (
                "Returns and gates are unavailable until the frozen OHLCV source "
                "is corrected or explicitly replaced; no clipping or winsorization was applied."
            ),
        }
        price_anomalies.to_csv(output / "data_return_anomalies.csv", index=False)
        blocked_manifest = {
            "schema_version": "1.0",
            "status": "failed",
            "research_only": True,
            "reason": blocked["reason"],
            "config_sha256": _sha256(config_path),
            "config_path": config_path.relative_to(REPO_ROOT).as_posix(),
            "output_path": output.relative_to(REPO_ROOT).as_posix(),
            "data_manifest_sha256": _sha256(
                _repo_path(config["source"]["data_manifest"])
            ),
            "summary": blocked,
        }
        blocked_json = json.dumps(
            blocked_manifest, indent=2, ensure_ascii=False, sort_keys=True
        )
        (output / "expert_pool_manifest.json").write_text(
            blocked_json, encoding="utf-8"
        )
        (output / "phase3_summary.json").write_text(
            blocked_json, encoding="utf-8"
        )
        report_lines = [
            "# Phase 3 数据质量阻断报告",
            "",
            "> Status: `failed`; this research run is blocked before factor calculation.",
            "",
            f"- Date window: `{blocked['date_start']}` to `{blocked['date_end']}`",
            f"- Adjustment: `{blocked['adjustment']}`",
            f"- Raw price anomaly rows: `{blocked['raw_price_anomaly_count']}`",
            f"- Affected symbols: `{', '.join(blocked['raw_price_anomaly_symbols'])}`",
            "",
            "The anomaly details are in `raw_price_anomalies.csv`. The source contains "
            "price-scale and/or adjacent-close jumps above the registered threshold.",
            "Sharpe, total return, fold winners, and Composite-vs-baseline gates are "
            "not valid evidence and are intentionally not recomputed.",
            "No return clipping, winsorization, or gate relaxation was applied.",
            "",
        ]
        (REPO_ROOT / "document" / "phase3_expert_orthogonality_report.md").write_text(
            "\n".join(report_lines), encoding="utf-8"
        )
        (REPO_ROOT / "document" / "phase3_expert_backtest_report.md").write_text(
            "\n".join(report_lines), encoding="utf-8"
        )
        raise ValueError(
            "raw price audit failed; see "
            f"{(output / 'raw_price_anomalies.csv').relative_to(REPO_ROOT)}"
        )
    daily, aggregate, positions, audit = aggregate_expert_returns(universe, config)
    diagnostics = _market_neutral_diagnostics(aggregate, config, output)
    daily.to_parquet(output / "expert_daily_returns.parquet", index=False)
    aggregate.to_csv(output / "expert_aggregate_daily_returns.csv", index=False)
    _, folds, summary = summarize(daily, config, output, positions, audit)
    summary["diagnostics"] = diagnostics
    folds.to_csv(output / "expert_fold_metrics.csv", index=False)
    decision = summary["decision"]
    orthogonality_report = REPO_ROOT / "document" / "phase3_expert_orthogonality_report.md"
    orthogonality_report_text = "\n".join(
        [
            "# Phase 3 专家正交性验证",
            "",
            "> Scope: research-only heterogeneous expert pool; this report does not change production or Streamlit.",
            "",
            f"- Symbols evaluated: `{len(universe)}`",
            f"- Average pairwise Spearman correlation: `{decision['average_pairwise_spearman']:.6f}`",
            f"- Distinct fold winners: `{decision['distinct_fold_winners']}`",
            f"- Experts with Sharpe above threshold: `{decision['experts_sharpe_above_threshold']}`",
            f"- Composite Sharpe improvement over Phase 2: `{decision['composite_sharpe_improvement']:.6f}`",
            f"- Residual average Spearman correlation: `{diagnostics['average_residual_spearman']:.6f}`",
            f"- Maximum absolute SPY beta: `{diagnostics['max_abs_spy_beta']:.6f}`",
            f"- Orthogonality gate: `{decision['status']}`",
            "",
            "The machine-readable matrix and fold evidence are stored under the Phase 3 output directory.",
            "A failed gate is retained as evidence and does not authorize Phase 4 or online integration.",
            "",
        ]
    )
    backtest_report = REPO_ROOT / "document" / "phase3_expert_backtest_report.md"
    backtest_report_text = "\n".join(
        [
            "# Phase 3 专家回测报告",
            "",
            "> Returns use `strategy_return` semantics with execution costs charged once in this research runner.",
            "",
            "## Metrics",
            "",
            pd.DataFrame(summary["metrics"]).to_markdown(index=False),
            "",
            "## Decision",
            "",
            f"- Status: `{decision['status']}`",
            f"- Average correlation: `{decision['average_pairwise_spearman']:.6f}`",
            f"- Distinct fold winners: `{decision['distinct_fold_winners']}`",
            f"- Composite Sharpe improvement over Phase 2: `{decision['composite_sharpe_improvement']:.6f}`",
            f"- Residual average Spearman correlation: `{summary['diagnostics']['average_residual_spearman']:.6f}`",
            f"- Maximum absolute SPY beta: `{summary['diagnostics']['max_abs_spy_beta']:.6f}`",
            "",
            "A full frozen-universe run is formal Phase 3 evidence."
            if symbols is None and len(universe) == int(config["source"]["required_universe"])
            else "The subset command is diagnostic only; a full frozen-universe run is required before treating this as formal Phase 3 evidence.",
            "",
        ]
    )
    config_hash = _sha256(config_path)
    data_manifest_path = _repo_path(config["source"]["data_manifest"])
    data_manifest = json.loads(data_manifest_path.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": "1.0",
        "status": summary["decision"]["status"],
        "research_only": True,
        "config_sha256": config_hash,
        "config_path": config_path.relative_to(REPO_ROOT).as_posix(),
        "output_path": output.relative_to(REPO_ROOT).as_posix(),
        "data_manifest_sha256": _sha256(data_manifest_path),
        "data_manifest_path": config["source"]["data_manifest"],
        "source_manifest_sha256": _sha256(_repo_path(config["source"]["source_manifest"])),
        "source_semantic_fingerprint": data_manifest["data"]["source_semantic_fingerprint"],
        "macro_data_manifest_sha256": _sha256(_repo_path(config["source"]["macro_data_manifest"])),
        "snapshot_sha256": data_manifest["data"]["snapshot_sha256"],
        "snapshot_provider": data_manifest["source"]["provider"],
        "snapshot_adjustment": data_manifest["data"]["adjustment"],
        "factor_source_sha256": _sha256(_repo_path(config["factor_source"])),
        "macro_sources_sha256": {
            name: _sha256(_repo_path(config["source"]["macro_data_dir"]) / name)
            for name in ("vix_daily.parquet", "spy_daily.parquet")
        },
        "symbol_count": len(universe),
        "experts": config["experts"],
        "cost_treatment": config["execution"]["cost_treatment"],
        "summary": summary,
    }
    (output / "expert_pool_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (output / "phase3_summary.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    orthogonality_report.write_text(orthogonality_report_text, encoding="utf-8")
    backtest_report.write_text(backtest_report_text, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="model-test/configs/expert_pool_v2.json")
    parser.add_argument("--symbols", default=None, help="comma-separated subset; omit for frozen universe")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    config_path = _repo_path(args.config)
    config = load_config(config_path)
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()] if args.symbols else None
    output = _repo_path(args.output or config["output_subdir"])
    print(json.dumps(run(config, config_path, symbols, output)["summary"]["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
