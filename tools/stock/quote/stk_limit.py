import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stk_limit_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stk_limit(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取A股每日涨跌停价格 (stk_limit)。
        
        参数:
            ts_code: 股票代码 (e.g., '000001.SZ', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool stk_limit called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.stk_limit(**api_params)
        
        if df.empty:
            return "未找到涨跌停价格数据"

        results = [f"--- 每日涨跌停价格 (Total: {len(df)}) ---"]
        
        # Limit display for large results
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('pre_close')): info.append(f"昨收:{row['pre_close']}")
             if pd.notna(row.get('up_limit')): info.append(f"涨停:{row['up_limit']}")
             if pd.notna(row.get('down_limit')): info.append(f"跌停:{row['down_limit']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
