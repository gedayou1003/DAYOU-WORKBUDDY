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
