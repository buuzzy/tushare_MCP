"""服务端区间统计行回归测试（daily_basic / moneyflow / fund_nav）。

原则：极值/合计等"扫描大量数值行"的活由代码完成，工具输出必须附带
可直接引用的统计行（tools/stats_utils.py 约定），模型不得自行扫描。
"""

import unittest
from unittest import mock

import pandas as pd

from tools.stock.quote import daily_basic as daily_basic_module
from tools.stock.finance import moneyflow as moneyflow_module
from tools.fund import fund_nav as fund_nav_module


class _CaptureInto:
    """最小 mcp stub：捕获 @mcp.tool() 注册的函数。"""

    def __init__(self, container: dict):
        self.container = container

    def tool(self):
        def register(function):
            self.container[function.__name__] = function
            return function

        return register


class DailyBasicStatsTests(unittest.TestCase):
    def test_appends_valuation_stats_over_full_df(self):
        pro = mock.Mock()
        rows = []
        for i in range(60):
            rows.append({
                "ts_code": "000001.SZ",
                "trade_date": str(20260101 + i),
                "close": 10,
                "pe_ttm": 20,
                "pb": 2,
                "total_mv": 1000,
            })
        rows[3]["pe_ttm"] = 88.8  # 最早段（不在显示的最近 50 条内）
        rows[-1]["pb"] = 0.5
        pro.daily_basic.return_value = pd.DataFrame(rows)

        container = {}
        with mock.patch.object(daily_basic_module, "get_pro_client", return_value=pro):
            daily_basic_module.register_daily_basic_tools(_CaptureInto(container))
            output = container["daily_basic"](
                ts_code="000001.SZ", start_date="20260101", end_date="20260301"
            )

        self.assertIn("📊 区间统计（服务端已计算", output)
        self.assertIn("PE(TTM) 最高 88.8（20260104）", output)
        self.assertIn("PB 最高 2（", output)
        self.assertIn("/ 最低 0.5（", output)


class MoneyflowStatsTests(unittest.TestCase):
    def test_appends_flow_summary(self):
        pro = mock.Mock()
        rows = [
            {"ts_code": "600519.SH", "trade_date": "20260910", "net_mf_amount": 1.2e8},
            {"ts_code": "600519.SH", "trade_date": "20260911", "net_mf_amount": -3.4e8},
            {"ts_code": "600519.SH", "trade_date": "20260912", "net_mf_amount": 0.5e8},
        ]
        pro.moneyflow.return_value = pd.DataFrame(rows[::-1])  # API 倒序返回

        container = {}
        with mock.patch.object(moneyflow_module, "get_pro_client", return_value=pro):
            moneyflow_module.register_moneyflow_tools(_CaptureInto(container))
            output = container["moneyflow"](ts_code="600519.SH")

        self.assertIn("📊 区间统计（服务端已计算", output)
        self.assertIn("区间主力净流出合计 -1.70亿", output)
        self.assertIn("最大单日净流入 1.20亿（20260910）", output)
        self.assertIn("最大单日净流出 -3.40亿（20260911）", output)


class FundNavStatsTests(unittest.TestCase):
    def test_appends_nav_extremes(self):
        pro = mock.Mock()
        rows = [
            {"ts_code": "001102.OF", "nav_date": "20260910", "unit_nav": 1.5, "adj_nav": 2.5},
            {"ts_code": "001102.OF", "nav_date": "20260911", "unit_nav": 1.6, "adj_nav": 2.9},
            {"ts_code": "001102.OF", "nav_date": "20260912", "unit_nav": 1.4, "adj_nav": 2.1},
        ]
        pro.fund_nav.return_value = pd.DataFrame(rows[::-1])

        container = {}
        with mock.patch.object(fund_nav_module, "get_pro_client", return_value=pro):
            fund_nav_module.register_fund_nav_tools(_CaptureInto(container))
            output = container["fund_nav"](ts_code="001102.OF")

        self.assertIn("📊 区间统计（服务端已计算", output)
        self.assertIn("区间最高 复权净值=2.9（20260911）", output)
        self.assertIn("区间最低 复权净值=2.1（20260912）", output)
        self.assertIn("最新 20260912 复权净值=2.1", output)


if __name__ == "__main__":
    unittest.main()
