"""更新共识链：复盘上期+写本期"""
import json
with open('.workbuddy/consensus_chain.json', encoding='utf-8') as f:
    data = json.load(f)

last = data['records'][-1]
print('Last pending:', last['id'])

# 复盘 review
last['review'] = {
    'reviewed_at': '2026-08-22 09:10 晨报（2026-08-22 周六休市，仅做参考性核验；正式验证需 8/24 开盘后）',
    'consensus_review': [
        {'topic': '国内大盘短期方向', 'verdict': '兑现（震荡偏空基调）', 'detail': '8/21 实际窄幅震荡 3883-3912 / 收 3905.20（+0.04%），未出现明确方向；大鹏鸟+T&J 震荡偏空基调正确（未给抄底机会），技术面偏多未兑现上涨（仅微涨 0.04%）'},
        {'topic': 'AI算力/阿里仍是核心标的', 'verdict': '不参与（事件事实）', 'detail': '8/21 收盘后 4 大行（GS/MS/JPM/Citi）+ Nomura + Bernstein 同步看多阿里；属 event 事件性描述，非预测，不参与复盘'},
        {'topic': '黄金中长期看多', 'verdict': '跟踪中（中期）', 'detail': 'BofA Cross-Asset：2026YTD 黄金 +26%；3m/1y/5y IRR 黄金分别 9.5%/26.4%/27.4% 居首；中长期逻辑不变'},
        {'topic': '炼油股利润率新中枢', 'verdict': '跟踪中（中期）', 'detail': '窗口内未见反驳；大摩核心观点延续'},
        {'topic': '港股MXHK逢低吸纳', 'verdict': '部分兑现（偏多但空间有限）', 'detail': '8/21 港股小幅收高（GS Asia Wrap：材料与矿业走强带动大盘），与 J.P. Morgan 逢低吸纳一致；但成交清淡（1.89 万亿 4 月以来最低）'},
        {'topic': '国内机器人板块', 'verdict': '部分（节奏分歧延续）', 'detail': '8/21 窗口内未见机器人板块明确催化；大鹏鸟等龙一与基业长青+审美投资时代基本面判断延续；窗口内未决'},
        {'topic': '3D打印/铂力特/华曙高科', 'verdict': '跟踪中（中期）', 'detail': '中期逻辑未变，窗口内未见新调研'},
        {'topic': '泡泡玛特2026H2业绩', 'verdict': '不参与（事件事实）', 'detail': '事件事实描述，非预测'},
        {'topic': 'NV供应链国产化受益', 'verdict': '跟踪中（中期）', 'detail': '窗口内未见新调研；2026-08-21 基业长青+旭创 H1 财报点评：光模块毛利率涨 6 个点、需求不减、上游锁货/囤货/预付款/应收大涨、现金流-44%；行业景气延续'},
    ],
    'opposite_review': [
        {'topic': '机器人板块节奏与风险偏好', 'verdict': '未决（窗口内无新催化）', 'detail': '基本面-节奏分歧延续'},
        {'topic': '国内大盘短期方向：跨星球 vs 技术面', 'verdict': '部分（双方部分命中）', 'detail': '偏空一方（控制仓位、不抄底）命中（8/21 收盘 3905.20 持平未给机会）；偏多一方（15F三买+日线BOLL开口）未兑现上涨（仅+0.04%），但 15F 三买支撑 3883.79 精准有效；最终判定：实际窄幅震荡 0.04%，未走出方向，双方均部分兑现'},
    ]
}
last['status'] = 'verified'
print('共识链 8/21-close 记录 review 写入完成，status 改为 verified')

