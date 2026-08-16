import unittest
from unittest import mock

import pandas as pd

from tools.stock.quote.quote_utils import (
    fetch_quote_data,
    format_quote_data,
    is_index_code,
    split_ts_codes,
)
from tools.stock.quote import daily as daily_module


class FakeProClient:
    def __init__(self):
        self.calls = []

    def daily(self, **params):
        self.calls.append(("daily", params))
        return pd.DataFrame(
            [{"ts_code": params["ts_code"], "trade_date": "20260801", "close": 10}]
        )

    def index_daily(self, **params):
        self.calls.append(("index_daily", params))
        return pd.DataFrame(
            [{"ts_code": params["ts_code"], "trade_date": "20260801", "close": 3000}]
        )


class QuoteUtilsTests(unittest.TestCase):
    def test_split_codes_removes_duplicates_and_whitespace(self):
        self.assertEqual(
            split_ts_codes(" 000001.SH ,399001.SZ，000001.SH "),
            ["000001.SH", "399001.SZ"],
        )

    def test_index_code_detection(self):
        self.assertTrue(is_index_code("000001.SH"))
        self.assertTrue(is_index_code("000300.SH"))
        self.assertTrue(is_index_code("399006.SZ"))
        self.assertFalse(is_index_code("000001.SZ"))
        self.assertFalse(is_index_code("600519.SH"))

    def test_mixed_codes_are_split_and_routed(self):
        pro = FakeProClient()
        df = fetch_quote_data(
            pro,
            stock_api="daily",
            index_api="index_daily",
            ts_code="000001.SZ,000001.SH",
            start_date="20260701",
            end_date="20260815",
        )

        self.assertEqual(len(df), 2)
        self.assertEqual(
            pro.calls,
            [
                ("daily", {"ts_code": "000001.SZ", "start_date": "20260701", "end_date": "20260815"}),
                ("index_daily", {"ts_code": "000001.SH", "start_date": "20260701", "end_date": "20260815"}),
            ],
        )

    def test_display_limit_is_per_code(self):
        dates = [str(20260101 + index) for index in range(60)]
        rows = []
        for code in ("000001.SH", "399001.SZ"):
            rows.extend({"ts_code": code, "trade_date": date, "close": 1} for date in dates)
        df = pd.DataFrame(rows)
        output = format_quote_data(df, "daily", ["000001.SH", "399001.SZ"])

        self.assertIn("Total: 120", output)
        self.assertEqual(output.count("代码:000001.SH"), 50)
        self.assertEqual(output.count("代码:399001.SZ"), 50)
        self.assertIn("每个代码仅显示最近 50 条", output)

    def test_daily_tool_routes_index_codes(self):
        pro = FakeProClient()
        container = {}

        class ToolCapture:
            def tool(self):
                def register(function):
                    container["daily"] = function
                    return function

                return register

        with mock.patch.object(daily_module, "get_pro_client", return_value=pro):
            daily_module.register_daily_tools(ToolCapture())
            output = container["daily"](
                ts_code="000001.SH,000001.SZ",
                start_date="20260701",
                end_date="20260815",
            )

        self.assertIn("代码:000001.SH", output)
        self.assertIn("代码:000001.SZ", output)
        self.assertEqual([name for name, _ in pro.calls], ["index_daily", "daily"])


if __name__ == "__main__":
    unittest.main()
