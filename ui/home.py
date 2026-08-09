"""
首页模块
========
"""

from __future__ import annotations

import hashlib
import html
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
import streamlit as st
from opencc import OpenCC

from core.market_context import get_recommended_stocks
from core.perf import performance_span
from ui.theme import get_ui_language, render_html, render_route_nav


NEWS_API_ENDPOINT = "https://newsapi.org/v2/everything"
NEWS_API_CACHE_TTL_SECONDS = 24 * 60 * 60
NEWS_API_HEADLINE_COUNT = 4
NEWS_API_CACHE_REVISION = "simplified-zh-v1"
NEWS_API_REQUEST_TIMEOUT = (1.0, 2.0)
HOME_MARKET_ENDPOINT = "https://qt.gtimg.cn/q="
HOME_MARKET_CACHE_TTL_SECONDS = 15 * 60
HOME_MARKET_REQUEST_TIMEOUT = (1.0, 2.0)
HOME_STOCK_CANDLE_ENDPOINT = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
HOME_STOCK_CANDLE_CACHE_TTL_SECONDS = 15 * 60
HOME_STOCK_CANDLE_REQUEST_TIMEOUT = (1.0, 2.0)
HOME_STOCK_MARKET_STATE_KEY = "home_stock_focus_market"
HOME_STOCK_INDEX_STATE_KEY = "home_stock_focus_index"

_HOME_INDEX_CONFIG = (
    {"request_symbol": "usINX", "symbol": "SPX", "name_zh": "标普 500", "name_en": "S&P 500", "region_zh": "美国", "region_en": "US", "compact": False},
    {"request_symbol": "usIXIC", "symbol": "IXIC", "name_zh": "纳斯达克", "name_en": "Nasdaq", "region_zh": "美国", "region_en": "US", "compact": False},
    {"request_symbol": "s_sh000001", "symbol": "000001", "name_zh": "上证指数", "name_en": "Shanghai", "region_zh": "中国内地", "region_en": "Mainland China", "compact": True},
    {"request_symbol": "s_sz399001", "symbol": "399001", "name_zh": "深证成指", "name_en": "Shenzhen", "region_zh": "中国内地", "region_en": "Mainland China", "compact": True},
    {"request_symbol": "hkHSI", "symbol": "HSI", "name_zh": "恒生指数", "name_en": "Hang Seng", "region_zh": "中国香港", "region_en": "Hong Kong", "compact": False},
)

_HOME_STOCK_CONFIG = (
    {"request_symbol": "usNVDA", "symbol": "NVDA", "name_zh": "英伟达", "name_en": "NVIDIA", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usAMD", "symbol": "AMD", "name_zh": "超威半导体", "name_en": "AMD", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usMSFT", "symbol": "MSFT", "name_zh": "微软", "name_en": "Microsoft", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usAAPL", "symbol": "AAPL", "name_zh": "苹果", "name_en": "Apple", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usMETA", "symbol": "META", "name_zh": "Meta", "name_en": "Meta", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usAMZN", "symbol": "AMZN", "name_zh": "亚马逊", "name_en": "Amazon", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usGOOGL", "symbol": "GOOGL", "name_zh": "谷歌", "name_en": "Alphabet", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "usTSLA", "symbol": "TSLA", "name_zh": "特斯拉", "name_en": "Tesla", "region_zh": "美股", "region_en": "US", "compact": False},
    {"request_symbol": "s_sh600519", "symbol": "600519", "name_zh": "贵州茅台", "name_en": "Kweichow Moutai", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sz300750", "symbol": "300750", "name_zh": "宁德时代", "name_en": "CATL", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sh601318", "symbol": "601318", "name_zh": "中国平安", "name_en": "Ping An", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sz000858", "symbol": "000858", "name_zh": "五粮液", "name_en": "Wuliangye", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sh600036", "symbol": "600036", "name_zh": "招商银行", "name_en": "CMB", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sz002594", "symbol": "002594", "name_zh": "比亚迪", "name_en": "BYD", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sz300059", "symbol": "300059", "name_zh": "东方财富", "name_en": "East Money", "region_zh": "A 股", "region_en": "CN A", "compact": True},
    {"request_symbol": "s_sh600276", "symbol": "600276", "name_zh": "恒瑞医药", "name_en": "Hengrui Pharma", "region_zh": "A 股", "region_en": "CN A", "compact": True},
)

_TRADITIONAL_TO_SIMPLIFIED = OpenCC("t2s")