# 追加本期新记录（8/22-morning）
new_rec = {
    'id': '2026-08-22-morning',
    'report_type': '晨报',
    'created_at': '2026-08-22 09:10',
    'window': '2026-08-21 16:00 ~ 2026-08-22 09:00',
    'consensus': [
        {
            'topic': '阿里仍是 AI 算力核心标的（4 大行 +2 看多共识）',
            'view': '8/21 阿里 1QFY27 财报后 GS（PT 186/180、+44.3% Upside、Buy）、MS（mid-teens ROIC、<3-yr payback）、JPM（AI Capex From Spend to Return、Buy）、Citi（SOTP 190/189、Buy）、Nomura（Brighter outlook for AI Cloud）、Bernstein（Outperform、PT 180/176）6 家国际投行同日看多，capex 持续上修+ROIC 路径清晰',
            'type': 'event',
            'sources': ['卫斯李的投研笔记（GS/MS/JPM/Citi/Nomura/Bernstein 摘要）', 'xxpq 知识库（GS / MS / JPM / Citi / Nomura / Bernstein 6 份研报）', '基业长青+ 高盛中国市场日报（2026-08-22 00:02）']
        },
        {
            'topic': '国内光模块/光通信板块短期偏多',
            'view': '8/22 高盛中国市场日报：板块层面光网络板块相对走强（头部光模块企业即将迎来财报披露期）；中际旭创(30030.SH)+4.29%（盘后业绩催化）、新易盛(300502.SZ)+6.76%；资金买入 PCB + 电子元器件',
            'type': 'event',
            'sources': ['基业长青+ 高盛中国市场日报（2026-08-22 00:02）', '180K Research（GS China Wrap 2026-08-21 16:06/17:21）', '基业长青+ 旭创 H1 财报点评（2026-08-22 00:23）']
        },
        {
            'topic': '30Y 美债收益率红线 5% 政策护盘有效但短期不可持续',
            'view': 'BofA 30Y 5% Maginot Line：US 30Y 5.25% 接近 5% 红线；贝森特 Treasury twist + 美元互换 + 日元干预 + 长期国债回购翻倍等贝森特看跌期权组合为美债收益率设上限；但 JPM 等机构警示市场将视财政部缺乏公信力',
            'type': 'mid',
            'sources': ['卫斯李的投研笔记（美银哈特内特 16:04 8图研报 + 20:30 高盛美股盘前）', 'xxpq 知识库（JPM Slams Bessent / 华尔街对财政部回购的反应 8/20）']
        },
        {
            'topic': '黄金中长期看多（5Y IRR 27.4% 居首）',
            'view': 'BofA 5 年 IRR 黄金 27.4% 居所有资产之首；3 个月/1 年 IRR 分别 9.5%/26.4%；Cross-Asset 2026YTD 黄金 +26%；特朗普支持率创新低（39% 综合/36% 经济/30% 通胀）+ USD/Gold 比例走弱 + 信用公信力下降，避险逻辑延续',
            'type': 'mid',
            'sources': ['卫斯李的投研笔记（美银 16:04）', '卫斯李 23:23 日评（油价利率视角看黄金）', 'xxpq 知识库（Hartnett: The Trade Is Long Gold 8/17）']
        },
        {
            'topic': 'AI Capex 浪潮延续但 AI fragility 显现',
            'view': 'BofA 16:08：超大规模云厂商 12m fwd capex 从 2025 初 3000 亿美元升至 9400 亿美元（占美国 GDP 3%）；但 AI fragility 持续：Hyperscaler 6 周内相对市场回撤 20%、HBM token 支出指数回落、Chinese model usage 8 月超越 US（OpenRouter）、Oracle CDS 利差升至 2008 以来新高、Hyperscaler FCF 流入半导体',
            'type': 'mid',
            'sources': ['卫斯李的投研笔记（美银 16:08 5图）', 'xxpq 知识库（Goldman Warns Massive Hyperscaler Bond Issuance）']
        },
        {
            'topic': '韩国存储：三星 HBM4 上量超预期 vs SK 海力士受 Rubin 延期承压',
            'view': '伯恩斯坦韩国 7 月存储出口追踪：三星 HBM 出口（忠清南道）较 4 月环比暴增 122%，三季度 HBM 收入将环比增 80% 至 120 亿美元（较此前预期高 30%），单位重量出口价值 7 月再涨 21%、是 SK 海力士同期近 4 倍；SK 海力士（忠清北道/利川）7 月出口环比下滑 27%，三季度 HBM 收入将环比降 20% 至 56 亿美元（较预期低 55%），主因英伟达 Rubin 延期',
            'type': 'event',
            'sources': ['基业长青+ 伯恩斯坦 韩国存储出口追踪 7月（2026-08-22 00:09）', '180K Research 外资研报（2026-08-21 19:43，Samsung W90-110tr Capital Returns + Korea Memory Export Tracker 7月）']
        },
        {
            'topic': '北美数据中心制冷/电气设备订单确定性极强',
            'view': '伯恩斯坦调研 50 位采购负责人：约半数超额下单（部分品类超 50%），但取消订单违约金比预期严苛，倒逼客户提货；短期设备商订单确定性极强；模块化/预制化渗透率 60% 受访者认为将显著提升；施耐德占电力与制冷设备支出 20%+，维谛/伊顿紧随',
            'type': 'mid',
            'sources': ['基业长青+ 伯恩斯坦 北美数据中心制冷与电气设备（2026-08-22 00:07）']
        },
        {
            'topic': '港股 8/24 开盘后或迎 AI 算力龙头领涨',
            'view': '港股与 A 股 8/21 收高（材料/矿业走强带动大盘）；下周多家中国 AI 算力龙头可能因美股 AI 标的（NVDA 财报、阿里 4 大行上调）联动走强；摩根大通建议 MXHK 逢低吸纳（超配金融/地产/创科/领展）',
            'type': 'short',
            'sources': ['基业长青+ 高盛中国市场日报（2026-08-22 00:02）', '基业长青+ 是什么驱动了市场行情（2026-08-22 00:02）', '卫斯李的投研笔记（港股 MXHK 逢低吸纳）']
        },
        {
            'topic': 'Q2 财报中游制造：风电纱/华利集团/巴比食品业绩亮眼',
            'view': '① 山东玻纤（天风建筑建材）2026H1 营收 15.6 亿（+38%）、归母净利 2922.77 万（+235%）、经营现金流 1.06 亿（同比大幅转正），风电纱量价齐升（产能 15 万吨，2027 达 30 万吨）；② 华利集团 26H1 前五大：Nike(~18%)/Hoka(~11%)/UGG(~10.8%)/On(~9.8%)/Vans(~9.5%)，Hoka 印尼第一工厂月产 80 万双已达集团平均 95% 盈利；③ 巴比食品门店转型加速，全年开店 600-700 家，6 月豆花/干蒸小笼/小龙虾拌面堂食反馈好',
            'type': 'event',
            'sources': ['基业长青+ 山东玻纤 26H1 业绩（2026-08-21 21:41）', '基业长青+ 华利集团 26H1 业绩（2026-08-21 22:48）', '基业长青+ 巴比食品 26H1 业绩（2026-08-21 22:29）']
        },
        {
            'topic': 'A 股 8/21 成交萎缩（1.89 万亿 4 月以来最低）= 短期承压信号',
            'view': '8/21 沪深成交 1.89 万亿元（-9.63% DoD），为 4 月初以来最低 / 年内第四低；高盛中国日报：市场整体走势方向感偏弱，缺少催化因素；BofA B&B Indicator 9.5（卖）= 极端 V Bullish；周末无新增数据，方向承压',
            'type': 'event',
            'sources': ['基业长青+ 高盛中国市场日报（2026-08-22 00:02）', '卫斯李的投研笔记（美银 16:04 Chart 23-24 B&B Indicator 9.5 卖）']
        },
    ],
    'opposite': [
        {
            'topic': '阿里 8/21 财报后股价方向：内部分歧 vs 共识',
            'side_a': {
                'direction': '短期看多（基于 4 大行同步上调 + ROIC 路径清晰）',
                'view': '8/21 收盘后 GS/MS/JPM/Citi/Nomura/Bernstein 6 家同日看多，capex 持续上修 + ROIC 路径清晰，AI Capex From Spend to Return',
                'source': '卫斯李的投研笔记（GS/MS/JPM/Citi 摘要） + xxpq 知识库（6 份研报）'
            },
            'side_b': {
                'direction': '中期存疑（基于 AI fragility 持续）',
                'view': '美银 8/21 报告：超大规模云厂商 6 周内相对市场回撤 20%、HBM token 支出指数回落、Chinese model usage 8 月超越 US、Oracle CDS 利差 2008 以来新高，AI Capex 持续性存疑；摩根大通抨击贝森特财政部缺乏公信力',
                'source': '卫斯李的投研笔记（美银 16:08） + xxpq 知识库（JPM Slams Bessent 8/20）'
            },
            'judgment_note': '时间维度分歧，非资产方向互斥。短期（数日-数周）看多 vs 中期（数月-数季）看空，节奏差异'
        },
        {
            'topic': '美股科技/大盘方向：龙头护盘 vs 内部分化',
            'side_a': {
                'direction': '偏多（科技龙头护盘 + 财报季催化）',
                'view': 'BofA 私行客户：4 周 ETF 流入 Japan/Munis/TIPS 居前；GWIM 股票配置 66%（历史新高）= 风险偏好高位；NVDA 8/27 财报 + 7 月 PCE 数据催化；8/21 道指 +0.98% / 罗素 2000 +0.85% 领涨',
                'source': '卫斯李的投研笔记（美银 16:04 Chart 16-19 + 隔夜美股评论 08:38）'
            },
            'side_b': {
                'direction': '偏空（科技板块内部分化 + 标普 500 科技 6 连跌）',
                'view': '8/21 标普 500 科技板块连续第 6 个交易日下跌（2022/9 以来最长连跌）；纳指 100 终结 5 连跌但周跌 2.1%；8 月 FMS 调查：56% 预期民主党横扫两院（37% 预期债熊股熊）；标普 500 板块广度 11 板块中 7 涨但公用事业跌 2%+',
                'source': '卫斯李的投研笔记（美银 16:04 Chart 3-4 + 隔夜美股评论 08:38）'
            },
            'judgment_note': '风格分歧：龙头护盘（Dow/RSP 领涨）vs 科技板块承压（标普科技 6 连跌）'
        },
    ],
    'status': 'pending'
}
data['records'].append(new_rec)

with open('.workbuddy/consensus_chain.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('consensus_chain.json updated. Total records:', len(data['records']))
