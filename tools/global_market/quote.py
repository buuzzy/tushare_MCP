"""港美股与全球指数的 K 线工具（日线/周线/月线）。

数据源：腾讯 ifzq.gtimg.cn（fqkline/kline 接口）。东财 push2his 对海外
数据中心 IP 存在无法根治的动态封禁（2026-09-13 线上实测：连续使用后
进入分钟级以上封禁、等待不复位），故行情统一走腾讯；财务/代码表仍走
东财 datacenter（不受影响）。所有请求经 em_client 限频。
"""

# 注意：本模块注册的工具函数带参数注解，mcp 1.7.1 的 Tool.from_function 会对
# 注解做 issubclass 判断；`from __future__ import annotations` 会把注解字符串化，
# 在部分 Python 版本（3.13 实测）导致注册直接 TypeError。本仓库 Python>=3.11，
# PEP 585/604 注解可原生求值，因此**禁止在此模块加 future annotations import**。

import datetime as dt
import time

import akshare as ak
import pandas as pd
import requests

from tools.global_market.em_client import em_call, TTL_KLINE
from tools.global_market.global_formatting import format_kline
from tools.global_market.symbol_resolver import (
    _load_hk_list, _load_us_list, normalize_hk, resolve_index,
    search_symbols,
)
from utils.logger import log_debug, log_info, handle_exception

_PERIOD_CN = {"daily": "日线", "weekly": "周线", "monthly": "月线"}
_PERIOD_TX = {"daily": "day", "weekly": "week", "monthly": "month"}

_TX_URL = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"
# 注：kline/get（不复权端点）实测已废弃（任何 param 均返回 code=11）；
# 不复权统一走 fqkline + 空 fq 段（尾逗号），实测 800 bars 正常。
_TX_BATCH = 800        # 单次请求上限（实测 800 可用）
# 每段自然日跨度（≈538 个交易日，必定低于单次 800 根上限——
# 因此绝不能以"返回不足一批"判定区间结束，见 _fetch_tx_kline）
_TX_SEGMENT_DAYS = 800
_TX_SEGMENT_GAP_SEC = 1.0  # 腾讯境外反爬：分段请求之间的最小间隔（秒）
# 连接超时单独收紧：跨境链路（Railway -> 境内行情源）的黑洞式丢包表现为
# 连接阶段挂死，15s 的连接超时纯属浪费；读超时保持 15s 不变。
_TX_TIMEOUT = (5.0, 15.0)
# 单次上游请求耗时超过该阈值就告警一行，用于线上判定跨境链路是否变慢
_TX_SLOW_SEC = float(5.0)


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


def _tx_fetch_once(tx_code: str, period: str, seg_start: str, seg_end: str, adjust: str) -> tuple[list[list], str]:
    """单次腾讯 K 线请求，返回 (bars, 证券中文名)。名称取自响应 qt 段（可能为空）。"""
    fq = adjust if adjust in ("qfq", "hfq") else ""

    def _do():
        started = time.monotonic()
        r = requests.get(
            _TX_URL,
            params={"param": _tx_param(tx_code, period, seg_start, seg_end, fq)},
            timeout=_TX_TIMEOUT,
        )
        elapsed = time.monotonic() - started
        if elapsed >= _TX_SLOW_SEC:
            # 仅慢响应时输出一行（正常路径 <1s 不产生日志），
            # 用于线上判定"慢"到底慢在跨境链路还是数据加工
            log_info(
                f"[global_kline] 上游慢响应 host=ifzq.gtimg.cn 用时 {elapsed:.1f}s "
                f"（阈值 {_TX_SLOW_SEC:.0f}s）status={r.status_code} code={tx_code} {period}"
            )
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
    bars = node.get(key) or node.get(_PERIOD_TX[period]) or []
    qt_row = (node.get("qt") or {}).get(tx_code) or []
    name = str(qt_row[1]).strip() if len(qt_row) > 1 else ""
    return bars, name


