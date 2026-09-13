"""全球市场数据源统一调用入口：按域名组限频 + 熔断 + 进程内缓存。

akshare 本身无限频逻辑（个人研究库），而东财对高频 IP 会直接断连。
2026-09-13 实测：push2his 行情域名短时 ~15-25 次请求后 TCP 断连（HTTP 000），
数字子域名（33.push2his 等）不绕过，恢复为分钟级；datacenter 财务域名独立
不受影响。因此所有港美股外部请求（akshare 调用与手写 HTTP）都必须经过本模块。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

import pandas as pd
import requests

from utils.logger import log_debug

# 域名组 -> (每秒令牌数, 桶容量突发)
_GROUP_RATES: dict[str, tuple[float, int]] = {
    "eastmoney_quote": (0.3, 3),       # push2his：K线/指数，最敏感（实测会断连）
    "eastmoney_datacenter": (1.0, 3),  # datacenter：F10 财务
    "eastmoney_list": (1.0, 2),        # push2：代码列表（24h 缓存，量极小）
    "sec_edgar": (8.0, 8),             # SEC EDGAR 官方上限 10 req/s，留余量
    "hkex": (1.0, 2),                  # 披露易，保守
}

_CIRCUIT_FAILS = 3       # 连续调用级失败 N 次后熔断（内部重试耗尽才算一次）
_CIRCUIT_COOLDOWN = 120  # 熔断时长（秒）：实测东财断连恢复为分钟级，10 分钟过长
_RETRY_BACKOFF = (0.5, 1.5)  # 连接层错误的内部重试退避（秒）
_CACHE_MAX = 500

# 视为"连接层失败"的异常（触发熔断计数）；数据类异常（空结果等）不计
_CONNECTION_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class RateLimitedError(RuntimeError):
    """限频熔断期间拒绝请求。异常消息为面向用户的中文说明。"""


class _GroupState:
    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.consecutive_failures = 0
        self.open_until = 0.0

    def refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(
            self.tokens + (now - self.last_refill) * self.rate, self.rate * 10 + 3
        )
        self.last_refill = now


class _EMClient:
    def __init__(self) -> None:
        self._groups = {name: _GroupState(*cfg) for name, cfg in _GROUP_RATES.items()}
        self._cond = threading.Condition()
        self._cache: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    # -- 限频与熔断 ----------------------------------------------------------

    def _acquire(self, group: str) -> None:
        with self._cond:
            state = self._groups[group]
            while True:
                state.refill()
                now = time.monotonic()
                if state.open_until > now:
                    wait_min = int((state.open_until - now) / 60) + 1
                    raise RateLimitedError(
                        f"数据源（{group}）触发访问限制，已暂时熔断，"
                        f"预计约 {wait_min} 分钟后恢复，请稍后再试。"
                    )
                if state.tokens >= 1.0:
                    state.tokens -= 1.0
                    return
                # 等待一个令牌周期再试（等待期间释放锁）
                self._cond.wait(timeout=1.0 / state.rate + 0.05)

    def _record_success(self, group: str) -> None:
        with self._cond:
            self._groups[group].consecutive_failures = 0

    def _record_failure(self, group: str) -> None:
        with self._cond:
            state = self._groups[group]
            state.consecutive_failures += 1
            if state.consecutive_failures >= _CIRCUIT_FAILS:
                state.open_until = time.monotonic() + _CIRCUIT_COOLDOWN
                state.consecutive_failures = 0
                log_debug(
                    f"[em_client] group '{group}' circuit OPEN for {_CIRCUIT_COOLDOWN}s"
                )

    # -- 统一入口 ------------------------------------------------------------

    def call(
        self,
        group: str,
        fn: Callable[[], Any],
        cache_key: str = "",
        ttl_seconds: float = 0.0,
    ) -> Any:
        """经限频与缓存执行一次外部数据调用。

        连接层错误（断连/超时）会在内部带退避重试至多 2 次；重试全部耗尽才
        计一次"调用级失败"并进入熔断计数。实测东财 push2his 存在"冷启动头
        1-2 次连接被 reset、之后稳定"的抖动，靠内部重试消化而不是熔断。

        Args:
            group: 域名组名（见 _GROUP_RATES）
            fn: 无参可调用，执行真实请求（如 akshare 函数的 partial）
            cache_key: 缓存键；空串表示不缓存
            ttl_seconds: 缓存有效期（秒），0 表示不缓存
        """
        if group not in self._groups:
            raise ValueError(f"Unknown rate-limit group: {group}")

        if cache_key and ttl_seconds > 0:
            cached = self._peek_cache(cache_key, ttl_seconds)
            if cached is not None:
                log_debug(f"[em_client] cache HIT '{cache_key}'")
                return cached

        last_error: BaseException = RuntimeError("unreachable")
        for attempt in range(len(_RETRY_BACKOFF) + 1):
            self._acquire(group)  # 重试同样消耗令牌，尊重限速
            try:
                value = fn()
            except _CONNECTION_ERRORS as e:
                last_error = e
                log_debug(f"[em_client] {group} connection error on attempt "
                          f"{attempt + 1}: {type(e).__name__}")
                if attempt < len(_RETRY_BACKOFF):
                    time.sleep(_RETRY_BACKOFF[attempt])
                continue
            self._record_success(group)
            if cache_key and ttl_seconds > 0:
                self._store_cache(cache_key, value)
            return _copy_value(value)

        self._record_failure(group)
        raise last_error

    def _peek_cache(self, key: str, ttl: float) -> Optional[Any]:
        with self._cond:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return _copy_value(value)

    def _store_cache(self, key: str, value: Any) -> None:
        with self._cond:
            self._cache[key] = (time.time(), _copy_value(value))
            self._cache.move_to_end(key)
            while len(self._cache) > _CACHE_MAX:
                self._cache.popitem(last=False)


def _copy_value(value: Any) -> Any:
    # DataFrame 返回副本，避免调用方修改污染缓存
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=True)
    return value


_client = _EMClient()


def em_call(
    group: str,
    fn: Callable[[], Any],
    cache_key: str = "",
    ttl_seconds: float = 0.0,
) -> Any:
    """模块级统一调用入口（见 _EMClient.call）。"""
    return _client.call(group, fn, cache_key=cache_key, ttl_seconds=ttl_seconds)


# 常用 TTL（秒）
TTL_KLINE = 3 * 3600       # K线 3 小时：每股每天最多 8 次真实请求
TTL_DAILY = 24 * 3600      # 财务/公告/代码表 24 小时
