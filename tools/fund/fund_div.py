import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_fund_div_tools(mcp):
    @mcp.tool()
    @handle_exception
    def fund_div(ann_date: str = "", ex_date: str = "", pay_date: str = "", ts_code: str = "", limit: int = None, offset: int = None) -> str:
        """
        获取公募基金分红数据。
        
        参数:
            ann_date: 公告日 (以下参数四选一)
            ex_date: 除息日
            pay_date: 派息日
            ts_code: 基金代码
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool fund_div called with ts_code='{ts_code}', ann_date='{ann_date}'...")
        pro = get_pro_client()
        
        # Construct API parameters
        api_params = {
            "ann_date": ann_date,
            "ex_date": ex_date,
            "pay_date": pay_date,
            "ts_code": ts_code,
            "limit": limit,
            "offset": offset
        }
        
        # Filter out empty parameters
        api_params = {k: v for k, v in api_params.items() if v is not None and v != ""}
        
        fields = 'ts_code,ann_date,imp_anndate,base_date,div_proc,record_date,ex_date,pay_date,earpay_date,net_ex_date,div_cash,base_unit,ear_distr,ear_amount,account_date,base_year'
        
        if ts_code and ',' in ts_code:
            code_list = [c.strip() for c in ts_code.split(',') if c.strip()]
            df_list = []
            for code in code_list:
                api_params['ts_code'] = code
                temp_df = pro.fund_div(**api_params, fields=fields)
                if not temp_df.empty:
                    df_list.append(temp_df)
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
            else:
                df = pd.DataFrame()
        else:
            df = pro.fund_div(**api_params, fields=fields)
        
        if df.empty:
            return "未找到符合条件的基金分红数据"

        # Format output
        result = [f"--- size: {len(df)} ---"]
        
        # Sort by ann_date descending (newest first)
        if 'ann_date' in df.columns:
            df = df.sort_values(by='ann_date', ascending=False)
            
        display_cap = 50
        
        # Smart Truncation Logic
        if not limit and len(df) > display_cap:
            head_df = df.head(45)
            tail_df = df.tail(5)
            
            for _, row in head_df.iterrows():
                result.append(format_row(row))
            
            result.append(f"... (中间省略 {len(df) - 50} 条数据) ...")
            
            for _, row in tail_df.iterrows():
                result.append(format_row(row))
        else:
            if limit:
                display_df = df.head(limit)
            else:
                display_df = df.head(display_cap)
            
            for _, row in display_df.iterrows():
                result.append(format_row(row))
                
            if limit and len(df) > limit:
                 result.append(f"... (共 {len(df)} 条，仅显示前 {limit} 条)")
            elif not limit and len(df) > display_cap:
                 result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        return "\n".join(result)

def format_row(row) -> str:
    info_parts = []
    if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
    if pd.notna(row.get('ann_date')): info_parts.append(f"公告: {row['ann_date']}")
    if pd.notna(row.get('ex_date')): info_parts.append(f"除息: {row['ex_date']}")
    if pd.notna(row.get('pay_date')): info_parts.append(f"派息: {row['pay_date']}")
    
    if pd.notna(row.get('div_cash')): info_parts.append(f"每股派息: {row['div_cash']}元")
    if pd.notna(row.get('ear_distr')): info_parts.append(f"可分配: {row['ear_distr']}")
    if pd.notna(row.get('div_proc')): info_parts.append(f"进度: {row['div_proc']}")
    
    return " | ".join(info_parts)
