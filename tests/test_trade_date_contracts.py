import unittest
from unittest import mock

import pandas as pd

from tools.stock.quote import (
    ggt_daily as ggt_daily_module,
    ggt_top10 as ggt_top10_module,
    hsgt_top10 as hsgt_top10_module,
    suspend_d as suspend_d_module,
)


class ToolCapture:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(function):
            self.tools[function.__name__] = function
            return function

        return register


def register(module, register_name):
    container = ToolCapture()
    module.__dict__[register_name](container)
    return container.tools


class TradeDateContractTests(unittest.TestCase):
    def fresh_calendar_client(self):
        pro = mock.Mock()
        pro.index_daily.return_value = pd.DataFrame({"trade_date": ["20260814"]})
        pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20260728"]})
        return pro

    def test_suspend_d_auto_prefers_fresh_index_data(self):
        pro = self.fresh_calendar_client()
        pro.suspend_d.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ", "suspend_type": "S"}]
        )
        with mock.patch.object(suspend_d_module, "get_pro_client", return_value=pro):
            tools = register(suspend_d_module, "register_suspend_d_tools")
            output = tools["suspend_d"]()

        pro.index_daily.assert_called_once_with(
            ts_code="000001.SH", start_date=mock.ANY, end_date=mock.ANY
        )
        pro.trade_cal.assert_not_called()
        pro.suspend_d.assert_called_once_with(trade_date="20260814")
        self.assertIn("日期:20260814", output)

    def test_suspend_d_end_only_becomes_single_trade_date(self):
        pro = self.fresh_calendar_client()
        pro.suspend_d.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ"}]
        )
        with mock.patch.object(suspend_d_module, "get_pro_client", return_value=pro):
            tools = register(suspend_d_module, "register_suspend_d_tools")
            tools["suspend_d"](end_date="20260815")

        pro.suspend_d.assert_called_once_with(trade_date="20260814")

    def test_suspend_d_explicit_range_is_preserved(self):
        pro = self.fresh_calendar_client()
        pro.suspend_d.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ"}]
        )
        with mock.patch.object(suspend_d_module, "get_pro_client", return_value=pro):
            tools = register(suspend_d_module, "register_suspend_d_tools")
            tools["suspend_d"](start_date="20260810", end_date="20260814")

        pro.index_daily.assert_not_called()
        pro.suspend_d.assert_called_once_with(
            start_date="20260810", end_date="20260814"
        )

    def test_hsgt_and_ggt_daily_end_only_use_one_date(self):
        pro = self.fresh_calendar_client()
        pro.hsgt_top10.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ"}]
        )
        pro.ggt_daily.return_value = pd.DataFrame([{"trade_date": "20260814"}])
        with mock.patch.object(hsgt_top10_module, "get_pro_client", return_value=pro):
            hsgt_tools = register(hsgt_top10_module, "register_hsgt_top10_tools")
            hsgt_tools["hsgt_top10"](end_date="20260815")
        with mock.patch.object(ggt_daily_module, "get_pro_client", return_value=pro):
            ggt_tools = register(ggt_daily_module, "register_ggt_daily_tools")
            ggt_tools["ggt_daily"](end_date="20260815")

        pro.hsgt_top10.assert_called_once_with(trade_date="20260814")
        pro.ggt_daily.assert_called_once_with(trade_date="20260814")

    def test_ggt_top10_converts_range_to_trade_date_only(self):
        pro = self.fresh_calendar_client()
        pro.ggt_top10.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "00700.HK"}]
        )
        with mock.patch.object(ggt_top10_module, "get_pro_client", return_value=pro):
            tools = register(ggt_top10_module, "register_ggt_top10_tools")
            tools["ggt_top10"](start_date="20260810", end_date="20260815")

        pro.ggt_top10.assert_called_once_with(trade_date="20260814")

    def test_upstream_exception_is_not_swallowed_as_text(self):
        pro = self.fresh_calendar_client()
        pro.ggt_top10.side_effect = ValueError("参数校验失败")
        with mock.patch.object(ggt_top10_module, "get_pro_client", return_value=pro):
            tools = register(ggt_top10_module, "register_ggt_top10_tools")
            with self.assertRaisesRegex(ValueError, "参数校验失败"):
                tools["ggt_top10"](end_date="20260815")


if __name__ == "__main__":
    unittest.main()
