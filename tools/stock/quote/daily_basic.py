import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from tools.stats_utils import STATS_PREFIX, downsample_weekly_last, extremes_with_dates, fmt_num

# 时间序列长窗口的降采样阈值（行宽大，阈值低于 K 线的 250）
_DAILY_BASIC_THRESHOLD = 120


def render_daily_basic(df: pd.DataFrame, single_ts: str = "") -> str:
    """daily_basic 输出渲染（模块级函数，便于单测）。

    长窗口图表供给工程解（2026-09-21 Q3 实测：3 年 725 行只显示尾部
    50 天，图表"标题近三年、图上近两月"）：单代码时间序列超过阈值时
    整段降采样为周频全史（每列取周内最新值），图表拿到的即全史；
    📊 区间统计行仍对全量日线计算，精度不受降采样影响。
    """
    results = [f"--- 每日基本面指标 (Total: {len(df)}) ---"]
    chart_note = ""
    display_df = df.head(50)

    if (
        single_ts
        and "trade_date" in df.columns
        and len(df) > _DAILY_BASIC_THRESHOLD
    ):
        slim_cols = ["close", "turnover_rate", "pe", "pe_ttm", "pb", "ps_ttm",
                     "dv_ttm", "total_mv", "circ_mv"]
        ds_df, freq = downsample_weekly_last(
            df, "trade_date", slim_cols, threshold=_DAILY_BASIC_THRESHOLD
        )
        if freq:
            display_df = ds_df
            chart_note = (
                f"原始 {len(df)} 条日线超过显示上限，已自动降采样为 {len(ds_df)} 条{freq}频"
                f"（每列取{freq}内最新值，区间走势图表直接用本数据绘制即可，与日线等效；"
                f"📊 区间统计行仍按日线全量计算，精度到日）。如需日线明细，请缩小日期范围重新查询。"
            )

    results[0] = f"--- 每日基本面指标 (Total: {len(display_df)}) ---"
    if chart_note:
        results.append(f"... ⚠️ {chart_note}")

    for _, row in display_df.iterrows():
        info = []
        if pd.notna(row.get("trade_date")): info.append(f"日期:{row['trade_date']}")
        if pd.notna(row.get("ts_code")): info.append(f"代码:{row['ts_code']}")
        if pd.notna(row.get("close")): info.append(f"收盘:{row['close']}")
        if pd.notna(row.get("turnover_rate")): info.append(f"换手率:{row['turnover_rate']}%")
        if pd.notna(row.get("pe")): info.append(f"PE:{row['pe']}")
        if pd.notna(row.get("pe_ttm")): info.append(f"PE(TTM):{row['pe_ttm']}")
        if pd.notna(row.get("pb")): info.append(f"PB:{row['pb']}")
        if pd.notna(row.get("ps")): info.append(f"PS:{row['ps']}")
        if pd.notna(row.get("ps_ttm")): info.append(f"PS(TTM):{row['ps_ttm']}")
        if pd.notna(row.get("dv_ratio")): info.append(f"股息率:{row['dv_ratio']}%")
        if pd.notna(row.get("dv_ttm")): info.append(f"股息率(TTM):{row['dv_ttm']}%")
        if pd.notna(row.get("total_mv")): info.append(f"总市值:{row['total_mv']}万元")
        if pd.notna(row.get("circ_mv")): info.append(f"流通市值:{row['circ_mv']}万元")
        results.append(" | ".join(info))

    if len(display_df) < len(df):
        results.append(f"... (共 {len(df)} 条，仅显示前 {len(display_df)} 条)")

    # 区间统计：PE/PB/市值的极值扫描是代码该干的活（截断场景下未显示
    # 行的极值也能统计到），模型直接引用，不再自行扫 50+ 行找数。
    if not df.empty and "trade_date" in df.columns:
        stat_parts = []
        for col, label in (("pe_ttm", "PE(TTM)"), ("pb", "PB"), ("total_mv", "总市值")):
            ext = extremes_with_dates(df, "trade_date", col)
            if ext:
                stat_parts.append(
                    f"{label} 最高 {fmt_num(ext[0])}（{ext[1]}）/ 最低 {fmt_num(ext[2])}（{ext[3]}）"
                )
        latest = df.loc[df["trade_date"].idxmax()]
        latest_parts = []
        for col, label in (("pe_ttm", "PE(TTM)"), ("pb", "PB"), ("total_mv", "总市值(万元)")):
            if pd.notna(latest.get(col)):
                latest_parts.append(f"{label}={fmt_num(latest[col])}")
        if latest_parts:
            stat_parts.append(f"最新 {latest['trade_date']}：" + "、".join(latest_parts))
        if stat_parts:
            results.append(f"... {STATS_PREFIX}：" + "；".join(stat_parts))

    return "\n".join(results)


def register_daily_basic_tools(mcp):
    @mcp.tool()
    @handle_exception
    def daily_basic(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取A股每日重要的基本面指标 (daily_basic)，如PE、PB、换手率等。

        输出附带📊区间统计行（PE(TTM)/PB/总市值的区间最高/最低及发生日、
        最新值，服务端已对全量数据计算）：直接引用该行，无需自行扫描。

        长区间（单代码超过约 120 个交易日）自动降采样为周频全史输出，
        图表绘制区间走势直接用返回数据即可；如需日线明细，缩小日期范围。

        参数:
            ts_code: 股票代码 (e.g., '000001.SZ', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool daily_basic called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}

        df = pro.daily_basic(**api_params)

        if df.empty:
            return "未找到每日基本面指标数据"

        single_ts = ts_code if (ts_code and ',' not in ts_code) else ""
        return render_daily_basic(df, single_ts)
