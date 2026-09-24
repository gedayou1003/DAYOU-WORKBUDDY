# -*- coding: utf-8 -*-
"""test_dragonball_signals.py —— DRAGONBALL 融合 P0 纯函数的回归测试。

覆盖三层（《DRAGONBALL_融合蓝图.md》§六「反向验证三件套」）：
  A. 正向测试：六态分类 / 零轴交叉 / 55线网格 / 刺破分层 / 极强传递性 / X段，逐态断言；
  B. 变异测试：把判据改错（正则替换源码再 exec），断言正向测试**必须变红（CAUGHT）**，
     证明本测试不是「恒绿形同虚设」；
  C. 语义隔离测试：macd_state（稳定性）与现有 MACD 动能字段**独立**，不互相覆盖。

用法：$PY .workbuddy/test_dragonball_signals.py
退出码：0 全部通过 · 1 有失败（可接进 run_tests 聚合闸门）
"""
import importlib.util
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, 'dragonball_signals.py')

spec = importlib.util.spec_from_file_location('dbsig', MOD)
dbsig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbsig)

fails = []
total = [0]


def ck(cond, msg):
    total[0] += 1
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def st(dif, dea):
    return dbsig.classify_macd_state(dif, dea)['state']


print('=== A. 正向测试 ===')

# A1 六态分类（篇4 原文判据逐态钉死）
ck(st(1.0, -0.5) == '极强', '极强：DIF≥0 且 DEA≤0 且多头')
ck(st(0.0, -0.5) == '极强', '极强边界：DIF=0 仍归极强（原文 DIF≥0）')
ck(st(1.0, 0.0) == '极强', '极强边界：DEA=0 仍归极强（原文 DEA≤0）')
ck(st(1.5, 1.0) == '强', '强：DIF>DEA>0')
ck(st(-0.5, -1.0) == '中性偏强', '中性偏强：0>DIF>DEA')
ck(st(1.0, 1.5) == '中性偏弱', '中性偏弱：0<DIF<DEA')
ck(st(-1.0, -0.5) == '弱', '弱：DIF<DEA<0')
ck(st(-0.5, 1.0) == '极弱', '极弱：DIF≤0 且 DEA≥0 且空头')
ck(st(0.0, 1.0) == '极弱', '极弱边界：DIF=0 仍归极弱（原文 DIF≤0）')
ck(st(-1.0, 0.0) == '极弱', '极弱边界：DEA=0 仍归极弱（原文 DEA≥0）')
ck(st(0.5, 0.5) == 'cross', 'DIF==DEA 归 cross（金叉/死叉点）')

# A2 六态完备性：多头 3 态 + 空头 3 态 + cross 恰好覆盖所有组合（符号维度）
seen = set()
for dif, dea in [(1, -0.5), (1.5, 1.0), (-0.5, -1.0),
                 (1, 1.5), (-1, -0.5), (-0.5, 1), (0.5, 0.5)]:
    seen.add(st(dif, dea))
ck(seen == {'极强', '强', '中性偏强', '中性偏弱', '弱', '极弱', 'cross'},
   '六态 + cross 完备覆盖（无遗漏、无重叠）')

# A3 零轴金叉/死叉等价（篇4：零轴金叉≡极强、零轴死叉≡极弱）
ck(dbsig.detect_zero_cross(0.1, -0.1, -0.1, 0.05) == 'golden', '零轴金叉（跨零轴）')
ck(dbsig.detect_zero_cross(-0.1, 0.1, 0.05, -0.1) == 'dead', '零轴死叉（跨零轴）')
ck(dbsig.detect_zero_cross(1.0, 0.5, 0.4, 0.6) is None, '零轴上方金叉≠零轴金叉（不跨零轴）')
ck(dbsig.detect_zero_cross(0.5, 1.0, 1.0, 0.5) is None, '零轴上方死叉≠零轴死叉（不跨零轴）')

# A4 多级别 55 线网格
g = dbsig.build_ma55_grid({'日线': list(range(1, 56)), '60F': [1.0] * 60, '15F': [1, 2, 3]})
ck(g['日线'] == round(sum(range(1, 56)) / 55.0, 2), '55 根取最近 55 根均值')
ck(g['60F'] == 1.0, '60 根取最近 55 根（=1.0）')
ck(g['15F'] is None, '不足 55 根 → None（不猜）')

