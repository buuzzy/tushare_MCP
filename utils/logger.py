import os
import sys
import logging
import functools
import traceback

# 日志级别由环境变量 LOG_LEVEL 控制（默认 INFO）。
# 排查线上问题时设 LOG_LEVEL=DEBUG 打开诊断日志，日常保持默认以免刷屏。
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Logger for debugging
logger = logging.getLogger("minishare_mcp")
logger.setLevel(_LOG_LEVEL)

# Create logging handler
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(_LOG_LEVEL)

# Create logging formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add handler to logger
if not logger.handlers:
    logger.addHandler(handler)

def log_debug(message: str):
    """诊断日志：默认静默，仅 LOG_LEVEL=DEBUG 时输出。

    2026-09-19 线上事故：本函数原先直接调用 logger.info，而 em_client 的
    缓存命中、K 线分段、限频重试等**高频路径**都走它（单次 hk_daily 可产生
    数十至上百行），把 stderr 刷爆。Railway 对日志做限流（Messages
    dropped:400）后，同步写 stderr 阻塞工作线程，事件循环被拖死，SSE 全路径
    无响应 —— 前端表现为永久"执行中"。

    因此这里必须是 DEBUG 级：**不得再改回 logger.info**。
    需要这些信息时，用环境变量 LOG_LEVEL=DEBUG 临时打开。
    """
    logger.debug(message)

def handle_exception(func):
    """Unified exception handler decorator"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
           return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            traceback.print_exc(file=sys.stderr)
            last_error = e
            # Retry once for transient errors
            if _is_transient(e):
                logger.warning(f"Transient error in {func.__name__}, retrying once...")
                import time
                time.sleep(1)
                try:
                    return func(*args, **kwargs)
                except Exception as e2:
                    logger.error(f"Retry also failed in {func.__name__}: {str(e2)}")
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
