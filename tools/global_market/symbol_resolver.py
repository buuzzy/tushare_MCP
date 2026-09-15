"""港美股/全球指数的代码解析与搜索。

代码表来源（互为兜底）：
- 东财 push2 clist：按成交额降序拉前若干页（24h 缓存），覆盖活跃股票；
  仅靠它时次新股/低成交股会漏（实测 02714 牧原、SNDK 均缺席）。
- 东财 suggest（searchadapter 域，全库）：名称/代码/拼音缩写搜索，
  clist 未命中或加载失败时的主兜底；两者均不可用时代码直查透传。
本机/服务 IP 若触发东财限流，列表加载失败时：
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

_SUGGEST_URL = "https://searchadapter.eastmoney.com/api/suggest/get"
_SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"  # 东财 web 端公开 token

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


def _parse_suggest(resp: dict, market: str, limit: int) -> list[dict]:
    """解析 suggest 响应，过滤出港美股正股（剔除窝轮/债券/板块/A股）。

    港股窝轮/牛熊证代码 >= 10000，与 _load_hk_list 同样按 '09999' 截断。
    """
    rows = (resp.get("QuotationCodeTable") or {}).get("Data") or []
    out: list[dict] = []
    for item in rows:
        classify = item.get("Classify")
        code = str(item.get("Code", "")).strip()
        name = str(item.get("Name", "")).strip()
        if classify == "HK" and code.isdigit() and code <= "09999":
            entry = {"market": "HK", "code": code.zfill(5), "name": name}
        elif classify == "UsStock" and code:
            entry = {"market": "US", "code": code.upper(), "name": name}
        else:
            continue
        if market not in ("all", entry["market"].lower()):
            continue
        if entry not in out:
            out.append(entry)
        if len(out) >= limit:
            break
    return out


def _suggest_search(query: str, market: str, limit: int) -> list[dict]:
    """东财 suggest 全库搜索（名称/代码/拼音缩写，带中文名）。

    活跃表只是成交额前若干页的快照，次新股/低成交股常缺席（实测：
    牧原 02714、SNDK 均不在快照内），名称搜索以此为主兜底。
    """
    def _do() -> list[dict]:
        resp = requests.get(
            _SUGGEST_URL,
            params={"input": query, "type": "14", "token": _SUGGEST_TOKEN,
                    "count": "20"},
            timeout=15,
        ).json()
        return _parse_suggest(resp, market, limit)

    return em_call(
        "eastmoney_suggest", _do,
        cache_key=f"suggest:{market}:{query}", ttl_seconds=TTL_DAILY,
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
    """按代码前缀或名称包含匹配港股/美股证券（活跃表 -> suggest 全库 -> 代码透传）。

    美股 query 形如 ticker 而列表未命中时，用新浪源直接验证兜底；
    港股 5 位数字代码同理直接透传（列表仅用于补中文名）。

    Returns: [{"market": "HK"/"US", "code": "00700", "name": "腾讯控股"}...]
    """
    query = query.strip()
    if not query:
        return []
    q_upper = query.upper()
    results: list[dict] = []

    def safe_list(loader) -> list[dict]:
        try:
            return loader()
        except Exception as e:  # clist 加载失败不阻塞搜索，降级到 suggest
            log_debug(f"[symbol_resolver] list load failed: {e}")
            return []

    def match(tag: str, rows: list[dict]) -> None:
        for row in rows:
            code, name = row["code"], row["name"]
            if code.upper().startswith(q_upper) or (query in name):
                results.append({"market": tag, "code": code, "name": name})
                if len(results) >= limit:
                    return

    if market in ("all", "hk"):
        match("HK", safe_list(_load_hk_list))
    if len(results) < limit and market in ("all", "us"):
        match("US", safe_list(_load_us_list))

    # suggest 全库兜底：活跃表是成交额快照，次新股/低成交股/名称搜索常缺席
    if not results:
        try:
            results = _suggest_search(query, market, limit)
        except Exception as e:
            log_debug(f"[symbol_resolver] suggest search failed: {e}")

    # ticker / 数字代码直查兜底（活跃表是快照，覆盖不稳定）
    if not results:
        if market in ("all", "us") and re.fullmatch(r"[A-Z][A-Z0-9._-]{0,9}", q_upper):
            if _verify_us_ticker_via_sina(q_upper):
                results.append({"market": "US", "code": q_upper,
                                "name": _us_name_from_em(q_upper) or q_upper})
        elif market in ("all", "hk") and re.fullmatch(r"\d{1,5}", query):
            # 仅短简写透传（suggest 不支持前缀匹配，'700'→'00700' 属代码归一化）。
            # 完整 5 位代码不透传：suggest 全库未命中即视为不存在——
            # 盲回显会给无效代码（如 99999）发放"存在证书"，误导 Agent
            # 查行情失败后自行猜测替换标的（2026-09-15 P2#39 实测）
            if len(query) < 5:
                results.append({"market": "HK", "code": query.zfill(5), "name": query.zfill(5)})
    return results[:limit]
