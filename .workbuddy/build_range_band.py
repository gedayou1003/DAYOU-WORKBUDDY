# -*- coding: utf-8 -*-
"""预判核心区间上下轨 vs 上证综指实际走势 —— 数据构建"""
import json, re, urllib.request, os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'range_band_data.json')

_LOG = []
def log(*a):
    _LOG.append(' '.join(str(x) for x in a))

def flush_log():
    with open(os.path.join(BASE, '_band_log.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(_LOG))

# ---------- 1. 取实际日线 ----------
def dkline(count):
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
           f'?param=sh000001,day,,,{count},qfq')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    js = json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))
    node = js['data']['sh000001']
    rows = node.get('qfqday') or node.get('day')
    return [{'date': r[0], 'open': float(r[1]), 'close': float(r[2]),
             'high': float(r[3]), 'low': float(r[4]), 'vol': float(r[5])} for r in rows]

bars = dkline(80)
by_date = {b['date']: b for b in bars}
log('日线范围:', bars[0]['date'], '->', bars[-1]['date'], '共', len(bars))

# ---------- 2. 解析预判区间 ----------
chain = json.load(open(os.path.join(BASE, 'forecast_chain.json'), encoding='utf-8'))

def parse_ranges(s):
    s = str(s or '').replace('～', '-').replace('~', '-').replace('—', '-').replace('－', '-')
    pats = re.findall(r'(\d{4}(?:\.\d+)?)\s*-\s*(\d{4}(?:\.\d+)?)', s)
    if not pats:
        return None
    core = (float(pats[0][0]), float(pats[0][1]))
    ext = (float(pats[-1][0]), float(pats[-1][1])) if len(pats) > 1 else core
    core = (min(core), max(core)); ext = (min(ext), max(ext))
    return core, ext

def parse_target_date(t):
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(t or ''))
    return m.group(0) if m else None

recs = []
for r in chain:
    pr = parse_ranges(r.get('range'))
    if not pr:
        continue
    core, ext = pr
    td = parse_target_date(r.get('target'))
    if not td:
        continue
    sup = (r.get('support') or {}).get('primary')
    res = (r.get('resistance') or {}).get('primary')
    rv = r.get('review') or {}
    act = rv.get('actual') or {}
    if not isinstance(act, dict):
        act = {}
    recs.append(dict(id=r['id'], rtype=r.get('report_type', ''), created=r.get('created_at', ''),
                     target_date=td, direction=str(r.get('direction', ''))[:20],
                     lo=core[0], hi=core[1], elo=ext[0], ehi=ext[1],
                     sup=sup, res=res,
                     act_high=act.get('high'), act_low=act.get('low'),
                     act_close=act.get('close'), act_open=act.get('open'),
                     act_pct=act.get('pct_chg')))
log('可用预判(核心+目标日):', len(recs), '/ 总', len(chain))

# ---------- 3. 聚合到交易日 ----------
TRADE = [b['date'] for b in bars if '2026-08-21' <= b['date'] <= '2026-09-15']
log('目标交易日:', len(TRADE), TRADE[0], '->', TRADE[-1])

days = []
for d in TRADE:
    rs = [x for x in recs if x['target_date'] == d]
    if not rs:
        days.append(dict(date=d, n=0, bar=by_date.get(d)))
        continue
    import statistics as st
    days.append(dict(
        date=d, n=len(rs),
        lo=round(st.median([x['lo'] for x in rs]), 2),
        hi=round(st.median([x['hi'] for x in rs]), 2),
        elo=round(st.median([x['elo'] for x in rs]), 2),
        ehi=round(st.median([x['ehi'] for x in rs]), 2),
        lo_w=round(min(x['lo'] for x in rs), 2),
        hi_w=round(max(x['hi'] for x in rs), 2),
        kinds=','.join(sorted(set(x['id'].split('-')[-1] for x in rs))),
        ids=[x['id'] for x in rs],
        bar=by_date.get(d),
    ))

log('')
log('日期        n  核心下轨  核心上轨  实测L     实测H     收盘      收盘带内  高低全带内')
for x in days:
    b = x['bar']
    if not b or x['n'] == 0:
        log(f"{x['date']}  -- 无预判")
        continue
    close_in = x['lo'] <= b['close'] <= x['hi']
    full_in = x['lo'] <= b['low'] and b['high'] <= x['hi']
    log(f"{x['date']}  {x['n']:2d}  {x['lo']:8.2f}  {x['hi']:8.2f}  {b['low']:9.2f} {b['high']:9.2f} {b['close']:9.2f}   {'Y' if close_in else 'N':^9}  {'Y' if full_in else 'N':^9}")

val = [x for x in days if x['n'] > 0 and x['bar']]
in_close = sum(1 for x in val if x['lo'] <= x['bar']['close'] <= x['hi'])
in_high = sum(1 for x in val if x['bar']['high'] <= x['hi'])
in_low = sum(1 for x in val if x['bar']['low'] >= x['lo'])
in_full = sum(1 for x in val if x['lo'] <= x['bar']['low'] and x['bar']['high'] <= x['hi'])
width = [x['hi'] - x['lo'] for x in val]
log('')
log(f'=== 汇总（{len(val)} 个交易日）===')
log(f'收盘落在核心带内: {in_close}/{len(val)} = {in_close/len(val)*100:.1f}%')
log(f'高点未破上轨  : {in_high}/{len(val)} = {in_high/len(val)*100:.1f}%')
log(f'低点未破下轨  : {in_low}/{len(val)} = {in_low/len(val)*100:.1f}%')
log(f'高低全在带内  : {in_full}/{len(val)} = {in_full/len(val)*100:.1f}%')
log(f'核心带平均宽度: {sum(width)/len(width):.1f} 点 ({sum(width)/len(width)/val[-1]["bar"]["close"]*100:.2f}%) / 最窄 {min(width):.0f} / 最宽 {max(width):.0f}')

json.dump(dict(days=days, bars=bars[-40:], summary=dict(
    n_days=len(val), in_close=in_close, in_high=in_high, in_low=in_low, in_full=in_full,
    avg_width=round(sum(width)/len(width), 1))),
    open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, default=str)
log('\n写出:', OUT)
flush_log()
