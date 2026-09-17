# -*- coding: utf-8 -*-
"""负例验证：把 gen_forecast_svg.py 逐个回退成「静默兜底」旧行为，跑回归测试，每次都应被拦下。

做法：对**每一个**变异点，从正本重新出发只注入这一处，单独跑一遍回归测试。
期望每个变异体都 rc!=0 且至少 1 条 FAIL —— 这样才证明 test_gen_forecast_svg.py
里的断言是真的在拦回归，而不是恒 PASS 的装饰。

只读正本、只写临时副本，不碰仓库文件。
用法：python .workbuddy/_neg_test_gen_forecast_svg.py
退出码：0 全部变异被拦下（测试有效）/ 1 有变异溜过（测试有洞）
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SRC = os.path.join(HERE, 'gen_forecast_svg.py')
TEST = os.path.join(HERE, 'test_gen_forecast_svg.py')

MUTS = [
    ('M1 无 pending 时静默兜底（旧版行为）',
     "        if not pend:\n"
     "            raise SystemExit(\n"
     "                '[FAIL] 预判链中没有任何 pending 记录，无法确定本期预判。\\n'\n"
     "                '       请先跑 chain_apply 落链（追本期预判），或用 --pred <id> 指定历史记录重绘。')\n"
     "        p = pend[-1]",

     "        if not pend:\n"
     "            p = {'id': 'MUTANT', 'levels': {'date': '2026-08-31', 'now': 3900,\n"
     "                 'decision': {'price': 3910, 'label': 'x'},\n"
     "                 'up_target': {'price': 3960, 'label': 'y'},\n"
     "                 'down_support': {'price': 3880, 'label': 'z'},\n"
     "                 'down_lower': {'price': 3850, 'label': 'w'}}}\n"
     "        else:\n"
     "            p = pend[-1]"),

    ('M2 levels 残缺时直接放行',
     "    if not isinstance(lv, dict) or not all(k in lv for k in need):\n"
     "        raise SystemExit('[FAIL] %s 的 levels 不完整（需含 %s），无法绘图。'\n"
     "                         % (rid, ' / '.join(need)))",

     "    if not isinstance(lv, dict):\n"
     "        lv = {}"),

    ('M3 缺 verified.actual 时编造假数据',
     "    if act is None:\n"
     "        raise SystemExit('[FAIL] 链中找不到含 open/high/low/close 的 verified.review.actual，'\n"
     "                         '走势图无法叠加真实走势。\\n'\n"
     "                         '       请先完成上一条的复盘（chain_apply 的 review 段）再生成图。')",

     "    if act is None:\n"
     "        act = {'open': 3895.0, 'high': 3920.0, 'low': 3885.0, 'close': 3905.0}"),

    ('M4 缺 date 时退化成写死 2026-08-31',
     "        d = lv.get('date', '')\n"
     "        if not d:\n"
     "            raise SystemExit(\n"
     "                '[FAIL] %s 的 levels 缺少 date 字段，推不出默认输出文件名。\\n'\n"
     "                '       请用 --out <路径.svg> 显式指定输出。' % rid)\n"
     "        d = str(d).replace('/', '-')",

     "        d = lv.get('date', '') or '2026-08-31'\n"
     "        d = str(d).replace('/', '-')"),

    ('M5 坏 --pred 不报错、静默取最后一条 pending',
     "        cand = [r for r in chain if r.get('id') == pred_id]\n"
     "        if not cand:\n"
     "            raise SystemExit('[FAIL] 链中找不到记录 id=%s' % pred_id)\n"
     "        p = cand[0]",

     "        cand = [r for r in chain if r.get('id') == pred_id]\n"
     "        if not cand:\n"
     "            cand = [r for r in chain if r.get('status') == 'pending']\n"
     "        p = cand[0]"),
]


def run_mutant(mut_code):
    """把变异体写成临时文件，以 FSVG_SCRIPT 指向它跑一遍回归测试。"""
    d = tempfile.mkdtemp(prefix='wbneg_fsvg_')
    try:
        mut = os.path.join(d, 'gen_forecast_svg_mutated.py')
        with open(mut, 'w', encoding='utf-8') as f:
            f.write(mut_code)
        env = dict(os.environ, FSVG_SCRIPT=mut)
        r = subprocess.run([PY, TEST], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=env, cwd=HERE)
        out = (r.stdout or '') + (r.stderr or '')
        n_fail = sum(1 for ln in out.splitlines()
                     if ln.strip().startswith('FAIL ') or ' FAIL ' in ln)
        return r.returncode, n_fail, out
    finally:
        shutil.rmtree(d, ignore_errors=True)


print('=== 负例验证：test_gen_forecast_svg.py 是否真的在拦回归 ===')
print('')

with open(SRC, encoding='utf-8') as f:
    pristine = f.read()

missed = []
for name, old, new in MUTS:
    if old not in pristine:
        print('SKIP  %s —— 变异点未匹配（脚本已改动，请同步本文件）' % name)
        missed.append(name + '（变异点失配，无法验证）')
        continue
    rc, n_fail, out = run_mutant(pristine.replace(old, new, 1))
    caught = (rc != 0 and n_fail >= 1)
    print('%s  %s → rc=%d, FAIL=%d' % ('CAUGHT' if caught else 'MISSED', name, rc, n_fail))
    if caught:
        for ln in out.splitlines():
            if ' FAIL ' in ln:
                print('          %s' % ln.strip())
    else:
        missed.append(name)

print('')
if missed:
    print('有 %d 处变异溜过，测试存在空洞：' % len(missed))
    for m in missed:
        print('  - %s' % m)
    sys.exit(1)
print('全部 %d 处变异均被拦下 —— 回归测试有效。' % len(MUTS))
sys.exit(0)
