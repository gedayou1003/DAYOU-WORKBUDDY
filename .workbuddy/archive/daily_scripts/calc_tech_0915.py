# -*- coding: utf-8 -*-
"""9/15 收盘技术指标：日线/60F/15F 的 MACD(12,26,9) + MA55/MA20"""
import json, urllib.request, os

BASE = os.path.dirname(os.path.abspath(__file__))

def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))

def dkline(count):
    js = _get(f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,{count},qfq')
    node = js['data']['sh000001']
    rows = node.get('qfqday') or node.get('day')
    return [{'t': r[0], 'o': float(r[1]), 'c': float(r[2]), 'h': float(r[3]), 'l': float(r[4])} for r in rows]

def mkline(period, count):
    js = _get(f'https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh000001,{period},,{count}')
    node = js['data']['sh000001']
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
    if d > e and d1 <= e1: cross = ' → 金叉成立（本根）'
    elif d < e and d1 >= e1: cross = ' → 死叉成立（本根）'
    return {
        'name': name, 't': last['t'], 'close': last['c'],
        'ma55': round(m55, 2) if m55 else None,
        'ma20': round(m20, 2) if m20 else None,
        'dif': round(d, 2), 'dea': round(e, 2),
        'prev_dif': round(d1, 2), 'prev_dea': round(e1, 2),
        'zone': trend + cross,
        'gap': round(d - e, 2),
        'dif_dir': '向上' if d > d1 else '向下',
        'close_vs_ma55': ('上方' if m55 and last['c'] > m55 else '下方'),
        'close_vs_ma20': ('上方' if m20 and last['c'] > m20 else '下方'),
    }

out = {}
out['day'] = report('日线', dkline(120))
out['m60'] = report('60F', mkline('m60', 300))
out['m15'] = report('15F', mkline('m15', 500))

# 日线近 5 日 OHLC
day = dkline(120)
out['recent'] = [{'date': r['t'], 'o': r['o'], 'h': r['h'], 'l': r['l'], 'c': r['c']} for r in day[-6:]]

with open(os.path.join(BASE, '_tech_0915.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('OK')
