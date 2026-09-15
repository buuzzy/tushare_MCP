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
    # (工具, 参数, 预期子串, 最小bar数)  min_bars>0 时校验 Total 根数，防"只返回1根"回归
    ("search_symbol", {"query": "00700"}, "00700", 0),
    ("search_symbol", {"query": "AAPL", "market": "us"}, "AAPL", 0),
    ("search_symbol", {"query": "SNDK", "market": "us"}, "SNDK", 0),
    # 次新股/中文名搜索回归（活跃表快照不含 02714，靠 suggest 全库兜底）
    ("search_symbol", {"query": "牧原", "market": "hk"}, "02714", 0),
    ("search_symbol", {"query": "苹果", "market": "us"}, "AAPL", 0),
    # 无效完整代码须诚实拒答（P2#39 回归：99999 曾被盲回显"确认存在"）
    ("search_symbol", {"query": "99999", "market": "hk"}, "未找到", 0),
    # 短简写透传保留（suggest 不支持前缀匹配）
    ("search_symbol", {"query": "700", "market": "hk"}, "00700", 0),
    ("hk_fina_indicator", {"symbol": "00700", "limit": 3}, "ROE", 0),
    ("hk_income", {"symbol": "00700", "limit": 2}, "营业", 0),
    ("hk_balancesheet", {"symbol": "700", "limit": 1}, "报告期", 0),
    ("hk_cashflow", {"symbol": "00700", "limit": 1}, "报告期", 0),
    ("us_fina_indicator", {"symbol": "AAPL", "limit": 3}, "报告期", 0),
    ("us_income", {"symbol": "AAPL", "limit": 2}, "营业收入", 0),
    ("us_balancesheet", {"symbol": "AAPL", "limit": 1}, "报告期", 0),
    ("us_cashflow", {"symbol": "AAPL", "limit": 1}, "报告期", 0),
    ("us_filings", {"symbol": "AAPL", "form": "10-K", "limit": 3}, "10-K", 0),
    ("hk_announcements", {"symbol": "00700", "limit": 5}, "公告", 0),
    # 港股每日回购（datacenter 域）：验证海外可达 + 数据量（腾讯几乎逐日回购）
    ("hk_buyback", {"symbol": "00700"}, "腾讯控股", 8),
    ("hk_daily", {"symbol": "00700", "start_date": "20260901"}, "代码:00700.HK", 8),
    # 分页回归（P1#7 实测）：默认 3 年窗口必须拉全——旧判据在 ~538 根（首段）止步，
    # 数据错误地停在 2025-11-21；3 个港股交易日年 ≈ 745 根
    ("hk_daily", {"symbol": "00700"}, "名称:腾讯控股", 700),
    # 20 年多段拼接（验收 #14）：~4900 根，验证跨 ~10 段无丢段
    ("hk_daily", {"symbol": "00700", "start_date": "20060914"}, "名称:腾讯控股", 4500),
    # 次新股回归：默认近 3 年窗口首段在上市前（2026-02-06 上市），须跳过空段
    ("hk_daily", {"symbol": "02714"}, "名称:牧原股份", 100),
    # 截断脚注须自述完整区间（防 Agent 把首行可见日期误当数据起点/误推上市时间）
    ("hk_daily", {"symbol": "02714", "start_date": "20250601"}, "数据区间 2026-02-06", 100),
    # 上市前区间无数据：错误消息应带候选 hint（suggest 回填中文名）
    ("hk_daily", {"symbol": "02714", "start_date": "20230101", "end_date": "20240101"}, "牧原股份", 0),
    ("hk_weekly", {"symbol": "00700", "start_date": "20260801"}, "代码:00700.HK", 4),
    ("hk_monthly", {"symbol": "00700", "start_date": "20260601"}, "代码:00700.HK", 3),
    ("us_daily", {"symbol": "AAPL", "start_date": "20260901"}, "代码:AAPL", 7),
    ("us_daily", {"symbol": "SNDK", "start_date": "20260827"}, "代码:SNDK", 8),
    ("us_weekly", {"symbol": "AAPL", "start_date": "20260801"}, "代码:AAPL", 4),
    ("global_index_daily", {"symbol": "HSI", "start_date": "20260901"}, "代码:hkHSI", 8),
    ("global_index_daily", {"symbol": "SPX", "start_date": "20260901"}, "代码:.INX", 5),
    ("global_index_daily", {"symbol": "DJIA", "start_date": "20260901"}, "代码:.DJI", 5),
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
            for tool, args, expect, min_bars in CASES:
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
                    elif min_bars:
                        import re as _re
                        m = _re.search(r"\((?:Total: (\d+)|共 (\d+) 条)\)", text)
                        total = int(m.group(1) or m.group(2)) if m else 0
                        if total < min_bars:
                            print(f"  FAIL  {tool}{args}: 仅 {total} 根 (< {min_bars}): {text[:100]}")
                            failed += 1
                            continue
                        print(f"  PASS  {tool}: bars={total} (>= {min_bars})")
                        passed += 1
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
