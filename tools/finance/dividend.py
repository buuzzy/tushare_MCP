import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_dividend_tools(mcp):
    @mcp.tool()
    @handle_exception
    def dividend(ts_code: str = "", ann_date: str = "", record_date: str = "", 
               ex_date: str = "", imp_ann_date: str = "", 
               limit: int = None, offset: int = None) -> str:
        """
        获取上市公司分红送股数据。(对应 tushare dividend 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            record_date: 股权登记日期
            ex_date: 除权除息日
            imp_ann_date: 实施公告日
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool dividend called with ts_code='{ts_code}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'ann_date': ann_date,
            'record_date': record_date,
            'ex_date': ex_date,
            'imp_ann_date': imp_ann_date,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,imp_ann_date,base_date,base_share'
        
        df = pro.dividend(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的分红送股数据"

        result = [f"--- size: {len(df)} ---"]
        
        # Display cap
        display_cap = 20
        # If user explicitly set a limit that is smaller, use that.
        if limit and limit < display_cap:
             display_cap = limit
             
        display_df = df.head(display_cap)

        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"分红年度: {row['end_date']}")
            if pd.notna(row.get('div_proc')): info_parts.append(f"进度: {row['div_proc']}")
            
            # Cash dividend
            cash = ""
            if pd.notna(row.get('cash_div_tax')) and row['cash_div_tax'] > 0:
                 cash = f"{row['cash_div_tax']}元"
            elif pd.notna(row.get('cash_div')) and row['cash_div'] > 0:
                 cash = f"{row['cash_div']}元(税后)"
            
            if cash: info_parts.append(f"每股派息(税前): {cash}")

            # Stock dividend
            stk = []
            if pd.notna(row.get('stk_div')) and row['stk_div'] > 0: stk.append(f"送{row['stk_div']}")
            if pd.notna(row.get('stk_bo_rate')) and row['stk_bo_rate'] > 0: stk.append(f"送{row['stk_bo_rate']}")
            if pd.notna(row.get('stk_co_rate')) and row['stk_co_rate'] > 0: stk.append(f"转{row['stk_co_rate']}")
            
            if stk: info_parts.append(f"送转: {','.join(stk)}")

            # Key Dates
            dates = []
            if pd.notna(row.get('ann_date')): dates.append(f"公告: {row['ann_date']}")
            if pd.notna(row.get('record_date')): dates.append(f"登记: {row['record_date']}")
            if pd.notna(row.get('ex_date')): dates.append(f"除除: {row['ex_date']}")
            if pd.notna(row.get('pay_date')): dates.append(f"派息: {row['pay_date']}")
            
            if dates:
                dates_str = " | ".join(dates)
                # If dates string is long, put it on a new line or just append if short
                if len(info_parts) > 2:
                     result.append(" | ".join(info_parts))
                     result.append(f"  日期: {dates_str}")
                     result.append("---")
                     continue
                else:
                     info_parts.append(dates_str)

            result.append(" | ".join(info_parts))
            result.append("---")
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
