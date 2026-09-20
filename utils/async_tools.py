"""把同步工具函数搬到工作线程执行，并给每次调用加硬时限。

为什么必须这么做
----------------
FastMCP 1.7.1 的调用链是：

    Tool.run(**arguments)
      -> FuncMetadata.call_fn_with_arg_validation(self.fn, self.is_async, ...)
           -> 若 is_async 为 False，直接 `fn(**args)` —— **就在事件循环里同步调用**

本项目全部数据工具都是同步阻塞的（requests / akshare / 限频等待），因此一次
hk_daily 的上游等待 = 整个事件循环同样时长不可用：`/sse`、`/messages`、健康
检查全部无响应。2026-09-19 线上实测正是如此——调用开始后服务端静默，连 `/`
都不再应答，前端表现为永久"执行中"。

本模块在工具注册完成后统一替换每个工具的调用方式：

    async def wrapper(**kwargs):
        await loop.run_in_executor(线程池, fn, **kwargs)   # 事件循环始终空闲

同时用 asyncio.wait_for 给单次调用设硬上限：超时返回可读的中文提示，而不是
让调用方无限等待。工作线程内部仍受 requests 超时约束，不会永久泄漏。

注意：替换只改 `tool.fn` 与 `tool.is_async`，**不动 `tool.fn_metadata`**，
因此工具名、描述、参数 schema 与包装前逐字节一致（有本地验证覆盖）。
"""

from __future__ import annotations

import os
import time
import asyncio
import functools
import threading
from concurrent.futures import ThreadPoolExecutor

from utils.logger import log_info, logger

# 工作线程上限：工具本身是阻塞 IO，线程数只要够并发隔离即可，不宜过大
_MAX_WORKERS = int(os.getenv("TOOL_MAX_WORKERS", "16"))
# 单次工具调用的硬上限（秒）。超时返回可读错误，避免调用方无限等待。
# 55s：MCP 协议层客户端默认 60s 就放弃（-32001），服务端必须在它之前
# 给出结果或明确错误（2026-09-20 超时错配校准，原 120s 永远跑不过客户端）
_DEFAULT_TIMEOUT = float(os.getenv("TOOL_TIMEOUT_SEC", "55"))
# 超过该耗时的调用打一条告警（线上定位跨境链路延迟用）
_SLOW_CALL_SEC = float(os.getenv("TOOL_SLOW_SEC", "10"))

_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="tool")
_lock = threading.Lock()
_inflight = 0
_slow_calls = 0
_timed_out = 0
_completed = 0


def _bump(field: str, delta: int = 1) -> None:
    global _inflight, _slow_calls, _timed_out, _completed
    with _lock:
        if field == "inflight":
            _inflight += delta
        elif field == "slow":
            _slow_calls += delta
        elif field == "timed_out":
            _timed_out += delta
        elif field == "completed":
            _completed += delta


def tool_runtime_stats() -> dict:
    """运行态指标（供 /health 观测：是否还有调用在跑、是否在超时）。"""
    with _lock:
        return {
            "tool_inflight": _inflight,
            "tool_completed": _completed,
            "tool_slow": _slow_calls,
            "tool_timed_out": _timed_out,
            "tool_workers": _MAX_WORKERS,
            "tool_timeout_sec": _DEFAULT_TIMEOUT,
        }


def _wrap_tool(name: str, fn, timeout: float):
    """返回 async 包装：在工作线程里跑 fn，外层加硬时限。"""

    @functools.wraps(fn)
    async def _async_tool(*args, **kwargs):
        loop = asyncio.get_running_loop()
        started = time.monotonic()
        _bump("inflight")
        try:
            future = loop.run_in_executor(_executor, functools.partial(fn, *args, **kwargs))
            try:
                return await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError:
                # 注意：工作线程无法被强杀，它会继续跑到内部超时；这里只是
                # 让调用方及时拿到结果，不再无限等待。
                _bump("timed_out")
                logger.warning(
                    "[tool] %s 超时（>%.0fs），已返回超时提示；工作线程仍在收尾",
                    name, timeout,
                )
                return (
                    f"错误：数据服务响应超时（已等待 {timeout:.0f} 秒仍未取到数据）。"
                    f"可能是上游繁忙或区间数据量过大，请缩小时间区间后重试。"
                )
        finally:
            elapsed = time.monotonic() - started
            _bump("inflight", -1)
            _bump("completed")
            if elapsed >= _SLOW_CALL_SEC:
                _bump("slow")
                logger.warning("[tool] %s 慢调用：耗时 %.1fs", name, elapsed)
            else:
                log_info(f"[tool] {name} 耗时 {elapsed:.1f}s")

    return _async_tool


def make_tools_nonblocking(mcp, timeout: float | None = None) -> int:
    """把所有**同步**工具替换为线程池执行的 async 包装。

    必须在全部工具（含别名）注册完成之后调用一次。已经是协程函数的工具
    保持原样（本身就不阻塞事件循环）。
    """
    effective_timeout = _DEFAULT_TIMEOUT if timeout is None else timeout
    tools = getattr(mcp._tool_manager, "_tools", {})
    patched = 0
    for tool in tools.values():
        if getattr(tool, "is_async", False):
            continue
        tool.fn = _wrap_tool(tool.name, tool.fn, effective_timeout)
        tool.is_async = True
        patched += 1
    log_info(
        f"[tool] 非阻塞执行已启用：{patched}/{len(tools)} 个同步工具改走线程池，"
        f"单次调用上限 {effective_timeout:.0f}s，工作线程 {_MAX_WORKERS} 个"
    )
    return patched
