import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

def register_irm_qa_tools(mcp):
    @mcp.tool()
    @handle_exception
    def irm_qa(ts_code: str = '', trade_date: str = '', start_date: str = '',
               end_date: str = '', limit: int = 20, offset: int = 0) -> str:
        """
        获取上市公司董秘互动问答数据（上交所+深交所）。

        参数:
            ts_code: 股票代码（可选），如 600519.SH。不传则返回全市场最新问答
            trade_date: 问答日期 YYYYMMDD（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            limit: 返回条数上限，默认20
            offset: 分页位移量，默认0
        """
        log_debug(f"Tool irm_qa called: ts_code={ts_code}")
        pro = get_corpus_client()
        params = {key: value for key, value in {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset,
        }.items() if value}

        results = []
        for method_name in ['irm_qa_sh', 'irm_qa_sz']:
            try:
                method = getattr(pro, method_name, None)
                if method is None:
                    continue
                df = method(**params)
                df_type = type(df).__name__
                df_empty = getattr(df, "empty", "N/A")
                df_shape = getattr(df, "shape", "N/A")
                df_cols = list(getattr(df, "columns", []))
                log_debug(f"API returned: type={df_type}, empty={df_empty}, shape={df_shape}, columns={df_cols}")
                if not df.empty:
                    results.append(f"--- {method_name} ({len(df)} 条) ---")
                    for _, row in df.head(10).iterrows():
                        parts = []
                        if pd.notna(row.get('ts_code')): parts.append(f"代码:{row['ts_code']}")
                        if pd.notna(row.get('name')): parts.append(f"名称:{row['name']}")
                        if pd.notna(row.get('trade_date')): parts.append(f"日期:{row['trade_date']}")
                        q = str(row.get('q', ''))[:100]
                        a = str(row.get('a', ''))[:200]
                        parts.append(f"问:{q}")
                        parts.append(f"答:{a}")
                        results.append(" | ".join(parts))
            except Exception as e:
                log_debug(f"irm_qa {method_name} failed: {e}")
                continue

        if not results:
            return "未找到董秘问答数据"
        return "\n".join(results)
