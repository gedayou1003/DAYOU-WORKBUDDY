# -*- coding: utf-8 -*-
"""聚合测试入口（2026-09-21 建）—— 一次跑完全部 test_*.py。

为什么需要它：
  在此之前测试只能一个个手动跑，后果是 **test_layout_typography.py 连红两天无人发现**
  （原因是该测试的「since 未到」断言用了 TODAY，2026-09-19 日历越过规则生效起点后
   前提永久失效 —— 见该文件 §4 的修复注释）。
  **没有聚合入口的测试体系 ≈ 没有测试体系**：单点测试会随日历、环境、数据静默腐烂。

用法：
    $PY .workbuddy/run_tests.py                        # 全部
    $PY .workbuddy/run_tests.py --for check_integrity   # 改哪个脚本就跑哪个的对口测试（推荐）
    $PY .workbuddy/run_tests.py --audit                 # 自检映射表（孤儿测试/死 key/死脚本）
    $PY .workbuddy/run_tests.py --only layout           # 只跑名字含 layout 的
    $PY .workbuddy/run_tests.py -v                      # 失败时多打几行尾部输出

⚠️ 解释器：$PY 必须是装了 pandas 的 venv 解释器（`.../envs/default/Scripts/python.exe`），
  部分测试（如 test_degrade_exitcodes 的 analyze_000001_multi 段）import pandas，
  用裸解释器跑会 ModuleNotFoundError。本脚本会在启动时检测并显式提示。

退出码：0 全部通过 · 1 有失败（可直接接进闸门）

2026-09-21 修：原先用 `capture_output=True`，**只收 stdout、把 stderr 丢掉**。
测试脚本一旦抛异常，traceback 全在 stderr —— 于是闸门只留下「输出写了几行就断了」
这种线索，最有用的一行反而看不到（test_chain_apply 的偶发红就是这样被藏了一整轮）。
现改为 `stderr=STDOUT` 合并捕获。
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
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PER_TEST_TIMEOUT = 300   # 秒；单个测试卡死不应拖住整套


# ---------------------------------------------------------------------------
# 「改哪个脚本，就跑哪个脚本的对口测试」映射（2026-09-28 建）。
#
# 为什么要有这张表：改完代码后全量跑 21 个测试既慢又贵（且历史上全量跑被 SIGTERM），
# 而「只跑对口的那 1~3 个」才是性价比最高的回归。键 = .workbuddy 下的脚本名（去 .py），
# 值 = 该脚本改动会影响到的 test_*.py。
#
# 维护规则（防映射腐烂，与 check_integrity 白名单同一套纪律）：
#   · 新增脚本且有对应对口测试 → 必须在这里加一行；
#   · 新增测试 → 必须挂到某个脚本名下，否则它会成为「孤儿测试」（--audit 会报）；
#   · 改映射后跑一次 `run_tests.py --audit` 自检。
# ---------------------------------------------------------------------------
SCRIPT_TO_TESTS = {
    'check_integrity': ['test_check_integrity_neg.py', 'test_degrade_exitcodes.py'],
    'check_layout': ['test_check_layout_basis.py', 'test_layout_typography.py',
                     'test_degrade_exitcodes.py'],
    'layout_spec': ['test_layout_typography.py'],
    'chain_apply': ['test_chain_apply.py'],
    'chainlib': ['test_chain_apply.py', 'test_degrade_exitcodes.py'],
    'fetch_zsxq': ['test_fetch_snapshot.py', 'test_arg_guard.py', 'test_degrade_exitcodes.py'],
    'get_daily_ohlc': ['test_arg_guard.py'],
    'gen_tj_archive': ['test_tj_guard.py', 'test_gen_tj_archive.py'],
    'scan_ths': ['test_scan_ths_guard.py'],
    'display_names': ['test_display_name_guard.py'],
    'check_display_name': ['test_display_name_guard.py'],
    'gen_forecast_svg': ['test_gen_forecast_svg.py', 'test_gen_forecast_svg_neg.py',
                         'test_svg_date_mismatch.py'],
    'dragonball_signals': ['test_dragonball_signals.py'],
    'dragonball_narrative': ['test_dragonball_narrative.py'],
    'normalize_chain': ['test_normalize_chain.py'],
    'backfill_actual_data': ['test_backfill_actual.py'],
    'audit_pipeline': ['test_audit_detector.py', 'test_audit_docrot_neg.py'],
    'recycle_smoke_tmp': ['test_recycle_smoke_tmp.py'],
    'forecast_analyze': ['test_degrade_exitcodes.py'],
    'check_cookie': ['test_degrade_exitcodes.py'],
    'anonymize_report': ['test_degrade_exitcodes.py'],
    'run_morning_report': ['test_run_morning_report.py'],
    # 以下脚本目前**无独立回归测试**（改它们只有 py_compile + --help 弱验证）：
    #   calc_tech / calc_tech_multi / scan_sw_realtime
    # calc_turn_score 有内置 --selftest（无独立 test 文件）
}


def _resolve_script(name):
    """把 --for 的输入解析成映射 key。返回 key 或 None（带 stderr 诊断）。"""
    key = name[:-3] if name.endswith('.py') else name
    if key in SCRIPT_TO_TESTS:
        return key
    # 模糊兜底：唯一子串匹配（如 'check_integrity.py' 已去 .py；'integrity' → check_integrity）
    cands = [k for k in SCRIPT_TO_TESTS if key in k or k in key]
    if len(cands) == 1:
        return cands[0]
    if cands:
        sys.stderr.write('[FAIL] --for %r 命中多个脚本，请精确：%s\n'
                         % (name, '、'.join(sorted(cands))))
    else:
        sys.stderr.write('[FAIL] --for %r 没有对口测试映射。可用脚本名：\n  %s\n'
                         % (name, '、'.join(sorted(SCRIPT_TO_TESTS))))
    return None


def cmd_audit_map():
    """映射自检（闸门的闸门）：孤儿测试 / 死 key / 死脚本 三查。

    映射表是「改哪跑哪」的唯一依据，它自己会腐烂，必须能被检查：
      · 孤儿测试：磁盘有 test_*.py 但没挂到任何脚本名下 → 映射不完整；
      · 死 key：映射引用了磁盘上不存在的测试 → 映射过期；
      · 死脚本：映射 key 对应的 .py 脚本已不存在 → 键失效。
    """
    avail_tests = set(os.path.basename(p) for p in glob.glob(os.path.join(HERE, 'test_*.py')))
    referenced = set()
    for ts in SCRIPT_TO_TESTS.values():
        referenced.update(ts)
    orphan = sorted(avail_tests - referenced)
    dead_key = [(k, [t for t in ts if t not in avail_tests])
                for k, ts in SCRIPT_TO_TESTS.items()
                if any(t not in avail_tests for t in ts)]
    dead_script = [k for k in SCRIPT_TO_TESTS
                   if not os.path.exists(os.path.join(HERE, k + '.py'))]
    print('映射自检：%d 个脚本名 → %d 个测试（磁盘共 %d 个 test_*.py）'
          % (len(SCRIPT_TO_TESTS), len(referenced), len(avail_tests)))
    problems = 0
    if orphan:
        print('  [X] 孤儿测试 %d 个（磁盘有、映射未挂，需补挂到某脚本名下）：%s'
              % (len(orphan), '、'.join(orphan)))
        problems += 1
    else:
        print('  [OK] 无孤儿测试（%d 个测试全部被映射引用）' % len(avail_tests))
    if dead_key:
        for k, ts in dead_key:
            print('  [X] 死 key %s → 引用了不存在的测试：%s' % (k, '、'.join(ts)))
        problems += 1
    else:
        print('  [OK] 无死 key（映射引用的测试全部存在）')
    if dead_script:
        print('  [X] 死脚本 %d 个（映射 key 对应的 .py 已不存在）：%s'
              % (len(dead_script), '、'.join(dead_script)))
        problems += 1
    else:
        print('  [OK] 无死脚本（映射 key 对应的脚本全部存在）')
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='聚合测试入口（只读，不改任何文件）')
    ap.add_argument('--only', default=None, metavar='SUBSTR',
                    help='只跑文件名包含该子串的测试')
    ap.add_argument('--files', default=None, metavar='LIST',
                    help='只跑指定的测试文件名，逗号分隔（供 gate.py fast 级用；'
                         '与 --only 的区别是**精确指定**而非子串匹配）')
    ap.add_argument('--for', dest='for_script', default=None, metavar='SCRIPT',
                    help='改哪个脚本就跑哪个的对口测试（如 check_integrity / gen_forecast_svg）；'
                         '这是「改完代码跑对口回归」的默认动作，避免全量跑')
    ap.add_argument('--audit', action='store_true', help='自检映射表（孤儿测试/死 key/死脚本）')
    ap.add_argument('-v', '--verbose', action='store_true', help='失败时多打尾部输出')
    a = ap.parse_args(argv)

    if a.audit:
        return cmd_audit_map()

    # 解释器自检（2026-09-28 踩坑）：部分测试 import pandas，裸解释器会 ModuleNotFoundError。
    # 报在**跑测试之前**，避免「跑了半天结果一排 FAIL」才意识到用错解释器。
    try:
        import pandas  # noqa: F401
    except ImportError:
        _hint = os.path.expanduser('~/.workbuddy/binaries/python/envs/default/Scripts/python.exe')
        print('[WARN] 当前解释器无 pandas（%s）。依赖 pandas 的测试会 ModuleNotFoundError。'
              % sys.executable)
        print('       请改用装了 pandas 的 venv 解释器：%s' % _hint)
        print('       本次仍继续跑不依赖 pandas 的测试。\n')

    tests = sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, 'test_*.py')))
    if a.for_script:
        key = _resolve_script(a.for_script)
        if key is None:
            return 1
        tests = SCRIPT_TO_TESTS[key]
        print('脚本 %s → 对口测试 %d 个：%s'
              % (key, len(tests), '、'.join(tests)))
    elif a.files:
        want = [x.strip() for x in a.files.split(',') if x.strip()]
        missing = [w for w in want if w not in tests]
        if missing:
            # 拼错文件名会导致"跑了 0 个但报通过"—— 必须有意报错
            sys.stderr.write('[FAIL] --files 里有不存在的测试：%s\n' % '、'.join(missing))
            return 1
        tests = [t for t in tests if t in want]
    elif a.only:
        tests = [t for t in tests if a.only in t]
    if not tests:
        sys.stderr.write('[FAIL] 没有匹配的测试（--only %r / --files %r / --for %r）\n'
                         % (a.only, a.files, a.for_script))
        return 1

    print('=' * 62)
    print('聚合测试 · %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    print('共 %d 个测试文件' % len(tests))
    print('=' * 62)

    bad, total_t0 = [], time.time()
    for t in tests:
        t0 = time.time()
        try:
            r = subprocess.run([PY, os.path.join(HERE, t)], cwd=HERE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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
                # 25 行而不是 8 行：traceback + 最后几条断言才够定位（8 行时 traceback 会被截掉）
                for ln in out.splitlines()[-25:]:
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
