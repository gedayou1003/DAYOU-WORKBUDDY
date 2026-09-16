# -*- coding: utf-8 -*-
"""2026-09-10 收盘复盘：复盘 9/10-morning（9/10 全天收盘数据）。
幂等：morning 已有 review 则跳过。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(BASE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    d = json.load(f)

morning = next((x for x in d if x['id'] == '2026-09-10-morning'), None)
if morning and not morning.get('review'):
    morning['review'] = {
        "reviewed_at": "2026-09-10 16:55（收盘复盘，验证 9/10 全天）",
        "actual": {
            "date": "2026-09-10",
            "open": 3939.09,
            "high": 3949.25,
            "low": 3927.35,
            "close": 3934.40,
            "pct_chg": -0.43,
            "prev_close": 3951.51,
            "note": "全天：低开 3939.09（-0.31%）后一度冲高 3949.25（距翻红 3951.51 仅差 2 点未翻红），随后震荡回落探低 3927.35（一度跌破周线一买 3927.85），尾盘收 3934.40（-0.43%）。全天窄幅阴跌 22 点（3927-3949），量能 5 亿手与前两日（9/8、9/9 均 5 亿手）持平、未放量。风格：银行 +1.52% 领涨（高股息防御接棒），农林牧渔 -3.10% 领跌（厄尔尼诺粮食/糖方向证伪），科技继续回调（通信 -1.01%、计算机 -0.86%、电子 -0.57%、传媒 -1.25%）。"
        },
        "direction_verdict": "✅ 命中（预判「方向不明」，实际全天 -0.43% 窄幅阴跌、无单边，|pct|<0.5% 落「方向不明」区间——未现放量突破也未现主跌，Scenario B「窄幅震荡」兑现）",
        "range_verdict": "⚠️ 部分（预判核心 3935-3959 / 扩展 3928-3968，实际 3927.35-3949.25：收盘 3934.40 微破核心下沿 3935 仅 0.6 点，低点 3927.35 微破扩展下沿 3928 仅 0.65 点后收回；高点 3949.25 未触及核心上沿 3959——全天在核心带下沿附近窄幅震荡，微向下偏移）",
        "support_verdict": "⚠️ 假破位（预判支撑 3935.44=60F55，实际盘中 low 3927.35 深破至周线一买 3927.85 下方后收回，收盘 3934.40 微破 primary 仅 -0.026%（0.94 点）但收回日线55 3932.74 上方——支撑带守住，未有效跌破前低 3915.22）",
        "resistance_verdict": "✅ 守住（预判压力 3958.91=15F上轨/9/9高点，实际全天高点 3949.25 未触及，距离 -0.24%——压力位有效压制，无量上攻乏力）",
        "bias_type": [
            "区间微向下偏移（收盘微破核心下沿 0.6 点）",
            "支撑假破位（盘中深破 60F55 至周线一买后收回）",
            "量能确认缺失（5 亿手与前两日持平，未放量）"
        ],
        "foreseeable": "部分可预料",
        "foresee_reason": "T&J 22:51「技术上过于窄幅震荡没特征」+ 大鹏鸟「无量磨、盘面没量说啥都没用、大方向偏防守」已预警无量震荡，9/10 实际就是无量窄幅阴跌（5 亿手持平、全天 22 点窄幅），Scenario B（窄幅震荡 40%）兑现。「技术面转多但缺量」最终未突破 3958.91 反而回落——量能是突破的硬门槛，无量就磨，这一点预判到位。",
        "note": "方向+压力二维守住（方向不明兑现、压力位有效），支撑/区间因微向下偏移判「假破位/部分」。核心教训：①「技术面转多 + 缺量」= 不能突破只能窄幅回落，量能是确认突破的硬门槛；②大鹏鸟「厄尔尼诺大周期（粮食/糖/化工）」今天被证伪（农林牧渔 -3.10% 领跌、基础化工 -1.80% 领跌），星球主题的方向性延续不可盲信、切换极快；③无量环境资金抱团高股息防御（银行 +1.52% 领涨），印证「无量→防守」的仓位逻辑。"
    }
    morning['status'] = 'verified'
    print('[复盘] 9/10-morning 已写 review，status -> verified')
else:
    print('[跳过] 9/10-morning 已有 review 或不存在')

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('\n=== 当前链状态 ===')
print('总条数:', len(d))
verified = sum(1 for x in d if x.get('status') == 'verified')
pending = sum(1 for x in d if x.get('status') == 'pending')
print(f'verified: {verified} | pending: {pending}')
for x in d[-3:]:
    print(' -', x['id'], '| status=', x.get('status'))
