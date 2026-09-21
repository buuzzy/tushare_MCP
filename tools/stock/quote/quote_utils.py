from __future__ import annotations

import datetime as dt
from typing import Iterable

import pandas as pd

from tools.stats_utils import STATS_PREFIX, fmt_num
from utils.logger import log_debug


def split_ts_codes(ts_code: str) -> list[str]:
    """Split the comma-separated code list commonly produced by LLM agents."""
    if not ts_code:
        return []
    return list(dict.fromkeys(code.strip() for code in ts_code.replace("，", ",").split(",") if code.strip()))


def is_index_code(ts_code: str) -> bool:
    """Identify the common A-share index code ranges used by TinyShare."""
    symbol, _, exchange = ts_code.partition(".")
    if exchange == "SH":
        return symbol.startswith("000")
    if exchange == "SZ":
        return symbol.startswith("399")
    return exchange == "CSI" or is_sw_index_code(ts_code)


def is_sw_index_code(ts_code: str) -> bool:
    symbol, _, exchange = ts_code.partition(".")
    return exchange == "SI" and symbol.startswith("801")


# 复权口径归一：'qfq'（默认前复权）/ 'hfq' 后复权 / '' 不复权；非法值回退 qfq。
def normalize_adjust(adjust: str) -> str:
    return adjust if adjust in ("qfq", "hfq", "") else "qfq"


# 参与复权缩放的价格类列（成交量/成交额/涨跌幅不缩放：前复权乘常数因子
# 不改变相邻日比值，pct_chg 本身已是除权调整后的真实涨跌幅）。
_ADJ_PRICE_COLS = ("open", "high", "low", "close", "pre_close", "change")


def _fetch_adj_factor(pro, code: str, api_params: dict) -> pd.DataFrame:
    try:
        af = pro.adj_factor(ts_code=code, **api_params)
    except Exception as e:
        log_debug(f"[adj] adj_factor fetch failed for {code}: {type(e).__name__}: {e}")
        return pd.DataFrame()
    if af is None or af.empty or "adj_factor" not in af.columns:
        return pd.DataFrame()
    return af[["trade_date", "adj_factor"]].copy()


def _apply_price_adjustment(
    pro, code: str, daily_df: pd.DataFrame, api_params: dict, adjust: str
) -> pd.DataFrame:
    """按复权因子调整价格列（工程解：模型拿到即最终口径）。

    - qfq（默认）：价格 × 因子/最新因子，最新收盘保持真实价，历史价随
      除权除息回溯调整——拆股/送转/分红不再呈现假断崖（2026-09-20 Q2
      实测：NVDA 10:1 拆股在不复权数据上呈现 -89% 假跌幅）。
    - hfq：价格 × 累计因子（以上市首日为基准 1）。
    - 因子接口不可用时降级不复权，df.attrs["adjust"] 始终记录实际口径，
      输出标题按实际口径声明，绝不虚标。
    """
    daily_df.attrs["adjust"] = ""
    if adjust not in ("qfq", "hfq") or daily_df is None or daily_df.empty:
        return daily_df
    af = _fetch_adj_factor(pro, code, api_params)
    if af.empty:
        log_debug(f"[adj] no adj_factor for {code}, fallback to unadjusted")
        return daily_df
    merged = daily_df.merge(af, on="trade_date", how="inner")
    if merged.empty:
        return daily_df
    factor = pd.to_numeric(merged["adj_factor"], errors="coerce")
    if adjust == "qfq":
        # 前复权基准 = 全历史最新因子。区间末即为最新（end_date 缺省或为
        # 今天）时直接取区间内最大日期的因子；区间止于过去时补拉一次
        # 最近因子（近 15 天窗口内必有一条），否则历史除权会漏调。
        base = float(pd.to_numeric(af.sort_values("trade_date")["adj_factor"]).iloc[-1])
        last_date = str(af["trade_date"].max())
        today = dt.date.today().strftime("%Y%m%d")
        if last_date < today:
            try:
                recent = pro.adj_factor(
                    ts_code=code,
                    start_date=(dt.date.today() - dt.timedelta(days=15)).strftime("%Y%m%d"),
                )
                if recent is not None and not recent.empty:
                    base = float(pd.to_numeric(recent.sort_values("trade_date")["adj_factor"]).iloc[-1])
            except Exception as e:
                log_debug(f"[adj] recent factor fetch failed for {code}: {type(e).__name__}")
        if not base:
            return daily_df
        k = factor / base
    else:
        k = factor
    for col in _ADJ_PRICE_COLS:
        if col in merged.columns:
            merged[col] = (pd.to_numeric(merged[col], errors="coerce") * k).round(4)
    merged = merged.drop(columns=["adj_factor"])
    merged.attrs["adjust"] = adjust
    return merged


