"""资讯上下文（2026-09-22）。

背景：模型凭训练记忆回答"近期事件"类问题会翻车（2026-09 实测两轮同题，
一轮查了资讯答对 9/17 加息，一轮没查、凭记忆答"在降息"）。靠提示词约束
"必须查资讯"是软约束，拦不住模型彻底不搜。本模块把事件背景变成确定性供给：

1. ``news_context`` 工具：宏观/市场要闻摘要（近 N 天）+ 指定标的的相关报道，
   供模型显式调用，也供 sage-web 服务端预取背景卡。
2. ``news_section``：K 线输出的"相关资讯"附带段——拉行情时顺便把该标的
   近期报道带过来（用户拍板的架构：搜行情时顺便带资讯，不靠关键词启发式）。

数据源：corpus major_news（tushare pro）。按天窗口整窗拉取 + 进程内缓存
（TTL 1h），宏观筛选与标的过滤全部内存完成，K 线高频调用零额外 API 压力。
"""

import re
import time
from datetime import datetime, timedelta

from utils.logger import log_debug, handle_exception
from utils.token_manager import get_corpus_client

_NEWS_TTL_SEC = 3600.0
_PAGE_SIZE = 500
_MAX_SCAN_ROWS = 2000  # 14 天约 5-6 千条时优先保住最近两天，尾部丢弃可接受
_MAX_SYMBOL_ENTRIES = 2  # 单次 K 线输出最多附带的标的数
_MACRO_PAT = re.compile(
    "美联储|FOMC|Fed|加息|降息|利率|央行|货币政策|通胀|CPI|PPI|非农|"
    "国债|油价|原油|OPEC|黄金|证监会|国务院|财政部|关税|政策"
)

_corpus_cache: dict[int, tuple[float, list[dict]]] = {}


