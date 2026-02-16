import pandas as pd
from datetime import datetime, timedelta
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_ggt_monthly_tools(mcp):
    @mcp.tool()
    @handle_exception
    def ggt_monthly(month: str = '', start_month: str = '', end_month: str = '') -> str:
        """
        获取港股通每月成交统计 (ggt_monthly)。
        
        参数:
            month: 月度 (YYYYMM, 可选, 若不指定则自动获取最近月度)
            start_month: 开始月度 (YYYYMM, 可选)
            end_month: 结束月度 (YYYYMM, 可选)
        """
        log_debug(f"Tool ggt_monthly called with month='{month}', start_month='{start_month}', end_month='{end_month}'...")
        pro = get_pro_client()
        
        # Smart date logic: if no month args provided, default to latest month
        if not month and not start_month and not end_month:
            try:
                today = datetime.now()
                month = today.strftime('%Y%m')
                log_debug(f"No params provided. Automatically determined month: {month}")
            except Exception as e:
                log_debug(f"Failed to auto-determine month: {e}")

        params = {
            'trade_date': month,
            'start_date': start_month,
            'end_date': end_month
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.ggt_monthly(**api_params)
        
        # If no result found and we used auto-determined month, try previous month
        if df.empty and not start_month and not end_month and month:
             try:
                 dt = datetime.strptime(month, '%Y%m')
                 # Go back to the last day of the previous month
                 prev_month_dt = dt.replace(day=1) - timedelta(days=1)
                 prev_month = prev_month_dt.strftime('%Y%m')
                 
                 if prev_month != month:
                     log_debug(f"Current month {month} empty, trying previous month: {prev_month}")
                     api_params['trade_date'] = prev_month
                     df = pro.ggt_monthly(**api_params)
             except Exception as e:
                 log_debug(f"Failed to retry previous month: {e}")
        
        if df.empty:
            return "未找到港股通每月成交统计数据"

        results = [f"--- 港股通每月成交统计 (Total: {len(df)}) ---"]
        
        # Limit display if needed
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('month')): info.append(f"月度:{row['month']}")
             if pd.notna(row.get('day_buy_amt')): info.append(f"日均买入(亿):{row['day_buy_amt']}")
             if pd.notna(row.get('day_sell_amt')): info.append(f"日均卖出(亿):{row['day_sell_amt']}")
             if pd.notna(row.get('total_buy_amt')): info.append(f"总买入(亿):{row['total_buy_amt']}")
             if pd.notna(row.get('total_sell_amt')): info.append(f"总卖出(亿):{row['total_sell_amt']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
