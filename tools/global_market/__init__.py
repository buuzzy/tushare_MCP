"""全球市场（港美股）数据工具：行情 K 线、财务、代码搜索、公告。"""

from .announcements import register_announcement_tools
from .finance import register_finance_global_tools
from .quote import register_quote_tools
from .source_probe import register_probe_tools
from utils.logger import log_debug


def register_global_market_tools(mcp) -> None:
    """Register all global-market (HK/US) tools."""
    register_quote_tools(mcp)
    register_finance_global_tools(mcp)
    register_announcement_tools(mcp)
    register_probe_tools(mcp)  # 诊断探针：数据体系定稿后移除
    log_debug("Registered global market tools")
