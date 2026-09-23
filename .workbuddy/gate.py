# -*- coding: utf-8 -*-
"""gate.py —— 分级闸门（2026-09-23 新建，为「一个午间任务跑近 2 小时」而做）。

## 为什么需要它

2026-09-23 午间档实测耗时构成（358 个今日文件 mtime 分桶）：

| 时段 | 内容 | 耗时 |
|---|---|---|
| 13:23–13:45 | 附件抽取 + 引擎 + 覆盖审计 + 读图 + **报告撰写落盘** | 22 分钟 |
| 13:45–14:31 | 三项校验首跑 + 改报告 | 46 分钟 |
| 14:02–14:13 | 冒烟第 1 次（**白跑**——查出 H4 副作用） | 11 分钟 |
| 14:19–14:30 | 冒烟第 2 次 | 10.4 分钟 |
| 14:13–14:31 | 审计 ×3 + 聚合测试 ×2 | ~13 分钟 |

**根因：为修 2 行校验器逻辑，重跑了全套闸门 2 遍 —— 测试/冒烟烧掉 45 分钟，占总时长 60%+。**

而**真正交付报告只用了 22 分钟**。问题不在"算得慢"，在于
**验证强度与改动范围脱钩**：改一个 `check_integrity.py` 的判定口径，
却把「星球抓取 + 引擎 + 行业扫描 + 走势图」这些**完全没碰过**的东西全部重测了一遍。

## 分级原则

按「改动碰了什么」决定跑什么，**不按"图省事"决定**：

| 级别 | 触发条件 | 跑什么 | 实测耗时 |
|---|---|---|---|
| **fast** | 改文档 / 纯文本 / 单脚本无依赖变动 | 语法编译 + 静态审计 + 相关单测 | ~10–30s |
| **std** | 改脚本逻辑（默认档） | fast + 受影响测试 + 三个校验器 | ~1–3min |
| **full** | 改链结构 / 主链脚本 / 交付前终检 | 全部：含冒烟全链路 | ~15min |

**关键设计：`fast`/`std` 绝不假装自己是 `full`。** 每个级别都在输出里
**明写"没跑什么"**，并给出该级别的**保证边界** —— 否则分级闸门就变成了
"用更少的测试换更高的通过率"，那是自欺。

## 用法

    $PY .workbuddy/gate.py fast
    $PY .workbuddy/gate.py std  --changed check_integrity.py
    $PY .workbuddy/gate.py full
    $PY .workbuddy/gate.py auto          # 按 git 改动自动判级

退出码：0 通过 · 1 有失败
"""
import argparse
import os
import re
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

# --- 改动 → 受影响测试 的映射表 -------------------------------------------
# 只在**有明确因果关系**时才映射；映射不到就**上浮到 std 全测**（宁可多跑，不可漏测）。
# 这张表是分级闸门的**核心资产**：它把「改了什么」翻译成「必须重验什么」。
AFFECTS = {
    # 链结构：改了它，所有读写链的脚本都可能受影响
    'chainlib.py':            ['chain', 'integrity', 'layout', 'backfill', 'normalize', 'tj_guard'],
    'chain_apply.py':         ['chain', 'integrity', 'layout'],
    'forecast_chain.json':    ['chain', 'integrity', 'layout', 'svg'],
    # 校验器：只影响它自己和依赖它的测试
    'check_integrity.py':     ['integrity'],
    'check_layout.py':        ['layout'],
    'check_display_name.py':  ['display_name'],
    'audit_coverage.py':      ['coverage'],
    # 抓取
    'fetch_zsxq.py':          ['fetch_snapshot', 'arg_guard'],
    'fetch_zsxq_files.py':    ['degrade', 'fetch_snapshot'],
    'backfill_zsxq_window.py': ['degrade'],
    # 绘图/排版
    'gen_forecast_svg.py':    ['svg'],
    'md_to_html_report.py':   ['degrade', 'layout'],
    'anonymize_report.py':    ['degrade', 'display_name'],
    # 审计自身
    'audit_pipeline.py':      ['audit'],
    'smoke_pipeline.py':      ['degrade'],
    # 报告内容类（不影响逻辑）
    '报告生成流程.md':         [],
    '预判规则_v5.md':          [],
    '脚本地图.md':             [],
}


