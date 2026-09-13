"""港美股与全球指数的 K 线工具（日线/周线/月线）。

数据源：akshare 东财接口（stock_hk_hist / stock_us_hist）；指数为手写的
东财 push2his 请求（akshare 不覆盖全球指数）。所有请求经 em_client 限频。
"""

from __future__ import annotations

import akshare as ak
import pandas as pd
import requests

from tools.global_market.em_client import em_call, TTL_KLINE
from tools.global_market.global_formatting import format_kline
from tools.global_market.symbol_resolver import (
    _load_hk_list, _load_us_list, normalize_hk, resolve_index, resolve_us,
    search_symbols,
)
from utils.logger import log_debug, handle_exception

_PERIOD_KLT = {"daily": "101", "weekly": "102", "monthly": "103"}
_PERIOD_CN = {"daily": "日线", "weekly": "周线", "monthly": "月线"}

_PUSH2HIS_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


def _lookup_name(market: str, code: str) -> str:
    """从代码表缓存查名称（可选增强，失败不影响主流程）。"""
    try:
        rows = _load_us_list() if market == "US" else _load_hk_list()
        for row in rows:
            if row["code"].upper() == code.upper():
                return row["name"]
    except Exception as e:
        log_debug(f"[global_kline] name lookup failed: {e}")
    return code


def _normalize_dates(start_date: str, end_date: str) -> tuple[str, str]:
    start = (start_date or "").replace("-", "") or "19700101"
    end = (end_date or "").replace("-", "") or "20500101"
    return start, end