def _fetch_corpus(days: int) -> list[dict]:
    """拉取近 days 天重大新闻（分页，上限 2000 行），TTL 1h 进程内缓存。

    返回行: {title, time, src, content(截断)}，time 为 "YYYY-MM-DD HH:MM:SS"。
    """
    days = max(1, min(int(days), 30))
    now_ts = time.time()
    hit = _corpus_cache.get(days)
    if hit and now_ts - hit[0] < _NEWS_TTL_SEC:
        return hit[1]

    pro = get_corpus_client()
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[dict] = []
    for page in range(_MAX_SCAN_ROWS // _PAGE_SIZE):
        try:
            df = pro.major_news(
                start_date=start, end_date=end,
                limit=_PAGE_SIZE, offset=page * _PAGE_SIZE,
            )
        except Exception as e:  # 单页失败降级：用已拉到的行
            log_debug(f"[news_context] corpus 分页失败 page={page}: {e}")
            break
        if df is None or df.empty:
            break
        for _, r in df.iterrows():
            rows.append({
                "title": str(r.get("title", "")),
                "time": str(r.get("pub_time", "")),
                "src": str(r.get("src", "")),
                "content": str(r.get("content", ""))[:160],
            })
        if len(df) < _PAGE_SIZE:
            break
    log_debug(f"[news_context] corpus days={days} rows={len(rows)}")
    _corpus_cache[days] = (now_ts, rows)
    return rows


def _hit(row: dict, code: str, aliases: list[str]) -> bool:
    """标题/正文命中代码（拉丁码带边界）或任一别名（子串）。"""
    blob = row["title"] + "\n" + row["content"]
    if re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", blob):
        return True
    return any(a and a in blob for a in aliases)


def _fmt_rows(rows: list[dict], limit: int) -> list[str]:
    lines = []
    for r in rows[: max(0, limit)]:
        lines.append(f"📰 [{r['time']}] {r['title']} ({r['src']})")
    return lines


def build_news_context(
    symbol_entries: list[tuple[str, list[str]]] | None = None,
    macro_days: int = 7,
    symbol_days: int = 14,
    macro_limit: int = 8,
    symbol_limit: int = 5,
) -> str:
    """构造资讯上下文文本；宏观段与标的段均可独立关闭（limit=0 / entries=None）。

    symbol_entries: [(code, [别名...]), ...]，如 [("XOM", ["埃克森美孚"])]。
    """
    scan_days = max(macro_days if macro_limit > 0 else 0,
                    symbol_days if symbol_entries else 0)
    if scan_days <= 0:
        return ""
    try:
        rows = _fetch_corpus(scan_days)
    except Exception as e:
        log_debug(f"[news_context] corpus 不可用: {e}")
        return "资讯上下文暂不可用（数据源异常），请勿凭记忆回答事件类问题。"

    now = datetime.now()
    out: list[str] = ["--- 资讯上下文（事件与日期以此为准，禁止用训练记忆补充） ---"]

    if macro_limit > 0 and rows:
        macro_start = (now - timedelta(days=macro_days)).strftime("%Y-%m-%d")
        window = [r for r in rows if r["time"] >= macro_start]
        # 宏观词命中优先，其余按时间新到旧兜底（摘要排序，不做闸门）
        ranked = sorted(
            window,
            key=lambda r: (1 if _MACRO_PAT.search(r["title"]) else 0, r["time"]),
            reverse=True,
        )
        out.append(f"[宏观/市场要闻·近{macro_days}天]")
        out.extend(_fmt_rows(ranked, macro_limit) or ["（窗口内无新闻）"])

    if symbol_entries:
        sym_start = (now - timedelta(days=symbol_days)).strftime("%Y-%m-%d")
        window = [r for r in rows if r["time"] >= sym_start]
        for code, aliases in symbol_entries[:_MAX_SYMBOL_ENTRIES]:
            hits = [r for r in window if _hit(r, code, aliases)]
            hits.sort(key=lambda r: r["time"], reverse=True)
            label = "/".join([code] + [a for a in aliases if a])
            out.append(f"[{label}·近{symbol_days}天·{len(hits)}条相关]")
            if hits:
                out.extend(_fmt_rows(hits, symbol_limit))
            else:
                out.append(f"（窗口内未检索到与 {label} 直接相关的报道，"
                           f"不要据此认定'没有新闻'，可自行调用 major_news 核实）")
    return "\n".join(out)


def news_section(entries: list[tuple[str, list[str]]], days: int = 14, limit: int = 4) -> str:
    """K 线输出尾部的"相关资讯"附带段；无命中或异常时返回空串（零噪音）。"""
    if not entries:
        return ""
    try:
        text = build_news_context(
            symbol_entries=entries, macro_days=0,
            symbol_days=days, macro_limit=0, symbol_limit=limit,
        )
    except Exception as e:  # 资讯失败绝不影响行情主流程
        log_debug(f"[news_context] 附带段构造失败: {e}")
        return ""
    lines = text.split("\n") if text else []
    # build_news_context 的首行是总标头；无实质内容（仅标头+空窗口声明）不输出
    body = [ln for ln in lines if ln.startswith("📰")]
    if not body:
        return ""
    return "\n--- 相关资讯（服务端按 代码/名称 过滤，事件背景参考） ---\n" + "\n".join(
        ln for ln in lines if ln.startswith("📰") or ln.startswith("[")
    )


def register_news_context_tools(mcp):
    @mcp.tool()
    @handle_exception
    def news_context(symbols: str = "", macro_days: int = 7, symbol_days: int = 14) -> str:
        """
        获取资讯上下文：宏观/市场要闻摘要 + 指定标的的近期相关报道。

        适用：回答"近期事件/政策/为什么涨跌"前先核实事件是否真实发生、
        发生在哪天；事件日期必须来自本工具或 major_news，禁止用训练记忆。

        参数:
            symbols: 标的声明，"代码|别名1,别名2"，多标的分号分隔，
                     如 "XOM|埃克森美孚;KO|可口可乐"；留空则只返回宏观要闻。
            macro_days: 宏观要闻窗口天数，默认 7
            symbol_days: 标的报道窗口天数，默认 14
        """
        log_debug(f"Tool news_context called: symbols={symbols!r}, macro_days={macro_days}, symbol_days={symbol_days}")
        entries: list[tuple[str, list[str]]] = []
        for item in (symbols or "").split(";"):
            item = item.strip()
            if not item:
                continue
            code, _, alias_str = item.partition("|")
            code = code.strip()
            if not code:
                continue
            aliases = [a.strip() for a in alias_str.split(",") if a.strip()]
            entries.append((code, aliases))
        return build_news_context(
            symbol_entries=entries or None,
            macro_days=macro_days,
            symbol_days=symbol_days,
        )