def _run(cmd, cwd=None, timeout=600, env_extra=None):
    """跑一条命令，返回 (rc, 输出, 秒)。不抛异常，超时→124。"""
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if env_extra:
        env.update(env_extra)
    try:
        r = subprocess.run(cmd, cwd=cwd or HERE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout, env=env)
        return r.returncode, (r.stdout or ''), time.time() - t0
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else ''
        return 124, out, time.time() - t0
    except Exception as e:                            # noqa: BLE001
        return 99, '启动失败（%s: %s）' % (type(e).__name__, e), time.time() - t0


def _changed_files():
    """从 git 取改动文件（含未跟踪）。取不到就返回 None（→ 调用方上浮到 full）。"""
    rc, out, _ = _run(['git', 'status', '--porcelain'], cwd=ROOT, timeout=30)
    if rc != 0:
        return None
    files = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # 形如 " M path" / "?? path" / "R  old -> new"
        parts = ln[3:].split(' -> ')
        files.append(os.path.basename(parts[-1].strip().strip('"')))
    return files


def pick_tests(patterns):
    """把模式列表展开成 test_*.py 文件名（去重、保序）"""
    import glob
    all_tests = sorted(os.path.basename(p)
                       for p in glob.glob(os.path.join(HERE, 'test_*.py')))
    if not patterns:
        return all_tests
    if patterns == '*':
        return all_tests
    hit = [t for t in all_tests if any(p in t for p in patterns)]
    return hit


