"""数据源诊断探针（白名单 + 受控模式）。

用途：在指定部署区域（如新加坡）实测各上游数据源的连通性、延迟、
并发承受力与限速阈值，为数据源选型提供数据。仅接受白名单内的
URL 模板，任何外部输入都不能注入 URL 或 header，属于纯诊断工具，
后续可在数据体系定稿后移除。

模式：
- single: 单次请求，返回状态/耗时/字节数
- burst:  n 个线程同时并发打同一目标，返回成功数与耗时分布
- rate:   连续快速串行 n 次（无间隔），返回逐次结果，用于找限速阈值
"""

import time
from concurrent.futures import ThreadPoolExecutor

import requests

from utils.logger import log_debug

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 白名单：key -> (url, headers)
_HEADERS_BASE = {"User-Agent": _UA}
_HEADERS_SINA = {**_HEADERS_BASE, "Referer": "https://finance.sina.com.cn"}

TARGETS: dict[str, tuple[str, dict]] = {
    # ---- 腾讯 ifzq（当前港股 K 线主力源）----
    "tx_hk_recent": (
        "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk00700,day,2026-09-14,2026-09-18,10,",
        _HEADERS_BASE),
    "tx_hk_old800": (
        "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk00700,day,2023-09-21,2025-11-29,800,",
        _HEADERS_BASE),
    "tx_us_recent": (
        "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=usAAPL.OQ,day,2026-09-14,2026-09-18,10,",
        _HEADERS_BASE),
    "tx_rt_hk": (
        "https://qt.gtimg.cn/q=hk00700",
        _HEADERS_BASE),
    # ---- 东财 push2his（K 线，单请求全历史）----
    "em_hk_recent": (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=116.00700"
        "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=0&end=20260920&lmt=10",
        _HEADERS_BASE),
    "em_hk_full": (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=116.00700"
        "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=0&end=20260920&lmt=1000000",
        _HEADERS_BASE),
    "em_us_full": (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=105.AAPL"
        "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=0&end=20260920&lmt=1000000",
        _HEADERS_BASE),
    "em_rt": (
        "https://push2.eastmoney.com/api/qt/ulist.np/get?secids=116.00700,105.AAPL"
        "&fields=f2,f3,f12,f14&fltt=2",
        _HEADERS_BASE),
    "em_suggest": (
        "https://searchadapter.eastmoney.com/api/suggest/get?input=%E8%85%BE%E8%AE%AF&type=14&count=5",
        _HEADERS_BASE),
    # ---- 新浪（当前美股 K 线主力源）----
    "sina_us_static": (
        "https://finance.sina.com.cn/staticdata/us/AAPL",
        _HEADERS_SINA),
    "sina_hk_klc2": (
        "https://finance.sina.com.cn/stock/hkstock/hk00700/klc2_kl.js",
        _HEADERS_SINA),
    "sina_rt": (
        "https://hq.sinajs.cn/list=hk00700,gb_aapl",
        _HEADERS_SINA),
}

_HEADERS_PYUA = {"User-Agent": "python-requests/2.32.0"}  # 复现工具代码的真实 UA
TARGETS["tx_hk_recent_pyua"] = (
    TARGETS["tx_hk_recent"][0], _HEADERS_PYUA)

_TIMEOUT = 8  # 秒；探针目的在于区分"秒回"与"挂死"，8s 足够


def _hit(key: str) -> dict:
    url, headers = TARGETS[key]
    t0 = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=_TIMEOUT)
        elapsed = time.time() - t0
        return {
            "key": key,
            "http": r.status_code,
            "elapsed_s": round(elapsed, 2),
            "bytes": len(r.content),
            "ok": r.status_code == 200 and len(r.content) > 100,
        }
    except Exception as e:  # requests.exceptions.*
        return {"key": key, "http": 0, "elapsed_s": round(time.time() - t0, 2),
                "bytes": 0, "ok": False, "err": type(e).__name__ + ": " + str(e)[:60]}


def register_probe_tools(mcp) -> None:
    @mcp.tool()
    def source_probe(target: str, mode: str = "single", n: int = 5) -> str:
        """【诊断工具】对白名单数据源做连通性/并发/限速探测。

        target: 白名单键（tx_hk_recent/tx_hk_old800/tx_us_recent/tx_rt_hk/
                em_hk_recent/em_hk_full/em_us_full/em_rt/em_suggest/
                sina_us_daily/sina_hk_klc/sina_rt）
        mode:   single=单次 | burst=并发 n 个 | rate=连续快速 n 次
        n:      burst/rate 模式的次数（1-30）
        """
        if target not in TARGETS:
            return f"错误：未知 target '{target}'，可用：{', '.join(sorted(TARGETS))}"
        n = max(1, min(30, int(n)))

        if mode == "single":
            r = _hit(target)
            return str(r)

        if mode == "burst":
            with ThreadPoolExecutor(max_workers=n) as ex:
                results = list(ex.map(lambda _: _hit(target), range(n)))
            oks = [r for r in results if r["ok"]]
            times = sorted(r["elapsed_s"] for r in results)
            return str({
                "key": target, "mode": "burst", "n": n,
                "success": len(oks),
                "elapsed_s": {"min": times[0], "median": times[n // 2], "max": times[-1]},
                "errs": [r.get("err", f"http{r['http']}") for r in results if not r["ok"]][:5],
            })

        if mode == "rate":
            results = []
            for i in range(n):
                r = _hit(target)
                results.append(r)
                if not r["ok"] and sum(1 for x in results[-3:] if not x["ok"]) >= 3:
                    break
            seq = [f"{r['http']}/{r['elapsed_s']}" + ("" if r["ok"] else "!")
                   for r in results]
            return str({
                "key": target, "mode": "rate", "attempted": len(results),
                "success": sum(1 for r in results if r["ok"]),
                "seq": seq,
            })

        return f"错误：未知 mode '{mode}'（可用 single/burst/rate）"

    log_debug("Registered source probe tools")
