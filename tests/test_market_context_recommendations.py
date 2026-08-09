from __future__ import annotations

import core.market_context as market_context


class _FakeResponse:
    def __init__(self, records) -> None:
        self._records = records

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"Result": {"list": {"body": self._records}}}


def _uncached(func):
    return getattr(func, "__wrapped__", func)


def test_baidu_hot_search_normalizes_and_sorts_a_share_codes(monkeypatch) -> None:
    records = [
        {"code": "SZ000725", "name": "京东方Ａ", "heat": "200", "pxChangeRate": "+1.25%"},
        {"code": "601288", "name": "农业银行", "heat": "900", "pxChangeRate": "-0.40%"},
        {"code": "", "name": "无代码", "heat": "9999", "pxChangeRate": "+9.99%"},
    ]
    monkeypatch.setattr(
        market_context.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(records),
    )

    result = market_context._load_baidu_hot_search_recommendations("A", limit=2)

    assert [item["symbol"] for item in result] == ["601288", "000725"]
    assert [item["rank"] for item in result] == [1, 2]
    assert result[0]["heat"] == 900
    assert result[0]["pct_change"] == -0.4


def test_baidu_hot_search_keeps_us_tickers_and_limit(monkeypatch) -> None:
    records = [
        {"code": "nvda", "name": "NVIDIA", "heat": "1200", "pxChangeRate": "+0.50%"},
        {"code": "SOUN", "name": "SoundHound AI", "heat": "1800", "pxChangeRate": "+4.20%"},
    ]
    monkeypatch.setattr(
        market_context.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(records),
    )

    result = market_context._load_baidu_hot_search_recommendations("US", limit=1)

    assert result == [
        {
            "symbol": "SOUN",
            "name": "SoundHound AI",
            "label": "SOUN SoundHound AI",
            "price": None,
            "pct_change": 4.2,
            "heat": 1800,
            "rank": 1,
        }
    ]


def test_recommendations_prefer_hot_search_without_loading_movers(monkeypatch) -> None:
    hot_items = [{"symbol": "NVDA", "name": "NVIDIA", "heat": 100}]
    monkeypatch.setattr(
        market_context,
        "_load_baidu_hot_search_recommendations",
        lambda market, limit: hot_items,
    )
    monkeypatch.setattr(
        market_context,
        "_load_us_famous_recommendations",
        lambda limit: (_ for _ in ()).throw(AssertionError("movers should not load")),
    )

    result = _uncached(market_context.get_recommended_stocks)("US", 10)

    assert result["source_kind"] == market_context.RECOMMENDATION_SOURCE_HOT_SEARCH
    assert result["items"] == hot_items


def test_recommendations_fall_back_to_live_movers(monkeypatch) -> None:
    mover_items = [{"symbol": "600519", "name": "贵州茅台", "pct_change": 2.5}]
    monkeypatch.setattr(
        market_context,
        "_load_baidu_hot_search_recommendations",
        lambda market, limit: [],
    )
    monkeypatch.setattr(market_context, "_load_a_top_movers", lambda limit: mover_items)

    result = _uncached(market_context.get_recommended_stocks)("A", 10)

    assert result["source_kind"] == market_context.RECOMMENDATION_SOURCE_A_MOVERS
    assert result["items"] == mover_items


def test_recommendations_return_explicit_empty_state_when_all_sources_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        market_context,
        "_load_baidu_hot_search_recommendations",
        lambda market, limit: [],
    )
    monkeypatch.setattr(market_context, "_load_us_famous_recommendations", lambda limit: [])

    result = _uncached(market_context.get_recommended_stocks)("US", 10)

    assert result == {
        "source_kind": market_context.RECOMMENDATION_SOURCE_UNAVAILABLE,
        "source_label": "暂时无法获取推荐股票",
        "items": [],
    }
    assert not hasattr(market_context, "_fallback_recommendations")


def test_us_famous_recommendations_use_one_total_deadline(monkeypatch) -> None:
    import time

    class FakeAkshare:
        @staticmethod
        def stock_us_famous_spot_em(category):
            time.sleep(0.12)
            return None

    monkeypatch.setattr(market_context, "_load_akshare", lambda: FakeAkshare)
    monkeypatch.setattr(market_context, "RECOMMENDATION_TOTAL_DEADLINE_SECONDS", 0.02)

    started = time.perf_counter()
    result = market_context._load_us_famous_recommendations(limit=5)
    elapsed = time.perf_counter() - started

    assert result == []
    assert elapsed < 0.09


def test_build_market_context_uses_one_total_wait_for_indices_and_recommendations(monkeypatch) -> None:
    import time

    monkeypatch.setattr(market_context, "MARKET_CONTEXT_REQUEST_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(
        market_context,
        "get_market_indices",
        lambda market: (time.sleep(0.12), [])[1],
    )
    monkeypatch.setattr(
        market_context,
        "get_recommended_stocks",
        lambda market, limit: (time.sleep(0.12), {
            "source_kind": market_context.RECOMMENDATION_SOURCE_UNAVAILABLE,
            "source_label": "暂时无法获取推荐股票",
            "items": [],
        })[1],
    )

    started = time.perf_counter()
    result = market_context.build_market_context("US", limit=10)
    elapsed = time.perf_counter() - started

    assert result["indices"] == []
    assert result["recommendation_source_kind"] == market_context.RECOMMENDATION_SOURCE_UNAVAILABLE
    assert elapsed < 0.16


    monkeypatch.setattr(market_context, "get_market_indices", lambda market: [])
    monkeypatch.setattr(
        market_context,
        "get_recommended_stocks",
        lambda market, limit: {
            "source_kind": market_context.RECOMMENDATION_SOURCE_HOT_SEARCH,
            "source_label": "今日热搜综合热度",
            "items": [
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA",
                    "price": None,
                    "pct_change": 1.25,
                    "heat": 123456,
                }
            ],
        },
    )

    result = market_context.build_market_context("US", limit=10)

    assert result["recommendation_source_kind"] == market_context.RECOMMENDATION_SOURCE_HOT_SEARCH
    assert result["recommendations"][0]["heat_text"] == "123,456"
    assert result["recommendations"][0]["pct_text"] == "+1.25%"