def _fetch_hk_kline(symbol: str, period: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    return em_call(
        "eastmoney_quote",
        lambda: ak.stock_hk_hist(
            symbol=symbol, period=period, start_date=start, end_date=end, adjust=adjust
        ),
        cache_key=f"hk_kl:{symbol}:{period}:{adjust}:{start}:{end}",
        ttl_seconds=TTL_KLINE,
    )


def _fetch_us_kline(secid_symbol: str, period: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    return em_call(
        "eastmoney_quote",
        lambda: ak.stock_us_hist(
            symbol=secid_symbol, period=period, start_date=start, end_date=end, adjust=adjust
        ),
        cache_key=f"us_kl:{secid_symbol}:{period}:{adjust}:{start}:{end}",
        ttl_seconds=TTL_KLINE,
    )


def _fetch_index_kline(secid: str, period: str, start: str, end: str) -> pd.DataFrame:
    def _do() -> pd.DataFrame:
        resp = requests.get(
            _PUSH2HIS_URL,
            params={
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f59",
                "klt": _PERIOD_KLT[period],
                "fqt": 1,
                "beg": start,
                "end": end,
            },
            timeout=15,
        ).json()
        data = resp.get("data") or {}
        rows = [line.split(",") for line in (data.get("klines") or [])]
        df = pd.DataFrame(
            rows, columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "涨跌幅"]
        )
        for col in df.columns:
            if col != "日期":
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    return em_call(
        "eastmoney_quote", _do,
        cache_key=f"idx_kl:{secid}:{period}:{start}:{end}",
        ttl_seconds=TTL_KLINE,
    )


def _hk_kline_impl(period: str, symbol: str, start_date: str, end_date: str, adjust: str) -> str:
    log_debug(f"[global_kline] HK/{period} symbol='{symbol}'")
    if not symbol:
        return "错误：必须提供 symbol 参数（港股代码，如 00700）"
    code = normalize_hk(symbol)
    if not code:
        return f"错误：无法识别的港股代码 '{symbol}'（示例：00700 或 700）"
    start, end = _normalize_dates(start_date, end_date)
    adjust = adjust if adjust in ("qfq", "hfq") else ""
    df = _fetch_hk_kline(code, period, start, end, adjust)
    return format_kline(df, f"港股{_PERIOD_CN[period]}行情", "港元", f"{code}.HK", _lookup_name("HK", code))


def _us_kline_impl(period: str, symbol: str, start_date: str, end_date: str, adjust: str) -> str:
    log_debug(f"[global_kline] US/{period} symbol='{symbol}'")
    if not symbol:
        return "错误：必须提供 symbol 参数（美股代码，如 AAPL）"
    start, end = _normalize_dates(start_date, end_date)
    adjust = adjust if adjust in ("qfq", "hfq") else ""

    resolved = resolve_us(symbol)
    df = pd.DataFrame()
    if "." in resolved:  # 市场前缀已确定
        secid_symbol = resolved
        df = _fetch_us_kline(secid_symbol, period, start, end, adjust)
    else:  # 无法确定市场：顺序尝试 105/106/107，取首个非空
        for prefix in ("105", "106", "107"):
            secid_symbol = f"{prefix}.{resolved}"
            df = _fetch_us_kline(secid_symbol, period, start, end, adjust)
            if df is not None and not df.empty:
                break

    if df is None or df.empty:
        hint = ""
        try:
            rows = search_symbols(symbol, market="us", limit=5)
            if rows:
                hint = "候选：" + "; ".join(f"{r['code']} {r['name']}" for r in rows)
        except Exception:
            pass
        hint = hint or "可用 search_symbol 按名称搜索代码"
        return f"未找到美股{_PERIOD_CN[period]}数据（symbol='{symbol}'）。{hint}"
    ticker = secid_symbol.split(".")[-1]
    return format_kline(df, f"美股{_PERIOD_CN[period]}行情", "美元", ticker, _lookup_name("US", ticker))


def register_quote_tools(mcp) -> None:
    """注册港美股 K 线工具（日/周/月）。"""

    @mcp.tool()
    @handle_exception
    def hk_daily(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """
        获取港股日线行情（东财源，历史可回到上市初期）。
        输出：日期 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅 | 成交量 | 成交额(港元)。

        参数:
            symbol: 港股代码（'00700'=腾讯控股，支持 '700' 简写）
            start_date: 开始日期 (YYYYMMDD，可选，默认全历史)
            end_date: 结束日期 (YYYYMMDD，可选)
            adjust: 复权：''不复权 / 'qfq'前复权 / 'hfq'后复权（可选）
        """
        return _hk_kline_impl("daily", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def hk_weekly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取港股周线行情。参数同 hk_daily（symbol 如 '00700'=腾讯控股）。"""
        return _hk_kline_impl("weekly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def hk_monthly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取港股月线行情。参数同 hk_daily（symbol 如 '00700'=腾讯控股）。"""
        return _hk_kline_impl("monthly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def us_daily(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """
        获取美股日线行情（东财源，历史可回到 1990 年代）。
        输出：日期 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅 | 成交量 | 成交额(美元)。

        参数:
            symbol: 美股代码（'AAPL'=苹果；市场前缀自动匹配，无需手动指定）
            start_date: 开始日期 (YYYYMMDD，可选，默认全历史)
            end_date: 结束日期 (YYYYMMDD，可选)
            adjust: 复权：''不复权 / 'qfq'前复权 / 'hfq'后复权（可选）
        """
        return _us_kline_impl("daily", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def us_weekly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取美股周线行情。参数同 us_daily（symbol 如 'AAPL'=苹果）。"""
        return _us_kline_impl("weekly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def us_monthly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取美股月线行情。参数同 us_daily（symbol 如 'AAPL'=苹果）。"""
        return _us_kline_impl("monthly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def global_index_daily(symbol: str, period: str = "daily",
                           start_date: str = "", end_date: str = "") -> str:
        """
        获取全球指数K线（恒指HSI / 恒生科技HSTECH / 道指DJIA / 标普500 SPX / 纳指100 NDX / 纳指综合IXIC / VIX）。
        输出：日期 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅 | 成交量 | 成交额。

        参数:
            symbol: 指数代码或中文名（'HSI'/'恒指'、'SPX'/'标普500'、'IXIC'/'纳指'、'VIX' 等）
            period: 'daily'日线 / 'weekly'周线 / 'monthly'月线（默认日线）
            start_date: 开始日期 (YYYYMMDD，可选，默认近十年)
            end_date: 结束日期 (YYYYMMDD，可选)
        """
        log_debug(f"[global_index] symbol='{symbol}' period='{period}'")
        if not symbol:
            return "错误：必须提供 symbol 参数（指数代码，如 HSI/SPX/IXIC）"
        if period not in _PERIOD_KLT:
            return f"错误：period 仅支持 daily/weekly/monthly，收到 '{period}'"
        resolved = resolve_index(symbol)
        if not resolved:
            return ("错误：暂不支持的指数。当前支持：HSI恒指 / HSTECH恒生科技 / "
                    "DJIA道指 / SPX标普500 / NDX纳指100 / IXIC纳指综合 / VIX")
        secid, name = resolved
        start, end = _normalize_dates(start_date, end_date)
        if start == "19700101":
            start = "20160101"  # 指数默认近十年，避免超大响应
        df = _fetch_index_kline(secid, period, start, end)
        return format_kline(df, f"{name}{_PERIOD_CN[period]}行情", "点", secid, name)
