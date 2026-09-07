# -*- coding: utf-8 -*-
"""收盘复盘：把 9/7-morning 预判（pending）逐项判定并写 review，status 改 verified。"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    data = json.load(f)

recs = data.get('records', data) if isinstance(data, dict) else data

target_id = '2026-09-07-morning'
for r in recs:
    if r.get('id') == target_id and r.get('status') == 'pending':
        r['status'] = 'verified'
        r['verified_at'] = '2026-09-07 16:05'
        r['review'] = {
            "direction_verdict": "✅ 命中（震荡偏多兑现：收盘 +0.07% 微涨；高开 +0.32% 低走，日内 open→close -0.25%，gap 双口径背离）",
            "range_verdict": "⚠️ 部分（核心带 3930-3958：盘中跌破下沿至 3916.49，尾盘收回 3932.7 区间内）",
            "support_verdict": "✅ 守住（假破位/下跌衰竭：盘中 low 3916.49 破 3930，收盘 3932.7 收回支撑上方）",
            "resistance_verdict": "✅ 守住（压力 3958 未触及更未突破，high 3948.42 差 10 点）",
            "actual": {
                "date": "2026-09-07",
                "open": 3942.51,
                "high": 3948.42,
                "low": 3916.49,
                "close": 3932.70,
                "prev_close": 3930.12,
                "pct_chg": 0.07,
                "gap_pct": 0.32,
                "gap_type": "高开"
            },
            "bias_type": ["压力位未触及"],
            "summary": "9/7 周一验证：预判「震荡偏多」，实际高开 +0.32%（3942.51）后冲高乏力（high 3948.42 未触 3958 压力），午后下探跌破 3930 支撑至 3916.49（距 60F 三卖 3911 仅 5.5 点，触发剧本 C 路径），尾盘拉回收复 3930 上方、收 3932.7（+0.07% 微涨）。四维：方向✅（震荡兑现、微涨偏多）；压力✅（3958 压制有效未触）；支撑✅（假破位——盘中破 3930 至 3916 但收盘收回，属下跌衰竭而非真破位）；区间⚠️（盘中破核心带下沿 13.5 点、尾盘收回）。核心剧本覆盖到位：剧本 C「失守 3930 下看 3911」盘中真实演绎（3916.49 距 3911 仅 5.5 点），剧本 B「震荡」最终归宿（收盘收回 3930 上方）。高开是全天唯一干扰项——gap +0.32% 让「相对昨收」的支撑 3930 在开盘即变成「相对今开 -0.32%」的下方位置，日内真实方向是高开低走（-0.25%）。",
            "foreseeable": True,
            "foresee_reason": "预判主剧本 B「政策利好但技术压制震荡」占 45%，剧本 C「失守 3930 下看 3911」已明确写出下跌路径。今日高开冲高乏力、盘中下探 3916.49（距 3911 三卖位仅 5.5 点）、尾盘拉回收平，正是 B+C 混合演绎，节奏完全在预判覆盖内。仅「盘中探至 3916.49 的精确幅度 + 尾盘拉回力度」属盘中博弈细节。"
        }
        break

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('✅ forecast 9/7-morning 已复盘 verified')
