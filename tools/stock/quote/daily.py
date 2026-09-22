from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client
from .quote_utils import fetch_quote_data, format_quote_data, split_ts_codes

def register_daily_tools(mcp):
    @mcp.tool()
    @handle_exception
    def daily(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '', adjust: str = 'qfq') -> str:
        """
        获取A股日线行情数据 (daily)，支持股票、沪深指数与申万行业指数(801xxx.SI)。

        输出附带📊区间统计行（区间最高/最低及发生日、区间涨跌幅、最新收盘，
        服务端已对全量数据计算）：求区间极值/涨幅直接引用该行，无需自行扫描
        或分段补查。

        复权口径：股票默认前复权（qfq），拆股/送转/分红不呈现假断崖，标题行
        有"前复权"声明；显式传 adjust='' 可取不复权原始价，'hfq' 为后复权。
        指数/申万行业指数无复权概念，adjust 参数不生效。

        长区间（单代码超 250 根）自动聚合为周线全史输出（附极值发生日），
        区间走势图表直接用返回数据绘制；如需日线明细，缩小日期范围。

        参数:
            ts_code: 股票或指数代码，支持逗号分隔 (e.g., '000001.SZ,801080.SI', 可选)
            trade_date: 交易日期 (YYYYMMDD, 可选)
            start_date: 开始日期 (YYYYMMDD, 可选)
            end_date: 结束日期 (YYYYMMDD, 可选)
            adjust: 复权：'qfq'前复权(默认) / 'hfq'后复权 / ''不复权 (可选)
        """
        log_debug(f"Tool daily called with ts_code='{ts_code}', trade_date='{trade_date}', start_date='{start_date}', end_date='{end_date}', adjust='{adjust}'...")
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
            period="daily",
            ts_code=ts_code,
            adjust=adjust,
            **api_params,
        )

        if df.empty:
            return "未找到日线行情数据"

        return format_quote_data(df, "daily", requested_codes, adjust, attach_news=True)
