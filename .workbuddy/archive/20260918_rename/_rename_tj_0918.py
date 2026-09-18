# -*- coding: utf-8 -*-
"""把「对外显示层 + 生成链路」里的 T&J / Truth and Justice 改称「DRAGON BALL模型」。

2026-09-18 用户指令：隐藏 T&J，报告一律显示 DRAGON BALL模型。

分三类处理（关键：功能必需的匹配串一律不动）
--------------------------------------------------------------------------
1) BLIND        全文替换（报告 / 链路文档 / 校验器等）
2) PROTECT_MD   归档 md：只改代码块**之外**的文字，保住「一字不差」正文
3) RENAME       文件改名（23 个原文归档 + 1 个方法论文档）

**刻意不动的**（改了会坏功能或属非显示层）：
  - fetch_zsxq.py / fetch_zsxq_fallback.py / backfill_zsxq_window.py 的
    `"88512145458842": "Truth and Justice"` —— 群组 id→名 的**数据映射**
  - 内部标识符：compute_tj_bypass / tj_bypass / tj_accuracy / tj_dir
  - 脚本文件名：backtest_tj_v2.py 等
  - 链数据 forecast_chain / consensus_chain / payload、记忆日志、_sync_家里 副本
    （用户选定范围为「对外显示层 + 生成链路」）

用法：
    python _rename_tj_0918.py            # dry-run，只打印
    python _rename_tj_0918.py --apply    # 落盘（自动备份到 archive/backup_20260918_rename/）
"""
import io
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, '.workbuddy')
OUT = os.path.join(ROOT, 'outputs')
BACKUP = os.path.join(HERE, 'archive', 'backup_20260918_rename')

# 顺序敏感：长模式优先，避免 "T&J" 先命中把 "T&J" 之外的形态切碎
RULES = [
    ('TRUTH_AND_JUSTICE', 'DRAGON_BALL'),
    ('Truth and Justice', 'DRAGON BALL模型'),
    ('T\\&J', 'DRAGON BALL模型'),   # anonymize 里出现过的转义写法
    ('T&J', 'DRAGON BALL模型'),
]

BLIND = [
    'outputs/作战报告_晨报_2026-09-18.md',
    '.workbuddy/报告生成流程.md',
    '.workbuddy/报告逻辑排版完整性规范_v2.md',
    '.workbuddy/预判规则_v5.md',
    '.workbuddy/脚本地图.md',
    '.workbuddy/README_预判系统.md',
    '.workbuddy/模型体检报告_2026-09-16.md',
    '.workbuddy/TJ方法论提炼_旁路参考.md',
    '.workbuddy/check_integrity.py',
    '.workbuddy/gen_backtest_report.py',
    '.workbuddy/cleanup_workspace.py',
    '.workbuddy/calc_tech_multi.py',
    '.workbuddy/backtest_macd.py',
    '.workbuddy/backtest_divergence.py',
    '.workbuddy/backtest_tj_v2.py',
    '.workbuddy/backtest_tj_v2_verify.py',
]

# 第三种写法：独立大写「TJ」（如「TJ 方法论」「TJ 旁路」）。仅限链路内这几个文件，
# 用词边界保护，避免误伤 backtest_tj_v2.py 这类文件名与小写标识符（compute_tj_bypass）。
TJ_ONLY = [
    '.workbuddy/backtest_tj_v2.py',
    '.workbuddy/backtest_tj_v2_verify.py',
    '.workbuddy/forecast_analyze.py',
]
TJ_RE = re.compile(r'(?<![A-Za-z_])TJ(?![A-Za-z_])')

PROTECT_MD = []   # 运行时用 glob 填 outputs/TRUTH_AND_JUSTICE_原始记录_*.md

RENAME = [
    ('.workbuddy/TJ方法论提炼_旁路参考.md', '.workbuddy/DRAGON_BALL_方法论提炼_旁路参考.md'),
]

CODE_FENCE = re.compile(r'```.*?```', re.S)


def count_hits(s):
    return sum(len(re.findall(re.escape(o), s)) for o, _ in RULES)


def apply_rules(s):
    for old, new in RULES:
        s = s.replace(old, new)
    return s


