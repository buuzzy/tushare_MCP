import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .trade_date_utils import resolve_trade_date

def register_suspend_d_tools(mcp):
    @mcp.tool()
    @handle_exception
    def suspend_d(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', suspend_type: str = '') -> str:
        """
        获取A股每日停复牌信息 (suspend_d)。
        
        参数:
            ts_code: 股票代码 (e.g., '000001.SZ', 可选)
            trade_date: 单个交易日期 (YYYYMMDD, 可选)
            start_date: 区间开始日期 (YYYYMMDD)。仅与 end_date 同时传入时按区间查询
            end_date: 区间结束日期 (YYYYMMDD)。单独传入时归一化为当日或之前最近交易日
            suspend_type: 停复牌类型：S-停牌, R-复牌 (可选)
        """
        log_debug(f"Tool suspend_d called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}', suspend_type='{suspend_type}'...")
        pro = get_pro_client()
        
        # Keep true range semantics only when both boundaries are explicit.
        # A lone end_date is normalized to one trading day for agent requests
        # that mean "latest as of this date".
        if not trade_date and not (start_date and end_date):
            resolved_date = resolve_trade_date(pro, start_date, end_date)
            if resolved_date:
                trade_date = resolved_date
                start_date = ""
                end_date = ""
                log_debug(f"Normalized suspend_d query to trading date: {trade_date}")

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
