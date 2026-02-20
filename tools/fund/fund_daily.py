import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_daily_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_daily(ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取ETF/基金日线行情收盘数据。
        
        参数:
            ts_code: 基金代码 (必填, e.g. 510330.SH)
            trade_date: 交易日期 (YYYYMMDD)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            limit: 单次返回数据长度（最大2000行）
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_daily called with ts_code='{ts_code}', trade_date='{trade_date}'...")
        
        # Clean inputs
        if ts_code:
            ts_code = ts_code.replace(" ", "")
            
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
            'offset': offset
        }
        api_params = {k: v for k, v in params.items() if v}
        
        fields = 'ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_daily(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_daily(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的ETF/基金日线行情数据"

        # Tushare typically returns data sorted by date descending.
        # Ensure it's sorted by trade_date descending just in case.
        if 'trade_date' in df.columns:
            df = df.sort_values(by='trade_date', ascending=False)

        result = [f"--- size: {len(df)} ---"]
        display_cap = 50
        display_df = df.head(display_cap)
        
        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('trade_date')): info_parts.append(f"日期: {row['trade_date']}")
            if pd.notna(row.get('close')): info_parts.append(f"收: {row['close']}")
            if pd.notna(row.get('open')): info_parts.append(f"开: {row['open']}")
            if pd.notna(row.get('high')): info_parts.append(f"高: {row['high']}")
            if pd.notna(row.get('low')): info_parts.append(f"低: {row['low']}")
            if pd.notna(row.get('pct_chg')): info_parts.append(f"涨跌幅: {row['pct_chg']}%")
            if pd.notna(row.get('vol')): info_parts.append(f"量: {row['vol']}")
            if pd.notna(row.get('amount')): info_parts.append(f"额: {row['amount']}")
            
            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)
