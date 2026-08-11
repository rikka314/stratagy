"""
数据预处理模块
==============
股票数据的获取、加载和标准化。
"""

import contextlib
import io
import os
import unicodedata
from typing import Callable, Iterable

import akshare as ak
import pandas as pd
from requests.exceptions import ProxyError, RequestException, Timeout
import streamlit as st

from core.config import DATA_DIR

REQUIRED_OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close"]
CATALOG_DIR = os.path.join(os.path.dirname(__file__), "catalogs")
A_STOCK_CATALOG_SNAPSHOT = os.path.join(CATALOG_DIR, "a_stock_catalog.csv")
US_STOCK_CATALOG_SNAPSHOT = os.path.join(CATALOG_DIR, "us_stock_catalog.csv")
OPTIONAL_NUMERIC_COLUMNS = [
    "amount",
    "amplitude_pct",
    "pct_change",
    "price_change",
    "turnover_pct",
]
COMMON_COLUMN_ALIASES = {
    "trade_date": "date",
    "datetime": "date",
    "日期": "date",
    "date": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "vol": "volume",
    "volumn": "volume",
    "成交量": "volume",
    "成交量(手)": "volume",
    "股票代码": "symbol",
    "代码": "symbol",
    "成交额": "amount",
    "成交额(元)": "amount",
    "振幅": "amplitude_pct",
    "涨跌幅": "pct_change",
    "涨跌额": "price_change",
    "换手率": "turnover_pct",
}


def _normalize_adjust(adjust: str) -> str:
    """统一复权方式字段，兼容 UI 中的 none 取值。"""
    adjust_value = str(adjust or "none").strip().lower()
    return adjust_value or "none"


def _normalize_symbol(symbol: str, market: str) -> str:
    """统一股票代码格式。A 股保留 6 位数字，美股转大写。"""
    normalized_symbol = str(symbol or "").strip().upper()
    if market == "CN_A":
        digits = "".join(ch for ch in normalized_symbol if ch.isdigit())
        if not digits:
            return ""
        return digits.zfill(6)[-6:]
    return normalized_symbol


def _normalize_search_text(text: str) -> str:
    """统一搜索文本，兼容全角字符和名称中的空格。"""
    normalized_text = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    return "".join(normalized_text.split())


def _normalize_market_key(market: str | None) -> str:
    """统一市场标识，兼容 UI 中的 A / US 写法。"""
    market_value = str(market or "US").strip().upper()
    if market_value in {"A", "CN_A", "CN"}:
        return "CN_A"
    return "US"


def _coerce_numeric_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """将指定列转换为数值类型。"""
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _write_market_cache(df: pd.DataFrame, symbol: str, *, report_errors: bool = True) -> None:
    """将已标准化的行情写入临时缓存，失败时不影响主流程。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, f"{str(symbol).strip().lower()}_daily.csv")

    try:
        df.to_csv(cache_path, index=False)
    except Exception as exc:
        if report_errors:
            st.warning(f"{symbol} 缓存写入失败：{exc}")


def _get_a_symbol_with_exchange(symbol: str) -> str:
    """为腾讯/新浪等数据源补全 A 股交易所前缀。"""
    normalized_symbol = _normalize_symbol(symbol, "CN_A")
    if normalized_symbol.startswith(("4", "8")):
        return f"bj{normalized_symbol}"
    if normalized_symbol.startswith(("6", "9")):
        return f"sh{normalized_symbol}"
    return f"sz{normalized_symbol}"


def _read_catalog_snapshot(snapshot_path: str, required_columns: list[str]) -> pd.DataFrame:
    """读取随代码部署的股票索引快照。"""
    if not os.path.exists(snapshot_path):
        return pd.DataFrame(columns=required_columns)

    try:
        df = pd.read_csv(snapshot_path, dtype=str)
    except Exception:
        return pd.DataFrame(columns=required_columns)

    if df.empty:
        return pd.DataFrame(columns=required_columns)

    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        return pd.DataFrame(columns=required_columns)

    return df[required_columns].fillna("")


def _finalize_market_dataframe(
    df: pd.DataFrame,
    *,
    symbol: str,
    market: str,
    currency: str,
    adjust: str,
    volume_multiplier: float = 1.0,
    allow_first_column_as_date: bool = False,
) -> pd.DataFrame:
    """
    将市场原始行情统一收口为项目标准结构。
    """
    df = standardize_columns(df)

    if "date" not in df.columns and allow_first_column_as_date and len(df.columns) > 0:
        df = df.rename(columns={df.columns[0]: "date"})

    missing_columns = [col for col in REQUIRED_OHLCV_COLUMNS if col not in df.columns]
    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise ValueError(f"缺少必需列: {missing_text}")

    df = ensure_date_column(df)
    df = _coerce_numeric_columns(
        df,
        [col for col in REQUIRED_OHLCV_COLUMNS if col != "date"] + OPTIONAL_NUMERIC_COLUMNS,
    )

    if volume_multiplier != 1.0:
        df["volume"] = df["volume"] * volume_multiplier

    if market == "CN_A":
        df["symbol"] = _normalize_symbol(symbol, market)
    elif "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    else:
        df["symbol"] = _normalize_symbol(symbol, market)

    negative_qfq_count = 0
    if market == "CN_A" and adjust == "qfq":
        negative_qfq_mask = (df[PRICE_COLUMNS] < 0).any(axis=1)
        negative_qfq_count = int(negative_qfq_mask.sum())
        if negative_qfq_count:
            df = df.loc[~negative_qfq_mask].copy()

    df = df.dropna(subset=REQUIRED_OHLCV_COLUMNS)
    invalid_price_mask = (df[PRICE_COLUMNS] <= 0).any(axis=1)
    invalid_volume_mask = df["volume"] < 0
    df = df.loc[~(invalid_price_mask | invalid_volume_mask)].copy()

    if df.empty:
        raise ValueError("清洗后没有可用行情数据")

    df["market"] = market
    df["currency"] = currency
    df["adjust"] = adjust
    df = df.reset_index(drop=True)

    if negative_qfq_count:
        st.error(
            f"A股 {df['symbol'].iloc[0]} 的前复权数据中发现 {negative_qfq_count} 行早期异常负价格，已自动过滤。"
        )

    return df


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化 DataFrame 的列名

    功能说明：
    1. 将所有列名转换为小写并去除空格
    2. 统一不同数据源的列名差异（如 trade_date → date, vol → volume）
    """
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    rename_map = {
        source: target
        for source, target in COMMON_COLUMN_ALIASES.items()
        if source in df.columns and target not in df.columns
    }

    if rename_map:
        df = df.rename(columns=rename_map)

    return df


