import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_nav_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_nav(ts_code: str = "", nav_date: str = "", market: str = "", start_date: str = "", end_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取公募基金净值数据。
        
        参数:
            ts_code: TS基金代码 (支持多只基金，逗号分隔)
            nav_date: 净值日期 (YYYYMMDD)
            market: 场内/场外 (E场内 O场外)
            start_date: 净值开始日期 (YYYYMMDD)
            end_date: 净值结束日期 (YYYYMMDD)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_nav called with ts_code='{ts_code}', nav_date='{nav_date}'...")
        pro = get_pro_client()
        
        # Construct API parameters
        api_params = {
            "ts_code": ts_code,
            "nav_date": nav_date,
            "market": market,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "offset": offset
        }
        
        # Filter out empty parameters
        api_params = {k: v for k, v in api_params.items() if v is not None and v != ""}
        
        fields = 'ts_code,ann_date,nav_date,unit_nav,accum_nav,accum_div,net_asset,total_netasset,adj_nav'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_nav(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_nav(**api_params, fields=fields)
        
        if df.empty:
            return "未找到符合条件的基金净值数据"

        # Format output
        result = [f"--- size: {len(df)} ---"]
        
        # Sort logic:
        # P1. If cross-section (single date, multiple funds), sort by adj_nav descending (Performance view).
        # P2. If time-series (single fund, multiple dates), sort by nav_date descending (Latest first).
        
        is_cross_section = False
        if 'nav_date' in df.columns and df['nav_date'].nunique() == 1:
            is_cross_section = True
            
        if is_cross_section and 'adj_nav' in df.columns:
             df = df.sort_values(by='adj_nav', ascending=False)
        elif 'nav_date' in df.columns:
            df = df.sort_values(by='nav_date', ascending=False)

        display_cap = 50
        
        # Smart Truncation Logic for Time Series
        if not limit and len(df) > display_cap and not is_cross_section:
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
    if pd.notna(row.get('nav_date')): info_parts.append(f"日期: {row['nav_date']}")
    if pd.notna(row.get('unit_nav')): info_parts.append(f"单位: {row['unit_nav']}")
    if pd.notna(row.get('accum_nav')): info_parts.append(f"累计: {row['accum_nav']}")
    if pd.notna(row.get('adj_nav')): info_parts.append(f"复权: {row['adj_nav']}")
    if pd.notna(row.get('net_asset')): info_parts.append(f"资产: {row['net_asset']}")
    
    return " | ".join(info_parts)
