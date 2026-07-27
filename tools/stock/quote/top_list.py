import pandas as pd
from datetime import datetime, timedelta
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_top_list_tools(mcp):
    @mcp.tool()
    @handle_exception
    def top_list(trade_date: str = '', ts_code: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        龙虎榜每日明细 (top_list)。

        参数:
            trade_date: 交易日期 (YYYYMMDD, 若不指定且无其他参数则自动取最近交易日)
            ts_code: 股票代码 (e.g., '600519.SH', 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool top_list called with trade_date='{trade_date}', ts_code='{ts_code}', start_date='{start_date}', end_date='{end_date}'")
        pro = get_pro_client()

        # Smart date: if no date args and no ts_code, default to latest trade date
        if not trade_date and not start_date and not end_date and not ts_code:
            try:
                today = datetime.now().strftime('%Y%m%d')
                start_check = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
                df_cal = pro.trade_cal(start_date=start_check, end_date=today, is_open='1')
                if not df_cal.empty:
                    trade_date = df_cal['cal_date'].iloc[-1]
                    log_debug(f"Auto-determined latest trade date: {trade_date}")
            except Exception as e:
                log_debug(f"Failed to auto-determine latest trade date: {e}")

        params = {
            'trade_date': trade_date,
            'ts_code': ts_code,
            'start_date': start_date,
            'end_date': end_date,
        }
        api_params = {k: v for k, v in params.items() if v}

        df = pro.top_list(**api_params)

        if df.empty:
            return "当日无龙虎榜数据"

        results = [f"--- 龙虎榜每日明细 (Total: {len(df)}) ---"]
        df_limited = df.head(50)

        for _, row in df_limited.iterrows():
            info = []
            if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
            if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
            if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
            if pd.notna(row.get('close')): info.append(f"收盘价:{row['close']}")
            if pd.notna(row.get('pct_chg')): info.append(f"涨跌幅:{row['pct_chg']}%")
            if pd.notna(row.get('turnover_rate')): info.append(f"换手率:{row['turnover_rate']}%")
            if pd.notna(row.get('amount')): info.append(f"成交额:{row['amount']}万")
            if pd.notna(row.get('reason')): info.append(f"上榜原因:{row['reason']}")
            results.append(" | ".join(info))

        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")

        return "\n".join(results)
    return top_list
