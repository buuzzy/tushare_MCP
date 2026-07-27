from .news import register_news_tools
from .major_news import register_major_news_tools
from .cctv_news import register_cctv_news_tools
from .research_report import register_research_report_tools
from .anns_d import register_anns_d_tools
from .irm_qa import register_irm_qa_tools
from .npr import register_npr_tools

def register_corpus_tools(mcp):
    """Register all corpus/news/policy tools (powered by minishare)."""
    register_news_tools(mcp)
    register_major_news_tools(mcp)
    register_cctv_news_tools(mcp)
    register_research_report_tools(mcp)
    register_anns_d_tools(mcp)
    register_irm_qa_tools(mcp)
    register_npr_tools(mcp)
