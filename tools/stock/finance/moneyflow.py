import pandas as pd
from utils.logger import log_debug, handle_exception
from utils.token_manager import get_pro_client

def register_moneyflow_tools(mcp):
    @mcp.tool()
    @handle_exception
    def moneyflow(ts_code: str = '', trade_date: str = '', start_date: str = '',
                  end_date: str = '', limit: int = None) -> str:
        """
        获取个股资金流向数据（主力、超大单、大单、中单、小单净流入/流出）。

        参数:
            ts_code: 股票代码（如 600519.SH）
            trade_date: 交易日期 YYYYMMDD（可选）
            start_date: 开始日期 YYYYMMDD（可选）
            end_date: 结束日期 YYYYMMDD（可选）
            limit: 返回条数上限，默认20
        """
        log_debug(f"Tool moneyflow called: ts_code={ts_code}, start={start_date}, end={end_date}")
        if not any([ts_code, trade_date, start_date]):
            return "错误：至少提供一个筛选条件（ts_code/trade_date/start_date）"

        pro = get_pro_client()
        raw_params = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'start_date': start_date,
            'end_date': end_date
        }
        api_params = {k: v for k, v in raw_params.items() if v}

        effective_limit = limit if limit else 20
        api_params['limit'] = effective_limit

        fields = 'ts_code,trade_date,net_mf_amount,buy_elg_amount,sell_elg_amount,buy_lg_amount,sell_lg_amount,buy_md_amount,sell_md_amount,buy_sm_amount,sell_sm_amount'

        df = pro.moneyflow(**api_params, fields=fields)
        if df.empty:
            return "未找到符合条件的资金流向数据"

        # API returns DESC (newest first); take newest N, then reverse to chronological
        df = df.head(effective_limit)
        df = df.iloc[::-1].reset_index(drop=True)

        result = [f"--- 个股资金流向 (共 {len(df)} 天) ---"]

        def fmt(val):
            if pd.isna(val):
                return "N/A"
            val_abs = abs(val)
            if val_abs >= 1e8:
                return f"{val/1e8:.2f}亿"
            elif val_abs >= 1e4:
                return f"{val/1e4:.2f}万"
            return f"{val:.0f}"

        for _, row in df.iterrows():
            parts = []
            if pd.notna(row.get('trade_date')):
                parts.append(f"日期:{row['trade_date']}")

            if pd.notna(row.get('net_mf_amount')):
                nmf = row['net_mf_amount']
                direction = "净流入" if nmf >= 0 else "净流出"
                parts.append(f"主力{direction}:{fmt(nmf)}")

            if pd.notna(row.get('buy_elg_amount')) and pd.notna(row.get('sell_elg_amount')):
                elg_net = row['buy_elg_amount'] - row['sell_elg_amount']
                parts.append(f"超大单:{fmt(elg_net)}")

            if pd.notna(row.get('buy_lg_amount')) and pd.notna(row.get('sell_lg_amount')):
                lg_net = row['buy_lg_amount'] - row['sell_lg_amount']
                parts.append(f"大单:{fmt(lg_net)}")

            if pd.notna(row.get('buy_md_amount')) and pd.notna(row.get('sell_md_amount')):
                md_net = row['buy_md_amount'] - row['sell_md_amount']
                parts.append(f"中单:{fmt(md_net)}")

            if pd.notna(row.get('buy_sm_amount')) and pd.notna(row.get('sell_sm_amount')):
                sm_net = row['buy_sm_amount'] - row['sell_sm_amount']
                parts.append(f"小单:{fmt(sm_net)}")

            result.append(" | ".join(parts))

        return "\n".join(result)