_FALLBACK_MARKET_HEADLINES = {
    "zh": (
        "微软创 2008 年以来最佳单日表现，科技股重新领涨美股。",
        "AMD 财报进入焦点，数据中心需求成为半导体估值的新锚。",
        "通胀担忧仍压在债券市场上，长端利率继续牵动成长股定价。",
        "AI 资本开支越过高峰后，市场开始追问：收入何时跟上投入？",
    ),
    "en": (
        "Microsoft posts its best day since 2008 as technology stocks retake the lead.",
        "AMD earnings move into focus as data-center demand resets the chip valuation debate.",
        "Inflation anxiety lingers in bonds, keeping long-term yields at the center of growth-stock pricing.",
        "After the AI spending surge, markets are asking when revenue will catch up with investment.",
    ),
}


def _news_api_key() -> str:
    return str(os.getenv("NEWS_API_KEY", "")).strip()


def _parse_windows_proxy_server(proxy_server: str) -> dict[str, str]:
    """Translate the Windows Internet Settings proxy value for requests."""
    value = str(proxy_server or "").strip()
    if not value:
        return {}

    if "=" not in value:
        proxy_url = value if "://" in value else f"http://{value}"
        return {"http": proxy_url, "https": proxy_url}

    proxies: dict[str, str] = {}
    for entry in value.split(";"):
        scheme, separator, address = entry.partition("=")
        normalized_scheme = scheme.strip().lower()
        normalized_address = address.strip()
        if not separator or normalized_scheme not in {"http", "https"} or not normalized_address:
            continue
        proxies[normalized_scheme] = (
            normalized_address
            if "://" in normalized_address
            else f"http://{normalized_address}"
        )
    if "http" in proxies and "https" not in proxies:
        proxies["https"] = proxies["http"]
    return proxies


def _windows_system_proxies() -> dict[str, str]:
    """Read the active per-user Windows proxy when requests has no proxy env."""
    if os.name != "nt" or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"):
        return {}
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            proxy_enabled = bool(winreg.QueryValueEx(key, "ProxyEnable")[0])
            proxy_server = str(winreg.QueryValueEx(key, "ProxyServer")[0])
    except (ImportError, OSError, TypeError, ValueError):
        return {}
    return _parse_windows_proxy_server(proxy_server) if proxy_enabled else {}


def _request_newsapi_headlines(*, api_key: str, language: str) -> tuple[str, ...]:
    normalized_language = "zh" if language == "zh" else "en"
    query = (
        '(股票 OR 股市 OR A股 OR 美股 OR 上证 OR 纳斯达克)'
        if normalized_language == "zh"
        else '(stocks OR "stock market" OR equities OR Nasdaq OR "S&P 500")'
    )
    now = datetime.now(timezone.utc)
    request_kwargs: dict[str, object] = {
        "params": {
            "q": query,
            "searchIn": "title,description",
            "language": normalized_language,
            "from": (now - timedelta(days=7)).isoformat(timespec="seconds"),
            "to": now.isoformat(timespec="seconds"),
            "sortBy": "publishedAt",
            "pageSize": 12,
            "page": 1,
        },
        "headers": {
            "X-Api-Key": api_key,
            "User-Agent": "StrategyLab/1.0",
        },
        "timeout": NEWS_API_REQUEST_TIMEOUT,
    }
    windows_proxies = _windows_system_proxies()
    if windows_proxies:
        request_kwargs["proxies"] = windows_proxies

    response = requests.get(
        NEWS_API_ENDPOINT,
        **request_kwargs,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(str(payload.get("message") or "NewsAPI request failed"))

    headlines: list[str] = []
    seen: set[str] = set()
    for article in payload.get("articles") or []:
        title = " ".join(str(article.get("title") or "").split()).strip()
        if not title or title == "[Removed]":
            continue
        if normalized_language == "zh":
            title = _TRADITIONAL_TO_SIMPLIFIED.convert(title)
        fingerprint = title.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        headlines.append(title)
        if len(headlines) >= NEWS_API_HEADLINE_COUNT:
            break
    return tuple(headlines)


@st.cache_data(ttl=NEWS_API_CACHE_TTL_SECONDS, show_spinner=False, max_entries=8)
def _cached_newsapi_headlines(
    language: str,
    refresh_date: str,
    api_key_fingerprint: str,
    *,
    _api_key: str,
) -> tuple[str, ...]:
    _ = refresh_date, api_key_fingerprint
    try:
        return _request_newsapi_headlines(api_key=_api_key, language=language)
    except (requests.RequestException, RuntimeError, ValueError):
        return ()


def get_daily_market_headlines(language: str | None = None) -> tuple[str, ...]:
    normalized_language = "zh" if (language or get_ui_language()) == "zh" else "en"
    fallback = _FALLBACK_MARKET_HEADLINES[normalized_language]
    api_key = _news_api_key()
    if not api_key:
        return fallback

    fetched = _cached_newsapi_headlines(
        normalized_language,
        f"{date.today().isoformat()}:{NEWS_API_CACHE_REVISION}",
        hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12],
        _api_key=api_key,
    )
    combined = list(fetched)
    combined.extend(headline for headline in fallback if headline not in combined)
    return tuple(combined[:NEWS_API_HEADLINE_COUNT])