@st.cache_data(show_spinner=False, ttl=86400, max_entries=1)
def load_a_stock_catalog() -> pd.DataFrame:
    """加载 A 股代码名称索引，供侧边栏搜索使用。"""
    snapshot_columns = ["code", "name", "search_name", "label"]
    snapshot_df = _read_catalog_snapshot(A_STOCK_CATALOG_SNAPSHOT, snapshot_columns)
    if not snapshot_df.empty:
        return snapshot_df

    df = ak.stock_info_a_code_name()
    if df is None or df.empty:
        raise ValueError("A 股代码名称索引为空")
    df = df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]

    if "code" not in df.columns or "name" not in df.columns:
        raise ValueError("A 股代码名称索引缺少 code/name 列")

    df["code"] = df["code"].astype(str).str.extract(r"(\d+)")[0].fillna("")
    df["code"] = df["code"].str.zfill(6).str[-6:]
    df["name"] = df["name"].astype(str).str.strip()
    df = df[(df["code"] != "") & (df["name"] != "")].copy()
    df["search_name"] = df["name"].map(_normalize_search_text)
    df["label"] = df["code"] + " " + df["name"]
    df = df.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    return df[["code", "name", "search_name", "label"]]


@st.cache_data(show_spinner=False, ttl=86400, max_entries=1)
def load_us_stock_catalog() -> pd.DataFrame:
    """加载美股代码名称索引，优先使用本地快照。"""
    snapshot_columns = ["symbol", "name", "cname", "search_symbol", "search_name", "search_cname", "label"]
    snapshot_df = _read_catalog_snapshot(US_STOCK_CATALOG_SNAPSHOT, snapshot_columns)
    if not snapshot_df.empty:
        return snapshot_df

    from akshare.stock import stock_us_sina

    original_tqdm = stock_us_sina.tqdm
    stock_us_sina.tqdm = lambda iterable, **kwargs: iterable
    try:
        df = stock_us_sina.get_us_stock_name()
    finally:
        stock_us_sina.tqdm = original_tqdm

    if df is None or df.empty:
        raise ValueError("美股代码名称索引为空")

    df = df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]

    if "symbol" not in df.columns or "name" not in df.columns:
        raise ValueError("美股代码名称索引缺少 symbol/name 列")

    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["name"] = df["name"].astype(str).str.strip()
    df["cname"] = df.get("cname", "").astype(str).str.strip() if "cname" in df.columns else ""
    df = df[(df["symbol"] != "") & (df["name"] != "")].copy()
    df["search_symbol"] = df["symbol"].map(_normalize_search_text)
    df["search_name"] = df["name"].map(_normalize_search_text)
    df["search_cname"] = df["cname"].map(_normalize_search_text)
    df["label"] = df.apply(
        lambda row: (
            f"{row['symbol']} {row['name']} / {row['cname']}"
            if row["cname"]
            else f"{row['symbol']} {row['name']}"
        ),
        axis=1,
    )
    df = df.drop_duplicates(subset=["symbol"], keep="first").reset_index(drop=True)
    return df[["symbol", "name", "cname", "search_symbol", "search_name", "search_cname", "label"]]


