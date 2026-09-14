"""全球市场（港美股）工具测试。

离线部分：schema 注册、formatter、代码解析、限频熔断与缓存逻辑。
联网部分：默认跳过，设 RUN_NETWORK_TESTS=1 启用（依赖东财/SEC/披露易可达）。
"""

import os
import sys
import types
import unittest
from unittest import mock

# 本地开发环境可能未安装私有数据 SDK（tinyshare/minishare 来自私有源）。
# global_market 工具不直接使用它们，但 tools/__init__.py 的 import 链会加载；
# 缺包时注入空壳模块以便离线测试（真实环境中此处不生效）。
for _name in ("tinyshare", "minishare"):
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            _stub = types.ModuleType(_name)
            _stub.pro_api = lambda *a, **k: None
            sys.modules[_name] = _stub

import pandas as pd

from tools.global_market.em_client import (
    _EMClient, RateLimitedError, em_call, TTL_DAILY,
)
from tools.global_market.global_formatting import (
    format_generic_rows, format_indicator, format_kline, format_report,
)
from tools.global_market.symbol_resolver import INDEX_ALIASES, normalize_hk, resolve_index


def _register_global_tools():
    import asyncio

    from mcp.server.fastmcp import FastMCP

    from tools.global_market import register_global_market_tools

    async def run():
        mcp = FastMCP("global-test")
        register_global_market_tools(mcp)
        return {tool.name: tool for tool in await mcp.list_tools()}

    return asyncio.run(run())


class ToolSchemaTests(unittest.TestCase):
    def test_all_global_tools_registered(self):
        tools = _register_global_tools()
        expected = {
            "hk_daily", "hk_weekly", "hk_monthly",
            "us_daily", "us_weekly", "us_monthly",
            "global_index_daily",
            "hk_fina_indicator", "us_fina_indicator",
            "hk_income", "hk_balancesheet", "hk_cashflow",
            "us_income", "us_balancesheet", "us_cashflow",
            "search_symbol", "us_filings", "hk_announcements",
        }
        self.assertEqual(expected, set(tools.keys()))

    def test_required_params(self):
        tools = _register_global_tools()
        for name in ("hk_daily", "us_daily", "hk_fina_indicator", "us_filings",
                     "hk_announcements", "global_index_daily"):
            self.assertEqual(tools[name].inputSchema["required"], ["symbol"],
                             f"{name} should require only symbol")
        self.assertEqual(tools["search_symbol"].inputSchema["required"], ["query"])
        self.assertEqual(tools["us_fina_indicator"].inputSchema["required"], ["symbol"])

    def test_report_tools_have_docstring(self):
        tools = _register_global_tools()
        for name in ("hk_income", "us_balancesheet"):
            self.assertTrue(tools[name].description, f"{name} missing description")


class VendorLeakageTests(unittest.TestCase):
    """MCP 运行时可见面（工具描述/错误消息）不得暴露商业数据供应商。
    官方权威机构（SEC/披露易）不在限制内。"""

    BANNED = ("tushare", "akshare", "东财", "东方财富", "腾讯", "tinyshare",
              "minishare", "sina", "新浪", "eastmoney", "tencent", "gtimg", "ifzq")
    # 公司名示例（如 '00700'=腾讯控股）是代码格式的说明，不属于供应商泄漏
    COMPANY_NAME_WHITELIST = ("腾讯控股", "腾讯音乐", "特斯拉")

    def test_tool_descriptions_do_not_leak_vendors(self):
        tools = _register_global_tools()
        for name, tool in tools.items():
            desc = (tool.description or "").lower()
            for company in self.COMPANY_NAME_WHITELIST:
                desc = desc.replace(company.lower(), "")
            for banned in self.BANNED:
                self.assertNotIn(banned, desc, f"tool '{name}' leaks '{banned}'")

    def test_rate_limited_message_does_not_leak_group_name(self):
        import requests as _requests

        from tools.global_market import em_client as _em

        client = _EMClient()
        calls = []

        def fn():
            calls.append(1)
            raise _requests.exceptions.ConnectionError("reset")

        with mock.patch.object(_em, "_RETRY_BACKOFF", (0, 0)):
            for _ in range(3):
                with self.assertRaises(_requests.exceptions.ConnectionError):
                    client.call("eastmoney_datacenter", fn)
            with self.assertRaises(RateLimitedError) as ctx:
                client.call("eastmoney_datacenter", fn)
        for banned in ("eastmoney", "tencent", "数据源"):
            self.assertNotIn(banned, str(ctx.exception))
        self.assertIn("财务数据服务", str(ctx.exception))


