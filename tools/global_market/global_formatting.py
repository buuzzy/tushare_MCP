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


def _aggregate_kline(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """日线 -> 周线/月线（freq: 'W'=周 / 'M'=月）。

    每根周/月线：open=期内首日开盘、high/low=期内日内最高/最低、
    close=期末日收盘、vol/amount 期内求和、pct_chg 由相邻期收盘价重算
    （首期无前期收盘则留空）。另附最高日/最低日——极值发生的具体交易日，
    模型求区间极值时价格与日期可一次性引用，无需再拉日线明细核对。
    求区间最高/最低/涨跌幅与日线完全等效，因此超长窗口降级周/月线后
    模型一次查询即可正确作答，无需分段补查。
    """
    dt = pd.to_datetime(df["日期"])
    key = dt.dt.strftime("%G-%V") if freq == "W" else dt.dt.strftime("%Y-%m")
    rows = []
    for _, g in df.groupby(key, sort=False):
        row = {"日期": g["日期"].iloc[-1]}
        if "开盘" in g:
            row["开盘"] = g["开盘"].iloc[0]
        if "最高" in g:
            row["最高"] = g["最高"].max()
            row["最高日"] = str(g.loc[g["最高"].idxmax(), "日期"])
        if "最低" in g:
            row["最低"] = g["最低"].min()
            row["最低日"] = str(g.loc[g["最低"].idxmin(), "日期"])
        if "收盘" in g:
            row["收盘"] = g["收盘"].iloc[-1]
        if "成交量" in g:
            row["成交量"] = g["成交量"].sum()
        if "成交额" in g:
            row["成交额"] = g["成交额"].sum()
        rows.append(row)
    agg = pd.DataFrame(rows)
    if "收盘" in agg and len(agg) > 0:
        prev = agg["收盘"].shift(1)
        agg["涨跌幅"] = ((agg["收盘"] / prev) - 1) * 100
    return agg


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

    超长窗口策略：日线超过 per_code_limit 时自动聚合为周线（仍超则月线），
    置顶声明等效性——2026-09-20 实测：截断+提示"分段查询"后模型仍会漏查
    省略段、凭记忆填极值；周线的 high/low 即当周日内极值，等效后一次查询
    即可正确作答，从源头消灭分段/补查/编造。聚合行额外携带 high_date/
    low_date（极值发生的具体交易日），图文引用口径天然一致，无需二段补查。
    """
    if df is None or df.empty:
        return f"未找到{title}数据"
    total = len(df)

    agg_df, agg_note, fallback_truncate = df, "", False
    if total > per_code_limit:
        weekly = _aggregate_kline(df, "W")
        if len(weekly) <= per_code_limit:
            agg_df = weekly
            title = title.replace("日线", "周线")
            agg_note = (
                f"原始 {total} 根日线超过 250 上限，已自动聚合为 {len(weekly)} 根周线"
                f"（每周 high/low 为当周日内最高/最低，high_date/low_date 为其发生的"
                f"具体交易日；求区间最高/最低/涨跌幅与日线完全等效，极值价格与日期"
                f"直接引用本结果即可，无需分段或补查日线）；如需某段日线明细，"
                f"请缩小日期范围重新查询。"
            )
        else:
            monthly = _aggregate_kline(df, "M")
            if len(monthly) <= per_code_limit:
                agg_df = monthly
                title = title.replace("日线", "月线")
                agg_note = (
                    f"原始 {total} 根日线超过上限，已自动聚合为 {len(monthly)} 根月线"
                    f"（每月 high/low 为当月日内最高/最低，high_date/low_date 为其发生的"
                    f"具体交易日；求区间最高/最低/涨跌幅与日线等效，极值价格与日期"
                    f"直接引用本结果即可）。"
                )
            else:
                # 极端长历史（26 年+月线仍超限）：退回首尾截断
                agg_df, fallback_truncate = monthly, True

    # 列声明随输出内容自适应：聚合输出附带极值发生日
    if "最高日" in agg_df.columns:
        cols = "date,open,high,high_date,low,low_date,close,pct_chg,vol(股),amount"
    else:
        cols = "date,open,high,low,close,pct_chg,vol(股),amount"
    lines = [
        f"--- {title} | {code_label} {name} | 单位:{currency} | "
        f"列: {cols} (Total: {len(agg_df)}) ---"
    ]

    def _bar_line(row) -> str:
        parts = [f"date:{row['日期']}"]
        for src, key in (("开盘", "open"), ("最高", "high"), ("最低", "low"), ("收盘", "close")):
            if src in row and pd.notna(row[src]):
                parts.append(f"{key}:{_fmt_value(key, row[src])}")
        if "最高日" in row and pd.notna(row["最高日"]):
            parts.append(f"high_date:{row['最高日']}")
        if "最低日" in row and pd.notna(row["最低日"]):
            parts.append(f"low_date:{row['最低日']}")
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

    if agg_note:
        # 置顶提示：紧跟标题行，Agent 首先看到的就是它
        lines.append(f"... ⚠️ {agg_note}")

    if fallback_truncate:
        head_n = min(_TRUNCATE_HEAD_N, per_code_limit)
        tail_n = per_code_limit - head_n
        lines.append(
            f"... ⚠️ 共 {total} 条，仅显示最早 {head_n} 条 + 最新 {tail_n} 条月线，"
            f"完整区间 {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}，中间有省略。"
        )
        for _, row in agg_df.head(head_n).iterrows():
            lines.append(_bar_line(row))
        lines.append("... （中间省略）...")
        for _, row in agg_df.tail(tail_n).iterrows():
            lines.append(_bar_line(row))
    else:
        for _, row in agg_df.iterrows():
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
