import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_manager_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_manager(ts_code: str = "", ann_date: str = "", name: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取公募基金经理数据，包括基金经理简历等数据。
        
        参数:
            ts_code: 基金代码 (支持多只基金，逗号分隔)
            ann_date: 公告日期 (YYYYMMDD)
            name: 基金经理姓名
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_manager called with ts_code='{ts_code}', name='{name}'...")
        pro = get_pro_client()
        
        # Construct API parameters
        api_params = {
            "ts_code": ts_code,
            "ann_date": ann_date,
            "name": name,
            "limit": limit,
            "offset": offset
        }
        
        # Filter out empty parameters
        api_params = {k: v for k, v in api_params.items() if v is not None and v != ""}
        
        fields = 'ts_code,ann_date,name,gender,birth_year,edu,nationality,begin_date,end_date,resume'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_manager(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_manager(**api_params, fields=fields)
        
        if df.empty:
            return "未找到符合条件的基金经理信息"

        # Format output
        result = [f"--- size: {len(df)} ---"]
        
        # Display logic: If limit is small, show all. If large, cap at 50 for display unless requested.
        display_cap = 50
        if limit:
            display_df = df.head(limit)
        else:
            display_df = df.head(display_cap)
            
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"基金代码: {row['ts_code']}")
            if pd.notna(row.get('name')): info_parts.append(f"姓名: {row['name']}")
            if pd.notna(row.get('gender')): info_parts.append(f"性别: {row['gender']}")
            if pd.notna(row.get('edu')): info_parts.append(f"学历: {row['edu']}")
            if pd.notna(row.get('nationality')): info_parts.append(f"国籍: {row['nationality']}")
            if pd.notna(row.get('begin_date')): info_parts.append(f"任职: {row['begin_date']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"离任: {row['end_date']}")
            
            # Resume might be long, put it at the end or truncate if needed
            # For now, just append it.
            resume = row.get('resume')
            if pd.notna(resume):
                # Truncate resume if too long for a single line view
                if len(resume) > 50:
                    resume_short = resume[:50] + "..."
                    info_parts.append(f"简历: {resume_short}")
                else:
                    info_parts.append(f"简历: {resume}")

            result.append(" | ".join(info_parts))
            
        if limit and len(df) > limit:
             result.append(f"... (共 {len(df)} 条，仅显示前 {limit} 条)")
        elif not limit and len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
