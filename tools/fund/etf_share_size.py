import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_etf_share_size_tools(mcp):
    @mcp.tool()
    @handle_exception
    def etf_share_size(ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "", exchange: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取ETF每日份额和规模数据。
        
        参数:
            ts_code: 基金代码 (e.g. 510330.SH)
            trade_date: 交易日期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            exchange: 交易所 (SSE上交所 SZSE深交所)
            limit: 单次返回数据长度（最大5000行）
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool etf_share_size called with ts_code='{ts_code}', trade_date='{trade_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date,
            'exchange': exchange,
            'limit': limit,
            'offset': offset
        }
        api_params = {k: v for k, v in params.items() if v}
        
        fields = 'trade_date,ts_code,etf_name,total_share,total_size,nav,close,exchange'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.etf_share_size(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.etf_share_size(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的ETF份额规模数据"

        # Sort logic: 
        # 1. If looking at a specific date (cross-section), sort by Total Size descending (to show largest ETFs).
        # 2. If looking at time-series (default), sort by Date descending (newest first).
        
        is_cross_section = False
        if 'trade_date' in df.columns:
             # Check if all rows have the same trade_date
             if df['trade_date'].nunique() == 1:
                 is_cross_section = True

        if is_cross_section and 'total_size' in df.columns:
            df = df.sort_values(by='total_size', ascending=False)
        elif 'trade_date' in df.columns:
            df = df.sort_values(by='trade_date', ascending=False)

        result = [f"--- size: {len(df)} ---"]
        # Truncation logic: Show Head + Tail if too long
        display_cap = 50
        if len(df) > display_cap:
            # Show top 45 and bottom 5 to allow seeing the start/end of the period
            head_df = df.head(45)
            tail_df = df.tail(5)
            
            # Process Head
            for _, row in head_df.iterrows():
                result.append(format_row(row))
            
            result.append(f"... (中间省略 {len(df) - 50} 条) ...")
            
            # Process Tail
            for _, row in tail_df.iterrows():
                result.append(format_row(row))
        else:
            for _, row in df.iterrows():
                result.append(format_row(row))
             
        return "\n".join(result)

def format_row(row) -> str:
    info_parts = []
    if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
    if pd.notna(row.get('trade_date')): info_parts.append(f"日期: {row['trade_date']}")
    if pd.notna(row.get('etf_name')): info_parts.append(f"名称: {row['etf_name']}")
    
    # Formatting numbers for readability
    if pd.notna(row.get('total_share')): 
        share = row['total_share']
        info_parts.append(f"份额: {share:,.2f}万份")
    if pd.notna(row.get('total_size')): 
        size = row['total_size']
        info_parts.append(f"规模: {size:,.2f}万元")
    
    if pd.notna(row.get('nav')): info_parts.append(f"净值: {row['nav']}")
    if pd.notna(row.get('close')): info_parts.append(f"收盘: {row['close']}")
    
    return " | ".join(info_parts)
