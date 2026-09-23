# -*- coding: utf-8 -*-
"""scan_ths 缩水守卫的「证据缺失」回归（2026-09-23 加固）。

背景
----
缩水守卫的职责：本轮行业成功条数若较上次大幅缩水，就**不覆盖主结果**
（防止一次残缺抓取冲掉完整结果）。它的输入来自上次结果文件。

旧实现读不动该文件就 `return None`，而调用点写的是 `if old_n and results_ths and ...`
—— 于是**缓存损坏时缩水守卫静默失效**，残缺结果照样覆盖完整主结果。
「文件不存在」（首次运行，本就无从比较）与「文件在但读不动」（证据损坏）必须分开，
后者要把原因带出去由调用点记降级。

本测试用沙箱文件证明这个区分，并守住「调用点确实把原因接进了 degraded」的契约。

用法：$PY .workbuddy/test_scan_ths_guard.py
"""
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('st', os.path.join(HERE, 'scan_ths.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


sb = tempfile.mkdtemp(prefix='scan_ths_guard_')
saved = m.CACHE
try:
    print('1) 三种文件状态 → 三种结论（「没有上次结果」≠「上次结果读不动」）')
    m.CACHE = os.path.join(sb, 'absent.json')
    ck(m._shrink_guard() == (None, None), '缓存不存在 → (None, None)：首次运行，无从比较、不算问题')

    m.CACHE = os.path.join(sb, 'broken.json')
    with open(m.CACHE, 'w', encoding='utf-8') as f:
        f.write('{ 这不是合法 JSON')
    n, note = m._shrink_guard()
    ck(n is None and note and '读不动' in note, '缓存损坏 → 带出原因：%s' % note)

    m.CACHE = os.path.join(sb, 'ok.json')
    with open(m.CACHE, 'w', encoding='utf-8') as f:
        json.dump({'ths': [1, 2, 3]}, f)
    ck(m._shrink_guard() == (3, None), '缓存正常 → (3, None)：缩水守卫拿到可比基线')

    m.CACHE = os.path.join(sb, 'empty.json')
    with open(m.CACHE, 'w', encoding='utf-8') as f:
        json.dump({}, f)
    ck(m._shrink_guard() == (0, None), '缓存合法但无 ths 字段 → (0, None)（0 会被调用点当假值，属原口径）')

    print('\n2) 契约守卫：调用点必须把原因接进降级（否则等于白带出来）')
    src = io.open(os.path.join(HERE, 'scan_ths.py'), encoding='utf-8').read()
    # 只看代码区，避免 docstring 里的说明被当命中（本项目的老坑）
    code = '\n'.join(ln.split('#')[0] for ln in src.split('\n'))
    ck(re.search(r'old_n,\s*guard_note\s*=\s*_shrink_guard\(\)', code) is not None,
       'main() 解包 (old_n, guard_note)')
    ck(re.search(r'if guard_note:\s*\n\s*degraded\.append\(guard_note\)', code) is not None,
       'guard_note 非空 → degraded（降级 = 不覆盖主结果）')
    ck('_old_ths_count' not in code, '旧函数 _old_ths_count 已彻底移除（不留两套口径）')
finally:
    m.CACHE = saved
    shutil.rmtree(sb, ignore_errors=True)

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
