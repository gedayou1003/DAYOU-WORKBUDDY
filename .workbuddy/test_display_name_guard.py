# -*- coding: utf-8 -*-
"""check_display_name 假绿回归（闸门的闸门）。

为什么必须有这个测试（2026-09-23 加固）
-------------------------------------
旧实现读文件失败就 `continue` —— **不计数、不上报**；main() 在无命中时打印
「OK 对外产物与生成链路零泄漏」。于是「一个文件都没读成」与「读了 200 个文件、
确实干净」**输出一字不差**、退出码都是 0。本脚本是**安全守卫**（对外显示名泄漏），
证据缺失被当成通过 = 泄漏了也没人知道。

本测试用合成沙箱（不碰真实仓库、临时目录均在系统 temp）双向证明：
  · 读到 0 个文件 → 必须 rc≠0 且措辞为「无结论」（该红的必须红）
  · 干净目录     → rc=0 且明确写「全读通、零泄漏」（该绿的不许红）
  · 有泄漏       → rc=1 并列出命中文件
  · 证据缺失时**不许**出现「零泄漏」字样（假绿的实质是那句结论）

用法：$PY .workbuddy/test_display_name_guard.py
"""
import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('cdn', os.path.join(HERE, 'check_display_name.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def run(root):
    """在指定 ROOT 下跑 main()，返回 (rc, 输出)。ROOT 用打桩注入，跑完还原。"""
    old = m.ROOT
    m.ROOT = root
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = m.main([])
    finally:
        m.ROOT = old
    return rc, buf.getvalue()


def sandbox(files):
    d = tempfile.mkdtemp(prefix='cdnguard_')
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(body)
    return d


tmpdirs = []
try:
    # ── ① 假绿回归：读通 0 个文件时不许报 OK ─────────────────────────
    print('1) 读通 0 个文件（旧实现此处报「零泄漏 OK」并退出 0）')
    d = sandbox({})
    tmpdirs.append(d)
    rc, out = run(d)
    ck(rc == 1, '空目录 → rc=1（旧实现 rc=0）')
    ck('[FAIL]' in out, '输出含 [FAIL]，明示「本次检查无结论」')
    ck('零泄漏' not in out, '证据缺失时**不许**出现「零泄漏」字样（假绿的实质就是那句结论）')

    # ── ② 干净目录：该绿的不许红，且必须打得出「扫了几个文件」 ─────────
    print('\n2) 干净目录（对照：证明收紧后没有误红）')
    d = sandbox({'rep.md': '这是一份不含敏感显示名的报告\n'})
    tmpdirs.append(d)
    rc, out = run(d)
    ck(rc == 0, '干净文件 → rc=0')
    ck('OK' in out and '零泄漏' in out, '结论明确写「全读通、零泄漏」')
    ck('扫描 1 个文件' in out, '打印扫描文件数（「0 个」与「N 个」从此可区分）')

    # ── ③ 真泄漏：必须红且指得出文件 ────────────────────────────────
    print('\n3) 真泄漏（证明收紧后闸门仍然咬得住）')
    d = sandbox({'rep.md': '来源：T&J 星球\n', 'sub/deep.html': '<p>Truth and Justice</p>\n'})
    tmpdirs.append(d)
    rc, out = run(d)
    ck(rc == 1, '有泄漏 → rc=1')
    ck('rep.md' in out and os.path.join('sub', 'deep.html') in out, '两个命中文件都被列出')

    # ── ④ 白名单与 `_` 前缀中间件不算命中（反向用例，防放水过度） ─────
    print('\n4) 反向：白名单文件 / `_` 前缀中间产物 → 不报')
    d = sandbox({'display_names.py': 'T&J = "T&J"\n', '_tech_2026-09-23.json': 'T&J\n',
                 'clean.md': '无敏感词\n'})
    tmpdirs.append(d)
    rc, out = run(d)
    ck(rc == 0, '白名单与中间产物命中不算问题 → rc=0')
    ck('白名单跳过' in out, '汇总行如实报告白名单跳过数')
finally:
    for d in tmpdirs:
        shutil.rmtree(d, ignore_errors=True)

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
