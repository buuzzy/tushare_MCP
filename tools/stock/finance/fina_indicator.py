import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fina_indicator_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fina_indicator(ts_code: str = "", ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取上市公司财务指标数据。(对应 tushare fina_indicator 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            start_date: 报告期开始日期
            end_date: 报告期结束日期
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fina_indicator called with ts_code='{ts_code}', period='{period}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'ann_date': ann_date,
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,ann_date,end_date,eps,dt_eps,revenue_ps,bps,roe,netprofit_margin,grossprofit_margin,debt_to_assets,current_ratio,q_profit_yoy,q_sales_yoy,ocfps,extra_item,profit_dedt'
        
        df = pro.fina_indicator(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的财务指标数据"

        result = [f"--- size: {len(df)} ---"]
        
        # Display cap
        display_cap = 20
        # If user explicitly set a limit that is smaller, use that.
        if limit and limit < display_cap:
             display_cap = limit
             
        display_df = df.head(display_cap)
        
        def format_pct(val):
             if pd.isna(val):
                 return ""
             return f"{val:.2f}%"

        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"报告期: {row['end_date']}")
            
            # Basic Per Share
            ps = []
            if pd.notna(row.get('eps')): ps.append(f"EPS:{row['eps']}")
            if pd.notna(row.get('bps')): ps.append(f"BPS:{row['bps']}")
            if pd.notna(row.get('ocfps')): ps.append(f"OCFPS:{row['ocfps']}")
            if ps: info_parts.append(" | ".join(ps))

            # Profitability
            prof = []
            if pd.notna(row.get('roe')): prof.append(f"ROE:{format_pct(row['roe'])}")
            if pd.notna(row.get('grossprofit_margin')): prof.append(f"毛利:{format_pct(row['grossprofit_margin'])}")
            if pd.notna(row.get('netprofit_margin')): prof.append(f"净利:{format_pct(row['netprofit_margin'])}")
            if prof: info_parts.append(" | ".join(prof))
            
            # Solvency & Growth
            other = []
            if pd.notna(row.get('debt_to_assets')): other.append(f"负债率:{format_pct(row['debt_to_assets'])}")
            if pd.notna(row.get('q_sales_yoy')): other.append(f"营收同比(单季):{format_pct(row['q_sales_yoy'])}")
            if pd.notna(row.get('q_profit_yoy')): other.append(f"净利同比(单季):{format_pct(row['q_profit_yoy'])}")
            if other: info_parts.append(" | ".join(other))

            result.append("\n".join(info_parts))
            result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
