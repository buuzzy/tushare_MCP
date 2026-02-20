import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_share_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_share(ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "", market: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取基金规模数据，包含上海和深圳ETF基金。
        支持时间序列数据的智能截断展示（显示头部和尾部数据）。
        
        参数:
            ts_code: 基金代码，支持多只基金同时提取，用逗号分隔
            trade_date: 交易（变动）日期，格式YYYYMMDD
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            market: 市场代码（SH上交所 ，SZ深交所）
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_share called with ts_code='{ts_code}', trade_date='{trade_date}', market='{market}'...")
        pro = get_pro_client()
        
        # Construct API parameters
        api_params = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "market": market,
            "limit": limit,
            "offset": offset
        }
        
        # Filter out empty parameters
        api_params = {k: v for k, v in api_params.items() if v is not None and v != ""}
        
        fields = 'ts_code,trade_date,fd_share'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_share(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_share(**api_params, fields=fields)
        
        if df.empty:
            return "未找到符合条件的基金规模数据"

        # Format output
        result = [f"--- size: {len(df)} ---"]
        
        # Sort logic: 
        # 1. If looking at a specific date (cross-section), sort by Share Size descending (to show largest funds).
        # 2. If looking at time-series (default), sort by Date descending (newest first).
        
        is_cross_section = False
        if 'trade_date' in df.columns and df['trade_date'].nunique() == 1:
            is_cross_section = True
            
        if is_cross_section and 'fd_share' in df.columns:
            df = df.sort_values(by='fd_share', ascending=False)
        elif 'trade_date' in df.columns:
            df = df.sort_values(by='trade_date', ascending=False)

        display_cap = 50
        
        # Smart Truncation Logic:
        # If no strict limit is set, and data exceeds cap, show Head + Tail
        if not limit and len(df) > display_cap:
            head_df = df.head(45)
            tail_df = df.tail(5)
            
            for _, row in head_df.iterrows():
                result.append(format_row(row))
            
            result.append(f"... (中间省略 {len(df) - 50} 条数据) ...")
            
            for _, row in tail_df.iterrows():
                result.append(format_row(row))
        else:
            # Standard logic: strictly follow limit or cap
            if limit:
                display_df = df.head(limit)
            else:
                display_df = df.head(display_cap)
                
            for _, row in display_df.iterrows():
                result.append(format_row(row))
                
            if limit and len(df) > limit:
                 result.append(f"... (共 {len(df)} 条，仅显示前 {limit} 条)")
            elif not limit and len(df) > display_cap:
                 result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)

def format_row(row) -> str:
    info_parts = []
    if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
    if pd.notna(row.get('trade_date')): info_parts.append(f"日期: {row['trade_date']}")
    
    # Format float with commas
    share = row.get('fd_share')
    if pd.notna(share):
        share_str = f"{share:,.2f}"
        info_parts.append(f"份额(万): {share_str}")
        
    return " | ".join(info_parts)
