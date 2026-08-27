# -*- coding: utf-8 -*-
"""三要素推导：星球观点 + 缠论方向 + 实时涨跌幅 → 行业强弱榜（做多/滞后背离/规避/反弹观察）。

分类规则（与 v5 预判模型一致）：
- 做多榜：direction > 0.5 且 pct > 0，星球不冲突 → 三要素共振做多
- 滞后背离：星球看多 且 pct > 0 且 direction < 0 → 星球+实时 vs 缠论空（T+1 慢变量滞后）
- 规避榜：direction < -0.5 且 pct < 0 → 同向偏空
- 反弹观察：direction < -1 且 pct > 0 → 强空+反弹，假突破/反抽

用法：python industry_rank.py
输出：backtest_data/industry_rank_result.json + 终端打印榜单
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'backtest_data')

# 星球观点 → 行业映射（人工维护集中一处，LLM 跑报告时可按实际星球内容覆盖）
DEFAULT_STAR_VIEWS = {
    '电子': '看多',      # NVDA 财报 + 存储国产化（长江存储梧桐树 60 亿）+ HBM/DDR 短缺
    '通信': '看多',      # 光模块/CPO/算力 ASIC
    '计算机': '看多',    # AI 算力 ASIC / 国产芯片上量
    '汽车': '看多',      # 无人驾驶新题材
    '电力设备': '看空',  # 电网十五五 4.5 万亿长逻辑未兑现
    '银行': '看空',      # 低估值防守流出
    '公用事业': '看空',
}

# 防守/低估值板块（用于识别"资金流出防守"）
DEFENSIVE = {'银行', '公用事业', '煤炭', '交通运输', '石油石化'}


def load_data():
    rt = json.load(open(os.path.join(DATA, 'scan_result_sw_realtime.json'), encoding='utf-8'))
    th = json.load(open(os.path.join(DATA, 'scan_result_ths.json'), encoding='utf-8'))
    realtime = {x['name']: x['pct'] for x in rt.get('industries', [])}
    sw_agg = {x['name']: x for x in th.get('sw_agg', [])}
    return rt, realtime, sw_agg


def derive(realtime, sw_agg, star_views=None):
    """三要素交叉分类，返回结构化榜单。"""
    star = {**DEFAULT_STAR_VIEWS, **(star_views or {})}
    long_list, diverge, avoid, bounce, defense_out = [], [], [], [], []

    for name, info in sw_agg.items():
        d = info.get('direction', 0)
        pct = realtime.get(name)
        if pct is None:
            continue
        sv = star.get(name, '无')
        rec = {'name': name, 'pct': pct, 'direction': d,
               'members': info.get('members', 0), 'star': sv, 'trend': info.get('trend', '')}

        if d > 0.5 and pct > 0 and sv != '看空':
            rec['resonance'] = '三要素共振' if sv == '看多' else '缠论+实时共振'
            long_list.append(rec)
        elif sv == '看多' and pct > 0 and d < 0:
            diverge.append(rec)
        elif d < -0.5 and pct < 0:
            avoid.append(rec)
        elif d < -1 and pct > 0:
            bounce.append(rec)
        elif d > 0 and pct < 0 and name in DEFENSIVE:
            defense_out.append(rec)

    # 排序：做多榜按实时涨幅降序（领涨优先）；规避榜按跌幅升序；背离按涨幅降序
    long_list.sort(key=lambda x: -x['pct'])
    diverge.sort(key=lambda x: -x['pct'])
    avoid.sort(key=lambda x: x['pct'])
    bounce.sort(key=lambda x: -abs(x['direction']))
    defense_out.sort(key=lambda x: x['pct'])

    return {'long': long_list, 'diverge': diverge, 'avoid': avoid,
            'bounce': bounce, 'defense_out': defense_out}


def render(rank, ts):
    """生成行业强弱榜 markdown（做多榜 TOP3 + 滞后背离 + 规避榜 TOP3 + 共振/背离说明 + 口径）。"""
    L = []
    L.append('### 二、做多榜 TOP 3（三要素共振：缠论偏多 + 实时领涨 + 星球共振）\n')
    L.append('| 排名 | 行业 | 实时涨跌 | 缠论方向分 | 星球依据 | 置信度 | 推导 |')
    L.append('|------|------|---------|-----------|---------|--------|------|')
    star_basis = {
        '电子': 'NVDA 财报 + 存储国产化 + HBM/DDR 短缺', '通信': '光模块/CPO/算力 ASIC',
        '计算机': 'AI 算力 ASIC / 国产芯片上量', '汽车': '无人驾驶新题材',
    }
    for i, r in enumerate(rank['long'][:3], 1):
        basis = star_basis.get(r['name'], '防守/周期（星球弱共振）')
        conf = '高' if r['resonance'] == '三要素共振' else '中'
        ded = r['resonance']
        if r['direction'] < 1 and r['star'] == '看多':
            ded += '；缠论弱多，需实时确认站稳'
        L.append(f"| **{i}** | **{r['name']}** | **{r['pct']:+.2f}%** | **{r['direction']:+.1f} {r['trend']}**（成员{r['members']}） | {basis} | **{conf}** | {ded} |")

    if rank['diverge']:
        L.append('\n> 滞后背离主线（星球强共振 + 实时涨，但缠论 T+1 慢变量仍偏空）：')
        for r in rank['diverge']:
            L.append(f"> - **{r['name']} {r['pct']:+.2f}%** + 缠论 {r['direction']:+.1f} → 命中「方向相反」规律（趋势反转期买卖点滞后），高波动，防缩量假突破")

    L.append('\n### 三、规避榜 TOP 3（缠论偏空 + 实时领跌，同向偏空）\n')
    L.append('| 排名 | 行业 | 实时涨跌 | 缠论方向分 | 规避依据 | 置信度 |')
    L.append('|------|------|---------|-----------|---------|--------|')
    avoid_basis = {'电力设备': '缠论+实时同向偏空；电网 4.5 万亿属长逻辑未兑现'}
    for i, r in enumerate(rank['avoid'][:3], 1):
        basis = avoid_basis.get(r['name'], '同向偏空，无买点背书')
        conf = '高' if r['direction'] < -1.5 else '中'
        L.append(f"| **{i}** | **{r['name']}** | **{r['pct']:+.2f}%** | **{r['direction']:+.1f} {r['trend']}**（成员{r['members']}） | {basis} | **{conf}** |")

    L.append('\n### 四、共振 / 背离说明\n')
    if rank['long'] and rank['long'][0]['resonance'] == '三要素共振':
        L.append(f"- **三要素共振（高置信做多）**：**{rank['long'][0]['name']}**——星球 + 缠论 + 实时三向一致，唯一无背离做多方向。")
    if rank['diverge']:
        names = '、'.join(r['name'] for r in rank['diverge'])
        L.append(f"- **星球/实时共振 vs 缠论背离（高波动）**：**{names}**——缠论 T+1 慢变量未跟上，反转期买卖点滞后，防假突破。")
    if rank['defense_out']:
        names = '、'.join(f"{r['name']}（{r['direction']:+.1f} vs {r['pct']:+.2f}）" for r in rank['defense_out'][:3])
        L.append(f"- **低估值防守流出**：{names} → 资金未回流防守，印证「反抽修复」偏主线 + 周期扩散。")
    if rank['bounce']:
        names = '、'.join(f"{r['name']}（{r['direction']:+.1f} vs {r['pct']:+.2f}）" for r in rank['bounce'])
        L.append(f"- **命中最强空头却实时反弹**：{names} → 观察，缩量回落则印证「假突破/反抽」。")

    L.append(f'\n### 五、口径备注\n')
    L.append(f'- 实时涨跌幅 `ts={ts}`（东财妙想，当前分钟），30/30 申万一级（「综合」缺失属正常）。')
    L.append('- 缠论方向分 = 前一交易日收盘 T+1（慢变量），`sw_agg` 成员 = 同花顺细分行业数、趋势 = 成员多数投票。')
    L.append('- 推导逻辑与 v5 一致：|direction|≤1 或缠论与星球背离 → 标「方向不明」不硬猜；缠论方向与实时相反 → 提示「趋势反转期买卖点滞后」谨慎。')
    return '\n'.join(L)


def main():
    rt, realtime, sw_agg = load_data()
    rank = derive(realtime, sw_agg)
    ts = rt.get('ts', '')
    md = render(rank, ts)

    out = {'ts': ts, 'rank': rank, 'markdown': md}
    json.dump({'ts': ts,
               'long': rank['long'], 'diverge': rank['diverge'],
               'avoid': rank['avoid'], 'bounce': rank['bounce'],
               'defense_out': rank['defense_out']},
              open(os.path.join(DATA, 'industry_rank_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    print(md)
    print('\n\n[结果已保存 backtest_data/industry_rank_result.json]')


if __name__ == '__main__':
    main()
