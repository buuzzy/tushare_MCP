import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fina_audit_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fina_audit(ts_code: str = "", ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取上市公司定期财务审计意见数据。(对应 tushare fina_audit 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            start_date: 公告开始日期
            end_date: 公告结束日期
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fina_audit called with ts_code='{ts_code}', period='{period}'...")
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
        fields = 'ts_code,ann_date,end_date,audit_result,audit_fees,audit_agency,audit_sign'
        
        df = pro.fina_audit(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的财务审计意见数据"

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
            if pd.notna(row.get('audit_result')): info_parts.append(f"结果: {row['audit_result']}")
            
            # Audit Details
            details = []
            if pd.notna(row.get('audit_agency')): details.append(f"机构: {row['audit_agency']}")
            if pd.notna(row.get('audit_sign')): details.append(f"签字: {row['audit_sign']}")
            if pd.notna(row.get('audit_fees')): details.append(f"费用: {format_money(row['audit_fees'])}")
            
            if details: info_parts.append(" | ".join(details))

            if pd.notna(row.get('ann_date')): info_parts.append(f"公告: {row['ann_date']}")

            result.append("\n".join(info_parts))
            result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
