# -*- coding: utf-8 -*-
"""回收工具的合成验证：造 4 个假 run 目录（含 1 个超大），验证
  ① 默认 dry-run 一个字都不删；
  ② --keep N 只保留最近 N 个；
  ③ 超大目录被跳过（不硬删）；
  ④ 不合命名的目录**绝不被碰**（护栏）。
全程在临时目录里做，不碰真实 .workbuddy/_smoke_tmp。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
TOOL = os.path.join(HERE, 'recycle_smoke_tmp.py')
FAILS = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        FAILS.append(msg)


def run(*args):
    p = subprocess.run([PY, TOOL] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


root = tempfile.mkdtemp(prefix='recycle_')
names = ['run_20260901_100000', 'run_20260902_100000',
         'run_20260903_100000', 'run_20260904_100000']
for n in names:
    d = os.path.join(root, n)
    os.makedirs(d)
    io.open(os.path.join(d, 'a.txt'), 'w', encoding='utf-8').write('x')
# 超大目录 → 必须被跳过（阈值 400）
big = os.path.join(root, 'run_20260905_100000')
os.makedirs(big)
for i in range(410):
    io.open(os.path.join(big, 'f%03d.txt' % i), 'w', encoding='utf-8').write('y')
# 不合命名 → 绝不能被碰
keepme = os.path.join(root, 'my_manual_backup')
os.makedirs(keepme)
io.open(os.path.join(keepme, 'important.txt'), 'w', encoding='utf-8').write('do not delete')

print('=== ① 默认 dry-run：一个字都不许删 ===')
rc, blob = run('--root', root)
# ⚠️ 退出码预期是 2 而非 0：本 fixture **故意**含一个 410 文件的超大目录，
# 而「有跳过/超标项就报 2」是设计（初版写成只看 skipped、漏了保留区间的超标项，
# 已被本文件的 ③ 组抓出并修好）。所以这里断言 2 —— 若断言 0，
# 就等于要求工具**对超标目录保持沉默**，那正是要修的 bug。
ck(rc == 2, '预演本身不删文件，但有超标项 → 退出码 2（实测 %d）' % rc)
ck(len(os.listdir(root)) == 6, '文件系统未变（仍有 6 个条目，实测 %d）' % len(os.listdir(root)))
ck('未删除任何东西' in blob or '预演' in blob, '输出须自述「未删除」')
ck('run_20260901_100000' in blob, '须列出待回收明细')

print('=== ② --apply --keep 3：保留最近 3 个，删更早的 ===')
rc, blob = run('--root', root, '--keep', '3', '--apply')
print('    rc=%d' % rc)
left = sorted(os.listdir(root))
ck('run_20260901_100000' not in left, '最早的 09-01 应被回收')
ck('run_20260902_100000' not in left, '09-02 应被回收')
ck('run_20260903_100000' in left, '最近的 09-03 应保留')
ck('run_20260904_100000' in left, '最近的 09-04 应保留')
ck('run_20260905_100000' in left, '超大目录应被跳过（不硬删）')
ck('my_manual_backup' in left, '⚠️ 不合命名的目录绝不能被碰（护栏）')
ck(os.path.exists(os.path.join(keepme, 'important.txt')), '护栏目录内的文件须完好')

print('=== ③ 超大目录须被明确报出（不能静默跳过）===')
# ⚠️ 本组暴露的**真 BUG**（初版实现）：「保留最近 N 次」把 kept 直接从候选集里剔掉，
# 于是**落在保留区间里的超大目录从不被检查** —— 既不在待删清单、也不被跳过逻辑看到，
# 等于静默豁免（实测：410 文件的 run 目录 + --keep 1 → 一句提示都没有，退出码还是 0）。
# 现在改成「全部扫描，只是保留项不删」；保留区间的超标项报进 frozen_big 并计入退出码。
ck('跳过' in blob or '超标' in blob, '输出须点明有跳过/超标项')
ck('run_20260905_100000' in blob, '须指名哪个目录被跳过/超标')
ck(rc == 2, '有跳过项 → 退出码 2（实测 %d）' % rc)

print('=== ④ --all：连最近的也回收（但超大与护栏仍不动）===')
rc, blob = run('--root', root, '--all', '--apply')
left = sorted(os.listdir(root))
ck('run_20260903_100000' not in left, '--all 下最近的 09-03 也应被回收')
ck('run_20260904_100000' not in left, '--all 下 09-04 也应被回收')
ck('run_20260905_100000' in left, '超大目录仍不动')
ck('my_manual_backup' in left, '护栏目录仍不动')

print('=== ⑤ 非法参数 ===')
rc, blob = run('--root', root, '--keep', '-1')
ck(rc == 1, '--keep 为负 → 退出码 1（实测 %d）' % rc)

print('=== ⑥ 目录不存在时不崩 ===')
rc, blob = run('--root', os.path.join(root, 'nosuch'))
ck(rc == 0, '不存在的根目录 → 0 且不崩（实测 %d）' % rc)

shutil.rmtree(root, ignore_errors=True)
print()
if FAILS:
    print('RESULT: FAIL（%d 条）' % len(FAILS))
    for m in FAILS:
        print('  -', m)
    sys.exit(1)
print('RESULT: ALL PASS')
