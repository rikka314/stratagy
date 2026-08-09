from __future__ import annotations

import ui.home as home


class _FakeNewsResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "status": "ok",
            "articles": [
                {"title": "  Market closes higher after chip rally  "},
                {"title": "Market closes higher after chip rally"},
                {"title": "[Removed]"},
                {"title": "Bank shares rise as yields stabilize"},
                {"title": "Investors await the next inflation report"},
                {"title": "Energy stocks track a rebound in oil"},
                {"title": "This fifth valid headline is not displayed"},
            ],
        }


class _FakeTraditionalNewsResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "status": "ok",
            "articles": [
                {"title": "台積電下挫，市場關注半導體後續走勢"},
                {"title": "投資人等待聯準會公布最新決策"},
            ],
        }


class _FakeMarketResponse:
    content = (
        'v_usINX="200~S&P 500~.INX~7,300~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~~'
        '2026-08-06 10:56:00~15.00~0.21~0~0~USD";\n'
        'v_s_sh000001="1~上证指数~000001~3,650~18.25~0.50~0";\n'
        'v_usNVDA="200~NVIDIA~NVDA.OQ~205.00~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~~'
        '2026-08-06 10:56:00~4.00~2.00~0~0~USD";\n'
        'v_s_sh600519="1~贵州茅台~600519~1,500~15.00~1.01~0";'
    ).encode("gb18030")

    def raise_for_status(self) -> None:
        return None


class _FakeCandleResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "code": 0,
            "data": {
                "usMSFT.OQ": {
                    "day": [
                        ["2026-08-03", "490.00", "495.00", "498.00", "488.00", "100"],
                        ["2026-08-04", "495.00", "492.00", "499.00", "490.00", "120"],
                        ["2026-08-05", "492.00", "500.00", "501.00", "491.00", "150"],
                    ]
                }
            },
        }


