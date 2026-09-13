"""港美股财务数据工具（主要指标 + 三大报表）。

数据源：akshare 东财 F10 接口（datacenter 域名组）。实测（2026-09-13）
datacenter 与行情域名（push2his）限流相互独立，财务请求可用更高速率。
"""

from __future__ import annotations

import akshare as ak

from tools.global_market.em_client import em_call, TTL_DAILY
from tools.global_market.global_formatting import (
    HK_INDICATOR_FIELDS, US_INDICATOR_FIELDS, format_indicator, format_report,
)
from tools.global_market.symbol_resolver import normalize_hk
from utils.logger import log_debug, handle_exception

# 港股报表名（akshare 参数值）
_HK_REPORTS = {"hk_income": "利润表", "hk_balancesheet": "资产负债表", "hk_cashflow": "现金流量表"}
# 美股报表名（注意 akshare 用"综合损益表"）
_US_REPORTS = {"us_income": "综合损益表", "us_balancesheet": "资产负债表", "us_cashflow": "现金流量表"}


def _fetch_hk_indicator(code: str, indicator: str):
    return em_call(
        "eastmoney_datacenter",
        lambda: ak.stock_financial_hk_analysis_indicator_em(symbol=code, indicator=indicator),
        cache_key=f"hk_fi:{code}:{indicator}",
        ttl_seconds=TTL_DAILY,
    )


def _fetch_us_indicator(ticker: str, indicator: str):
    return em_call(
        "eastmoney_datacenter",
        lambda: ak.stock_financial_us_analysis_indicator_em(symbol=ticker, indicator=indicator),
        cache_key=f"us_fi:{ticker}:{indicator}",
        ttl_seconds=TTL_DAILY,
    )


def _fetch_hk_report(code: str, report: str, indicator: str):
    return em_call(
        "eastmoney_datacenter",
        lambda: ak.stock_financial_hk_report_em(stock=code, symbol=report, indicator=indicator),
        cache_key=f"hk_rp:{code}:{report}:{indicator}",
        ttl_seconds=TTL_DAILY,
    )


def _fetch_us_report(ticker: str, report: str, indicator: str):
    return em_call(
        "eastmoney_datacenter",
        lambda: ak.stock_financial_us_report_em(stock=ticker, symbol=report, indicator=indicator),
        cache_key=f"us_rp:{ticker}:{report}:{indicator}",
        ttl_seconds=TTL_DAILY,
    )


def register_finance_global_tools(mcp) -> None:
    """注册港美股财务工具。"""

    @mcp.tool()
    @handle_exception
    def hk_fina_indicator(symbol: str, indicator: str = "年度", limit: int = 10) -> str:
        """
        获取港股公司主要财务指标（EPS/ROE/毛利率/净利率/资产负债率/营收与净利同比等）。

        参数:
            symbol: 港股代码（'00700'=腾讯控股，支持 '700' 简写）
            indicator: '年度'（年报，默认）或 '报告期'（含中报/季报）
            limit: 返回最近 N 期（默认 10）
        """
        log_debug(f"[global_finance] hk_fina_indicator symbol='{symbol}'")
        code = normalize_hk(symbol or "")
        if not code:
            return "错误：必须提供港股代码（如 00700）"
        indicator = indicator if indicator in ("年度", "报告期") else "年度"
        df = _fetch_hk_indicator(code, indicator)
        return format_indicator(df, HK_INDICATOR_FIELDS, f"港股主要财务指标（{indicator}）", limit=limit)

    @mcp.tool()
    @handle_exception
    def us_fina_indicator(symbol: str, indicator: str = "年报", limit: int = 8) -> str:
        """
        获取美股公司主要财务指标（营收/净利及同比/毛利率/净利率/ROE/资产负债率/EPS 等）。

        参数:
            symbol: 美股代码（'AAPL'=苹果，无需市场前缀）
            indicator: '年报'（默认）/ '单季报' / '累计季报'
            limit: 返回最近 N 期（默认 8）
        """
        log_debug(f"[global_finance] us_fina_indicator symbol='{symbol}'")
        ticker = (symbol or "").strip().upper()
        if not ticker:
            return "错误：必须提供美股代码（如 AAPL）"
        ticker = ticker.split(".")[-1] if ticker.startswith(("105.", "106.", "107.")) else ticker
        indicator = indicator if indicator in ("年报", "单季报", "累计季报") else "年报"
        df = _fetch_us_indicator(ticker, indicator)
        return format_indicator(df, US_INDICATOR_FIELDS, f"美股主要财务指标（{indicator}）", limit=limit)

    def _make_hk_report_tool(tool_name: str, report_cn: str, title: str):
        def _hk_report(symbol: str, indicator: str = "年度", limit: int = 4) -> str:
            code = normalize_hk(symbol or "")
            if not code:
                return "错误：必须提供港股代码（如 00700）"
            indicator = indicator if indicator in ("年度", "报告期") else "年度"
            df = _fetch_hk_report(code, report_cn, indicator)
            return format_report(df, "STD_ITEM_NAME", "AMOUNT", f"港股{title}（{indicator}）", limit=limit)

        _hk_report.__doc__ = f"""
            获取港股{title}（东财 F10，逐科目金额，报告期分行输出）。

            参数:
                symbol: 港股代码（'00700'=腾讯控股）
                indicator: '年度'（默认）或 '报告期'
                limit: 返回最近 N 个报告期（默认 4）
            """
        mcp.tool(name=tool_name)(handle_exception(_hk_report))

    def _make_us_report_tool(tool_name: str, report_cn: str, title: str):
        def _us_report(symbol: str, indicator: str = "年报", limit: int = 4) -> str:
            ticker = (symbol or "").strip().upper()
            if not ticker:
                return "错误：必须提供美股代码（如 AAPL）"
            ticker = ticker.split(".")[-1] if ticker.startswith(("105.", "106.", "107.")) else ticker
            indicator = indicator if indicator in ("年报", "单季报", "累计季报") else "年报"
            df = _fetch_us_report(ticker, report_cn, indicator)
            return format_report(df, "ITEM_NAME", "AMOUNT", f"美股{title}（{indicator}）", limit=limit)

        _us_report.__doc__ = f"""
            获取美股{title}（东财 F10，逐科目金额，报告期分行输出，美元）。

            参数:
                symbol: 美股代码（'AAPL'=苹果，无需市场前缀）
                indicator: '年报'（默认）/ '单季报' / '累计季报'
                limit: 返回最近 N 个报告期（默认 4）
            """
        mcp.tool(name=tool_name)(handle_exception(_us_report))

    _make_hk_report_tool("hk_income", _HK_REPORTS["hk_income"], "利润表")
    _make_hk_report_tool("hk_balancesheet", _HK_REPORTS["hk_balancesheet"], "资产负债表")
    _make_hk_report_tool("hk_cashflow", _HK_REPORTS["hk_cashflow"], "现金流量表")
    _make_us_report_tool("us_income", _US_REPORTS["us_income"], "综合损益表")
    _make_us_report_tool("us_balancesheet", _US_REPORTS["us_balancesheet"], "资产负债表")
    _make_us_report_tool("us_cashflow", _US_REPORTS["us_cashflow"], "现金流量表")