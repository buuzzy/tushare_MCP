import functools
import pandas as pd
from typing import Optional, Callable, Any
from .logger import log_debug

def _get_stock_name(pro_api_instance, ts_code: str) -> str:
    """Helper function to get stock name from ts_code."""
    log_debug(f"_get_stock_name called for ts_code: {ts_code}")
    if not pro_api_instance:
        log_debug("_get_stock_name received no pro_api_instance. Cannot fetch name.")
        return ts_code
    try:
        df_basic = pro_api_instance.stock_basic(ts_code=ts_code, fields='ts_code,name')
        if not df_basic.empty:
            return df_basic.iloc[0]['name']
    except Exception as e:
        log_debug(f"Warning: Failed to get stock name for {ts_code}: {e}")
    return ts_code

def _fetch_latest_report_data(
    api_func: Callable[..., pd.DataFrame],
    result_period_field_name: str, 
    result_period_value: str, 
    is_list_result: bool = False, # New parameter to indicate if multiple rows are expected for the latest announcement
    **api_params: Any
) -> Optional[pd.DataFrame]:
    """
    Internal helper to fetch report data.
    If is_list_result is True, it returns all rows matching the latest announcement date.
    Otherwise, it returns only the single latest announced record.
    """
    func_name = "Unknown API function"
    if isinstance(api_func, functools.partial):
        func_name = api_func.func.__name__
    elif hasattr(api_func, '__name__'):
        func_name = api_func.__name__

    log_debug(f"_fetch_latest_report_data called for {func_name}, period: {result_period_value}, is_list: {is_list_result}")
    try:
        df = api_func(**api_params)
        if df.empty:
            log_debug(f"_fetch_latest_report_data: API call {func_name} returned empty DataFrame for {api_params.get('ts_code')}")
            return None

        # Ensure 'ann_date' and the specified period field exist for sorting/filtering
        if 'ann_date' not in df.columns:
            log_debug(f"Warning: _fetch_latest_report_data: 'ann_date' not in DataFrame columns for {func_name} on {api_params.get('ts_code')}. Returning raw df (or first row if not list).")
            return df if is_list_result else df.head(1)

        if result_period_field_name not in df.columns:
            log_debug(f"Warning: _fetch_latest_report_data: Period field '{result_period_field_name}' not in DataFrame columns for {func_name} on {api_params.get('ts_code')}. Filtering by ann_date only.")
            # Sort by ann_date to get the latest announcement(s)
            df_sorted_by_ann = df.sort_values(by='ann_date', ascending=False)
            if df_sorted_by_ann.empty:
                return None
            latest_ann_date = df_sorted_by_ann['ann_date'].iloc[0]
            df_latest_ann = df_sorted_by_ann[df_sorted_by_ann['ann_date'] == latest_ann_date]
            return df_latest_ann # Return all rows for the latest announcement date

        # Filter by the specific report period first
        # Convert both to string for robust comparison, in case of type mismatches
        df_filtered_period = df[df[result_period_field_name].astype(str) == str(result_period_value)]

        if df_filtered_period.empty:
            log_debug(f"_fetch_latest_report_data: No data found for period {result_period_value} after filtering by '{result_period_field_name}' for {func_name} on {api_params.get('ts_code')}. Original df had {len(df)} rows.")
            # Fallback: if strict period filtering yields nothing, but original df had data,
            # it might be that ann_date is more reliable or the period was slightly off.
            # For now, let's return None if period match fails, to be strict.
            # Consider alternative fallback if needed, e.g. using latest ann_date from original df.
            return None

        # Sort by ann_date to get the latest announcement(s) for that specific period
        df_sorted_by_ann = df_filtered_period.sort_values(by='ann_date', ascending=False)
        if df_sorted_by_ann.empty: # Should not happen if df_filtered_period was not empty
            return None
        
        latest_ann_date = df_sorted_by_ann['ann_date'].iloc[0]
        df_latest_ann = df_sorted_by_ann[df_sorted_by_ann['ann_date'] == latest_ann_date]

        if is_list_result:
            log_debug(f"_fetch_latest_report_data: Returning {len(df_latest_ann)} rows for latest announcement on {latest_ann_date} (list_result=True)")
            return df_latest_ann # Return all rows for the latest announcement date for this period
        else:
            # Return only the top-most row (which is the latest announcement for that period)
            log_debug(f"_fetch_latest_report_data: Returning 1 row for latest announcement on {latest_ann_date} (list_result=False)")
            return df_latest_ann.head(1)

    except Exception as e:
        log_debug(f"Error in _fetch_latest_report_data calling {func_name} for {api_params.get('ts_code', 'N/A')}, period {result_period_value}: {e}")
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)
        return None
