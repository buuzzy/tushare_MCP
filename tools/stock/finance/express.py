import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_express_tools(mcp):
    @mcp.tool()
    @handle_exception
    def express(ts_code: str = "", ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取上市公司业绩快报数据。(对应 tushare express 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            start_date: 公告日开始日期
            end_date: 公告日结束日期
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool express called with ts_code='{ts_code}', period='{period}'...")
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
        fields = 'ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,bps,yoy_sales,yoy_op,yoy_tp,yoy_dedu_np,yoy_eps,yoy_roe,growth_assets,yoy_equity,growth_bps,or_last_year,op_last_year,tp_last_year,np_last_year,eps_last_year,open_net_assets,open_bps,perf_summary,is_audit,remark'
        
        df = pro.express(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的业绩快报数据"

        result = [f"--- size: {len(df)} ---"]
        
        # Display cap
        display_cap = 20
        # If user explicitly set a limit that is smaller, use that.
        if limit and limit < display_cap:
             display_cap = limit
             
        display_df = df.head(display_cap)
        
        def format_money(val):
            if pd.isna(val):
                return ""
            try:
                val_float = float(val)
                if abs(val_float) > 1e8:
                    return f"{val_float/1e8:.2f}亿"
                elif abs(val_float) > 1e4:
                    return f"{val_float/1e4:.2f}万"
                return str(val)
            except:
                return str(val)

        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"报告期: {row['end_date']}")
            
            # Key financial metrics
            if pd.notna(row.get('revenue')): info_parts.append(f"营收: {format_money(row['revenue'])}")
            if pd.notna(row.get('n_income')): info_parts.append(f"净利: {format_money(row['n_income'])}")
            if pd.notna(row.get('total_assets')): info_parts.append(f"总资产: {format_money(row['total_assets'])}")
            if pd.notna(row.get('total_hldr_eqy_exc_min_int')): info_parts.append(f"股东权益: {format_money(row['total_hldr_eqy_exc_min_int'])}")

            # Growth metrics
            if pd.notna(row.get('yoy_sales')): info_parts.append(f"营收同比: {row['yoy_sales']}%")
            if pd.notna(row.get('yoy_dedu_np')): info_parts.append(f"扣非净利同比: {row['yoy_dedu_np']}%")

            result.append(" | ".join(info_parts))
            
            # Summary
            if pd.notna(row.get('perf_summary')):
                result.append(f"  摘要: {row['perf_summary']}")
            if pd.notna(row.get('remark')):
                result.append(f"  备注: {row['remark']}")
            
            result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
