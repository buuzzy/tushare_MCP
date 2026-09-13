"""港美股/全球指数的代码解析与搜索。

代码表来源：东财 push2 clist 接口（按成交额降序拉前若干页，覆盖活跃股票，
24h 进程内缓存）。本机/服务 IP 若触发东财限流，列表加载失败时：
- search_symbol 返回友好错误
- 美股 K 线前缀解析回退为 105→106→107 顺序尝试
"""

from __future__ import annotations

import re
from typing import Optional

import requests

from tools.global_market.em_client import em_call, TTL_DAILY
from utils.logger import log_debug

_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_LIST_PAGES = 20          # 每页 100 条，共 2000 只活跃股
_LIST_PAGE_SIZE = 100

# 全球指数别名 -> (指数代码, 中文名)。港股（hk* 前缀）走腾讯；美股指数（. 前缀）走新浪
# （腾讯 fqkline 对 us 前缀区间请求仅返回 1 根，实测废弃）
INDEX_ALIASES: dict[str, tuple[str, str]] = {
    "HSI": ("hkHSI", "恒生指数"),
    "恒指": ("hkHSI", "恒生指数"),
    "恒生指数": ("hkHSI", "恒生指数"),
    "HSTECH": ("hkHSTECH", "恒生科技指数"),
    "恒生科技": ("hkHSTECH", "恒生科技指数"),
    "恒生科技指数": ("hkHSTECH", "恒生科技指数"),
    "HSCEI": ("hkHSCEI", "恒生中国企业指数"),
    "国企指数": ("hkHSCEI", "恒生中国企业指数"),
    "DJIA": (".DJI", "道琼斯工业指数"),
    "道指": (".DJI", "道琼斯工业指数"),
    "DJI": (".DJI", "道琼斯工业指数"),
    "SPX": (".INX", "标普500指数"),
    "标普500": (".INX", "标普500指数"),
    "标普": (".INX", "标普500指数"),
    "GSPC": (".INX", "标普500指数"),
    "INX": (".INX", "标普500指数"),
    "NDX": (".NDX", "纳斯达克100指数"),
    "纳斯达克100": (".NDX", "纳斯达克100指数"),
    "IXIC": (".IXIC", "纳斯达克综合指数"),
    "纳指": (".IXIC", "纳斯达克综合指数"),
    "纳斯达克指数": (".IXIC", "纳斯达克综合指数"),
}


def resolve_index(raw: str) -> Optional[tuple[str, str]]:
    """解析全球指数别名，返回 (secid, 中文名)；非指数返回 None。"""
    return INDEX_ALIASES.get(raw.strip().upper())


def normalize_hk(raw: str) -> Optional[str]:
    """港股代码归一化：'700'/'00700'/'0700.HK'/'hk0700' -> '00700'。"""
    code = raw.strip().upper().replace("HK", "").replace(".", "")
    if not re.fullmatch(r"\d{1,5}", code):
        return None
    return code.zfill(5)


def _fetch_clist_pages(fs: str) -> list[dict]:
    """拉取 clist 若干页（成交额降序），返回 [{"code","name","market"}...]。

    单页失败重试一次，仍失败则提前结束（部分结果好于全无——列表按成交额
    降序，前面的页覆盖最活跃的股票）。
    """
    rows: list[dict] = []
    for page in range(1, _LIST_PAGES + 1):
        diff: list = []
        for attempt in range(2):
            try:
                resp = em_call(
                    "eastmoney_list",
                    lambda p=page: requests.get(
                        _CLIST_URL,
                        params={
                            "pn": p, "pz": _LIST_PAGE_SIZE, "po": 1, "np": 1,
                            "fltt": 2, "invt": 2, "fid": "f6", "fs": fs,
                            "fields": "f12,f13,f14",
                        },
                        timeout=15,
                    ).json(),
                    cache_key="",
                )
                diff = (resp.get("data") or {}).get("diff") or []
                break
            except requests.exceptions.RequestException:
                if attempt == 1:
                    return rows  # 已尽力，返回已拉到的部分
        for item in diff:
            rows.append(
                {"code": str(item.get("f12", "")), "name": str(item.get("f14", "")).strip(),
                 "market": item.get("f13")}
            )
        if len(diff) < _LIST_PAGE_SIZE:
            break
    return rows


def _load_hk_list() -> list[dict]:
    """港股活跃正股列表（剔除代码 >09999 的窝轮/牛熊证）。"""
    rows = em_call(
        "eastmoney_list",
        lambda: _fetch_clist_pages("m:116"),
        cache_key="global_hk_list",
        ttl_seconds=TTL_DAILY,
    )
    return [r for r in rows if r["code"].isdigit() and r["code"] <= "09999"]


def _load_us_list() -> list[dict]:
    """美股活跃股列表（含市场前缀 105/106/107）。"""
    return em_call(
        "eastmoney_list",
        lambda: _fetch_clist_pages("m:105,m:106,m:107"),
        cache_key="global_us_list",
        ttl_seconds=TTL_DAILY,
    )


