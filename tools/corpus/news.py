import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_news_tools(mcp):
    @mcp.tool()
    @handle_exception
    def news(start_date: str = '', end_date: str = '', src: str = '', limit: int = 500, offset: int = 0) -> str:
        """
        获取财经新闻快讯数据。支持按来源和时间范围筛选。

        参数:
            start_date: 开始时间，格式 YYYY-MM-DD HH:mm:ss（必填）
            end_date: 结束时间，格式 YYYY-MM-DD HH:mm:ss（必填）
            src: 新闻来源（可选）：sina-新浪, wallstreetcn-华尔街见闻, 10jqka-同花顺, cls-财联社, eastmoney-东方财富
            limit: 单次返回条数上限，默认500，最大1500
            offset: 跳过前 offset 条，用于分页
        """
        log_debug(f"Tool news called: start={start_date}, end={end_date}, src={src}")
        if not start_date or not end_date:
            return "错误：必须提供 start_date 和 end_date 参数（格式：YYYY-MM-DD HH:mm:ss）"

        pro = get_corpus_client()
        params = {'start_date': start_date, 'end_date': end_date, 'limit': limit, 'offset': offset}
        if src:
            params['src'] = src

        df = pro.news(**params)
        log_debug(f"API returned: type={type(df).__name__}, empty={getattr(df, "empty", "N/A")}, shape={getattr(df, "shape", "N/A")}, columns={list(getattr(df, "columns", []))}")
        if df.empty:
            return "未找到符合条件的新闻数据"

        result = [f"--- 新闻快讯 (Total: {len(df)}) ---"]
        display_cap = min(50, len(df))
        for _, row in df.head(display_cap).iterrows():
            dt = row.get('datetime', '')
            content = str(row.get('content', ''))[:200]
            result.append(f"[{dt}] {content}")

        if len(df) > display_cap:
            result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
        return "\n".join(result)
