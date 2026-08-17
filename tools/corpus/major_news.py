import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_major_news_tools(mcp):
    @mcp.tool()
    @handle_exception
    def major_news(start_date: str, end_date: str, limit: int = 500, offset: int = 0) -> str:
        """
        获取重大新闻数据（含标题、正文、来源、链接）。支持按时间范围筛选。

        参数:
            start_date: 开始时间，格式 YYYY-MM-DD HH:mm:ss（必填）
            end_date: 结束时间，格式 YYYY-MM-DD HH:mm:ss（必填）
            limit: 单次返回条数上限，默认500
            offset: 跳过前 offset 条，用于分页
        """
        log_debug(f"Tool major_news called: start={start_date}, end={end_date}")
        pro = get_corpus_client()
        df = pro.major_news(start_date=start_date, end_date=end_date, limit=limit, offset=offset)
        df_type = type(df).__name__
        df_empty = getattr(df, "empty", "N/A")
        df_shape = getattr(df, "shape", "N/A")
        df_cols = list(getattr(df, "columns", []))
        log_debug(f"API returned: type={df_type}, empty={df_empty}, shape={df_shape}, columns={df_cols}")
        if df.empty:
            return "未找到符合条件的重大新闻数据"

        result = [f"--- 重大新闻 (Total: {len(df)}) ---"]
        display_cap = min(30, len(df))
        for _, row in df.head(display_cap).iterrows():
            title = row.get('title', '')
            pub_time = row.get('pub_time', '')
            news_src = row.get('src', '')
            content = str(row.get('content', ''))[:300]
            result.append(f"[{pub_time}] {title} ({news_src})\n  {content}")

        if len(df) > display_cap:
            result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
        return "\n".join(result)
