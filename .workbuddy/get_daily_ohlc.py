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
import qt_api      # 腾讯接口多域名 failover（2026-09-18：web.ifzq.gtimg.cn 被代理拦）

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
    except Exception:  # silent-ok: 缓存读失败按未命中处理，会走网络重新抓取
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
    except Exception:  # silent-ok: 缓存写失败不影响本轮已取到的行情
        pass


def fetch_daily_ohlc(tencent_code, days=1):
    """腾讯 fqkline 日线，取最近 N 个交易日（最后一个为最近交易日）"""
    data, src = qt_api.get_json(
        f"/appstock/app/fqkline/get?param={tencent_code},day,,,60,qfq", timeout=15)
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


def _int_arg(raw, what):
    """整型入参解析：非法即报错，**不再静默回退默认值**（2026-09-21 加固）。

    旧实现是 `except ValueError: pass`，于是 `--ttl abc`、`000001 abc` 会
    静默按默认值执行 —— 调用方以为自己指定了 TTL / 拿了 N 天，实际拿到默认值。
    属「静默失败」反模式，与 fetch_zsxq 的窗口静默回退同族。
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError('%s 需为整数，收到 %r' % (what, raw))


def _need_val(argv, i, opt):
    """取 `--opt value` 形式的取值；缺值直接报错（旧实现是静默忽略整个选项）。"""
    if i + 1 >= len(argv):
        raise ValueError('%s 缺少取值' % opt)
    return argv[i + 1]


def _parse_args(argv):
    """解析入参。非法入参一律 raise ValueError，由 __main__ 转成 stderr + 退出码 1。

    2026-09-21 加固前：`--ttl abc` / `000001 abc` / `--slot`（缺值）/ `--no-cach`
    （拼错）**全部被静默忽略并落回默认值**，调用方拿到的数据与预期不符却零提示。
    """
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
            slot = _need_val(argv, i, '--slot')
            i += 1
        elif a.startswith('--slot='):
            slot = a.split('=', 1)[1]
        elif a == '--ttl':
            ttl = _int_arg(_need_val(argv, i, '--ttl'), '--ttl')
            i += 1
        elif a.startswith('--ttl='):
            ttl = _int_arg(a.split('=', 1)[1], '--ttl')
        elif a.startswith('-'):
            # 拼错的选项旧实现会被当成位置参数或直接吞掉；现在显式报错
            raise ValueError('未知选项 %r' % a)
        else:
            pos.append(a)
        i += 1
    if pos:
        code_arg = pos[0]
    if len(pos) > 1:
        days = _int_arg(pos[1], '天数（第 2 个位置参数）')
    return code_arg, days, slot, force, no_cache, ttl


if __name__ == "__main__":
    try:
        code_arg, days, slot, force, no_cache, ttl = _parse_args(sys.argv[1:])
    except ValueError as _e:
        _usage = next((l.strip() for l in (__doc__ or '').splitlines()
                       if 'python get_daily_ohlc.py' in l),
                      'python get_daily_ohlc.py [code] [days] [--slot <slot>] [--force] [--no-cache]')
        sys.stderr.write('[FAIL] 参数错误：%s\n用法：%s\n' % (_e, _usage))
        sys.exit(1)

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
        # 实际命中的域名（备用镜像与主域名数据同源，仅便于排查网络层问题）
        r["source_host"] = qt_api.LAST_SOURCE
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
