import pytest
from fastapi import HTTPException

from api.home import candles, market_snapshot, news, recommendations


def test_fallback_news_is_explicit(monkeypatch):
    from ui import home

    monkeypatch.setattr(home, "get_daily_market_headlines", lambda lang: home._FALLBACK_MARKET_HEADLINES[lang])
    result = news("zh")
    assert result["headlines"]
    assert all(item["fallback"] for item in result["headlines"])


def test_market_fallback_does_not_fabricate_quotes(monkeypatch):
    from ui import home

    monkeypatch.setattr(home, "get_home_market_snapshot", home._empty_home_market_snapshot)
    assert all(item["price"] is None for item in market_snapshot()["indices"])


def test_recommendation_market_is_passed_explicitly(monkeypatch):
    from ui import home

    monkeypatch.setattr(home, "get_home_recommendation_pool", lambda market: ({"market": market},))
    assert recommendations("CN_A")["items"][0]["market"] == "CN_A"


def test_candles_reject_cross_market_and_unknown_symbols(monkeypatch):
    from ui import home
    monkeypatch.setattr(home, 'get_home_recommendation_pool', lambda _: ())
    with pytest.raises(HTTPException) as exc:
        candles("AAPL", "CN_A")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        candles("NOT-A-STOCK", "US")


def test_missing_candles_are_explicit(monkeypatch):
    from ui import home

    monkeypatch.setattr(home, "get_home_stock_candles", lambda *_: ())
    result = candles("AAPL", "US")
    assert result["status"] == "unavailable"
    assert not result["candles"]


def test_candles_support_dynamic_recommendation(monkeypatch):
    from ui import home
    monkeypatch.setattr(home, 'get_home_recommendation_pool', lambda _: ({'symbol':'BIDU','request_symbol':'usBIDU'},))
    monkeypatch.setattr(home, 'get_home_stock_candles', lambda request, symbol: ({'close':123,'symbol':symbol},))
    assert candles('BIDU', 'US')['candles'][0]['symbol'] == 'BIDU'