def _fetch_tx_kline(tx_code: str, period: str, start: str, end: str, adjust: str) -> tuple[pd.DataFrame, str]:
    """按日期分段拉取腾讯 K 线并拼接（单次上限约 800 根）。

    腾讯按"区间内截取至多 count 根"返回，故从 start 起逐段向前推进。
    - 空段不终止扫描：上市前/长期停牌的段无数据属正常，跳到下一段继续
      （实测次新股 hk02714 默认近 3 年窗口首段全空，一旦 break 即误报无数据）。
    - 段是否结束只看 last_date 是否到达 end：800 自然日 ≈ 538 个交易日，
      首段必然"不足一批"（<800 根），旧判据 len(bars)<_TX_BATCH 即停导致
      长窗口止步首段（2026-09-14 实测 hk00700 默认窗口数据停在 2025-11-21）。
    返回 (DataFrame, 证券中文名)；名称取自任一段响应的 qt 段，可能为空。
    """
    all_bars: list[list] = []
    name = ""
    seg_days = _TX_SEGMENT_DAYS * (5 if period == "weekly" else 22 if period == "monthly" else 1)
    cursor = start
    _seg_seq = 0
    while cursor <= end:
        # 腾讯对境外 IP 的反爬：同一来源毫秒级连发的第 2 段请求会被挂死
        # （2026-09-20 新加坡节点实测：单段正常 ~1s，连续两段第二段永久读超时）。
        # 段与段之间强制留出间隔。
        _seg_seq += 1
        if _seg_seq > 1:
            time.sleep(_TX_SEGMENT_GAP_SEC)
        seg_end_dt = dt.datetime.strptime(cursor, "%Y-%m-%d").date() + dt.timedelta(days=seg_days)
        seg_end = min(seg_end_dt.isoformat(), end)
        bars, seg_name = _tx_fetch_once(tx_code, period, cursor, seg_end, adjust)
        name = name or seg_name
        if not bars:
            if seg_end >= end:
                break  # 已扫完全区间仍无数据
            cursor = (seg_end_dt + dt.timedelta(days=1)).isoformat()  # 上市前/停牌空段，跳过
            continue
        for bar in bars:
            if not all_bars or bar[0] > all_bars[-1][0]:
                all_bars.append(bar)
        last_date = dt.datetime.strptime(bars[-1][0], "%Y-%m-%d").date()
        if last_date.isoformat() >= end:
            break
        # 关键：游标至少要推进过本段边界。腾讯对 end≥今天的无效区间（周末/
        # 未来日期）会返回 1 根旧K线（如周五收盘那根），last_date 可能落后于
        # 游标；若仅用 last_date+1 推进，游标原地踏步 → 无限循环（2026-09-20
        # 实锤："时好时坏"的根因——周末 100% 触发、交易日正常）。段内不可能
        # 截断（800 自然日 ≈ 538 交易日 < 800 根上限），跳到 seg_end+1 无损。
        cursor = (max(last_date, seg_end_dt) + dt.timedelta(days=1)).isoformat()

    if not all_bars:
        return pd.DataFrame(), name
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
    return df, name


def _fetch_us_kline(ticker: str, adjust: str) -> pd.DataFrame:
    """美股 K 线（新浪源全历史，本地过滤日期）。

    腾讯 fqkline 对美股实测仅返回 1 根（无论日期区间/复权参数），不可用，
    故美股走新浪全历史（一次拉取 + 缓存，akshare 解码）。
    返回中文列 DataFrame。
    """
    fq = adjust if adjust in ("qfq", "hfq") else ""
    df = em_call(
        "sina_quote",
        lambda: ak.stock_us_daily(symbol=ticker, adjust=fq),
        cache_key=f"us_kl_sina:{ticker}:{fq}",
        ttl_seconds=TTL_KLINE,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "日期": df["date"].astype(str),
        "开盘": pd.to_numeric(df["open"], errors="coerce"),
        "最高": pd.to_numeric(df["high"], errors="coerce"),
        "最低": pd.to_numeric(df["low"], errors="coerce"),
        "收盘": pd.to_numeric(df["close"], errors="coerce"),
        "成交量": pd.to_numeric(df["volume"], errors="coerce"),
    })
    out["涨跌额"] = out["收盘"] - out["收盘"].shift(1)
    out["涨跌幅"] = out["涨跌额"] / out["收盘"].shift(1) * 100
    return out


def _staleness_note(df: pd.DataFrame, end: str) -> str:
    """最新一根 K 线距区间末超过 10 个自然日时附加提示（停牌/退市等）。

    行以 "..." 开头：与截断脚注同款，data-cache 解析器跳过该行，
    不会污染服务端图表缓存数据；Agent 据此如实告知用户而非当作最新数据。
    """
    try:
        last = str(df["日期"].iloc[-1])
        gap = (dt.date.fromisoformat(end) - dt.date.fromisoformat(last)).days
        if gap > 10:
            return (f"\n... (注意：最新数据仅到 {last}，距区间末 {end} 已 {gap} 天，"
                    f"标的可能停牌或退市)")
    except Exception:
        log_debug("[global_kline] staleness note skipped")
    return ""


