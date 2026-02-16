import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stock_st_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stock_st(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', exchange: str = '', limit: int = None, offset: int = None) -> str:
        """
        获取ST股票列表，可根据交易日期获取历史上每天的ST列表。(对应 tushare stock_st 接口)
        
        参数:
            ts_code: 股票代码 (可选)
            trade_date: 交易日期 (YYYYMMDD格式, 可选)
            start_date: 开始时间 (可选)
            end_date: 结束时间 (可选)
            exchange: 交易所过滤 (可选, 例如 'SZSE', 'SSE', 'BSE') -- *本地增强参数*
            limit: 单次返回数据长度 (可选)
            offset: 请求数据的开始位移量 (可选)
        """
        log_debug(f"Tool stock_st called with ts_code='{ts_code}', trade_date='{trade_date}', exchange='{exchange}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params - but handle limit carefully
        api_params = {k: v for k, v in params.items() if v and k not in ['limit', 'offset']}
        
        # If we are doing local filtering (exchange), we MUST NOT limit the API call
        # otherwise we might get the first 10 rows from API (e.g. SZSE), none of which match the filter (SSE).
        # We only pass limit to API if NO local filter is applied.
        has_local_filter = bool(exchange)
        if not has_local_filter:
             if limit: api_params['limit'] = limit
             if offset: api_params['offset'] = offset
        
        # Explicit fields from doc
        fields = 'ts_code,name,trade_date,type,type_name'

        df = pro.stock_st(**api_params, fields=fields)
        
        if df.empty:
            return "未找到ST股票列表数据"

        # --- Local Enhancement: Filter by Exchange ---
        if exchange:
            # Map common exchange names to suffixes if needed, or just check containment
            # Tushare ts_code: 000001.SZ (SZSE), 600000.SH (SSE), 8xxxx.BJ (BSE)
            exchange = exchange.upper()
            suffix_map = {
                'SZSE': '.SZ',
                'SSE': '.SH',
                'BSE': '.BJ'
            }
            suffix = suffix_map.get(exchange)
            
            if suffix:
                df = df[df['ts_code'].str.endswith(suffix)]
            else:
                # Fallback: try direct string match if user passes '.SZ' or something
                df = df[df['ts_code'].str.contains(exchange)]
            
            if df.empty:
                return f"未找到该交易所 ({exchange}) 的ST股票数据"
            if df.empty:
                return f"未找到该交易所 ({exchange}) 的ST股票数据"
        # ---------------------------------------------

        # Apply limit/offset locally if we had local filters
        if has_local_filter:
            start = offset if offset else 0
            end = start + limit if limit else None
            df = df.iloc[start:end]
            
        results = [f"--- ST股票列表 (Total: {len(df)}) ---"]
        
        # Limit display if too large to save tokens
        # If user just asked for count, the 'Total' above is enough.
        # But we still show some data.
        df_limited = df.head(50)
        
        # ts_code   name trade_date type type_name
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('type_name')): info.append(f"说明:{row['type_name']}")
             
             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
