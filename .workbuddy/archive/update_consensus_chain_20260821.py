#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新 consensus_chain.json：复盘16:00 close + 新增晚间快报共识"""
import json
from collections import OrderedDict

path = 'consensus_chain.json'
with open(path, encoding='utf-8') as f:
    cc = json.load(f, object_pairs_hook=OrderedDict)

# 1) 复盘 16:00 收盘的共识链
rec = next(r for r in cc['records'] if r['id'] == '2026-08-21-close')
rec['status'] = 'verified'
short_review = OrderedDict()
short_review['国内大盘短期方向'] = OrderedDict([
    ('consensus_view', '大鹏鸟+T&J+技术面共同指向震荡偏空'),
    ('actual', 'SHCOMP +0.04% 收 3905.20，窄幅震荡（高 3912.13 / 低 3883.79）；T+1D 资金面 GS 略偏多 Buy（买 PCB/电子设备）；15F 带宽 0.44% 极度收口=变盘前兆'),
    ('verdict', '⏳ 震荡成立，方向未确认；T&J 15F 中枢+大鹏鸟"控制仓位"提示**未到位**，下周一 08-24 开盘验证谁主导'),
])
short_review['港股MXHK逢低吸纳'] = OrderedDict([
    ('consensus_view', '摩根大通 MXHK 逢低吸纳 + 180K 亚洲小结'),
    ('actual', '180K 亚洲区域小结：港股小幅收高；GS CHINA WRAP 港股小幅收高'),
    ('verdict', '✅ 兑现（港股小幅上涨印证低吸判断）'),
])
short_review['国内机器人板块'] = OrderedDict([
    ('consensus_view', '基业长青+ 基本面偏多（审美投资时代） vs 大鹏鸟 节奏偏空（等龙一确认）'),
    ('actual', '士兰作为容量龙一今日表现待查；GS 资金买 PCB/电子设备（属电子设备未明确机器人）'),
    ('verdict', '⏳ 节奏分歧：大鹏鸟等龙一确认（基业长青+ 基本面已确认审美投资时代）'),
])
rec['review'] = OrderedDict([
    ('reviewed_at', '2026-08-21 20:35（晚间快报复盘）'),
    ('short_type_review', short_review),
    ('observation', '本次 short 类共识（国内大盘 + 港股 MXHK + 机器人）均得到"部分兑现"（震荡成立 / 低吸兑现 / 节奏分歧），**未出现明确"❌未兑现"案例**。该标签（"震荡成立·方向未确认"）出现 1 次，频次 < 3 次，暂不标注"规律已现"。继续观察，不修改策略。'),
])

# 2) 增加晚间快报的共识记录
new = OrderedDict()
new['id'] = '2026-08-21-evening'
new['report_type'] = '晚间快报（19:00）'
new['created_at'] = '2026-08-21 20:35'
new['window'] = '2026-08-21 12:00 ~ 19:00'

consensus = []
c1 = OrderedDict()
c1['topic'] = '阿里AI资本支出回报可测'
c1['view'] = '摩根大通上调阿里目标价 210 美元/205 港元（NPV 36元/100元，IRR 22%）；大摩重申阿里首选 180 美元（十项关键指标全部满足）'
c1['type'] = 'event'
c1['sources'] = ['卫斯李(摩根大通)', '卫斯李(大摩)', 'AI产业链·Serenity']
consensus.append(c1)

c2 = OrderedDict()
c2['topic'] = '港股MXHK逢低吸纳(延续)'
c2['view'] = '摩根大通在政策噪音中建议低吸（远期 PE 14.0x 低于 10 年均值 0.4 个标准差）；180K 亚洲区域小结印证港股小幅收高'
c2['type'] = 'short'
c2['sources'] = ['卫斯李(摩根大通)', '180K Research']
consensus.append(c2)

c3 = OrderedDict()
c3['topic'] = 'A股疲态+光网络/有色走强'
c3['view'] = 'GS CHINA WRAP：成交 1.89 万亿创 4 月来最低(-9.63% DoD)；中际旭创+4.29% / 新易盛+6.76%；资金买 PCB/电子设备'
c3['type'] = 'short'
c3['sources'] = ['180K Research(GS)']
consensus.append(c3)

c4 = OrderedDict()
c4['topic'] = '全球资本回报故事'
c4['view'] = '180K 韩国小结：三星 W150tn 股东回报方案（vs 昨日报道 W100tn）；大摩延续炼油股利润率新中枢 +30%'
c4['type'] = 'event'
c4['sources'] = ['180K Research(GS Korea)', '卫斯李(大摩)']
consensus.append(c4)

