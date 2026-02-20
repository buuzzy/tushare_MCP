import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_income_tools(mcp):
    @mcp.tool()
    @handle_exception
    def income(ts_code: str = "", ann_date: str = "", f_ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", report_type: str = "", comp_type: str = "", 
               limit: int = None, offset: int = None) -> str:
        """
        获取上市公司财务利润表数据。(对应 tushare income 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            f_ann_date: 实际公告日期
            start_date: 公告日开始日期
            end_date: 公告日结束日期
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            report_type: 报告类型，参考文档说明 (1合并报表, 2单季合并, 3调整单季合并表, 4调整合并报表, 5调整前合并报表, 6母公司报表, 7母公司单季表, 8母公司调整单季表, 9母公司调整表, 10母公司调整前报表, 11母公司调整前合并报表, 12母公司调整前报表)
            comp_type: 公司类型（1一般工商业 2银行 3保险 4证券）
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool income called with ts_code='{ts_code}', period='{period}'...")
        pro = get_pro_client()
        params = {
            'ts_code': ts_code,
            'ann_date': ann_date,
            'f_ann_date': f_ann_date,
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'report_type': report_type,
            'comp_type': comp_type,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,basic_eps,diluted_eps,total_revenue,revenue,int_income,prem_earned,comm_income,n_commis_income,n_oth_income,n_oth_b_income,prem_income,out_prem,une_prem_reser,reins_income,n_sec_tb_income,n_sec_uw_income,n_asset_mg_income,oth_b_income,fv_value_chg_gain,invest_income,ass_invest_income,forex_gain,total_cogs,oper_cost,int_exp,comm_exp,biz_tax_surchg,sell_exp,admin_exp,fin_exp,assets_impair_loss,prem_refund,compens_payout,reser_insur_liab,div_payt,reins_exp,oper_exp,compens_payout_refu,insur_reser_refu,reins_cost_refund,other_bus_cost,operate_profit,non_oper_income,non_oper_exp,nca_disploss,total_profit,income_tax,n_income,n_income_attr_p,minority_gain,oth_compr_income,t_compr_income,compr_inc_attr_p,compr_inc_attr_m_s,ebit,ebitda,insurance_exp,undist_profit,distable_profit,rd_exp,fin_exp_int_exp,fin_exp_int_inc,transfer_surplus_rese,transfer_housing_imprest,transfer_oth,adj_lossgain,withdra_legal_surplus,withdra_legal_pubfund,withdra_biz_devfund,withdra_rese_fund,withdra_oth_ersu,workers_welfare,distr_profit_shrhder,prfshare_payable_dvd,comshare_payable_dvd,capit_comstock_div,net_after_nr_lp_correct,credit_impa_loss,net_expo_hedging_benefits,oth_impair_loss_assets,total_opcost,amodcost_fin_assets,oth_income,asset_disp_income,continued_net_profit,end_net_profit,update_flag'
        
        df = pro.income(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的利润表数据"

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

        REPORT_TYPE_MAP = {
            '1': '合并报表', '2': '单季合并', '3': '调整单季合并表', '4': '调整合并报表',
            '5': '调整前合并报表', '6': '母公司报表', '7': '母公司单季表', '8': '母公司调整单季表',
            '9': '母公司调整表', '10': '母公司调整前报表', '11': '母公司调整前合并报表', '12': '母公司调整前报表'
        }

        for _, row in display_df.iterrows():
            info_parts = []
            if pd.notna(row.get('ts_code')): info_parts.append(f"代码: {row['ts_code']}")
            if pd.notna(row.get('end_date')): info_parts.append(f"报告期: {row['end_date']}")
            
            r_type = str(row['report_type']) if pd.notna(row.get('report_type')) else ""
            if r_type:
                r_type_str = REPORT_TYPE_MAP.get(r_type, r_type)
                info_parts.append(f"类型: {r_type_str}")
            
            # Add some key financial metrics for quick view
            if pd.notna(row.get('basic_eps')): info_parts.append(f"EPS: {row['basic_eps']}")
            if pd.notna(row.get('total_revenue')): info_parts.append(f"营收: {format_money(row['total_revenue'])}")
            if pd.notna(row.get('n_income')): info_parts.append(f"净利: {format_money(row['n_income'])}")
            if pd.notna(row.get('n_income_attr_p')): info_parts.append(f"归母净利: {format_money(row['n_income_attr_p'])}")

            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        # Add a note about the full data
        result.append("\n(更多字段请在代码中查看 'fields' 列表)")

        return "\n".join(result)
