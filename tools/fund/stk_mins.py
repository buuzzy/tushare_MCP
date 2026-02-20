import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stk_mins_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stk_mins(ts_code: str, freq: str = "1min", start_date: str = "", end_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取ETF分钟数据，支持1min/5min/15min/30min/60min行情。
        
        参数:
            ts_code: ETF代码，e.g. 159001.SZ (必填)
            freq: 分钟频度（1min/5min/15min/30min/60min），默认1min
            start_date: 开始日期 格式：2025-06-01 09:00:00
            end_date: 结束时间 格式：2025-06-20 19:00:00
            limit: 单次返回数据长度（最大8000行）
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool stk_mins called with ts_code='{ts_code}', freq='{freq}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'freq': freq,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        api_params = {k: v for k, v in params.items() if v}
        
        fields = 'ts_code,trade_time,open,close,high,low,vol,amount'
        
        df = pro.stk_mins(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的分钟行情数据"

        # Sort by trade_time descending if available, though API usually does this
        if 'trade_time' in df.columns:
            df = df.sort_values('trade_time', ascending=False)

        result = [f"--- size: {len(df)} ---"]
        display_cap = 50
        display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('trade_time')): info_parts.append(f"时间: {row['trade_time']}")
            if pd.notna(row.get('close')): info_parts.append(f"收: {row['close']}")
            if pd.notna(row.get('open')): info_parts.append(f"开: {row['open']}")
            if pd.notna(row.get('high')): info_parts.append(f"高: {row['high']}")
            if pd.notna(row.get('low')): info_parts.append(f"低: {row['low']}")
            if pd.notna(row.get('vol')): info_parts.append(f"量: {row['vol']}")
            if pd.notna(row.get('amount')): info_parts.append(f"额: {row['amount']}")
            
            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
