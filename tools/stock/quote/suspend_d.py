import pandas as pd
from datetime import datetime, timedelta
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_suspend_d_tools(mcp):
    @mcp.tool()
    @handle_exception
    def suspend_d(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', suspend_type: str = '') -> str:
        """
        获取A股每日停复牌信息 (suspend_d)。
        
        参数:
            ts_code: 股票代码 (e.g., '000001.SZ', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选, 若不指定则自动获取最近一个交易日)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
            suspend_type: 停复牌类型：S-停牌, R-复牌 (可选)
        """
        log_debug(f"Tool suspend_d called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}', suspend_type='{suspend_type}'...")
        pro = get_pro_client()
        
        # If no dates are provided, default to the latest trading day
        if not trade_date and not start_date and not end_date:
            try:
                today = datetime.now().strftime('%Y%m%d')
                start_check = (datetime.now() - timedelta(days=20)).strftime('%Y%m%d')
                # Fetch recent trading calendar to find the latest open day
                df_cal = pro.trade_cal(start_date=start_check, end_date=today, is_open='1')
                if not df_cal.empty:
                    latest_trade_date = df_cal['cal_date'].iloc[-1]
                    trade_date = latest_trade_date
                    log_debug(f"No date provided. Automatically determined latest trading date: {trade_date}")
            except Exception as e:
                log_debug(f"Failed to auto-determine latest trade date: {e}")

        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date,
            'suspend_type': suspend_type
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.suspend_d(**api_params)
        
        if df.empty:
            return "未找到停复牌信息"

        results = [f"--- 每日停复牌信息 (Total: {len(df)}) ---"]
        
        # Limit display for large results
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('suspend_type')): info.append(f"类型:{row['suspend_type']}")
             if pd.notna(row.get('suspend_timing')): info.append(f"时间段:{row['suspend_timing']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
