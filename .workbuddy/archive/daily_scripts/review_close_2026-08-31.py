# -*- coding: utf-8 -*-
"""8/31 收盘复盘：把 2026-08-28-evening（target 2026-08-31 周一）pending 转 verified 并写 review。

复盘数据源：
- 8/31 全天 OHLC（腾讯 fqkline）：open 3926.53 / high 3986.30 / low 3926.50 / close 3986.30 / pct +0.86%
- 前收 3952.18（8/28 收盘）

8-28-evening 预判原文要点：
- direction: 震荡偏多（v5 -2 方向不明偏多）
- range: 3927-3970
- support: 3927.85（周线一买 + 60F中枢下沿共振）
- resistance: 3967.59（60F中枢上沿 + 今日高3970.31假突破压力带）
- scenario A: 放量突破3967-3970 → 看4034/4061
- scenario B: 缩量冲3970遇阻 → 回踩3927/3909
- note: 日线MACD DIF上穿零轴转多 + 引擎C全线偏多，但日线结构仍在4061中枢下方
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    fc = json.load(f)

# ============ 复盘 8/28-evening（target 8/31 周一） ============
for item in fc:
    if item.get('id') == '2026-08-28-evening' and item.get('status') == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-03 23:10（补复盘）',
            'actual': {
                'date': '2026-08-31',
                'open': 3926.53, 'high': 3986.30, 'low': 3926.50, 'close': 3986.30,
                'pct_chg': 0.86, 'prev_close': 3952.18,
                'note': '8/31 低开 3926.53（精准踩 3927.85 下沿 1.32 点）后单边上行，收 3986.30(+0.86%)，光头光脚大阳线（收盘=最高）。最低 3926.50 刺破支撑 3927.85 仅 1.35 点即拉起；有效突破压力 3967.59 及 8/28 假突破高点 3970.31，收盘站稳其上方 18.71 点。'
            },
            'direction_verdict': '✅ 命中（预判「震荡偏多」，实际 +0.86% 单边大涨收光头大阳线，偏多兑现；且 note 已点出「日线MACD DIF上穿零轴转多 + 引擎C全线偏多」动能转多判断精准）',
            'range_verdict': '⚠️ 部分（预判 3927-3970，实际 3926.50-3986.30：低点 3926.50 精准踩下沿 3927 差 0.5 点，高点 3986.30 突破上沿 3970 超 16.3 点——A 剧本「放量突破→看更高」兑现）',
            'support_verdict': '✅ 守住（支撑 3927.85=周线一买+60F中枢下沿共振，实际低 3926.50 刺破 1.35 点后快速拉起收 3986.30——「极限刺破快收回」经典走势）',
            'resistance_verdict': '⚠️ 突破但剧本已预见（压力 3967.59 被有效突破、收盘 3986.30 站上 18.71 点；但 A 剧本明确写了「放量突破 3967-3970 → 看 4034/4061」，突破属可预料方向，不算误判）',
            'bias_type': [
                'v5打分偏空(-2)与direction文字"震荡偏多"矛盾：结构偏空(日线/周线中枢下方-4)滞后，动能转多(MACD上穿零轴+引擎C全线偏多)领先，实际大涨印证动能因子应优先',
                '压力位被有效突破（A剧本兑现，非误判）'
            ],
            'foreseeable': '关键位完全可预料，方向靠动能因子判对',
            'foresee_reason': 'note 已明确点出「日线MACD DIF上穿零轴(8-26:-4.03→8-27:-0.07→8-28:+2.72)转多 + 引擎C全线偏多(15F82%/60F82%/120F88%/日线64%)」，但 v5 结构打分仍给 -2 偏空（trend 日线/周线结构在 4061 中枢下方 -4）。8/31 实际动能转多兑现、单边大涨 +0.86% 收光头大阳线，证明「动能转多 vs 结构偏空」背离时应以动能因子优先。关键位方面：低点 3926.50 精准踩 3927.85（差 0.5 点）、突破 3970 假突破压力后看更高，均符合剧本。',
            'note': '支撑 3927.85 精准守住（刺破 1.35 点收回）、方向偏多兑现；压力 3967.59 被有效突破（A 剧本兑现）。核心偏差：v5 结构打分偏空滞后于动能转多信号，是「动能 vs 结构背离」的典型样本，仅记录不优化。'
        }
        break

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(fc, f, ensure_ascii=False, indent=2)

from collections import Counter
print('status 分布:', Counter(r.get('status') for r in fc))
print('total:', len(fc))

# ============ 程序化重算偏差统计 ============
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

print('\n=== 偏差统计（%d 期 verified） ===' % len(verified))
for k, zh in [('direction', '方向'), ('range', '区间'), ('support', '支撑'), ('resistance', '压力')]:
    s = stat[k]
    ok, part, fail = s['ok'], s['part'], s['fail']
    tot = ok + part + fail
    rate = f'{ok/tot*100:.1f}%' if tot else '-'
    print(f'{zh}: ✅{ok} ⚠️{part} ❌{fail} 纯命中率 {rate}')

print('\n=== bias_type 分布 ===')
for k, v in bc.most_common():
    print(f'  {k}: {v}')
