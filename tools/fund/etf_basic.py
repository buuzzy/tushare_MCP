import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_etf_basic_tools(mcp):
    @mcp.tool()
    @handle_exception
    def etf_basic(ts_code: str = "", index_code: str = "", list_date: str = "", list_status: str = "", exchange: str = "", mgr: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取国内ETF基础信息，包括了QDII。
        
        参数:
            ts_code: ETF代码（带.SZ/.SH后缀的6位数字，如：159526.SZ。**支持多代码批量查询，逗号分隔**）
            index_code: 跟踪指数代码
            list_date: 上市日期（格式：YYYYMMDD）
            list_status: 上市状态（L上市 D退市 P待上市）
            exchange: 交易所（SH上交所 SZ深交所）
            mgr: 管理人（简称，e.g.华夏基金)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool etf_basic called with ts_code='{ts_code}', mgr='{mgr}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'index_code': index_code,
            'list_date': list_date,
            'list_status': list_status,
            'exchange': exchange,
            'mgr': mgr,
            'limit': limit,
            'offset': offset
        }
        api_params = {k: v for k, v in params.items() if v}
        
        fields = 'ts_code,csname,extname,cname,index_code,index_name,setup_date,list_date,list_status,exchange,mgr_name,custod_name,mgt_fee,etf_type'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                params = {
                    'ts_code': code,
                    'index_code': index_code,
                    'list_date': list_date,
                    'list_status': list_status,
                    'exchange': exchange,
                    'mgr': mgr,
                    'limit': limit,
                    'offset': offset
                }
                api_params = {k: v for k, v in params.items() if v}
                temp_df = pro.etf_basic(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            params = {
                'ts_code': ts_code,
                'index_code': index_code,
                'list_date': list_date,
                'list_status': list_status,
                'exchange': exchange,
                'mgr': mgr,
                'limit': limit,
                'offset': offset
            }
            api_params = {k: v for k, v in params.items() if v}
            df = pro.etf_basic(**api_params, fields=fields)
            
        if df.empty:
            return "未找到符合条件的ETF基础信息"

        # --- Local Enhancement: Filter by Manager (mgr) ---
        if mgr:
            # Filter where mgr_name contains the search term (loose matching)
            df = df[df['mgr_name'].str.contains(mgr, na=False)]
            if df.empty:
                return f"未找到管理人包含 '{mgr}' 的ETF"
        # --------------------------------------------------

        result = [f"--- size: {len(df)} ---"]
        display_cap = 50
        display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('extname')): info_parts.append(f"简称: {row['extname']}")
            if pd.notna(row.get('index_name')): info_parts.append(f"指数: {row['index_name']}")
            if pd.notna(row.get('exchange')): info_parts.append(f"交易所: {row['exchange']}")
            if pd.notna(row.get('mgr_name')): info_parts.append(f"管理人: {row['mgr_name']}")
            if pd.notna(row.get('etf_type')): info_parts.append(f"类型: {row['etf_type']}")
            
            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
