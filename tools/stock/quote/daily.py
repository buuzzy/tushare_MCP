import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_daily_tools(mcp):
    @mcp.tool()
    @handle_exception
    def daily(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取A股日线行情数据 (daily)。
        
        参数:
            ts_code: 股票代码 (e.g., '000001.SZ', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool daily called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.daily(**api_params)
        
        if df.empty:
            return "未找到日线行情数据"

        results = [f"--- 日线行情数据 (Total: {len(df)}) ---"]
        
        # Limit display for large results if no specific date or code is provided, but usually user asks specific questions.
        # If result is large, limit to 50.
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('open')): info.append(f"开盘:{row['open']}")
             if pd.notna(row.get('high')): info.append(f"最高:{row['high']}")
             if pd.notna(row.get('low')): info.append(f"最低:{row['low']}")
             if pd.notna(row.get('close')): info.append(f"收盘:{row['close']}")
             if pd.notna(row.get('pre_close')): info.append(f"昨收:{row['pre_close']}")
             if pd.notna(row.get('change')): info.append(f"涨跌额:{row['change']}")
             if pd.notna(row.get('pct_chg')): info.append(f"涨跌幅:{row['pct_chg']}%")
             if pd.notna(row.get('vol')): info.append(f"成交量:{row['vol']}手")
             if pd.notna(row.get('amount')): info.append(f"成交额:{row['amount']}千元")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
