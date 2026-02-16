import sys
import argparse
import traceback
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Import from our new modules
from utils.logger import log_debug
from utils.token_manager import set_tinyshare_token, get_tinyshare_token, get_pro_client
from tools import register_all_tools
import tinyshare as ts

# --- MCP Instance Creation ---
# host=0.0.0.0 对外暴露, 关闭 DNS rebinding 保护 (由 Cloudflare Tunnel 负责安全)
try:
    mcp = FastMCP(
        "Tinyshare Tools Enhanced",
        host="0.0.0.0",
        port=8000,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
    log_debug("FastMCP instance created for Tinyshare Tools Enhanced.")
except Exception as e:
    log_debug(f"ERROR creating FastMCP: {e}")
    traceback.print_exc(file=sys.stderr)
    raise

# --- Register Tools ---
@mcp.prompt()
def configure_token() -> str:
    """配置Tinyshare token的提示模板"""
    return """请提供您的Tinyshare API token。

请输入您的token:"""

@mcp.tool()
def setup_tinyshare_token(token: str) -> str:
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

@mcp.tool()
def check_token_status() -> str:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tushare MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode for MCP clients")
    parser.add_argument("--category", action="append", help="Tool category to load (e.g. 'stock'). Can be specified multiple times.")
    args = parser.parse_args()

    # Register tools based on categories
    categories = args.category if args.category else None
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
        print("DEBUG: Starting Streamable HTTP server on 0.0.0.0:8000/mcp ...", file=sys.stderr, flush=True)
        mcp.run(transport='streamable-http')