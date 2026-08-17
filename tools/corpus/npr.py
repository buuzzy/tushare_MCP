import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_npr_tools(mcp):
    @mcp.tool()
    @handle_exception
    def npr(org: str = '', start_date: str = '', end_date: str = '',
            ptype: str = '', limit: int = 30) -> str:
        """
        获取政策法规数据（国家各部委发布的政策文件）。

        参数:
            org: 发布机构（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            ptype: 政策类型（可选）
            limit: 返回条数上限，默认30
        """
        log_debug(f"Tool npr called: limit={limit}")
        pro = get_corpus_client()
        api_params = {key: value for key, value in {
            'org': org,
            'start_date': start_date,
            'end_date': end_date,
            'ptype': ptype,
            'limit': limit,
        }.items() if value}
        df = pro.npr(**api_params)
        df_type = type(df).__name__
        df_empty = getattr(df, "empty", "N/A")
        df_shape = getattr(df, "shape", "N/A")
        df_cols = list(getattr(df, "columns", []))
        log_debug(f"API returned: type={df_type}, empty={df_empty}, shape={df_shape}, columns={df_cols}")
        if df.empty:
            return "未找到政策法规数据"

        result = [f"--- 政策法规 (Total: {len(df)}) ---"]
        for _, row in df.head(30).iterrows():
            parts = []
            if pd.notna(row.get('pubtime')): parts.append(f"时间:{row['pubtime']}")
            if pd.notna(row.get('title')): parts.append(f"标题:{row['title']}")
            if pd.notna(row.get('puborg')): parts.append(f"机构:{row['puborg']}")
            if pd.notna(row.get('ptype')): parts.append(f"类型:{row['ptype']}")
            result.append(" | ".join(parts))
        return "\n".join(result)
