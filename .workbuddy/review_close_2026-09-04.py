# -*- coding: utf-8 -*-
"""9/4 收盘复盘：把 2026-09-03-evening / 2026-09-04-morning 两条 pending 转 verified 并写 review。

复盘数据源：
- 全天 OHLC（腾讯 fqkline 日线）：open 3955.55 / high 3980.20 / low 3915.22 / close 3930.12 / pct -0.30% / prev 3942.09
- 分时（腾讯 minute 接口）：
  早盘 09:30~11:30：09:37 冲高 3979.64（全天最高）→ 回落，早盘收 3955.15
  午后 13:00~15:00：13:21 反弹 3967.73（午后最高）→ 持续下杀，14:46 最低 3915.74 → 尾盘微拉回收 3930.12

核心结论：9/4 是「早盘冲高诱多 → 午后单边破位」的走势。两条预判均预判「震荡偏多」，
但早盘 09:37 冲高 3979.64（突破所有压力位）是假突破诱多，午后 14:46 单边下杀至 3915.74，
收盘 3930.12 跌破 60F55 分水岭(3931.52)——「60F55 连续四日精准」纪录终结，T&J 罕见「买点」判断落空。
"""
import json, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    fc = json.load(f)

# 全天实际（日线 OHLC）
ACT_DAY = {
    'date': '2026-09-04', 'open': 3955.55, 'high': 3980.20, 'low': 3915.22,
    'close': 3930.12, 'pct_chg': -0.30, 'prev_close': 3942.09,
}

# ============ 1. 复盘 2026-09-04-morning（target 全天） ============
for item in fc:
    if item['id'] == '2026-09-04-morning' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-04 22:10（收盘后复盘）',
            'actual': dict(ACT_DAY, note=(
                '低开 3955.55 后早盘 09:37 冲高 3979.64（+0.95%），突破 15F 中轨(3950)/15F55(3962)/60F 中枢上沿(3967.59) 全部压力位，'
                '但这是假突破诱多——早盘尾段即回落收 3955.15；午后 13:21 短暂反抽 3967.73 未创新高，随后单边下杀，'
                '14:46 最低 3915.74（-0.67%）跌破 60F55(3931.52) 与「踩一脚位」3930，尾盘微拉回收 3930.12（-0.30%）。'
                '全天 64.98 点宽幅震荡，冲高回落收跌，T&J「买点」判断落空。'
            )),
            'direction_verdict': '❌ 判反（预判震荡偏多探底回升 v5 -1，实际收 -0.30% 跌、午后单边下杀。早盘冲高 3979.64 一度 +0.95% 看似偏多兑现，但午后全线回落，收盘转跌——「探底回升」的回升只在早盘昙花一现，全天是「冲高回落」而非「探底回升」）',
            'range_verdict': '⚠️ 偏失（预判核心 3930-3950 仅 20 点窄幅，实际 3915.22-3980.20 宽幅 64.98 点，下破 3927 扩展下沿至 3915、上破 3962 扩展上沿至 3980，双向突破）',
            'support_verdict': '❌ 失效（支撑 3930.0=T&J「踩一脚位」，实际最低 3915.22 跌破 14.78 点，收盘 3930.12 勉强收回 3930 上方 0.12 点——盘中有效跌破，尾盘勉强拉回，支撑被击穿）',
            'resistance_verdict': '⚠️ 部分（压力 3950.16=15F 中轨，盘中突破至 3980.20 但收盘 3930.12 得而复失——「突破 3950 确认买点」的判据盘中触发后反手回落，属假突破诱多）',
            'bias_type': ['方向判反', '冲高诱多假突破', '支撑位击穿（3930 踩一脚位）', 'T&J买点落空'],
            'foreseeable': '部分可预料（假突破风险已预警，但方向仍判反）',
            'foresee_reason': '早盘 09:37 冲高 3979.64 突破全部压力位时，「突破 15F 中轨确认买点」的 A 剧本判据一度触发，但剧本 A 前提是「下探 3930 附近不破后再回升」——实际 9/4 低开 3955.55 直接冲高，未先踩 3930，属于「回踩不足即反弹」的诱多形态。T&J 22:28 明确警告「很墨迹下周要当心（60F 极弱 + 日线死叉）」，120F 死叉 + 日线向下的大级别压制在午后兑现，把早盘冲高打回。核心教训：小级别买点信号（15F 三买）遇到大级别压制（120F 死叉 + 日线向下）时，买点不可靠，反弹是逃命波而非反转。',
            'note': 'B 剧本（墨迹横盘 35%）与 C 剧本（快速击穿 30%）的混合兑现——早盘冲高后横盘，午后转快速击穿。方向、支撑双失，压力假突破。是「小级别买点 vs 大级别压制」背离的典型反面样本。'
        }
        break

