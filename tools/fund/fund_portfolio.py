import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_portfolio_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_portfolio(ts_code: str = "", symbol: str = "", ann_date: str = "", start_date: str = "", end_date: str = "", period: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取公募基金持仓数据，季度更新。
        
        参数:
            ts_code: 基金代码 (ts_code,ann_date,period至少输入一个参数)
            symbol: 股票代码
            ann_date: 公告日期 (YYYYMMDD)
            start_date: 报告期开始日期 (YYYYMMDD)
            end_date: 报告期结束日期 (YYYYMMDD)
            period: 权益登记日(季度截止日, e.g. 20230630)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_portfolio called with ts_code='{ts_code}', symbol='{symbol}', period='{period}'...")
        pro = get_pro_client()
        
        # Construct API parameters
        api_params = {
            "ts_code": ts_code,
            "symbol": symbol,
            "ann_date": ann_date,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "limit": limit,
            "offset": offset
        }
        
        # Filter out empty parameters
        api_params = {k: v for k, v in api_params.items() if v is not None and v != ""}
        
        fields = 'ts_code,ann_date,end_date,symbol,mkv,amount,stk_mkv_ratio,stk_float_ratio'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_portfolio(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_portfolio(**api_params, fields=fields)
        
        if df.empty:
            return "未找到符合条件的基金持仓数据"

        # Format output
        result = [f"--- size: {len(df)} ---"]
        
        # Sort logic:
        # 1. If looking at a single fund's portfolio for a specific date (cross-section of stocks), sort by Market Value (mkv) descending to show top holdings.
        # 2. Otherwise, sort by Announcement Date descending (newest first).
        
        is_single_fund_snapshot = False
        if 'ts_code' in df.columns and df['ts_code'].nunique() == 1:
             is_single_fund_snapshot = True
        
        # Sort by Market Value (mkv) if looking at a single fund's portfolio OR a specific stock's holders
        if (is_single_fund_snapshot or symbol) and 'mkv' in df.columns:
            df = df.sort_values(by='mkv', ascending=False)
        elif 'ann_date' in df.columns:
            df = df.sort_values(by='ann_date', ascending=False)
            
        display_cap = 50
        
        # Smart Truncation Logic
        if not limit and len(df) > display_cap:
            head_df = df.head(display_cap)
            for _, row in head_df.iterrows():
                result.append(format_row(row))
            result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条，建议通过 limit 参数获取更多) ...")
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
    if pd.notna(row.get('ts_code')): info_parts.append(f"基金: {row['ts_code']}")
    if pd.notna(row.get('end_date')): info_parts.append(f"截止: {row['end_date']}")
    if pd.notna(row.get('symbol')): info_parts.append(f"股票: {row['symbol']}")
    
    if pd.notna(row.get('mkv')): 
        mkv = row['mkv']
        info_parts.append(f"市值: {mkv:,.2f}元")
        
    if pd.notna(row.get('amount')): 
        amt = row['amount']
        info_parts.append(f"数量: {amt:,.0f}股")
        
    if pd.notna(row.get('stk_mkv_ratio')): info_parts.append(f"占比: {row['stk_mkv_ratio']}%")
    
    return " | ".join(info_parts)
