"""港美股财务数据工具（主要指标 + 三大报表）。

数据源：akshare 东财 F10 接口（datacenter 域名组）。实测（2026-09-13）
datacenter 与行情域名（push2his）限流相互独立，财务请求可用更高速率。
"""

from __future__ import annotations

import datetime as dt

import akshare as ak
import requests

from tools.global_market.em_client import em_call, TTL_DAILY, TTL_KLINE
from tools.global_market.global_formatting import (
    HK_INDICATOR_FIELDS, US_INDICATOR_FIELDS, format_generic_rows,
    format_indicator, format_report,
)
from tools.global_market.quote import _normalize_dates
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


# 港股每日回购（数据中心 datacenter 域名组；与披露易"翌日披露報表"逐日对应）
_BUYBACK_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _format_buyback_rows(raw: list[dict]) -> list[dict]:
    """原始行 -> 输出行（最新在前，单位进值便于阅读与 data-cache 解析）。"""
    rows: list[dict] = []
    for r in raw:
        num, avg, amt = r.get("REPO_NUM"), r.get("AVG_PRICE"), r.get("REPO_AMT")
        if num is None or avg is None or amt is None:
            continue
        row = {
            "日期": str(r.get("TRADE_DATE", ""))[:10],
            "代码": str(r.get("SECUCODE", "")),
            "名称": str(r.get("SECURITY_NAME_ABBR", "")).strip(),
            "回购股数": f"{int(num):,}股",
            "回购均价": f"{float(avg):.4f}",
            "回购金额": f"{float(amt):,.1f}",
        }
        pcg = r.get("REPO_NUM_PCG")
        if pcg is not None:
            row["占总股本比"] = f"{pcg}%"
        rows.append(row)
    return rows


def _fetch_hk_buyback(code: str, start: str, end: str) -> list[dict]:
    """港股每日回购明细（最新在前，单页 500 条足够覆盖任何常规区间）。"""
    flt = f'(SECURITY_CODE="{code}")'
    if start:
        flt += f"(TRADE_DATE>='{start}')"
    if end:
        flt += f"(TRADE_DATE<='{end}')"

    def _do() -> list[dict]:
        resp = requests.get(
            _BUYBACK_URL,
            params={
                "reportName": "RPT_HK_BUYBACK", "columns": "ALL",
                "pageSize": "500", "pageNumber": "1",
                "sortColumns": "TRADE_DATE", "sortTypes": "-1",
                "filter": flt,
            },
            timeout=15,
        ).json()
        return (resp.get("result") or {}).get("data") or []

    return em_call(
        "eastmoney_datacenter", _do,
        cache_key=f"hk_bb:{code}:{start}:{end}",
        ttl_seconds=TTL_KLINE,  # T+1 更新，3h 缓存平衡新鲜度与请求量
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
            获取港股{title}（逐科目金额，报告期分行输出）。

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
            获取美股{title}（逐科目金额，报告期分行输出，美元）。

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

    @mcp.tool()
    @handle_exception
    def hk_buyback(symbol: str, start_date: str = "", end_date: str = "", limit: int = 30) -> str:
        """
        获取港股每日回购明细（回购股数/均价/金额，逐交易日一行，港元）。
        适合"最近回购了多少金额/每天回购情况"类问题；只要公告列表和原文链接请用 hk_announcements。

        参数:
            symbol: 港股代码（'00700'=腾讯控股，支持 '700' 简写）
            start_date: 开始日期 (YYYYMMDD，可选，默认近90天)
            end_date: 结束日期 (YYYYMMDD，可选)
            limit: 返回最近 N 条（默认 30，最新在前）
        """
        log_debug(f"[global_finance] hk_buyback symbol='{symbol}' {start_date}~{end_date}")
        code = normalize_hk(symbol or "")
        if not code:
            return f"错误：无法识别的港股代码 '{symbol}'（示例：00700 或 700）"
        default_start = (dt.date.today() - dt.timedelta(days=90)).strftime("%Y%m%d")
        start, end, _ = _normalize_dates(start_date or default_start, end_date)
        raw = _fetch_hk_buyback(code, start, end)
        if not raw:
            return (f"未找到港股回购数据（{symbol}，区间 {start}~{end}）。"
                    "该区间可能无回购记录；可用 hk_announcements 查公告原文")
        rows = _format_buyback_rows(raw)[:max(1, limit)]
        name = rows[0]["名称"] or code if rows else code
        return format_generic_rows(f"港股回购（{code} {name}，港元）", rows)