def _empty_home_market_snapshot() -> dict[str, Any]:
    return {
        "source": "fallback",
        "retrieved_at": "",
        "indices": tuple({**item, "price": None, "pct_change": None} for item in _HOME_INDEX_CONFIG),
        "stocks": tuple({**item, "price": None, "pct_change": None} for item in _HOME_STOCK_CONFIG),
        "leaders": (),
    }


def _coerce_quote_number(value: object) -> float | None:
    try:
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number


def _parse_home_market_response(payload: str) -> dict[str, Any]:
    """Normalize Tencent quote rows for the home-page market lens."""
    configs = {
        item["request_symbol"]: item
        for item in (*_HOME_INDEX_CONFIG, *_HOME_STOCK_CONFIG)
    }
    parsed: dict[str, dict[str, Any]] = {}
    quote_times: list[str] = []
    for raw_line in str(payload or "").splitlines():
        key_part, separator, quoted = raw_line.partition("=")
        if not separator or '"' not in quoted:
            continue
        request_symbol = key_part.strip().removeprefix("v_")
        config = configs.get(request_symbol)
        if config is None:
            continue
        fields = quoted.split('"', 2)[1].split("~")
        price_index, pct_index = (3, 5) if config["compact"] else (3, 32)
        if len(fields) <= max(price_index, pct_index):
            continue
        price = _coerce_quote_number(fields[price_index])
        pct_change = _coerce_quote_number(fields[pct_index])
        if price is None or pct_change is None:
            continue
        parsed[request_symbol] = {**config, "price": price, "pct_change": pct_change}
        if not config["compact"] and len(fields) > 30 and fields[30].strip():
            quote_times.append(fields[30].strip())

    indices = tuple(
        parsed.get(item["request_symbol"], {**item, "price": None, "pct_change": None})
        for item in _HOME_INDEX_CONFIG
    )
    stocks = [parsed[item["request_symbol"]] for item in _HOME_STOCK_CONFIG if item["request_symbol"] in parsed]
    leaders = tuple(sorted(stocks, key=lambda item: item["pct_change"], reverse=True)[:4])
    return {
        "source": "tencent" if parsed else "fallback",
        "retrieved_at": max(quote_times, default=""),
        "indices": indices,
        "stocks": tuple(stocks),
        "leaders": leaders,
    }


def _request_home_market_snapshot() -> dict[str, Any]:
    symbols = ",".join(
        item["request_symbol"] for item in (*_HOME_INDEX_CONFIG, *_HOME_STOCK_CONFIG)
    )
    request_kwargs: dict[str, object] = {
        "headers": {
            "User-Agent": "Mozilla/5.0 StrategyLab/1.0",
            "Referer": "https://gu.qq.com/",
        },
        "timeout": HOME_MARKET_REQUEST_TIMEOUT,
    }
    windows_proxies = _windows_system_proxies()
    if windows_proxies:
        request_kwargs["proxies"] = windows_proxies
    response = requests.get(f"{HOME_MARKET_ENDPOINT}{symbols}", **request_kwargs)
    response.raise_for_status()
    return _parse_home_market_response(response.content.decode("gb18030", errors="replace"))


@st.cache_data(ttl=HOME_MARKET_CACHE_TTL_SECONDS, show_spinner=False, max_entries=4)
def get_home_market_snapshot() -> dict[str, Any]:
    try:
        return _request_home_market_snapshot()
    except (requests.RequestException, UnicodeError, ValueError):
        return _empty_home_market_snapshot()


def _home_candle_request_symbol(stock: dict[str, Any]) -> str:
    request_symbol = str(stock.get("request_symbol") or "")
    if request_symbol.startswith("s_"):
        return request_symbol.removeprefix("s_")
    if request_symbol.startswith("us"):
        return f"us{stock.get('symbol', '')}.OQ"
    return request_symbol


def _parse_home_candle_payload(
    payload: dict[str, Any],
    request_symbol: str,
) -> tuple[dict[str, Any], ...]:
    stock_payload = (payload.get("data") or {}).get(request_symbol) or {}
    rows = stock_payload.get("qfqday") or stock_payload.get("day") or ()
    candles: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        open_price = _coerce_quote_number(row[1])
        close_price = _coerce_quote_number(row[2])
        high_price = _coerce_quote_number(row[3])
        low_price = _coerce_quote_number(row[4])
        if None in {open_price, close_price, high_price, low_price}:
            continue
        candles.append(
            {
                "date": str(row[0]),
                "open": open_price,
                "close": close_price,
                "high": high_price,
                "low": low_price,
            }
        )
    return tuple(candles[-20:])