class SymbolResolverTests(unittest.TestCase):
    def test_normalize_hk(self):
        self.assertEqual(normalize_hk("00700"), "00700")
        self.assertEqual(normalize_hk("700"), "00700")
        self.assertEqual(normalize_hk("0700.HK"), "00700")
        self.assertEqual(normalize_hk("hk0700"), "00700")
        self.assertIsNone(normalize_hk("AAPL"))
        self.assertIsNone(normalize_hk(""))

    def test_resolve_index(self):
        self.assertEqual(resolve_index("HSI"), ("hkHSI", "恒生指数"))
        self.assertEqual(resolve_index("恒指"), ("hkHSI", "恒生指数"))
        self.assertEqual(resolve_index("spx"), (".INX", "标普500指数"))
        self.assertIsNone(resolve_index("AAPL"))

    def test_index_aliases_unique_secids(self):
        secids = {v[0] for v in INDEX_ALIASES.values()}
        self.assertGreater(len(secids), 5)


class TxParamTests(unittest.TestCase):
    def test_param_shape(self):
        from tools.global_market.quote import _tx_param
        # 不复权：fq 段为空但保留尾逗号（腾讯 fqkline 约定；kline/get 端点已废弃）
        self.assertEqual(_tx_param("hk00700", "daily", "2026-09-01", "2026-09-13", ""),
                         "hk00700,day,2026-09-01,2026-09-13,800,")
        # 前复权/后复权
        self.assertTrue(_tx_param("hk00700", "daily", "a", "b", "qfq").endswith(",qfq"))
        self.assertTrue(_tx_param("usAAPL", "weekly", "a", "b", "hfq").endswith(",hfq"))
        self.assertIn("week", _tx_param("usAAPL", "weekly", "a", "b", "qfq"))


class TxKlinePaginationTests(unittest.TestCase):
    """分段拉取：上市前/停牌的空段应跳过而不是终止（hk02714 次新股回归）。"""

    def test_skips_pre_listing_empty_segments(self):
        from tools.global_market import quote

        real_bars = [["2026-02-06", "38.0", "40.5", "37.5", "40.0", "1000"],
                     ["2026-02-09", "40.0", "41.0", "39.5", "40.5", "1200"]]
        calls = []

        def fake_fetch(tx_code, period, seg_start, seg_end, adjust):
            calls.append((seg_start, seg_end))
            if seg_end <= "2025-11-22":
                return [], ""  # 上市前空段
            return list(real_bars), "牧原股份"

        with mock.patch.object(quote, "_tx_fetch_once", side_effect=fake_fetch):
            df, name = quote._fetch_tx_kline("hk02714", "daily", "2023-09-14", "2026-09-14", "")

        self.assertEqual(name, "牧原股份")
        self.assertEqual(len(df), 2)
        self.assertGreaterEqual(len(calls), 2)  # 空段后继续扫描而非 break

    def test_all_empty_returns_empty_df_with_name(self):
        from tools.global_market import quote

        with mock.patch.object(quote, "_tx_fetch_once", return_value=([], "")):
            df, name = quote._fetch_tx_kline("hk99999", "daily", "2026-01-01", "2026-02-01", "")
        self.assertTrue(df.empty)
        self.assertEqual(name, "")

    def test_returns_name_from_empty_segment(self):
        from tools.global_market import quote

        # 全区间无数据但 qt 带名称（代码有效、区间在上市前）
        with mock.patch.object(quote, "_tx_fetch_once", return_value=([], "牧原股份")):
            df, name = quote._fetch_tx_kline("hk02714", "daily", "2023-01-01", "2024-01-01", "")
        self.assertTrue(df.empty)
        self.assertEqual(name, "牧原股份")


