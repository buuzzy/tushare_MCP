import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .trade_date_utils import resolve_trade_date

def register_ggt_daily_tools(mcp):
    @mcp.tool()
    @handle_exception
    def ggt_daily(trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取港股通每日成交统计 (ggt_daily)。
        
        参数:
            trade_date: 单个交易日期 (YYYYMMDD, 可选)
            start_date: 区间开始日期 (YYYYMMDD)。仅与 end_date 同时传入时按区间查询
            end_date: 区间结束日期 (YYYYMMDD)。单独传入时归一化为当日或之前最近交易日
        """
        log_debug(f"Tool ggt_daily called with trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        
        # Keep true range semantics only when both boundaries are explicit.
        if not trade_date and not (start_date and end_date):
            resolved_date = resolve_trade_date(pro, start_date, end_date)
            if resolved_date:
                trade_date = resolved_date
                start_date = ""
                end_date = ""
                log_debug(f"Normalized ggt_daily query to trading date: {trade_date}")

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
