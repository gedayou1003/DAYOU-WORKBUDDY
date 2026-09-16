# -*- coding: utf-8 -*-
"""
获取指数/标的当日（最近交易日）OHLC，供"预判复盘"对比实际走势使用。
支持任意腾讯可用的宽基指数（通过 market_codes 注册表解析）。

用法:
    python get_daily_ohlc.py [code] [days] [--slot <slot>] [--force] [--no-cache]
    code: 标准代码或名称，如 000001 / 000300 / 沪深300 / sh000905 / 中证1000（默认 000001 上证综指）
    days: 往回取几个交易日（默认 1=最近交易日）
    --slot:  数据时点槽位（morning / noon / afternoon / close），同一槽位同日复用缓存
    --force: 忽略缓存强制重新拉取（并覆盖该槽位缓存）
    --no-cache: 不读也不写缓存（纯透传，调试用）

输出: JSON {code, name, date, open, high, low, close, prev_close, pct_chg, gap_pct, gap, gap_type, source}

缓存设计（2026-09-16 维护新增 I-4）
-----------------------------------
问题：本脚本原先无缓存，一份报告生成过程中会被反复调用 4-5 次。盘中（午间档 12:30 /
盘中档）价格在动，多次调用必然返回不同数字 → 同一份报告里印出两组「现价 / 涨跌幅」，
支撑压力相对现价 % 自相矛盾。实测 2026-09-16 相隔 1 分钟两次调用：close 3855.48(-0.23%)
vs 3854.20(-0.26%)。

方案：按「日期 + 槽位」落盘缓存 + **统一 TTL（默认 30 分钟）**。
  - 一份报告的生成过程通常 < 30 分钟 → 报告内所有取数完全一致（解决矛盾）
  - 各档位之间相隔数小时 → TTL 必然过期 → 自动重新取数（不会串味）
    例如：午间档 12:30 缓存的盘中快照，不会污染 16:00 收盘档的真实收盘价
  - --slot 只做缓存命名空间（便于排查/对比），不改变 TTL 语义
  - --ttl N 自定义有效期（分钟）；--ttl 0 表示当日长期有效（需显式指定，谨慎使用）
  - --force 强制刷新；--no-cache 完全禁用
"""
import sys, json, datetime, urllib.request, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_codes import resolve

UA = {'User-Agent': 'Mozilla/5.0'}

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, '_ohlc_cache')
ADHOC_SLOT = '__adhoc__'
DEFAULT_TTL_MIN = 30


def _cache_path(code, slot, day):
    safe = slot.replace('/', '_').replace('\\', '_')
    return os.path.join(CACHE_DIR, f'{code}_{day}_{safe}.json')


def _read_cache(code, slot, day, ttl_min=None):
    """ttl_min=None → 不过期；ttl_min=0 → 当日不过期；ttl_min>0 → 分钟数"""
    p = _cache_path(code, slot, day)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            payload = json.load(f)
    except Exception:
        return None
    if ttl_min:
        ts = payload.get('_cached_at_ts')
        if not ts:
            return None
        age_min = (datetime.datetime.now().timestamp() - ts) / 60.0
        if age_min > ttl_min:
            return None
    return payload.get('data')


def _write_cache(code, slot, day, data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(code, slot, day), 'w', encoding='utf-8') as f:
            json.dump({'_cached_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                       '_cached_at_ts': datetime.datetime.now().timestamp(),
                       '_slot': slot, 'data': data}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_daily_ohlc(tencent_code, days=1):
    """腾讯 fqkline 日线，取最近 N 个交易日（最后一个为最近交易日）"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={tencent_code},day,,,60,qfq")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    node = data["data"][tencent_code]
    kline = node.get("qfqday") or node.get("day") or []
    if not kline:
        raise RuntimeError(f"腾讯接口未返回K线数据 ({tencent_code})")
    rows = kline[-days:] if days > 0 else kline
    out = []
    for r in rows:
        # r: [date, open, close, high, low, volume, ...]
        dt = r[0]
        o, c, h, l = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        out.append({"date": dt, "open": o, "high": h, "low": l, "close": c})
    result = out[-1]
    # prev_close 取完整 kline 的倒数第二根（而非切片后 rows 的倒数第二根），
    # 否则 days=1 时 rows 只有 1 根，prev_close/pct_chg 会缺失
    if len(kline) >= 2:
        prev_close = float(kline[-2][2])  # kline 行格式 [date, open, close, high, low, ...]
        result["prev_close"] = prev_close
        result["pct_chg"] = round((result["close"] - prev_close) / prev_close * 100, 2)
        # 开盘跳空（gap）：今日开盘 vs 昨日收盘，量化高低开幅度（供预判"现价锚点"修正用）
        gap_pct = round((result["open"] - prev_close) / prev_close * 100, 2)
        result["gap_pct"] = gap_pct
        result["gap"] = round(result["open"] - prev_close, 2)  # 跳空绝对点数
        if gap_pct > 0.15:
            result["gap_type"] = "高开"
        elif gap_pct < -0.15:
            result["gap_type"] = "低开"
        else:
            result["gap_type"] = "平开"
    return result


def _parse_args(argv):
    code_arg, days = "000001", 1
    slot, force, no_cache, ttl = None, False, False, DEFAULT_TTL_MIN
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--force':
            force = True
        elif a == '--no-cache':
            no_cache = True
        elif a == '--slot':
            i += 1
            if i < len(argv):
                slot = argv[i]
        elif a.startswith('--slot='):
            slot = a.split('=', 1)[1]
        elif a == '--ttl':
            i += 1
            if i < len(argv):
                try:
                    ttl = int(argv[i])
                except ValueError:
                    pass
        elif a.startswith('--ttl='):
            try:
                ttl = int(a.split('=', 1)[1])
            except ValueError:
                pass
        else:
            pos.append(a)
        i += 1
    if pos:
        code_arg = pos[0]
    if len(pos) > 1:
        try:
            days = int(pos[1])
        except ValueError:
            pass
    return code_arg, days, slot, force, no_cache, ttl


if __name__ == "__main__":
    code_arg, days, slot, force, no_cache, ttl = _parse_args(sys.argv[1:])

    resolved = resolve(code_arg)
    if not resolved:
        print(json.dumps({"error": f"无法识别的标的: {code_arg}", "source": "market_codes"},
                         ensure_ascii=False))
        sys.exit(1)
    if not resolved["tencent"]:
        print(json.dumps({"error": f"{resolved['name']} 腾讯接口暂不支持（数据源: {resolved['data_source']}）",
                          "code": resolved["code"], "source": "market_codes"},
                         ensure_ascii=False))
        sys.exit(1)

    std_code = resolved["code"]
    day = datetime.datetime.now().strftime('%Y-%m-%d')
    eff_slot = slot or ADHOC_SLOT

    # 1) 读缓存（统一 TTL：0 = 当日不过期）
    if not force and not no_cache:
        cached = _read_cache(std_code, eff_slot, day, ttl_min=ttl)
        if cached is not None:
            cached = dict(cached)
            cached["cache"] = "hit"
            print(json.dumps(cached, ensure_ascii=False, indent=2))
            sys.exit(0)

    # 2) 拉取
    try:
        r = fetch_daily_ohlc(resolved["tencent"], days)
        r["code"] = std_code
        r["name"] = resolved["name"]
        r["source"] = "tencent_fqkline"
        r["fetch_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        r["cache"] = "miss"
        if not no_cache:
            _write_cache(std_code, eff_slot, day, r)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "code": std_code,
                          "name": resolved["name"], "source": "tencent_fqkline"},
                         ensure_ascii=False))
        sys.exit(1)
