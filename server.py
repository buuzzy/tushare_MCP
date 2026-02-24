import sys
import argparse
import traceback
from mcp.server.fastmcp import FastMCP
# Import from our new modules
from utils.logger import log_debug
from utils.token_manager import set_tinyshare_token, get_tinyshare_token, get_pro_client
from tools import register_all_tools
import tinyshare as ts



# Define local tools as standalone functions first
def configure_token_impl() -> str:
    """配置Tinyshare token的提示模板"""
    return """请提供您的Tinyshare API token。

请输入您的token:"""

def setup_tinyshare_token_impl(token: str) -> str:
    """设置Tinyshare API token"""
    log_debug(f"Tool setup_tinyshare_token called.")
    try:
        set_tinyshare_token(token)
        # Verify immediately
        current_token = get_tinyshare_token()
        if not current_token:
            return "Token配置尝试完成，但未能立即验证。请稍后使用 check_token_status 检查。"
        ts.pro_api(current_token) # Verify
        log_debug("setup_tinyshare_token verification successful.")
        return "Token配置成功！您现在可以使用Tinyshare的API功能了。"
    except Exception as e:
        log_debug(f"ERROR in setup_tinyshare_token: {str(e)}")
        traceback.print_exc(file=sys.stderr)
        return f"Token配置失败：{str(e)}"

def check_token_status_impl() -> str:
    """检查Tinyshare token状态"""
    log_debug("Tool check_token_status called.")
    token = get_tinyshare_token()
    if not token:
        return "未配置Tinyshare token。请使用 setup_tinyshare_token 配置。"
    try:
        ts.pro_api(token)
        return "Token配置正常，可以使用Tinyshare API。"
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return f"Token无效或已过期: {str(e)}"

def create_mcp_server(port: int = 8000) -> FastMCP:
    try:
        mcp = FastMCP(
            "Tinyshare Tools Enhanced",
            host="0.0.0.0", # Bind to all interfaces by default for convenience in docker/deployment
            port=port,
        )
        log_debug(f"FastMCP instance created for Tinyshare Tools Enhanced on port {port}.")
        return mcp
    except Exception as e:
        log_debug(f"ERROR creating FastMCP: {e}")
        traceback.print_exc(file=sys.stderr)
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tushare MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode for MCP clients")
    parser.add_argument("--category", action="append", help="Tool category to load (e.g. 'stock', 'fund'). Can be specified multiple times.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()

    # 1. Create Server Instance
    mcp = create_mcp_server(port=args.port)

    # 2. Register local tools
    # Note: FastMCP.tool() and .prompt() decorators can be used as function calls if we bind them
    # But here we use the name argument to register existing functions
    mcp.prompt(name="configure_token")(configure_token_impl)
    mcp.tool(name="setup_tinyshare_token")(setup_tinyshare_token_impl)
    mcp.tool(name="check_token_status")(check_token_status_impl)

    # 3. Register External Tools based on categories
    categories = args.category if args.category else None
    print(f"DEBUG: Parsed categories: {categories}", file=sys.stderr)
    register_all_tools(mcp, categories=categories)
    log_debug(f"Registered tools with categories: {categories if categories else 'ALL'}")

    if args.stdio:
        print("DEBUG: Starting in stdio mode...", file=sys.stderr, flush=True)
        try:
            mcp.run(transport='stdio')
        except Exception as e:
            print(f"DEBUG: Error in stdio mode: {e}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
    else:
        print(f"DEBUG: Starting SSE server on 0.0.0.0:{args.port}/sse ...", file=sys.stderr, flush=True)
        mcp.run(transport='sse')