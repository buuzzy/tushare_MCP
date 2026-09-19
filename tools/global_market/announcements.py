"""代码搜索与港美股公告工具。

- search_symbol：东财代码表模糊匹配（活跃股票）
- us_filings：SEC EDGAR 官方 API（申报文件列表）
- hk_announcements：港交所披露易官方接口（公告列表）
"""


import datetime as dt
import json
import re

import requests

from tools.global_market.em_client import em_call, TTL_DAILY
from tools.global_market.global_formatting import format_generic_rows
from tools.global_market.symbol_resolver import normalize_hk, search_symbols
from utils.logger import log_debug, handle_exception

_SEC_UA = "Sage/1.0 (contact@app.nakocai.com)"  # SEC 政策要求声明访问方身份
_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

_HKEX_PREFIX_URL = "https://www1.hkexnews.hk/search/prefix.do"
_HKEX_SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
_HKEX_DOCS_URL = "https://www1.hkexnews.hk"


def _load_sec_tickers() -> dict[str, tuple[int, str]]:
    """SEC 官方 ticker -> (CIK, 公司名) 映射，24h 缓存。"""
    def _do() -> dict[str, tuple[int, str]]:
        data = requests.get(_SEC_TICKERS_URL, headers={"User-Agent": _SEC_UA}, timeout=30).json()
        return {v["ticker"].upper(): (int(v["cik_str"]), v["title"]) for v in data.values()}

    return em_call("sec_edgar", _do, cache_key="sec_tickers", ttl_seconds=TTL_DAILY)


def _fetch_us_filings(ticker: str, form: str, limit: int) -> list[dict]:
    tickers = _load_sec_tickers()
    entry = tickers.get(ticker)
    if not entry:
        return []
    cik, company = entry

    def _do() -> list[dict]:
        data = requests.get(
            _SEC_SUBMISSIONS_URL.format(cik=cik), headers={"User-Agent": _SEC_UA}, timeout=30
        ).json()
        recent = data.get("filings", {}).get("recent", {})
        rows: list[dict] = []
        for form_type, fdate, acc, doc in zip(
            recent.get("form", []), recent.get("filingDate", []),
            recent.get("accessionNumber", []), recent.get("primaryDocument", []),
        ):
            if form and form.lower() not in form_type.lower():
                continue
            link = _SEC_ARCHIVE_URL.format(
                cik=cik, acc_nodash=acc.replace("-", ""), doc=doc
            )
            rows.append({
                "日期": fdate, "类型": form_type, "公司": company,
                "文件": link,
            })
            if len(rows) >= limit:
                break
        return rows

    return em_call(
        "sec_edgar", _do, cache_key=f"sec_filings:{cik}:{form}:{limit}", ttl_seconds=TTL_DAILY
    )


def _hkex_stock_id(code: str) -> int | None:
    """披露易代码 -> stockId（prefix.do）。"""
    def _do() -> int | None:
        text = requests.get(
            _HKEX_PREFIX_URL,
            params={"callback": "callback", "lang": "ZH", "type": "A", "name": code, "market": "SEHK"},
            timeout=15,
        ).text
        m = re.search(r"\((\{.*\})\)", text, re.S)
        if not m:
            return None
        info = json.loads(m.group(1)).get("stockInfo") or []
        for row in info:
            if row.get("code") == code:
                return int(row["stockId"])
        return None

    return em_call("hkex", _do, cache_key=f"hkex_id:{code}", ttl_seconds=TTL_DAILY)


def _fetch_hk_announcements(stock_id: int, days: int, limit: int) -> list[dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=days)

    def _do() -> list[dict]:
        resp = requests.get(
            _HKEX_SEARCH_URL,
            params={
                "sortDir": 0, "sortByOptions": "DateTime", "category": 0,
                "market": "SEHK", "stockId": stock_id, "documentType": -1,
                "fromDate": start.strftime("%Y%m%d"), "toDate": end.strftime("%Y%m%d"),
                "title": "", "searchType": 1,
                "t1code": -2, "t2Gcode": -2, "t2code": -2,
                "rowRange": limit, "lang": "zh",
            },
            timeout=15,
        )
        # result 字段是字符串化的 JSON
        payload = resp.json()
        rows = json.loads(payload.get("result") or "[]")
        out: list[dict] = []
        for row in rows:
            title = str(row.get("SHORT_TEXT", ""))
            title = title.replace("<br/>", "").replace("<br>", "").strip()
            out.append({
                "日期": str(row.get("DATE_TIME", ""))[:10],
                "标题": title,
                "链接": _HKEX_DOCS_URL + str(row.get("FILE_LINK", "")),
            })
        return out

    return em_call(
        "hkex", _do,
        cache_key=f"hkex_ann:{stock_id}:{days}:{limit}", ttl_seconds=TTL_DAILY,
    )