class SuggestParseTests(unittest.TestCase):
    def test_parse_filters_and_market(self):
        from tools.global_market.symbol_resolver import _parse_suggest
        resp = {"QuotationCodeTable": {"Data": [
            {"Code": "002714", "Name": "牧原股份", "Classify": "AStock"},
            {"Code": "02714", "Name": "牧原股份", "Classify": "HK"},
            {"Code": "16542", "Name": "牧原华泰七六购A", "Classify": "HK"},
            {"Code": "AAPL", "Name": "苹果", "Classify": "UsStock"},
            {"Code": "BK0666", "Name": "苹果概念", "Classify": "BK"},
        ]}}
        rows = _parse_suggest(resp, "all", 10)
        self.assertEqual([r["code"] for r in rows], ["02714", "AAPL"])
        self.assertEqual(rows[0]["name"], "牧原股份")
        hk_only = _parse_suggest(resp, "hk", 10)
        self.assertEqual([r["code"] for r in hk_only], ["02714"])

    def test_parse_empty_and_malformed(self):
        from tools.global_market.symbol_resolver import _parse_suggest
        self.assertEqual(_parse_suggest({}, "all", 10), [])
        self.assertEqual(_parse_suggest({"QuotationCodeTable": {"Data": None}}, "all", 10), [])


class SearchFallbackTests(unittest.TestCase):
    def test_clist_miss_falls_back_to_suggest(self):
        from tools.global_market import symbol_resolver as sr
        with mock.patch.object(sr, "_load_hk_list", return_value=[]), \
             mock.patch.object(sr, "_load_us_list", return_value=[]), \
             mock.patch.object(sr, "_suggest_search",
                               return_value=[{"market": "HK", "code": "02714", "name": "牧原股份"}]):
            rows = sr.search_symbols("牧原", market="hk")
        self.assertEqual(rows[0]["code"], "02714")
        self.assertEqual(rows[0]["name"], "牧原股份")

    def test_clist_failure_degrades_to_suggest(self):
        from tools.global_market import symbol_resolver as sr

        def _boom():
            raise RuntimeError("circuit open")

        with mock.patch.object(sr, "_load_hk_list", side_effect=_boom), \
             mock.patch.object(sr, "_load_us_list", side_effect=_boom), \
             mock.patch.object(sr, "_suggest_search",
                               return_value=[{"market": "HK", "code": "00700", "name": "腾讯控股"}]):
            rows = sr.search_symbols("腾讯", market="hk")
        self.assertEqual(rows[0]["name"], "腾讯控股")

    def test_suggest_failure_falls_back_to_passthrough(self):
        from tools.global_market import symbol_resolver as sr

        def _boom(*a, **k):
            raise RuntimeError("down")

        with mock.patch.object(sr, "_load_hk_list", return_value=[]), \
             mock.patch.object(sr, "_load_us_list", return_value=[]), \
             mock.patch.object(sr, "_suggest_search", side_effect=_boom):
            rows = sr.search_symbols("02714", market="hk")
        self.assertEqual(rows, [{"market": "HK", "code": "02714", "name": "02714"}])


