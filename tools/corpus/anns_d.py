import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_anns_d_tools(mcp):
    @mcp.tool()
    @handle_exception
    def anns_d(ts_code: str = '', trade_date: str = '', start_date: str = '', end_date: str = '',
               limit: int = 50) -> str:
        """
        获取上市公司公告数据。

        参数:
            ts_code: 股票代码（可选），如 600519.SH
            trade_date: 公告日期 YYYYMMDD（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            limit: 返回条数上限，默认50
        """
        log_debug(f"Tool anns_d called: ts_code={ts_code}, trade_date={trade_date}")
        if not any([ts_code, trade_date, start_date, end_date]):
            return "错误：至少提供一个筛选条件（ts_code/trade_date/start_date/end_date）"

        params = {k: v for k, v in {
            'ts_code': ts_code, 'trade_date': trade_date,
            'start_date': start_date, 'end_date': end_date, 'limit': limit,
        }.items() if v}
        pro = get_corpus_client()
        df = pro.anns_d(**params)
        log_debug(f"API returned: type={type(df).__name__}, empty={getattr(df, "empty", "N/A")}, shape={getattr(df, "shape", "N/A")}, columns={list(getattr(df, "columns", []))}")
        if df.empty:
            return "未找到符合条件的公告数据"

        result = [f"--- 上市公司公告 (Total: {len(df)}) ---"]
        display_cap = min(30, len(df))
        for _, row in df.head(display_cap).iterrows():
            parts = []
            if pd.notna(row.get('ann_date')): parts.append(f"日期:{row['ann_date']}")
            if pd.notna(row.get('ts_code')): parts.append(f"代码:{row['ts_code']}")
            if pd.notna(row.get('name')): parts.append(f"名称:{row['name']}")
            if pd.notna(row.get('title')): parts.append(f"标题:{row['title']}")
            result.append(" | ".join(parts))

        if len(df) > display_cap:
            result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
        return "\n".join(result)