def register_announcement_tools(mcp) -> None:
    """注册代码搜索与公告工具。"""

    @mcp.tool()
    @handle_exception
    def search_symbol(query: str, market: str = "all", limit: int = 10) -> str:
        """
        按代码或名称搜索港股/美股代码（基于活跃股票表）。
        在不确定代码时先用本工具查询，再调用行情/财务工具。

        参数:
            query: 代码前缀或名称关键字（如 '00700'、'腾讯控股'、'AAPL'、'苹果'）
            market: 'all'（默认）/ 'hk' / 'us'
            limit: 返回条数（默认 10）
        """
        log_debug(f"[global] search_symbol query='{query}' market={market}")
        if not query or not query.strip():
            return "错误：必须提供 query 参数（代码或名称关键字）"
        market = market if market in ("all", "hk", "us") else "all"
        try:
            rows = search_symbols(query.strip(), market=market, limit=limit)
        except Exception as e:
            log_debug(f"[global] search_symbol failed: {e}")
            return "股票代码表暂时不可用（服务繁忙），请稍后再试；港股可直接用 5 位数字代码，美股用 ticker"
        if not rows:
            num_hint = ("；纯数字代码未匹配到有效证券——可能不存在或已退市，"
                        "建议与用户确认代码是否笔误" if query.strip().isdigit() else "")
            return (f"未找到匹配 '{query}' 的股票{num_hint}，请确认代码或名称是否正确"
                    "（港股为 5 位数字如 00700，美股为 ticker 如 AAPL）")
        return format_generic_rows(
            "股票代码搜索",
            [{"市场": r["market"], "代码": r["code"], "名称": r["name"]} for r in rows],
        )

    @mcp.tool()
    @handle_exception
    def us_filings(symbol: str, form: str = "", limit: int = 10) -> str:
        """
        获取美股公司 SEC 申报文件列表（10-K 年报 / 10-Q 季报 / 8-K 重大事项 / 4 高管变动等）。

        参数:
            symbol: 美股代码（'AAPL'=苹果）
            form: 申报类型过滤（可选，如 '10-K'、'10-Q'、'8-K'；留空返回全部）
            limit: 返回条数（默认 10）
        """
        log_debug(f"[global] us_filings symbol='{symbol}' form='{form}'")
        ticker = (symbol or "").strip().upper()
        if not ticker:
            return "错误：必须提供美股代码（如 AAPL）"
        rows = _fetch_us_filings(ticker, (form or "").strip(), limit)
        if not rows:
            return (f"未找到 '{ticker}' 的申报记录（SEC 官方映射表中无此 ticker，"
                    "注意 ADR/小众代码可能有差异）")
        return format_generic_rows(f"SEC 申报文件（{ticker}）", rows)

    @mcp.tool()
    @handle_exception
    def hk_announcements(symbol: str, days: int = 30, limit: int = 10) -> str:
        """
        获取港股公司公告列表（港交所披露易官方数据，含 PDF 链接）。

        参数:
            symbol: 港股代码（'00700'=腾讯控股，支持 '700' 简写）
            days: 近 N 天（默认 30）
            limit: 返回条数（默认 10）
        """
        log_debug(f"[global] hk_announcements symbol='{symbol}' days={days}")
        code = normalize_hk(symbol or "")
        if not code:
            return "错误：必须提供港股代码（如 00700）"
        stock_id = _hkex_stock_id(code)
        if not stock_id:
            return f"未在披露易找到代码 '{code}'"
        rows = _fetch_hk_announcements(stock_id, days, limit)
        return format_generic_rows(f"港股公告（{code}，近 {days} 天）", rows)
