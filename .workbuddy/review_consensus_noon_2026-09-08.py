# -*- coding: utf-8 -*-
"""2026-09-08 午间：复盘 9/8-morning 共识链 + 追加 9/8-noon 共识。
幂等：morning 已有 review 则跳过复盘；noon 已存在则跳过追加。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(BASE, 'consensus_chain.json')

with open(CHAIN, encoding='utf-8') as f:
    d = json.load(f)

# ---------- 1) 复盘 9/8-morning ----------
morning = next((x for x in d if x['id'] == '2026-09-08-morning'), None)
if morning and not morning.get('review'):
    morning['review'] = {
        "review_time": "2026-09-08 14:00",
        "phase": "午间档·上午实际走势验证（9/8 上午：平开 3935.55→高 3951.32→现价 3947.16，+0.37%）",
        "per_topic": [
            {"topic": "AI 算力/光模块/CPO 是 9/8 绝对主线", "type": "event",
             "verdict": "⏸ 不参与复盘",
             "note": "事件事实类，午间窗口继续共振（HBM 2027 短缺更严、旭创 225% 目标价、CIOE 前瞻、PTFE/电子纱涨价超预期）"},
            {"topic": "科技强旧经济弱分化延续", "type": "short",
             "verdict": "✅ 兑现",
             "note": "上午科技继续吃肉（大鹏鸟午间「科技先手吃到肉、溢价不错」），上证窄幅震荡偏多 +0.37%，风格分化延续"},
            {"topic": "粮食/厄尔尼诺/糖供给收紧", "type": "short",
             "verdict": "⏳ 跟踪中",
             "note": "午间高盛农产品观察继续催化（霍尔木兹/黑海/超级厄尔尼诺），但盘中未见粮食板块领涨，属持续事件待发酵"},
            {"topic": "9/16 大事件集中爆发", "type": "event",
             "verdict": "⏸ 不参与复盘",
             "note": "事件事实类（预热行情），未到 9/16 兑现日，按机制不参与"}
        ],
        "opposite_judgments": [
            {"topic": "9/8 方向：技术压制偏空 vs 政策/AI 催化修复",
             "verdict": "修复侧占优（方向不明兑现）",
             "note": "上午实际走 B 修复路径——站上日线 55（3938.64）与 15F55（3943.87），但未有效突破 60F 中轨（3945.54），最高 3951.32 后回落，符合「方向不明、B 震荡 50% 最可能」判断；A 偏空（失守 3927）与 C 修复（放量站稳 3945+）均未兑现"},
            {"topic": "科技主线条：AI 算力持续 vs 78 月大阳后调整",
             "verdict": "持续侧占优（但短线高位震荡风险仍在）",
             "note": "光模块/PCB 继续强（旭创 225% 目标价、CIOE 前瞻），但大鹏鸟「市场整体没量、超短性价比一般」+ T&J「磨叽观望」确认短线高位震荡风险，主线方向不变、追高需谨慎"}
        ]
    }
    morning['status'] = 'verified'
    print('[共识复盘] 9/8-morning 已写 review，status -> verified')
else:
    print('[跳过] 9/8-morning 共识已有 review 或不存在')

# ---------- 2) 追加 9/8-noon ----------
if any(x['id'] == '2026-09-08-noon' for x in d):
    print('[跳过] 9/8-noon 共识已存在')
else:
    noon = {
        "id": "2026-09-08-noon",
        "report_type": "午间快报（14:00）",
        "created_at": "2026-09-08 14:00",
        "window": "2026-09-08 08:00 ~ 14:00（noon 窗口，37 条）",
        "consensus": [
            {"topic": "AI 算力/光模块/CPO 主线延续（HBM 短缺更严 + 旭创 225% 目标价）",
             "view": "基业长青：2027 年 HBM 短缺比 2026 更严（单一客户需求超 400 亿 Gb）；DRAM Q3 环比 +15.8%、2027 同比 +23.9%；ASIC 占比 2026/27/28 达 50%/52%/55%；高盛给中际旭创 225% 上行空间（1.6T 顶点 2027）；野村 CIOE 2026 前瞻（200G/400G 芯片、硅光、NPO/CPO）；大摩「AI 瓶颈」杠铃策略（AI 计算+存储+网络）",
             "type": "event",
             "sources": ["基业长青+ 多篇（HBM/DRAM/ASIC/CIOE）", "AI 产业链地图 高盛旭创 225%", "野村 CIOE 前瞻"]},
            {"topic": "市场整体没量、超短性价比一般（游资逻辑不追高）",
             "view": "大鹏鸟午间总结：科技先手吃到肉、溢价不错，但市场整体没量，超短打二板性价比一般；T&J 午间「磨叽走势先观望」；180K「叙事边际转向、ARR 脱敏」",
             "type": "short",
             "sources": ["大鹏鸟 12:33 午间总结", "T&J 12:45", "180K Research"]},
            {"topic": "技术面偏多修复但未确认（T&J 需 60F 金叉）",
             "view": "T&J 12:45：上午站上 15F55 但未明显离开（3F 顶背离+回踩 3F 中轨），继续向上需「60F 金叉下的 3F 主涨段」；有效突破则 60F 进入 3850 以来第三段上涨，回踩 15F 中轨出主涨段突破 4012；15F 已金叉、60F 未金叉（DIF 拐头向上靠拢）",
             "type": "short",
             "sources": ["T&J 12:45 午间定调", "缠论引擎 B + BOLL×缠论"]}
        ],
        "opposite": [
            {"topic": "9/8 下午方向：有效突破（60F 金叉）vs 磨叽回落",
             "side_a": {"direction": "A 有效突破",
                        "view": "15F 已金叉站上 15F55 + 日线 DIF 拐头向上 + 60F 趋势转向上；下午快速上涨触发 60F 金叉 → 突破 3947.56（120F 中轨）→ 3967.59（60F 中枢上沿）→ 4012",
                        "source": "缠论引擎 B + BOLL + 日线 MACD"},
             "side_b": {"direction": "B 磨叽回落",
                        "view": "60F 未金叉（零轴下方死叉）+ 15F 带宽 0.85% 极度收口 + 3F 顶背离 + 市场没量（大鹏鸟）；失守 3943.87（15F55）→ 3936/3931",
                        "source": "T&J「磨叽观望」+ 大鹏鸟「没量」+ BOLL 收口"},
             "judgment_note": "方向不明（中性偏多待确认）：v5 总分 +1 + 15F 带宽 0.85%<1% 触发方向不明；T&J 核心变量 = 60F 金叉（目前未金叉、DIF 拐头向上靠拢中）；剧本 A 30% / B 45% / C 25%；操作纪律 = 60F 金叉前不追多、磨叽观望为主（T&J 游击战）"}
        ],
        "status": "pending"
    }
    d.append(noon)
    print('[追加] 9/8-noon 共识已写入，status=pending')

with open(CHAIN, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print('\n=== 共识链状态 ===')
print('总条数:', len(d))
verified = sum(1 for x in d if x.get('status') == 'verified')
pending = sum(1 for x in d if x.get('status') == 'pending')
print(f'verified: {verified} | pending: {pending}')
for x in d[-2:]:
    print(' -', x['id'], '| status=', x.get('status'))