def test_newsapi_request_uses_server_side_header_and_latest_sort(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeNewsResponse()

    monkeypatch.setattr(home, "_windows_system_proxies", lambda: {})
    monkeypatch.setattr(home.requests, "get", fake_get)

    headlines = home._request_newsapi_headlines(api_key="secret-key", language="en")

    assert headlines == (
        "Market closes higher after chip rally",
        "Bank shares rise as yields stabilize",
        "Investors await the next inflation report",
        "Energy stocks track a rebound in oil",
    )
    assert captured["url"] == home.NEWS_API_ENDPOINT
    assert captured["headers"]["X-Api-Key"] == "secret-key"
    assert "apiKey" not in captured["params"]
    assert captured["params"]["sortBy"] == "publishedAt"
    assert captured["params"]["language"] == "en"
    assert captured["timeout"] == home.NEWS_API_REQUEST_TIMEOUT


def test_windows_proxy_server_is_mapped_for_https_requests() -> None:
    assert home._parse_windows_proxy_server("127.0.0.1:7897") == {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897",
    }
    assert home._parse_windows_proxy_server("http=proxy.local:8080;https=secure.local:8443") == {
        "http": "http://proxy.local:8080",
        "https": "http://secure.local:8443",
    }


def test_newsapi_chinese_headlines_are_normalized_to_simplified(monkeypatch) -> None:
    monkeypatch.setattr(home, "_windows_system_proxies", lambda: {})
    monkeypatch.setattr(home.requests, "get", lambda *args, **kwargs: _FakeTraditionalNewsResponse())

    assert home._request_newsapi_headlines(api_key="secret-key", language="zh") == (
        "台积电下挫，市场关注半导体后续走势",
        "投资人等待联准会公布最新决策",
    )


def test_daily_headlines_fill_short_api_result_with_fallback(monkeypatch) -> None:
    monkeypatch.setattr(home, "_news_api_key", lambda: "configured-key")
    monkeypatch.setattr(
        home,
        "_cached_newsapi_headlines",
        lambda language, refresh_date, api_key_fingerprint, *, _api_key: (
            "API headline one",
            "API headline two",
        ),
    )

    headlines = home.get_daily_market_headlines("en")

    assert headlines[:2] == ("API headline one", "API headline two")
    assert len(headlines) == home.NEWS_API_HEADLINE_COUNT


def test_daily_headlines_fall_back_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(home, "_news_api_key", lambda: "")

    assert home.get_daily_market_headlines("zh") == home._FALLBACK_MARKET_HEADLINES["zh"]


def test_home_market_snapshot_parses_indices_and_ranks_liquid_watchlist(monkeypatch) -> None:
    monkeypatch.setattr(home, "_windows_system_proxies", lambda: {})
    monkeypatch.setattr(home.requests, "get", lambda *args, **kwargs: _FakeMarketResponse())

    snapshot = home._request_home_market_snapshot()

    assert snapshot["source"] == "tencent"
    assert snapshot["indices"][0]["price"] == 7300.0
    assert snapshot["indices"][0]["pct_change"] == 0.21
    assert snapshot["indices"][2]["price"] == 3650.0
    assert {item["symbol"] for item in snapshot["stocks"]} == {"NVDA", "600519"}
    assert [item["symbol"] for item in snapshot["leaders"]] == ["NVDA", "600519"]


def test_home_stock_daily_candles_use_exchange_qualified_us_symbol(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _FakeCandleResponse()

    monkeypatch.setattr(home, "_windows_system_proxies", lambda: {})
    monkeypatch.setattr(home.requests, "get", fake_get)

    candles = home._request_home_stock_candles(
        {"request_symbol": "usMSFT", "symbol": "MSFT"}
    )

    assert captured["url"] == home.HOME_STOCK_CANDLE_ENDPOINT
    assert captured["params"]["param"] == "usMSFT.OQ,day,,,20,qfq"
    assert candles[0] == {
        "date": "2026-08-03",
        "open": 490.0,
        "close": 495.0,
        "high": 498.0,
        "low": 488.0,
    }
    assert len(candles) == 3


def test_candlestick_chart_uses_sharp_real_ohlc_bodies() -> None:
    candles = home._parse_home_candle_payload(_FakeCandleResponse().json(), "usMSFT.OQ")

    markup = home._render_candlestick_chart(candles, "zh")

    assert "近 20 个交易日日 K" in markup
    assert 'class="market-candle-body is-up"' in markup
    assert 'class="market-candle-body is-down"' in markup
    assert "market-candle-body" in markup


def test_home_market_lens_has_three_data_scenes_without_fake_quotes() -> None:
    markup = home._render_market_lens(
        home._empty_home_market_snapshot(),
        "zh",
        recommendation_stocks=[],
    )

    assert "market-lens-indices" in markup
    assert "market-lens-leaders" in markup
    assert "market-lens-temperature" in markup
    assert "推荐股票与单股分析入口保持一致，不构成投资建议" in markup
    assert "待更新" in markup


def test_stock_cloud_renders_focus_and_scattered_relative_leaders() -> None:
    candles = home._parse_home_candle_payload(_FakeCandleResponse().json(), "usMSFT.OQ")
    pool = home._home_recommendation_pool(
        [{"symbol": "NVDA", "name": "英伟达", "price": 205, "pct_change": 2.0}],
        "US",
    )
    markup = home._render_stock_cloud(
        pool,
        "zh",
        market="US",
        focus_index=0,
        candles=candles,
    )

    assert "market-stock-cloud" in markup
    assert "单股分析推荐 · 日 K" in markup
    assert "英伟达" in markup
    assert "NVDA" in markup
    assert "market-candles" in markup
    assert "market-stock-orbit" not in markup


def test_home_stock_lens_uses_single_stock_recommendations_not_default_watchlist() -> None:
    pool = home._home_recommendation_pool(
        [{"symbol": "SOUN", "name": "SoundHound AI", "price": 13.2, "pct_change": 4.2}],
        "US",
    )

    cloud_markup = home._render_stock_cloud(pool, "en", market="US", focus_index=0)
    lens_markup = home._render_market_lens(
        home._empty_home_market_snapshot(),
        "en",
        recommendation_stocks=pool,
    )

    assert "SOUN" in cloud_markup
    assert "SOUN" in lens_markup
    assert "NVDA" not in cloud_markup
