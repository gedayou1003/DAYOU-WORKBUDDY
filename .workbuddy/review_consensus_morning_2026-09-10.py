# -*- coding: utf-8 -*-
"""2026-09-10 晨报：复盘 consensus 9/9-morning（逐条验证 9/9 全天）+ 追加 9/10-morning 新共识。
幂等：已有 review 则跳过复盘；9/10-morning 已存在则跳过追加。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(BASE, 'consensus_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    d = json.load(f)

# ---------- 1) 复盘 9/9-morning ----------
c9 = next((x for x in d if x['id'] == '2026-09-09-morning'), None)
if c9 and not c9.get('review'):
    c9['review'] = {
        "review_time": "2026-09-10 09:00",
        "phase": "晨报档·9/9 全天走势验证（9/9 收盘：open 3943.92→high 3958.12→low 3933.47→close 3951.51，+0.28%）",
        "per_topic": [
            {
                "topic": "AI 算力/光模块主线延续但短线回调（美股科技大涨 + 高盛上修光通信）",
                "type": "event",
                "verdict": "⏸ 不参与复盘",
                "note": "事件事实类。9/9 美股科技继续涨（海力士创新高），但 A 股科技继续回调（传媒 -2.77% 领跌、半导体同花顺方向 -2.0），「短线回调」延续；高盛光通信上修逻辑未变，缺的是放量确认"
            },
            {
                "topic": "油气/中东冲突催化（美军打击伊朗哈尔克岛油价飙升）",
                "type": "short",
                "verdict": "✅ 兑现",
                "note": "9/9 收盘周期继续领涨：煤炭 +3.03%、有色 +1.49%、交运 +1.35%、军工 +1.30%，石油石化同花顺方向 +1.0——油气/中东催化扩散为周期普涨，主角从石油石化外溢到煤炭有色"
            },
            {
                "topic": "风格切换：科技回调、周期/高股息接棒",
                "type": "short",
                "verdict": "✅ 兑现",
                "note": "9/9 收盘传媒 -2.77% 领跌、房地产 -1.72%、美容护理 -1.40%，煤炭 +3.03%、有色 +1.49%、交运 +1.35% 领涨——科技继续回调、周期/高股息接棒，风格切换进一步强化"
            },
            {
                "topic": "技术面：15F 二买评估 + 日线死叉风险（T&J 定调）",
                "type": "short",
                "verdict": "❌ 未兑现",
                "note": "9/9 实际日线 DIF 拐头向上（6.70→7.26）化解死叉（死叉未发生）、60F 金叉成立（0.88>-0.22）、收盘站上 120F 中轨 3947.39——「日线死叉主跌段」剧本未兑现，反而向上化解，Scenario A 温和兑现"
            }
        ],
        "opposite_review": {
            "topic": "9/9 方向：向上加速（避开日线死叉）vs 向下加速（日线死叉主跌段）",
            "verdict": "A 向上加速侧占优（温和）",
            "note": "9/9 收盘 3951.51（+0.28%）站上 120F 中轨 3947.39，日线 DIF 拐头向上化解死叉、60F 金叉成立——「向上加速」侧兑现，但幅度温和（+0.28%，非强攻），属「方向对、幅度温和」的兑现"
        }
    }
    c9['status'] = 'verified'
    print('[复盘] 9/9-morning 共识已写 review，status -> verified')
else:
    print('[跳过] 9/9-morning 已有 review 或不存在')

# ---------- 2) 追加 9/10-morning ----------
if any(x['id'] == '2026-09-10-morning' for x in d):
    print('[跳过] 9/10-morning 已存在')
else:
    c10 = {
        "id": "2026-09-10-morning",
        "report_type": "晨报（手动 09:00）",
        "created_at": "2026-09-10 09:00",
        "window": "2026-09-09 16:00 ~ 09:00（morning 窗口，62 条）",
        "consensus": [
            {
                "topic": "科技主线分歧加剧：逻辑在但缺量（T&J 质疑筹码 vs 美股继续涨）",
                "view": "T&J 18:56：科技需要一个理由让大家闭眼冲锋，闭眼冲锋的表现就是放量；一级股东有退出诉求就有 EPS、没诉求 EPS 可瞬间消失；DS 出 IPO 辅导新闻（文峰量化割 vs 解禁退出）。大鹏鸟 22:47/07:53：美股科技继续涨（海力士创新高），但 A 股无量磨、科技只做前排活口（不放大量不做盘子偏大）；光纤/电子布涨价/金刚石散热有催化但需放量确认",
                "type": "short",
                "sources": [
                    "T&J 18:56 科技筹码质疑",
                    "大鹏鸟 22:47 + 07:53 盘前热榜",
                    "AI 产业链地图"
                ]
            },
            {
                "topic": "周期/高股息/厄尔尼诺延续（煤炭有色交运领涨）",
                "view": "9/9 收盘煤炭 +3.03%、有色 +1.49%、交运 +1.35%、军工 +1.30% 领涨；大鹏鸟「投机人气妖还是厄尔尼诺大周期为主（粮食/糖/海运/化工）」；同花顺缠论方向：农林牧渔 +2.0、煤炭 +2.0、基础化工 +3.0 趋势向上",
                "type": "short",
                "sources": [
                    "申万实时榜（9/10 09:04）",
                    "大鹏鸟 07:53 盘前",
                    "同花顺缠论方向"
                ]
            },
            {
                "topic": "量能是核心变量（两万亿分水岭）",
                "view": "大鹏鸟：两万亿以下只能做 100-500 亿流通市值容量标，若出现近千亿容量标领头必须放量到 2 万亿以上；盘面没量说啥都没用",
                "type": "short",
                "sources": [
                    "大鹏鸟 07:53 盘前热榜"
                ]
            },
            {
                "topic": "技术面转多但未确认（日线死叉解除 + 60F 金叉 + 15F 极度收口）",
                "view": "日线 DIF 拐头向上（6.70→7.26）化解死叉、60F 金叉成立（0.88>-0.22）、收盘站上 120F 中轨 3950.99；但 15F 带宽 0.61% 极度收口 + T&J「窄幅震荡没看出特征」= 变盘在即方向不明，缺量能确认",
                "type": "short",
                "sources": [
                    "T&J 22:51",
                    "缠论引擎 B + BOLL×缠论",
                    "日线/60F/15F MACD"
                ]
            }
        ],
        "opposite": [
            {
                "topic": "9/10 方向：向上突破（放量）vs 窄幅震荡（无量）vs 向下回落",
                "side_a": {
                    "direction": "A 向上突破",
                    "view": "日线死叉解除 + 60F 金叉成立 + 收盘站上 120F 中轨 + BOLL 15F/120F/日线全偏多（82%/72%/64%）；放量突破 3958.91（9/9高点/15F上轨）→ 3966.84 → 3967.59",
                    "source": "缠论引擎 + BOLL 变盘概率 + MACD 拐头向上"
                },
                "side_b": {
                    "direction": "B 窄幅震荡",
                    "view": "T&J「窄幅震荡没特征」+ 大鹏鸟「无量磨」+ 15F 带宽 0.61% 极度收口；3935-3959 无量磨，等变盘",
                    "source": "T&J + 大鹏鸟 + BOLL 收口"
                },
                "side_c": {
                    "direction": "C 向下回落",
                    "view": "科技无量回调扩散（传媒 -2.77% 领跌）+ 宽基中证1000/沪深300 同花顺方向向下；失守 3935.44（60F55）→ 3932.74（日线55）→ 3927.85（周线一买）",
                    "source": "同花顺宽基方向向下 + 科技回调 + 大鹏鸟防守"
                },
                "judgment_note": "方向不明：v5 总分 +1（买卖点 0 + T&J 中性 0 + BOLL 变盘 0 + MACD DIF 拐头向上 +1）+ 15F 带宽 0.61%<1% 触发方向不明；核心变量 = 量能（大鹏鸟两万亿分水岭）；剧本 A 35% / B 40% / C 25%；操作纪律 = 放量站稳 3958.91 才看更高、失守 3935.44 转防守、无量磨不重仓"
            }
        ],
        "status": "pending"
    }
    d.append(c10)
    print('[追加] 9/10-morning 共识已写入，status=pending')

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('\n=== 共识链状态 ===')
print('总条数:', len(d))
verified = sum(1 for x in d if x.get('status') == 'verified')
pending = sum(1 for x in d if x.get('status') == 'pending')
print(f'verified: {verified} | pending: {pending}')
for x in d[-2:]:
    print(' -', x['id'], '| status=', x.get('status'))