def get_stock_label_map(symbols: Iterable[str], market: str) -> dict[str, str]:
    """为股票代码列表构建界面展示标签。"""
    market_key = _normalize_market_key(market)
    symbol_list = [str(symbol or "").strip() for symbol in symbols if str(symbol or "").strip()]
    if not symbol_list:
        return {}

    if market_key == "CN_A":
        catalog = load_a_stock_catalog()
        label_lookup = catalog.set_index("code")["label"].to_dict()
        return {
            symbol: label_lookup.get(_normalize_symbol(symbol, "CN_A"), symbol)
            for symbol in symbol_list
        }

    catalog = load_us_stock_catalog()
    label_lookup = catalog.set_index("symbol")["label"].to_dict()
    return {
        symbol: label_lookup.get(_normalize_symbol(symbol, "US"), symbol)
        for symbol in symbol_list
    }


def search_stock_candidates(query: str, market: str, limit: int = 8) -> pd.DataFrame:
    """按市场搜索股票候选项。"""
    raw_query = str(query or "").strip()
    if not raw_query:
        return pd.DataFrame()

    market_key = str(market or "US").strip().upper()
    normalized_query = _normalize_search_text(raw_query)
    query_digits = "".join(ch for ch in raw_query if ch.isdigit())

    if market_key in {"A", "CN_A", "CN"}:
        catalog = load_a_stock_catalog()
        candidate_frames: list[pd.DataFrame] = []

        if query_digits:
            normalized_code = query_digits.zfill(6)[-6:] if len(query_digits) >= 6 else query_digits
            candidate_frames.extend(
                [
                    catalog[catalog["code"] == normalized_code],
                    catalog[catalog["code"].str.startswith(query_digits)],
                    catalog[catalog["code"].str.contains(query_digits, regex=False)],
                ]
            )

        if normalized_query:
            candidate_frames.extend(
                [
                    catalog[catalog["search_name"] == normalized_query],
                    catalog[catalog["search_name"].str.startswith(normalized_query)],
                    catalog[catalog["search_name"].str.contains(normalized_query, regex=False)],
                ]
            )

        if not candidate_frames:
            return pd.DataFrame(columns=["symbol", "name", "label"])

        result = (
            pd.concat(candidate_frames, ignore_index=True)
            .drop_duplicates(subset=["code"], keep="first")
            .head(limit)
            .reset_index(drop=True)
            .rename(columns={"code": "symbol"})
        )
        return result[["symbol", "name", "label"]]

    catalog = load_us_stock_catalog()
    candidate_frames = []

    if normalized_query:
        candidate_frames.extend(
            [
                catalog[catalog["search_symbol"] == normalized_query],
                catalog[catalog["search_symbol"].str.startswith(normalized_query)],
                catalog[catalog["search_name"] == normalized_query],
                catalog[catalog["search_name"].str.startswith(normalized_query)],
                catalog[catalog["search_cname"] == normalized_query],
                catalog[catalog["search_cname"].str.startswith(normalized_query)],
                catalog[catalog["search_symbol"].str.contains(normalized_query, regex=False)],
                catalog[catalog["search_name"].str.contains(normalized_query, regex=False)],
                catalog[catalog["search_cname"].str.contains(normalized_query, regex=False)],
            ]
        )

    if not candidate_frames:
        return pd.DataFrame(columns=["symbol", "name", "label"])

    result = (
        pd.concat(candidate_frames, ignore_index=True)
        .drop_duplicates(subset=["symbol"], keep="first")
        .head(limit)
        .reset_index(drop=True)
    )
    return result[["symbol", "name", "label"]]


def search_a_stock_candidates(query: str, limit: int = 8) -> pd.DataFrame:
    """兼容旧调用，按代码或名称搜索 A 股候选项。"""
    return search_stock_candidates(query=query, market="A", limit=limit)


