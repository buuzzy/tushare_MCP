import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_research_report_tools(mcp):
    @mcp.tool()
    @handle_exception
    def research_report(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '',
                        report_type: str = '', inst_csname: str = '', ind_name: str = '',
                        limit: int = 20) -> str:
        """
        获取券商研究报告（个股研报、行业研报、宏观研究等）。数据自2021年起覆盖，每日增量更新。

        参数:
            ts_code: 股票代码（可选），如 600519.SH
            trade_date: 研报日期 YYYYMMDD（可选），按该日拉取全市场
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            report_type: 研报类别（可选）：个股研报 / 行业研报 / 宏观研究
            inst_csname: 券商简称（可选）
            ind_name: 行业名称（可选）
            limit: 返回条数上限，默认20
        """
        log_debug(f"Tool research_report called: ts_code={ts_code}, trade_date={trade_date}")
        if not any([ts_code, trade_date, start_date, report_type, inst_csname, ind_name]):
            return "错误：至少提供一个筛选条件（ts_code/trade_date/start_date/report_type 等）"

        params = {k: v for k, v in {
            'ts_code': ts_code, 'trade_date': trade_date,
            'start_date': start_date, 'end_date': end_date,
            'report_type': report_type, 'inst_csname': inst_csname,
            'ind_name': ind_name, 'limit': limit,
        }.items() if v}
        pro = get_corpus_client()
        df = pro.research_report(**params)
        if df.empty:
            return "未找到符合条件的研报数据"

        result = [f"--- 券商研报 (Total: {len(df)}) ---"]
        display_cap = min(20, len(df))
        for _, row in df.head(display_cap).iterrows():
            parts = []
            if pd.notna(row.get('trade_date')): parts.append(f"日期:{row['trade_date']}")
            if pd.notna(row.get('title')): parts.append(f"标题:{row['title']}")
            if pd.notna(row.get('report_type')): parts.append(f"类型:{row['report_type']}")
            if pd.notna(row.get('inst_csname')): parts.append(f"机构:{row['inst_csname']}")
            if pd.notna(row.get('name')): parts.append(f"个股:{row['name']}")
            if pd.notna(row.get('ind_name')): parts.append(f"行业:{row['ind_name']}")
            result.append(" | ".join(parts))

        if len(df) > display_cap:
            result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
        return "\n".join(result)
