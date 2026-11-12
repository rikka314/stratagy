"""Market-aware inputs for factor computation.

The context is deliberately small: it records the market-native benchmark and
optional observed factor sources while keeping source selection outside the
factor calculation code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd


_MARKET_ALIASES = {
    "US": "US",
    "USA": "US",
    "CN_A": "CN_A",
    "CN-A": "CN_A",
    "CNA": "CN_A",
}


def normalize_market(market: str) -> str:
    """Return the canonical market name or fail on an unknown market."""
    normalized = str(market).strip().upper().replace(" ", "_")
    try:
        return _MARKET_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported market: {market!r}. Expected US or CN_A") from exc


def _validate_frame(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    required = {"date", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} data missing columns: {', '.join(sorted(missing))}")
    result = frame.loc[:, ["date", "close"]].copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    if result["date"].duplicated().any() or not result["date"].is_monotonic_increasing:
        raise ValueError(f"{name} dates must be unique and sorted")
    values = result["close"].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError(f"{name} close values must be finite and positive")
    return result


@dataclass(frozen=True)
class MarketFactorContext:
    """Market-native data sources used by the macro factor layer."""

    market: str
    benchmark_symbol: str
    benchmark_frame: pd.DataFrame
    volatility_frame: pd.DataFrame | None = None
    breadth_frame: pd.DataFrame | None = None
    sector_frame: pd.DataFrame | None = None
    factor_availability: Mapping[str, str] = MappingProxyType({})
    source_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", normalize_market(self.market))
        if not str(self.benchmark_symbol).strip():
            raise ValueError("benchmark_symbol must not be empty")
        object.__setattr__(
            self,
            "benchmark_frame",
            _validate_frame(self.benchmark_frame, "benchmark"),
        )
        for field_name in ("volatility_frame", "breadth_frame", "sector_frame"):
            frame = getattr(self, field_name)
            if frame is not None:
                if "date" not in frame.columns:
                    raise ValueError(f"{field_name} must contain date")
                copied = frame.copy()
                copied["date"] = pd.to_datetime(copied["date"], errors="raise")
                if copied["date"].duplicated().any() or not copied["date"].is_monotonic_increasing:
                    raise ValueError(f"{field_name} dates must be unique and sorted")
                object.__setattr__(self, field_name, copied)
        object.__setattr__(self, "factor_availability", MappingProxyType(dict(self.factor_availability)))


def _load_observed_frame(path: Path, name: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{name} data not found at {path}")
    return _validate_frame(pd.read_parquet(path), name)


def _build_equal_weight_benchmark(universe_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"date", "symbol", "close"}
    missing = required - set(universe_frame.columns)
    if missing:
        raise ValueError(f"universe_frame missing columns: {', '.join(sorted(missing))}")
    source = universe_frame.loc[:, ["date", "symbol", "close"]].copy()
    source["date"] = pd.to_datetime(source["date"], errors="raise")
    source["symbol"] = source["symbol"].astype(str)
    if source[["date", "symbol"]].duplicated().any():
        raise ValueError("universe_frame contains duplicate date-symbol rows")
    source["close"] = pd.to_numeric(source["close"], errors="coerce")
    values = source["close"].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("universe_frame close values must be finite and positive")
    source = source.sort_values(["symbol", "date"])
    source["return_1"] = source.groupby("symbol", sort=False)["close"].pct_change(fill_method=None)
    returns = source.dropna(subset=["return_1"]).groupby("date", sort=True)["return_1"].mean()
    if returns.empty:
        raise ValueError("universe_frame cannot build an equal-weight benchmark")
    benchmark = pd.DataFrame({"date": returns.index, "close": (1.0 + returns).cumprod()})
    benchmark = benchmark.reset_index(drop=True)
    breadth = source.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
    breadth.index.name = None
    breadth = pd.DataFrame({
        "date": breadth.index,
        "market_constituent_count": breadth.notna().sum(axis=1).astype(float).to_numpy(),
        "breadth_up_ratio_1": breadth.pct_change(fill_method=None).gt(0).mean(axis=1).to_numpy(),
    })
    breadth["breadth_up_ratio_20"] = breadth["breadth_up_ratio_1"].rolling(20, min_periods=20).mean()
    breadth["market_breadth"] = breadth["breadth_up_ratio_1"]
    return _validate_frame(benchmark, "CN_A fallback benchmark"), breadth


def build_market_factor_context(
    market: str,
    *,
    data_dir: str | Path = "data/macro",
    universe_frame: pd.DataFrame | None = None,
    benchmark_frame: pd.DataFrame | None = None,
) -> MarketFactorContext:
    """Build a context using only sources allowed for ``market``.

    US may use the observed SPY/VIX artifacts. CN_A requires an explicit
    benchmark or an explicit universe frame; it never probes US artifacts.
    """
    canonical = normalize_market(market)
    root = Path(data_dir)
    breadth_frame = None
    availability: dict[str, str] = {}
    if benchmark_frame is not None:
        benchmark = _validate_frame(benchmark_frame, f"{canonical} benchmark")
        benchmark_symbol = "provided"
        availability["benchmark"] = "provided"
        if canonical == "CN_A" and universe_frame is not None:
            _, breadth_frame = _build_equal_weight_benchmark(universe_frame)
            availability["breadth"] = "frozen_universe"
    elif canonical == "US":
        benchmark = _load_observed_frame(root / "spy_daily.parquet", "US SPY")
        benchmark_symbol = "SPY"
        availability["benchmark"] = "observed"
    elif universe_frame is not None:
        benchmark, breadth_frame = _build_equal_weight_benchmark(universe_frame)
        benchmark_symbol = "frozen_universe_equal_weight"
        availability["benchmark"] = "frozen_universe_equal_weight_close_return"
        availability["breadth"] = "frozen_universe"
    else:
        raise ValueError("CN_A requires an explicit benchmark_frame or universe_frame")

    volatility = None
    if canonical == "US":
        volatility = _load_observed_frame(root / "vix_daily.parquet", "US VIX")
        availability["volatility"] = "observed_vix"
    else:
        availability["volatility"] = "benchmark_realized_volatility"
    availability.setdefault("breadth", "benchmark_return_proxy" if canonical == "US" else "unavailable")
    availability.setdefault("sector", "unavailable")
    return MarketFactorContext(
        market=canonical,
        benchmark_symbol=benchmark_symbol,
        benchmark_frame=benchmark,
        volatility_frame=volatility,
        breadth_frame=breadth_frame,
        factor_availability=availability,
    )
