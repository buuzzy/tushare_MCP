import sys
import argparse
import traceback
import uvicorn
from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI, HTTPException, Body
from starlette.requests import Request
from mcp.server.sse import SseServerTransport

# Import from our new modules
from utils.logger import log_debug
from utils.token_manager import set_tinyshare_token, get_tinyshare_token, get_pro_client
from tools import register_all_tools
import tinyshare as ts

# --- MCP Instance Creation ---
try:
    mcp = FastMCP("Tinyshare Tools Enhanced")
    log_debug("FastMCP instance created for Tinyshare Tools Enhanced.")
except Exception as e:
    log_debug(f"ERROR creating FastMCP: {e}")
    traceback.print_exc(file=sys.stderr)
    raise

# --- Register Tools ---
# 1. Core Token Tools (kept here or moved to a core tools module? Kept here for simplicity of initialization)
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

# 2. Register all other tools (Moved to main execution block for modularity)
# register_all_tools(mcp) 
# log_debug("All external tools registered.")

# --- FastAPI App Creation (for SSE) ---
app = FastAPI(title="Tinyshare MCP API", version="0.0.1")

@app.get("/")
async def read_root():
    return {"message": "Hello World - Tinyshare MCP API is running!"}

@app.post("/tools/setup_tinyshare_token", summary="Setup Tinyshare API token")
async def api_setup_tinyshare_token(payload: dict = Body(...)):
    token = payload.get("token")
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'token'")
    try:
        output = setup_tinyshare_token(token=token)
        return {"status": "success", "message": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- SSE Integration ---
MCP_BASE_PATH = "/sse"
messages_full_path = f"{MCP_BASE_PATH}/messages/"
sse_transport = SseServerTransport(messages_full_path)

async def handle_mcp_sse_handshake(request: Request) -> None:
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp._mcp_server.run(
            read_stream, write_stream, mcp._mcp_server.create_initialization_options()
        )

app.add_route(MCP_BASE_PATH, handle_mcp_sse_handshake, methods=["GET"])
app.mount(messages_full_path, sse_transport.handle_post_message)


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
        print("DEBUG: Starting HTTP server for SSE...", file=sys.stderr, flush=True)
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")