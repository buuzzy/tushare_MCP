"""全球市场（港美股）数据工具：行情 K 线、财务、代码搜索、公告。"""

from .announcements import register_announcement_tools
from .finance import register_finance_global_tools
from .quote import register_quote_tools
from utils.logger import log_debug


def register_global_market_tools(mcp) -> None:
    """Register all global-market (HK/US) tools."""
    register_quote_tools(mcp)
    register_finance_global_tools(mcp)
    register_announcement_tools(mcp)
    # source_probe 诊断探针已于 2026-09-20 移除（数据体系定稿，见 commit 046813d 与
    # docs/data-source-design-sg.md 清单第 8 项；需要时从 git 历史恢复）
    log_debug("Registered global market tools")
