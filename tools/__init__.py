# tools/__init__.py
from .stock.basic.stock_basic import register_stock_basic_tools
from .stock.basic.trade_cal import register_trade_calendar_tools
from .stock.basic.st import register_st_tools
from .stock.basic.stock_st import register_stock_st_tools
from .stock.basic.stock_hsgt import register_stock_hsgt_tools
from .stock.basic.namechange import register_namechange_tools
from .stock.basic.stock_company import register_stock_company_tools
from .stock.basic.stk_managers import register_stk_managers_tools
from .stock.basic.stk_rewards import register_stk_rewards_tools
from .stock.basic.bse_mapping import register_bse_mapping_tools
from .stock.basic.new_share import register_new_share_tools
from .stock.basic.bak_basic import register_bak_basic_tools
from .stock.quote.daily import register_daily_tools
from .stock.quote.weekly import register_weekly_tools
from .stock.quote.monthly import register_monthly_tools
from .stock.quote.daily_basic import register_daily_basic_tools
from .stock.quote.stk_limit import register_stk_limit_tools
from .stock.quote.suspend_d import register_suspend_d_tools
from .stock.quote.hsgt_top10 import register_hsgt_top10_tools
from .stock.quote.ggt_top10 import register_ggt_top10_tools
from .stock.quote.ggt_daily import register_ggt_daily_tools
from .stock.quote.ggt_monthly import register_ggt_monthly_tools
# from .stock.premarket import register_stock_premarket_tools
from .finance import register_finance_tools

from typing import List, Optional
from utils.logger import log_debug

def register_stock_tools(mcp):
    """Register all stock-related tools."""
    register_stock_basic_tools(mcp)
    register_trade_calendar_tools(mcp)
    register_stock_st_tools(mcp)
    register_st_tools(mcp)
    register_stock_hsgt_tools(mcp)
    register_namechange_tools(mcp)
    register_stock_company_tools(mcp)
    register_stk_managers_tools(mcp)
    register_stk_rewards_tools(mcp)
    register_bse_mapping_tools(mcp)
    register_new_share_tools(mcp)
    register_bak_basic_tools(mcp)
    register_daily_tools(mcp)
    register_weekly_tools(mcp)
    register_monthly_tools(mcp)
    register_daily_basic_tools(mcp)
    register_stk_limit_tools(mcp)
    register_suspend_d_tools(mcp)
    register_hsgt_top10_tools(mcp)
    register_ggt_top10_tools(mcp)
    register_ggt_daily_tools(mcp)
    register_ggt_monthly_tools(mcp)
    # register_stock_premarket_tools(mcp)
    register_finance_tools(mcp)

def register_all_tools(mcp, categories: Optional[List[str]] = None):
    """
    Register tools to the given FastMCP instance based on categories.
    
    Args:
        mcp: FastMCP instance
        categories: List of tool categories to register. If None or empty, registers ALL tools.
                    Available categories: 'stock'
    """
    # Map category names to registration functions
    category_map = {
        'stock': register_stock_tools,
        'finance': register_finance_tools,
        # Future categories:
        # 'fund': register_fund_tools,
    }
    
    if not categories:
        # If no categories specified, register everything
        log_debug("No tool categories specified, registering ALL tools.")
        for category, register_func in category_map.items():
            register_func(mcp)
            log_debug(f"Registered tool category: {category}")
    else:
        # Register simplified list of requested categories
        for category in categories:
            if category in category_map:
                category_map[category](mcp)
                log_debug(f"Registered tool category: {category}")
            else:
                log_debug(f"Warning: Unknown tool category '{category}' skipped.")