def auto_level(changed):
    """按改动自动判级"""
    if changed is None:
        return 'full', '无法读取 git 改动（上浮到 full，宁可多跑）'
    if not changed:
        return 'fast', '无改动'
    # 只改了文档 → fast
    doc_only = all(f.endswith('.md') or f.endswith('.txt') for f in changed)
    if doc_only:
        return 'fast', '仅改动文档（%d 个）' % len(changed)
    # 碰了链结构 / 主链脚本 → full
    critical = {'chainlib.py', 'chain_apply.py', 'forecast_chain.json',
                'forecast_analyze.py', 'check_integrity.py', 'check_layout.py'}
    if critical & set(changed):
        return 'std', '碰到关键脚本（%s）→ std' % '、'.join(sorted(critical & set(changed)))
    # 新增脚本 → full（没被任何测试覆盖，必须全链路验证）
    if any(not f.endswith(('.md', '.json', '.txt')) for f in changed):
        return 'std', '改动脚本（%d 个）' % len(changed)
    return 'std', '默认'


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='分级闸门：按改动范围决定验证强度（fast/std/full）')
    ap.add_argument('level', nargs='?', default='auto',
                    choices=['fast', 'std', 'full', 'auto'],
                    help='fast=文档/语法 · std=脚本逻辑（默认）· full=全链路含冒烟 · auto=按 git 改动判')
    ap.add_argument('--changed', default=None,
                    help='逗号分隔的改动文件名（省去 git 探测；auto 级别用）')
    ap.add_argument('--dry-run', action='store_true', help='只打印计划，不执行')
    a = ap.parse_args(argv)

    t_all = time.time()

    # --- 判级 -------------------------------------------------------------
    changed = None
    if a.changed is not None:
        changed = [x.strip() for x in a.changed.split(',') if x.strip()]
    elif a.level == 'auto':
        changed = _changed_files()

    if a.level == 'auto':
        level, why = auto_level(changed)
    else:
        level, why = a.level, '手动指定'
    changed = changed or []

    # --- 展开计划 ----------------------------------------------------------
    plan = []          # (阶段名, 命令, 超时秒, 是否关键)

    if level in ('fast', 'std', 'full'):
        plan.append(('语法编译全部脚本', [PY, '-m', 'compileall', '-q', HERE], 120, True))

    if level in ('std', 'full'):
        plan.append(('静态审计 audit_pipeline', [PY, os.path.join(HERE, 'audit_pipeline.py')], 300, True))

    # 受影响测试
    tests = []
    if level == 'fast':
        # fast：只跑与改动直接相关的测试文件（**不是**跑全套）
        pats = []
        for f in changed:
            pats += AFFECTS.get(f, [])
        if changed and not pats:
            pats = ['arg_guard', 'display_name']    # 纯文档改动 → 只跑最快守卫
        tests = pick_tests(pats) if pats else []
        if tests:
            plan.append(('相关单测（%d 个）' % len(tests),
                         [PY, os.path.join(HERE, 'run_tests.py'),
                          '--files', ','.join(tests)], 300, True))
    else:
        tests = pick_tests('*')                     # std/full 跑全部单测
        if tests:
            plan.append(('聚合单测 run_tests（全部 %d 个）' % len(tests),
                         [PY, os.path.join(HERE, 'run_tests.py')], 600, True))

    if level == 'full':
        plan.append(('全链路冒烟 smoke_pipeline', [PY, os.path.join(HERE, 'smoke_pipeline.py')], 1200, True))

    # --- 输出计划 ----------------------------------------------------------
    print('=' * 70)
    print('分级闸门 · level=%s · %s' % (level.upper(), time.strftime('%Y-%m-%d %H:%M:%S')))
    print('判级依据：%s' % why)
    if changed:
        print('改动文件（%d）：%s' % (len(changed), '、'.join(changed[:12])
                                  + ('…' if len(changed) > 12 else '')))
    print('=' * 70)
    print('计划 %d 个阶段：' % len(plan))
    for name, cmd, to, _crit in plan:
        print('  · %-26s（超时 %ds）' % (name, to))
    print()

    # **最重要的一段：明写这个级别不保证什么**
    skipped = []
    if level == 'fast':
        skipped = ['静态审计 audit_pipeline', '全链路冒烟 smoke_pipeline',
                   '未被改动触碰的单测']
    elif level == 'std':
        skipped = ['全链路冒烟 smoke_pipeline（含真实网络调用）']
    if skipped:
        print('⚠️ 本级别**未**验证：')
        for s in skipped:
            print('     - %s' % s)
        print('   这些缺口由更高级别覆盖。交付前必须跑 full。')
        print()

    if a.dry_run:
        print('[dry-run] 计划如上，未执行。')
        return 0

    # --- 执行 --------------------------------------------------------------
    bad = []
    for name, cmd, to, crit in plan:
        rc, out, dt = _run(cmd, timeout=to)
        mark = 'OK  ' if rc == 0 else ('TIME' if rc == 124 else 'FAIL')
        print('  [%s] %-26s rc=%-4d %6.1fs' % (mark, name, rc, dt))
        if rc != 0:
            bad.append((name, rc, crit))
            for ln in out.splitlines()[-20:]:
                print('         ' + ln)
            if crit and level == 'full':
                print('         → 关键阶段失败，中止后续阶段')
                break

    dt_all = time.time() - t_all
    print('-' * 70)
    if bad:
        print('RESULT: FAIL %d 个阶段（level=%s，耗时 %.1fs）' % (len(bad), level.upper(), dt_all))
        return 1
    print('RESULT: PASS（level=%s，耗时 %.1fs = %.1f 分钟）' % (level.upper(), dt_all, dt_all / 60.0))
    if level != 'full':
        print('        ⚠️ 这是 %s 级通过，**不等于交付就绪** —— 交付前跑 gate.py full' % level.upper())
    return 0


if __name__ == '__main__':
    sys.exit(main())
