from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from core.data import ensure_date_column, fetch_a_stock, fetch_data, standardize_columns

from model_test import REPO_ROOT, WORKSPACE_ROOT
from model_test.models import ResearchConfig, StockProfile


# Research-fetched history is intentionally separate from the tracked data/
# samples. Keep this module-level name for tests and local overrides.
DATA_DIR = str(WORKSPACE_ROOT / "cache" / "history")


COMMON_STOCK_NAME_EXCLUSIONS = (
    " ETF",
    "ETN",
    " FUND",
    " TRUST",
    " WARRANT",
    " RIGHTS",
    " UNIT",
    " NOTES",
    " BOND",
    " ACQUISITION",
    " SPAC",
)

BUCKET_ORDER = [
    "Up__Low",
    "Up__Mid",
    "Up__High",
    "Flat__Low",
    "Flat__Mid",
    "Flat__High",
    "Down__Low",
    "Down__Mid",
    "Down__High",
]

UNIVERSE_CACHE_VERSION = "v3"
_COMMON_STOCK_NAME_EXCLUSION_REGEX = "|".join(re.escape(keyword) for keyword in COMMON_STOCK_NAME_EXCLUSIONS)


def _read_market_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


def _resolve_repo_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def _resolve_data_cache_dir() -> Path:
    data_dir = Path(DATA_DIR)
    if data_dir.is_absolute():
        return data_dir.resolve()
    return (REPO_ROOT / data_dir).resolve()


