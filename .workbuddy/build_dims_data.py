# -*- coding: utf-8 -*-
"""四维命中率（方向/区间/支撑/压力）滚动序列构建"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(BASE, 'forecast_chain.json')
OUT = os.path.join(BASE, 'dims_hitrate_data.json')
LOG = os.path.join(BASE, '_dims_log.txt')

L = []
def log(*a): L.append(' '.join(str(x) for x in a))

fc = json.load(open(CHAIN, encoding='utf-8'))
verified = [r for r in fc if r.get('status') == 'verified']
log('verified 条数:', len(verified))

DIMS = ['direction', 'range', 'support', 'resistance']
ZH = {'direction': '方向', 'range': '区间', 'support': '支撑', 'resistance': '压力'}

def sort_key(r):
    rv = r.get('review') or {}
    t = rv.get('reviewed_at') or rv.get('verified_at') or r.get('created_at') or r.get('id')
    return str(t)

verified.sort(key=sort_key)

rows = []
for idx, r in enumerate(verified, 1):
    rv = r.get('review') or {}
    if not isinstance(rv, dict):
        rv = {}
    t = rv.get('reviewed_at') or rv.get('verified_at') or r.get('created_at') or r.get('id')
    date = str(t)[:10]
    row = dict(idx=idx, id=r['id'], date=date)
    for k in DIMS:
        v = rv.get(k + '_verdict') or rv.get(k) or ''
        v = v if isinstance(v, str) else ''
        if v.startswith('✅'):
            row[k] = 1
        elif v.startswith('⚠'):
            row[k] = 0.5  # 部分：暂记 0.5，用于"含部分"口径
        elif v.startswith('❌'):
            row[k] = 0
        else:
            row[k] = None
    rows.append(row)

# 滚动累计命中率（两种口径：纯✅ / ✅+0.5*⚠️）
acc = {k: {'ok': 0, 'part': 0, 'tot': 0} for k in DIMS}
for row in rows:
    for k in DIMS:
        v = row[k]
        if v is None:
            continue
        acc[k]['tot'] += 1
        if v == 1:
            acc[k]['ok'] += 1
        elif v == 0.5:
            acc[k]['part'] += 1
    # 记录当前累计
    for k in DIMS:
        a = acc[k]
        row[k + '_pure'] = round(a['ok'] / a['tot'] * 100, 1) if a['tot'] else None
        row[k + '_soft'] = round((a['ok'] + 0.5 * a['part']) / a['tot'] * 100, 1) if a['tot'] else None

# 最终统计
log('')
log('=== 最终四维命中率（按 id 时间序累计） ===')
for k in DIMS:
    a = acc[k]
    tot = a['tot']; ok = a['ok']; part = a['part']
    pure = ok / tot * 100 if tot else 0
    soft = (ok + 0.5 * part) / tot * 100 if tot else 0
    log(f"{ZH[k]}: ✅{ok} ⚠️{part} ❌{tot-ok-part} 纯命中率 {pure:.1f}%  含部分(0.5) {soft:.1f}%")

# 缺失统计
miss = {k: sum(1 for r in rows if r[k] is None) for k in DIMS}
log('缺失判定:', miss)

json.dump(dict(rows=rows, final={k: acc[k] for k in DIMS}), open(OUT, 'w', encoding='utf-8'),
          ensure_ascii=False, default=str)
with open(LOG, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('OK rows=', len(rows))
