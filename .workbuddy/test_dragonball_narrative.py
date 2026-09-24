# -*- coding: utf-8 -*-
"""test_dragonball_narrative.py —— DRAGONBALL 融合 D 叙事层（篇1 反身性）回归测试。

覆盖两层（沿用《DRAGONBALL_融合蓝图.md》§六反向验证方法论）：
  A. 正向测试：波动趋势 / 价格趋势 / 反身性四阶段归类 / 风险提示文案，逐态断言；
  B. 变异测试：把判据改错（字符串替换源码再 exec），断言正向测试必须变红（CAUGHT）。

用法：$PY .workbuddy/test_dragonball_narrative.py
退出码：0 全部通过 · 1 有失败
"""
import importlib.util
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, 'dragonball_narrative.py')

spec = importlib.util.spec_from_file_location('dbnar', MOD)
dbnar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbnar)

fails = []
total = [0]


def ck(cond, msg):
    total[0] += 1
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def _vol_closes(prior_amp, recent_amp):
    """11 根交替波动序列：前 5 根 prior_amp、后 5 根 recent_amp（win=5 下 prior/recent 各 5 根）。"""
    c = [100.0]
    for i in range(1, 6):
        c.append(c[-1] + (prior_amp if i % 2 == 1 else -prior_amp))
    for i in range(6, 11):
        c.append(c[-1] + (recent_amp if i % 2 == 1 else -recent_amp))
    return c


def _trend_closes(pct1, pct2):
    """11 根：前 5 根累计 pct1%、后 5 根累计 pct2%（ma_win=5 下 prior/recent 各 5 根）。"""
    c = [100.0]
    for i in range(1, 6):
        c.append(c[-1] * (1 + pct1 / 100 / 5))
    for i in range(6, 11):
        c.append(c[-1] * (1 + pct2 / 100 / 5))
    return c


print('=== A. 正向测试 ===')

# A1 波动趋势（win=5）
ck(dbnar.vol_trend(_vol_closes(3, 1), win=5) == 'squeeze', '波动收缩 → squeeze')
ck(dbnar.vol_trend(_vol_closes(1, 3), win=5) == 'explode', '波动激增 → explode')
ck(dbnar.vol_trend(_vol_closes(2, 2), win=5) == 'stable', '波动持平 → stable')
ck(dbnar.vol_trend([100.0, 101.0], win=5) is None, '样本不足 → None')

# A2 价格趋势（ma_win=5）
ck(dbnar.price_trend(_trend_closes(1, 3), ma_win=5) == 'accel_up', '加速上涨 → accel_up')
ck(dbnar.price_trend(_trend_closes(-6, -10), ma_win=5) == 'crash', '加速下跌 → crash')
ck(dbnar.price_trend(_trend_closes(0.5, 1), ma_win=5) == 'up', '温和上涨 → up')
ck(dbnar.price_trend(_trend_closes(-0.5, -1), ma_win=5) == 'down', '温和下跌 → down')
ck(dbnar.price_trend(_trend_closes(0.1, -0.1), ma_win=5) == 'flat', '窄幅 → flat')

# A3 反身性四阶段归类
ck(dbnar.reflexivity_stage('crash', 'stable') == 'stage4', '崩溃 → 阶段4')
ck(dbnar.reflexivity_stage('crash', 'explode') == 'stage4', '崩溃优先（即便波动激增）→ 阶段4')
ck(dbnar.reflexivity_stage('accel_up', 'explode') == 'stage3', '波动激增（分岔）→ 阶段3')
ck(dbnar.reflexivity_stage('accel_up', 'squeeze') == 'stage2', '加速+波动压制 → 阶段2')
ck(dbnar.reflexivity_stage('accel_up', 'stable') == 'stage2', '加速+波动稳定 → 阶段2')
ck(dbnar.reflexivity_stage('up', 'stable') == 'stage1', '温和 → 阶段1')
ck(dbnar.reflexivity_stage(None, 'stable') is None, '缺价格趋势 → None')
ck(dbnar.reflexivity_stage('up', None) is None, '缺波动趋势 → None')

# A4 风险提示文案
note2 = dbnar.build_risk_note('stage2')
ck('阶段2' in note2 and '正反馈' in note2, '阶段2 文案含「阶段2·正反馈」')
note4 = dbnar.build_risk_note('stage4')
ck('崩溃' in note4, '阶段4 文案含「崩溃」')
note_none = dbnar.build_risk_note(None)
ck('无法判定' in note_none, '信息不足 → 未定文案')
note_xi = dbnar.build_risk_note('stage2', tail_xi=0.4)
ck('尾指数' in note_xi and '尾部偏厚' in note_xi, '尾指数薄尾 → 量化佐证引用')
note_full = dbnar.build_risk_note('stage3', main_up=True, conc_high=True)
ck('主涨段' in note_full and '集中度' in note_full, '主涨段+集中度 → 量化佐证全引')
ck('定性叙事' in note_full and '不参与' in note_full, '文案标注「定性、不参与打分」')

print('=== B. 变异测试（判据改错必须被抓住） ===')

_SRC = open(MOD, encoding='utf-8').read()


def mutate(old, new, label):
    mut = _SRC.replace(old, new)
    ck(mut != _SRC, '变异命中：%s（%r→%r）' % (label, old, new))
    if mut == _SRC:
        return None
    ns = {}
    exec(compile(mut, MOD, 'exec'), ns)
    return ns


# B1 变异波动激增阈值：ratio > 1.4 → ratio > 2.0（1.5 倍放大被漏判）。
ns = mutate('ratio > 1.4', 'ratio > 2.0', 'vol_trend explode 阈值 1.4→2.0')
if ns:
    mut_vt = ns['vol_trend']
    caught = mut_vt(_vol_closes(1, 1.5), win=5) != 'explode'  # 正确版 1.5 倍放大应 explode
    ck(caught, 'B1 变异被抓住（阈值改错 → 波动放大被漏判）')

# B2 变异阶段2 判据：accel_up → up（把「加速」放宽为「温和上涨」）。
ns = mutate("pt == 'accel_up' and vt in ('squeeze', 'stable')",
            "pt == 'up' and vt in ('squeeze', 'stable')", '阶段2 判据 accel_up→up')
if ns:
    mut_rs = ns['reflexivity_stage']
    caught = mut_rs('accel_up', 'squeeze') != 'stage2'  # 正确版 accel_up+squeeze 应 stage2
    ck(caught, 'B2 变异被抓住（判据放宽 → 加速上涨被漏判为阶段1）')

# B3 变异阶段4 判据：crash → down（把「崩溃」放宽为「温和下跌」）。
ns = mutate("pt == 'crash'", "pt == 'down'", '阶段4 判据 crash→down')
if ns:
    mut_rs = ns['reflexivity_stage']
    caught = mut_rs('down', 'stable') != 'stage1'  # 正确版 温和下跌应 stage1，变异版误判 stage4
    ck(caught, 'B3 变异被抓住（判据放宽 → 温和下跌被误判为崩溃）')

print('')
if fails:
    print('FAIL %d/%d 组断言失败：' % (len(fails), total[0]))
    for m in fails:
        print('  - %s' % m)
    sys.exit(1)
print('全部 %d 组断言通过（含 %d 个变异测试）。' % (total[0], 3))