# ============ 2. 复盘 2026-09-03-evening（target 全天） ============
for item in fc:
    if item['id'] == '2026-09-03-evening' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-04 22:10（收盘后复盘）',
            'actual': dict(ACT_DAY, note=(
                '9/3-evening 针对 9/4 全天：低开 3955.55 早盘 09:37 冲高 3979.64 触 60F 中枢上沿(3967.59) 上方 12 点，'
                '但未站稳即回落；午后 13:21 反抽 3967.73 未创新高，随后单边下杀 14:46 最低 3915.74，'
                '收盘 3930.12 跌破 60F55(3931.52) 约 1.4 点——「只要不大阴线快速击穿 60F55」的条件被打破，分水岭失守。'
            )),
            'direction_verdict': '❌ 判反（预判震荡偏多（条件性：60F55 不快速失守），实际收 -0.30% 跌且 60F55 被有效跌破。条件「不快速失守」未满足——午后 14:46 单边快速击穿 60F55 至 3915.74，偏多前提崩塌，方向转空）',
            'range_verdict': '⚠️ 偏失（预判 3927-3967 核心 40 点 / 3931-3968 紧区间，实际 3915.22-3980.20，下破 3927 至 3915、上破 3968 至 3980，双向突破）',
            'support_verdict': '❌ 失效（支撑 3931.52=60F55 分水岭（连续四日精准：9/1 未触及 + 9/2 差 1.25 + 9/3 刺破 1 点），9/4 首次收盘有效跌破——最低 3915.22 跌破 16.3 点，收盘 3930.12 在分水岭下方 1.4 点。连续四日精准纪录终结）',
            'resistance_verdict': '⚠️ 部分（压力 3967.59=60F 中枢上沿，盘中 09:37 冲高 3979.64 突破 12 点，但收盘 3930.12 跌回——盘中假突破、收盘得而复失）',
            'bias_type': ['方向判反', '60F55分水岭首次有效跌破', '冲高诱多假突破', 'T&J买点落空'],
            'foreseeable': '部分可预料（条件已内置「快速击穿转空」，但未按 C/D 剧本降仓位）',
            'foresee_reason': '9/3-evening 已内置条件性判断「只要不大阴线快速击穿 60F55 则偏多」，并给出 D 剧本「跌破 60F55(3931) 15%：60F 极弱 + 日线死叉 → 下探 3927.85(周线一买)」。9/4 午后确实快速击穿 60F55 并下探至 3915.74（甚至跌破 3927.85 周线一买 12 点），D 剧本兑现但概率只给 15%，被低估。核心教训：120F 死叉 + 日线向下的大级别压制，叠加缩量（9/3 缩量 1.7 万亿），「条件性买点」的向下破位概率应显著上调，D 剧本概率给低了。',
            'note': 'D 剧本（跌破 60F55 15%）兑现但概率被低估。方向、支撑双失，压力假突破。与 9/4-morning 形成同向偏差：两条预判都被早盘 09:37 的冲高诱多，忽视了大级别（120F 死叉 + 日线向下）压制。'
        }
        break

# ============ 3. 程序化重算偏差统计 ============
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

print('\n=== 偏差统计（%d 期，家里口径） ===' % len(verified))
for k, zh in [('direction', '方向'), ('range', '区间'), ('support', '支撑'), ('resistance', '压力')]:
    s = stat[k]
    ok, part, fail = s['ok'], s['part'], s['fail']
    tot = ok + part + fail
    rate = f'{ok/tot*100:.1f}%' if tot else '-'
    print(f'{zh}: ✅{ok} ⚠️{part} ❌{fail} 纯命中率 {rate}')

print('\n=== bias_type 分布（TOP 12） ===')
for k, v in bc.most_common(12):
    print(f'  {k}: {v}')

# 保存
with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(fc, f, ensure_ascii=False, indent=2)
print('\n已写入 forecast_chain.json')
