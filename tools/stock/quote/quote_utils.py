from __future__ import annotations

from typing import Iterable

import pandas as pd


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


def fetch_quote_data(
    pro,
    stock_api: str,
    index_api: str,
    period: str,
    ts_code: str,
    **api_params,
) -> pd.DataFrame:
    """Fetch stock or index quotes, splitting multi-code requests locally."""
    codes = split_ts_codes(ts_code)
    if not codes:
        return getattr(pro, stock_api)(**api_params)

    frames: list[pd.DataFrame] = []
    sw_codes: list[str] = []
    for code in codes:
        if is_sw_index_code(code):
            sw_codes.append(code)
        else:
            api_name = index_api if is_index_code(code) else stock_api
            frame = getattr(pro, api_name)(**api_params, ts_code=code)
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
    return pd.concat(frames, ignore_index=True)


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


def format_quote_data(df: pd.DataFrame, period: str, requested_codes: Iterable[str]) -> str:
    labels = {
        "daily": ("日线", ""),
        "weekly": ("周线", "周"),
        "monthly": ("月线", "月"),
    }
    period_name, value_prefix = labels[period]
    display_df = _select_display_rows(df, requested_codes, per_code_limit=50)
    requested_code_list = list(requested_codes)

    results = [f"--- {period_name}行情数据 (Total: {len(df)}) ---"]
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
            ("low", "最低"),
            ("close", "收盘"),
            ("pre_close", pre_close_label),
            ("change", "涨跌额"),
            ("pct_chg", "涨跌幅"),
        ):
            if pd.notna(row.get(field)):
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

    if len(display_df) < len(df):
        results.append(f"... (共 {len(df)} 条，每个代码仅显示最近 50 条)")
    return "\n".join(results)
