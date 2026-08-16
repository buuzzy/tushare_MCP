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
    return exchange == "CSI"


def fetch_quote_data(
    pro,
    stock_api: str,
    index_api: str,
    ts_code: str,
    **api_params,
) -> pd.DataFrame:
    """Fetch stock or index quotes, splitting multi-code requests locally."""
    codes = split_ts_codes(ts_code)
    if not codes:
        return getattr(pro, stock_api)(**api_params)

    frames: list[pd.DataFrame] = []
    for code in codes:
        api_name = index_api if is_index_code(code) else stock_api
        frame = getattr(pro, api_name)(**api_params, ts_code=code)
        if frame is not None and not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


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

    results = [f"--- {period_name}行情数据 (Total: {len(df)}) ---"]
    for _, row in display_df.iterrows():
        info = []
        if pd.notna(row.get("trade_date")):
            info.append(f"日期:{row['trade_date']}")
        if pd.notna(row.get("ts_code")):
            info.append(f"代码:{row['ts_code']}")
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

    if len(display_df) < len(df):
        results.append(f"... (共 {len(df)} 条，每个代码仅显示最近 50 条)")
    return "\n".join(results)
