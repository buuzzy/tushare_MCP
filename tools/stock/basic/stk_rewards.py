import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_stk_rewards_tools(mcp):
    @mcp.tool()
    @handle_exception
    def stk_rewards(ts_code: str, end_date: str = '') -> str:
        """
        获取上市公司管理层薪酬和持股信息 (stk_rewards)。
        
        参数:
            ts_code: 股票代码 (必选, 支持单个或多个)
            end_date: 报告期 (可选)
        """
        log_debug(f"Tool stk_rewards called with ts_code='{ts_code}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'ts_code,ann_date,end_date,name,title,reward,hold_vol'

        df = pro.stk_rewards(**api_params, fields=fields)
        
        if df.empty:
            return "未找到上市公司管理层薪酬和持股信息"

        results = [f"--- 上市公司管理层薪酬和持股信息 (Total: {len(df)}) ---"]
        
        # Limit display if too large
        df_limited = df.head(50) # Rewards list can be long
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('ann_date')): info.append(f"公告:{row['ann_date']}")
             if pd.notna(row.get('end_date')): info.append(f"截止:{row['end_date']}")
             if pd.notna(row.get('name')): info.append(f"姓名:{row['name']}")
             if pd.notna(row.get('title')): info.append(f"职务:{row['title']}")
             
             # Format reward and hold_vol
             if pd.notna(row.get('reward')): info.append(f"报酬:{row['reward']}万元")
             if pd.notna(row.get('hold_vol')): info.append(f"持股:{row['hold_vol']}股")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
