import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_daily_basic_tools(mcp):
    @mcp.tool()
    @handle_exception
    def daily_basic(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取A股每日重要的基本面指标 (daily_basic)，如PE、PB、换手率等。
        
        参数:
            ts_code: 股票代码 (e.g., '000001.SZ', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool daily_basic called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.daily_basic(**api_params)
        
        if df.empty:
            return "未找到每日基本面指标数据"

        results = [f"--- 每日基本面指标 (Total: {len(df)}) ---"]
        
        # Limit display for large results
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('close')): info.append(f"收盘:{row['close']}")
             if pd.notna(row.get('turnover_rate')): info.append(f"换手率:{row['turnover_rate']}%")
             if pd.notna(row.get('turnover_rate_f')): info.append(f"换手率(自由):{row['turnover_rate_f']}%")
             if pd.notna(row.get('volume_ratio')): info.append(f"量比:{row['volume_ratio']}")
             if pd.notna(row.get('pe')): info.append(f"PE:{row['pe']}")
             if pd.notna(row.get('pe_ttm')): info.append(f"PE(TTM):{row['pe_ttm']}")
             if pd.notna(row.get('pb')): info.append(f"PB:{row['pb']}")
             if pd.notna(row.get('ps')): info.append(f"PS:{row['ps']}")
             if pd.notna(row.get('ps_ttm')): info.append(f"PS(TTM):{row['ps_ttm']}")
             if pd.notna(row.get('dv_ratio')): info.append(f"股息率:{row['dv_ratio']}%")
             if pd.notna(row.get('dv_ttm')): info.append(f"股息率(TTM):{row['dv_ttm']}%")
             if pd.notna(row.get('total_share')): info.append(f"总股本:{row['total_share']}万股")
             if pd.notna(row.get('float_share')): info.append(f"流通股本:{row['float_share']}万股")
             if pd.notna(row.get('free_share')): info.append(f"自由流通股本:{row['free_share']}万股")
             if pd.notna(row.get('total_mv')): info.append(f"总市值:{row['total_mv']}万元")
             if pd.notna(row.get('circ_mv')): info.append(f"流通市值:{row['circ_mv']}万元")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
