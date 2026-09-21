# -*- coding: utf-8 -*-
"""文档腐烂判定的**变异测试**（闸门的闸门）。

为什么必须有：
  2026-09-21 把「文档腐烂」从「文件名出现即算」改成四分类（stale / missing / explained / external），
  这是一次**降噪**。而项目在 M-9 上刚吃过教训：降噪很容易顺手把闸门一起关掉 ——
  判定一放宽，`test_audit_detector.py` 照样全绿，谁也看不出来它已经不再报了。
  故按 `test_gen_forecast_svg_neg.py` 的同款做法：**逐处把判定改回坏行为，验证自检真的会红**。

  本测试同时跑一个**对照组**（未变异的源码 + 同一份自检 = 必须 rc 0），
  否则「变异后 rc≠0」可能只是因为沙箱本身起不来（假红）。

用法：$PY .workbuddy/test_audit_docrot_neg.py
退出码：0 全部变异都被拦下且对照组全绿 / 1 有变异溜过或对照组本身不绿
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(errors='replace') if hasattr(sys.stdout, 'reconfigure') else None

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'audit_pipeline.py')
TEST = os.path.join(HERE, 'test_audit_detector.py')
PY = sys.executable

# (编号, 说明, 锚点原文, 替换为)  —— 每处都对应一类「闸门失效」
MUTATIONS = [
    ('M1', '关掉「已交代归档」抑制（explained 永不成立）',
     'mk = EXPLAINED.search(ln)',
     'mk = None'),
    ('M2', '退回「按文件去重、只看第一处出现」',
     'bad = next((it for it in items if not it[2] and not it[3]), None)',
     'bad = next((it for it in items[:1] if not it[2] and not it[3]), None)'),
    ('M3', '_resolve 变成万能白名单（声明即通过）',
     'return any(os.path.exists(c) for c in cands)',
     'return True'),
    ('M4', '丢掉行号（告警无法定位）',
     "                detail = 'L%d' % bad[0]",
     "                detail = ''"),
    ('M5', '不再区分已归档/真不存在（stale 恒空）',
     '(stale if arch else missing).append((fn, d, detail))',
     'missing.append((fn, d, detail))'),
]


def run_pair(pipe_src):
    """把（可能变异的）audit_pipeline.py 与自检放进同一临时目录跑，返回 (rc, 输出)。"""
    d = tempfile.mkdtemp(prefix='audit_docrot_neg_')
    try:
        with open(os.path.join(d, 'audit_pipeline.py'), 'w', encoding='utf-8') as fh:
            fh.write(pipe_src)
        shutil.copy2(TEST, os.path.join(d, 'test_audit_detector.py'))
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        p = subprocess.run([PY, os.path.join(d, 'test_audit_detector.py')],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', env=env, cwd=d)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    finally:
        shutil.rmtree(d, ignore_errors=True)


fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


base = open(SRC, encoding='utf-8').read()

# ── 对照组：未变异必须全绿 ──────────────────────────────────────────
print('0) 对照组（未变异 → 自检必须全绿）')
rc0, out0 = run_pair(base)
ck(rc0 == 0 and 'ALL PASS' in out0, '未变异源码 → 自检 ALL PASS（rc=%s）' % rc0)
if rc0 != 0:
    print('  对照输出尾部：\n%s' % out0[-1500:])

# ── 逐处注入变异 ────────────────────────────────────────────────────
print('\n1) 变异注入（每一处都必须被自检拦下）')
for mid, why, old, new in MUTATIONS:
    if old not in base:
        ck(False, '%s 锚点未找到（源码已改？需同步更新本测试）：%s' % (mid, old[:60]))
        continue
    mutated = base.replace(old, new, 1)
    # 守卫：确认变异**真的生效**了。否则会得到「修复无效」的假红
    # （踩过：非贪婪正则只替换了一半，变异没落地却被读成闸门失效）。
    ck(old not in mutated and new in mutated,
       '%s 变异已生效（锚点已消失）' % mid)
    rc, out = run_pair(mutated)
    ck(rc != 0, '%s %s → 自检被拦下（rc=%s）' % (mid, why, rc))
    if rc == 0:
        print('      ⚠️ 溜过：变异后自检仍全绿，说明这条判定没有断言覆盖')

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
