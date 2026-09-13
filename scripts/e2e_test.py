"""Sage 端到端测试：模拟用户在 app 里的提问，验证港美股工具链路。

凭证从环境变量读取（不落盘）：
    SAGE_TEST_EMAIL / SAGE_TEST_PASSWORD  测试账号（必需）
    SAGE_SUPABASE_URL / SAGE_SUPABASE_ANON_KEY  覆盖默认值（可选）

用法: .venv/bin/python scripts/e2e_test.py [case_no ...]
"""

import json
import os
import re
import sys

import requests

SUPABASE_URL = os.environ.get(
    "SAGE_SUPABASE_URL", "https://wymqgwtagpsjuonsclye.supabase.co")
SUPABASE_ANON_KEY = os.environ["SAGE_SUPABASE_ANON_KEY"] if "SAGE_SUPABASE_ANON_KEY" in os.environ else None
AGENT_URL = os.environ.get("SAGE_AGENT_URL", "https://sage.nakocai.com/agent")
TEST_EMAIL = os.environ.get("SAGE_TEST_EMAIL", "")
TEST_PASSWORD = os.environ.get("SAGE_TEST_PASSWORD", "")

# (提示词, 期望工具, 禁用工具, 期望文本)
CASES = {
    1: ("腾讯控股最近一个月的股价走势如何？画个图",
        ["hk_daily"], [], ["腾讯"]),
    2: ("苹果公司最近三个财年的营收和净利润表现怎么样？",
        ["us_fina_indicator", "us_income"], [], []),
    3: ("恒生指数和标普500今年以来走势对比，用图表展示",
        ["global_index_daily"], [], []),
    4: ("港股比亚迪股份(01211)最近有什么公告？",
        ["hk_announcement"], [], ["比亚迪"]),
    5: ("查询 SNDK 最近10个交易日的行情",
        ["us_daily"], [], ["闪迪"]),
}


def login() -> str:
    headers = {"Content-Type": "application/json"}
    if SUPABASE_ANON_KEY:
        headers["apikey"] = SUPABASE_ANON_KEY
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=headers,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def run_case(token: str, case_no: int) -> bool:
    prompt, expect_tools, forbid_tools, expect_texts = CASES[case_no]
    print(f"\n===== Case {case_no}: {prompt} =====")
    raw_chunks: list[bytes] = []
    tool_calls = []
    with requests.post(
        AGENT_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"prompt": prompt},
        stream=True,
        timeout=300,
    ) as resp:
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        for raw in resp.iter_lines():  # bytes：避免 SSE 分片截断多字节字符
            if not raw:
                continue
            raw_chunks.append(raw + b"\n")
            line = raw.decode("utf-8", errors="ignore")
            for m in re.finditer(r'"(?:toolName|tool_name|name)"\s*:\s*"([a-z_0-9]+)"', line):
                if m.group(1) != "render_canvas":
                    tool_calls.append(m.group(1))

    tool_seq = list(dict.fromkeys(tool_calls))
    print(f"  工具调用序列: {tool_seq or '(无)'}")
    full_text = b"".join(raw_chunks).decode("utf-8", errors="ignore")

    ok = True
    for expect in expect_tools:
        hit = any(expect in t for t in tool_seq)
        print(f"  {'PASS' if hit else 'FAIL'}  期望工具 {expect}: {'命中' if hit else '未命中'}")
        ok = ok and hit
    for forbid in forbid_tools:
        bad = forbid in tool_seq
        print(f"  {'FAIL' if bad else 'PASS'}  禁用工具 {forbid}: {'被调用了!' if bad else '未使用'}")
        ok = ok and not bad
    for text in expect_texts:
        hit = text in full_text
        print(f"  {'PASS' if hit else 'FAIL'}  文本包含 '{text}': {'是' if hit else '否'}")
        ok = ok and hit
    return ok


def main() -> int:
    if not TEST_EMAIL or not TEST_PASSWORD:
        print("需要 SAGE_TEST_EMAIL / SAGE_TEST_PASSWORD 环境变量")
        return 2
    case_nos = [int(a) for a in sys.argv[1:]] or sorted(CASES)
    token = login()
    print(f"登录成功（token {token[:12]}...）")
    results = {no: run_case(token, no) for no in case_nos}
    print("\n===== 汇总 =====")
    for no, ok in results.items():
        print(f"  Case {no}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
