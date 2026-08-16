from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .quote_utils import fetch_quote_data, format_quote_data, split_ts_codes

def register_daily_tools(mcp):
    @mcp.tool()
    @handle_exception
    def daily(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '') -> str:
        """
        获取A股日线行情数据 (daily)，支持股票与常见沪深指数。
        
        参数:
            ts_code: 股票或指数代码，支持逗号分隔 (e.g., '000001.SZ,000001.SH', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
        """
        log_debug(f"Tool daily called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}'...")
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
            stock_api="daily",
            index_api="index_daily",
            ts_code=ts_code,
            **api_params,
        )
        
        if df.empty:
            return "未找到日线行情数据"

        return format_quote_data(df, "daily", requested_codes)
