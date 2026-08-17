import sys
import logging
import functools
import traceback

# Logger for debugging
logger = logging.getLogger("minishare_mcp")
logger.setLevel(logging.INFO)

# Create logging handler
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)

# Create logging formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add handler to logger
if not logger.handlers:
    logger.addHandler(handler)

def log_debug(message: str):
    """Unified logging function"""
    logger.info(message)

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
