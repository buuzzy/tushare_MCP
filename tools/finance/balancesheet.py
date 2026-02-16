import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_balancesheet_tools(mcp):
    @mcp.tool()
    @handle_exception
    def balancesheet(ts_code: str = "", ann_date: str = "", f_ann_date: str = "", start_date: str = "", 
               end_date: str = "", period: str = "", report_type: str = "", comp_type: str = "", 
               limit: int = None, offset: int = None) -> str:
        """
        获取上市公司资产负债表数据。(对应 tushare balancesheet 接口)

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
        log_debug(f"Tool balancesheet called with ts_code='{ts_code}', period='{period}'...")
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
        fields = 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,end_type,total_share,cap_rese,undistr_porfit,surplus_rese,special_rese,money_cap,trad_asset,notes_receiv,accounts_receiv,oth_receiv,prepayment,div_receiv,int_receiv,inventories,amor_exp,nca_within_1y,sett_rsrv,loanto_oth_bank_fi,premium_receiv,reinsur_receiv,reinsur_res_receiv,pur_resale_fa,oth_cur_assets,total_cur_assets,fa_avail_for_sale,htm_invest,lt_eqt_invest,invest_real_estate,time_deposits,oth_assets,lt_rec,fix_assets,cip,const_materials,fixed_assets_disp,produc_bio_assets,oil_and_gas_assets,intan_assets,r_and_d,goodwill,lt_amor_exp,defer_tax_assets,decr_in_disbur,oth_nca,total_nca,cash_reser_cb,depos_in_oth_bfi,prec_metals,deriv_assets,rr_reins_une_prem,rr_reins_outstd_cla,rr_reins_lins_liab,rr_reins_lthins_liab,refund_depos,ph_pledge_loans,refund_cap_depos,indep_acct_assets,client_depos,client_prov,transac_seat_fee,invest_as_receiv,total_assets,lt_borr,st_borr,cb_borr,depos_ib_deposits,loan_oth_bank,trading_fl,notes_payable,acct_payable,adv_receipts,sold_for_repur_fa,comm_payable,payroll_payable,taxes_payable,int_payable,div_payable,oth_payable,acc_exp,deferred_inc,st_bonds_payable,payable_to_reinsurer,rsrv_insur_cont,acting_trading_sec,acting_uw_sec,non_cur_liab_due_1y,oth_cur_liab,total_cur_liab,bond_payable,lt_payable,specific_payables,estimated_liab,defer_tax_liab,defer_inc_non_cur_liab,oth_ncl,total_ncl,depos_oth_bfi,deriv_liab,depos,agency_bus_liab,oth_liab,prem_receiv_adva,depos_received,ph_invest,reser_une_prem,reser_outstd_claims,reser_lins_liab,reser_lthins_liab,indept_acc_liab,pledge_borr,indem_payable,policy_div_payable,total_liab,treasury_share,ordin_risk_reser,forex_differ,invest_loss_unconf,minority_int,total_hldr_eqy_exc_min_int,total_hldr_eqy_inc_min_int,total_liab_hldr_eqy,lt_payroll_payable,oth_comp_income,oth_eqt_tools,oth_eqt_tools_p_shr,lending_funds,acc_receivable,st_fin_payable,payables,hfs_assets,hfs_sales,cost_fin_assets,fair_value_fin_assets,cip_total,oth_pay_total,long_pay_total,debt_invest,oth_debt_invest,oth_eq_invest,oth_illiq_fin_assets,oth_eq_ppbond,receiv_financing,use_right_assets,lease_liab,contract_assets,contract_liab,accounts_receiv_bill,accounts_pay,oth_rcv_total,fix_assets_total,update_flag'
        
        df = pro.balancesheet(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的资产负债表数据"

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
            if pd.notna(row.get('total_assets')): info_parts.append(f"总资产: {format_money(row['total_assets'])}")
            if pd.notna(row.get('total_liab')): info_parts.append(f"总负债: {format_money(row['total_liab'])}")
            if pd.notna(row.get('total_hldr_eqy_exc_min_int')): info_parts.append(f"股东权益: {format_money(row['total_hldr_eqy_exc_min_int'])}")
            if pd.notna(row.get('money_cap')): info_parts.append(f"货币资金: {format_money(row['money_cap'])}")

            result.append(" | ".join(info_parts))
            
        if len(df) > display_cap:
             result.append(f"... (共 {len(df)} 条，仅显示前 {display_cap} 条)")
             
        # Add a note about the full data
        result.append("\n(更多字段请在代码中查看 'fields' 列表)")

        return "\n".join(result)