c5 = OrderedDict()
c5['topic'] = '机器人 / NV 供应链国产化'
c5['view'] = '基业长青+：国瓷陶瓷基板(27H2 放量)/铂科芯片电感(TLVR ASP 2→6 元/颗)量价齐升；天风继续看好上纬、福莱（审美投资时代）'
c5['type'] = 'mid'
c5['sources'] = ['基业长青+']
consensus.append(c5)

c6 = OrderedDict()
c6['topic'] = '防御板块相对抗跌'
c6['view'] = '美银看空欧洲超配食品饮料/电信/制药；花旗 8 月增持黄金对抗贬值交易；GS 卖出材料和电气设备'
c6['type'] = 'mid'
c6['sources'] = ['卫斯李(美银)', '卫斯李(花旗)', '180K Research(GS)']
consensus.append(c6)

new['consensus'] = consensus

# 相反观点
opposite = []
o1 = OrderedDict()
o1['topic'] = '港股/大盘短期方向'
sa = OrderedDict()
sa['direction'] = '偏多'
sa['view'] = '摩根大通 MXHK 逢低吸纳（PE 估值吸引 + 政策是情绪而非基本面）；GS CHINA WRAP 资金略偏多 Buy（买 PCB/电子设备）'
sa['source'] = '卫斯李(摩根大通) + 180K Research(GS)'
sb = OrderedDict()
sb['direction'] = '偏空'
sb['view'] = '大鹏鸟"调整还没到位，控制仓位"；T&J"15F 下跌中枢构建中，等待日线死叉"'
sb['source'] = '大鹏鸟笔记 + Truth and Justice'
o1['side_a'] = sa
o1['side_b'] = sb
o1['judgment_note'] = '方向相反（A 多 vs B 空），且 A 用估值/资金面、B 用技术面/节奏，互斥。午后实际 SHCOMP +0.04% 收 3905.20 窄幅震荡，未给出明确方向 → 双方均"部分对"（震荡成立，方向未确认）'
opposite.append(o1)

o2 = OrderedDict()
o2['topic'] = 'AI资本支出可持续性'
sa2 = OrderedDict()
sa2['direction'] = '偏多（基础设施回报）'
sa2['view'] = '摩根大通模型显示 AI capex 回报可测（NPV 36元/100元，IRR 22%）；大摩十项全中重申阿里首选；基业 NPO 进展印证光模块景气'
sa2['source'] = '卫斯李(摩根大通/大摩) + 基业长青+'
sb2 = OrderedDict()
sb2['direction'] = '偏空（模型层变现）'
sb2['view'] = '美银：AI 模型层价格战（自 5 月起 Silicon Data Token 支出指数降 50%）+ 超大规模运营商借贷成本翻倍（55bp→120bp）+ 物流与政治障碍 → Stoxx 600 明年 Q2 跌 10% 至 580 点'
sb2['source'] = '卫斯李(美银欧洲团队)'
o2['side_a'] = sa2
o2['side_b'] = sb2
o2['judgment_note'] = '同一产业链不同环节，方向相反（基础设施回报看多 vs 模型层变现看空），构成实质性相反观点'
opposite.append(o2)

o3 = OrderedDict()
o3['topic'] = '泡泡玛特/中国消费IP'
sa3 = OrderedDict()
sa3['direction'] = '偏多（情绪托底）'
sa3['view'] = '段永平持 7%+ 计划持有 10 年；港股投资者对 IP 故事仍有信心'
sa3['source'] = '卫斯李(德银) - 段永平持仓段'
sb3 = OrderedDict()
sb3['direction'] = '偏空（基本面恶化）'
sb3['view'] = '德银：1H26 营收低于一致 14%/净利低于一致 22%；2Q 营收 -12%（1Q +75-80%）；海外 2Q -48%；库存周转 203 天（北美 427 天）；Labubu -7.5% / Molly -33.6%'
sb3['source'] = '卫斯李(德银)'
o3['side_a'] = sa3
o3['side_b'] = sb3
o3['judgment_note'] = '方向相反（情绪托底 vs 基本面恶化）。德银维持卖出，目标价 115 港元 — 基本面证据充分，情绪支撑有限'
opposite.append(o3)

new['opposite'] = opposite
new['status'] = 'pending'

cc['records'].append(new)
with open(path, 'w', encoding='utf-8') as f:
    json.dump(cc, f, ensure_ascii=False, indent=2)
print('consensus_chain updated: 16:00 close record verified + evening record appended')
print('total records:', len(cc['records']))
