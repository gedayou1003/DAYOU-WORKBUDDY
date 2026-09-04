# -*- coding: utf-8 -*-
"""统一 forecast_chain.json 的 review verdict 字段名。

历史遗留：早期记录用 `*_hit` 字段（部分还带 ✅/⚠️/❌ 前缀，部分是纯中文），
后期记录用 `*_verdict` 字段。review_close_*.py 的偏差统计只读 `*_verdict`，
导致旧记录被静默跳过、方向命中率虚高。

本脚本把 5 条旧记录补上 `*_verdict` 字段，统一口径后重算偏差统计。
"""
import json, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

# 纯中文 *_hit 记录的人工 verdict 映射（无 ✅/⚠️/❌ 前缀，需按语义补）
MANUAL_MAP = {
    '2026-08-21-close': {
        'direction_verdict': '❌ 相反（预判震荡偏多，实际收跌）',
        'range_verdict': '❌ 下沿失守（收盘3882.01破3884下沿，盘中低3855.35）',
        'support_verdict': '❌ 支撑跌破（3883.79，收盘3882.01，真破位）',
        'resistance_verdict': '✅ 压力精准命中（3911.08，实际高3910.24，差0.02%）',
    },
    '2026-08-21-evening': {
        'direction_verdict': '❌ 相反（预判震荡偏多，实际收跌）',
        'range_verdict': '❌ 下沿失守（收盘3882.01破3884下沿，盘中低3855.35）',
        'support_verdict': '❌ 支撑跌破（3883.79，收盘3882.01，真破位）',
        'resistance_verdict': '✅ 压力精准命中（3911.08，实际高3910.24，差0.02%）',
    },
    '2026-08-25-evening': {
        'direction_verdict': '❌ 相反（预判偏空，实际收涨+0.59%）',
        'range_verdict': '❌ 上沿失守（收盘3912.52破3911上沿，盘中高3926.44）',
        'support_verdict': '✅ 支撑未触及（实际低3881.74，高于3850.86支撑30点）',
        'resistance_verdict': '❌ 压力被突破（3911.08被收盘突破，盘中高3926.44）',
    },
}

with open(CHAIN, encoding='utf-8') as f:
    fc = json.load(f)

patched = 0
for item in fc:
    rv = item.get('review')
    if not isinstance(rv, dict):
        continue
    # 已有 *_verdict 的跳过
    if all(rv.get(k + '_verdict') for k in ('direction', 'range', 'support', 'resistance')):
        continue
    rid = item.get('id')
    # 1) 人工映射表优先
    if rid in MANUAL_MAP:
        for k, v in MANUAL_MAP[rid].items():
            rv[k] = v
        patched += 1
        continue
    # 2) *_hit 已有 ✅/⚠️/❌ 前缀的，直接复制到 *_verdict
    if all(rv.get(k + '_hit') for k in ('direction', 'range', 'support', 'resistance')):
        for k in ('direction', 'range', 'support', 'resistance'):
            rv[k + '_verdict'] = rv[k + '_hit']
        patched += 1

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(fc, f, ensure_ascii=False, indent=2)

print(f'已补 *_verdict 字段：{patched} 条')

# ============ 重算偏差统计（统一口径） ============
verified = [r for r in fc if r.get('status') == 'verified']
dims = ['direction', 'range', 'support', 'resistance']
stat = {k: {'ok': 0, 'part': 0, 'fail': 0} for k in dims}
for r in verified:
    rv = r.get('review')
    if not isinstance(rv, dict):
        continue
    for k in dims:
        v = rv.get(k + '_verdict') or ''
        if not isinstance(v, str) or not v:
            continue
        if v.startswith('✅'):
            stat[k]['ok'] += 1
        elif v.startswith('⚠'):
            stat[k]['part'] += 1
        elif v.startswith('❌'):
            stat[k]['fail'] += 1

bc = Counter()
for r in verified:
    rv = r.get('review')
    if not isinstance(rv, dict):
        continue
    bt = rv.get('bias_type') or rv.get('bias') or []
    if isinstance(bt, str):
        bt = [bt]
    for t in bt:
        bc[t] += 1

print(f'\n=== 偏差统计（{len(verified)} 期 verified，统一口径） ===')
for k, zh in [('direction', '方向'), ('range', '区间'), ('support', '支撑'), ('resistance', '压力')]:
    s = stat[k]
    ok, part, fail = s['ok'], s['part'], s['fail']
    tot = ok + part + fail
    rate = f'{ok/tot*100:.1f}%' if tot else '-'
    print(f'{zh}: ✅{ok} ⚠️{part} ❌{fail} 纯命中率 {rate}')

print('\n=== bias_type 分布（top 12） ===')
for k, v in bc.most_common(12):
    print(f'  {k}: {v}')
