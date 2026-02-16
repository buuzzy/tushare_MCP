import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_cashflow_tools(mcp):
    @mcp.tool()
    @handle_exception
    def cashflow(ts_code: str = "", ann_date: str = "", f_ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", report_type: str = "", comp_type: str = "", 
               is_calc: int = None, limit: int = None, offset: int = None) -> str:
        """
        获取上市公司现金流量表数据。(对应 tushare cashflow 接口)

        参数:
            ts_code: 股票代码
            ann_date: 公告日期（YYYYMMDD格式）
            f_ann_date: 实际公告日期
            start_date: 公告日开始日期
            end_date: 公告日结束日期
            period: 报告期(每个季度最后一天的日期，比如20171231表示年报)
            report_type: 报告类型，参考文档说明 (1合并报表, 2单季合并, 3调整单季合并表, 4调整合并报表, 5调整前合并报表, 6母公司报表, 7母公司单季表, 8母公司调整单季表, 9母公司调整表, 10母公司调整前报表, 11母公司调整前合并报表, 12母公司调整前报表)
            comp_type: 公司类型（1一般工商业 2银行 3保险 4证券）
            is_calc: 是否计算报表
            limit: 单次返回数据长度
            offset: 请求数据的开始位移量
        """
        log_debug(f"Tool cashflow called with ts_code='{ts_code}', period='{period}'...")
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
            'is_calc': is_calc,
            'limit': limit,
            'offset': offset
        }
        # Filter out empty params
        api_params = {k: v for k, v in params.items() if v}
        
        # Explicit fields matching documentation desirable output
        fields = 'ts_code,ann_date,f_ann_date,end_date,comp_type,report_type,end_type,net_profit,finan_exp,c_fr_sale_sg,recp_tax_rends,n_depos_incr_fi,n_incr_loans_cb,n_inc_borr_oth_fi,prem_fr_orig_contr,n_incr_insured_dep,n_reinsur_prem,n_incr_disp_tfa,ifc_cash_incr,n_incr_disp_faas,n_incr_loans_oth_bank,n_cap_incr_repur,c_fr_oth_operate_a,c_inf_fr_operate_a,c_paid_goods_s,c_paid_to_for_empl,c_paid_for_taxes,n_incr_clt_loan_adv,n_incr_dep_cbob,c_pay_claims_orig_inco,pay_handling_chrg,pay_comm_insur_plcy,oth_cash_pay_oper_act,st_cash_out_act,n_cashflow_act,oth_recp_ral_inv_act,c_disp_withdrwl_invest,c_recp_return_invest,n_recp_disp_fiolta,n_recp_disp_sobu,stot_inflows_inv_act,c_pay_acq_const_fiolta,c_paid_invest,n_disp_subs_oth_biz,oth_pay_ral_inv_act,n_incr_pledge_loan,stot_out_inv_act,n_cashflow_inv_act,c_recp_borrow,proc_issue_bonds,oth_cash_recp_ral_fnc_act,stot_cash_in_fnc_act,free_cashflow,c_prepay_amt_borr,c_pay_dist_dpcp_int_exp,incl_dvd_profit_paid_sc_ms,oth_cashpay_ral_fnc_act,stot_cashout_fnc_act,n_cash_flows_fnc_act,eff_fx_flu_cash,n_incr_cash_cash_equ,c_cash_equ_beg_period,c_cash_equ_end_period,c_recp_cap_contrib,incl_cash_rec_saims,uncon_invest_loss,prov_depr_assets,depr_fa_coga_dpba,amort_intang_assets,lt_amort_deferred_exp,decr_deferred_exp,incr_acc_exp,loss_disp_fiolta,loss_scr_fa,loss_fv_chg,invest_loss,decr_def_inc_tax_assets,incr_def_inc_tax_liab,decr_inventories,decr_oper_payable,incr_oper_payable,others,im_net_cashflow_oper_act,conv_debt_into_cap,conv_copbonds_due_within_1y,fa_fnc_leases,im_n_incr_cash_equ,net_dism_capital_add,net_cash_rece_sec,credit_impa_loss,use_right_asset_dep,oth_loss_asset,end_bal_cash,beg_bal_cash,end_bal_cash_equ,beg_bal_cash_equ,update_flag'
        
        df = pro.cashflow(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的现金流量表数据"

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
            if pd.notna(row.get('net_profit')): info_parts.append(f"净利润: {format_money(row['net_profit'])}")
            if pd.notna(row.get('n_cashflow_act')): info_parts.append(f"经营净现金流: {format_money(row['n_cashflow_act'])}")
            if pd.notna(row.get('n_cashflow_inv_act')): info_parts.append(f"投资净现金流: {format_money(row['n_cashflow_inv_act'])}")
            if pd.notna(row.get('n_cash_flows_fnc_act')): info_parts.append(f"筹资净现金流: {format_money(row['n_cash_flows_fnc_act'])}")
            if pd.notna(row.get('n_incr_cash_cash_equ')): info_parts.append(f"现金净增: {format_money(row['n_incr_cash_cash_equ'])}")

            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        # Add a note about the full data
        result.append("\n(更多字段请在代码中查看 'fields' 列表)")

        return "\n".join(result)
