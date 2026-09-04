# -*- coding: utf-8 -*-
"""9/3 收盘复盘：把 2026-09-03-morning / -intraday / -noon 三条 pending 转 verified 并写 review。

复盘数据源：
- 全天 OHLC（腾讯 fqkline，get_daily_ohlc.py）：open 3952.79 / high 3968.11 / low 3930.45 / close 3942.09 / pct +0.02% / prev 3941.39
- 分时（腾讯 minute 接口）：
  早盘 09:30~11:30：高 3967.91 / 低 3951.10 / 收 3958.19
  午后 13:00~15:00：高 3958.19（13:00 开盘即高）/ 低 3930.51（13:28）/ 收 3942.09（午后 -0.41%）
  全天最低 3930.45 出现在午后 13:28，刺破 60F55 分水岭(3931.52)约 1 点后快速收回，收盘 3942.09 回到分水岭上方。

核心结论：三条预判的 B 剧本（反抽遇阻回落 → 回踩 60F55 分水岭 → 极限刺破后快收回）全线命中，
T&J 昨夜 23:52「反抽站稳 15F55 才见底 + 60F55 得失是分水岭 + 极限刺破后快收回」精准兑现。
"""
import json, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    fc = json.load(f)

# 全天实际（日线 OHLC）
ACT_DAY = {
    'date': '2026-09-03', 'open': 3952.79, 'high': 3968.11, 'low': 3930.45,
    'close': 3942.09, 'pct_chg': 0.02, 'prev_close': 3941.39,
}

# ============ 1. 复盘 9/3-morning（target 全天） ============
for item in fc:
    if item['id'] == '2026-09-03-morning' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-03 22:40（收盘后复盘）',
            'actual': dict(ACT_DAY, note=(
                '全天高开 3952.79 冲高 3968.11（早盘 09:50 破 60F 中枢上沿 3967.59 未站稳即回落），'
                '午后 13:28 下探 3930.45 刺破 60F55 分水岭(3931.52)约 1 点后快速收回，尾盘收 3942.09(+0.02%) 平盘。'
                '全天振幅 38 点宽幅震荡，收盘回到 60F55 上方、15F55 下方。'
            )),
            'direction_verdict': '⚠️ 部分（预判震荡偏空 v5 -3，实际 +0.02% 平收：偏空盘中兑现——13:28 下探 3930.45 一度 -0.28%，但尾盘拉回平盘，收盘方向未兑现；"震荡"兑现、全天 38 点宽幅）',
            'range_verdict': '⚠️ 部分（预判 3931-3962 核心 31 点，实际 3930.45-3968.11：下沿 3931 微破 0.55 点、上沿 3962 被破 6.11 点；扩展带 3927-3994 完整兜住实际区间）',
            'support_verdict': '✅ 守住（支撑 3931.52=60F55 分水岭，实际低 3930.45 刺破 1.07 点后快速收回、收盘 3942.09 在上方——T&J「极限刺破后快收回」剧本精准兑现，未有效跌破）',
            'resistance_verdict': '⚠️ 部分（压力 3961.62=15F55，实际高 3968.11 盘中突破 6.49 点，但收盘 3942.09 回到下方——盘中突破、收盘得而复失，T&J「反抽须站稳 15F55 才见底」判据未满足）',
            'bias_type': ['压力位短暂突破', '区间上沿破位', '方向部分（盘中兑现·尾盘收回）'],
            'foreseeable': '大部分可预料',
            'foresee_reason': 'T&J 昨夜 23:52 三层判断全部兑现：①「反抽无法站稳 15F55(3962) 就很难见底」——早盘冲高 3968.11 破 3962 但收盘 3942.09 未站稳，见底证伪；②「60F55(3931) 得失是分水岭」——午后 13:28 精准刺破 3930.45 后快速收回；③「极限刺破后快收回，否则升级日线调整」——刺破 1 点即收回，日线调整未确认。唯一偏差：早盘冲高力度（破 3962 至 3968）略超晨报三态预期，导致核心带上沿被突破，但收盘回落验证了「冲高即回落」的偏空底色。',
            'note': 'B 剧本（反抽不破回落 40%）主体兑现，叠加早盘假突破（先破 15F55 再回落）。四维 1✅2⚠️1❌无，方向与区间因「早盘冲高超预期+尾盘平收」小幅失分，但 T&J 分水岭判断满分。'
        }
        break

