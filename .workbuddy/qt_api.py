# -*- coding: utf-8 -*-
"""腾讯行情接口统一入口（多域名 failover + 显式来源标注）。

为什么存在（2026-09-18 实测，本机沙箱代理会**按域名**拦截，且清单会变）
------------------------------------------------------------------------
  - `web.ifzq.gtimg.cn`                → **HTTP 501 Not Implemented**（本次被拦）
  - `push2his / push2.eastmoney.com`   → RemoteDisconnected（本次被拦）
  - `ifzq.gtimg.cn`（分钟线）           → 200 正常
  - `proxy.finance.qq.com/ifzqgtimg`   → 200 正常（**同一份数据的官方镜像**）
  - `qt.gtimg.cn`（实时行情）           → 200 正常
  → 因此 akshare 的**东财系**函数不可用；**申万系**（`index_realtime_sw` /
    `index_hist_sw`，走申万源）实测正常。

后果：原先 6 个脚本把 `https://web.ifzq.gtimg.cn/...` 各自写死在文件里 ——
一处被拦 → 6 个脚本同时瘫（get_daily_ohlc / calc_tech（含 calc_tech_multi）/
scan_ths / analyze_000001_multi / build_range_band / forecast_analyze /
fetch_backtest_data）。修法：**域名收敛到本模块**，按 QT_BASES 顺序尝试。

设计纪律（与 `gen_forecast_svg.py` 的教训一致）
----------------------------------------------
**不做静默回退**：全部域名都失败 → 抛 RuntimeError，并把每个域名各自的失败原因
列出来。绝不在失败时返回陈旧/写死数据 —— 那比崩溃危险得多（曾把 8/31 的走势图
静默塞进 9 月报告）。备用域名只改变「从哪台机器取」，**不改变取到的是什么**：
同一 API、同一参数、同一份行情，因此不构成「静默换口径」。

用法：
    from qt_api import get_json
    data, src = get_json('/appstock/app/fqkline/get?param=sh000001,day,,,60,qfq')
    # src = 实际命中的域名，可写进产物做来源标注
"""
import json
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'}

# 同一 API 的多个可达域名（前缀不同，但 `/appstock/...` 路径完全一致），按优先级排列
QT_BASES = (
    'https://web.ifzq.gtimg.cn',               # 历史既有域名（本机代理可能拦）
    'https://proxy.finance.qq.com/ifzqgtimg',  # 官方镜像（2026-09-18 新增，实测可用）
    'https://ifzq.gtimg.cn',                   # 备用（分钟线历来走这个）
)

# 最近一次成功使用的域名（供调用方标注来源；进程级）
LAST_SOURCE = None


def get_json(path, timeout=20):
    """GET 腾讯 appstock 接口。

    path 形如 `/appstock/app/fqkline/get?param=...`（不含域名）。
    返回 `(data, base)`；全部域名均失败时抛 RuntimeError（含逐域名失败原因）。
    """
    global LAST_SOURCE
    errs = []
    for base in QT_BASES:
        try:
            req = urllib.request.Request(base + path, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            LAST_SOURCE = base
            return data, base
        except Exception as e:          # noqa: BLE001 —— 逐个域名试，失败仅记录
            errs.append('%s → %r' % (base, e))
    raise RuntimeError(
        '腾讯接口全部域名不可用（path=%s）：\n  %s' % (path, '\n  '.join(errs)))


def get(url, timeout=20):
    """兼容旧调用风格：传**完整 URL** 时自动抽出 `/appstock/...` 走 failover。

    仅支持 appstock 接口；其他接口直接报错，避免误用。
    """
    i = url.find('/appstock/')
    if i < 0:
        raise ValueError('非 appstock 接口，不适用 failover：%s' % url)
    data, _ = get_json(url[i:], timeout=timeout)
    return data


if __name__ == '__main__':
    import sys
    probe = ('/appstock/app/fqkline/get?param=sh000001,day,,,3,qfq'
             if len(sys.argv) < 2 else sys.argv[1])
    d, s = get_json(probe)
    print('OK via %s' % s)
    print(json.dumps(d, ensure_ascii=False)[:400])
