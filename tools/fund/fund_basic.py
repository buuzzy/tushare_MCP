import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_basic_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_basic(ts_code: str = "", market: str = "", status: str = "", name: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取公募基金数据列表，包括场内和场外基金。
        **注意：不包含ETF基金，ETF请使用 etf_basic 接口。**
        
        参数:
            ts_code: 基金代码 (支持多只基金，逗号分隔)
            market: 交易市场: E场内 O场外
            status: 存续状态 D摘牌 I发行 L上市中
            name: 基金名称（本地筛选，支持模糊匹配）
            limit: 单次返回数据长度（最大15000行）
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_basic called with market='{market}', status='{status}', name='{name}', ts_code='{ts_code}'...")
        pro = get_pro_client()
        
        fields = 'ts_code,name,management,custodian,fund_type,found_date,list_date,issue_amount,m_fee,c_fee,p_value,min_amount,exp_return,status,market'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                params = {
                    'ts_code': code,
                    'market': market,
                    'status': status,
                    'limit': limit,
                    'offset': offset
                }
                api_params = {k: v for k, v in params.items() if v}
                temp_df = pro.fund_basic(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            params = {
                'ts_code': ts_code,
                'market': market,
                'status': status,
                'limit': limit,
                'offset': offset
            }
            api_params = {k: v for k, v in params.items() if v}
            df = pro.fund_basic(**api_params, fields=fields)
            
        if df.empty:
            return "未找到符合条件的公募基金信息"

        # --- Local Enhancement: Filter by Name ---
        if name:
            df = df[df['name'].str.contains(name, na=False)]
            if df.empty:
                return f"未找到名称包含 '{name}' 的基金"
        # -----------------------------------------

        result = [f"--- size: {len(df)} ---"]
        display_cap = 50
        display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('name')): info_parts.append(f"名称: {row['name']}")
            if pd.notna(row.get('management')): info_parts.append(f"管理人: {row['management']}")
            if pd.notna(row.get('fund_type')): info_parts.append(f"类型: {row['fund_type']}")
            if pd.notna(row.get('market')): 
                mkt = "场内" if row['market'] == 'E' else "场外"
                info_parts.append(f"市场: {mkt}")
            if pd.notna(row.get('status')): 
                st =  {'L':'上市','D':'摘牌','I':'发行'}.get(row['status'], row['status'])
                info_parts.append(f"状态: {st}")
            
            if pd.notna(row.get('issue_amount')): info_parts.append(f"发行份额: {row['issue_amount']}亿")
            if pd.notna(row.get('m_fee')): info_parts.append(f"管理费: {row['m_fee']}%")
            
            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
