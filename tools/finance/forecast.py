import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_forecast_tools(mcp):
    @mcp.tool()
    @handle_exception
    def forecast(ts_code: str = "", ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", type: str = "", 
               limit: int = None, offset: int = None) -> str:
        """
        获取上市公司业绩预告数据。(对应 tushare forecast 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            start_date: 公告日开始日期
            end_date: 公告日结束日期
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            type: 预告类型(预增/预减/扭亏/首亏/续亏/续盈/略增/略减)
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool forecast called with ts_code='{ts_code}', period='{period}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'ann_date': ann_date,
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'type': type,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,first_ann_date,summary,change_reason'
        
        df = pro.forecast(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的业绩预告数据"

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
            if pd.notna(row.get('type')): info_parts.append(f"类型: {row['type']}")
            
            # Profit change range
            p_change = ""
            if pd.notna(row.get('p_change_min')): p_change += f"{row['p_change_min']}%"
            if pd.notna(row.get('p_change_max')): 
                if p_change: p_change += f" ~ {row['p_change_max']}%"
                else: p_change = f"{row['p_change_max']}%"
            if p_change: info_parts.append(f"变动幅度: {p_change}")

            # Net profit range (Original is in 万元, convert to Yuan for formatter if needed, or handle directly)
            # Strategy: Convert '万元' to base unit (float) then pass to format_money.
            # 1 万元 = 10000
            
            n_profit = ""
            n_min = row.get('net_profit_min')
            n_max = row.get('net_profit_max')
            
            formatted_min = ""
            if pd.notna(n_min):
                formatted_min = format_money(float(n_min) * 10000)
            
            formatted_max = ""
            if pd.notna(n_max):
                formatted_max = format_money(float(n_max) * 10000)
                
            if formatted_min: n_profit += formatted_min
            if formatted_max:
                if n_profit: n_profit += f" ~ {formatted_max}"
                else: n_profit = formatted_max
            
            if n_profit: info_parts.append(f"预告净利: {n_profit}")
            
            # Last year
            if pd.notna(row.get('last_parent_net')):
                 info_parts.append(f"上年同期: {format_money(float(row['last_parent_net']) * 10000)}")

            result.append(" | ".join(info_parts))
            
            # Summary often contains important text, add it on a new line if present
            if pd.notna(row.get('summary')):
                result.append(f"  摘要: {row['summary']}")
            if pd.notna(row.get('change_reason')):
                result.append(f"  原因: {row['change_reason']}")
                
            result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
