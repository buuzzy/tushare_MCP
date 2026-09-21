"""图表供给工程解回归（2026-09-21 Q3 实测缺口）。

长区间时间序列整段降采样/聚合为周频全史，图表拿到完整数据，
杜绝"标题近三年、图上近 50 天"的图文打架。
"""

import unittest

import pandas as pd

from tools.stats_utils import STATS_PREFIX, downsample_weekly_last
from tools.stock.quote.daily_basic import render_daily_basic
from tools.stock.quote.quote_utils import format_quote_data


def _make_daily_rows(n: int, start: str = "20250101") -> list[dict]:
    """n 个连续交易日（跳过周末）的合成日线，PE 随日期单调变化。"""
    import datetime as dt

    d = dt.datetime.strptime(start, "%Y%m%d").date()
    rows = []
    while len(rows) < n:
        if d.weekday() < 5:
            i = len(rows)
            rows.append(
                {
                    "ts_code": "600519.SH",
                    "trade_date": d.strftime("%Y%m%d"),
                    "close": 1000 + i,
                    "pe": 20.0 + i * 0.01,
                    "pe_ttm": 20.0 + i * 0.02,
                    "pb": 6.0,
                    "total_mv": 1500000 + i,
                }
            )
        d += dt.timedelta(days=1)
    return rows


class DownsampleWeeklyLastTests(unittest.TestCase):
    def test_short_series_untouched(self):
        df = pd.DataFrame(_make_daily_rows(100))
        out, freq = downsample_weekly_last(df, "trade_date", ["close"], threshold=120)
        self.assertEqual(freq, "")
        self.assertEqual(len(out), len(df))

    def test_long_series_weekly_last_values(self):
        df = pd.DataFrame(_make_daily_rows(300))  # ~60 周
        out, freq = downsample_weekly_last(df, "trade_date", ["close", "pe_ttm"], threshold=120)
        self.assertEqual(freq, "周")
        self.assertLessEqual(len(out), 120)
        # 日期升序且为周内最大交易日
        dates = out["trade_date"].tolist()
        self.assertEqual(dates, sorted(dates))
        # 每周取末值：对照最后一个完整周
        dts = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        last_week = dts.dt.to_period("W-SUN").astype(str).iloc[-1]
        expected_close = df.loc[dts.dt.to_period("W-SUN").astype(str) == last_week, "close"].iloc[-1]
        self.assertEqual(out["close"].iloc[-1], expected_close)

    def test_weekly_overflow_falls_back_to_monthly(self):
        # ~3 年日线：周频约 157 条 > 120 阈值 -> 月频
        df = pd.DataFrame(_make_daily_rows(725, start="20230921"))
        out, freq = downsample_weekly_last(df, "trade_date", ["close"], threshold=120)
        self.assertEqual(freq, "月")
        self.assertLessEqual(len(out), 120)


class DailyBasicChartSupplyTests(unittest.TestCase):
    def test_long_series_downsamples_and_keeps_full_precision_stats(self):
        df = pd.DataFrame(_make_daily_rows(300))
        output = render_daily_basic(df, "600519.SH")
        self.assertIn("已自动降采样", output)
        self.assertIn("周频", output)
        # 图表数据 = 全史周频，不再是尾部 50 天
        data_rows = [line for line in output.split("\n") if line.startswith("日期:")]
        self.assertGreater(len(data_rows), 50)
        first_date = data_rows[0].split("|")[0].split(":")[1]
        # 周频首点=首周最后一个交易日（20250101 为周三，首周止于 20250103），
        # 只要覆盖到区间起点所在周即可
        self.assertLessEqual(first_date, "20250107")
        # 区间统计仍对全量日线计算，精度到日：周频行里首周 PE(TTM)=20.04
        #（周内末值），但统计行的最低 20（20250101 首日）只有日线精度才有
        self.assertIn("最低 20（20250101）", output)
        self.assertIn(STATS_PREFIX, output)

    def test_short_series_unchanged(self):
        df = pd.DataFrame(_make_daily_rows(50))
        output = render_daily_basic(df, "600519.SH")
        self.assertNotIn("降采样", output)
        self.assertEqual(output.count("日期:"), 50)


class AShareLongWindowQuoteTests(unittest.TestCase):
    def test_daily_over_250_aggregates_to_weekly(self):
        rows = _make_daily_rows(300)
        for r in rows:
            r.update(
                {
                    "open": r["close"] - 1,
                    "high": r["close"] + 2,
                    "low": r["close"] - 2,
                    "pre_close": r["close"] - 0.5,
                    "change": 0.5,
                    "pct_chg": 0.05,
                    "vol": 100,
                    "amount": 2000,
                }
            )
        df = pd.DataFrame(rows)
        output = format_quote_data(df, "daily", ["600519.SH"], adjust="qfq")
        self.assertIn("已自动聚合为周线全史", output)
        self.assertIn("最高日:", output)  # 聚合行附极值发生日（A股中文列格式）
        # 区间统计行按原始日线全量计算，精度到日
        self.assertIn(STATS_PREFIX, output)

    def test_short_daily_unchanged(self):
        rows = _make_daily_rows(30)
        for r in rows:
            r.update(
                {
                    "open": r["close"] - 1,
                    "high": r["close"] + 2,
                    "low": r["close"] - 2,
                    "pre_close": r["close"] - 0.5,
                    "change": 0.5,
                    "pct_chg": 0.05,
                    "vol": 100,
                    "amount": 2000,
                }
            )
        df = pd.DataFrame(rows)
        output = format_quote_data(df, "daily", ["600519.SH"], adjust="qfq")
        self.assertNotIn("聚合", output)


if __name__ == "__main__":
    unittest.main()