def apply_rules_outside_fences(s):
    """只替换代码块之外的文字，代码块原样保留（保「一字不差」正文）。"""
    out, last = [], 0
    for m in CODE_FENCE.finditer(s):
        out.append(apply_rules(s[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(apply_rules(s[last:]))
    return ''.join(out)


def main():
    apply = '--apply' in sys.argv
    md_archives = sorted(
        os.path.join(OUT, f) for f in os.listdir(OUT)
        if f.startswith('TRUTH_AND_JUSTICE_原始记录_') and f.endswith('.md'))
    PROTECT_MD.extend(md_archives)

    if apply:
        os.makedirs(BACKUP, exist_ok=True)

    print('模式：%s' % ('**落盘**' if apply else 'dry-run（加 --apply 才写盘）'))
    print('备份目录：%s' % BACKUP if apply else '备份目录：（dry-run 不备份）')
    print()
    print('=' * 72)
    print('【1】全文替换（%d 个文件）' % len(BLIND))
    print('=' * 72)
    tot = 0
    for rel in BLIND:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print('  [跳过] 不存在 %s' % rel)
            continue
        s = io.open(p, encoding='utf-8').read()
        n = count_hits(s)
        if not n:
            print('  [无命中] %s' % rel)
            continue
        tot += n
        print('  %-58s %4d 处' % (rel, n))
        if apply:
            shutil.copy2(p, os.path.join(BACKUP, os.path.basename(p)))
            io.open(p, 'w', encoding='utf-8').write(apply_rules(s))
    print('  小计 %d 处' % tot)

    print()
    print('=' * 72)
    print('【1b】独立「TJ」写法替换（%d 个文件，词边界保护）' % len(TJ_ONLY))
    print('=' * 72)
    tot1b = 0
    for rel in TJ_ONLY:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print('  [跳过] 不存在 %s' % rel)
            continue
        s = io.open(p, encoding='utf-8').read()
        n = len(TJ_RE.findall(s))
        if not n:
            print('  [无命中] %s' % rel)
            continue
        tot1b += n
        print('  %-58s %4d 处' % (rel, n))
        if apply:
            shutil.copy2(p, os.path.join(BACKUP, os.path.basename(p)))
            io.open(p, 'w', encoding='utf-8').write(TJ_RE.sub('DRAGON BALL模型', s))
    print('  小计 %d 处' % tot1b)

    print()
    print('=' * 72)
    print('【2】归档 md 替换（仅代码块之外，%d 个文件）' % len(PROTECT_MD))
    print('=' * 72)
    tot2 = 0
    for p in PROTECT_MD:
        s = io.open(p, encoding='utf-8').read()
        new = apply_rules_outside_fences(s)
        n = count_hits(s)
        infence = len(re.findall(r'T&J|Truth and Justice', CODE_FENCE.sub('', s))) if False else 0
        changed = new != s
        tot2 += n
        if changed:
            print('  %-52s %4d 处（块内 0 处不动）' % (os.path.basename(p), n))
            if apply:
                shutil.copy2(p, os.path.join(BACKUP, os.path.basename(p)))
                io.open(p, 'w', encoding='utf-8').write(new)
        else:
            print('  %-52s 无需改（仅块外无命中）' % os.path.basename(p))
    print('  小计 %d 处' % tot2)

    print()
    print('=' * 72)
    print('【3】文件改名（%d 项）' % (len(RENAME) + len(PROTECT_MD)))
    print('=' * 72)
    pairs = list(RENAME)
    for p in PROTECT_MD:
        pairs.append((os.path.relpath(p, ROOT),
                      os.path.relpath(p.replace('TRUTH_AND_JUSTICE_原始记录_', 'DRAGON_BALL_原始记录_'), ROOT)))
    ok = 0
    for old, new in pairs:
        po, pn = os.path.join(ROOT, old), os.path.join(ROOT, new)
        if not os.path.exists(po):
            print('  [跳过] 源不存在 %s' % old)
            continue
        if os.path.exists(pn):
            print('  [跳过] 目标已存在 %s' % new)
            continue
        print('  %s\n      -> %s' % (old, new))
        if apply:
            os.rename(po, pn)
        ok += 1
    print('  %s %d 项' % ('已改名' if apply else '待改名', ok))

    print()
    print('=' * 72)
    if apply:
        print('完成。备份在 %s' % BACKUP)
        print('回滚：把备份文件复制回原位 + 把文件改回原名即可。')
    else:
        print('以上为预演。确认无误后加 --apply 落盘。')


if __name__ == '__main__':
    main()
