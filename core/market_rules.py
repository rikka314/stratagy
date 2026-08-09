"""Market-specific execution assumptions used by the backtest engine."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from math import isfinite
from typing import Iterator, Literal


CanonicalMarket = Literal["US", "CN_A"]

_MARKET_ALIASES: dict[str, CanonicalMarket] = {
    "US": "US",
    "CN_A": "CN_A",
    "CN": "CN_A",
    "A": "CN_A",
}

DEFAULT_EXECUTION_COST_BPS: dict[CanonicalMarket, tuple[float, float]] = {
    "US": (1.0, 2.0),
    "CN_A": (3.0, 5.0),
}

_ACTIVE_EXECUTION_CONFIG: ContextVar["MarketExecutionConfig | None"] = ContextVar(
    "active_execution_config",
    default=None,
)


def normalize_market(market: str) -> CanonicalMarket:
    """Return a canonical market identifier or raise for an unsupported market."""
    if not isinstance(market, str):
        raise ValueError("market must be a string")

    normalized = _MARKET_ALIASES.get(market.strip().upper())
    if normalized is None:
        raise ValueError(f"Unsupported market `{market}`; expected US or CN_A")
    return normalized


@dataclass(frozen=True, slots=True)
class MarketExecutionConfig:
    """Proportional execution costs for a single equity market.

    Costs are expressed in basis points and are charged once per unit of daily
    position change.  A caller must opt in by passing this config to
    :func:`core.backtest.simulate_strategy`; omitted configs preserve legacy
    zero-cost behavior exactly.
    """

    market: CanonicalMarket | str
    commission_bps: float
    slippage_bps: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", normalize_market(self.market))

        for field_name in ("commission_bps", "slippage_bps"):
            value = float(getattr(self, field_name))
            if not isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be a finite, non-negative number")
            object.__setattr__(self, field_name, value)

    @property
    def total_cost_rate(self) -> float:
        """Combined commission and slippage as a decimal return rate."""
        return (self.commission_bps + self.slippage_bps) / 10_000


def default_execution_config(market: str) -> MarketExecutionConfig:
    """Build the frozen default research-cost configuration for a market."""
    canonical_market = normalize_market(market)
    commission_bps, slippage_bps = DEFAULT_EXECUTION_COST_BPS[canonical_market]
    return MarketExecutionConfig(canonical_market, commission_bps, slippage_bps)


def get_active_execution_config() -> MarketExecutionConfig | None:
    """Return the opt-in execution configuration for the current run context."""
    return _ACTIVE_EXECUTION_CONFIG.get()


@contextmanager
def using_execution_config(config: MarketExecutionConfig | None) -> Iterator[None]:
    """Apply a cost configuration to nested backtests without changing UI defaults."""
    token = _ACTIVE_EXECUTION_CONFIG.set(config)
    try:
        yield
    finally:
        _ACTIVE_EXECUTION_CONFIG.reset(token)
