# -*- coding: utf-8 -*-
"""2026-09-09 晨报：复盘 9/8-noon 共识 + 追加 9/9-morning 新共识。
幂等：noon 已有 review 则跳过复盘；morning 已存在则跳过追加。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(BASE, 'consensus_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    d = json.load(f)

# ---------- 1) 复盘 9/8-noon ----------
noon = next((x for x in d if x['id'] == '2026-09-08-noon'), None)
if noon and not noon.get('review'):
    noon['review'] = {
        "review_time": "2026-09-09 08:58",
        "phase": "晨报档·9/8 全天走势验证（9/8 收盘：open 3935.55→high 3951.32→low 3925.72→close 3940.55，+0.20%）",
        "per_topic": [
            {"topic": "AI 算力/光模块/CPO 主线延续（HBM 短缺更严 + 旭创 225% 目标价）", "type": "event", "verdict": "⏸ 不参与复盘", "note": "事件事实类，9/8 收盘科技主线回调（电子 -1.11%、科创50 -1.52%）但 9/9 晨报高盛又上修光通信（677→1314→1485亿）、剑桥科技激光器告急，景气逻辑未变，仅短线回调"},
            {"topic": "市场整体没量、超短性价比一般（游资逻辑不追高）", "type": "short", "verdict": "✅ 兑现", "note": "9/8 收盘 A 股总成交额 1.98 万亿、科技冲高回落（电子领跌）、周期接棒（石油石化 +3.68%），印证「没量+科技先手吃溢价后回落、游资不追高」判断"},
            {"topic": "技术面偏多修复但未确认（T&J 需 60F 金叉）", "type": "short", "verdict": "✅ 兑现", "note": "9/8 收盘 3940.55，60F 始终未金叉（DIF -1.67<DEA -0.77），午后跳水刺破 60F55（low 3925.72）后尾盘收回 15F55 附近——「偏多修复未确认」完全兑现，未突破 120F 中轨"}
        ],
        "opposite_review": {
            "topic": "9/8 下午方向：有效突破（60F 金叉）vs 磨叽回落",
            "verdict": "B 磨叽回落侧占优",
            "note": "9/8 收盘 3940.55（+0.20%），60F 未金叉、午后跳水刺破 60F55、收盘未站上 120F 中轨 3947.56——「磨叽回落」侧兑现，剧本 B 震荡/回落 70%（45%+25%）大致兑现"
        }
    }
    noon['status'] = 'verified'
    print('[复盘] 9/8-noon 共识已写 review，status -> verified')
else:
    print('[跳过] 9/8-noon 已有 review 或不存在')

# ---------- 2) 追加 9/9-morning ----------
if any(x['id'] == '2026-09-09-morning' for x in d):
    print('[跳过] 9/9-morning 已存在')
else:
    morning = {
        "id": "2026-09-09-morning",
        "report_type": "晨报（手动 09:00）",
        "created_at": "2026-09-09 08:58",
        "window": "2026-09-08 16:00 ~ 09:00（morning 窗口，55 条）",
        "consensus": [
            {
                "topic": "AI 算力/光模块主线延续但短线回调（美股科技大涨 + 高盛上修光通信）",
                "view": "高盛上调光通信预测 2026-2028 年 677亿→1314亿→1485亿美元（+33%/+81%/+115% 上修）；剑桥科技 CIG 70mW-200mW 激光器严重短缺；长光华芯 EML/CW 激光器产能爬坡；阿贝尔押注 AI 瓶颈；但 9/8 A 股科技已回调（电子 -1.11%、科创50 -1.52%），大鹏鸟「昨天科技小调、今天可能回暖但没量、谨慎追高」",
                "type": "event",
                "sources": [
                    "基业长青+ 高盛光通信上修 + 长光华芯调研",
                    "AI 产业链地图 白毛日报 + Serenity",
                    "大鹏鸟 07:39 盘前热榜"
                ]
            },
            {
                "topic": "油气/中东冲突催化（美军打击伊朗哈尔克岛油价飙升）",
                "view": "美军对伊朗哈尔克岛（主要石油出口枢纽）+ 贾斯克港口实施打击后油价大幅飙升；石油石化 +3.68% 领涨申万；大鹏鸟「中东大概率难太平、朗子炸饭碗」",
                "type": "short",
                "sources": [
                    "基业长青+ GS China Open",
                    "大鹏鸟 07:39 盘前热榜",
                    "申万实时榜（石油石化 +3.68%）"
                ]
            },
            {
                "topic": "风格切换：科技回调、周期/高股息接棒",
                "view": "9/8 收盘分化：上证 +0.20% vs 科创50 -1.52%、创业板 -1.15%、电子 -1.11%；高股息板块跑赢、化工再度上行、石油石化 +3.68% 领涨；高盛「A股行情分化、高股息跑赢、电池走弱（理想自研电池）」",
                "type": "short",
                "sources": [
                    "基业长青+ 高盛中国日报",
                    "申万实时榜（9/8 收盘）"
                ]
            },
            {
                "topic": "技术面：15F 二买评估 + 日线死叉风险（T&J 定调）",
                "view": "T&J 22:07：午后跳水刺破 60F55 后尾盘回 15F55 附近，评估 15F 二买；反抽低点无 3F 底背离，直接高举高打可能性不大，若低点给补偿性二买；不快速拉升则日线死叉下主跌段风险，二买很极限；窄幅震荡不会维持太久，上下都有明显加速信号",
                "type": "short",
                "sources": [
                    "T&J 22:07 晨报定调",
                    "缠论引擎 B + BOLL×缠论（15F 带宽 0.51% 极度收口）"
                ]
            }
        ],
        "opposite": [
            {
                "topic": "9/9 方向：向上加速（避开日线死叉）vs 向下加速（日线死叉主跌段）",
                "side_a": {
                    "direction": "A 向上加速",
                    "view": "美股科技大涨带动回暖 + 高盛光通信上修 + 周线一买 3927.85 支撑；快速拉升避开日线死叉，放量突破 3947.39（120F 中轨）→ 3950.40 → 3966.02",
                    "source": "美股科技 + 高盛光通信 + 缠论周线一买"
                },
                "side_b": {
                    "direction": "B 向下加速",
                    "view": "日线 DIF 拐头向下（7.05→6.75 死叉风险）+ 15F 带宽 0.51% 极度收口 + 市场没量 + 科技回调；日线死叉下主跌段，失守 3935.63（日线55）→ 3931.87（60F55）→ 3925.72 → 3915",
                    "source": "T&J「不快速拉升则日线死叉主跌段」+ 日线 MACD 拐头向下 + 大鹏鸟没量"
                },
                "judgment_note": "方向不明：v5 总分 -1（买卖点 0 + T&J 中性谨慎 0 + BOLL 0 + MACD DIF 拐头向下 -1）+ 15F 带宽 0.51%<1% 触发方向不明；T&J 核心变量 = 能否快速拉升避开日线死叉（二买很极限）；剧本 A 30% / B 35% / C 35%；操作纪律 = 放量站稳 3947.39 才看更高、失守 3935.63 转防守"
            }
        ],
        "status": "pending"
    }
    d.append(morning)
    print('[追加] 9/9-morning 共识已写入，status=pending')

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('\n=== 共识链状态 ===')
print('总条数:', len(d))
verified = sum(1 for x in d if x.get('status') == 'verified')
pending = sum(1 for x in d if x.get('status') == 'pending')
print(f'verified: {verified} | pending: {pending}')
