import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .trade_date_utils import resolve_trade_date

def register_ggt_top10_tools(mcp):
    @mcp.tool()
    @handle_exception
    def ggt_top10(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', market_type: str = '') -> str:
        """
        获取港股通每日成交数据 (ggt_top10)，包括沪市、深市详细数据。
        
        参数:
            ts_code: 股票代码 (e.g., '00700', 可选)
            trade_date: 单个交易日期 (YYYYMMDD, 可选)
            start_date: 兼容输入 (YYYYMMDD, 可选)。上游只支持 trade_date，会转换为该日期当日或之后最近交易日
            end_date: 兼容输入 (YYYYMMDD, 可选)。上游只支持 trade_date，会转换为该日期当日或之前最近交易日
            market_type: 市场类型 2：港股通（沪） 4：港股通（深） (可选)
        """
        log_debug(f"Tool ggt_top10 called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}', market_type='{market_type}'...")
        pro = get_pro_client()
        
        # This TinyShare endpoint only accepts trade_date. Convert common
        # range-style arguments instead of forwarding unsupported parameters.
        if not trade_date:
            resolved_date = resolve_trade_date(pro, start_date, end_date)
            if resolved_date:
                trade_date = resolved_date
                log_debug(f"Normalized ggt_top10 query to trading date: {trade_date}")

        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'market_type': market_type
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        df = pro.ggt_top10(**api_params)
        
        if df.empty:
            return "未找到港股通十大成交股数据"

        results = [f"--- 港股通十大成交股 (Total: {len(df)}) ---"]
        
        # Limit display
        df_limited = df.head(50) 
        
        for _, row in df_limited.iterrows():
             info = []
             if pd.notna(row.get('trade_date')): info.append(f"日期:{row['trade_date']}")
             if pd.notna(row.get('ts_code')): info.append(f"代码:{row['ts_code']}")
             if pd.notna(row.get('name')): info.append(f"名称:{row['name']}")
             if pd.notna(row.get('rank')): info.append(f"排名:{row['rank']}")
             if pd.notna(row.get('market_type')): info.append(f"市场:{row['market_type']}")
             if pd.notna(row.get('net_amount')): info.append(f"净买入:{row['net_amount']}")
             if pd.notna(row.get('amount')): info.append(f"成交额:{row['amount']}")

             results.append(" | ".join(info))
            
        if len(df) > 50:
            results.append(f"... (共 {len(df)} 条，仅显示前 50 条)")
            
        return "\n".join(results)
