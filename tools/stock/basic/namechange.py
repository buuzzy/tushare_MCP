import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_namechange_tools(mcp):
    @mcp.tool()
    @handle_exception
    def namechange(ts_code: str = '', start_date: str = '', end_date: str = '', limit: int = None, offset: int = None) -> str:
        """
        获取上市公司历史名称变更记录 (namechange)。
        
        参数:
            ts_code: TS股票代码 (可选)
            start_date: 公告开始日期 (YYYYMMDD格式, 可选)
            end_date: 公告结束日期 (YYYYMMDD格式, 可选)
            limit: 单次返回数据长度 (可选)
            offset: 请求数据的开始位移量 (可选)
        """
        log_debug(f"Tool namechange called with ts_code='{ts_code}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,name,start_date,end_date,ann_date,change_reason'

        df = pro.namechange(**api_params, fields=fields)
        
        if df.empty:
            return "未找到名称变更记录"

        # Remove duplicate records
        df = df.drop_duplicates()

        results = [f"--- 历史名称变更记录 (Total: {len(df)}) ---"]
        
        # Limit display if too large
        df_limited = df.head(50)
        
        # ts_code, name, start_date, end_date, ann_date, change_reason
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('start_date')): info.append(f"开始日期:{row['start_date']}")
             if pd.notna(row.get('end_date')): info.append(f"结束日期:{row['end_date']}")
             if pd.notna(row.get('ann_date')): info.append(f"公告日期:{row['ann_date']}")
             if pd.notna(row.get('change_reason')): info.append(f"原因:{row['change_reason']}")
             
             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
