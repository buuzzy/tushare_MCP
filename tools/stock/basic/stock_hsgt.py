import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stock_hsgt_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stock_hsgt(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', type: str = '', limit: int = None, offset: int = None) -> str:
        """
        获取沪深港通股票列表 (stock_hsgt)。
        
        参数:
            ts_code: 股票代码 (可选)
            trade_date: 交易日期 (YYYYMMDD格式, 可选)
            start_date: 开始时间 (可选)
            end_date: 结束时间 (可选)
            type: 类型 (可选, 建议提供以过滤数据)
                  HK_SZ: 深股通(港>深)
                  SZ_HK: 港股通(深>港)
                  HK_SH: 沪股通(港>沪)
                  SH_HK: 港股通(沪>港)
            limit: 单次返回数据长度 (可选)
            offset: 请求数据的开始位移量 (可选)
            
        注意：本接口数据从 20250812 开始。
        """
        log_debug(f"Tool stock_hsgt called with type='{type}', trade_date='{trade_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date,
            'type': type,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,name,trade_date,type,type_name'

        df = pro.stock_hsgt(**api_params, fields=fields)
        
        if df.empty:
            return "未找到沪深港通股票列表数据"

        results = [f"--- 沪深港通股票列表 (Total: {len(df)}) ---"]
        
        # Limit display if too large
        df_limited = df.head(50)
        
        # ts_code, name, trade_date, type, type_name
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('type_name')): info.append(f"类型:{row['type_name']}")
             
             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
