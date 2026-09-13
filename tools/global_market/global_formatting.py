"""港美股工具的统一输出格式化。

输出为一行一条记录的 `key:value | key:value` 文本，与 A 股工具及
sage-web 侧 data-cache.ts 的解析器（按行、按 `|` 分段、按第一个冒号取键）兼容。
"""

from __future__ import annotations

import pandas as pd

# 港股主要指标：字段 -> 中文标签（列存在才输出）
HK_INDICATOR_FIELDS: list[tuple[str, str]] = [
    ("BASIC_EPS", "EPS"),
    ("BPS", "BPS"),
    ("OPERATE_INCOME", "营业收入"),
    ("OPERATE_INCOME_YOY", "营收同比"),
    ("HOLDER_PROFIT", "归母净利"),
    ("HOLDER_PROFIT_YOY", "归母净利同比"),
    ("GROSS_PROFIT_RATIO", "毛利率"),
    ("NET_PROFIT_RATIO", "净利率"),
    ("ROE_AVG", "ROE"),
    ("ROA", "ROA"),
    ("DEBT_ASSET_RATIO", "资产负债率"),
    ("CURRENT_RATIO", "流动比率"),
    ("OCF_SALES", "经营现金流/营收"),
]

# 美股主要指标：字段 -> 中文标签
US_INDICATOR_FIELDS: list[tuple[str, str]] = [
    ("OPERATE_INCOME", "营业收入"),
    ("OPERATE_INCOME_YOY", "营收同比"),
    ("NET_INCOME", "归母净利"),
    ("NET_INCOME_YOY", "归母净利同比"),
    ("GROSS_PROFIT_RATIO", "毛利率"),
    ("NET_PROFIT_RATIO", "净利率"),
    ("ROE_AVG", "ROE"),
    ("ROA", "ROA"),
    ("DEBT_ASSET_RATIO", "资产负债率"),
    ("CURRENT_RATIO", "流动比率"),
    ("BASIC_EPS", "EPS"),
    ("BPS", "BPS"),
]

# 百分比类字段（输出时加 %）
_PCT_FIELDS = {
    "OPERATE_INCOME_YOY", "HOLDER_PROFIT_YOY", "NET_INCOME_YOY",
    "GROSS_PROFIT_RATIO", "NET_PROFIT_RATIO", "ROE_AVG", "ROA",
    "DEBT_ASSET_RATIO", "OCF_SALES", "涨跌幅", "YOY_RATIO",
}


def _fmt_value(field: str, value) -> str:
    if pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text}%" if field in _PCT_FIELDS else text


def format_kline(
    df: pd.DataFrame,
    title: str,
    currency: str,
    code_label: str,
    name: str,
    per_code_limit: int = 50,
) -> str:
    """K 线（akshare 中文列）-> `--- 标题 (Total: N) ---` + 每行一根 Bar。"""
    if df is None or df.empty:
        return f"未找到{title}数据"
    display = df.tail(per_code_limit)
    lines = [f"--- {title} (Total: {len(df)}) ---"]
    for _, row in display.iterrows():
        parts = [f"日期:{row['日期']}", f"代码:{code_label}", f"名称:{name}"]
        for field, label in (
            ("开盘", "开盘"), ("最高", "最高"), ("最低", "最低"), ("收盘", "收盘"),
            ("涨跌额", "涨跌额"), ("涨跌幅", "涨跌幅"),
        ):
            if field in row and pd.notna(row[field]):
                parts.append(f"{label}:{_fmt_value(field, row[field])}")
        if "成交量" in row and pd.notna(row["成交量"]):
            vol = row["成交量"]
            vol_text = str(int(vol)) if isinstance(vol, float) and vol.is_integer() else _fmt_value("成交量", vol)
            parts.append(f"成交量:{vol_text}股")
        if "成交额" in row and pd.notna(row["成交额"]):
            parts.append(f"成交额:{row['成交额']:,.2f}{currency}" if isinstance(row["成交额"], float)
                         else f"成交额:{row['成交额']}{currency}")
        lines.append(" | ".join(parts))
    if len(display) < len(df):
        lines.append(f"... (共 {len(df)} 条，仅显示最近 {per_code_limit} 条)")
    return "\n".join(lines)


def format_indicator(
    df: pd.DataFrame,
    fields: list[tuple[str, str]],
    title: str,
    currency: str = "",
    limit: int = 10,
) -> str:
    """财务主要指标宽表 -> 每个报告期一行。"""
    if df is None or df.empty:
        return f"未找到{title}数据"
    df = df.head(limit)
    code = str(df.iloc[0].get("SECURITY_CODE", "")) if "SECURITY_CODE" in df.columns else ""
    secucode = str(df.iloc[0].get("SECUCODE", "")) if "SECUCODE" in df.columns else code
    name = str(df.iloc[0].get("SECURITY_NAME_ABBR", "")) if "SECURITY_NAME_ABBR" in df.columns else ""
    currency = currency or str(df.iloc[0].get("CURRENCY", "")) if "CURRENCY" in df.columns else currency

    lines = [f"--- {title} (共 {len(df)} 期) ---"]
    for _, row in df.iterrows():
        report_date = str(row.get("REPORT_DATE", ""))[:10]
        parts = [f"报告期:{report_date}", f"代码:{secucode}"]
        if name:
            parts.append(f"名称:{name}")
        if currency:
            parts.append(f"货币:{currency}")
        for field, label in fields:
            if field in row:
                parts.append(f"{label}:{_fmt_value(field, row[field])}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_report(
    df: pd.DataFrame,
    item_col: str,
    amount_col: str,
    title: str,
    limit: int = 5,
) -> str:
    """三大报表长表（每行一个科目）-> 每个报告期一行、科目为键值段。"""
    if df is None or df.empty:
        return f"未找到{title}数据"
    date_col = "REPORT_DATE"
    currency = ""
    if "CURRENCY" in df.columns:
        currency = str(df.iloc[0].get("CURRENCY", ""))

    # 最近 limit 个报告期
    dates = list(dict.fromkeys(df[date_col].astype(str).str[:10]))
    dates = sorted(dates, reverse=True)[:limit]

    name = str(df.iloc[0].get("SECURITY_NAME_ABBR", "")) if "SECURITY_NAME_ABBR" in df.columns else ""
    secucode = str(df.iloc[0].get("SECUCODE", "")) if "SECUCODE" in df.columns else ""

    lines = [f"--- {title} (共 {len(df)} 条科目记录) ---"]
    for date in dates:
        period_df = df[df[date_col].astype(str).str[:10] == date]
        parts = [f"报告期:{date}"]
        if secucode:
            parts.append(f"代码:{secucode}")
        if name:
            parts.append(f"名称:{name}")
        if currency:
            parts.append(f"货币:{currency}")
        for _, row in period_df.iterrows():
            item = str(row.get(item_col, "")).strip()
            if not item or pd.isna(row.get(amount_col)):
                continue
            amount = row[amount_col]
            amount_text = f"{amount:,.0f}" if isinstance(amount, float) else str(amount)
            parts.append(f"{item}:{amount_text}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_generic_rows(title: str, rows: list[dict]) -> str:
    """通用 `key:value | key:value` 行输出（搜索结果/公告列表等）。"""
    lines = [f"--- {title} (共 {len(rows)} 条) ---"]
    for row in rows:
        parts = [f"{k}:{v}" for k, v in row.items() if v not in (None, "")]
        if parts:
            lines.append(" | ".join(parts))
    return "\n".join(lines) if len(lines) > 1 else f"未找到{title}数据"
