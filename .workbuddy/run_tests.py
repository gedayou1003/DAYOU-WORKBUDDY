# -*- coding: utf-8 -*-
"""聚合测试入口（2026-09-21 建）—— 一次跑完全部 test_*.py。

为什么需要它：
  在此之前测试只能一个个手动跑，后果是 **test_layout_typography.py 连红两天无人发现**
  （原因是该测试的「since 未到」断言用了 TODAY，2026-09-19 日历越过规则生效起点后
   前提永久失效 —— 见该文件 §4 的修复注释）。
  **没有聚合入口的测试体系 ≈ 没有测试体系**：单点测试会随日历、环境、数据静默腐烂。

用法：
    $PY .workbuddy/run_tests.py                 # 全部
    $PY .workbuddy/run_tests.py --only layout   # 只跑名字含 layout 的
    $PY .workbuddy/run_tests.py -v              # 失败时多打几行尾部输出

退出码：0 全部通过 · 1 有失败（可直接接进闸门）
"""
import argparse
import glob
import os
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PER_TEST_TIMEOUT = 300   # 秒；单个测试卡死不应拖住整套


def main(argv=None):
    ap = argparse.ArgumentParser(description='聚合测试入口（只读，不改任何文件）')
    ap.add_argument('--only', default=None, metavar='SUBSTR',
                    help='只跑文件名包含该子串的测试')
    ap.add_argument('-v', '--verbose', action='store_true', help='失败时多打尾部输出')
    a = ap.parse_args(argv)

    tests = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, 'test_*.py')))
    if a.only:
        tests = [t for t in tests if a.only in t]
    if not tests:
        sys.stderr.write('[FAIL] 没有匹配的测试（--only %r）\n' % a.only)
        return 1

    print('=' * 62)
    print('聚合测试 · %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    print('共 %d 个测试文件' % len(tests))
    print('=' * 62)

    bad, total_t0 = [], time.time()
    for t in tests:
        t0 = time.time()
        try:
            r = subprocess.run([PY, os.path.join(HERE, t)], cwd=HERE, capture_output=True,
                               text=True, encoding='utf-8', errors='replace',
                               timeout=PER_TEST_TIMEOUT,
                               env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            rc, out, timed_out = r.returncode, (r.stdout or ''), False
        except subprocess.TimeoutExpired as e:
            rc, out, timed_out = 124, (e.stdout or '') if isinstance(e.stdout, str) else '', True
        dt = time.time() - t0

        mark = 'OK  ' if rc == 0 else ('TIME' if timed_out else 'FAIL')
        print('  [%s] %-30s rc=%-3d %5.1fs' % (mark, t, rc, dt))
        if rc != 0:
            bad.append((t, rc, timed_out))
            if a.verbose or timed_out:
                for ln in out.splitlines()[-8:]:
                    print('         ' + ln)

    dt_all = time.time() - total_t0
    print('-' * 62)
    if bad:
        print('RESULT: FAIL %d / %d 个测试（耗时 %.1fs）' % (len(bad), len(tests), dt_all))
        for t, rc, to in bad:
            print('  · %s（rc=%d%s）' % (t, rc, '，超时' if to else ''))
        print('\n排查建议：先看该测试是否依赖「今天」——日期相关断言在日历越过阈值后会自坏。')
    else:
        print('RESULT: ALL PASS（%d 个测试，耗时 %.1fs）' % (len(tests), dt_all))
    print('=' * 62)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
