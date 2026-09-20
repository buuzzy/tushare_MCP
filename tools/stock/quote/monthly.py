from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .quote_utils import fetch_quote_data, format_quote_data, split_ts_codes

def register_monthly_tools(mcp):
    @mcp.tool()
    @handle_exception
    def monthly(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', adjust: str = 'qfq') -> str:
        """
        获取A股月线行情数据 (monthly)，支持股票、常见沪深指数与申万行业指数。

        股票月线由服务端按"日线+复权因子"聚合（与港股/美股月线同款工程解）：
        每月 high/low 为当月日内最高/最低，输出行含 最高日/最低日（极值发生的
        具体交易日），📊 区间统计行的极值价格与日期均已精确到日，直接引用即可，
        无需再补查日线锁定日期。指数/申万走原生月线 API，无极值发生日。

        复权口径：股票默认前复权（qfq），显式传 adjust='' 取不复权，'hfq' 后复权；
        指数/申万无复权概念。

        参数:
            ts_code: 股票或指数代码，支持逗号分隔 (e.g., '000001.SZ,801080.SI', 可选)
            trade_date: 交易日期 (YYYYMMDD, 需是月最后交易日, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
            adjust: 复权：'qfq'前复权(默认) / 'hfq'后复权 / ''不复权 (可选)
        """
        log_debug(f"Tool monthly called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}', adjust='{adjust}'...")
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
            stock_api="monthly",
            index_api="index_monthly",
            period="monthly",
            ts_code=ts_code,
            adjust=adjust,
            **api_params,
        )

        if df.empty:
            return "未找到月线行情数据"

        return format_quote_data(df, "monthly", requested_codes, adjust)
