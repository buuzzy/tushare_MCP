import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_disclosure_date_tools(mcp):
    @mcp.tool()
    @handle_exception
    def disclosure_date(ts_code: str = "", end_date: str = "", pre_date: str = "", 
               actual_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取上市公司的财报披露计划日期。(对应 tushare disclosure_date 接口)

        参数:
            ts_code: 股票代码
            end_date: 财报周期（每个季度最后一天的日期，比如20181231表示2018年年报）
            pre_date: 计划披露日期
            actual_date: 实际披露日期
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool disclosure_date called with ts_code='{ts_code}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'end_date': end_date,
            'pre_date': pre_date,
            'actual_date': actual_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,ann_date,end_date,pre_date,actual_date,modify_date'
        
        df = pro.disclosure_date(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的财报披露计划数据"

        result = [f"--- size: {len(df)} ---"]
        
        # Display cap
        display_cap = 100
        # If user explicitly set a limit that is smaller, use that.
        if limit and limit < display_cap:
             display_cap = limit
             
        display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"报告期: {row['end_date']}")
            
            # Dates
            dates = []
            if pd.notna(row.get('pre_date')): dates.append(f"预计: {row['pre_date']}")
            if pd.notna(row.get('actual_date')): dates.append(f"实际: {row['actual_date']}")
            if dates: info_parts.append(" | ".join(dates))

            # Modify history
            if pd.notna(row.get('modify_date')): info_parts.append(f"修正记录: {row['modify_date']}")
            
             # Announce date
            if pd.notna(row.get('ann_date')): info_parts.append(f"公告: {row['ann_date']}")

            result.append("\n".join(info_parts))
            result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
