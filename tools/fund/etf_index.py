import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_etf_index_tools(mcp):
    @mcp.tool()
    @handle_exception
    def etf_index(ts_code: str = "", name: str = "", pub_date: str = "", base_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取ETF基准指数列表信息。
        
        参数:
            ts_code: 指数代码
            name: 指数名称 (本地筛选，支持模糊匹配)
            pub_date: 发布日期（格式：YYYYMMDD）
            base_date: 指数基期（格式：YYYYMMDD）
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool etf_index called with ts_code='{ts_code}', name='{name}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'pub_date': pub_date,
            'base_date': base_date,
            'limit': limit,
            'offset': offset
        }
        api_params = {k: v for k, v in params.items() if v}
        
        fields = 'ts_code,indx_name,indx_csname,pub_party_name,pub_date,base_date,bp,adj_circle'
        
        # Tushare API returns old data first by default.
        # To support "recent" queries without explicit date, we should sort by pub_date descending locally.
        # But fetching ALL data (thousands of rows) might be slow. 
        # API doesn't support sort.
        # Strategy: If no specific date is given, we try to fetch distinct recent data or just sort what we get.
        # Actually, for "recent", we ideally want the API to sort, but it can't.
        # So we must fetch a reasonable amount (e.g. 5000 is the max limit per call) and sort locally.
        
        # If limit is small (e.g. 5), we still need to fetch MORE to find the *true* recent ones among the dataset,
        # unless we know the API order. Tushare usually returns chronological.
        # So the latest are at the END.
        
        # We override limit for the API call to get a good chunk of data to sort, 
        # UNLESS the user specified a date (then likely the result is small).
        
        api_limit = limit
        if not pub_date and not base_date and not ts_code:
             # If querying generally, we likely want recent data.
             # Fetching 2000 items is fast enough.
             api_limit = 2000 
             if limit and limit > 2000: api_limit = limit

        # Update api_params with our internal limit
        if api_limit: api_params['limit'] = api_limit
        
        df = pro.etf_index(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的ETF基准指数信息"

        # --- Local Enhancement: Filter by Name ---
        if name:
            df = df[df['indx_name'].str.contains(name, na=False) | df['indx_csname'].str.contains(name, na=False)]
            if df.empty:
                return f"未找到名称包含 '{name}' 的指数"
        # -----------------------------------------

        # --- Local Enhancement: Default Sort by pub_date DESC ---
        # Ensure we show the most recent ones first, as that's what users usually want when browsing.
        if 'pub_date' in df.columns:
             df = df.sort_values(by='pub_date', ascending=False)
        # --------------------------------------------------------

        result = [f"--- size: {len(df)} ---"]
        
        # Now apply the user's requested limit for *display*
        actual_limit = limit if limit else 50
        display_df = df.head(actual_limit)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('indx_name')): info_parts.append(f"名称: {row['indx_name']}")
            # if pd.notna(row.get('indx_csname')): info_parts.append(f"简称: {row['indx_csname']}")
            if pd.notna(row.get('pub_date')): info_parts.append(f"发布日期: {row['pub_date']}")
            if pd.notna(row.get('base_date')): info_parts.append(f"基期: {row['base_date']}")
            if pd.notna(row.get('bp')): info_parts.append(f"基点: {row['bp']}")
            
            result.append(" | ".join(info_parts))
            
        if len(df) > actual_limit:
             result.append(f"... (共 {len(df)} 条，仅显示前 {actual_limit} 条)")
             
        return "\n".join(result)