# A5 刺破 / 有效跌破 分层（优先级：破55 > 破中轨 > 刺破收回 > 站上）
ck(dbsig.classify_break(100, 99, 105, 110) == '有效破55线', 'close<ma55 → 有效破55线')
ck(dbsig.classify_break(107, 99, 110, 105) == '有效破中轨', 'close<ma20 且 ≥ma55 → 有效破中轨')
ck(dbsig.classify_break(111, 108, 110, 105) == '刺破中轨收回', 'low<ma20≤close → 刺破收回')
ck(dbsig.classify_break(115, 112, 110, 105) == '站上中轨', 'close≥ma20 且 low≥ma20 → 站上')

# A6 极强传递性
ck(dbsig.infer_transmission('极强', 106, 100, 120) ==
   {'transmission': True, 'target': 120}, '极强 + 突破本级55 → 目标=上一级55')
ck(dbsig.infer_transmission('强', 106, 100, 120) ==
   {'transmission': False, 'target': None}, '非极强不传递')
ck(dbsig.infer_transmission('极强', 95, 100, 120) ==
   {'transmission': False, 'target': None}, '极强但未突破本级55 → 不传递')

# A7 X 段 vs 带结构回踩
ck(dbsig.classify_pullback(False, True) == 'X段', '主涨段 + 上一级没结构 → X段')
ck(dbsig.classify_pullback(True, True) == '带结构回踩', '主涨段 + 上一级有结构 → 带结构回踩')
ck(dbsig.classify_pullback(False, False) == '非主涨段', '非主涨段 → X 段不适用')
ck(dbsig.classify_pullback(True, False) == '非主涨段', '非主涨段（即使有结构）→ 不适用')


def _bi(t, s, e):
    return {'bi_type': t, 'start_price': s, 'end_price': e,
            'start_date': None, 'end_date': None}


# A8 主涨段判定（篇5 严格公式：N+2 极强/金叉 + N 上涨线段 + N 低位）
_bi3 = [_bi('up', 100, 110), _bi('down', 110, 105), _bi('up', 105, 115)]
r = dbsig.detect_main_up('极强', None, _bi3, 2.0)
ck(r['is_main_up'] is True, '主涨段：极强触发 + 上涨线段 + 低位 → True')
ck(r['up_segment'] == 1 and r['n_segments'] == 1, '3 笔 → 1 个上涨线段')
r = dbsig.detect_main_up('极强', None, [_bi('up', 100, 110), _bi('down', 110, 105)], 2.0)
ck(r['is_main_up'] is False, '不足 3 笔（回调中）→ 非主涨段')
r = dbsig.detect_main_up('极强', None, _bi3, 8.0)
ck(r['is_main_up'] is False, '价格远离 55 线（dist>5%）→ 非低位 → 非主涨段')
r = dbsig.detect_main_up('强', None, _bi3, 2.0)
ck(r['is_main_up'] is False, 'N+2 非极强且无金叉 → 未触发')
r = dbsig.detect_main_up('强', 'golden', _bi3, 1.0)
ck(r['is_main_up'] is True, '零轴金叉触发（篇5「或金叉」并集）→ True')
_bi6 = [_bi('up', 100, 110), _bi('down', 110, 105), _bi('up', 105, 115),
        _bi('down', 115, 110), _bi('up', 110, 112), _bi('down', 112, 108)]
r = dbsig.detect_main_up('极强', None, _bi6, 2.0)
ck(r['n_segments'] == 2 and r['up_segment'] == 1, '多线段：2 段(1up+1down)，up_segment=1')


# A9 缠论线段划分（特征序列分型法）
segs = dbsig.divide_segments([
    _bi('up', 100, 110), _bi('down', 110, 105), _bi('up', 105, 115)])
ck(len(segs) == 1 and segs[0]['direction'] == 'up' and segs[0]['bi_count'] == 3,
   '3 笔无破坏 → 1 段 up（bi_count=3）')
ck(segs[0]['end_price'] == 115, '向上段终点 = 段内最高（115）')

segs = dbsig.divide_segments([
    _bi('up', 100, 110), _bi('down', 110, 105), _bi('up', 105, 115),
    _bi('down', 115, 110), _bi('up', 110, 112), _bi('down', 112, 108)])
ck(len(segs) == 2, '顶分型破坏 → 2 段')
ck(segs[0]['direction'] == 'up' and segs[0]['end_price'] == 115, '第一段 up 终点=顶分型极点 115')
ck(segs[1]['direction'] == 'down', '第二段方向 down（从破坏笔开始）')

# 向下段对称（底分型破坏）
segs = dbsig.divide_segments([
    _bi('down', 200, 190), _bi('up', 190, 195), _bi('down', 195, 185),
    _bi('up', 185, 192), _bi('down', 192, 180), _bi('up', 180, 188)])
ck(len(segs) >= 1, '向下段至少 1 段')

