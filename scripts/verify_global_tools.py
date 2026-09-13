"""港美股工具 MCP 协议级验证脚本。

用法:
    本地:  .venv/bin/python scripts/verify_global_tools.py
    线上:  .venv/bin/python scripts/verify_global_tools.py --url https://minishare-mcp-production.up.railway.app/sse

本地运行说明：若未安装私有 SDK（tinyshare/minishare），脚本生成 sitecustomize
stub 后以 --category global 启动子进程 server，再经 SSE 逐工具调用。
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import textwrap
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUB = textwrap.dedent("""
    import sys, types
    for _name in ("tinyshare", "minishare"):
        try:
            __import__(_name)
        except ImportError:
            _m = types.ModuleType(_name)
            _m.pro_api = lambda *a, **k: None
            sys.modules[_name] = _m
""")

# (工具, 参数, 预期包含的子串或 None)
CASES = [
    ("search_symbol", {"query": "00700"}, "00700"),
    ("search_symbol", {"query": "AAPL", "market": "us"}, "AAPL"),
    ("hk_fina_indicator", {"symbol": "00700", "limit": 3}, "ROE"),
    ("hk_income", {"symbol": "00700", "limit": 2}, "营业"),
    ("hk_balancesheet", {"symbol": "700", "limit": 1}, "报告期"),
    ("hk_cashflow", {"symbol": "00700", "limit": 1}, "报告期"),
    ("us_fina_indicator", {"symbol": "AAPL", "limit": 3}, "报告期"),
    ("us_income", {"symbol": "AAPL", "limit": 2}, "营业收入"),
    ("us_balancesheet", {"symbol": "AAPL", "limit": 1}, "报告期"),
    ("us_cashflow", {"symbol": "AAPL", "limit": 1}, "报告期"),
    ("us_filings", {"symbol": "AAPL", "form": "10-K", "limit": 3}, "10-K"),
    ("hk_announcements", {"symbol": "00700", "limit": 5}, "公告"),
    ("hk_daily", {"symbol": "00700", "start_date": "20260901"}, "代码:00700.HK"),
    ("hk_weekly", {"symbol": "00700", "start_date": "20260801"}, "代码:00700.HK"),
    ("hk_monthly", {"symbol": "00700", "start_date": "20260601"}, "代码:00700.HK"),
    ("us_daily", {"symbol": "AAPL", "start_date": "20260901"}, "代码:AAPL"),
    ("us_weekly", {"symbol": "AAPL", "start_date": "20260801"}, "代码:AAPL"),
    ("global_index_daily", {"symbol": "HSI", "start_date": "20260901"}, "代码:hkHSI"),
    ("global_index_daily", {"symbol": "SPX", "start_date": "20260901"}, "代码:usINX"),
]


def start_local_server(port: int) -> subprocess.Popen:
    stub_dir = tempfile.mkdtemp(prefix="gm_stub_")
    with open(os.path.join(stub_dir, "sitecustomize.py"), "w") as f:
        f.write(STUB)
    env = dict(os.environ, PYTHONPATH=stub_dir)
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port), "--category", "global"],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(4)  # 等待 SSE server 就绪
    return proc


async def verify(url: str) -> int:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    passed, failed = 0, 0
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            listed = resp.tools if hasattr(resp, "tools") else resp[0].tools
            names = {t.name for t in listed}
            print(f"server tools: {len(names)} registered")
            for tool, args, expect in CASES:
                if tool not in names:
                    print(f"  SKIP  {tool}: not registered")
                    failed += 1
                    continue
                try:
                    result = await session.call_tool(tool, args)
                    text = "".join(
                        getattr(c, "text", "") for c in result.content
                    )
                    if result.isError:
                        print(f"  FAIL  {tool}{args}: isError -> {text[:120]}")
                        failed += 1
                    elif expect and expect not in text:
                        print(f"  FAIL  {tool}{args}: '{expect}' not in output: {text[:120]}")
                        failed += 1
                    else:
                        first = text.split("\n")[1] if "\n" in text else text
                        print(f"  PASS  {tool}: {first[:100]}")
                        passed += 1
                except Exception as e:
                    print(f"  FAIL  {tool}{args}: {type(e).__name__}: {str(e)[:100]}")
                    failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="", help="MCP SSE endpoint；留空则本地起 server")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    proc = None
    url = args.url
    if not url:
        proc = start_local_server(args.port)
        url = f"http://127.0.0.1:{args.port}/sse"
        print(f"local server started: {url}")
    try:
        return asyncio.run(verify(url))
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
