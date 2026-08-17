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

    def sw_daily(self, **params):
        self.calls.append(("sw_daily", params))
        return pd.DataFrame(
            [
                {
                    "ts_code": params["ts_code"],
                    "trade_date": "20260810",
                    "name": "电子",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "vol": 10,
                    "amount": 1000,
                },
                {
                    "ts_code": params["ts_code"],
                    "trade_date": "20260814",
                    "name": "电子",
                    "open": 100,
                    "high": 103,
                    "low": 100,
                    "close": 102,
                    "vol": 15,
                    "amount": 1500,
                },
            ]
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
        self.assertTrue(is_index_code("801080.SI"))
        self.assertFalse(is_index_code("000001.SZ"))
        self.assertFalse(is_index_code("600519.SH"))

    def test_mixed_codes_are_split_and_routed(self):
        pro = FakeProClient()
        df = fetch_quote_data(
            pro,
            stock_api="daily",
            index_api="index_daily",
            period="daily",
            ts_code="000001.SZ,000001.SH,801080.SI",
            start_date="20260701",
            end_date="20260815",
        )

        sw_rows = df[df["ts_code"] == "801080.SI"]
        self.assertEqual(len(sw_rows), 2)
        self.assertEqual(sw_rows.iloc[0]["open"], 100)
        self.assertEqual(sw_rows["high"].max(), 103)
        self.assertEqual(sw_rows["low"].min(), 99)
        self.assertEqual(sw_rows.iloc[-1]["close"], 102)
        self.assertEqual(sw_rows["vol"].sum(), 25)
        self.assertEqual(
            pro.calls,
            [
                ("daily", {"ts_code": "000001.SZ", "start_date": "20260701", "end_date": "20260815"}),
                ("index_daily", {"ts_code": "000001.SH", "start_date": "20260701", "end_date": "20260815"}),
                ("sw_daily", {"ts_code": "801080.SI", "start_date": "20260701", "end_date": "20260815"}),
            ],
        )

    def test_sw_daily_aggregates_weekly_bars(self):
        pro = FakeProClient()
        df = fetch_quote_data(
            pro,
            stock_api="weekly",
            index_api="index_weekly",
            period="weekly",
            ts_code="801080.SI",
            start_date="20260801",
            end_date="20260815",
        )

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["trade_date"], "20260814")
        self.assertEqual(df.iloc[0]["open"], 100)
        self.assertEqual(df.iloc[0]["high"], 103)
        self.assertEqual(df.iloc[0]["low"], 99)
        self.assertEqual(df.iloc[0]["close"], 102)
        self.assertEqual(df.iloc[0]["vol"], 25)

    def test_sw_daily_aggregates_monthly_bars(self):
        pro = mock.Mock()
        pro.sw_daily.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "801080.SI",
                    "trade_date": "20260731",
                    "name": "电子",
                    "open": 98,
                    "high": 101,
                    "low": 97,
                    "close": 100,
                    "vol": 100,
                    "amount": 10000,
                    "pct_change": 1.0,
                },
                {
                    "ts_code": "801080.SI",
                    "trade_date": "20260831",
                    "name": "电子",
                    "open": 100,
                    "high": 103,
                    "low": 99,
                    "close": 102,
                    "vol": 120,
                    "amount": 12000,
                    "pct_change": 2.0,
                },
            ]
        )

        df = fetch_quote_data(
            pro,
            stock_api="monthly",
            index_api="index_monthly",
            period="monthly",
            ts_code="801080.SI",
            start_date="20260701",
            end_date="20260831",
        )

        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[-1]["pre_close"], 100)
        self.assertEqual(df.iloc[-1]["change"], 2)
        self.assertAlmostEqual(df.iloc[-1]["pct_chg"], 2.0)

    def test_empty_sw_result_keeps_other_code_results(self):
        pro = mock.Mock()
        pro.daily.return_value = pd.DataFrame(
            [{"ts_code": "000001.SZ", "trade_date": "20260814", "close": 10}]
        )
        pro.sw_daily.return_value = pd.DataFrame()

        df = fetch_quote_data(
            pro,
            stock_api="daily",
            index_api="index_daily",
            period="daily",
            ts_code="000001.SZ,801080.SI",
            trade_date="20260814",
        )

        self.assertEqual(df["ts_code"].tolist(), ["000001.SZ"])
        pro.sw_daily.assert_called_once_with(trade_date="20260814", ts_code="801080.SI")

    def test_format_lists_missing_requested_codes(self):
        df = pd.DataFrame([{"ts_code": "801080.SI", "trade_date": "20260814"}])

        output = format_quote_data(df, "daily", ["801080.SI", "801020.SI"])

        self.assertIn("未找到代码:801020.SI", output)

    def test_display_limit_is_per_code(self):
        dates = [str(20260101 + index) for index in range(60)]
        rows = []
        for code in ("000001.SH", "399001.SZ"):
            rows.extend({"ts_code": code, "trade_date": date, "close": 1} for date in dates)
        df = pd.DataFrame(rows)
        output = format_quote_data(df, "daily", ["000001.SH", "399001.SZ"])

        self.assertIn("Total: 120", output)
        self.assertIn("名称:", format_quote_data(
            pd.DataFrame([{"ts_code": "801080.SI", "trade_date": "20260814", "name": "电子"}]),
            "daily",
            ["801080.SI"],
        ))
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