class FormattingTests(unittest.TestCase):
    def _kline_df(self):
        return pd.DataFrame({
            "日期": ["2026-09-10", "2026-09-11"],
            "开盘": [420.0, 419.4], "收盘": [422.0, 425.6],
            "最高": [425.0, 430.8], "最低": [418.0, 419.4],
            "成交量": [15000000.0, 15628379.0],
            "成交额": [6.3e9, 6.67e9],
            "涨跌幅": [0.5, 0.658],
        })

    def test_format_kline(self):
        out = format_kline(self._kline_df(), "港股日线行情", "港元", "00700.HK", "腾讯控股")
        self.assertIn("--- 港股日线行情 (Total: 2) ---", out)
        self.assertIn("日期:2026-09-11 | 代码:00700.HK | 名称:腾讯控股", out)
        self.assertIn("收盘:425.6", out)
        self.assertIn("成交量:15628379股", out)
        self.assertIn("成交额:6,670,000,000.00港元", out)

    def test_format_kline_empty(self):
        self.assertEqual(format_kline(pd.DataFrame(), "港股日线行情", "港元", "x", "y"),
                         "未找到港股日线行情数据")

    def test_format_indicator(self):
        df = pd.DataFrame({
            "SECUCODE": ["00700.HK"], "SECURITY_CODE": ["00700"],
            "SECURITY_NAME_ABBR": ["腾讯控股"], "REPORT_DATE": ["2025-12-31 00:00:00"],
            "CURRENCY": ["人民币"], "ROE_AVG": [21.13], "GROSS_PROFIT_RATIO": [56.21],
            "BASIC_EPS": [24.97], "MISSING_FIELD": [1],
        })
        out = format_indicator(df, [("ROE_AVG", "ROE"), ("GROSS_PROFIT_RATIO", "毛利率"),
                                    ("BASIC_EPS", "EPS")], "港股主要财务指标")
        self.assertIn("报告期:2025-12-31", out)
        self.assertIn("ROE:21.13%", out)
        self.assertIn("毛利率:56.21%", out)
        self.assertNotIn("MISSING_FIELD", out)

    def test_format_report_pivots_items(self):
        df = pd.DataFrame({
            "SECUCODE": ["00700.HK"] * 2, "SECURITY_NAME_ABBR": ["腾讯控股"] * 2,
            "REPORT_DATE": ["2025-12-31 00:00:00"] * 2,
            "STD_ITEM_NAME": ["营业额", "毛利"], "AMOUNT": [396431000000.0, 229698000000.0],
        })
        out = format_report(df, "STD_ITEM_NAME", "AMOUNT", "港股利润表", limit=2)
        self.assertIn("报告期:2025-12-31", out)
        self.assertIn("营业额:396,431,000,000", out)
        self.assertIn("毛利:229,698,000,000", out)

    def test_format_generic_rows(self):
        out = format_generic_rows("股票代码搜索", [{"市场": "HK", "代码": "00700", "名称": "腾讯控股"}])
        self.assertIn("市场:HK | 代码:00700 | 名称:腾讯控股", out)
        self.assertEqual(format_generic_rows("搜索", []), "未找到搜索数据")


class EMClientTests(unittest.TestCase):
    def test_cache_hits_and_fn_called_once(self):
        client = _EMClient()
        calls = []

        def fn():
            calls.append(1)
            return pd.DataFrame({"a": [1]})

        r1 = client.call("sec_edgar", fn, cache_key="k", ttl_seconds=60)
        r2 = client.call("sec_edgar", fn, cache_key="k", ttl_seconds=60)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(r1), len(r2))

    def test_dataframe_copy_on_cache_hit(self):
        client = _EMClient()
        df = pd.DataFrame({"a": [1]})
        r1 = client.call("sec_edgar", lambda: df, cache_key="k", ttl_seconds=60)
        r1["a"] = [999]  # 修改返回值不应污染缓存
        r2 = client.call("sec_edgar", lambda: df, cache_key="k", ttl_seconds=60)
        self.assertEqual(r2["a"].tolist(), [1])

    def test_circuit_opens_after_consecutive_failures(self):
        import requests as _requests

        from tools.global_market import em_client as _em

        client = _EMClient()
        boom = _requests.exceptions.ConnectionError("reset")
        calls = []

        def fn():
            calls.append(1)
            raise boom

        with mock.patch.object(_em, "_RETRY_BACKOFF", (0, 0)):
            for _ in range(3):  # 阈值 3：一次 call 内部重试耗尽计一次调用级失败
                with self.assertRaises(_requests.exceptions.ConnectionError):
                    client.call("hkex", fn)
            with self.assertRaises(RateLimitedError):
                client.call("hkex", fn)
        # 每次 call 内部尝试 3 次（首次 + 2 重试）
        self.assertEqual(len(calls), 9)

    def test_transient_connection_error_recovers_without_circuit_count(self):
        import requests as _requests

        from tools.global_market import em_client as _em

        client = _EMClient()
        state = {"n": 0}

        def flaky():
            state["n"] += 1
            if state["n"] == 1:
                raise _requests.exceptions.ConnectionError("cold start reset")
            return "ok"

        with mock.patch.object(_em, "_RETRY_BACKOFF", (0,)):
            self.assertEqual(client.call("hkex", flaky), "ok")
        # 首连抖动被内部重试消化，未计入熔断
        self.assertEqual(client._groups["hkex"].consecutive_failures, 0)

    def test_data_error_does_not_trip_circuit(self):
        client = _EMClient()
        with self.assertRaises(ValueError):
            client.call("hkex", lambda: (_ for _ in ()).throw(ValueError("bad data")))
        # 数据类异常不计入熔断：下一次仍正常执行
        self.assertEqual(client.call("hkex", lambda: "ok"), "ok")

    def test_em_call_module_entry(self):
        self.assertEqual(em_call("sec_edgar", lambda: 42, cache_key="", ttl_seconds=0), 42)

    def test_ttl_reexpiry(self):
        client = _EMClient()
        calls = []
        client.call("sec_edgar", lambda: calls.append(1) or 1,
                    cache_key="k", ttl_seconds=TTL_DAILY)
        client._cache["k"] = (0.0, 1)  # 强制过期
        client.call("sec_edgar", lambda: calls.append(1) or 2,
                    cache_key="k", ttl_seconds=TTL_DAILY)
        self.assertEqual(len(calls), 2)


