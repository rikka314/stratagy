"""Market-aware macro and relative factor calculations."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from core.market_factor_context import MarketFactorContext, build_market_factor_context, normalize_market


MACRO_FEATURE_COLUMNS = (
    "vix_level",
    "rel_strength_vs_spy",
    "market_breadth",
    "beta_20d",
    "sector_momentum",
)


def _as_date_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "date" not in result.columns:
        if isinstance(result.index, pd.DatetimeIndex):
            result = result.reset_index(names="date")
        else:
            raise ValueError("price frame must contain date")
    result = result.rename(columns={"Close": "close"})
    if "close" not in result.columns:
        raise ValueError("price frame must contain close")
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    if result["date"].duplicated().any():
        raise ValueError("price frame dates must be unique")
    return result.sort_values("date").reset_index(drop=True)


class MacroFactors:
    """Compute market factors from an explicit market context."""

    def __init__(
        self,
        data_dir: str | Path = "data/macro",
        *,
        macro_data_dir: str | Path | None = None,
        context: MarketFactorContext | None = None,
    ) -> None:
        if macro_data_dir is not None:
            data_dir = macro_data_dir
        self.data_dir = Path(data_dir)
        self.context = context
        self._vix_data: pd.DataFrame | None = None
        self._spy_data: pd.DataFrame | None = None
        self._sector_map: pd.DataFrame | None = None

    @property
    def sector_map(self) -> pd.DataFrame:
        """Load the US sector map only when the US path uses it."""
        if self._sector_map is None:
            self._sector_map = self._load_sector_map()
        return self._sector_map.copy()

    @property
    def vix_data(self) -> pd.DataFrame:
        """Load US VIX only when a caller explicitly requests it."""
        if self._vix_data is None:
            self._vix_data = self._load_optional("vix_daily.parquet")
        return self._vix_data.copy()

    @property
    def spy_data(self) -> pd.DataFrame:
        """Load US SPY only when a caller explicitly requests it."""
        if self._spy_data is None:
            self._spy_data = self._load_optional("spy_daily.parquet")
        return self._spy_data.copy()

    def with_context(self, context: MarketFactorContext) -> "MacroFactors":
        """Return a calculator bound to a new immutable context."""
        return MacroFactors(data_dir=self.data_dir, context=context)

    def compute(
        self,
        df: pd.DataFrame | pd.Timestamp | None = None,
        symbol: str | pd.DataFrame | None = None,
        *args: object,
        market: str | None = None,
        market_context: MarketFactorContext | None = None,
        date: pd.Timestamp | None = None,
        stock_data: pd.DataFrame | None = None,
        stock_symbol: str | None = None,
    ) -> pd.DataFrame | dict[str, float]:
        """Compute market factors in the new or legacy calling convention.

        The DataFrame-first form returns an augmented DataFrame. The historical
        ``compute(date, stock_data, stock_symbol=None)`` form returns one factor
        dictionary and remains US-only for compatibility with old research code.
        """
        if date is not None or stock_data is not None:
            if df is not None or symbol is not None:
                raise TypeError("use either legacy date/stock_data keywords or positional arguments")
            df, symbol = date, stock_data
        if args:
            if len(args) > 1 or stock_symbol is not None:
                raise TypeError("too many legacy compute arguments")
            stock_symbol = str(args[0])
        if isinstance(df, (pd.Timestamp, str)) and isinstance(symbol, pd.DataFrame):
            if market not in (None, "US", "USA"):
                raise ValueError("legacy MacroFactors.compute supports US only")
            return self._compute_legacy_point(
                pd.to_datetime(df), symbol, stock_symbol=stock_symbol
            )
        if not isinstance(df, pd.DataFrame) or not isinstance(symbol, str):
            raise TypeError("compute expects (DataFrame, symbol) or (date, stock_data)")
        result = _as_date_frame(df)
        context = market_context or self.context
        canonical = normalize_market(market or (context.market if context else "US"))
        if context is None:
            if canonical != "US":
                raise ValueError("CN_A requires an explicit MarketFactorContext")
            context = build_market_factor_context("US", data_dir=self.data_dir)
        if context.market != canonical:
            raise ValueError(f"market/context mismatch: {canonical} != {context.market}")
        return self._compute_context_factors(result, symbol, context, cn_a=canonical == "CN_A")

    def _compute_legacy_point(
        self,
        date: pd.Timestamp,
        stock_data: pd.DataFrame,
        *,
        stock_symbol: str | None = None,
    ) -> dict[str, float]:
        prices = _as_date_frame(stock_data)
        point = self._compute_context_factors(
            prices, stock_symbol or "", build_market_factor_context("US", data_dir=self.data_dir), cn_a=False
        )
        rows = point.loc[point["date"].eq(date)]
        if rows.empty:
            return {
                "vix_level": self.get_vix(date),
                "vix_regime_low": float(self.classify_vix_regime(date) == "low"),
                "vix_regime_med": float(self.classify_vix_regime(date) == "med"),
                "vix_regime_high": float(self.classify_vix_regime(date) == "high"),
                "rel_strength_vs_spy": self.compute_relative_strength(prices, date),
                "beta_20d": self.compute_rolling_beta(prices, date),
                "market_breadth": float("nan"),
                "sector_momentum": 0.0,
            }
        row = rows.iloc[-1]
        return {
            "vix_level": float(row["vix_level"]),
            "vix_regime_low": float(row["vix_regime"] == 0),
            "vix_regime_med": float(row["vix_regime"] == 1),
            "vix_regime_high": float(row["vix_regime"] == 2),
            "rel_strength_vs_spy": float(row["rel_strength_spy"]),
            "beta_20d": float(row["beta_20d"]),
            "market_breadth": float(row["market_breadth"]),
            "sector_momentum": float(row["sector_momentum"]),
        }

    def _compute_context_factors(
        self,
        df: pd.DataFrame,
        symbol: str,
        context: MarketFactorContext,
        *,
        cn_a: bool,
    ) -> pd.DataFrame:
        result = df.copy()
        benchmark = context.benchmark_frame.rename(columns={"close": "_market_close"})
        result = result.merge(benchmark[["date", "_market_close"]], on="date", how="left")
        result["_market_close"] = result["_market_close"].ffill()
        market_return_20 = result["_market_close"].pct_change(20, fill_method=None)
        stock_return_20 = result["close"].pct_change(20, fill_method=None)
        market_return_1 = result["_market_close"].pct_change(fill_method=None)
        result["market_breadth"] = self._market_breadth(result, context)
        beta = self._rolling_beta(result["close"], result["_market_close"])
        if not cn_a:
            result["beta_20d"] = beta
            result["sector_momentum"] = self._us_sector_momentum(
                result["close"], result["_market_close"], symbol
            )

        if cn_a:
            result["market_vol_level"] = market_return_1.rolling(20, min_periods=20).std() * np.sqrt(252)
            result["market_vol_regime"] = self._vol_regime(result["market_vol_level"])
            result["rel_strength_market"] = stock_return_20 - market_return_20
            result["market_beta_20d"] = beta
            result["breadth_up_ratio_1"] = result["market_breadth"]
            result["breadth_up_ratio_20"] = result["market_breadth"].rolling(20, min_periods=20).mean()
            result["market_return_1"] = market_return_1
            result["market_return_5"] = result["_market_close"].pct_change(5, fill_method=None)
            result["market_return_20"] = market_return_20
            result["market_drawdown_60"] = (
                result["_market_close"] / result["_market_close"].rolling(60, min_periods=1).max() - 1.0
            )
            result["market_constituent_count"] = self._constituent_count(result, context)
        else:
            if context.volatility_frame is None:
                result["vix_level"] = np.nan
                result["vix_regime"] = np.nan
            else:
                volatility = context.volatility_frame.rename(columns={"close": "_vix_level"})
                result = result.merge(volatility[["date", "_vix_level"]], on="date", how="left")
                result["vix_level"] = result["_vix_level"].ffill()
                result["vix_regime"] = self._vol_regime(result["vix_level"], thresholds=(15.0, 25.0))
            result["rel_strength_spy"] = stock_return_20 - market_return_20
            result["rel_strength_vs_spy"] = result["rel_strength_spy"]

        result = result.drop(columns=["_market_close", "_vix_level"], errors="ignore")
        return result

    @staticmethod
    def _vol_regime(series: pd.Series, thresholds: tuple[float, float] = (0.15, 0.25)) -> pd.Series:
        return pd.cut(series, bins=[-np.inf, thresholds[0], thresholds[1], np.inf], labels=[0, 1, 2]).astype(float)

    @staticmethod
    def _rolling_beta(stock: pd.Series, market: pd.Series, window: int = 20) -> pd.Series:
        stock_return = stock.pct_change(fill_method=None)
        market_return = market.pct_change(fill_method=None)
        variance = market_return.rolling(window).var()
        beta = stock_return.rolling(window).cov(market_return) / variance
        return beta.replace([np.inf, -np.inf], np.nan).fillna(1.0)

    @staticmethod
    def _market_breadth(frame: pd.DataFrame, context: MarketFactorContext) -> pd.Series:
        if context.breadth_frame is not None and "breadth_up_ratio_1" in context.breadth_frame:
            breadth = context.breadth_frame[["date", "breadth_up_ratio_1"]].rename(
                columns={"breadth_up_ratio_1": "_breadth"}
            )
            merged = frame[["date"]].merge(breadth, on="date", how="left")
            return merged["_breadth"].ffill()
        return pd.Series(np.nan, index=frame.index, dtype=float)

    @staticmethod
    def _constituent_count(frame: pd.DataFrame, context: MarketFactorContext) -> pd.Series:
        if context.breadth_frame is not None and "market_constituent_count" in context.breadth_frame:
            values = context.breadth_frame[["date", "market_constituent_count"]]
            return frame[["date"]].merge(values, on="date", how="left")["market_constituent_count"].ffill()
        return pd.Series(np.nan, index=frame.index, dtype=float)

    def get_vix(self, date: pd.Timestamp) -> float:
        values = self.vix_data
        if values.empty:
            return float("nan")
        eligible = values.loc[values["date"] <= pd.to_datetime(date)]
        return float(eligible["close"].iloc[-1]) if not eligible.empty else float("nan")

    def classify_vix_regime(self, date: pd.Timestamp) -> str:
        level = self.get_vix(date)
        if np.isnan(level):
            return "med"
        return "low" if level < 15 else "med" if level < 25 else "high"

    def compute_relative_strength(
        self, stock_data: pd.DataFrame, date: pd.Timestamp, window: int = 20
    ) -> float:
        stock = _as_date_frame(stock_data)
        spy = self.spy_data
        if spy.empty:
            return float("nan")
        end = pd.to_datetime(date)
        stock_window = stock.loc[stock["date"] <= end, ["date", "close"]].tail(window + 1)
        spy_window = spy.loc[spy["date"] <= end, ["date", "close"]].tail(window + 1)
        if len(stock_window) < 2 or len(spy_window) < 2:
            return float("nan")
        stock_return = stock_window["close"].iloc[-1] / stock_window["close"].iloc[0] - 1
        spy_return = spy_window["close"].iloc[-1] / spy_window["close"].iloc[0] - 1
        spy_vol = spy_window["close"].pct_change().dropna().std() * np.sqrt(252)
        if not np.isfinite(spy_vol):
            spy_vol = 0.01
        return float((stock_return - spy_return) / (spy_vol + 1e-8))

    def compute_rolling_beta(
        self, stock_data: pd.DataFrame, date: pd.Timestamp, window: int = 20
    ) -> float:
        stock = _as_date_frame(stock_data)
        spy = self.spy_data
        if spy.empty:
            return float("nan")
        end = pd.to_datetime(date)
        joined = stock.loc[stock["date"] <= end, ["date", "close"]].merge(
            spy.loc[spy["date"] <= end, ["date", "close"]], on="date", suffixes=("_stock", "_spy")
        ).tail(window + 1)
        if len(joined) < 3:
            return float("nan")
        market_return = joined["close_spy"].pct_change().dropna()
        stock_return = joined["close_stock"].pct_change().dropna()
        variance = market_return.var()
        return float(stock_return.cov(market_return) / variance) if variance >= 1e-8 else 1.0

    def compute_batch(
        self, stock_data: pd.DataFrame, dates: pd.DatetimeIndex | None = None
    ) -> pd.DataFrame:
        prices = _as_date_frame(stock_data)
        selected = pd.to_datetime(dates) if dates is not None else prices["date"]
        rows = []
        for date in selected:
            rows.append({
                "date": date,
                "vix_level": self.get_vix(date),
                "vix_regime_low": float(self.classify_vix_regime(date) == "low"),
                "vix_regime_med": float(self.classify_vix_regime(date) == "med"),
                "vix_regime_high": float(self.classify_vix_regime(date) == "high"),
                "rel_strength_vs_spy": self.compute_relative_strength(prices, date),
                "beta_20d": self.compute_rolling_beta(prices, date),
            })
        return pd.DataFrame(rows).set_index("date")

    def _us_sector_momentum(
        self, stock_close: pd.Series, market_close: pd.Series, symbol: str
    ) -> pd.Series:
        if self.sector_map.empty or not {"symbol", "sector"}.issubset(self.sector_map.columns):
            return pd.Series(0.0, index=stock_close.index)
        sector = self._get_sector(symbol)
        if sector == "Unknown":
            return pd.Series(0.0, index=stock_close.index)
        return (stock_close.pct_change(20, fill_method=None) - market_close.pct_change(20, fill_method=None)) * 0.5

    def _get_sector(self, symbol: str) -> str:
        matches = self.sector_map.loc[self.sector_map["symbol"].eq(str(symbol)), "sector"]
        return str(matches.iloc[0]) if not matches.empty else "Unknown"

    def compute_batch_panel(
        self,
        universe: Mapping[str, pd.DataFrame] | pd.DataFrame,
        dates: pd.DatetimeIndex | None = None,
        *,
        sector_map: Mapping[str, str] | None = None,
        market_context: MarketFactorContext | None = None,
        market: str = "US",
    ) -> pd.DataFrame:
        """Compute either the historical point panel or a symbol universe panel."""
        if isinstance(universe, pd.DataFrame):
            return self.compute_batch(universe, dates=dates)
        if dates is not None:
            raise TypeError("dates is only supported for a single stock DataFrame")
        context = market_context or self.context
        if context is None:
            context = build_market_factor_context(market, data_dir=self.data_dir)
        rows = []
        for symbol, frame in universe.items():
            factors = self.compute(frame, str(symbol), market=market, market_context=context)
            factors = factors.assign(symbol=str(symbol))
            columns = ["date", "symbol"] + [
                column for column in MACRO_FEATURE_COLUMNS if column in factors.columns
            ]
            rows.append(factors[columns])
        if not rows:
            return pd.DataFrame(columns=["date", "symbol", *MACRO_FEATURE_COLUMNS])
        return pd.concat(rows, ignore_index=True)

    def _load_optional(self, filename: str) -> pd.DataFrame:
        path = self.data_dir / filename
        if not path.is_file():
            return pd.DataFrame(columns=["date", "close"])
        return self._validate_macro_frame(pd.read_parquet(path), filename)

    @staticmethod
    def _validate_macro_frame(frame: pd.DataFrame, name: str) -> pd.DataFrame:
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

    def _load_sector_map(self) -> pd.DataFrame:
        path = self.data_dir / "us_sector_map.csv"
        if not path.is_file():
            return pd.DataFrame(columns=["symbol", "sector"])
        return pd.read_csv(path, dtype={"symbol": str})


_macro_factors_instance: Optional[MacroFactors] = None


def get_macro_factors() -> MacroFactors:
    global _macro_factors_instance
    if _macro_factors_instance is None:
        _macro_factors_instance = MacroFactors()
    return _macro_factors_instance


def add_macro_factors(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    return get_macro_factors().compute(df, symbol)
