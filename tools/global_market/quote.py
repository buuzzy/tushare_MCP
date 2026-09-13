"""港美股与全球指数的 K 线工具（日线/周线/月线）。

数据源：腾讯 ifzq.gtimg.cn（fqkline/kline 接口）。东财 push2his 对海外
数据中心 IP 存在无法根治的动态封禁（2026-09-13 线上实测：连续使用后
进入分钟级以上封禁、等待不复位），故行情统一走腾讯；财务/代码表仍走
东财 datacenter（不受影响）。所有请求经 em_client 限频。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import requests

from tools.global_market.em_client import em_call, TTL_KLINE
from tools.global_market.global_formatting import format_kline
from tools.global_market.symbol_resolver import (
    _load_hk_list, _load_us_list, normalize_hk, resolve_index,
    search_symbols,
)
from utils.logger import log_debug, handle_exception

_PERIOD_CN = {"daily": "日线", "weekly": "周线", "monthly": "月线"}
_PERIOD_TX = {"daily": "day", "weekly": "week", "monthly": "month"}

_TX_URL = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"
# 注：kline/get（不复权端点）实测已废弃（任何 param 均返回 code=11）；
# 不复权统一走 fqkline + 空 fq 段（尾逗号），实测 800 bars 正常。
_TX_BATCH = 800        # 单次请求上限（实测 800 可用）
_TX_SEGMENT_DAYS = 800  # 分页拉取时每段覆盖的交易日跨度估算


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


def _normalize_dates(start_date: str, end_date: str) -> tuple[str, str, int]:
    """返回 (start YYYY-MM-DD, end YYYY-MM-DD, 天数跨度)。"""
    end = end_date.replace("-", "") if end_date else ""
    end_dt = dt.datetime.strptime(end, "%Y%m%d").date() if end else dt.date.today()
    start = start_date.replace("-", "") if start_date else ""
    start_dt = (
        dt.datetime.strptime(start, "%Y%m%d").date()
        if start else end_dt - dt.timedelta(days=3 * 365)  # 默认近3年
    )
    return start_dt.isoformat(), end_dt.isoformat(), (end_dt - start_dt).days


def _tx_param(tx_code: str, period: str, seg_start: str, seg_end: str, fq: str) -> str:
    """构造腾讯 K 线 param（6 段）。不复权时 fq 段为空（保留尾逗号）。"""
    base = f"{tx_code},{_PERIOD_TX[period]},{seg_start},{seg_end},{_TX_BATCH}"
    return f"{base},{fq}"


def _tx_fetch_once(tx_code: str, period: str, seg_start: str, seg_end: str, adjust: str) -> list[list]:
    """单次腾讯 K 线请求，返回 bars 列表。"""
    fq = adjust if adjust in ("qfq", "hfq") else ""

    def _do():
        r = requests.get(_TX_URL, params={"param": _tx_param(tx_code, period, seg_start, seg_end, fq)}, timeout=15)
        if (r.json().get("data") or {}).get(tx_code) is None:
            log_debug(f"[global_kline] tencent suspicious response: url={r.url} "
                      f"status={r.status_code} body={r.text[:120]}")
        return r.json()

    resp = em_call(
        "tencent_quote",
        _do,
        cache_key=f"tx_kl:{tx_code}:{period}:{adjust}:{seg_start}:{seg_end}",
        ttl_seconds=TTL_KLINE,
    )
    node = (resp.get("data") or {}).get(tx_code) or {}
    if not node:
        log_debug(
            f"[global_kline] tencent empty node: {tx_code} code={resp.get('code')} "
            f"msg={str(resp.get('msg'))[:80]} keys={list((resp.get('data') or {}).keys())[:5]}"
        )
    key = f"{fq}{_PERIOD_TX[period]}" if fq else _PERIOD_TX[period]
    return node.get(key) or node.get(_PERIOD_TX[period]) or []


def _fetch_tx_kline(tx_code: str, period: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    """按日期分段拉取腾讯 K 线并拼接（单次上限约 800 根）。

    腾讯按"区间末尾截取 count 根"返回，故从 start 起逐段向前推进。
    """
    all_bars: list[list] = []
    seg_days = _TX_SEGMENT_DAYS * (5 if period == "weekly" else 22 if period == "monthly" else 1)
    cursor = start
    while cursor <= end:
        seg_end_dt = dt.datetime.strptime(cursor, "%Y-%m-%d").date() + dt.timedelta(days=seg_days)
        seg_end = min(seg_end_dt.isoformat(), end)
        bars = _tx_fetch_once(tx_code, period, cursor, seg_end, adjust)
        if not bars:
            break
        for bar in bars:
            if not all_bars or bar[0] > all_bars[-1][0]:
                all_bars.append(bar)
        last_date = dt.datetime.strptime(bars[-1][0], "%Y-%m-%d").date()
        if len(bars) < _TX_BATCH or last_date.isoformat() >= end:
            break
        cursor = (last_date + dt.timedelta(days=1)).isoformat()

    if not all_bars:
        return pd.DataFrame()
    # 腾讯 bar 长度不固定（6/7/8 元素，含成交额与否随市场而异），按实际长度适配列名
    base_cols = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
    max_len = max(len(bar) for bar in all_bars)
    columns = [base_cols[i] if i < len(base_cols) else f"_extra{i}" for i in range(max_len)]
    df = pd.DataFrame(all_bars, columns=columns)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_extra")], errors="ignore")
    for col in ("开盘", "收盘", "最高", "最低", "成交量", "成交额"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "成交额" in df.columns and df["成交额"].isna().all():
        df["成交额"] = float("nan")  # 该市场不提供成交额时让 formatter 跳过
    # 自算涨跌额/涨跌幅（腾讯不返回）
    df["涨跌额"] = df["收盘"] - df["收盘"].shift(1)
    df["涨跌幅"] = df["涨跌额"] / df["收盘"].shift(1) * 100
    return df


def _hk_kline_impl(period: str, symbol: str, start_date: str, end_date: str, adjust: str) -> str:
    log_debug(f"[global_kline] HK/{period} symbol='{symbol}'")
    if not symbol:
        return "错误：必须提供 symbol 参数（港股代码，如 00700）"
    code = normalize_hk(symbol)
    if not code:
        return f"错误：无法识别的港股代码 '{symbol}'（示例：00700 或 700）"
    start, end, _ = _normalize_dates(start_date, end_date)
    adjust = adjust if adjust in ("qfq", "hfq") else ""
    df = _fetch_tx_kline(f"hk{code}", period, start, end, adjust)
    return format_kline(df, f"港股{_PERIOD_CN[period]}行情", "港元", f"{code}.HK", _lookup_name("HK", code))


def _us_kline_impl(period: str, symbol: str, start_date: str, end_date: str, adjust: str) -> str:
    log_debug(f"[global_kline] US/{period} symbol='{symbol}'")
    if not symbol:
        return "错误：必须提供 symbol 参数（美股代码，如 AAPL）"
    ticker = symbol.strip().upper()
    for prefix in ("105.", "106.", "107."):  # 容错：去掉东财风格前缀
        if ticker.startswith(prefix):
            ticker = ticker[len(prefix):]
    if ticker.endswith((".O", ".N", ".A")):
        ticker = ticker[:-2]
    start, end, _ = _normalize_dates(start_date, end_date)
    adjust = adjust if adjust in ("qfq", "hfq") else ""
    df = _fetch_tx_kline(f"us{ticker}", period, start, end, adjust)
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
    return format_kline(df, f"美股{_PERIOD_CN[period]}行情", "美元", ticker, _lookup_name("US", ticker))


def register_quote_tools(mcp) -> None:
    """注册港美股 K 线工具（日/周/月，腾讯源）。"""

    @mcp.tool()
    @handle_exception
    def hk_daily(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """
        获取港股日线行情（腾讯源，前复权可选，默认近3年、最早可到 2000 年代）。
        输出：日期 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅 | 成交量(股)。

        参数:
            symbol: 港股代码（'00700'=腾讯控股，支持 '700' 简写）
            start_date: 开始日期 (YYYYMMDD，可选，默认近3年)
            end_date: 结束日期 (YYYYMMDD，可选)
            adjust: 复权：''不复权 / 'qfq'前复权 / 'hfq'后复权（可选）
        """
        return _hk_kline_impl("daily", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def hk_weekly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取港股周线行情（腾讯源）。参数同 hk_daily（symbol 如 '00700'=腾讯控股）。"""
        return _hk_kline_impl("weekly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def hk_monthly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取港股月线行情（腾讯源）。参数同 hk_daily（symbol 如 '00700'=腾讯控股）。"""
        return _hk_kline_impl("monthly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def us_daily(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """
        获取美股日线行情（腾讯源，前复权可选，默认近3年）。
        输出：日期 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅 | 成交量(股)。

        参数:
            symbol: 美股代码（'AAPL'=苹果）
            start_date: 开始日期 (YYYYMMDD，可选，默认近3年)
            end_date: 结束日期 (YYYYMMDD，可选)
            adjust: 复权：''不复权 / 'qfq'前复权 / 'hfq'后复权（可选）
        """
        return _us_kline_impl("daily", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def us_weekly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取美股周线行情（腾讯源）。参数同 us_daily（symbol 如 'AAPL'=苹果）。"""
        return _us_kline_impl("weekly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def us_monthly(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """获取美股月线行情（腾讯源）。参数同 us_daily（symbol 如 'AAPL'=苹果）。"""
        return _us_kline_impl("monthly", symbol, start_date, end_date, adjust)

    @mcp.tool()
    @handle_exception
    def global_index_daily(symbol: str, period: str = "daily",
                           start_date: str = "", end_date: str = "") -> str:
        """
        获取全球指数K线（恒指HSI / 恒生科技HSTECH / 国企指数HSCEI / 道指DJIA /
        标普500 SPX / 纳指100 NDX / 纳指综合IXIC）。腾讯源。
        输出：日期 | 代码 | 名称 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅。

        参数:
            symbol: 指数代码或中文名（'HSI'/'恒指'、'SPX'/'标普500'、'IXIC'/'纳指' 等）
            period: 'daily'日线 / 'weekly'周线 / 'monthly'月线（默认日线）
            start_date: 开始日期 (YYYYMMDD，可选，默认近3年)
            end_date: 结束日期 (YYYYMMDD，可选)
        """
        log_debug(f"[global_index] symbol='{symbol}' period='{period}'")
        if not symbol:
            return "错误：必须提供 symbol 参数（指数代码，如 HSI/SPX/IXIC）"
        if period not in _PERIOD_TX:
            return f"错误：period 仅支持 daily/weekly/monthly，收到 '{period}'"
        resolved = resolve_index(symbol)
        if not resolved:
            return ("错误：暂不支持的指数。当前支持：HSI恒指 / HSTECH恒生科技 / "
                    "HSCEI国企指数 / DJIA道指 / SPX标普500 / NDX纳指100 / IXIC纳指综合")
        tx_code, name = resolved
        start, end, _ = _normalize_dates(start_date, end_date)
        df = _fetch_tx_kline(tx_code, period, start, end, "")
        return format_kline(df, f"{name}{_PERIOD_CN[period]}行情", "点", tx_code, name)
