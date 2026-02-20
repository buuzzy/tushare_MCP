import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_factor_pro_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_factor_pro(ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取场内基金每日技术面因子数据(专业版)。
        
        参数:
            ts_code: 基金代码
            trade_date: 交易日期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_factor_pro called with ts_code='{ts_code}', trade_date='{trade_date}'...")
        pro = get_pro_client()
        
        # Construct API parameters
        api_params = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "offset": offset
        }
        
        # Filter out empty parameters
        api_params = {k: v for k, v in api_params.items() if v is not None and v != ""}
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_factor_pro(**api_params)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_factor_pro(**api_params)
        
        if df.empty:
            return "未找到符合条件的基金因子数据"

        # Format output
        result = [f"--- size: {len(df)} ---"]
        
        # Sort logic:
        # Time-series data, sort by Date descending (newest first).
        if 'trade_date' in df.columns:
            df = df.sort_values(by='trade_date', ascending=False)
            
        display_cap = 50
        
        # Smart Truncation Logic
        if not limit and len(df) > display_cap:
            head_df = df.head(45)
            tail_df = df.tail(5)
            
            for _, row in head_df.iterrows():
                result.append(format_row(row))
            
            result.append(f"... (中间省略 {len(df) - 50} 条数据) ...")
            
            for _, row in tail_df.iterrows():
                result.append(format_row(row))
        else:
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
    
    # Core price info if available
    if pd.notna(row.get('close')): info_parts.append(f"收盘: {row['close']}")
    if pd.notna(row.get('pct_change')): info_parts.append(f"涨跌幅: {row['pct_change']}%")
    
    # Specific Factors - add a few key ones or just dump relevant ones that are not null
    # To avoid extremely long lines, we'll pick popular ones if they exist, or let the user fetch specific fields
    factors = ['macd_bfq', 'rsi_bfq_12', 'kdj_k_bfq', 'kdj_d_bfq', 'boll_mid_bfq', 'cci_bfq']
    for f in factors:
        if f in row and pd.notna(row[f]):
            info_parts.append(f"{f}: {row[f]:.4f}")
            
    # Include any dynamically requested factors that might not be in the predefined list above
    # We will limit the total length of the row string to avoid token explosion
    return " | ".join(info_parts)
