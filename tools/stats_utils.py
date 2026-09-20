"""服务端区间统计工具。

极值/合计等"扫描大量数值行"的活由代码完成（2026-09-20 事故：模型扫
157 行周线漏看极值行，把区间最高答错），输出一行可直接引用的统计文本，
模型不再自行扫描或分段补查。

输出约定：
- 行首以 "..." 开头：sage-web 侧 data-cache.ts 解析器会跳过省略行，
  统计行不会混入图表数据。
- 使用全角冒号"："，避免被解析器误认为 key:value 数据行。
"""

from __future__ import annotations

import pandas as pd

STATS_PREFIX = "📊 区间统计（服务端已计算，直接引用即可，无需自行扫描或补查）"


def fmt_num(v) -> str:
    """紧凑数值：12.3400 -> 12.34，419.0 -> 419。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:.4f}".rstrip("0").rstrip(".")


def extremes_with_dates(df: pd.DataFrame, date_col: str, value_col: str):
    """返回 (最大值, 最大值日期, 最小值, 最小值日期)；无有效值返回 None。"""
    if df is None or df.empty or value_col not in df.columns or date_col not in df.columns:
        return None
    sub = df[[date_col, value_col]].dropna(subset=[value_col])
    if sub.empty:
        return None
    hi_row = sub.loc[sub[value_col].idxmax()]
    lo_row = sub.loc[sub[value_col].idxmin()]
    return hi_row[value_col], hi_row[date_col], lo_row[value_col], lo_row[date_col]
