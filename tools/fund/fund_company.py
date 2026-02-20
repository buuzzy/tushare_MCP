import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_company_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_company(name: str = "", province: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取公募基金管理人（基金公司）列表。
        **默认按成立日期倒序排列（新成立的在前）。**
        
        参数:
            name: 基金公司名称或简称 (本地筛选，支持模糊匹配)
            province: 省份 (本地筛选，支持模糊匹配)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_company called with name='{name}', province='{province}'...")
        pro = get_pro_client()
        
        # API takes no parameters, returns all data
        fields = 'name,shortname,province,city,setup_date,manager,chairman,website,phone,office'
        
        df = pro.fund_company(fields=fields)
        if df.empty:
            return "未找到基金公司信息"

        # --- Local Enhancement: Filter by Name/Province ---
        if name:
            df = df[df['name'].str.contains(name, na=False) | df['shortname'].str.contains(name, na=False)]
        
        if province:
             df = df[df['province'].str.contains(province, na=False)]
             
        if df.empty:
            return "未找到符合条件的基金公司"
        # --------------------------------------------------

        # Sort by setup_date descending (newest first)
        if 'setup_date' in df.columns:
            df = df.sort_values(by='setup_date', ascending=False)

        result = [f"--- size: {len(df)} ---"]
        display_cap = 50
        
        # Apply strict limit if provided
        if limit:
            display_df = df.head(limit)
        else:
            display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('name')): info_parts.append(f"公司: {row['name']}")
            # if pd.notna(row.get('shortname')): info_parts.append(f"简称: {row['shortname']}")
            if pd.notna(row.get('province')): info_parts.append(f"省份: {row['province']}")
            if pd.notna(row.get('city')): info_parts.append(f"城市: {row['city']}")
            if pd.notna(row.get('setup_date')): info_parts.append(f"成立: {row['setup_date']}")
            if pd.notna(row.get('manager')): info_parts.append(f"总经理: {row['manager']}")
            
            result.append(" | ".join(info_parts))
            
        if limit and len(df) > limit:
             result.append(f"... (共 {len(df)} 条，仅显示前 {limit} 条)")
        elif not limit and len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
