# -*- coding: utf-8 -*-
"""9/2 收盘复盘：把 2026-09-02-morning / 2026-09-02-noon 两条 pending 转 verified 并写 review。

复盘数据源：
- 全天 OHLC：腾讯 fqkline（get_daily_ohlc.py）open 3963.07 / high 3965.81 / low 3932.25 / close 3941.39 / pct -0.97%
- 午后分时（腾讯 minute 接口，noon 预判针对"午后~收盘"时段）：午后高 3957.38 / 午后低 3939.39 / 收 3941.39
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    fc = json.load(f)

# ============ 1. 复盘 9/2-morning（target 全天） ============
for item in fc:
    if item['id'] == '2026-09-02-morning' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-02 15:10（收盘后复盘）',
            'actual': {
                'date': '2026-09-02',
                'open': 3963.07, 'high': 3965.81, 'low': 3932.25, 'close': 3941.39,
                'pct_chg': -0.97, 'prev_close': 3979.89,
                'note': '全天低开低走收 3941.39 -0.97%；盘中最低 3932.25 精准回踩 60F55(3930.92) 差 1.25 点未破；全天高点 3965.81 仅开盘瞬间，远未触及 4012'
            },
            'direction_verdict': '✅ 命中（预判震荡偏空 v5 -2，实际收 -0.97% 偏空兑现）',
            'range_verdict': '✅ 区间内（预判 3931-4012 核心 81 点，实际 3932.25-3965.81 完全在内）',
            'support_verdict': '✅ 守住（支撑 3931=60F55 分水岭，实际低 3932.25 差 1.25 点精准回踩未破）',
            'resistance_verdict': '✅ 守住（压力 4012=233日线，实际高 3965.81 差 46.19 点，全天未触及）',
            'bias_type': [],
            'foreseeable': '完全可预料',
            'foresee_reason': 'T&J 昨夜「明天大概率有效跌破 15F 中轨、最小调整 15F X段回踩 60F 中轨、60F55 得失关键」完全兑现——开盘 3963 直接低开破 15F 中轨(3983)，一路下探至 3932.25 精准回踩 60F55(3930.92) 后止跌，收 3941.39。v5 方向打分 -2 偏空 + 15F BOLL 0.46% 极度收口（变盘前）双确认，无偏差。',
            'note': '四维全 ✅ 满分命中。morning 核心场景 A「有效跌破 15F 中轨 → 回踩 60F55 找支撑」完整兑现，60F55 得失判断精准。'
        }
        break

# ============ 2. 复盘 9/2-noon（target 午后~收盘） ============
for item in fc:
    if item['id'] == '2026-09-02-noon' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-02 15:10（收盘后复盘）',
            'actual': {
                'date': '2026-09-02',
                'open': 3963.07, 'high': 3965.81, 'low': 3932.25, 'close': 3941.39,
                'pct_chg': -0.97, 'prev_close': 3979.89,
                'note': 'noon 预判针对「午后~收盘」时段：午后高点 3957.38（未破 15F55=3962.84）、午后低点 3939.39、午后从 3949.52 收 3941.39 跌 -0.21%'
            },
            'direction_verdict': '✅ 命中（预判震荡偏弱 v5 -1，午后 3949.52→3941.39 继续下探 -0.21%，偏弱兑现）',
            'range_verdict': '✅ 区间内（预判 3931-3963 核心 32 点，午后实际 3939.39-3957.38 完全在内）',
            'support_verdict': '✅ 守住（支撑 3931=60F55，午后低 3939.39 未触及）',
            'resistance_verdict': '✅ 守住（压力 3962.84=15F55 反抽必过线，午后高 3957.38 差 5.46 点未破，反抽失败）',
            'bias_type': [],
            'foreseeable': '完全可预料',
            'foresee_reason': 'T&J 盘中 10:46「反抽必须突破 15F55(3963)，否则确认 60F 级别下跌」精准兑现——午后反抽最高 3957.38 未破 3963，60F 级别下跌确认，收盘 3941.39 继续下探。noon 三剧本中 B 剧本（反抽不破 15F55 → 60F 下跌确认，prob 0.35）命中。',
            'note': '四维全 ✅ 满分命中。核心分水岭 15F55(3963) 判断精准，B 剧本兑现，午后无追高误判。'
        }
        break

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(fc, f, ensure_ascii=False, indent=2)

from collections import Counter
print('status 分布:', Counter(r.get('status') for r in fc))
print('total:', len(fc))

# ============ 3. 程序化重算偏差统计（复用 report_builder 逻辑） ============
verified = [r for r in fc if r.get('status') == 'verified']
dims = ['direction', 'range', 'support', 'resistance']
stat = {k: {'ok': 0, 'part': 0, 'fail': 0} for k in dims}
for r in verified:
    rv = r.get('review')
    if not isinstance(rv, dict):
        continue
    for k in dims:
        v = rv.get(k + '_verdict') or rv.get(k) or ''
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

print('\n=== 偏差统计（%d 期） ===' % len(verified))
for k, zh in [('direction', '方向'), ('range', '区间'), ('support', '支撑'), ('resistance', '压力')]:
    s = stat[k]
    ok, part, fail = s['ok'], s['part'], s['fail']
    tot = ok + part + fail
    rate = f'{ok/tot*100:.1f}%' if tot else '-'
    print(f'{zh}: ✅{ok} ⚠️{part} ❌{fail} 纯命中率 {rate}')

print('\n=== bias_type 分布 ===')
for k, v in bc.most_common():
    print(f'  {k}: {v}')