def _request_home_stock_candles(stock: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    request_symbol = _home_candle_request_symbol(stock)
    request_kwargs: dict[str, object] = {
        "params": {"param": f"{request_symbol},day,,,20,qfq"},
        "headers": {
            "User-Agent": "Mozilla/5.0 StrategyLab/1.0",
            "Referer": "https://gu.qq.com/",
        },
        "timeout": HOME_STOCK_CANDLE_REQUEST_TIMEOUT,
    }
    windows_proxies = _windows_system_proxies()
    if windows_proxies:
        request_kwargs["proxies"] = windows_proxies
    response = requests.get(HOME_STOCK_CANDLE_ENDPOINT, **request_kwargs)
    response.raise_for_status()
    return _parse_home_candle_payload(response.json(), request_symbol)


@st.cache_data(ttl=HOME_STOCK_CANDLE_CACHE_TTL_SECONDS, show_spinner=False, max_entries=12)
def get_home_stock_candles(
    request_symbol: str,
    symbol: str,
) -> tuple[dict[str, Any], ...]:
    stock = {"request_symbol": request_symbol, "symbol": symbol}
    try:
        return _request_home_stock_candles(stock)
    except (requests.RequestException, TypeError, ValueError):
        return ()


def _quote_state_class(pct_change: float | None) -> str:
    if pct_change is None:
        return "is-unavailable"
    if pct_change > 0:
        return "is-positive"
    if pct_change < 0:
        return "is-negative"
    return "is-flat"


def _format_market_value(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _format_market_pct(value: float | None, language: str = "zh") -> str:
    if value is None:
        return "待更新" if language == "zh" else "Pending"
    return f"{value:+.2f}%"


def _market_temperature(indices: tuple[dict[str, Any], ...], language: str) -> dict[str, Any]:
    available = [item for item in indices if item.get("pct_change") is not None]
    if not available:
        return {
            "tone": "unavailable",
            "word": "等待行情" if language == "zh" else "Awaiting quotes",
            "summary": "数据恢复后自动更新" if language == "zh" else "Updates automatically when data returns",
            "breadth": "—",
            "average": "—",
            "dispersion": "—",
        }

    changes = [float(item["pct_change"]) for item in available]
    positive_count = sum(change > 0 for change in changes)
    ratio = positive_count / len(changes)
    average = sum(changes) / len(changes)
    dispersion = max(changes) - min(changes)
    strongest = max(available, key=lambda item: float(item["pct_change"]))
    if average >= 0.35 and ratio >= 0.6:
        tone = "positive"
        word = "风险偏好回升" if language == "zh" else "Risk appetite rising"
    elif average <= -0.35 and ratio <= 0.4:
        tone = "negative"
        word = "市场情绪偏弱" if language == "zh" else "Risk tone softer"
    else:
        tone = "mixed"
        word = "市场分化运行" if language == "zh" else "Markets are mixed"
    strongest_name = strongest["name_zh" if language == "zh" else "name_en"]
    summary = (
        f"{strongest_name}相对领先，其余市场仍需分别判断"
        if language == "zh"
        else f"{strongest_name} leads; other markets still need separate reads"
    )
    return {
        "tone": tone,
        "word": word,
        "summary": summary,
        "breadth": f"{positive_count}/{len(available)}",
        "average": f"{average:+.2f}%",
        "dispersion": f"{dispersion:.2f} pt",
    }


def _home_recommendation_request_symbol(symbol: str, market: str) -> str:
    """Map a shared recommendation ticker to the Tencent K-line request format."""
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return ""
    if market != "CN_A":
        return f"us{normalized}"

    digits = "".join(character for character in normalized if character.isdigit())[-6:]
    if len(digits) != 6:
        return ""
    exchange = "sh" if digits.startswith(("5", "6", "9")) else "bj" if digits.startswith(("4", "8")) else "sz"
    return f"s_{exchange}{digits}"


def _home_recommendation_pool(
    recommendations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    market: str,
) -> list[dict[str, Any]]:
    """Keep the home stock lens on the same recommendation feed as Single Stock."""
    region = "CN A" if market == "CN_A" else "US"
    selected: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for item in recommendations:
        symbol = str(item.get("symbol") or "").strip().upper()
        request_symbol = _home_recommendation_request_symbol(symbol, market)
        if not symbol or not request_symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        name = str(item.get("name") or symbol).strip() or symbol
        selected.append(
            {
                "request_symbol": request_symbol,
                "symbol": symbol,
                "name_zh": name,
                "name_en": name,
                "region_zh": "A 股" if market == "CN_A" else "美股",
                "region_en": region,
                "price": _coerce_quote_number(item.get("price")),
                "pct_change": _coerce_quote_number(item.get("pct_change")),
            }
        )
        if len(selected) == 5:
            break
    return selected


@st.cache_data(ttl=HOME_MARKET_CACHE_TTL_SECONDS, show_spinner=False, max_entries=4)
def get_home_recommendation_pool(market: str) -> tuple[dict[str, Any], ...]:
    selected_market = "CN_A" if market == "CN_A" else "US"
    recommendation_context = get_recommended_stocks(
        "A" if selected_market == "CN_A" else "US",
        limit=5,
    )
    return tuple(
        _home_recommendation_pool(
            recommendation_context.get("items") or [],
            selected_market,
        )
    )


def _focused_home_stock(pool: list[dict[str, Any]], focus_index: int) -> dict[str, Any] | None:
    return pool[focus_index % len(pool)] if pool else None


def _render_stock_controls(stock_pool: list[dict[str, Any]], language: str) -> tuple[str, int]:
    market = str(st.session_state.get(HOME_STOCK_MARKET_STATE_KEY, "US"))
    market = "CN_A" if market == "CN_A" else "US"
    focus_index = int(st.session_state.get(HOME_STOCK_INDEX_STATE_KEY, 0) or 0)
    us_label = "美股" if language == "zh" else "US"
    cn_label = "A 股" if language == "zh" else "CN A"
    next_label = "换一只 ↗" if language == "zh" else "Next ↗"
    with st.container(key="home-stock-controls"):
        us_column, cn_column, next_column = st.columns([0.85, 0.85, 1.15], gap="small")
        if us_column.button(
            us_label,
            key="home_stock_market_us",
            type="primary" if market == "US" else "secondary",
            width="stretch",
        ):
            st.session_state[HOME_STOCK_MARKET_STATE_KEY] = "US"
            st.session_state[HOME_STOCK_INDEX_STATE_KEY] = 0
            st.rerun()
        if cn_column.button(
            cn_label,
            key="home_stock_market_cn",
            type="primary" if market == "CN_A" else "secondary",
            width="stretch",
        ):
            st.session_state[HOME_STOCK_MARKET_STATE_KEY] = "CN_A"
            st.session_state[HOME_STOCK_INDEX_STATE_KEY] = 0
            st.rerun()
        if next_column.button(
            next_label,
            key="home_stock_next",
            type="secondary",
            width="stretch",
        ):
            pool_size = max(1, len(stock_pool))
            st.session_state[HOME_STOCK_INDEX_STATE_KEY] = (focus_index + 1) % pool_size
            st.rerun()
    return market, focus_index


def _render_candlestick_chart(
    candles: tuple[dict[str, Any], ...],
    language: str,
) -> str:
    if len(candles) < 2:
        empty_label = "K 线暂不可用" if language == "zh" else "Candles unavailable"
        return f'<div class="market-candles-empty">{empty_label}</div>'

    width, height = 440.0, 104.0
    plot_top, plot_bottom = 7.0, 93.0
    low = min(float(candle["low"]) for candle in candles)
    high = max(float(candle["high"]) for candle in candles)
    price_range = max(high - low, max(abs(high), 1.0) * 0.002)
    low -= price_range * 0.08
    high += price_range * 0.08

    def y_position(value: float) -> float:
        return plot_top + ((high - value) / (high - low)) * (plot_bottom - plot_top)

    step = width / len(candles)
    body_width = max(4.0, min(10.0, step * 0.52))
    candle_markup: list[str] = []
    for index, candle in enumerate(candles):
        x = (index + 0.5) * step
        open_y = y_position(float(candle["open"]))
        close_y = y_position(float(candle["close"]))
        high_y = y_position(float(candle["high"]))
        low_y = y_position(float(candle["low"]))
        body_y = min(open_y, close_y)
        body_height = max(2.0, abs(close_y - open_y))
        state = "is-up" if float(candle["close"]) >= float(candle["open"]) else "is-down"
        candle_markup.append(
            f'<span class="market-candle-wick {state}" aria-hidden="true" '
            f'style="left:{x / width * 100:.2f}%;top:{high_y / height * 100:.2f}%;'
            f'height:{(low_y - high_y) / height * 100:.2f}%;">&nbsp;</span>'
            f'<span class="market-candle-body {state}" aria-hidden="true" '
            f'style="left:{x / width * 100:.2f}%;top:{body_y / height * 100:.2f}%;'
            f'width:{body_width:.2f}px;height:{body_height / height * 100:.2f}%;">&nbsp;</span>'
        )
    grid_lines = "".join(
        f'<span class="market-candle-grid-line" aria-hidden="true" '
        f'style="top:{y / height * 100:.2f}%;">&nbsp;</span>'
        for y in (plot_top, (plot_top + plot_bottom) / 2, plot_bottom)
    )
    chart_label = "近 20 个交易日日 K" if language == "zh" else "Last 20 sessions · daily candles"
    return f"""
    <div class="market-candles" aria-label="{chart_label}">
      {grid_lines}
      {''.join(candle_markup)}
    </div>
    """


def _render_stock_cloud(
    pool: list[dict[str, Any]],
    language: str,
    *,
    market: str,
    focus_index: int,
    candles: tuple[dict[str, Any], ...] = (),
) -> str:
    label_key = "name_zh" if language == "zh" else "name_en"
    if not pool:
        empty_label = "推荐股票暂不可用" if language == "zh" else "Recommendations unavailable"
        return f'<section class="market-stock-cloud"><p class="market-stock-empty">{empty_label}</p></section>'

    focus_index %= len(pool)
    focus = pool[focus_index]
    satellite_items = [item for index, item in enumerate(pool) if index != focus_index]
    day_seed = hashlib.sha256(
        f"{date.today().isoformat()}:{market}:{focus['symbol']}".encode("utf-8")
    ).digest()
    slot_order = sorted(range(1, 5), key=lambda slot: day_seed[slot])
    satellites = "".join(
        f"""
    <span class="market-stock-orbit slot-{slot} {_quote_state_class(item.get('pct_change'))}">
      <strong>{html.escape(str(item[label_key]))}</strong>
      <small>{html.escape(str(item['symbol']))}</small>
      <span>{_format_market_pct(item.get('pct_change'), language)}</span>
    </span>
        """
        for item, slot in zip(satellite_items, slot_order)
    )
    focus_name = html.escape(str(focus[label_key]))
    focus_state = _quote_state_class(focus.get("pct_change"))
    period_label = "单股分析推荐 · 日 K" if language == "zh" else "Single-stock recommendations · daily candles"
    market_label = "美股" if market == "US" and language == "zh" else (
        "A 股" if market == "CN_A" and language == "zh" else market
    )
    return f"""
<section class="market-stock-cloud" aria-label="{'近期强势股票' if language == 'zh' else 'Recent strong stocks'}">
  <div class="market-stock-focus {focus_state}">
    <span class="market-stock-eyebrow">{period_label}</span>
    <strong class="market-stock-company">{focus_name}</strong>
    <div class="market-stock-focus-line">
      <span>{html.escape(str(focus['symbol']))} · {market_label}</span>
      <b>{_format_market_pct(focus.get('pct_change'), language)}</b>
    </div>
    {_render_candlestick_chart(candles, language)}
  </div>
  {satellites}
</section>
    """


def _render_market_lens(
    snapshot: dict[str, Any],
    language: str,
    *,
    recommendation_stocks: list[dict[str, Any]],
) -> str:
    indices = tuple(snapshot.get("indices") or ())
    leaders = tuple(recommendation_stocks)
    temperature = _market_temperature(indices, language)
    label_key = "name_zh" if language == "zh" else "name_en"
    region_key = "region_zh" if language == "zh" else "region_en"

    index_items = "".join(
        f"""
        <div class="market-index-item {_quote_state_class(item.get('pct_change'))}">
          <span class="market-item-region">{html.escape(str(item[region_key]))}</span>
          <strong>{html.escape(str(item[label_key]))}</strong>
          <span class="market-item-quote">{_format_market_value(item.get('price'))}</span>
          <span class="market-item-change">{_format_market_pct(item.get('pct_change'), language)}</span>
        </div>
        """
        for item in indices
    )
    leader_items = "".join(
        f"""
        <div class="market-leader-item {_quote_state_class(item.get('pct_change'))}">
          <span class="market-leader-rank">{rank:02d}</span>
          <span class="market-leader-name"><strong>{html.escape(str(item['symbol']))}</strong>{html.escape(str(item[label_key]))}</span>
          <span class="market-leader-region">{html.escape(str(item[region_key]))}</span>
          <span class="market-leader-price">{_format_market_value(item.get('price'))}</span>
          <span class="market-item-change">{_format_market_pct(item.get('pct_change'), language)}</span>
        </div>
        """
        for rank, item in enumerate(leaders, start=1)
    )
    if not leader_items:
        leader_items = (
            '<p class="market-leaders-empty">'
            + ("推荐股票暂不可用" if language == "zh" else "Recommendations unavailable")
            + "</p>"
        )
    source_text = (
        "腾讯行情 · 15 分钟缓存" if language == "zh" else "Tencent Quotes · 15-minute cache"
    ) if snapshot.get("source") == "tencent" else (
        "行情暂不可用 · 自动重试" if language == "zh" else "Quotes unavailable · auto retry"
    )
    as_of = str(snapshot.get("retrieved_at") or "").replace("/", "-")
    source_meta = f"{source_text}{' · ' + html.escape(as_of) if as_of else ''}"
    return f"""
<section class="market-lens" aria-label="{'市场实时概览' if language == 'zh' else 'Live market overview'}">
  <div class="market-lens-scene market-lens-indices" style="--scene-delay:0s;">
    <div class="market-lens-heading">
      <span>{'01 / 双市场指数' if language == 'zh' else '01 / MARKET INDICES'}</span>
      <strong>{'先判断市场，再进入个股。' if language == 'zh' else 'Read the market before the stock.'}</strong>
    </div>
    <div class="market-index-strip">{index_items}</div>
  </div>

  <div class="market-lens-scene market-lens-leaders" style="--scene-delay:-16s;">
    <div class="market-lens-heading">
      <span>{'02 / 单股推荐观察' if language == 'zh' else '02 / SINGLE-STOCK RECOMMENDATIONS'}</span>
      <strong>{'与单股分析入口使用同一推荐来源。' if language == 'zh' else 'The same recommendation feed as the Single Stock entry.'}</strong>
    </div>
    <div class="market-leader-list">{leader_items}</div>
  </div>

  <div class="market-lens-scene market-lens-temperature" style="--scene-delay:-8s;">
    <div class="market-lens-heading">
      <span>{'03 / 市场温度' if language == 'zh' else '03 / MARKET TEMPERATURE'}</span>
      <strong>{'把分散报价压缩成一个市场读数。' if language == 'zh' else 'Compress the tape into one market read.'}</strong>
    </div>
    <div class="market-temperature-body is-{temperature['tone']}">
      <div class="market-temperature-statement">
        <strong>{html.escape(str(temperature['word']))}</strong>
        <span>{html.escape(str(temperature['summary']))}</span>
      </div>
      <dl class="market-temperature-metrics">
        <div><dt>{'上涨指数' if language == 'zh' else 'Indices up'}</dt><dd>{temperature['breadth']}</dd></div>
        <div><dt>{'平均涨跌' if language == 'zh' else 'Average'}</dt><dd>{temperature['average']}</dd></div>
        <div><dt>{'市场离散' if language == 'zh' else 'Dispersion'}</dt><dd>{temperature['dispersion']}</dd></div>
      </dl>
    </div>
  </div>

  <div class="market-lens-progress" aria-hidden="true">
    <i style="--step-delay:0s;"></i><i style="--step-delay:-16s;"></i><i style="--step-delay:-8s;"></i>
  </div>
  <p class="market-lens-source">{source_meta} · {'推荐股票与单股分析入口保持一致，不构成投资建议' if language == 'zh' else 'Recommendations match the Single Stock entry and are not investment advice'}</p>
</section>
    """


def _render_headline_track(headlines: tuple[str, ...]) -> str:
    return "".join(
        (
            f"<span class='market-news-item' style='animation-delay:{index * 6 - 0.4:.1f}s;' "
            f"aria-hidden='{'false' if index == 0 else 'true'}'>{html.escape(headline)}</span>"
        )
        for index, headline in enumerate(headlines)
    )


def _loading_label(language: str) -> str:
    return "正在加载最新市场数据" if language == "zh" else "Loading latest market data"


def _load_home_headlines(language: str) -> tuple[str, ...]:
    with performance_span("home", "headlines", source="newsapi" if _news_api_key() else "fallback"):
        try:
            return get_daily_market_headlines(language)
        except Exception:
            return _FALLBACK_MARKET_HEADLINES["zh" if language == "zh" else "en"]


def _load_home_stock_cloud_data(
    language: str,
    selected_market: str,
) -> tuple[list[dict[str, Any]], str, int, tuple[dict[str, Any], ...]]:
    with performance_span("home", "recommendations", market=selected_market):
        try:
            recommendation_pool = list(get_home_recommendation_pool(selected_market))
        except Exception:
            recommendation_pool = []
    focus_market, focus_index = _home_focus_state(recommendation_pool)
    focus_stock = _focused_home_stock(recommendation_pool, focus_index)
    with performance_span(
        "home",
        "candles",
        has_focus_stock=focus_stock is not None,
        source="tencent" if focus_stock else "not_requested",
    ):
        try:
            candles = (
                get_home_stock_candles(
                    str(focus_stock.get("request_symbol") or ""),
                    str(focus_stock.get("symbol") or ""),
                )
                if focus_stock
                else ()
            )
        except Exception:
            candles = ()
    return recommendation_pool, focus_market, focus_index, candles


def _load_home_market_lens_data(selected_market: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with performance_span("home", "market_snapshot", source="tencent"):
        try:
            market_snapshot = get_home_market_snapshot()
        except Exception:
            market_snapshot = _empty_home_market_snapshot()
    try:
        recommendation_pool = list(get_home_recommendation_pool(selected_market))
    except Exception:
        recommendation_pool = []
    return market_snapshot, recommendation_pool


def _render_home_identity_markup(
    language: str,
    headlines: tuple[str, ...],
    *,
    loading: bool = False,
    fragment: bool = False,
) -> str:
    platform_name = "股票策略分析平台" if language == "zh" else "Stock Strategy Analysis Platform"
    headline_label = "最新股票新闻" if language == "zh" else "Latest stock-market news"
    news_source = "newsapi" if _news_api_key() else "fallback"
    state_class = " home-loading-slot" if loading else (" home-headlines-fragment" if fragment else "")
    heading_id = "" if fragment else ' id="market-platform-title"'
    labelled_by = "" if fragment else ' aria-labelledby="market-platform-title"'
    return f"""
  <section class="market-identity{state_class}"{labelled_by}>
    <h1{heading_id} class="market-platform-title">{platform_name}</h1>
    <div class="market-news-ticker" role="region" aria-label="{headline_label}" data-news-source="{news_source}">
      {_render_headline_track(headlines)}
    </div>
  </section>
    """


def _render_home_loading_stage_markup(language: str, selected_market: str) -> str:
    loading_label = html.escape(_loading_label(language))
    loading_headlines = _FALLBACK_MARKET_HEADLINES["zh" if language == "zh" else "en"]
    return f"""
<main class="home-market-stage" aria-busy="true">
  {_render_home_identity_markup(language, loading_headlines, loading=True)}
  <section class="market-stock-cloud home-loading-slot" aria-label="{loading_label}">
    <p class="market-stock-empty">{loading_label}</p>
  </section>
  <section class="market-lens home-loading-slot" aria-label="{loading_label}">
    <div class="market-lens-scene market-lens-indices is-loading">
      <div class="market-lens-heading">
        <span>{'市场数据' if language == 'zh' else 'MARKET DATA'}</span>
        <strong>{loading_label}</strong>
      </div>
    </div>
    <div class="market-lens-scene market-lens-leaders is-loading" aria-hidden="true"></div>
    <div class="market-lens-scene market-lens-temperature is-loading" aria-hidden="true"></div>
    <p class="market-lens-source">{html.escape(selected_market)}</p>
  </section>
</main>
    """


@st.fragment(parallel=True)
def _render_home_headlines_fragment(language: str) -> None:
    render_html(
        _render_home_identity_markup(
            language,
            _load_home_headlines(language),
            fragment=True,
        ),
        localize=False,
    )


@st.fragment(parallel=True)
def _render_home_stock_cloud_fragment(language: str, selected_market: str) -> None:
    recommendation_pool, focus_market, focus_index, candles = _load_home_stock_cloud_data(
        language,
        selected_market,
    )
    render_html(
        _render_stock_cloud(
            recommendation_pool,
            language,
            market=focus_market,
            focus_index=focus_index,
            candles=candles,
        ),
        localize=False,
    )
    _render_stock_controls(recommendation_pool, language)


@st.fragment(parallel=True)
def _render_home_market_lens_fragment(language: str, selected_market: str) -> None:
    market_snapshot, lens_recommendations = _load_home_market_lens_data(selected_market)
    render_html(
        _render_market_lens(
            market_snapshot,
            language,
            recommendation_stocks=lens_recommendations,
        ),
        localize=False,
    )


def _render_home_stage_markup(
    language: str,
    *,
    headlines: tuple[str, ...],
    recommendation_pool: list[dict[str, Any]],
    focus_market: str,
    focus_index: int,
    candles: tuple[dict[str, Any], ...],
    market_snapshot: dict[str, Any],
    lens_recommendations: list[dict[str, Any]],
) -> str:
    headline_label = "最新股票新闻" if language == "zh" else "Latest stock-market news"
    return f"""
<main class="home-market-stage" aria-label="{headline_label}">
  {_render_home_identity_markup(language, headlines)}
  {_render_stock_cloud(recommendation_pool, language, market=focus_market, focus_index=focus_index, candles=candles)}
  {_render_market_lens(market_snapshot, language, recommendation_stocks=lens_recommendations)}
</main>
    """


def _home_focus_state(stock_pool: list[dict[str, Any]]) -> tuple[str, int]:
    market = str(st.session_state.get(HOME_STOCK_MARKET_STATE_KEY, "US"))
    market = "CN_A" if market == "CN_A" else "US"
    focus_index = int(st.session_state.get(HOME_STOCK_INDEX_STATE_KEY, 0) or 0)
    if stock_pool:
        focus_index %= len(stock_pool)
    return market, focus_index


def render_home_page() -> None:
    """Render the stable home shell before bounded parallel data fragments."""
    render_route_nav("home")
    language = get_ui_language()
    selected_market = "CN_A" if st.session_state.get(HOME_STOCK_MARKET_STATE_KEY) == "CN_A" else "US"
    with st.container(key="home-stage-shell"):
        render_html(
            _render_home_loading_stage_markup(language, selected_market),
            localize=False,
        )
        _render_home_headlines_fragment(language)
        _render_home_stock_cloud_fragment(language, selected_market)
        _render_home_market_lens_fragment(language, selected_market)
