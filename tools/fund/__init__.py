from .etf_basic import register_etf_basic_tools
from .etf_index import register_etf_index_tools
from .stk_mins import register_stk_mins_tools
from .fund_daily import register_fund_daily_tools
from .fund_adj import register_fund_adj_tools
from .etf_share_size import register_etf_share_size_tools
from .fund_basic import register_fund_basic_tools
from .fund_company import register_fund_company_tools
from .fund_manager import register_fund_manager_tools
from .fund_share import register_fund_share_tools
from .fund_nav import register_fund_nav_tools
from .fund_div import register_fund_div_tools
from .fund_portfolio import register_fund_portfolio_tools
from .fund_factor_pro import register_fund_factor_pro_tools

def register_fund_tools(mcp):
    """Register all fund-related tools."""
    register_etf_basic_tools(mcp)
    register_etf_index_tools(mcp)
    register_stk_mins_tools(mcp)
    register_fund_daily_tools(mcp)
    register_fund_adj_tools(mcp)
    register_etf_share_size_tools(mcp)
    register_fund_basic_tools(mcp)
    register_fund_company_tools(mcp)
    register_fund_manager_tools(mcp)
    register_fund_share_tools(mcp)
    register_fund_nav_tools(mcp)
    register_fund_div_tools(mcp)
    register_fund_portfolio_tools(mcp)
    register_fund_factor_pro_tools(mcp)
