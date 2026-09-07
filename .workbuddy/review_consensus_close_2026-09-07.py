# -*- coding: utf-8 -*-
"""收盘共识复盘：9/7-morning consensus pending -> verified，并追加午后新共识。"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'consensus_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    data = json.load(f)

recs = data.get('records', data) if isinstance(data, dict) else data

review = {
    "consensus_judgments": [
        {"topic": "政策利好催化（财政部 3600 亿注资金融央企）", "type": "event", "verdict": "⏳ 不参与", "note": "事件事实类，按机制不参与复盘"},
        {"topic": "AI 产业景气延续", "type": "event", "verdict": "⏳ 不参与", "note": "事件事实类，按机制不参与复盘"},
        {"topic": "冰点修复（周末跌透）", "type": "short", "verdict": "⚠️ 部分兑现", "note": "今日高开 +0.32% 体现修复意愿，但冲高乏力高开低走，收盘 +0.07% 微涨，修复弱（印证大鹏鸟「修复看量，量不够只有前排博弈价值」）"},
        {"topic": "A 股与外盘背离", "type": "short", "verdict": "✅ 兑现", "note": "今日 A 股高开低走收平，仍与外盘背离；创业板 +2.63% vs 上证 -0.24%，科技强旧经济弱分化延续"},
        {"topic": "中期谨慎（科技总量问题 + 解禁压力）", "type": "mid", "verdict": "⏳ 跟踪中", "note": "中期观点，需更长样本验证"}
    ],
    "opposite_judgments": [
        {
            "topic": "今日大盘方向：A 政策催化修复 vs B 技术压制偏空",
            "side_a_verdict": "⚠️ 部分兑现（高开修复但乏力）",
            "side_b_verdict": "✅ 兑现（技术压制，盘中跌破 3930 至 3916.49，接近 T&J 3915 警示位，60F 极弱兑现）",
            "note": "高开 +0.32% 后冲高乏力，午后下探 3916.49 验证技术压制，尾盘拉回收 3932.7。A/B 拉锯，最终偏弱修复"
        }
    ],
    "summary": "9/7-morning 共识复盘：short 类「A 股与外盘背离」✅ 兑现；「冰点修复」⚠️ 部分兑现（高开修复但量能不足）。对立方向 A（政策修复）⚠️ 部分、B（技术压制）✅ 兑现（盘中下探 3916 接近 T&J 3915 警示位）。event 类不参与；mid 类跟踪中。"
}

for r in recs:
    if r.get('id') == '2026-09-07-morning' and r.get('status') == 'pending':
        r['status'] = 'verified'
        r['verified_at'] = '2026-09-07 16:10'
        r['review'] = review
        break

new_rec = {
    "id": "2026-09-07-afternoon",
    "report_type": "收盘（16:00）",
    "created_at": "2026-09-07 16:10",
    "window": "2026-09-07 12:30 ~ 16:00（--window afternoon）",
    "consensus": [
        {
            "topic": "AI 算力/光模块景气持续上修",
            "view": "高盛全球光模块上调 2026-2028 年 1.6T 及以上出货量 29%/61%/50%；黄仁勋 GTC 把 2027 年高确信度需求从五千亿抬到一万亿美元，每瓦算力就是钱；SEMICON Taiwan 从卖芯片到卖 token 工厂；卫斯李高盛 AI 重回焦点",
            "type": "event",
            "sources": ["基业长青+ 13:41/14:17", "AI 产业链 13:33/12:39", "卫斯李 12:59"]
        },
        {
            "topic": "科技风格偏风险偏好，旧经济弱",
            "view": "高盛中国午间快讯：上证 -0.24%/上证50 -0.64% vs 深证 +1.38%/创业板 +2.63%，科技情绪偏风险偏好；比亚迪 H2 月销稳中有升，全年增速 80-90%",
            "type": "short",
            "sources": ["基业长青+ 13:00"]
        },
        {
            "topic": "沪指进入 60F 极弱（T&J 午后定调）",
            "view": "T&J 12:39：沪指早盘进入 60F 极弱，首先肯定要解除 60F 极弱；60F55 支撑还是有效跌破取决于 15F55 线的突破；深创周线极弱，60F55 是压制，突破不了就是老乡别走行情",
            "type": "short",
            "sources": ["T&J 12:39"]
        }
    ],
    "opposite": [
        {
            "topic": "次日（9/8）方向：技术压制偏空 vs 政策/AI 催化修复",
            "side_a": {"direction": "A 技术压制偏空", "view": "T&J 12:39 沪指 60F 极弱；v5 打分 -4 偏空（日线/周线趋势向下 + 60F 三卖@3911 压制）；60F/日线 BOLL 看空 72%/64%", "source": "T&J + 引擎B + 引擎C"},
            "side_b": {"direction": "B 政策/AI 催化修复", "view": "今日假破位收回（3916→3932.7）下方有承接；日线 MACD 多头区；财政部注资 + AI 光模块景气上修；15F/5F 趋势向上", "source": "引擎A + 政策面 + AI 产业链"},
            "judgment_note": "方向互斥；核心变量 = 15F BOLL 带宽 0.63% 极度收口（变盘临界）+ 量能。T&J 60F 极弱 vs 日线 MACD 多头区背离，v5 打分 -4 偏空但 15F 收口触发方向不明，最终定震荡偏空、给双向剧本"
        }
    ],
    "status": "pending"
}
recs.append(new_rec)

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('OK consensus verified + afternoon pending appended')
