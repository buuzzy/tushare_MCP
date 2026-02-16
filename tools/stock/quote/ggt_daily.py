import pandas as pd
from datetime import datetime, timedelta
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_ggt_daily_tools(mcp):
    @mcp.tool()
    @handle_exception
    def ggt_daily(trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取港股通每日成交统计 (ggt_daily)。
        
        参数:
            trade_date: 交易日期 (YYYYMMDD, 可选, 若不指定则自动获取最近交易日)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool ggt_daily called with trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        
        # Smart date logic: if no date args provided, default to latest trade date
        if not trade_date and not start_date and not end_date:
            try:
                today = datetime.now().strftime('%Y%m%d')
                start_check = (datetime.now() - timedelta(days=20)).strftime('%Y%m%d')
                df_cal = pro.trade_cal(start_date=start_check, end_date=today, is_open='1')
                if not df_cal.empty:
                    trade_date = df_cal['cal_date'].iloc[-1]
                    log_debug(f"No params provided. Automatically determined latest trading date: {trade_date}")
            except Exception as e:
                log_debug(f"Failed to auto-determine latest trade date: {e}")

        params = {
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.ggt_daily(**api_params)
        
        if df.empty:
            return "未找到港股通每日成交统计数据"

        results = [f"--- 港股通每日成交统计 (Total: {len(df)}) ---"]
        
        # Limit display if needed
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('buy_amount')): info.append(f"买入额(亿):{row['buy_amount']}")
             if pd.notna(row.get('buy_volume')): info.append(f"买入笔数(万):{row['buy_volume']}")
             if pd.notna(row.get('sell_amount')): info.append(f"卖出额(亿):{row['sell_amount']}")
             if pd.notna(row.get('sell_volume')): info.append(f"卖出笔数(万):{row['sell_volume']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
