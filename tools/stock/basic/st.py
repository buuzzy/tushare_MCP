import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_st_tools(mcp):
    @mcp.tool()
    @handle_exception
    def st(ts_code: str = '', pub_date: str = '', imp_date: str = '', limit: int = None, offset: int = None) -> str:
        """
        获取ST风险警示板股票列表。(对应 tushare st 接口)
        
        参数:
            ts_code: 股票代码 (可选)
            pub_date: 发布日期 (YYYYMMDD格式, 可选)
            imp_date: 实施日期 (YYYYMMDD格式, 可选)
            limit: 单次返回数据长度 (可选)
            offset: 请求数据的开始位移量 (可选)
        """
        log_debug(f"Tool st called with ts_code='{ts_code}', pub_date='{pub_date}', imp_date='{imp_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'pub_date': pub_date,
            'imp_date': imp_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,name,pub_date,imp_date,st_tpye,st_reason,st_explain'

        df = pro.st(**api_params, fields=fields)
        
        if df.empty:
            return "未找到ST风险警示板股票数据"

        results = [f"--- ST风险警示板股票列表 (Total: {len(df)}) ---"]
        
        # Limit display if too large
        df_limited = df.head(50)
        
        # ts_code, name, pub_date, imp_date, st_tpye, st_reason, st_explain
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('pub_date')): info.append(f"发布日期:{row['pub_date']}")
             if pd.notna(row.get('imp_date')): info.append(f"实施日期:{row['imp_date']}")
             if pd.notna(row.get('st_tpye')): info.append(f"类型:{row['st_tpye']}")
             if pd.notna(row.get('st_reason')): info.append(f"原因:{row['st_reason']}")
             # st_explain might be long, maybe truncate? keeping it for now.
             
             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
