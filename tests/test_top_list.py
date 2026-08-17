import unittest
from unittest import mock

import pandas as pd

from tools.stock.quote import top_list as top_list_module


class TopListTests(unittest.TestCase):
    def test_end_date_maps_to_previous_trading_day(self):
        pro = mock.Mock()
        pro.trade_cal.return_value = pd.DataFrame(
            {"cal_date": ["20260813", "20260814"]}
        )
        pro.top_list.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ", "name": "平安银行"}]
        )
        container = {}

        class ToolCapture:
            def tool(self):
                def register(function):
                    container["top_list"] = function
                    return function

                return register

        with mock.patch.object(top_list_module, "get_pro_client", return_value=pro):
            top_list_module.register_top_list_tools(ToolCapture())
            output = container["top_list"](end_date="20260815")

        pro.trade_cal.assert_called_once_with(
            start_date="20260726", end_date="20260815", is_open="1"
        )
        pro.top_list.assert_called_once_with(trade_date="20260814")
        self.assertIn("日期:20260814", output)

    def test_end_date_prefers_fresh_index_data_over_stale_calendar(self):
        pro = mock.Mock()
        pro.index_daily.return_value = pd.DataFrame({"trade_date": ["20260814"]})
        pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20260727"]})
        pro.top_list.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ"}]
        )
        container = {}

        class ToolCapture:
            def tool(self):
                def register(function):
                    container["top_list"] = function
                    return function

                return register

        with mock.patch.object(top_list_module, "get_pro_client", return_value=pro):
            top_list_module.register_top_list_tools(ToolCapture())
            container["top_list"](end_date="20260815")

        pro.index_daily.assert_called_once_with(
            ts_code="000001.SH", start_date="20260726", end_date="20260815"
        )
        pro.trade_cal.assert_not_called()
        pro.top_list.assert_called_once_with(trade_date="20260814")

    def test_ts_code_also_receives_a_resolved_trade_date(self):
        pro = mock.Mock()
        pro.trade_cal.return_value = pd.DataFrame({"cal_date": ["20260814"]})
        pro.top_list.return_value = pd.DataFrame(
            [{"trade_date": "20260814", "ts_code": "000001.SZ"}]
        )
        container = {}

        class ToolCapture:
            def tool(self):
                def register(function):
                    container["top_list"] = function
                    return function

                return register

        with mock.patch.object(top_list_module, "get_pro_client", return_value=pro):
            top_list_module.register_top_list_tools(ToolCapture())
            container["top_list"](ts_code="000001.SZ")

        pro.top_list.assert_called_once_with(trade_date="20260814", ts_code="000001.SZ")

    def test_start_date_maps_to_next_trading_day(self):
        pro = mock.Mock()
        pro.trade_cal.return_value = pd.DataFrame(
            {"cal_date": ["20260817", "20260818"]}
        )
        pro.top_list.return_value = pd.DataFrame(
            [{"trade_date": "20260817", "ts_code": "000001.SZ"}]
        )
        container = {}

        class ToolCapture:
            def tool(self):
                def register(function):
                    container["top_list"] = function
                    return function

                return register

        with mock.patch.object(top_list_module, "get_pro_client", return_value=pro):
            top_list_module.register_top_list_tools(ToolCapture())
            container["top_list"](start_date="20260815")

        pro.trade_cal.assert_called_once_with(
            start_date="20260815", end_date="20260904", is_open="1"
        )
        pro.top_list.assert_called_once_with(trade_date="20260817")


if __name__ == "__main__":
    unittest.main()