_RUN_NETWORK = os.environ.get("RUN_NETWORK_TESTS") == "1"


@unittest.skipUnless(_RUN_NETWORK, "set RUN_NETWORK_TESTS=1 to run network tests")
class NetworkIntegrationTests(unittest.TestCase):
    """联网冒烟：财务组（datacenter）与公告（EDGAR/披露易）当前可测；
    行情组（push2his）视所在 IP 的限流状态。"""

    def test_hk_fina_indicator(self):
        from tools.global_market.finance import _fetch_hk_indicator
        df = _fetch_hk_indicator("00700", "年度")
        self.assertFalse(df.empty)
        self.assertIn("ROE_AVG", df.columns)

    def test_us_fina_indicator(self):
        from tools.global_market.finance import _fetch_us_indicator
        df = _fetch_us_indicator("AAPL", "年报")
        self.assertFalse(df.empty)

    def test_us_filings(self):
        from tools.global_market.announcements import _fetch_us_filings
        rows = _fetch_us_filings("AAPL", "", 5)
        self.assertGreaterEqual(len(rows), 3)
        self.assertIn("类型", rows[0])

    def test_hk_announcements(self):
        from tools.global_market.announcements import _fetch_hk_announcements, _hkex_stock_id
        stock_id = _hkex_stock_id("00700")
        self.assertTrue(stock_id)
        rows = _fetch_hk_announcements(stock_id, 30, 5)
        self.assertGreaterEqual(len(rows), 1)

    def test_hk_kline(self):
        from tools.global_market.quote import _fetch_tx_kline
        df, name = _fetch_tx_kline("hk00700", "daily", "2026-09-01", "2026-09-13", "")
        self.assertFalse(df.empty)
        self.assertEqual(name, "腾讯控股")

    def test_hk_kline_new_listing_default_window(self):
        # 次新股回归：默认 3 年窗口首段在上市前，不得误报无数据
        from tools.global_market.quote import _fetch_tx_kline
        df, name = _fetch_tx_kline("hk02714", "daily", "2026-01-01", "2026-09-14", "")
        self.assertFalse(df.empty)
        self.assertEqual(name, "牧原股份")

    def test_suggest_search_online(self):
        from tools.global_market.symbol_resolver import _suggest_search
        rows = _suggest_search("牧原", "hk", 10)
        self.assertTrue(any(r["code"] == "02714" and r["name"] == "牧原股份" for r in rows))


if __name__ == "__main__":
    unittest.main()