ck(dbsig.divide_segments([]) == [], '空输入 → 空')
ck(dbsig.divide_segments([_bi('up', 100, 110), _bi('down', 110, 105)]) == [],
   '不足 3 笔 → 空（不成线段）')

# A10 主涨特征解除两路径状态机（篇5）
s, v = dbsig.track_break('维持', 106, 105)
ck(s == '维持', '维持 + 收盘在中轨上 → 维持')
s, v = dbsig.track_break('维持', 104, 105)
ck(s == '解除' and '不等于下跌' in v, '维持 + 跌破中轨 → 解除（不等于下跌）')
s, v = dbsig.track_break('解除', 104, 105)
ck(s == '解除' and '被压制' in v, '解除 + 继续中轨下 → 解除（路径①被压制）')
s, v = dbsig.track_break('解除', 106, 105)
ck(s == '反抽突破', '解除 + 反抽突破中轨 → 反抽突破（路径②）')
s, v = dbsig.track_break('反抽突破', 104, 105)
ck(s == '二次跌破' and '回调升级' in v, '反抽突破 + 再破中轨 → 二次跌破（回调升级，至少回踩55线）')
s, v = dbsig.track_break('反抽突破', 106, 105)
ck(s == '维持', '反抽突破 + 守住中轨 → 维持')

# A11 尾指数 Hill 估计量（篇1 V_tail = 1/ξ）
thick = [-0.1] * 20 + [-8.0, -6.0, -5.0, -4.0, -3.0]  # 少数极端损失（厚尾）
thin = [-1.0] * 25                                      # 均匀损失（薄尾）
r_thick = dbsig.hill_tail_index(thick)
r_thin = dbsig.hill_tail_index(thin)
ck(r_thick['xi'] is not None and r_thick['xi'] > 0, '厚尾序列 xi > 0')
ck(abs(r_thick['v_tail'] - round(1.0 / r_thick['xi'], 4)) < 1e-9, 'v_tail = 1/xi')
ck(r_thick['xi'] > r_thin['xi'], '厚尾 xi > 薄尾 xi（极端损失多 → 尾更厚）')
ck(dbsig.hill_tail_index([])['note'] == '下跌样本不足 10', '空输入 → note')
ck(dbsig.hill_tail_index([1.0] * 5)['note'] == '下跌样本不足 10', '无下跌样本 → note')

# A12 双日/双周聚合（篇4 体系 B）
dbl = dbsig.aggregate_double([
    {'date': 'd1', 'open': 100, 'close': 110, 'high': 112, 'low': 99, 'vol': 10},
    {'date': 'd2', 'open': 110, 'close': 105, 'high': 113, 'low': 104, 'vol': 20},
    {'date': 'd3', 'open': 105, 'close': 108, 'high': 109, 'low': 103, 'vol': 15},
    {'date': 'd4', 'open': 108, 'close': 112, 'high': 115, 'low': 107, 'vol': 25},
])
ck(len(dbl) == 2, '4 根 → 2 根双日')
ck(dbl[0]['open'] == 100 and dbl[0]['close'] == 105 and dbl[0]['date'] == 'd2',
   '双日 open=首根 open、close=次根 close、date=次根 date')
ck(dbl[0]['high'] == 113 and dbl[0]['low'] == 99 and dbl[0]['vol'] == 30,
   '双日 high=max、low=min、vol=和')
ck(len(dbsig.aggregate_double([{'date': 'd1', 'open': 1, 'close': 2, 'high': 2, 'low': 1}])
        ) == 0, '奇数根 → 最后单根丢弃')

# A13 集中度 Σwi²（篇2 抱团度量）
ck(dbsig.concentration([1, 1, 1, 1])['concentration'] == 0.25, '4 等权 → Σwi²=0.25')
c_conc = dbsig.concentration([100, 1, 1, 1])['concentration']
ck(c_conc > 0.9, '高度集中（100:1:1:1）→ Σwi² 接近 1')
ck(dbsig.concentration([])['concentration'] is None, '空输入 → None')
ck(abs(dbsig.concentration([2, 3, 5])['concentration'] - (0.2**2 + 0.3**2 + 0.5**2)) < 1e-9,
   '未归一权重 [2,3,5] → 先归一再 Σwi²')

print('=== B. 变异测试（判据改错必须被抓住） ===')

_SRC = open(MOD, encoding='utf-8').read()


def mutate(old, new, label):
    mut = _SRC.replace(old, new)
    ck(mut != _SRC, '变异命中：%s（%r→%r）' % (label, old, new))
    if mut == _SRC:
        return
    ns = {}
    exec(compile(mut, MOD, 'exec'), ns)
    return ns


