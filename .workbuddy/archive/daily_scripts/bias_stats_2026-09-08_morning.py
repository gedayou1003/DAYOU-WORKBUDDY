# -*- coding: utf-8 -*-
"""
9/8 晨报档：偏差观察统计表（v5 配对计数，兼容新老字段）
读 forecast_chain.json 所有 verified 记录，按四维（方向/区间/支撑/压力）配对统计
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    recs = json.load(f)

verified = [r for r in recs if r.get('status') == 'verified' and r.get('review')]
print(f'verified 记录数: {len(verified)}')
print()

# 兼容新老字段名
def get_verdict(rev, dim):
    """dim ∈ {direction, range, support, resistance}"""
    new_key = dim + '_verdict'
    v = rev.get(new_key, '')
    if v: return v
    # 兼容老格式：review 直接字段（带 ✅/⚠️/❌ 前缀）
    v = rev.get(dim, '')
    return v

dims = {
    '方向': 'direction',
    '区间': 'range',
    '支撑': 'support',
    '压力': 'resistance'
}
print('| 维度 | 命中 | 部分 | 失效 | 未判定 | 纯命中率 |')
print('|------|------|------|------|--------|---------|')
result = {}
for label, dim in dims.items():
    hit = part = miss = und = 0
    for r in verified:
        rev = r.get('review', {})
        v = get_verdict(rev, dim)
        if not v: continue
        if v.startswith('✅'): hit += 1
        elif v.startswith('⚠️'): part += 1
        elif v.startswith('❌'): miss += 1
        elif v.startswith('⏳') or v.startswith('⏸'): und += 1
        else: und += 1
    total = hit + part + miss
    rate = round(hit / total * 100, 1) if total else 0
    result[label] = {'hit': hit, 'part': part, 'miss': miss, 'und': und, 'total': total, 'rate': rate}
    print(f'| {label} | {hit} | {part} | {miss} | {und} | {rate}% (n={total}) |')

print()
# bias_type 三分类（兼容 list 类型）
bt = {}
for r in verified:
    t = r.get('review', {}).get('bias_type', '?')
    t = t if isinstance(t, str) else '? (list/复杂)'
    bt[t] = bt.get(t, 0) + 1
print('bias_type 三分类:', bt)
