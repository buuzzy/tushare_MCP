import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fina_mainbz_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fina_mainbz(ts_code: str = "", period: str = "", type: str = "P", 
               start_date: str = "", end_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取上市公司主营业务构成，分地区和产品两种方式。(对应 tushare fina_mainbz 接口)

        参数:
            ts_code: 股票代码
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            type: 类型：P按产品 D按地区 I按行业（请输入大写字母P或者D）。默认为P。
            start_date: 报告期开始日期
            end_date: 报告期结束日期
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fina_mainbz called with ts_code='{ts_code}', period='{period}', type='{type}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'period': period,
            'type': type,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params, but keep default type='P' if not overridden, 
        # though user passes it. API defaults to P if empty? Doc says nullable.
        # Let's keep what user passed if not empty.
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,end_date,bz_item,bz_sales,bz_profit,bz_cost,curr_type'
        
        df = pro.fina_mainbz(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的主营业务构成数据"

        # The data structure is usually multiple rows per report period (one per product/region)
        # We should group by end_date if multiple periods are returned, or just list them.
        
        result = [f"--- size: {len(df)} ---"]
        
        # Display cap
        display_cap = 50 # Main biz items can be numerous per report, so higher cap
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

        # Basic grouping by period for better readability if ts_code is single
        # If multiple ts_codes (unlikely given API usually one at a time or VIP), we can just list.
        # Tushare interface for this usually requires ts_code.
        
        current_period = None
        
        for _, row in display_df.iterrows():
            period = row.get('end_date')
            if period != current_period:
                if current_period is not None:
                     result.append("---")
                result.append(f"报告期: {period} | 代码: {row.get('ts_code')} | 类型: {type}")
                current_period = period
            
            item_parts = []
            if pd.notna(row.get('bz_item')): item_parts.append(f"项目: {row['bz_item']}")
            if pd.notna(row.get('bz_sales')): item_parts.append(f"收入: {format_money(row['bz_sales'])}")
            if pd.notna(row.get('bz_profit')): item_parts.append(f"利润: {format_money(row['bz_profit'])}")
            if pd.notna(row.get('bz_cost')): item_parts.append(f"成本: {format_money(row['bz_cost'])}")
            
            result.append("  " + " | ".join(item_parts))
            
        result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