# B1 变异极强边界：dea <= 0 → dea < 0（丢掉 DEA=0 归极强）。正向用例 dif=1,dea=0 期望「极强」。
ns = mutate('dea <= 0', 'dea < 0', '极强 DEA≤0 → DEA<0')
if ns:
    mut_st = ns['classify_macd_state']
    caught = mut_st(1.0, 0.0)['state'] != '极强'
    ck(caught, 'B1 变异被抓住（DEA=0 边界丢失 → 不再报极强）')

# B2 变异 X 段方向：把「上一级没结构→X段」搞反成「有结构→X段」（蓝图点名的最易搞反点）。
ns = mutate("return 'X段' if not has_structure_n1 else '带结构回踩'",
            "return 'X段' if has_structure_n1 else '带结构回踩'", 'X段方向搞反')
if ns:
    mut_pull = ns['classify_pullback']
    caught = mut_pull(False, True) != 'X段'
    ck(caught, 'B2 变异被抓住（没结构回踩被误判）')

# B3 变异网格除数：55 → 54（静默改数值）。正向用例期望 round(sum/55)。
ns = mutate('sum(closes[-55:]) / 55.0', 'sum(closes[-55:]) / 54.0', 'MA55 除数 55→54')
if ns:
    mut_grid = ns['build_ma55_grid']
    got = mut_grid({'日线': list(range(1, 56))})['日线']
    ck(got != round(sum(range(1, 56)) / 55.0, 2), 'B3 变异被抓住（除数改错 → 数值漂移）')

# B4 变异主涨段触发：把「极强 或 金叉」的 or 改成 and（把并集改成交集）。
ns = mutate("(n2_state == '极强') or (n2_zero_cross == 'golden')",
            "(n2_state == '极强') and (n2_zero_cross == 'golden')", '主涨段触发 or→and')
if ns:
    mut_mu = ns['detect_main_up']
    caught = (mut_mu('极强', None, _bi3, 2.0)['is_main_up'] is False)  # 极强但无金叉应被误判为未触发
    ck(caught, 'B4 变异被抓住（or 改 and → 极强单触发被漏判）')

# B5 变异低位阈值：<= 改 <（丢掉 dist==5.0 边界）。
ns = mutate('n_price_ma55_dist <= LOW_POSITION_THRESHOLD',
            'n_price_ma55_dist < LOW_POSITION_THRESHOLD', '低位阈值 <= → <')
if ns:
    mut_mu = ns['detect_main_up']
    caught = (mut_mu('极强', None, _bi3, 5.0)['low_position'] is False)  # 边界 5.0 应被判为低位
    ck(caught, 'B5 变异被抓住（<= 改 < → dist=5.0 边界被漏判为非低位）')

# B6 变异线段顶分型：> 改 <（搞反方向）。
_BIS6 = [_bi('up', 100, 110), _bi('down', 110, 105), _bi('up', 105, 115),
         _bi('down', 115, 110), _bi('up', 110, 112), _bi('down', 112, 108)]
ns = mutate("f2['start_price'] > f1['start_price']",
            "f2['start_price'] < f1['start_price']", '线段顶分型 > → <')
if ns:
    mut_seg = ns['divide_segments']
    caught = (len(mut_seg(_BIS6)) != 2)  # 正确版应为 2 段
    ck(caught, 'B6 变异被抓住（顶分型判据搞反 → 段数错）')

print('=== C. 语义隔离测试（稳定性 ≠ 动能） ===')

# C1 输出字段独立：classify_macd_state 只产 state/sign/side，不产也不覆盖现有动能字段
out = dbsig.classify_macd_state(1.5, 1.0)
ck(set(out.keys()) == {'state', 'sign', 'side'}, 'C1 输出仅含 state/sign/side（独立新字段）')
ck('dif_dir' not in out and 'zone' not in out and 'gap' not in out,
   'C1 不覆盖现有 dif_dir/zone/gap 动能字段')

# C2 语义并存：同一 DIF/DEA 可「稳定性=强」（多头持续）而「动能方向」由 dif 变化独立决定。
#    这里证明：classify_macd_state 只看 dif/dea 的符号关系，不接收 dif 变化量，
#    故它天然与「动能/背离」解耦（动能需要 prev_dif，本函数不接收）。
state_indep_of_direction = (st(1.5, 1.0) == '强')  # 只由 dif>dea>0 决定
ck(state_indep_of_direction, 'C2 稳定性分类只依赖 dif/dea 符号关系，与动能方向解耦')

print('-' * 62)
if fails:
    print('RESULT: FAIL %d 条' % len(fails))
    for f in fails:
        print('  · ' + f)
    sys.exit(1)
print('RESULT: ALL PASS（%d 组断言）' % total[0])
sys.exit(0)