# ============ 2. 复盘 9/3-intraday（target 盘中~收盘） ============
for item in fc:
    if item['id'] == '2026-09-03-intraday' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-03 22:40（收盘后复盘）',
            'actual': dict(ACT_DAY, note=(
                'intraday 针对「09:48 现价 3962.48 之后~收盘」：随后冲高 3968.11 触及 60F 中枢上沿 3967.59 未站稳，'
                '午后 13:28 下探 3930.45 刺破 60F55(3931.52) 后收回，收盘 3942.09。'
                '从 09:48 快照 3962.48 到收盘 3942.09，实际跌 -0.51%。'
            )),
            'direction_verdict': '✅ 命中（预判震荡偏空，实际 09:48 的 3962.48 → 收盘 3942.09 跌 -0.51%，午后一度下探 3930.45 -0.28%，偏空兑现）',
            'range_verdict': '⚠️ 部分（预判 3960-3968 核心 8 点，实际 3930.45-3968.11：上沿 3968 守住、下沿 3960 被破 29.5 点；扩展带 3931-3994 下沿 3931 微破 0.55 点基本兜住——B 剧本本就是「跌破 3960/3950 再测 3931」）',
            'support_verdict': '⚠️ 部分（第一支撑 3960.18=60F 中轨被跌破；但更深核心支撑 3931.52=60F55 分水岭刺破 1.07 点后收回，收盘 3942.09 在上方——「回踩分水岭」精准兑现）',
            'resistance_verdict': '✅ 守住（压力 3967.59=60F 中枢上沿，实际高 3968.11 触及 0.52 点未站稳即回落，反抽遇阻——正是 intraday B 剧本）',
            'bias_type': ['支撑跌破（3960 第一支撑）', '区间下沿破位'],
            'foreseeable': '完全可预料',
            'foresee_reason': 'intraday 三态 B「反抽遇阻 3967.59 回落 40% → 回踩 3960/3950 → 跌破再测 3931 分水岭」完整兑现：冲高 3968.11 触及 3967.59 即回落 → 跌破 3960/3950 → 午后 13:28 精准刺破 60F55(3931.52) 至 3930.45 后收回。T&J「反抽站不稳 15F55 难见底 + 60F55 分水岭」盘中二次验证。',
            'note': 'B 剧本（40% 概率）完整命中。方向与压力满分，区间/第一支撑因「回踩分水岭」场景而超核心带，属剧本内可预料偏移。'
        }
        break

# ============ 3. 复盘 9/3-noon（target 午后~收盘） ============
for item in fc:
    if item['id'] == '2026-09-03-noon' and item['status'] == 'pending':
        item['status'] = 'verified'
        item['review'] = {
            'reviewed_at': '2026-09-03 22:40（收盘后复盘）',
            'actual': dict(ACT_DAY, note=(
                'noon 针对「午后~收盘」：午后 13:00 开盘 3958.19（即午后最高）一路下探，'
                '13:28 探底 3930.51 刺破 60F55(3932.74) 后反弹，14:30 回升至 3951.12，尾盘回落收 3942.09。'
                '午后区间 3930.51-3958.19，午后跌 -0.41%。'
            )),
            'direction_verdict': '✅ 命中（预判震荡偏空，午后 3958.19 → 3942.09 跌 -0.41%，盘中最低 3930.51 -0.70%，偏空兑现）',
            'range_verdict': '⚠️ 部分（预判 3950-3968 核心 18 点，午后实际 3930.51-3958.19：上沿 3968 未触及、下沿 3950 被破 19.5 点；扩展带 3932-3994 下沿 3932 微破 1.5 点——B 剧本本就是「跌破 3950 回踩 3932 分水岭」）',
            'support_verdict': '⚠️ 部分（第一支撑 3950.25=15F 中轨被跌破；但更深核心支撑 3932.74=60F55 分水岭刺破 2.2 点后收回，收盘 3942.09 在上方——「回踩分水岭」精准兑现，未有效跌破）',
            'resistance_verdict': '✅ 守住（压力 3967.59=60F 中枢上沿，午后最高 3958.19 未触及、差 9.4 点，反抽无力）',
            'bias_type': ['支撑跌破（3950 15F中轨）', '区间下沿破位'],
            'foreseeable': '完全可预料',
            'foresee_reason': 'noon 三态 B「跌破 3950.25 回落 40% → 回踩 3932/3931 分水岭 → 跌破则日线调整看 3928/3904」完整兑现：午后开盘即跌破 3950.25 → 13:28 探底 3930.51 刺破 60F55(3932.74) → 未到 3928 即快速收回 → 收盘 3942.09 回到分水岭上方。T&J「60F55 得失是分水岭、极限刺破后快收回」第三次精准验证，日线调整未确认。',
            'note': 'B 剧本（40% 概率）完整命中。方向与压力满分，区间/第一支撑因「回踩分水岭」超核心带，属剧本内可预料偏移。'
        }
        break

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(fc, f, ensure_ascii=False, indent=2)

print('status 分布:', Counter(r.get('status') for r in fc))
print('total:', len(fc))

# ============ 4. 程序化重算偏差统计 ============
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

print('\n=== bias_type 分布（TOP 12） ===')
for k, v in bc.most_common(12):
    print(f'  {k}: {v}')
