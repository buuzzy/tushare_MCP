import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stock_company_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stock_company(ts_code: str = '', exchange: str = '', limit: int = None, offset: int = None) -> str:
        """
        获取上市公司基础信息 (stock_company)。
        
        参数:
            ts_code: 股票代码 (可选)
            exchange: 交易所代码 (SSE上交所 SZSE深交所 BSE北交所, 可选)
            limit: 单次返回数据长度 (可选)
            offset: 请求数据的开始位移量 (可选)
        """
        log_debug(f"Tool stock_company called with ts_code='{ts_code}', exchange='{exchange}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'exchange': exchange,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,com_name,com_id,exchange,chairman,manager,secretary,reg_capital,setup_date,province,city,introduction,website,email,office,employees,main_business,business_scope'

        df = pro.stock_company(**api_params, fields=fields)
        
        if df.empty:
            return "未找到上市公司基础信息"

        results = [f"--- 上市公司基础信息 (Total: {len(df)}) ---"]
        
        # Limit display if too large
        df_limited = df.head(10) # Company info is detailed, limit to 10 by default if list
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('com_name')): info.append(f"公司名称:{row['com_name']}")
             if pd.notna(row.get('exchange')): info.append(f"交易所:{row['exchange']}")
             if pd.notna(row.get('chairman')): info.append(f"法人代表:{row['chairman']}")
             if pd.notna(row.get('manager')): info.append(f"总经理:{row['manager']}")
             if pd.notna(row.get('secretary')): info.append(f"董秘:{row['secretary']}")
             if pd.notna(row.get('reg_capital')): info.append(f"注册资本:{row['reg_capital']}万元")
             if pd.notna(row.get('setup_date')): info.append(f"注册日期:{row['setup_date']}")
             if pd.notna(row.get('province')): info.append(f"省份:{row['province']}")
             if pd.notna(row.get('city')): info.append(f"城市:{row['city']}")
             
             # Detailed info, maybe truncate or put on new lines? 
             # For a list, keep it compact. If single result (ts_code specified), could be more detailed.
             # Given the format " | ".join(info), I'll add concise fields.
             
             if pd.notna(row.get('website')): info.append(f"主页:{row['website']}")
             if pd.notna(row.get('email')): info.append(f"Email:{row['email']}")
             if pd.notna(row.get('employees')): info.append(f"员工人数:{row['employees']}")
             
             # main_business and introduction can be very long. 
             if pd.notna(row.get('main_business')): 
                 mb = str(row['main_business'])
                 if len(mb) > 50: mb = mb[:50] + "..."
                 info.append(f"主营:{mb}")

             results.append(" | ".join(info))
            
        if len(df) > 10:
            results.append(f"... (共 {len(df)} 条，仅显示前 10 条)")
            
        return "\n".join(results)