def _resolve_cache_root(config: ResearchConfig) -> Path:
    cache_root = _resolve_repo_path(config.cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(encoded.encode("utf-8")).hexdigest()


def _path_metadata(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    if not resolved.exists():
        return None
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
    }


def _metadata_matches(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    return (
        str(left.get("path")) == str(right.get("path"))
        and int(left.get("mtime_ns", -1)) == int(right.get("mtime_ns", -2))
        and int(left.get("size", -1)) == int(right.get("size", -2))
    )


def _profile_cache_signature(config: ResearchConfig) -> str:
    return _json_hash(
        {
            "cache_version": UNIVERSE_CACHE_VERSION,
            "market": config.market.upper(),
            "adjust": config.adjust,
            "profile_lookback_days": int(config.profile_lookback_days),
            "minimum_data_end_date": config.minimum_data_end_date,
        }
    )[:12]


def _pool_cache_signature(config: ResearchConfig, catalog_path: Path) -> str:
    return _json_hash(
        {
            "cache_version": UNIVERSE_CACHE_VERSION,
            "catalog_meta": _path_metadata(catalog_path),
            "market": config.market.upper(),
            "adjust": config.adjust,
            "profile_lookback_days": int(config.profile_lookback_days),
            "main_pool_size": int(config.main_pool_size),
            "min_history_days": int(config.min_history_days),
            "main_window_days": int(config.main_window_days),
            "min_avg_traded_value": float(config.effective_min_avg_traded_value),
            "max_catalog_candidates": int(config.max_catalog_candidates),
            "candidate_selection_mode": config.candidate_selection_mode,
            "candidate_selection_seed": int(config.candidate_selection_seed),
            "minimum_data_end_date": config.minimum_data_end_date,
        }
    )[:16]


def _profile_cache_path(symbol: str, config: ResearchConfig) -> Path:
    cache_root = _resolve_cache_root(config)
    signature = _profile_cache_signature(config)
    return cache_root / "profiles" / signature / f"{_normalize_symbol(symbol, config.market)}.json"


def _normalize_symbol(symbol: str, market: str) -> str:
    normalized = str(symbol).strip().upper()
    if market == "CN_A":
        digits = re.sub(r"\D", "", normalized)
        return digits.zfill(6)[-6:]
    return normalized


def _pool_cache_path(config: ResearchConfig, catalog_path: Path) -> Path:
    cache_root = _resolve_cache_root(config)
    signature = _pool_cache_signature(config, catalog_path)
    return cache_root / "research_pool" / f"{signature}.json"


def _resolve_history_candidates(symbol: str, config: ResearchConfig, *, prefer_sample: bool) -> list[tuple[str, Path]]:
    normalized_symbol = _normalize_symbol(symbol, config.market)
    sample_path = _resolve_repo_path(Path(config.sample_data_dir) / f"{normalized_symbol.lower()}_daily.csv")
    cache_path = _resolve_data_cache_dir() / f"{normalized_symbol.lower()}_daily.csv"

    candidates: list[tuple[str, Path]] = []
    if prefer_sample and sample_path.exists():
        candidates.append(("sample_csv", sample_path))
    if cache_path.exists():
        candidates.append(("cache_csv", cache_path))
    if sample_path.exists() and sample_path not in [item[1] for item in candidates]:
        candidates.append(("sample_csv", sample_path))
    return candidates


def _current_history_source(symbol: str, config: ResearchConfig, *, prefer_sample: bool) -> tuple[str, Path] | None:
    candidates = _resolve_history_candidates(symbol, config, prefer_sample=prefer_sample)
    return candidates[0] if candidates else None


def _stock_profile_from_payload(payload: dict[str, Any]) -> StockProfile:
    return StockProfile(
        symbol=str(payload["symbol"]),
        company_name=str(payload["company_name"]),
        source_kind=str(payload["source_kind"]),
        data_path=str(payload["data_path"]),
        history_days=int(payload["history_days"]),
        recent_days=int(payload["recent_days"]),
        total_return_1y=payload.get("total_return_1y"),
        annualized_vol_1y=payload.get("annualized_vol_1y"),
        max_drawdown_1y=payload.get("max_drawdown_1y"),
        avg_dollar_volume_1y=payload.get("avg_dollar_volume_1y"),
        trend_bucket=str(payload.get("trend_bucket", "Unknown")),
        volatility_bucket=str(payload.get("volatility_bucket", "Unknown")),
        segment_key=str(payload.get("segment_key", "Unknown__Unknown")),
    )


def _load_cached_profile(
    symbol: str,
    config: ResearchConfig,
    *,
    current_source: tuple[str, Path] | None,
) -> StockProfile | None:
    cache_path = _profile_cache_path(symbol, config)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    expected_signature = _profile_cache_signature(config)
    if payload.get("profile_signature") != expected_signature:
        return None

    source_kind, source_path = current_source if current_source is not None else (None, None)
    current_meta = _path_metadata(source_path) if source_path is not None else None
    cached_meta = payload.get("source_meta")
    if not _metadata_matches(current_meta, cached_meta):
        return None

    try:
        profile = _stock_profile_from_payload(payload["profile"])
    except Exception:
        return None
    if source_kind is not None:
        profile.source_kind = str(source_kind)
    if current_meta is not None:
        profile.data_path = str(current_meta["path"])
    return profile


def _save_cached_profile(
    symbol: str,
    config: ResearchConfig,
    *,
    profile: StockProfile,
    source_meta: dict[str, Any] | None,
) -> None:
    if source_meta is None:
        return

    cache_path = _profile_cache_path(symbol, config)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile_signature": _profile_cache_signature(config),
        "source_meta": source_meta,
        "profile": profile.to_row(),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_pool_cache_candidates(config: ResearchConfig, catalog_path: Path) -> list[dict[str, Any]] | None:
    cache_path = _pool_cache_path(config, catalog_path)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    candidates = payload.get("candidate_entries")
    if not isinstance(candidates, list):
        return None
    normalized: list[dict[str, Any]] = []
    for order, item in enumerate(candidates):
        normalized.append(
            {
                "order": int(item.get("order", order)),
                "symbol": str(item.get("symbol", "")).strip().upper(),
                "name": str(item.get("name", "")).strip(),
            }
        )
    return normalized


def _save_pool_cache(
    config: ResearchConfig,
    catalog_path: Path,
    *,
    candidate_entries: list[dict[str, Any]],
    selected_profiles: list[StockProfile],
) -> None:
    cache_path = _pool_cache_path(config, catalog_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_version": UNIVERSE_CACHE_VERSION,
        "catalog_meta": _path_metadata(catalog_path),
        "candidate_entries": candidate_entries,
        "selected_profiles": [profile.to_row() for profile in selected_profiles],
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _finalize_local_frame(df: pd.DataFrame, symbol: str, config: ResearchConfig) -> pd.DataFrame:
    frame = df.copy()
    if "symbol" not in frame.columns:
        frame["symbol"] = symbol.upper()
    if "market" not in frame.columns:
        frame["market"] = config.market.upper()
    if "currency" not in frame.columns:
        frame["currency"] = "USD" if config.market == "US" else "CNY"
    if "adjust" not in frame.columns:
        frame["adjust"] = config.adjust
    return frame


def _write_cache(df: pd.DataFrame, symbol: str) -> Path:
    cache_dir = _resolve_data_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{symbol.lower()}_daily.csv"
    df.to_csv(cache_path, index=False)
    return cache_path


def _meets_minimum_data_end_date(df: pd.DataFrame, config: ResearchConfig) -> bool:
    if not config.minimum_data_end_date:
        return True
    if "date" not in df.columns:
        return False
    latest = pd.to_datetime(df["date"], errors="coerce").max()
    return bool(pd.notna(latest) and latest >= pd.Timestamp(config.minimum_data_end_date))


def load_symbol_history(symbol: str, config: ResearchConfig, *, prefer_sample: bool) -> tuple[pd.DataFrame, str, Path]:
    normalized_symbol = _normalize_symbol(symbol, config.market)
    for source_kind, path in _resolve_history_candidates(normalized_symbol, config, prefer_sample=prefer_sample):
        try:
            df = _read_market_csv(path)
            if not _meets_minimum_data_end_date(df, config):
                continue
            return _finalize_local_frame(df, normalized_symbol, config), source_kind, path.resolve()
        except Exception:
            continue

    if config.market == "US":
        df = fetch_data(normalized_symbol, config.adjust)
    else:
        df = fetch_a_stock(normalized_symbol, config.adjust)
        if df is None or df.empty:
            raise ValueError(f"No CN_A history is available for {normalized_symbol}.")
    cache_file = _write_cache(df, normalized_symbol)
    return _finalize_local_frame(df, normalized_symbol, config), "fetched", cache_file.resolve()


def _compute_recent_profile(df: pd.DataFrame, lookback_days: int) -> dict[str, float | int | None]:
    numeric = df.copy()
    for column in ("close", "volume"):
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    numeric = numeric.dropna(subset=["close", "volume"])
    if numeric.empty:
        return {
            "recent_days": 0,
            "total_return_1y": None,
            "annualized_vol_1y": None,
            "max_drawdown_1y": None,
            "avg_dollar_volume_1y": None,
        }

    recent = numeric.tail(lookback_days).copy()
    if recent.empty:
        return {
            "recent_days": 0,
            "total_return_1y": None,
            "annualized_vol_1y": None,
            "max_drawdown_1y": None,
            "avg_dollar_volume_1y": None,
        }

    equity = recent["close"] / recent["close"].iloc[0]
    drawdown = (equity / equity.cummax()) - 1.0
    daily_return = recent["close"].pct_change().fillna(0.0)
    if "amount" in recent.columns:
        amount = pd.to_numeric(recent["amount"], errors="coerce").dropna()
        avg_dollar_volume = float(amount.mean()) if not amount.empty else float((recent["close"] * recent["volume"]).mean())
    else:
        avg_dollar_volume = float((recent["close"] * recent["volume"]).mean())
    return {
        "recent_days": int(len(recent)),
        "total_return_1y": float(recent["close"].iloc[-1] / recent["close"].iloc[0] - 1.0),
        "annualized_vol_1y": float(daily_return.std(ddof=0) * math.sqrt(252)) if len(recent) > 1 else 0.0,
        "max_drawdown_1y": float(drawdown.min()) if not drawdown.empty else 0.0,
        "avg_dollar_volume_1y": avg_dollar_volume,
    }


def _profile_from_history(
    symbol: str,
    company_name: str,
    df: pd.DataFrame,
    source_kind: str,
    data_path: Path,
    config: ResearchConfig,
) -> StockProfile:
    recent_metrics = _compute_recent_profile(df, config.profile_lookback_days)
    return StockProfile(
        symbol=_normalize_symbol(symbol, config.market),
        company_name=company_name,
        source_kind=source_kind,
        data_path=str(data_path),
        history_days=int(len(df)),
        recent_days=int(recent_metrics["recent_days"]),
        total_return_1y=recent_metrics["total_return_1y"],
        annualized_vol_1y=recent_metrics["annualized_vol_1y"],
        max_drawdown_1y=recent_metrics["max_drawdown_1y"],
        avg_dollar_volume_1y=recent_metrics["avg_dollar_volume_1y"],
    )


def _assign_buckets(profiles: list[StockProfile]) -> None:
    vol_series = pd.Series([profile.annualized_vol_1y for profile in profiles], dtype="float64").dropna()
    if vol_series.empty:
        q1 = q2 = None
    else:
        q1 = float(vol_series.quantile(1.0 / 3.0))
        q2 = float(vol_series.quantile(2.0 / 3.0))

    for profile in profiles:
        total_return = profile.total_return_1y
        if total_return is None:
            profile.trend_bucket = "Unknown"
        elif total_return > 0.20:
            profile.trend_bucket = "Up"
        elif total_return < -0.10:
            profile.trend_bucket = "Down"
        else:
            profile.trend_bucket = "Flat"

        vol = profile.annualized_vol_1y
        if vol is None or q1 is None or q2 is None:
            profile.volatility_bucket = "Unknown"
        elif vol <= q1:
            profile.volatility_bucket = "Low"
        elif vol <= q2:
            profile.volatility_bucket = "Mid"
        else:
            profile.volatility_bucket = "High"

        profile.segment_key = f"{profile.trend_bucket}__{profile.volatility_bucket}"


def _liquidity_key(profile: StockProfile) -> tuple[float, str]:
    return (float(profile.avg_dollar_volume_1y or 0.0), profile.symbol)


def _select_balanced_sample(profiles: list[StockProfile], target_size: int) -> list[StockProfile]:
    buckets = {bucket: [] for bucket in BUCKET_ORDER}
    for profile in profiles:
        bucket = profile.segment_key
        buckets.setdefault(bucket, []).append(profile)
    for bucket in buckets:
        buckets[bucket].sort(key=_liquidity_key, reverse=True)

    selected: list[StockProfile] = []
    selected_symbols: set[str] = set()

    while len(selected) < target_size:
        progressed = False
        for bucket in BUCKET_ORDER:
            if not buckets.get(bucket):
                continue
            profile = buckets[bucket].pop(0)
            if profile.symbol in selected_symbols:
                continue
            selected.append(profile)
            selected_symbols.add(profile.symbol)
            progressed = True
            if len(selected) >= target_size:
                break
        if not progressed:
            break

    if len(selected) < target_size:
        leftovers: list[StockProfile] = []
        for bucket_profiles in buckets.values():
            leftovers.extend(bucket_profiles)
        leftovers.sort(key=_liquidity_key, reverse=True)
        for profile in leftovers:
            if profile.symbol in selected_symbols:
                continue
            selected.append(profile)
            selected_symbols.add(profile.symbol)
            if len(selected) >= target_size:
                break

    return selected


def build_smoke_profiles(config: ResearchConfig) -> list[StockProfile]:
    profiles: list[StockProfile] = []
    for symbol in config.smoke_symbols:
        df, source_kind, data_path = load_symbol_history(symbol, config, prefer_sample=True)
        profiles.append(_profile_from_history(symbol, symbol, df, source_kind, data_path, config))
    _assign_buckets(profiles)
    return profiles


def _is_common_stock_candidate(symbol: str, name: str) -> bool:
    if re.fullmatch(r"\d{6}", symbol):
        return True
    if not re.fullmatch(r"[A-Z]{1,5}", symbol):
        return False
    upper_name = f" {str(name or '').upper()} "
    for keyword in COMMON_STOCK_NAME_EXCLUSIONS:
        if keyword in upper_name:
            return False
    return True


def _filter_common_stock_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    filtered = candidates.copy()
    if "code" in filtered.columns and "symbol" not in filtered.columns:
        filtered = filtered.rename(columns={"code": "symbol"})
    filtered["symbol"] = filtered["symbol"].astype(str).str.extract(r"(\d+|[A-Za-z]+)")[0].fillna("").str.strip().str.upper()
    filtered["name"] = filtered["name"].astype(str).str.strip()
    symbol_mask = filtered["symbol"].str.fullmatch(r"(?:[A-Z]{1,5}|\d{6})", na=False)
    upper_name = " " + filtered["name"].str.upper() + " "
    name_mask = ~upper_name.str.contains(_COMMON_STOCK_NAME_EXCLUSION_REGEX, regex=True, na=False)
    cn_a_mask = filtered["symbol"].str.fullmatch(r"\d{6}", na=False)
    return filtered.loc[symbol_mask & (cn_a_mask | name_mask)].reset_index(drop=True)


def _profile_qualifies(profile: StockProfile, config: ResearchConfig, minimum_rows: int) -> bool:
    if profile.history_days < minimum_rows:
        return False
    if profile.recent_days < int(config.profile_lookback_days):
        return False
    if float(profile.avg_dollar_volume_1y or 0.0) < config.effective_min_avg_traded_value:
        return False
    return True


def _load_or_build_candidate_profile(
    candidate_entry: dict[str, Any],
    config: ResearchConfig,
    *,
    minimum_rows: int,
) -> tuple[int, StockProfile | None]:
    symbol = _normalize_symbol(str(candidate_entry["symbol"]), config.market)
    company_name = str(candidate_entry.get("name") or symbol).strip() or symbol
    order = int(candidate_entry.get("order", 0))
    current_source = _current_history_source(symbol, config, prefer_sample=False)

    cached_profile = _load_cached_profile(symbol, config, current_source=current_source)
    if cached_profile is not None:
        return order, cached_profile if _profile_qualifies(cached_profile, config, minimum_rows) else None

    try:
        df, source_kind, data_path = load_symbol_history(symbol, config, prefer_sample=False)
    except Exception:
        return order, None

    profile = _profile_from_history(symbol, company_name, df, source_kind, data_path, config)
    _save_cached_profile(
        symbol,
        config,
        profile=profile,
        source_meta=_path_metadata(data_path),
    )
    return order, profile if _profile_qualifies(profile, config, minimum_rows) else None


def _build_candidate_entries(config: ResearchConfig, catalog_path: Path) -> list[dict[str, Any]]:
    catalog = pd.read_csv(catalog_path, dtype=str).fillna("")
    symbol_column = "symbol" if "symbol" in catalog.columns else "code"
    if symbol_column not in catalog.columns or "name" not in catalog.columns:
        raise ValueError(f"Catalog {catalog_path} must contain symbol/code and name columns.")
    candidates = catalog[[symbol_column, "name"]].rename(columns={symbol_column: "symbol"})
    candidates = candidates.drop_duplicates(subset=["symbol"], keep="first")
    filtered = _filter_common_stock_candidates(candidates)
    candidate_limit = max(1, int(config.max_catalog_candidates))
    if config.candidate_selection_mode == "hybrid" and len(filtered) > candidate_limit:
        # Preserve a liquid/popular catalog head while adding deterministic broad-market coverage.
        head_count = max(1, candidate_limit // 4)
        head = filtered.head(head_count)
        remainder = filtered.iloc[head_count:]
        sampled = remainder.sample(
            n=min(candidate_limit - head_count, len(remainder)),
            random_state=int(config.candidate_selection_seed),
            replace=False,
        )
        limited = pd.concat([head, sampled], ignore_index=True)
    else:
        limited = filtered.head(candidate_limit).reset_index(drop=True)
    return [
        {
            "order": order,
            "symbol": _normalize_symbol(str(row.symbol), config.market),
            "name": str(row.name).strip(),
        }
        for order, row in enumerate(limited.itertuples(index=False))
    ]


def _qualified_profiles_from_candidates(
    candidate_entries: list[dict[str, Any]],
    config: ResearchConfig,
    *,
    minimum_rows: int,
) -> list[StockProfile]:
    if not candidate_entries:
        return []

    max_workers = max(1, int(config.universe_parallelism))
    qualified_records: list[tuple[int, StockProfile]] = []

    if max_workers == 1:
        for candidate_entry in candidate_entries:
            order, profile = _load_or_build_candidate_profile(candidate_entry, config, minimum_rows=minimum_rows)
            if profile is not None:
                qualified_records.append((order, profile))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_order = {
                executor.submit(
                    _load_or_build_candidate_profile,
                    candidate_entry,
                    config,
                    minimum_rows=minimum_rows,
                ): int(candidate_entry["order"])
                for candidate_entry in candidate_entries
            }
            for future in as_completed(future_to_order):
                try:
                    order, profile = future.result()
                except Exception:
                    continue
                if profile is not None:
                    qualified_records.append((order, profile))

    qualified_records.sort(key=lambda item: item[0])
    return [profile for _order, profile in qualified_records]


def build_main_research_profiles(config: ResearchConfig) -> list[StockProfile]:
    catalog_path = _resolve_repo_path(config.catalog_path)
    candidate_entries = _load_pool_cache_candidates(config, catalog_path)
    if candidate_entries is None:
        candidate_entries = _build_candidate_entries(config, catalog_path)

    qualified: list[StockProfile] = []
    minimum_rows = max(config.min_history_days, config.main_window_days, config.profile_lookback_days)
    qualified = _qualified_profiles_from_candidates(candidate_entries, config, minimum_rows=minimum_rows)

    if not qualified:
        raise RuntimeError(f"No qualified {config.market} stocks were found for the research pool.")

    _assign_buckets(qualified)
    selected = _select_balanced_sample(qualified, config.main_pool_size)
    _save_pool_cache(
        config,
        catalog_path,
        candidate_entries=candidate_entries,
        selected_profiles=selected,
    )
    return selected


def build_stock_profiles(config: ResearchConfig) -> list[StockProfile]:
    return build_smoke_profiles(config) if config.smoke_mode else build_main_research_profiles(config)
