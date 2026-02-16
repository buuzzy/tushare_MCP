import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stk_managers_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stk_managers(ts_code: str = '', ann_date: str = '', start_date: str = '', end_date: str = '', limit: int = None, offset: int = None) -> str:
        """
        获取上市公司管理层信息 (stk_managers)。
        
        参数:
            ts_code: 股票代码 (可选, 支持单个或多个)
            ann_date: 公告日期 (YYYYMMDD, 可选)
            start_date: 公告开始日期 (可选)
            end_date: 公告结束日期 (可选)
            limit: 单次返回数据长度 (可选)
            offset: 请求数据的开始位移量 (可选)
        """
        log_debug(f"Tool stk_managers called with ts_code='{ts_code}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'ann_date': ann_date,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,ann_date,name,gender,lev,title,edu,national,birthday,begin_date,end_date,resume'

        df = pro.stk_managers(**api_params, fields=fields)
        
        if df.empty:
            return "未找到上市公司管理层信息"

        # Remove duplicate records
        df = df.drop_duplicates()

        results = [f"--- 上市公司管理层信息 (Total: {len(df)}) ---"]
        
        # Limit display if too large
        df_limited = df.head(20) # Managers list can be long, 20 seem reasonable
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('ann_date')): info.append(f"公告:{row['ann_date']}")
             if pd.notna(row.get('name')): info.append(f"姓名:{row['name']}")
             if pd.notna(row.get('gender')): info.append(f"性别:{row['gender']}")
             if pd.notna(row.get('lev')): info.append(f"岗位类别:{row['lev']}")
             if pd.notna(row.get('title')): info.append(f"职务:{row['title']}")
             if pd.notna(row.get('edu')): info.append(f"学历:{row['edu']}")
             if pd.notna(row.get('national')): info.append(f"国籍:{row['national']}")
             if pd.notna(row.get('birthday')): info.append(f"出生:{row['birthday']}")
             if pd.notna(row.get('begin_date')): info.append(f"上任:{row['begin_date']}")
             if pd.notna(row.get('end_date')): info.append(f"离任:{row['end_date']}")
             
             # Resume is usually long text
             if pd.notna(row.get('resume')):
                 bg = str(row['resume'])
                 if len(bg) > 50: bg = bg[:50] + "..."
                 info.append(f"简历:{bg}")

             results.append(" | ".join(info))
            
        if len(df) > 20:
            results.append(f"... (共 {len(df)} 条，仅显示前 20 条)")
            
        return "\n".join(results)