_EM_HK_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_FQ = {"": "0", "qfq": "1", "hfq": "2"}
# 超过该自然日跨度的港股日线走东财单请求（一次拉全历史再本地截取），
# 避免腾讯多段拼接；窄窗口仍以腾讯为主（实测 0.5s、稳定且省配额）
_EM_HK_LONG_WINDOW_DAYS = 700


def _fetch_em_kline_hk(code: str, start: str, end: str, adjust: str) -> tuple[pd.DataFrame, str]:
    """港股日线（东财 push2his 单请求全历史，组内强制串行）。

    仅限日线；东财组并发零容忍（实测并发即断连），em_call 已按组串行。
    返回 (中文列 DataFrame, 证券名称)，失败抛异常由调用方决定降级。
    """
    def _do():
        r = requests.get(
            _EM_HK_KLINE_URL,
            params={
                "secid": f"116.{code}",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": "101",  # 日线
                "fqt": _EM_FQ.get(adjust, "0"),
                "end": "20500101",
                "lmt": "1000000",
            },
            timeout=(3, 10),
        )
        return r.json()

    resp = em_call(
        "eastmoney_quote",
        _do,
        cache_key=f"em_kl:116.{code}:{adjust}",
        ttl_seconds=TTL_KLINE,
    )
    data = resp.get("data") or {}
    kl = data.get("klines") or []
    if not kl:
        return pd.DataFrame(), ""
    rows = []
    for line in kl:
        p = line.split(",")
        # f51日期,f52开盘,f53收盘,f54最高,f55最低,f56成交量,f57成交额
        rows.append([p[0], p[1], p[2], p[3], p[4], p[5], p[6]])
    df = pd.DataFrame(rows, columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"])
    for c in ("开盘", "收盘", "最高", "最低", "成交量", "成交额"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[(df["日期"] >= start) & (df["日期"] <= end)]
    name = str(data.get("name") or "").strip()
    return df, name


def _hk_kline_impl(period: str, symbol: str, start_date: str, end_date: str, adjust: str) -> str:
    log_debug(f"[global_kline] HK/{period} symbol='{symbol}'")
    if not symbol:
        return "错误：必须提供 symbol 参数（港股代码，如 00700）"
    code = normalize_hk(symbol)
    if not code:
        return f"错误：无法识别的港股代码 '{symbol}'（示例：00700 或 700）"
    start, end, _ = _normalize_dates(start_date, end_date)
    adjust = adjust if adjust in ("qfq", "hfq") else ""
    span_days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days

    df, name = pd.DataFrame(), ""
    if period == "daily" and span_days > _EM_HK_LONG_WINDOW_DAYS:
        # 长窗口日线：东财单请求为主（免多段拼接），失败降级腾讯分段
        try:
            df, em_name = _fetch_em_kline_hk(code, start, end, adjust)
            name = em_name
        except Exception as e:
            log_debug(f"[global_kline] EM 长窗口失败，降级腾讯分段: {type(e).__name__}")
            df = pd.DataFrame()
        if df.empty:
            df, tx_name = _fetch_tx_kline(f"hk{code}", period, start, end, adjust)
            name = name or tx_name
    else:
        # 窄窗口（及周/月线）：腾讯为主，失败降级东财
        df, tx_name = _fetch_tx_kline(f"hk{code}", period, start, end, adjust)
        name = tx_name
        if df.empty and period == "daily":
            try:
                df, em_name = _fetch_em_kline_hk(code, start, end, adjust)
                name = name or em_name
            except Exception as e:
                log_debug(f"[global_kline] EM 备源失败: {type(e).__name__}")
                df = pd.DataFrame()
    name = name or _lookup_name("HK", code)
    if df.empty:
        hint = ""
        try:
            rows = [r for r in search_symbols(symbol, market="hk", limit=5)
                    if r["name"] != r["code"]]
            if rows:
                hint = "候选：" + "; ".join(f"{r['code']} {r['name']}" for r in rows)
        except Exception:
            pass
        hint = hint or "该代码可能不存在或已退市，建议与用户确认代码；也可用 search_symbol 按名称搜索"
        return (f"未找到港股{_PERIOD_CN[period]}行情数据（symbol='{symbol}'，"
                f"区间 {start}~{end}）。{hint}")
    return format_kline(df, f"港股{_PERIOD_CN[period]}行情", "港元", f"{code}.HK", name) + _staleness_note(df, end)


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

    df = _fetch_us_kline(ticker, adjust)
    if df is None or df.empty:
        hint = ""
        try:
            rows = search_symbols(symbol, market="us", limit=5)
            if rows:
                hint = "候选：" + "; ".join(f"{r['code']} {r['name']}" for r in rows)
        except Exception:
            pass
        hint = hint or "该代码可能不存在或已退市，建议与用户确认代码；也可用 search_symbol 按名称搜索"
        return f"未找到美股行情数据（symbol='{symbol}'）。{hint}"

    df = df[(df["日期"] >= start) & (df["日期"] <= end)]
    if period in ("weekly", "monthly"):
        # 新浪源仅提供日线，周/月线本地聚合（美股周线以周五为界）
        dates = pd.to_datetime(df["日期"])
        period_key = (dates.dt.to_period("W-FRI") if period == "weekly"
                      else dates.dt.to_period("M")).astype(str)
        df = (df.groupby(period_key, sort=True)
                .agg(日期=("日期", "first"), 开盘=("开盘", "first"), 最高=("最高", "max"),
                     最低=("最低", "min"), 收盘=("收盘", "last"), 成交量=("成交量", "sum"))
                .reset_index(drop=True))
        df["涨跌额"] = df["收盘"] - df["收盘"].shift(1)
        df["涨跌幅"] = df["涨跌额"] / df["收盘"].shift(1) * 100

    if df.empty:
        return f"未找到美股行情数据（symbol='{symbol}'，区间 {start}~{end}）"
    return format_kline(df, f"美股{_PERIOD_CN[period]}行情", "美元", ticker, _lookup_name("US", ticker)) + _staleness_note(df, end)


def _fetch_us_index_kline(code: str, period: str, start: str, end: str) -> pd.DataFrame:
    """美股指数 K 线（新浪源，全历史+缓存+本地过滤，周/月本地聚合）。"""
    df = em_call(
        "sina_quote",
        lambda: ak.index_us_stock_sina(symbol=code),
        cache_key=f"us_idx:{code}",
        ttl_seconds=TTL_KLINE,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "日期": df["date"].astype(str),
        "开盘": pd.to_numeric(df["open"], errors="coerce"),
        "最高": pd.to_numeric(df["high"], errors="coerce"),
        "最低": pd.to_numeric(df["low"], errors="coerce"),
        "收盘": pd.to_numeric(df["close"], errors="coerce"),
        "成交量": pd.to_numeric(df["volume"], errors="coerce"),
    })
    out = out[(out["日期"] >= start) & (out["日期"] <= end)]
    if period in ("weekly", "monthly") and not out.empty:
        dates = pd.to_datetime(out["日期"])
        period_key = (dates.dt.to_period("W-FRI") if period == "weekly"
                      else dates.dt.to_period("M")).astype(str)
        out = (out.groupby(period_key, sort=True)
                  .agg(日期=("日期", "first"), 开盘=("开盘", "first"), 最高=("最高", "max"),
                       最低=("最低", "min"), 收盘=("收盘", "last"), 成交量=("成交量", "sum"))
                  .reset_index(drop=True))
    if not out.empty:
        out["涨跌额"] = out["收盘"] - out["收盘"].shift(1)
        out["涨跌幅"] = out["涨跌额"] / out["收盘"].shift(1) * 100
    return out


def register_quote_tools(mcp) -> None:
    """注册港美股 K 线工具（日/周/月，腾讯源）。"""

    @mcp.tool()
    @handle_exception
    def hk_daily(symbol: str, start_date: str = "", end_date: str = "", adjust: str = "") -> str:
        """
        获取港股日线行情（前复权可选，默认近3年、最早可到 2000 年代）。
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
        获取美股日线行情（前复权可选，默认近3年）。
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
        获取全球指数K线（恒指HSI / 恒生科技HSTECH / 国企指数HSCEI / 道指DJIA /
        标普500 SPX / 纳指100 NDX / 纳指综合IXIC）。
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
        index_code, name = resolved
        start, end, _ = _normalize_dates(start_date, end_date)
        # 港股指数走腾讯；美股指数走新浪（腾讯 fqkline 对 us 前缀区间仅返回 1 根）
        if index_code.startswith("."):
            df = _fetch_us_index_kline(index_code, period, start, end)
        else:
            df, _ = _fetch_tx_kline(index_code, period, start, end, "")
        return format_kline(df, f"{name}{_PERIOD_CN[period]}行情", "点", index_code, name)