def ensure_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保 DataFrame 有合法的日期列
    """
    df = df.copy()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.sort_values("date")
        df = df.drop_duplicates(subset=["date"], keep="last")
        df = df.reset_index(drop=True)
        return df
    
    df["date"] = pd.RangeIndex(start=1, stop=len(df) + 1, step=1)
    return df


def fetch_data(symbol: str, adjust: str) -> pd.DataFrame:
    """
    从 AkShare 下载美股日线数据

    参数：
        symbol: 股票代码（如 'AAPL', 'TSLA'）
        adjust: 复权方式 ('qfq'=前复权, 'hfq'=后复权, 'none'=不复权)
    """
    normalized_symbol = _normalize_symbol(symbol, "US")
    normalized_adjust = _normalize_adjust(adjust)
    df = ak.stock_us_daily(symbol=normalized_symbol, adjust=normalized_adjust)

    if df is None or df.empty:
        raise ValueError(f"美股 {normalized_symbol} 无可用数据，请检查代码或复权方式。")

    return _finalize_market_dataframe(
        df,
        symbol=normalized_symbol,
        market="US",
        currency="USD",
        adjust=normalized_adjust,
        allow_first_column_as_date=True,
    )


def fetch_a_stock(
    symbol: str,
    adjust: str = "qfq",
    *,
    report_errors: bool = True,
) -> pd.DataFrame | None:
    """
    从 AkShare 下载 A 股日线数据并转换为统一标准结构。

    参数：
        symbol: A 股 6 位代码（如 '600519', '300750'）
        adjust: 复权方式 ('qfq'=前复权, 'hfq'=后复权, 'none'=不复权)
    """
    normalized_symbol = _normalize_symbol(symbol, "CN_A")
    normalized_adjust = _normalize_adjust(adjust)
    ak_adjust = "" if normalized_adjust == "none" else normalized_adjust

    if not normalized_symbol or len(normalized_symbol) != 6:
        if report_errors:
            st.error("A 股代码无效，请输入 6 位代码或从候选结果中选择。")
        return None

    symbol_with_exchange = _get_a_symbol_with_exchange(normalized_symbol)

    def _fetch_from_eastmoney() -> pd.DataFrame:
        return ak.stock_zh_a_hist(
            symbol=normalized_symbol,
            period="daily",
            start_date="19700101",
            end_date="20500101",
            adjust=ak_adjust,
            timeout=15,
        )

    def _fetch_from_tencent() -> pd.DataFrame:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            df = ak.stock_zh_a_hist_tx(
                symbol=symbol_with_exchange,
                start_date="19700101",
                end_date="20500101",
                adjust=ak_adjust,
                timeout=15,
            )
        if df is not None and not df.empty and "amount" in df.columns and "volume" not in df.columns:
            df = df.rename(columns={"amount": "volume"})
        return df

    def _fetch_from_sina() -> pd.DataFrame:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return ak.stock_zh_a_daily(
                symbol=symbol_with_exchange,
                start_date="19900101",
                end_date="20500101",
                adjust=ak_adjust,
            )

    data_sources: list[tuple[str, Callable[[], pd.DataFrame]]] = [
        ("东方财富", _fetch_from_eastmoney),
        ("腾讯证券", _fetch_from_tencent),
        ("新浪财经", _fetch_from_sina),
    ]

    last_error: Exception | None = None
    for _source_name, loader in data_sources:
        try:
            df = loader()
        except Timeout as exc:
            last_error = exc
            continue
        except ProxyError as exc:
            last_error = exc
            continue
        except RequestException as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue

        if df is None or df.empty:
            continue

        try:
            result_df = _finalize_market_dataframe(
                df,
                symbol=normalized_symbol,
                market="CN_A",
                currency="CNY",
                adjust=normalized_adjust,
                volume_multiplier=100.0,
            )
            _write_market_cache(result_df, normalized_symbol, report_errors=report_errors)
            return result_df
        except ValueError as exc:
            last_error = exc
            continue

    if last_error is not None and report_errors:
        st.error(
            f"A股 {normalized_symbol} 数据获取失败：东方财富/腾讯/新浪三路历史行情均未成功。"
            f" 最近错误：{last_error}"
        )
    elif report_errors:
        st.error(f"A股 {normalized_symbol} 无可用数据，请检查代码是否存在或当前复权方式是否可用。")
    return None


@st.cache_data(show_spinner=False, ttl=82800, max_entries=16)
def load_csv(path: str) -> pd.DataFrame:
    """从本地 CSV 文件加载数据（内存缓存 23 小时，与磁盘 TTL 24 小时配合）"""
    df = pd.read_csv(path)
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df


@st.cache_data(show_spinner=False, max_entries=2)
def load_uploaded_bytes(data: bytes) -> pd.DataFrame:
    """从上传的字节数据加载 CSV"""
    df = pd.read_csv(io.BytesIO(data))
    df = standardize_columns(df)
    df = ensure_date_column(df)
    return df
