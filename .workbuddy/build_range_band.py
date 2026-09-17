# -*- coding: utf-8 -*-
"""预判核心区间上下轨 vs 上证综指实际走势 —— 区间命中率统计（按需运行，非日常流水线）。

输出 range_band_data.json + _band_log.txt，用于「预判区间给得准不准」的量化复盘。

⚠️ 2026-09-17 加固：原版把统计窗口写死为 `'2026-08-21' <= date <= '2026-09-15'`，
   9 月一过就再也统计不到新数据（且没有任何报错，只是结果悄悄停在旧区间）。
   现改为**由链记录的目标日自动推导**区间（recs 的 target_date min..max），
   可用 --since/--until 显式覆盖。

用法：
    python build_range_band.py                                  # 窗口=链里所有目标日
    python build_range_band.py --since 2026-09-01 --until 2026-09-15
    python build_range_band.py --out /tmp/band.json --bars 400
"""
import argparse
import json
import os
import re
import statistics as st
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

_ap = argparse.ArgumentParser(
    description='预判核心区间 vs 实际走势 —— 区间命中率统计',
    formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument('--since', default=None, metavar='YYYY-MM-DD',
                 help='统计窗口起始日；不给则取链记录 target_date 的最小值')
_ap.add_argument('--until', default=None, metavar='YYYY-MM-DD',
                 help='统计窗口结束日；不给则取链记录 target_date 的最大值')
_ap.add_argument('--bars', type=int, default=260, metavar='N',
                 help='拉取日线条数（默认 260，约一年）')
_ap.add_argument('--out', default=None, metavar='PATH',
                 help='输出 JSON 路径（默认 .workbuddy/range_band_data.json）')
ARGS, _unknown = _ap.parse_known_args()

OUT = ARGS.out or os.path.join(BASE, 'range_band_data.json')

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

bars = dkline(ARGS.bars)
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
# 窗口不再写死：优先 --since/--until，否则由链记录的目标日自动推导
_tds = sorted(x['target_date'] for x in recs)
SINCE = ARGS.since or (_tds[0] if _tds else bars[-20]['date'])
UNTIL = ARGS.until or (_tds[-1] if _tds else bars[-1]['date'])
if SINCE > UNTIL:
    raise SystemExit('[FAIL] --since(%s) 晚于 --until(%s)' % (SINCE, UNTIL))
TRADE = [b['date'] for b in bars if SINCE <= b['date'] <= UNTIL]
if not TRADE:
    raise SystemExit('[FAIL] 窗口 %s~%s 内没有任何日线数据。\n'
                     '       日线可用范围 %s~%s，请用 --since/--until 调整。'
                     % (SINCE, UNTIL, bars[0]['date'], bars[-1]['date']))
log('统计窗口:', SINCE, '->', UNTIL, '(来自%s)' % ('参数' if (ARGS.since or ARGS.until) else '链记录目标日'))
log('目标交易日:', len(TRADE), TRADE[0], '->', TRADE[-1])

days = []
for d in TRADE:
    rs = [x for x in recs if x['target_date'] == d]
    if not rs:
        days.append(dict(date=d, n=0, bar=by_date.get(d)))
        continue
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
if not val:
    log('')
    log('=== 窗口内没有任何「有预判且已收盘」的交易日，无法统计 ===')
    json.dump(dict(days=days, bars=bars[-40:],
                   summary=dict(n_days=0, since=SINCE, until=UNTIL)),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, default=str)
    log('\n写出:', OUT)
    flush_log()
    sys.exit(2)
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
    n_days=len(val), since=SINCE, until=UNTIL,
    in_close=in_close, in_high=in_high, in_low=in_low, in_full=in_full,
    avg_width=round(sum(width)/len(width), 1))),
    open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, default=str)
log('\n写出:', OUT)
flush_log()
