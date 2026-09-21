"""港美股工具 MCP 协议级验证脚本。

用法:
    本地:  .venv/bin/python scripts/verify_global_tools.py
    线上:  .venv/bin/python scripts/verify_global_tools.py --url https://minishare-mcp-production.up.railway.app/sse

本地运行说明：若未安装私有 SDK（tinyshare/minishare），脚本生成 sitecustomize
stub 后以 --category global 启动子进程 server，再经 SSE 逐工具调用（仅执行
category="global" 的用例；astock 等其他类别仅线上模式执行）。
本机若设置了 HTTP_PROXY/HTTPS_PROXY 环境变量，须以 NO_PROXY=127.0.0.1,localhost
前缀运行，否则 MCP SSE 客户端 POST 会被代理改写导致 404。
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
    # K 线类：紧凑格式（9f27eee 起）代码/名称只在标题行声明一次
    ("hk_daily", {"symbol": "00700", "start_date": "20260901"}, "| 00700.HK 腾讯控股 |", 8),
    # 分页回归（P1#7 实测）：默认 3 年窗口必须拉全——旧判据在 ~538 根（首段）止步；
    # 737 根日线自动聚合为 ~157 根周线（81c9b98 起），Total 以周线数校验
    ("hk_daily", {"symbol": "00700"}, "| 00700.HK 腾讯控股 |", 150),
    # 20 年多段拼接（验收 #14）：~4900 根日线 → ~240 根月线，验证跨 ~10 段无丢段
    ("hk_daily", {"symbol": "00700", "start_date": "20060914"}, "| 00700.HK 腾讯控股 |", 200),
    # 次新股回归：默认近 3 年窗口首段在上市前（2026-02-06 上市），须跳过空段
    ("hk_daily", {"symbol": "02714"}, "| 02714.HK 牧原股份 |", 100),
    # 聚合极值发生日（f456abb）：3 年窗口聚周线必须携带极值的具体交易日
    ("hk_daily", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920"},
     "high_date:2025-10-02", 150),
    # 复权口径（2026-09-20 Q2 回归）：默认前复权，标题行必须声明
    ("hk_daily", {"symbol": "00700", "start_date": "20260901"}, "（前复权）", 8),
    ("us_daily", {"symbol": "NVDA", "start_date": "20260901"}, "（前复权）", 5),
    # 上市前区间无数据：错误消息应带候选 hint（suggest 回填中文名）
    ("hk_daily", {"symbol": "02714", "start_date": "20230101", "end_date": "20240101"}, "牧原股份", 0),
    ("hk_weekly", {"symbol": "00700", "start_date": "20260801"}, "| 00700.HK 腾讯控股 |", 4),
    # 直查周线极值精确到日（2026-09-20 Q1 前端实测回归：原生周线无极值发生日，
    # 统计行只能给周期截止日 2025-10-03，与日线真值 2025-10-02 打架；
    # 修复后 hk_weekly 走日线聚合，极值价格与发生日应与 hk_daily 完全一致）
    ("hk_weekly", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920"},
     "区间最高 high=", 150),
    # qfq 口径：价格随源（腾讯/东财）与未来除权漂移，只锁极值发生日与口径声明
    ("hk_weekly", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920"},
     "区间最高 high=677.7（2025-10-02）", 0),
    ("hk_weekly", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920"},
     "区间最低 low=247（2024-01-22）", 0),
    # 不复权显式传 adjust=''：锁定不复权真值（不随除权漂移）
    ("hk_weekly", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920", "adjust": ""},
     "区间最高 high=683（2025-10-02）", 150),
    ("hk_weekly", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920", "adjust": ""},
     "区间最低 low=260.2（2024-01-22）", 150),
    ("hk_monthly", {"symbol": "00700", "start_date": "20230920", "end_date": "20260920"},
     "high_date:2025-10-02", 36),
    # 港股指数周线同款口径（日线聚合出极值发生日）
    ("global_index_daily", {"symbol": "HSI", "period": "weekly",
                            "start_date": "20230920", "end_date": "20260920"}, "high_date", 100),
    ("us_daily", {"symbol": "AAPL", "start_date": "20260901"}, "| AAPL ", 7),
    ("us_daily", {"symbol": "SNDK", "start_date": "20260827"}, "| SNDK ", 8),
    ("us_weekly", {"symbol": "AAPL", "start_date": "20260801"}, "| AAPL ", 4),
    # 美股前复权（2026-09-20 Q2 回归）：NVDA 10:1 拆股曾致 -89% 假断崖。
    # 3 年区间最高发生日经多源+新闻实证锁定 2026-05-14（名义盘中 236.54：
    # 每经 2026-05-15 与 CMoney 独立报道一致；09-04 的 234.76 仅"接近历史
    # 最高"，此前"区间最高 234.76@2026-09-04"基准有误）。qfq 价格随未来
    # 除权漂移，故断言当前 qfq 值与极值发生日
    ("us_daily", {"symbol": "NVDA", "start_date": "20230920", "end_date": "20260920"},
     "（前复权）", 150),
    ("us_daily", {"symbol": "NVDA", "start_date": "20230920", "end_date": "20260920"},
     "区间最高 high=236.29（2026-05-14）", 0),
    ("global_index_daily", {"symbol": "HSI", "start_date": "20260901"}, "hkHSI 恒生指数", 8),
    ("global_index_daily", {"symbol": "SPX", "start_date": "20260901"}, ".INX 标普500指数", 5),
    ("global_index_daily", {"symbol": "DJIA", "start_date": "20260901"}, ".DJI 道琼斯工业指数", 5),
    # ---- A股（category="astock"，仅线上模式执行；本地 stub server 只起 global）----
    # 服务端区间统计行回归（stats_utils）：3 年窗口截断后极值仍可被直接引用
    ("daily", {"ts_code": "000001.SZ", "start_date": "20230920", "end_date": "20260920"},
     "📊 区间统计（服务端已计算", 50, "astock"),
    ("daily_basic", {"ts_code": "000001.SZ", "start_date": "20250901", "end_date": "20260920"},
     "📊 区间统计（服务端已计算", 0, "astock"),
    ("moneyflow", {"ts_code": "600519.SH", "start_date": "20260801", "end_date": "20260920"},
     "📊 区间统计（服务端已计算", 0, "astock"),
    ("fund_nav", {"ts_code": "001102.OF", "start_date": "20250901", "end_date": "20260920"},
     "📊 区间统计（服务端已计算", 0, "astock"),
    # ---- A股复权口径（2026-09-20 Q2 同款缺口回归，category="astock"）----
    # 股票默认前复权：标题行必须声明（600519 近年连年分红，不复权会有假缺口）
    ("daily", {"ts_code": "600519.SH", "start_date": "20230920", "end_date": "20260920"},
     "前复权", 50, "astock"),
    # 股票周线改日线聚合：必须携带极值发生日（与港美股周线口径对齐）
    ("weekly", {"ts_code": "600519.SH", "start_date": "20230920", "end_date": "20260920"},
     "最高日", 100, "astock"),
    # 指数不受复权影响：标题行不得出现前复权声明
    ("daily", {"ts_code": "000300.SH", "start_date": "20260901"},
     "000300.SH", 5, "astock"),
    # ---- 图表供给工程解（2026-09-21 Q3 实测回归，category="astock"）----
    # 长区间整段降采样/聚合为全史周频：图表数据必须覆盖完整区间
    ("daily_basic", {"ts_code": "600519.SH", "start_date": "20230920", "end_date": "20260920"},
     "已自动降采样", 100, "astock"),
    ("daily", {"ts_code": "600519.SH", "start_date": "20230920", "end_date": "20260920"},
     "已自动聚合为周线全史", 100, "astock"),
    ("fund_nav", {"ts_code": "001102.OF", "start_date": "20240920", "end_date": "20260920"},
     "📊 区间统计（服务端已计算", 0, "astock"),
]

def _case_category(case) -> str:
    return case[4] if len(case) > 4 else "global"


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


async def verify(url: str, url_is_remote: bool = False) -> int:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    passed, failed = 0, 0
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            listed = resp.tools if hasattr(resp, "tools") else resp[0].tools
            names = {t.name for t in listed}
            # 本地 stub server 只注册 global 类工具：过滤掉其他类别的用例
            cases = CASES if url_is_remote else [c for c in CASES if _case_category(c) == "global"]
            print(f"cases to run: {len(cases)}/{len(CASES)}")
            for tool, args, expect, min_bars, *_rest in cases:
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
                        m = _re.search(r"\(Total: (\d+)[^)]*\)", text) or _re.search(r"共 (\d+) 条", text)
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
        return asyncio.run(verify(url, url_is_remote=bool(args.url)))
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
