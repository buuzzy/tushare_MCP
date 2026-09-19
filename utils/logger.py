"""统一日志出口：低频可控 + 写入永不阻塞调用方。

2026-09-19 线上事故链
--------------------
现象：SSE 服务全路径无响应（`/`、`/sse` 全部超时），前端永久"执行中"。
链路：高频诊断日志（每次缓存命中一行，单次 hk_daily 可产生上百行）→ 平台
日志限流（Messages dropped:400）→ **同步写 stderr 阻塞线程** → 事件循环被
拖死 → 所有连接无响应。

两道防线
--------
1. `log_debug` 默认不打（DEBUG 级），从源头砍掉高频路径输出；
2. 写入交给独立后台线程（有界队列，满队列丢弃并计数）。**任何调用方都不会
   阻塞在 stderr 上**；即使日志量再次失控，最坏结果是丢日志，不会拖死服务。

约定
----
- `log_debug`：高频诊断（循环体内、每次请求）。默认静默，需要时 LOG_LEVEL=DEBUG。
- `log_info`：低频事件（每次工具调用一行、异常告警）。日常可见，务必节制。
"""

import os
import sys
import time
import queue
import logging
import functools
import threading
import traceback

# 日志级别由环境变量 LOG_LEVEL 控制（默认 INFO）。
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 后台写线程的队列长度：够吸收突发，又不至于把内存拖大
_QUEUE_SIZE = int(os.getenv("LOG_QUEUE_SIZE", "2000"))


class NonBlockingHandler(logging.Handler):
    """把日志投递到有界队列，由独立线程落盘/写 stderr。

    emit() 只做一次 put_nowait：队列满即丢弃计数，绝不阻塞调用线程。
    """

    def __init__(self, stream, queue_size: int = _QUEUE_SIZE) -> None:
        super().__init__()
        self._stream = stream
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=queue_size)
        self._dropped = 0
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(
            target=self._loop, name="log-writer", daemon=True
        )
        self._thread.start()

    # -- 调用方侧：永不阻塞 ------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            return
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            with self._lock:
                self._dropped += 1

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped

    def close(self) -> None:
        self._closed = True
        super().close()

    # -- 后台线程侧 --------------------------------------------------------

    def _loop(self) -> None:
        while not self._closed:
            batch = self._collect()
            if batch:
                self._write(batch)
                continue
            self._flush_dropped_notice()

    def _collect(self) -> list:
        """取走当前可用的日志（最多 500 条），避免单批过大长时间占用线程。"""
        try:
            first = self._queue.get(timeout=0.2)
        except queue.Empty:
            return []
        items = [first]
        while len(items) < 500:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items

    def _write(self, items: list) -> None:
        # 连续重复消息折叠成一行（例如健康轮询刷屏），显著降低写次数
        lines: list = []
        prev, count = None, 0
        for item in items:
            if item == prev:
                count += 1
                continue
            if prev is not None:
                lines.append(prev if count == 1 else f"{prev}  [x{count}]")
            prev, count = item, 1
        if prev is not None:
            lines.append(prev if count == 1 else f"{prev}  [x{count}]")

        with self._lock:
            dropped, self._dropped = self._dropped, 0
        if dropped:
            lines.append(f"minishare-mcp - WARNING - 日志队列已满，丢弃 {dropped} 条")

        try:
            self._stream.write("\n".join(lines) + "\n")
            self._stream.flush()
        except Exception:
            pass

    def _flush_dropped_notice(self) -> None:
        with self._lock:
            dropped, self._dropped = self._dropped, 0
        if not dropped:
            return
        try:
            self._stream.write(
                f"minishare-mcp - WARNING - 日志队列已满，丢弃 {dropped} 条\n"
            )
            self._stream.flush()
        except Exception:
            pass


logger = logging.getLogger("minishare_mcp")
logger.setLevel(_LOG_LEVEL)
# 不向 root 传播：避免被平台/依赖库的 root handler 二次格式化输出
logger.propagate = False

handler = NonBlockingHandler(sys.stderr)
handler.setLevel(_LOG_LEVEL)
handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

if not logger.handlers:
    logger.addHandler(handler)


def log_debug(message: str) -> None:
    """高频诊断日志：默认静默，仅 LOG_LEVEL=DEBUG 时输出。

    只能用于循环体内、每次请求都会触发的路径。这里必须是 DEBUG 级：
    **不得再改回 logger.info**（见模块头部事故复盘）。
    """
    logger.debug(message)


def log_info(message: str) -> None:
    """低频事件日志：每次工具调用一行、异常告警等。

    调用点必须节制——单次请求只允许输出常数行，禁止放进循环体。
    """
    logger.info(message)


def logger_stats() -> dict:
    """日志运行状态（供 /health 观测是否在丢日志）。"""
    return {
        "log_level": _LOG_LEVEL,
        "log_queue_size": handler._queue.qsize(),
        "log_dropped": handler.dropped_count,
    }


def handle_exception(func):
    """Unified exception handler decorator"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # 注意：不要用 traceback.print_exc(file=sys.stderr) 直写 stderr，
            # 那条路径绕过后台写线程，可能阻塞调用线程（见模块头部复盘）。
            logger.error("Error in %s: %s\n%s", func.__name__, e, traceback.format_exc())
            last_error = e
            # Retry once for transient errors
            if _is_transient(e):
                logger.warning("Transient error in %s, retrying once...", func.__name__)
                time.sleep(1)
                try:
                    return func(*args, **kwargs)
                except Exception as e2:
                    logger.error(
                        "Retry also failed in %s: %s\n%s",
                        func.__name__, e2, traceback.format_exc(),
                    )
                    last_error = e2
            # Let FastMCP convert the exception into a tool result with
            # isError=true. Returning a string here would hide upstream failures.
            raise last_error

    return wrapper


# Errors that are likely transient and worth retrying
_TRANSIENT_EXCEPTIONS = (
    TypeError, ConnectionError, TimeoutError, OSError,
)
_TRANSIENT_MESSAGES = (
    '处理服务端响应失败', 'timeout', 'timed out', 'connection reset',
    'temporarily unavailable', 'rate limit',
)


def _is_transient(e: Exception) -> bool:
    if isinstance(e, _TRANSIENT_EXCEPTIONS):
        return True
    msg = str(e).lower()
    return any(kw in msg for kw in _TRANSIENT_MESSAGES)
