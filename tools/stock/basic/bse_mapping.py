import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_bse_mapping_tools(mcp):
    @mcp.tool()
    @handle_exception
    def bse_mapping(o_code: str = '', n_code: str = '') -> str:
        """
        获取北交所股票代码变更后新旧代码映射表数据 (bse_mapping)。
        
        参数:
            o_code: 旧代码 (可选)
            n_code: 新代码 (可选)
        """
        log_debug(f"Tool bse_mapping called with o_code='{o_code}', n_code='{n_code}'...")
        pro = get_pro_client()
        params = {
            'o_code': o_code,
            'n_code': n_code
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'name,o_code,n_code,list_date'

        df = pro.bse_mapping(**api_params, fields=fields)
        
        if df.empty:
            return "未找到北交所新旧代码映射数据"

        results = [f"--- 北交所新旧代码映射数据 (Total: {len(df)}) ---"]
        
        # Limit display if too large (although docs say max 300 total, 1000 per call, let's limit output to 50)
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('o_code')): info.append(f"原代码:{row['o_code']}")
             if pd.notna(row.get('n_code')): info.append(f"新代码:{row['n_code']}")
             if pd.notna(row.get('list_date')): info.append(f"上市日期:{row['list_date']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
