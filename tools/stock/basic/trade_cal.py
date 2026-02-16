import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_trade_calendar_tools(mcp):
    @mcp.tool()
    @handle_exception
    def trade_cal(exchange: str = '', start_date: str = '', end_date: str = '', is_open: str = '') -> str:
        """
        获取各大交易所交易日历数据。(对应 tushare trade_cal 接口)
        
        参数:
            exchange: 交易所 SSE上交所 SZSE深交所 CFFEX中金所 SHFE上期所 CZCE郑商所 DCE大商所 INE上能源
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            is_open: 是否交易 '0'休市 '1'交易
        """
        log_debug(f"Tool trade_cal called with exchange='{exchange}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        
        # Mapping for exchanges not directly supported by trade_cal but sharing A-share calendar
        # BSE (Beijing) shares calendar with SSE/SZSE
        query_exchange = exchange
        if exchange and exchange.upper() in ['BSE', 'BJ']:
            query_exchange = 'SSE'  # Use SSE as proxy for A-share calendar

        params = {
            'exchange': query_exchange,
            'start_date': start_date,
            'end_date': end_date,
            'is_open': is_open
        }
        # Filter empty
        params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'exchange,cal_date,is_open,pretrade_date'

        df = pro.trade_cal(**params, fields=fields)
        
        if df.empty:
            return "未找到交易日历数据"
            
        # Format output
        results = [f"--- 交易日历 (exchange: {exchange or 'Default'}, {len(df)} days) ---"]
        
        # Limit display for standard output
        # If the user asks for a year, it's 365 rows. We should probably limit or paginate?
        # Let's show head 50 and tail if needed, or just head 50.
        df_limited = df.head(50)
        
        # exchange  cal_date  is_open
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('cal_date')): info.append(f"{row['cal_date']}")
             if pd.notna(row.get('is_open')): 
                 status = "交易" if str(row['is_open']) == '1' else "休市"
                 info.append(f"[{status}]")
             if pd.notna(row.get('pretrade_date')): info.append(f"(前:{row['pretrade_date']})")
             
             results.append("".join(info))
            
        # Group dates for compact display? 
        # The user example shows a list. Let's keep it line by line for clarity if it includes pretrade_date.
        # But if it's just a lot of dates, maybe compact is better.
        # Given "pretrade_date" is requested, line by line or 2-3 per line is better.
        # Let's try to group 3 per line to save space
        
        formatted_lines = []
        current_line = []
        for item in results[1:]: # Skip header
            current_line.append(item)
            if len(current_line) >= 4:
                formatted_lines.append(" | ".join(current_line))
                current_line = []
        
        if current_line:
            formatted_lines.append(" | ".join(current_line))
            
        final_output = [results[0]] + formatted_lines
            
        if len(df) > 50:
            final_output.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(final_output)
