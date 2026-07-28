import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fina_indicator_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fina_indicator(ts_code: str = "", ann_date: str = "", start_date: str = "",
               end_date: str = "", period: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取上市公司财务指标数据（含ROE、毛利率、净利率、资产负债率、流动比率、速动比率等）。
        默认返回最近12期（3年），适合趋势分析。

        参数:
            ts_code: 股票代码
            period: 报告期（精确匹配，指定后只返回该期单条）。趋势分析时请省略此参数
            start_date / end_date: 报告期日期范围
            limit: 返回条数，默认12（近3年）。趋势分析请直接设置更大值，而非逐期调用
            offset: 位移量

        用法:
            - 多期趋势: fina_indicator(ts_code="300760.SZ", limit=12)
            - 查单期: fina_indicator(ts_code="300760.SZ", period="20251231")
        """
        log_debug(f"Tool fina_indicator called with ts_code='{ts_code}', period='{period}'...")
        pro = get_pro_client()

        # Default to 12 periods (3 years) when no limit specified
        effective_limit = limit if limit else 12
        if period and limit:
            return ("参数冲突：period（精确匹配单期）和 limit（多期趋势）不应同时使用。"
                    f"趋势分析请省略 period，例如：fina_indicator(ts_code=..., limit=12)；"
                    f"查单期请省略 limit，例如：fina_indicator(ts_code=..., period=\"20251231\")")
        params = {
            'ts_code': ts_code,
            'ann_date': ann_date,
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'limit': effective_limit,
            'offset': offset
        }
        api_params = {k: v for k, v in params.items() if v}

        fields = 'ts_code,ann_date,end_date,eps,dt_eps,revenue_ps,bps,roe,netprofit_margin,grossprofit_margin,debt_to_assets,currentratio,quickratio,q_profit_yoy,q_sales_yoy,ocfps,extra_item,profit_dedt'

        df = pro.fina_indicator(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的财务指标数据"

        # Reverse to chronological order (oldest first) for trend charts
        df = df.iloc[::-1].reset_index(drop=True)

        result = [f"--- 财务指标 (共 {len(df)} 期) ---"]

        def fmt(val, suffix="%"):
            if pd.isna(val):
                return "N/A"
            return f"{val:.2f}{suffix}"

        for _, row in df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"报告期: {row['end_date']}")

            ps = []
            if pd.notna(row.get('eps')): ps.append(f"EPS:{row['eps']}")
            if pd.notna(row.get('bps')): ps.append(f"BPS:{row['bps']}")
            if ps: info_parts.append(" | ".join(ps))

            prof = []
            if pd.notna(row.get('roe')): prof.append(f"ROE:{fmt(row['roe'])}")
            if pd.notna(row.get('grossprofit_margin')): prof.append(f"毛利率:{fmt(row['grossprofit_margin'])}")
            if pd.notna(row.get('netprofit_margin')): prof.append(f"净利率:{fmt(row['netprofit_margin'])}")
            if prof: info_parts.append(" | ".join(prof))

            other = []
            if pd.notna(row.get('debt_to_assets')): other.append(f"资产负债率:{fmt(row['debt_to_assets'])}")
            if pd.notna(row.get('currentratio')): other.append(f"流动比率:{row['currentratio']:.2f}")
            if pd.notna(row.get('quickratio')): other.append(f"速动比率:{row['quickratio']:.2f}")
            if pd.notna(row.get('q_sales_yoy')): other.append(f"营收同比(单季):{fmt(row['q_sales_yoy'])}")
            if pd.notna(row.get('q_profit_yoy')): other.append(f"净利同比(单季):{fmt(row['q_profit_yoy'])}")
            if other: info_parts.append(" | ".join(other))

            result.append("\n".join(info_parts))

        return "\n---\n".join(result)