def _period_window_params(api_params: dict, period: str) -> dict:
    """trade_date 单周期查询 -> 覆盖整个自然周/月的日线区间参数。

    股票周/月线改为日线聚合后，trade_date（周五/月末）需换算成日线
    start/end（回看 6/31 个自然日必覆盖该周/月），聚合后取该根。
    """
    trade_date = str(api_params.get("trade_date") or "")
    if not trade_date:
        return api_params
    try:
        d = dt.datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        return api_params
    params = {k: v for k, v in api_params.items() if k != "trade_date"}
    back = 6 if period == "weekly" else 31
    params["start_date"] = (d - dt.timedelta(days=back)).strftime("%Y%m%d")
    params["end_date"] = trade_date
    return params


def _aggregate_stock_daily(daily_df: pd.DataFrame, period: str) -> pd.DataFrame:
    """日线 -> 周/月线（股票，复权后聚合），附 high_date/low_date 极值发生日。

    与港股/美股周月线的"日线拉取+本地聚合"口径完全对齐：原生周/月线
    API 无极值发生日，统计行只能给周期截止日，与精确日期打架（同款
    事故见 _hk_kline_impl 注释）。聚合后一并解决。
    """
    daily_df = daily_df.sort_values("trade_date").reset_index(drop=True)
    dts = pd.to_datetime(daily_df["trade_date"], format="%Y%m%d")
    key = dts.dt.to_period("W-SUN" if period == "weekly" else "M").astype(str)
    grouped = daily_df.groupby(key, sort=True)
    agg = grouped.agg(
        ts_code=("ts_code", "first"),
        trade_date=("trade_date", "max"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        vol=("vol", "sum"),
        amount=("amount", "sum"),
    ).reset_index(drop=True)
    agg["high_date"] = grouped.apply(lambda g: g.loc[g["high"].idxmax(), "trade_date"]).values
    agg["low_date"] = grouped.apply(lambda g: g.loc[g["low"].idxmin(), "trade_date"]).values
    agg["pre_close"] = agg["close"].shift(1)
    agg["change"] = agg["close"] - agg["pre_close"]
    agg["pct_chg"] = agg["change"] / agg["pre_close"] * 100
    return agg


def _fetch_stock_adjusted(
    pro, code: str, period: str, api_params: dict, adjust: str
) -> pd.DataFrame:
    """股票 K 线统一入口：日线 + 复权因子，周/月线本地聚合。

    pro.daily/pro.weekly/pro.monthly 均为不复权价，且原生周/月线无极值
    发生日。股票侧一律走 daily + adj_factor（qfq 默认）再聚合，一个入口
    同时解决复权缺口与极值日期缺口；指数/申万无复权概念，不走此函数。
    """
    adjust = normalize_adjust(adjust)
    query_params = api_params if period == "daily" else _period_window_params(api_params, period)
    daily_df = pro.daily(ts_code=code, **query_params)
    if daily_df is None or daily_df.empty:
        return pd.DataFrame()
    daily_df = _apply_price_adjustment(pro, code, daily_df, query_params, adjust)
    if period == "daily":
        return daily_df
    agg = _aggregate_stock_daily(daily_df, period)
    original = str(api_params.get("trade_date") or "")
    if original:
        agg = agg[agg["trade_date"] == original]
    agg.attrs["adjust"] = daily_df.attrs.get("adjust", "")
    return agg


def fetch_quote_data(
    pro,
    stock_api: str,
    index_api: str,
    period: str,
    ts_code: str,
    adjust: str = "qfq",
    **api_params,
) -> pd.DataFrame:
    """Fetch stock or index quotes, splitting multi-code requests locally.

    股票代码走 _fetch_stock_adjusted（daily + adj_factor，默认前复权，
    周/月线本地聚合出极值发生日）；指数/申万无复权概念，保持原 API。
    df.attrs["adjust"] 记录股票侧实际生效口径，供输出标题声明。
    """
    codes = split_ts_codes(ts_code)
    if not codes:
        return getattr(pro, stock_api)(**api_params)

    frames: list[pd.DataFrame] = []
    sw_codes: list[str] = []
    effective_adjust = ""
    for code in codes:
        if is_sw_index_code(code):
            sw_codes.append(code)
            continue
        if is_index_code(code):
            api_name = index_api
            frame = getattr(pro, api_name)(**api_params, ts_code=code)
        elif stock_api in ("daily", "weekly", "monthly"):
            frame = _fetch_stock_adjusted(pro, code, period, api_params, adjust)
            effective_adjust = str(frame.attrs.get("adjust", "")) or effective_adjust
        else:
            frame = getattr(pro, stock_api)(**api_params, ts_code=code)
        if frame is not None and not frame.empty:
            frames.append(frame)

    if sw_codes:
        frame = _fetch_sw_quote_data(
            pro,
            period=period,
            codes=sw_codes,
            **api_params,
        )
        if not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.attrs["adjust"] = effective_adjust
    return df


def _fetch_sw_quote_data(
    pro,
    period: str,
    codes: list[str],
    **api_params,
) -> pd.DataFrame:
    """Fetch Shenwan daily bars and aggregate them for weekly/monthly tools."""
    frames: list[pd.DataFrame] = []
    for code in codes:
        frame = pro.sw_daily(**api_params, ts_code=code)
        if frame is not None and not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()

    daily = pd.concat(frames, ignore_index=True)
    daily = daily.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    daily = daily.rename(columns={"pct_change": "pct_chg"})
    if period == "daily":
        return daily

    daily["trade_date_dt"] = pd.to_datetime(daily["trade_date"], format="%Y%m%d")
    frequency = "W-SUN" if period == "weekly" else "M"
    daily["__period"] = daily["trade_date_dt"].dt.to_period(frequency).astype(str)
    grouped = (
        daily.groupby(["ts_code", "__period"], sort=False)
        .agg(
            trade_date=("trade_date", "max"),
            name=("name", "first"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            vol=("vol", "sum"),
            amount=("amount", "sum"),
        )
        .reset_index()
    )
    grouped = grouped.sort_values(["ts_code", "trade_date"])
    grouped["pre_close"] = grouped.groupby("ts_code")["close"].shift(1)
    grouped["change"] = grouped["close"] - grouped["pre_close"]
    grouped["pct_chg"] = grouped["change"] / grouped["pre_close"] * 100
    return grouped.drop(columns=["__period"])


def _select_display_rows(df: pd.DataFrame, requested_codes: Iterable[str], per_code_limit: int) -> pd.DataFrame:
    code_list = list(requested_codes)
    if not code_list or "ts_code" not in df.columns:
        selected = df.sort_values("trade_date", ascending=False).head(per_code_limit)
        return selected.sort_values("trade_date", ascending=True).reset_index(drop=True)

    parts: list[pd.DataFrame] = []
    code_order = {code: index for index, code in enumerate(code_list)}
    known_codes = set()
    for code in code_list:
        known_codes.add(code)
        part = df[df["ts_code"] == code].sort_values("trade_date", ascending=False).head(per_code_limit)
        if part.empty:
            continue
        part = part.copy()
        part["__code_order"] = code_order[code]
        parts.append(part)

    # Preserve unexpected codes returned by the API instead of silently dropping them.
    for code in df["ts_code"].drop_duplicates():
        if code in known_codes:
            continue
        part = df[df["ts_code"] == code].sort_values("trade_date", ascending=False).head(per_code_limit)
        part = part.copy()
        part["__code_order"] = len(code_order)
        parts.append(part)

    if not parts:
        return pd.DataFrame()
    selected = pd.concat(parts, ignore_index=True)
    selected = selected.sort_values(["__code_order", "trade_date"], ascending=[True, True])
    return selected.drop(columns="__code_order").reset_index(drop=True)


def _interval_stats_line(sub: pd.DataFrame, code: str | None) -> str | None:
    """单个代码区间的服务端统计行（对全量 df 计算，含未显示的行）。

    周/月线场景 df 附带 high_date/low_date（极值发生的具体交易日），
    统计行优先取极值日而非周期截止日，与港股/美股口径一致。
    """
    if sub.empty:
        return None
    date_col = "trade_date"
    parts = []

    def _extreme(value_col: str, date_attr: str):
        if value_col not in sub.columns or sub[value_col].dropna().empty:
            return None, None
        row = sub.loc[sub[value_col].idxmax() if value_col == "high" else sub[value_col].idxmin()]
        date = row[date_attr] if date_attr in sub.columns and pd.notna(row.get(date_attr)) else row[date_col]
        return row[value_col], date

    hi_val, hi_date = _extreme("high", "high_date")
    if hi_val is not None:
        parts.append(f"区间最高 high={fmt_num(hi_val)}（{hi_date}）")
    lo_val, lo_date = _extreme("low", "low_date")
    if lo_val is not None:
        parts.append(f"区间最低 low={fmt_num(lo_val)}（{lo_date}）")

    # 区间涨跌幅：最早/最新收盘价由代码计算，避免模型自行除法出错
    if "close" in sub.columns:
        closes = sub[[date_col, "close"]].dropna(subset=["close"]).sort_values(date_col)
        if len(closes) >= 2 and closes["close"].iloc[0]:
            chg = (closes["close"].iloc[-1] / closes["close"].iloc[0] - 1) * 100
            sign = "+" if chg >= 0 else ""
            parts.append(f"区间涨跌幅={sign}{chg:.2f}%")
            parts.append(f"最新 {closes[date_col].iloc[-1]} 收 {fmt_num(closes['close'].iloc[-1])}")

    if not parts:
        return None
    tag = f"[{code}]：" if code else "："
    return f"... {STATS_PREFIX}{tag}" + "；".join(parts)


def _long_window_display(df: pd.DataFrame, period: str) -> tuple[pd.DataFrame, str]:
    """长窗口图表供给：单代码行数超限时自动聚合，图表拿到全史。

    与港美股 format_kline 同款策略（2026-09-21 Q3 实测：A股日线 725 行
    只显示尾部 50 条，图表"标题近三年、图上近 50 天"）。日线超 250 聚
    周线，周线仍超聚月线；周线工具超 250 直接聚月线。聚合复用
    _aggregate_stock_daily（复权后聚合，附 high_date/low_date 极值日）。
    返回 (展示df, 置顶提示)；无需聚合返回 (原df, "")。
    """
    if "ts_code" not in df.columns or df.empty:
        return df, ""
    parts: list[pd.DataFrame] = []
    freq = ""
    for code in df["ts_code"].dropna().unique():
        sub = df[df["ts_code"] == code]
        if len(sub) <= 250:
            parts.append(sub)
            continue
        target = "weekly" if period == "daily" else "monthly"
        agg = _aggregate_stock_daily(sub, target)
        if len(agg) > 250 and target == "weekly":
            agg = _aggregate_stock_daily(sub, "monthly")
            freq = "月"
        else:
            freq = freq or "周"
        parts.append(agg)
    if not freq:
        return df, ""
    out = pd.concat(parts, ignore_index=True)
    note = (
        f"原始数据单代码超过 250 根，已自动聚合为{freq}线全史共 {{n}} 条（每周/月 high/low 为期内日内极值，"
        f"high_date/low_date 为极值发生日，求区间最高/最低/涨跌幅与日线完全等效；"
        f"📊 区间统计行按原始数据计算，精度到日）。图表绘制区间走势直接用本数据；"
        f"如需日线明细，请缩小日期范围重新查询。"
    )
    return out, note.replace("{n}", str(len(out)))


def format_quote_data(
    df: pd.DataFrame, period: str, requested_codes: Iterable[str], adjust: str = ""
) -> str:
    labels = {
        "daily": ("日线", ""),
        "weekly": ("周线", "周"),
        "monthly": ("月线", "月"),
    }
    period_name, value_prefix = labels[period]
    # 口径声明以实际生效的复权为准（fetch 阶段 attrs 必记录实际口径，
    # 因子不可用降级不复权时 attrs=""，不虚标前复权；纯指数调用同样不声明）
    if "adjust" in df.attrs:
        effective = str(df.attrs["adjust"])
    else:
        effective = normalize_adjust(adjust)
    adjust_suffix = {"qfq": "，前复权", "hfq": "，后复权"}.get(effective, "")
    # 长窗口图表供给：单代码超 250 根自动聚合成全史周/月线（港美股同款），
    # 聚合结果整段输出（不再套 50 条显示上限，否则图表又只剩尾部）
    display_source, long_note = _long_window_display(df, period)
    if long_note:
        display_df = display_source.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    else:
        display_df = _select_display_rows(display_source, requested_codes, per_code_limit=50)
    requested_code_list = list(requested_codes)

    results = [f"--- {period_name}行情数据 (Total: {len(df)}{adjust_suffix}) ---"]
    if long_note:
        results.append(
            f"... ⚠️ 已聚合展示 {len(display_df)} 条。{long_note}"
        )
    for _, row in display_df.iterrows():
        info = []
        if pd.notna(row.get("trade_date")):
            info.append(f"日期:{row['trade_date']}")
        if pd.notna(row.get("ts_code")):
            info.append(f"代码:{row['ts_code']}")
        if pd.notna(row.get("name")):
            info.append(f"名称:{row['name']}")
        pre_close_label = {"daily": "昨收", "weekly": "上周收盘", "monthly": "上月收盘"}[period]
        for field, label in (
            ("open", "开盘"),
            ("high", "最高"),
            ("high_date", "最高日"),
            ("low", "最低"),
            ("low_date", "最低日"),
            ("close", "收盘"),
            ("pre_close", pre_close_label),
            ("change", "涨跌额"),
            ("pct_chg", "涨跌幅"),
        ):
            if pd.notna(row.get(field)):
                if field in ("high_date", "low_date"):
                    # 极值发生日不带周期前缀（"最高日"而非"周最高日"）
                    info.append(f"{label}:{row[field]}")
                    continue
                info.append(f"{value_prefix}{label}:{row[field]}")
        if pd.notna(row.get("pct_chg")):
            info[-1] += "%"
        if pd.notna(row.get("vol")):
            info.append(f"{value_prefix}成交量:{row['vol']}手")
        if pd.notna(row.get("amount")):
            info.append(f"{value_prefix}成交额:{row['amount']}千元")
        results.append(" | ".join(info))

    if "ts_code" in df.columns:
        found_codes = set(df["ts_code"].dropna())
        missing_codes = [code for code in requested_code_list if code not in found_codes]
        if missing_codes:
            results.append("未找到代码:" + ",".join(missing_codes))

    if len(display_df) < len(display_source):
        results.append(f"... (共 {len(display_source)} 条，每个代码仅显示最近 50 条)")

    # 区间统计：极值扫描是代码该干的活（同款事故见 tools/stats_utils.py 注释）。
    # 对全量 df 计算——截断场景下未显示行的极值也能统计到。
    if not df.empty and {"high", "low"}.issubset(df.columns):
        if "ts_code" in df.columns and not df["ts_code"].dropna().empty:
            code_order = list(dict.fromkeys(
                list(requested_code_list) + df["ts_code"].dropna().unique().tolist()
            ))
            for code in code_order:
                line = _interval_stats_line(df[df["ts_code"] == code], code)
                if line:
                    results.append(line)
        else:
            line = _interval_stats_line(df, None)
            if line:
                results.append(line)

    return "\n".join(results)
