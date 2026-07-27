import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_cctv_news_tools(mcp):
    @mcp.tool()
    @handle_exception
    def cctv_news(date: str = '', limit: int = 100) -> str:
        """
        获取央视新闻联播文字稿数据。

        参数:
            date: 日期，格式 YYYYMMDD（必填），如 20260725
            limit: 单次返回条数上限，默认100
        """
        log_debug(f"Tool cctv_news called: date={date}")
        if not date:
            return "错误：必须提供 date 参数（格式：YYYYMMDD）"

        pro = get_corpus_client()
        df = pro.cctv_news(date=date, limit=limit)
        if df.empty:
            return "未找到该日期的央视新闻联播数据"

        result = [f"--- 央视新闻联播 {date} (Total: {len(df)}) ---"]
        for _, row in df.head(50).iterrows():
            d = row.get('date', '')
            title = row.get('title', '')
            content = str(row.get('content', ''))[:200]
            result.append(f"[{d}] {title}\n  {content}")
        return "\n".join(result)
