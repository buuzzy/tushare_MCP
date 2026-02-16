import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_bak_basic_tools(mcp):
    @mcp.tool()
    @handle_exception
    def bak_basic(trade_date: str = '', ts_code: str = '') -> str:
        """
        获取备用基础列表数据 (bak_basic)。
        
        参数:
            trade_date: 交易日期 (YYYYMMDD, 可选)
            ts_code: 股票代码 (可选)
        """
        log_debug(f"Tool bak_basic called with trade_date='{trade_date}', ts_code='{ts_code}'...")
        pro = get_pro_client()
        params = {
            'trade_date': trade_date,
            'ts_code': ts_code
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields from doc
        fields = 'trade_date,ts_code,name,industry,area,pe,float_share,total_share,total_assets,liquid_assets,fixed_assets,reserved,reserved_pershare,eps,bvps,pb,list_date,undp,per_undp,rev_yoy,profit_yoy,gpr,npr,holder_num'

        df = pro.bak_basic(**api_params, fields=fields)
        
        if df.empty:
            return "未找到备用基础列表数据"

        results = [f"--- 备用基础列表数据 (Total: {len(df)}) ---"]
        
        # Limit display
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('industry')): info.append(f"行业:{row['industry']}")
             if pd.notna(row.get('area')): info.append(f"地域:{row['area']}")
             if pd.notna(row.get('pe')): info.append(f"PE:{row['pe']}")
             if pd.notna(row.get('float_share')): info.append(f"流通股:{row['float_share']}亿")
             if pd.notna(row.get('total_share')): info.append(f"总股本:{row['total_share']}亿")
             if pd.notna(row.get('total_assets')): info.append(f"总资产:{row['total_assets']}亿")
             if pd.notna(row.get('eps')): info.append(f"EPS:{row['eps']}")
             if pd.notna(row.get('pb')): info.append(f"PB:{row['pb']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
