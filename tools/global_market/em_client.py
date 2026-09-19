"""全球市场数据源统一调用入口：按域名组限频 + 熔断 + 进程内缓存。

akshare 本身无限频逻辑（个人研究库），而东财对高频 IP 会直接断连。
2026-09-13 实测：push2his 行情域名短时 ~15-25 次请求后 TCP 断连（HTTP 000），
数字子域名（33.push2his 等）不绕过，恢复为分钟级；datacenter 财务域名独立
不受影响。因此所有港美股外部请求（akshare 调用与手写 HTTP）都必须经过本模块。

并发模型（2026-09-19 修订）：限频等待与缓存读写使用**互相独立**的锁。
旧实现让所有域名组共用一把全局 Condition，缓存读写也挂在同一把锁上：
因 Condition.wait 会释放锁，多组并发并不会严格串行，但每次唤醒都要争抢
同一把锁（线程越多抖动越大），缓存热路径也被限频轮询牵连。实测两组各抽
3 个令牌（rate=2/s）总耗时由 1.66s 降至 1.51s（更接近理论值 1.5s）。

此外，缓存命中不再写日志——它是正常高频路径，每次命中打日志会刷爆
stderr，触发 Railway 日志限流后同步写阻塞线程，进而拖死服务。
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
    "tencent_quote": (1.0, 5),        # ifzq.gtimg.cn：港股K线/指数（线上实测稳定）
    "sina_quote": (1.0, 3),           # finance.sina.com.cn：美股K线（腾讯 fqkline 对美股仅返回1根，实测废弃）
    "eastmoney_quote": (0.3, 3),      # push2his：备用（东财对海外 IP 动态封禁，勿作主力）
    "eastmoney_datacenter": (1.0, 3),  # datacenter：F10 财务（海外稳定）
    "eastmoney_list": (1.0, 2),        # push2：代码列表（24h 缓存，量极小）
    "eastmoney_suggest": (1.0, 3),     # searchadapter：全库代码/名称搜索（24h 缓存）
    "sec_edgar": (8.0, 8),             # SEC EDGAR 官方上限 10 req/s，留余量
    "hkex": (1.0, 2),                  # 披露易，保守
}

_CIRCUIT_FAILS = 3       # 连续调用级失败 N 次后熔断（内部重试耗尽才算一次）
_CIRCUIT_COOLDOWN = 120  # 熔断时长（秒）：实测东财断连恢复为分钟级，10 分钟过长
_RETRY_BACKOFF = (0.5, 1.5)  # 连接层错误的内部重试退避（秒）
_CACHE_MAX = 500

# 对外（LLM/用户）可见的错误消息里，用中性的服务名代替内部域名组名，
# 避免暴露数据供应商。
_GROUP_PUBLIC_NAMES: dict[str, str] = {
    "tencent_quote": "行情数据服务",
    "sina_quote": "行情数据服务",
    "eastmoney_quote": "行情数据服务",
    "eastmoney_datacenter": "财务数据服务",
    "eastmoney_list": "基础数据服务",
    "eastmoney_suggest": "基础数据服务",
    "sec_edgar": "SEC 公告服务",
    "hkex": "披露易公告服务",
}

# 视为"连接层失败"的异常（触发熔断计数）；数据类异常（空结果等）不计
_CONNECTION_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class RateLimitedError(RuntimeError):
    """限频熔断期间拒绝请求。异常消息为面向用户的中文说明。"""


class _GroupState:
    """单个域名组的令牌桶状态，自带独立条件变量。"""

    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.consecutive_failures = 0
        self.open_until = 0.0
        # 每组独立锁：避免多组并发等待令牌时在唤醒瞬间争抢同一把全局锁
        self.cond = threading.Condition()

    def refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(
            self.tokens + (now - self.last_refill) * self.rate, self.rate * 10 + 3
        )
        self.last_refill = now


class _EMClient:
    def __init__(self) -> None:
        self._groups = {name: _GroupState(*cfg) for name, cfg in _GROUP_RATES.items()}
        self._cache_lock = threading.Lock()
        self._cache: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    # -- 限频与熔断 ----------------------------------------------------------

    def _acquire(self, group: str) -> None:
        state = self._groups[group]
        with state.cond:
            while True:
                state.refill()
                now = time.monotonic()
                if state.open_until > now:
                    wait_min = int((state.open_until - now) / 60) + 1
                    raise RateLimitedError(
                        f"{_GROUP_PUBLIC_NAMES.get(group, '数据服务')}暂时不可用（访问限制），"
                        f"预计约 {wait_min} 分钟后恢复，请稍后再试。"
                    )
                if state.tokens >= 1.0:
                    state.tokens -= 1.0
                    return
                # 只等"攒够 1 个令牌"所需的时间，避免固定 1s 空转；
                # 上限 1s 以便及时看到熔断状态变化。
                need = 1.0 - state.tokens
                wait = need / state.rate if state.rate > 0 else 1.0
                state.cond.wait(timeout=min(max(wait, 0.05), 1.0))

    def _record_success(self, group: str) -> None:
        state = self._groups[group]
        with state.cond:
            state.consecutive_failures = 0

    def _record_failure(self, group: str) -> None:
        state = self._groups[group]
        opened = False
        with state.cond:
            state.consecutive_failures += 1
            if state.consecutive_failures >= _CIRCUIT_FAILS:
                state.open_until = time.monotonic() + _CIRCUIT_COOLDOWN
                state.consecutive_failures = 0
                opened = True
                # 唤醒正在等令牌的线程，让它们立刻拿到熔断提示而不是继续空转
                state.cond.notify_all()
        if opened:
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
                # 缓存命中是高频正常路径，刻意不写日志：
                # 每次命中都打日志会刷爆 stderr，触发 Railway 日志限流后
                # 同步写阻塞线程，最终拖死服务。
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
        with self._cache_lock:
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
        with self._cache_lock:
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
