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

# 美股主要指标：字段 -> 中文标签（RPT_USF10_FN_GMAININDICATOR 实测列名）
US_INDICATOR_FIELDS: list[tuple[str, str]] = [
    ("OPERATE_INCOME", "营业收入"),
    ("OPERATE_INCOME_YOY", "营收同比"),
    ("PARENT_HOLDER_NETPROFIT", "归母净利"),
    ("PARENT_HOLDER_NETPROFIT_YOY", "归母净利同比"),
    ("GROSS_PROFIT_RATIO", "毛利率"),
    ("NET_PROFIT_RATIO", "净利率"),
    ("ROE_AVG", "ROE"),
    ("ROA", "ROA"),
    ("DEBT_ASSET_RATIO", "资产负债率"),
    ("CURRENT_RATIO", "流动比率"),
    ("SPEED_RATIO", "速动比率"),
    ("BASIC_EPS", "EPS"),
    ("DILUTED_EPS", "稀释EPS"),
]

# 百分比类字段（输出时加 %）
_PCT_FIELDS = {
    "OPERATE_INCOME_YOY", "HOLDER_PROFIT_YOY", "NET_INCOME_YOY",
    "PARENT_HOLDER_NETPROFIT_YOY", "GROSS_PROFIT_YOY",
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


# 截断时头部保留的行数（其余配额给尾部：最近数据通常更重要）
_TRUNCATE_HEAD_N = 50


def format_kline(
    df: pd.DataFrame,
    title: str,
    currency: str,
    code_label: str,
    name: str,
    per_code_limit: int = 250,
) -> str:
    """K 线（akshare 中文列）-> `--- 标题 (Total: N) ---` + 每行一根 Bar。

    紧凑行格式（sage data-cache/图表模板均兼容英文别名列）：
        date:YYYY-MM-DD|open:..|high:..|low:..|close:..|pct_chg:..|vol:..|amount:..
    代码/名称/货币只在标题行声明一次，行内不重复。

    截断策略：保留最早 _TRUNCATE_HEAD_N 条 + 最新（per_code_limit - head）条，
    并在标题行下方紧贴一条置顶省略提示（Agent 对开头的注意力远高于末尾脚注，
    2026-09-20 实测：末尾脚注被无视，模型把尾部 50 根当全区间求最高/最低）。
    """
    if df is None or df.empty:
        return f"未找到{title}数据"
    total = len(df)
    lines = [
        f"--- {title} | {code_label} {name} | 单位:{currency} | "
        f"列: date,open,high,low,close,pct_chg,vol(股),amount (Total: {total}) ---"
    ]

    def _bar_line(row) -> str:
        parts = [f"date:{row['日期']}"]
        for src, key in (("开盘", "open"), ("最高", "high"), ("最低", "low"), ("收盘", "close")):
            if src in row and pd.notna(row[src]):
                parts.append(f"{key}:{_fmt_value(key, row[src])}")
        if "涨跌幅" in row and pd.notna(row["涨跌幅"]):
            # pct_chg：数值不带 %（parseNum 会剥掉单位，省字符）
            parts.append(f"pct_chg:{_fmt_value('pct_chg', row['涨跌幅'])}")
        if "成交量" in row and pd.notna(row["成交量"]):
            vol = row["成交量"]
            vol_text = str(int(vol)) if isinstance(vol, float) and vol.is_integer() else _fmt_value("vol", vol)
            parts.append(f"vol:{vol_text}")
        if "成交额" in row and pd.notna(row["成交额"]):
            amt = row["成交额"]
            amt_text = str(int(amt)) if isinstance(amt, float) and amt.is_integer() else f"{amt:.2f}"
            parts.append(f"amount:{amt_text}")
        return "|".join(parts)

    if total <= per_code_limit:
        for _, row in df.iterrows():
            lines.append(_bar_line(row))
    else:
        head_n = min(_TRUNCATE_HEAD_N, per_code_limit)
        tail_n = per_code_limit - head_n
        full_start, full_end = df["日期"].iloc[0], df["日期"].iloc[-1]
        # 置顶提示：紧跟标题行，Agent 首先看到的就是它
        lines.append(
            f"... ⚠️ 共 {total} 条，仅显示最早 {head_n} 条 + 最新 {tail_n} 条，"
            f"完整区间 {full_start} ~ {full_end}，中间有省略；"
            f"求区间最高/最低/涨跌幅请缩小日期范围分段查询，或改用 weekly/monthly。"
        )
        for _, row in df.head(head_n).iterrows():
            lines.append(_bar_line(row))
        lines.append("... （中间省略）...")
        for _, row in df.tail(tail_n).iterrows():
            lines.append(_bar_line(row))
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
