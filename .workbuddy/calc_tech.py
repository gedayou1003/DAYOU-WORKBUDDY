# -*- coding: utf-8 -*-
"""技术指标计算：日线 / 60F / 15F 的 MACD(12,26,9) + MA55 / MA20 + 近 10 日前低。

2026-09-16 维护（I-6）：由每日复制的 calc_tech_0915.py / calc_tech_0916.py 合并而来
（两者行集合 Jaccard 0.85，0915 为纯冗余）。改进：
  - 去掉写死的输出文件名与指数代码，改为 --code / --date 参数
  - 修掉 dkline(160) 被调用两次的冗余（少 1 次 HTTP）

用法：
    python calc_tech.py [--code 000001] [--out .workbuddy/_tech_YYYY-MM-DD.json]
输出：
    JSON {day, m60, m15, recent, prev10_low, prev10_low_date}
    默认写 .workbuddy/_tech_<今日>.json 并同时打印到 stdout
"""
import json, urllib.request, os, sys, argparse, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from market_codes import resolve
from qt_api import get_json as _qt_json   # 域名 failover 统一入口（2026-09-18）
from dragonball_signals import classify_macd_state, classify_break  # DRAGONBALL 融合 P0（2026-09-24）


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))


def dkline(tcode, count):
    js, _src = _qt_json(f'/appstock/app/fqkline/get?param={tcode},day,,,{count},qfq')
    node = js['data'][tcode]
    rows = node.get('qfqday') or node.get('day')
    return [{'t': r[0], 'o': float(r[1]), 'c': float(r[2]), 'h': float(r[3]), 'l': float(r[4])} for r in rows]


def mkline(tcode, period, count):
    js, _src = _qt_json(f'/appstock/app/kline/mkline?param={tcode},{period},,{count}')
    node = js['data'][tcode]
    rows = node.get(period) or []
    return [{'t': r[0], 'o': float(r[1]), 'c': float(r[2]), 'h': float(r[3]), 'l': float(r[4])} for r in rows]


def ema(vals, n):
    k = 2 / (n + 1); e = vals[0]; out = [e]
    for v in vals[1:]:
        e = v * k + e * (1 - k); out.append(e)
    return out


def macd(vals):
    e12 = ema(vals, 12); e26 = ema(vals, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    return dif, dea


def ma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def report(name, rows):
    c = [r['c'] for r in rows]
    dif, dea = macd(c)
    m55 = ma(c, 55); m20 = ma(c, 20)
    last = rows[-1]
    d, e = dif[-1], dea[-1]
    d1, e1 = dif[-2], dea[-2]
    trend = '多头区' if d > e else '空头区'
    cross = ''
    if d > e and d1 <= e1:
        cross = ' → 金叉成立（本根）'
    elif d < e and d1 >= e1:
        cross = ' → 死叉成立（本根）'
    # DRAGONBALL 融合 P0（2026-09-24）：MACD 六态「稳定性」分类（篇4）。
    # 与 zone（多头/空头区）/ dif_dir / dea_dir（动能方向）**语义独立**——
    # 六态刻画「趋势持续性」，动能刻画「方向变化」，二者不可混用（融合蓝图 §一·3）。
    _st = classify_macd_state(d, e)
    return {
        'name': name, 't': last['t'], 'close': last['c'],
        'ma55': round(m55, 2) if m55 else None,
        'ma20': round(m20, 2) if m20 else None,
        'dif': round(d, 2), 'dea': round(e, 2),
        'prev_dif': round(d1, 2), 'prev_dea': round(e1, 2),
        'zone': trend + cross,
        'macd_state': _st['state'],
        'macd_state_side': _st['side'],
        'gap': round(d - e, 2),
        'dif_dir': '向上' if d > d1 else '向下',
        'dea_dir': '向上' if e > e1 else '向下',
        'close_vs_ma55': ('上方' if m55 and last['c'] > m55 else '下方'),
        'close_vs_ma20': ('上方' if m20 and last['c'] > m20 else '下方'),
        # DRAGONBALL 融合 P0（2026-09-24）：刺破/有效跌破语义分层（篇4/5）。
        # 「刺破=预警、有效跌破=确认、破55=分水岭」，用收盘价判「有效」，盘中最低判「刺破」。
        'break_state': classify_break(last['c'], last['l'], m20, m55) if (m20 is not None and m55 is not None) else None,
        'ma55_pct': round((last['c'] - m55) / m55 * 100, 2) if m55 else None,
        'ma20_pct': round((last['c'] - m20) / m20 * 100, 2) if m20 else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', default='000001')
    ap.add_argument('--out', default=None)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    r = resolve(args.code)
    if not r or not r.get('tencent'):
        print(json.dumps({'error': f'无法解析或不支持腾讯接口: {args.code}'}, ensure_ascii=False))
        return 1
    tcode = r['tencent']

    out = {}
    day = dkline(tcode, 160)          # 只取一次，避免重复 HTTP
    out['code'] = r['code']
    out['name'] = r['name']
    out['day'] = report('日线', day)
    out['m60'] = report('60F', mkline(tcode, 'm60', 400))
    out['m15'] = report('15F', mkline(tcode, 'm15', 600))
    out['recent'] = [{'date': x['t'], 'o': x['o'], 'h': x['h'], 'l': x['l'], 'c': x['c']}
                     for x in day[-8:]]
    # 近 10 日最低（前低，不含当日）
    prev10 = day[-11:-1]
    out['prev10_low'] = min(x['l'] for x in prev10)
    out['prev10_low_date'] = min(prev10, key=lambda x: x['l'])['t']
    out['calc_time'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    p = args.out or os.path.join(
        BASE, '_tech_%s.json' % datetime.datetime.now().strftime('%Y-%m-%d'))
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    if not args.quiet:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    print('SAVED=%s' % p, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
