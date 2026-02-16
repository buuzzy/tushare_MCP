from .income import register_income_tools
from .balancesheet import register_balancesheet_tools
from .cashflow import register_cashflow_tools
from .forecast import register_forecast_tools
from .express import register_express_tools
from .dividend import register_dividend_tools
from .fina_indicator import register_fina_indicator_tools
from .fina_audit import register_fina_audit_tools
from .fina_mainbz import register_fina_mainbz_tools
from .disclosure_date import register_disclosure_date_tools

def register_finance_tools(mcp):
    register_income_tools(mcp)
    register_balancesheet_tools(mcp)
    register_cashflow_tools(mcp)
    register_forecast_tools(mcp)
    register_express_tools(mcp)
    register_dividend_tools(mcp)
    register_fina_indicator_tools(mcp)
    register_fina_audit_tools(mcp)
    register_fina_mainbz_tools(mcp)
    register_disclosure_date_tools(mcp)
