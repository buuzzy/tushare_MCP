import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_new_share_tools(mcp):
    @mcp.tool()
    @handle_exception
    def new_share(start_date: str = '', end_date: str = '') -> str:
        """
        获取新股上市列表数据 (new_share)。
        
        参数:
            start_date: 上网发行开始日期 (YYYYMMDD, 可选)
            end_date: 上网发行结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool new_share called with start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'start_date': start_date,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,sub_code,name,ipo_date,issue_date,amount,market_amount,price,pe,limit_amount,funds,ballot'

        df = pro.new_share(**api_params, fields=fields)
        
        if df.empty:
            return "未找到新股上市列表数据"

        results = [f"--- 新股上市列表数据 (Total: {len(df)}) ---"]
        
        # Limit display
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('ipo_date')): info.append(f"上网发行:{row['ipo_date']}")
             if pd.notna(row.get('issue_date')): info.append(f"上市日期:{row['issue_date']}")
             if pd.notna(row.get('price')): info.append(f"发行价:{row['price']}")
             if pd.notna(row.get('pe')): info.append(f"市盈率:{row['pe']}")
             if pd.notna(row.get('limit_amount')): info.append(f"申购上限:{row['limit_amount']}万股")
             if pd.notna(row.get('funds')): info.append(f"募资:{row['funds']}亿元")
             if pd.notna(row.get('ballot')): info.append(f"中签率:{row['ballot']}%")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
