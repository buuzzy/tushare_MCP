import sys
import argparse
import traceback
from mcp.server.fastmcp import FastMCP
from utils.logger import log_debug
from utils.token_manager import (
    set_data_token, get_data_token,
    set_corpus_token, get_corpus_token,
)
from tools import register_all_tools
import tinyshare as ts  # minishare 数据 SDK（pip 包名仍为 tinyshare）


# ---------------------------------------------------------------------------
# Token setup tools (user-invocable via MCP)
# ---------------------------------------------------------------------------

def setup_data_token_impl(token: str) -> str:
    """设置行情/财报数据授权码"""
    log_debug("Tool setup_data_token called.")
    try:
        set_data_token(token)
        current = get_data_token()
        if not current:
            return "Token 配置未能验证，请重试。"
        ts.pro_api(current)
        return "行情数据授权码配置成功！"
    except Exception as e:
        log_debug(f"ERROR in setup_data_token: {str(e)}")
        traceback.print_exc(file=sys.stderr)
        return f"Token 配置失败：{str(e)}"


def setup_corpus_token_impl(token: str) -> str:
    """设置资讯/语料授权码"""
    log_debug("Tool setup_corpus_token called.")
    try:
        set_corpus_token(token)
        return "资讯语料授权码配置成功！"
    except Exception as e:
        log_debug(f"ERROR in setup_corpus_token: {str(e)}")
        traceback.print_exc(file=sys.stderr)
        return f"Token 配置失败：{str(e)}"


def check_token_status_impl() -> str:
    """检查授权码状态"""
    log_debug("Tool check_token_status called.")
    data_token = get_data_token()
    corpus_token = get_corpus_token()
    parts = []
    if data_token:
        try:
            ts.pro_api(data_token)
            parts.append("行情数据授权码：正常")
        except Exception as e:
            parts.append(f"行情数据授权码：无效或过期 ({str(e)[:80]})")
    else:
        parts.append("行情数据授权码：未配置")

    if corpus_token:
        parts.append("资讯语料授权码：已配置")
    else:
        parts.append("资讯语料授权码：未配置")

    return " | ".join(parts)


# Aliases: maps hallucinated tool names to the correct registered name.
TOOL_ALIASES = {
    "balance_sheet": "balancesheet",
    "cash_flow": "cashflow",
    "financial_indicator": "fina_indicator",
    "daily_quote": "daily",
    "income_statement": "income",
    "balance_sheet_data": "balancesheet",
    "cash_flow_statement": "cashflow",
    "dividend_data": "dividend",
    "news_search": "news",
    "research_reports": "research_report",
    "announcements": "anns_d",
    "announcement": "anns_d",
    "stock_data": "daily",
    "stock_quote": "daily",
    "market_data": "daily",
    "index_daily": "daily",
    "index_weekly": "weekly",
    "index_monthly": "monthly",
    "financial_data": "fina_indicator",
    "company_info": "stock_company",
    "basic_info": "stock_basic",
    "fund_data": "fund_daily",
    "fund_info": "fund_nav",
    "stk_holder_number": "stk_holdernumber",
    "holder_number": "stk_holdernumber",
    "top_holders": "stk_holdernumber",
}

def register_tool_aliases(mcp: FastMCP):
    """Register alias names so model-hallucinated tool calls resolve correctly."""
    tm = mcp._tool_manager
    for alias, real_name in TOOL_ALIASES.items():
        if real_name not in tm._tools:
            continue
        if alias in tm._tools:
            continue
        real_tool = tm._tools[real_name]
        tm.add_tool(real_tool.fn, name=alias, description=real_tool.description)
        log_debug(f"Registered alias '{alias}' -> '{real_name}'")

def create_mcp_server(port: int = 8000) -> FastMCP:
    mcp = FastMCP(
        "Minishare Data Service",
        host="0.0.0.0",
        port=port,
    )
    log_debug(f"FastMCP instance created on port {port}.")
    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minishare MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode")
    parser.add_argument("--category", action="append", help="Tool category (stock, fund, corpus). Can be repeated.")
    parser.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    args = parser.parse_args()

    mcp = create_mcp_server(port=args.port)

    # Token management tools
    mcp.tool(name="setup_data_token")(setup_data_token_impl)
    mcp.tool(name="setup_corpus_token")(setup_corpus_token_impl)
    mcp.tool(name="check_token_status")(check_token_status_impl)

    # Register data/corpus tools
    categories = args.category if args.category else None
    print(f"Categories: {categories}", file=sys.stderr)
    register_all_tools(mcp, categories=categories)
    log_debug(f"Registered tools: {categories if categories else 'ALL'}")

    # Register aliases for tool names that models commonly hallucinate
    register_tool_aliases(mcp)

    if args.stdio:
        print("Starting in stdio mode...", file=sys.stderr, flush=True)
        mcp.run(transport='stdio')
    else:
        print(f"Starting SSE server on 0.0.0.0:{args.port}/sse ...", file=sys.stderr, flush=True)
        mcp.run(transport='sse')
