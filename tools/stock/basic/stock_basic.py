import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stock_basic_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stock_basic(ts_code: str = "", name: str = "", exchange: str = "", market: str = "", 
                   is_hs: str = "", list_status: str = "L", area: str = "", industry: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取基础信息数据，包括股票代码、名称、上市日期、退市日期等。(对应 tushare stock_basic 接口)
        
        参数:
            ts_code: 股票代码（支持多个股票同时提取，逗号分隔）
            name: 股票名称
            exchange: 交易所 SSE上交所 SZSE深交所 BSE北交所
            market: 市场类别 （主板/创业板/科创板/CDR）
            is_hs: 是否沪深港通标的，N否 H沪股通 S深股通
            list_status: 上市状态 L上市 D退市 P暂停上市，默认是L
            area: 地域 (可选, 例如 '深圳', '北京') -- *本地增强参数*
            industry: 行业 (可选, 例如 '银行', '软件服务') -- *本地增强参数*
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool stock_basic called with ts_code='{ts_code}', area='{area}', industry='{industry}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'name': name,
            'exchange': exchange,
            'market': market,
            'is_hs': is_hs,
            'list_status': list_status,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params - but handle limit carefully
        api_params = {k: v for k, v in params.items() if v and k not in ['limit', 'offset']}
        
        # If we are doing local filtering (area/industry), we MUST NOT limit the API call
        # otherwise we might get the first 10 rows from API, none of which match the filter.
        # We only pass limit to API if NO local filter is applied.
        has_local_filter = bool(area or industry)
        if not has_local_filter:
             if limit: api_params['limit'] = limit
             if offset: api_params['offset'] = offset
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,symbol,name,area,industry,market,list_date,fullname,enname,cnspell,exchange,curr_type,list_status,delist_date,is_hs'
        
        df = pro.stock_basic(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的股票基础信息"

        # --- Local Enhancement: Filter by Area / Industry ---
        if area:
            df = df[df['area'] == area]
            if df.empty:
                return f"未找到地域为 '{area}' 的股票"
        
        if industry:
            df = df[df['industry'] == industry]
            if df.empty:
                return f"未找到行业为 '{industry}' 的股票"
        # ----------------------------------------------------

        # Apply limit/offset locally if we had local filters
        if has_local_filter:
            start = offset if offset else 0
            end = start + limit if limit else None
            df = df.iloc[start:end]

        result = [f"--- size: {len(df)} ---"]
        # Limit display quantity if too large, though user usually filters
        # If user explicitly set a limit (e.g. 5), df is already sliced above or via API.
        # But for display purposes in the return string, we might still want a cap if the result is huge 
        # (e.g. user asked for all banks, got 500 rows).
        display_cap = 50
        display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('name')): info_parts.append(f"名称: {row['name']}")
            if pd.notna(row.get('industry')): info_parts.append(f"行业: {row['industry']}")
            if pd.notna(row.get('area')): info_parts.append(f"地区: {row['area']}")
            if pd.notna(row.get('market')): info_parts.append(f"市场: {row['market']}")
            if pd.notna(row.get('list_date')): info_parts.append(f"上市日期: {row['list_date']}")
            if pd.notna(row.get('list_status')): info_parts.append(f"状态: {row['list_status']}")
            
            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
