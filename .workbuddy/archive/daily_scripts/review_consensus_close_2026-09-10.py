# -*- coding: utf-8 -*-
"""2026-09-10 收盘复盘：复盘 consensus_chain 9/10-morning（9/10 全天）。
幂等：已有 review 则跳过。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(BASE, 'consensus_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    d = json.load(f)

r = next((x for x in d if x.get('id') == '2026-09-10-morning'), None)
if r and not r.get('review'):
    r['review'] = {
        "review_time": "2026-09-10 16:56",
        "phase": "收盘档·9/10 全天走势验证（9/10 收盘：open 3939.09→high 3949.25→low 3927.35→close 3934.40，-0.43%，量能 5 亿手持平）",
        "per_topic": [
            {
                "topic": "科技主线分歧加剧：逻辑在但缺量（T&J 质疑筹码 vs 美股继续涨）",
                "type": "short",
                "verdict": "✅ 兑现",
                "note": "9/10 科技继续回调：通信 -1.01%、计算机 -0.86%、电子 -0.57%、传媒 -1.25%，量能 5 亿手与前两日持平未放量——T&J「需放量闭眼冲锋」+ 大鹏鸟「无量磨、只做前排活口」兑现，科技因缺量继续阴跌，未现放量突破"
            },
            {
                "topic": "周期/高股息/厄尔尼诺延续（煤炭有色交运领涨）",
                "type": "short",
                "verdict": "❌ 大部分证伪（仅高股息延续）",
                "note": "昨天领涨的周期今天全部回落：煤炭 +3.03%→-1.30%、有色 +1.49%→-1.26%、石油石化 -1.51%；厄尔尼诺方向领跌证伪（农林牧渔 -3.10% 全场领跌、基础化工 -1.80% 领跌），同花顺缠论方向「农林牧渔+2.0/煤炭+2.0/基础化工+3.0 趋势向上」全部反向打脸。仅「高股息」延续（银行 +1.52% 领涨、公用事业 +0.44%、建材 +0.64%）。教训：星球主题的方向性延续不可盲信，周期/主题切换极快（一日游）"
            },
            {
                "topic": "量能是核心变量（两万亿分水岭）",
                "type": "short",
                "verdict": "✅ 兑现",
                "note": "9/10 量能 5 亿手与前两日持平，未放量到两万亿——「盘面没量说啥都没用」兑现，无量环境指数窄幅阴跌、无大容量标领头，资金抱团防御（银行 +1.52% 领涨）"
            },
            {
                "topic": "技术面转多但未确认（日线死叉解除 + 60F 金叉 + 15F 极度收口）",
                "type": "short",
                "verdict": "✅ 兑现（「未确认」是核心）",
                "note": "9/10 确实「未确认」——没放量突破 3958.91（最高 3949.25 距压力仍差 -0.24%），15F 收口后未选向上反而窄幅回落收跌 -0.43%。技术面转多的信号（日线死叉解除/60F 金叉）没能转化为突破，缺量确认是关键"
            }
        ],
        "opposite_review": {
            "topic": "9/10 方向：向上突破（放量）vs 窄幅震荡（无量）vs 向下回落",
            "verdict": "B 窄幅震荡侧占优",
            "note": "实际全天 3927-3949 窄幅 22 点、收盘 3934.40（-0.43%），Scenario B「窄幅震荡 40%」兑现；A 向上突破未现（最高 3949.25 未触及 3958.91）、C 向下回落仅部分兑现（收盘微破 60F55 3935.44 但守住日线55 3932.74、未到前低 3915.22）。方向不明兑现，核心变量「量能」判断到位——无量则磨，T&J「窄幅震荡没特征」+ 大鹏鸟「无量磨」精准"
        }
    }
    r['status'] = 'verified'
    print('[复盘] 9/10-morning 共识已写 review，status -> verified')
else:
    print('[跳过] 9/10-morning 已有 review 或不存在')

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('\n=== 当前共识链状态 ===')
print('总条数:', len(d))
for x in d[-3:]:
    print(' -', x.get('id'), '| status=', x.get('status'))
