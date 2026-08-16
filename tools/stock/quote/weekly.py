from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .quote_utils import fetch_quote_data, format_quote_data, split_ts_codes

def register_weekly_tools(mcp):
    @mcp.tool()
    @handle_exception
    def weekly(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取A股周线行情数据 (weekly)，支持股票与常见沪深指数。
        
        参数:
            ts_code: 股票或指数代码，支持逗号分隔 (e.g., '000001.SZ,399001.SZ', 可选)
            trade_date: 交易日期 (YYYYMMDD, 需是周五或周最后一个交易日, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool weekly called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        # ts_code is passed separately to keep multi-code routing explicit.
        api_params = {k: v for k, v in params.items() if v and k != "ts_code"}
        
        requested_codes = split_ts_codes(ts_code)
        df = fetch_quote_data(
            pro,
            stock_api="weekly",
            index_api="index_weekly",
            ts_code=ts_code,
            **api_params,
        )
        
        if df.empty:
            return "未找到周线行情数据"

        return format_quote_data(df, "weekly", requested_codes)
