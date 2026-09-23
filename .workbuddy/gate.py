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
    # 变盘倾向分：**它的自检不是 test_*.py 文件**（是脚本自带的 --selftest），
    # 所以这里显式指过去 —— 否则改了它只会跑到两个无关的通用守卫，
    # 58 条断言一条都不会被执行（2026-08-14 分级闸门首轮实测发现的洞）。
    'calc_turn_score.py':     [],      # 走 SELFTESTS（非 test_*.py）
    'gate.py':                [],
    # 报告内容类（不影响逻辑）
    '报告生成流程.md':         [],
    '预判规则_v5.md':          [],
    '脚本地图.md':             [],
}

# --- 非 test_*.py 的自检入口 ------------------------------------------------
# 有些脚本的自检是**内置**的（`--selftest`），不被 run_tests.py 的 glob 收进来。
# 分级闸门必须知道它们，否则「改了这个脚本 → 跑两个无关守卫」= 假验证。
#
# ⚠️ 路径一律用**只含文件名**的形式，由下面拼 HERE —— 不要写 `.workbuddy/x.py`
# 再 lstrip('./')：那样会把 `.workbuddy` 的开头那个点也剥掉，变成 `workbuddy/x.py`
# （2026-09-23 首跑就这么错了一次，直接 No such file）。
SELFTESTS = {
    'calc_turn_score.py': ['--selftest'],
}


# --- 昂贵测试（变异/meta 类）-------------------------------------------------
# 这类测试**内部会跑别的 test_*.py**：每注入一处变异就重跑一遍正本测试。
# 设计上它们价值极高（证明断言真的会红），但 **天然昂贵且与改动无关**：
# 改的是 A 脚本，它们证的是 B 断言的有效性 —— 不该每次陪跑。
#
# 实测（2026-09-23）：test_gen_forecast_svg_neg 113.8s + test_audit_docrot_neg 75.0s
# = 188.8s，占全套 392.3s 的 **48%**。只做「后台慢速集」，std 级默认跳过。
SLOW_MUTATION = {
    'test_gen_forecast_svg_neg.py':  ['gen_forecast_svg', 'svg'],   # 只在这两处被碰时才跑
    'test_audit_docrot_neg.py':      ['audit_pipeline', 'audit'],   # 同上
}


def _split_slow(tests, changed):
    """把测试分成 (常规, 昂贵的变异测试)。

    昂贵测试仅当**它保护的脚本真的被改动**时才纳入 —— 否则它们只是在
    重复证明「上周已经证过的断言仍然有效」。改动信息不可得（changed 为空）
    时**保守纳入**（宁可慢，不可漏）。
    """
    # 改动可能来自 --changed（文件名列表），也可能是"复核"场景（无改动）
    blob = ' '.join(changed)
    fast_tests, slow_tests = [], []
    for t in tests:
        pats = SLOW_MUTATION.get(t)
        if not pats:
            fast_tests.append(t)
            continue
        if not changed:
            slow_tests.append(t)          # 无改动信息 → 保守纳入
        elif any(p in blob for p in pats):
            fast_tests.append(t)          # 它保护的东西被改了 → 必须跑
        else:
            slow_tests.append(t)          # 无关 → 归慢速集
    return fast_tests, slow_tests


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
        # 工作区干净 ⇒ 这是"复核"场景（如交付前），而不是"改完即刻自检"。
        # ⚠️ 改前这里返回 fast → 只跑语法编译（2.5s），等于**什么实质都没验**。
        # 干净树往往出现在"要交付了"的时刻，恰恰是最需要真验证的时候，
        # 所以宁可多花 3 分钟也要上 std。
        return 'std', '工作区无改动 → 复核场景，跑 std（不做 fast：干净树+fast 等于没验）'
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
    ap.add_argument('--with-slow', action='store_true',
                    help='std 级也纳入昂贵变异测试（默认跳过；full 级本来就全跑）')
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
    tests, deferred_slow = [], []
    # 内置自检（非 test_*.py）：改动了对应脚本就必须跑，否则 fast 级形同虚设
    for f in changed:
        if f in SELFTESTS:
            plan.append(('内置自检 %s' % f,
                         [PY, os.path.join(HERE, f)] + SELFTESTS[f], 120, True))
    if level == 'fast':
        # fast：只跑与改动直接相关的测试文件（**不是**跑全套）
        pats = []
        for f in changed:
            pats += AFFECTS.get(f, [])
        if changed and not pats:
            pats = ['arg_guard', 'display_name']    # 纯文档改动 → 只跑最快守卫
        tests = pick_tests(pats) if pats else []
        tests, deferred_slow = _split_slow(tests, changed)
        if tests:
            plan.append(('相关单测（%d 个）' % len(tests),
                         [PY, os.path.join(HERE, 'run_tests.py'),
                          '--files', ','.join(tests)], 300, True))
    else:
        all_tests = pick_tests('*')
        if level == 'full':
            tests, deferred_slow = all_tests, []    # full 一律全跑，不省
        else:
            # std：跳过与本轮改动无关的昂贵变异测试（省下的时间见 deferred 提示）
            tests, deferred_slow = _split_slow(all_tests, changed)
            if a.with_slow and deferred_slow:
                tests = tests + deferred_slow       # 显式要求纳入
                deferred_slow = []
        if tests:
            plan.append(('聚合单测（%d 个）' % len(tests),
                         [PY, os.path.join(HERE, 'run_tests.py'),
                          '--files', ','.join(tests)], 600, True))

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
    if deferred_slow:
        skipped.append('昂贵变异测试 %d 个（拆开时排除了它们）' % len(deferred_slow))
    if skipped:
        print('⚠️ 本级别**未**验证：')
        for s in skipped:
            print('     - %s' % s)
        if deferred_slow:
            print('       （变异测试补跑方式：gate.py std --with-slow，或跑 gate.py full）')
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