def resolve_us_prefix(ticker: str) -> Optional[str]:
    """美股 ticker -> 市场前缀（105 纳斯达克 / 106 纽交所 / 107 美交所）。

    依赖列表缓存；缓存不可用时返回 None，调用方应顺序尝试 105→106→107。
    """
    t = ticker.strip().upper()
    try:
        for row in _load_us_list():
            if row["code"].upper() == t and row.get("market") in (105, 106, 107, "105", "106", "107"):
                return str(row["market"])
    except Exception as e:  # 列表加载失败不阻塞 K 线查询
        log_debug(f"[symbol_resolver] us list unavailable: {e}")
        return None
    return None


def resolve_us(raw: str) -> str:
    """美股代码归一化为东财格式。

    'AAPL' -> '105.AAPL'（可解析时），'105.AAPL' 原样，'AAPL.O' -> '105.AAPL'。
    无法确定市场时返回裸 ticker（大写），由 K 线查询顺序尝试前缀。
    """
    raw = raw.strip().upper()
    if re.fullmatch(r"1(0[567])\.[A-Z._]+", raw):
        return raw  # 已带市场前缀
    suffix_map = {".O": "105", ".N": "106", ".A": "107"}
    for suffix, prefix in suffix_map.items():
        if raw.endswith(suffix):
            return f"{prefix}.{raw[: -len(suffix)]}"
    ticker = raw
    prefix = resolve_us_prefix(ticker)
    return f"{prefix}.{ticker}" if prefix else ticker


def _verify_us_ticker_via_sina(ticker: str) -> bool:
    """用新浪源验证美股 ticker 是否存在（拉全历史，非空即有效；3h 缓存）。

    活跃股表只是成交额前若干页的快照，覆盖不稳定（线上实测 SNDK 等
    热门票也可能缺席），ticker 直查兜底保证"像代码的查询"总能验证。
    """
    try:
        df = em_call(
            "sina_quote",
            lambda: _sina_us_daily(symbol=ticker, adjust=""),
            cache_key=f"us_kl_sina:{ticker}:",
            ttl_seconds=3 * 3600,
        )
        return df is not None and not df.empty
    except Exception as e:
        log_debug(f"[symbol_resolver] ticker verify failed for {ticker}: {e}")
        return False


def _sina_us_daily(symbol: str, adjust: str):
    """惰性导入 akshare，避免 symbol_resolver 顶层依赖。"""
    import akshare as ak
    return ak.stock_us_daily(symbol=symbol, adjust=adjust)


def _us_name_from_em(ticker: str) -> Optional[str]:
    """东财 F10 公司概况查美股中文名（datacenter 组稳定；24h 缓存）。"""
    def _do() -> Optional[str]:
        resp = requests.get(
            "https://datacenter.eastmoney.com/securities/api/data/v1/get",
            params={
                "reportName": "RPT_USF10_INFO_ORGPROFILE",
                "columns": "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,ORG_NAME",
                "quoteColumns": "", "filter": f'(SECURITY_CODE="{ticker}")',
                "pageNumber": "1", "pageSize": "2", "source": "SECURITIES", "client": "PC",
            },
            timeout=15,
        ).json()
        rows = (resp.get("result") or {}).get("data") or []
        for row in rows:
            name = str(row.get("SECURITY_NAME_ABBR") or "").strip()
            if name:
                return name
        return None

    try:
        return em_call("eastmoney_datacenter", _do,
                       cache_key=f"us_name:{ticker}", ttl_seconds=TTL_DAILY)
    except Exception as e:
        log_debug(f"[symbol_resolver] name lookup failed for {ticker}: {e}")
        return None


def search_symbols(query: str, market: str = "all", limit: int = 10) -> list[dict]:
    """按代码前缀或名称包含匹配港股/美股活跃股。

    美股 query 形如 ticker 而列表未命中时，用新浪源直接验证兜底；
    港股 5 位数字代码同理直接透传（列表仅用于补中文名）。

    Returns: [{"market": "HK"/"US", "code": "00700", "name": "腾讯控股"}...]
    """
    query = query.strip()
    if not query:
        return []
    q_upper = query.upper()
    results: list[dict] = []

    def match(tag: str, rows: list[dict]) -> None:
        for row in rows:
            code, name = row["code"], row["name"]
            if code.upper().startswith(q_upper) or (query in name):
                results.append({"market": tag, "code": code, "name": name})
                if len(results) >= limit:
                    return

    if market in ("all", "hk"):
        match("HK", _load_hk_list())
    if len(results) < limit and market in ("all", "us"):
        match("US", _load_us_list())

    # ticker / 数字代码直查兜底（活跃表是快照，覆盖不稳定）
    if not results:
        if market in ("all", "us") and re.fullmatch(r"[A-Z][A-Z0-9._-]{0,9}", q_upper):
            if _verify_us_ticker_via_sina(q_upper):
                results.append({"market": "US", "code": q_upper,
                                "name": _us_name_from_em(q_upper) or q_upper})
        elif market in ("all", "hk") and re.fullmatch(r"\d{1,5}", query):
            results.append({"market": "HK", "code": query.zfill(5), "name": query.zfill(5)})
    return results[:limit]
