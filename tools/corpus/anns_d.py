import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_anns_d_tools(mcp):
    @mcp.tool()
    @handle_exception
    def anns_d(ts_code: str = '', ann_date: str = '', start_date: str = '', end_date: str = '',
               limit: int = 50) -> str:
        """
        获取上市公司公告列表（含标题与详情链接）。数据自2023年起，实时更新。

        注意：此接口返回公告标题和详情页链接，不含公告全文。
        获取后请将链接提供给用户以便查看原文。

        参数:
            ts_code: 股票代码（可选），如 600519.SH
            ann_date: 公告日期 YYYYMMDD（可选），按该日拉取全市场公告
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            limit: 返回条数上限，默认50，最大2000
        """
        log_debug(f"Tool anns_d called: ts_code={ts_code}, ann_date={ann_date}")
        if not any([ts_code, ann_date, start_date, end_date]):
            return "错误：至少提供一个筛选条件（ts_code/ann_date/start_date/end_date）"

        params = {k: v for k, v in {
            'ts_code': ts_code, 'ann_date': ann_date,
            'start_date': start_date, 'end_date': end_date, 'limit': limit,
        }.items() if v}
        pro = get_corpus_client()
        df = pro.anns_d(**params)
        log_debug(f"anns_d API returned: type={type(df).__name__}, empty={getattr(df, 'empty', 'N/A')}, shape={getattr(df, 'shape', 'N/A')}, columns={list(getattr(df, 'columns', []))}")
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
            if pd.notna(row.get('url')): parts.append(f"链接:{row['url']}")
            result.append(" | ".join(parts))

        if len(df) > display_cap:
            result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
        output = "\n".join(result)
        log_debug(f"anns_d RETURNING: len={len(output)}, content={output[:500]}")
        return output
