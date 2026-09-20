import datetime as dt
import unittest
from unittest import mock

import pandas as pd

from tools.stock.quote.quote_utils import (
    fetch_quote_data,
    format_quote_data,
    is_index_code,
    normalize_adjust,
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

    def adj_factor(self, **params):
        self.calls.append(("adj_factor", params))
        today = dt.date.today().strftime("%Y%m%d")
        return pd.DataFrame(
            [
                {"ts_code": params["ts_code"], "trade_date": "20260801", "adj_factor": 1.0},
                {"ts_code": params["ts_code"], "trade_date": today, "adj_factor": 1.0},
            ]
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
            [(name, params["ts_code"]) for name, params in pro.calls],
            [
                ("daily", "000001.SZ"),
                ("adj_factor", "000001.SZ"),
                ("index_daily", "000001.SH"),
                ("sw_daily", "801080.SI"),
            ],
        )
        # 股票侧默认前复权：因子 1.0 时价格不变，口径已声明
        self.assertEqual(df.attrs["adjust"], "qfq")

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

    def test_format_appends_interval_stats_per_code(self):
        # 多代码：每个代码一条服务端统计行（极值/涨跌幅/最新收盘）
        rows = []
        for code, base in (("000001.SZ", 10.0), ("399001.SZ", 3000.0)):
            for i, day in enumerate(["20260105", "20260106", "20260107"]):
                rows.append({
                    "ts_code": code,
                    "trade_date": day,
                    "open": base,
                    "high": base + 1 + i,
                    "low": base - 1,
                    "close": base + i,
                })
        df = pd.DataFrame(rows)

        output = format_quote_data(df, "daily", ["000001.SZ", "399001.SZ"])

        self.assertIn("📊 区间统计（服务端已计算，直接引用即可，无需自行扫描或补查）[000001.SZ]", output)
        self.assertIn("区间最高 high=13（20260107）", output)
        self.assertIn("区间最低 low=9（20260105）", output)
        self.assertIn("最新 20260107 收 12", output)
        self.assertIn("[399001.SZ]", output)

    def test_interval_stats_cover_rows_omitted_by_display_limit(self):
        # 关键回归：极值落在被截断省略的行里，统计行仍必须包含
        dates = [str(20260101 + index) for index in range(60)]
        rows = [{"ts_code": "000001.SZ", "trade_date": d, "high": 1, "low": 1, "close": 1} for d in dates]
        rows[2]["high"] = 999  # 最早 3 号（不在显示的最近 50 条内）
        rows[-1]["low"] = 0.01
        df = pd.DataFrame(rows)

        output = format_quote_data(df, "daily", ["000001.SZ"])

        self.assertIn("high=999（20260103）", output)
        self.assertIn("low=0.01", output)
        self.assertIn("区间涨跌幅", output)

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
        self.assertEqual([name for name, _ in pro.calls], ["index_daily", "daily", "adj_factor"])


def _make_adj_pro(daily_rows, factor_rows):
    """构造带复权因子的 mock pro：daily/adj_factor 返回给定行。"""
    pro = mock.Mock()
    pro.daily.return_value = pd.DataFrame(daily_rows)
    pro.adj_factor.return_value = pd.DataFrame(factor_rows)
    return pro


class AShareAdjustmentTests(unittest.TestCase):
    """A 股默认前复权 + 周月线日线聚合（2026-09-20 Q2 复权缺口回归）。"""

    TODAY = dt.date.today().strftime("%Y%m%d")

    def _daily_and_factors(self):
        daily_rows = [
            # 除权日（10送10）：股价减半、因子翻倍（固定同周日期，便于周线聚合）
            {"ts_code": "000001.SZ", "trade_date": "20260105", "open": 20.0, "high": 21.0,
             "low": 19.0, "close": 20.0, "pre_close": 19.5, "change": 0.5, "pct_chg": 2.56,
             "vol": 100, "amount": 2000},
            {"ts_code": "000001.SZ", "trade_date": "20260106", "open": 10.0, "high": 10.5,
             "low": 9.5, "close": 10.2, "pre_close": 10.0, "change": 0.2, "pct_chg": 2.0,
             "vol": 110, "amount": 2200},
            {"ts_code": "000001.SZ", "trade_date": "20260107", "open": 10.4, "high": 11.0,
             "low": 10.1, "close": 11.0, "pre_close": 10.2, "change": 0.8, "pct_chg": 7.84,
             "vol": 120, "amount": 2400},
        ]
        factor_rows = [
            {"ts_code": "000001.SZ", "trade_date": "20260105", "adj_factor": 0.5},
            {"ts_code": "000001.SZ", "trade_date": "20260106", "adj_factor": 1.0},
            {"ts_code": "000001.SZ", "trade_date": "20260107", "adj_factor": 1.0},
            {"ts_code": "000001.SZ", "trade_date": self.TODAY, "adj_factor": 1.0},
        ]
        return daily_rows, factor_rows

    def test_qfq_removes_exrights_cliff(self):
        daily_rows, factor_rows = self._daily_and_factors()
        pro = _make_adj_pro(daily_rows, factor_rows)

        df = fetch_quote_data(
            pro, stock_api="daily", index_api="index_daily", period="daily",
            ts_code="000001.SZ", start_date="20260101",
        )

        # 前复权：除权日前价格 × (0.5/1.0)，10 送 10 的 -50% 假断崖消失
        self.assertAlmostEqual(df.iloc[0]["close"], 10.0)
        self.assertAlmostEqual(df.iloc[0]["high"], 10.5)
        # 最新日以最新因子为基准，价格保持真实价
        self.assertAlmostEqual(df.iloc[-1]["close"], 11.0)
        self.assertEqual(df.attrs["adjust"], "qfq")

    def test_hfq_scales_by_cumulative_factor(self):
        daily_rows, factor_rows = self._daily_and_factors()
        pro = _make_adj_pro(daily_rows, factor_rows)

        df = fetch_quote_data(
            pro, stock_api="daily", index_api="index_daily", period="daily",
            ts_code="000001.SZ", start_date="20260101", adjust="hfq",
        )

        # 后复权：价格 × 累计因子
        self.assertAlmostEqual(df.iloc[0]["close"], 10.0)
        self.assertAlmostEqual(df.iloc[1]["close"], 10.2)
        self.assertEqual(df.attrs["adjust"], "hfq")

    def test_unadjusted_when_explicitly_disabled(self):
        daily_rows, factor_rows = self._daily_and_factors()
        pro = _make_adj_pro(daily_rows, factor_rows)

        df = fetch_quote_data(
            pro, stock_api="daily", index_api="index_daily", period="daily",
            ts_code="000001.SZ", start_date="20260101", adjust="",
        )

        self.assertAlmostEqual(df.iloc[0]["close"], 20.0)
        self.assertEqual(df.attrs["adjust"], "")

    def test_weekly_stock_aggregates_from_daily_with_extreme_dates(self):
        daily_rows, factor_rows = self._daily_and_factors()
        pro = _make_adj_pro(daily_rows, factor_rows)

        df = fetch_quote_data(
            pro, stock_api="weekly", index_api="index_weekly", period="weekly",
            ts_code="000001.SZ", start_date="20260101",
        )

        # 全部日线落在同一自然周（2026-01-05 周一）：一根周线
        self.assertEqual(len(df), 1)
        row = df.iloc[0]
        # qfq 后当周最高为 0107 的 11.0（最新因子日原价保留），发生日精确到日
        self.assertAlmostEqual(row["high"], 11.0)
        self.assertEqual(row["high_date"], "20260107")
        self.assertAlmostEqual(row["low"], 9.5)
        self.assertEqual(row["low_date"], "20260105")
        self.assertEqual(df.attrs["adjust"], "qfq")

    def test_index_codes_bypass_adjustment(self):
        pro = _make_adj_pro([], [])
        pro.index_daily.return_value = pd.DataFrame(
            [{"ts_code": "000001.SH", "trade_date": self.TODAY, "close": 3000}]
        )

        df = fetch_quote_data(
            pro, stock_api="daily", index_api="index_daily", period="daily",
            ts_code="000001.SH", start_date="20260101",
        )

        self.assertAlmostEqual(df.iloc[0]["close"], 3000)
        pro.adj_factor.assert_not_called()

    def test_adjust_factor_failure_degrades_honestly(self):
        daily_rows, _ = self._daily_and_factors()
        pro = _make_adj_pro(daily_rows, [])
        pro.adj_factor.side_effect = ValueError("接口故障")

        df = fetch_quote_data(
            pro, stock_api="daily", index_api="index_daily", period="daily",
            ts_code="000001.SZ", start_date="20260101",
        )

        # 因子不可用：降级不复权，但口径声明必须如实（不虚标前复权）
        self.assertAlmostEqual(df.iloc[0]["close"], 20.0)
        self.assertEqual(df.attrs["adjust"], "")

    def test_normalize_adjust_defaults_to_qfq(self):
        self.assertEqual(normalize_adjust(""), "")
        self.assertEqual(normalize_adjust("qfq"), "qfq")
        self.assertEqual(normalize_adjust("hfq"), "hfq")
        self.assertEqual(normalize_adjust("whatever"), "qfq")

    def test_qfq_base_factor_uses_latest_when_window_ends_in_past(self):
        # 区间止于过去（除权后又除权）：基准因子必须取全历史最新，否则漏调
        daily_rows = [
            {"ts_code": "000001.SZ", "trade_date": "20260105", "open": 20.0, "high": 21.0,
             "low": 19.0, "close": 20.0, "pre_close": 19.5, "change": 0.5, "pct_chg": 2.56,
             "vol": 100, "amount": 2000},
        ]
        factor_rows = [
            {"ts_code": "000001.SZ", "trade_date": "20260105", "adj_factor": 0.5},
            {"ts_code": "000001.SZ", "trade_date": self.TODAY, "adj_factor": 1.0},
        ]
        pro = _make_adj_pro(daily_rows, factor_rows)

        df = fetch_quote_data(
            pro, stock_api="daily", index_api="index_daily", period="daily",
            ts_code="000001.SZ", start_date="20260101", end_date="20260106",
        )

        # 基准=今日因子 1.0 → 区间内 0.5 因子日 ×0.5
        self.assertAlmostEqual(df.iloc[0]["close"], 10.0)


class AShareFormatTests(unittest.TestCase):
    def _weekly_rows(self):
        return pd.DataFrame([
            {"ts_code": "000001.SZ", "trade_date": "20260109", "open": 10.0, "high": 12.0,
             "low": 9.0, "close": 11.0, "pre_close": None, "change": None, "pct_chg": None,
             "vol": 100, "amount": 1000, "high_date": "20260107", "low_date": "20260106"},
        ])

    def test_format_declares_adjust_suffix(self):
        output = format_quote_data(self._weekly_rows(), "weekly", ["000001.SZ"], adjust="qfq")
        self.assertIn("(Total: 1，前复权)", output)

    def test_format_uses_extreme_dates_from_columns(self):
        output = format_quote_data(self._weekly_rows(), "weekly", ["000001.SZ"])
        self.assertIn("区间最高 high=12（20260107）", output)
        self.assertIn("区间最低 low=9（20260106）", output)
        self.assertIn("最高日:20260107", output)
        self.assertIn("最低日:20260106", output)

    def test_format_daily_without_extreme_date_columns_still_works(self):
        df = pd.DataFrame([
            {"ts_code": "000001.SZ", "trade_date": "20260109", "open": 10, "high": 12,
             "low": 9, "close": 11},
        ])
        output = format_quote_data(df, "daily", ["000001.SZ"], adjust="qfq")
        self.assertIn("区间最高 high=12（20260109）", output)


if __name__ == "__main__":
    unittest.main()
