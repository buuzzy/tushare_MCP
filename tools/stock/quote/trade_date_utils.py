from datetime import datetime, timedelta

from utils.logger import log_debug


def resolve_trade_date(pro, start_date: str = "", end_date: str = "") -> str:
    """Resolve one trading day, preferring fresh index data over trade_cal."""
    if end_date:
        anchor = datetime.strptime(end_date, "%Y%m%d")
        start_check = (anchor - timedelta(days=20)).strftime("%Y%m%d")
        end_check = end_date
        prefer_previous = True
    elif start_date:
        anchor = datetime.strptime(start_date, "%Y%m%d")
        start_check = start_date
        end_check = (anchor + timedelta(days=20)).strftime("%Y%m%d")
        prefer_previous = False
    else:
        anchor = datetime.now()
        start_check = (anchor - timedelta(days=20)).strftime("%Y%m%d")
        end_check = anchor.strftime("%Y%m%d")
        prefer_previous = True

    # TinyShare's trade_cal can lag behind its quote data. The Shanghai
    # Composite index is a reliable A-share trading-day reference here.
    dates = []
    try:
        df_index = pro.index_daily(
            ts_code="000001.SH",
            start_date=start_check,
            end_date=end_check,
        )
        if df_index is not None and not df_index.empty:
            dates = df_index["trade_date"].dropna().tolist()
    except Exception as exc:
        log_debug(f"Failed to resolve trade date from index_daily: {exc}")

    if not dates:
        df_cal = pro.trade_cal(
            start_date=start_check,
            end_date=end_check,
            is_open="1",
        )
        if df_cal is not None and not df_cal.empty:
            dates = df_cal["cal_date"].dropna().tolist()

    if not dates:
        return ""

    if prefer_previous:
        eligible = [date for date in dates if date <= end_check]
        return max(eligible) if eligible else ""
    eligible = [date for date in dates if date >= start_check]
    return min(eligible) if eligible else ""
