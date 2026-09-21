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


def downsample_weekly_last(
    df: pd.DataFrame, date_col: str, value_cols: list[str], threshold: int = 120
) -> tuple[pd.DataFrame, str]:
    """时间序列周频降采样（图表供给工程解，2026-09-21 Q3 实测缺口）。

    sage 侧 data-cache 把一次调用的全部行解析为同一个数据集——"尾部 50 行
    日线 + 追加降采样块"会混频出时间倒错的图表。因此长区间时**整段**改为
    周频全史：每列取周内最新有效值，日期取周内最大交易日。

    len(df) <= threshold 原样返回 (df, "")；超限按周降采样（约 /5）。周频
    结果超过 250（硬上限，与港美股 K 线一致）才继续降为月频——三年日线
    周频约 157 条，精度优于月频 37 条，不应过度降采样。返回 (df, 频率)。
    """
    if df is None or df.empty or len(df) <= threshold or date_col not in df.columns:
        return df, ""
    dts = pd.to_datetime(df[date_col].astype(str), errors="coerce")
    order = df.assign(__dt=dts).sort_values("__dt")
    out = df
    for freq_key, freq_name in (("W-SUN", "周"), ("M", "月")):
        key = order["__dt"].dt.to_period(freq_key).astype(str)
        grouped = order.groupby(key, sort=True)
        data = {date_col: grouped[date_col].max()}
        for col in value_cols:
            if col in order.columns:
                data[col] = grouped[col].last()
        out = pd.DataFrame(data).reset_index(drop=True)
        if len(out) <= 250:
            return out, freq_name
    return out, "月"
