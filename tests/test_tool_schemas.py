import unittest

from mcp.server.fastmcp import FastMCP

from tools.corpus.news import register_news_tools
from tools.fund.fund_daily import register_fund_daily_tools
from tools.stock.finance.income import register_income_tools


class ToolSchemaTests(unittest.TestCase):
    def test_required_fields(self):
        import asyncio

        async def run():
            mcp = FastMCP("schema-test")
            register_news_tools(mcp)
            register_fund_daily_tools(mcp)
            register_income_tools(mcp)
            tools = {tool.name: tool for tool in await mcp.list_tools()}
            return tools

        tools = asyncio.run(run())
        self.assertEqual(
            set(tools["news"].inputSchema["required"]), {"start_date", "end_date"}
        )
        self.assertEqual(tools["fund_daily"].inputSchema["required"], ["ts_code"])
        self.assertEqual(tools["income"].inputSchema["required"], ["ts_code"])


if __name__ == "__main__":
    unittest.main()
