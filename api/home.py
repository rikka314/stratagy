"""Read-only homepage data; reuse existing providers and their bounded caches."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/news")
def news(lang: Literal["zh", "en"] = "zh") -> dict:
    from ui.home import _FALLBACK_MARKET_HEADLINES, get_daily_market_headlines

    headlines = get_daily_market_headlines(lang)
    fallback = _FALLBACK_MARKET_HEADLINES[lang]
    return {
        "headlines": [{"title": title, "fallback": title in fallback} for title in headlines],
        "language": lang,
    }


@router.get("/market")
def market_snapshot() -> dict:
    from ui.home import get_home_market_snapshot

    return get_home_market_snapshot()


@router.get("/recommendations")
def recommendations(market: Literal["US", "CN_A"] = "US") -> dict:
    from ui.home import get_home_recommendation_pool

    return {"market": market, "items": get_home_recommendation_pool(market)}


@router.get("/candles")
def candles(
    symbol: str = Query(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.^-]+$"),
    market: Literal["US", "CN_A"] = "US",
) -> dict:
    from ui.home import _HOME_STOCK_CONFIG, get_home_stock_candles, get_home_recommendation_pool

    # Only the existing homepage watchlist is accepted; data-loader search is separate.
    stock = next((item for item in _HOME_STOCK_CONFIG if item["symbol"] == symbol.upper()
                  and item["request_symbol"].startswith("us") == (market == "US")), None)
    if stock is None:
        stock = next((item for item in get_home_recommendation_pool(market)
                      if item['symbol'].upper() == symbol.upper()), None)
    if stock is None:
        raise HTTPException(404, "Symbol is not in the homepage watchlist.")
    rows = get_home_stock_candles(stock["request_symbol"], stock["symbol"])
    return {"symbol": stock["symbol"], "market": market, "candles": rows,
            "status": "available" if rows else "unavailable"}
