# -*- coding: utf-8 -*-
"""对外显示名守卫：对外产物里是否泄漏了知识星球③的真实名称。

背景（2026-09-18）：
    用户要求对外一律称该星球为「DRAGON BALL模型」，隐藏原名。
    改名分两层 —— 生成链路已直接改写；**数据层刻意保留原名**
    （forecast_chain.json / consensus_chain.json / zsxq_fetch_raw.json，
     改动会波及历史回测与链比对）。
    于是存在一条结构性泄漏路径：
        链数据原文 → 各生成器渲染 → SVG / HTML / 报告 md
    本脚本即针对这条路径的回归守卫：**扫描对外产物 + 生成链路**，
    任一命中即报错退出（非零），防止将来新增生成器时又一次漏出去。

用法：
    $PY .workbuddy/check_display_name.py            # 只看对外产物与生成链路
    $PY .workbuddy/check_display_name.py --all      # 连白名单一起列（排查用）

刻意不改、因此**永久白名单**（命中不算问题）：
    · fetch_zsxq.py / fetch_zsxq_fallback.py / backfill_zsxq_window.py
        → group_id → 星球名 的**数据映射**，改名会坏归档筛选
    · anonymize_report.py
        → 匿名化**历史报告**必需的匹配串（8 月老报告里写的是原名）
    · forecast_chain.json / consensus_chain.json / payload_*.json / zsxq_fetch_raw.json
        → 链数据与原始抓取数据（用户选定范围外）
    · .workbuddy/archive/** 与 `_` 前缀的按天中间产物（_tech_*.json / _build_payload_*.py
      / _zsxq_digest_*.txt / _*.log …，被 .gitignore 排除）
        → 历史快照与运行时件，不参与对外输出
    · .workbuddy/memory/** 与 _sync_家里/**
        → 内部记忆、家用同步副本
    · outputs/ 下非当日的历史报告
        → 历史产物不动
    · 本文件、display_names.py、_rename_tj_0918.py
        → 必须含匹配串才能工作（display_names.py 就是脱敏机制本体）
"""
import argparse
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 需要排除的目录（整棵子树）
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '_sync_家里', 'archive'}
# 命中的文件名（按 basename 精确匹配）
SKIP_FILES = {
    'fetch_zsxq.py', 'fetch_zsxq_fallback.py', 'backfill_zsxq_window.py',
    'anonymize_report.py',
    # display_names.py 是脱敏规则本体，必然含全部匹配串 —— 它**就是**脱敏机制
    'display_names.py',
    'forecast_chain.json', 'consensus_chain.json', 'zsxq_fetch_raw.json',
    'check_display_name.py', '_rename_tj_0918.py', '_scan_tj_residual.py',
}
SKIP_FILE_PREFIX = ('payload_', 'zsxq_fetch_raw')
# 路径片段排除
SKIP_PATH_SEG = (os.sep + 'memory' + os.sep,)


def _is_runtime_intermediate(name):
    """`_` 前缀 = 本项目「按天中间产物」约定（_tech_*.json / _build_payload_*.py /
    _zsxq_digest_*.txt / _*.log …），且被 .gitignore 排除。
    它们属当日运行时件、不参与对外输出，故不纳入守卫。"""
    return name.startswith('_')

# 需检查的后缀
EXTS = ('.md', '.py', '.html', '.svg', '.json', '.txt', '.yaml', '.yml')

# 三种历史写法 + 独立大写 TJ（词边界，避免误伤 tj_bypass 之类内部标识符）
PAT = re.compile(
    r'T&J|T\\&J|Truth and Justice|TRUTH_AND_JUSTICE|(?<![A-Za-z_])TJ(?![A-Za-z_])')


def scan(show_all=False, today=None):
    """返回 (命中字典, 白名单跳过数)。命中字典 = {相对路径: (次数, 写法集合)}"""
    hits, skipped = {}, 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.lower().endswith(EXTS):
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT)
            white = (fn in SKIP_FILES
                     or fn.startswith(SKIP_FILE_PREFIX)
                     or _is_runtime_intermediate(fn)
                     or any(s in fp for s in SKIP_PATH_SEG)
                     or rel.startswith('outputs' + os.sep) and today and today not in rel)
            if white:
                skipped += 1
                if not show_all:
                    continue
            try:
                with open(fp, encoding='utf-8', errors='replace') as f:
                    txt = f.read()
            except Exception:
                continue
            found = PAT.findall(txt)
            if found:
                hits[rel] = (len(found), sorted(set(found)))
    return hits, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description='对外显示名守卫：检查是否泄漏星球③原名')
    ap.add_argument('--all', action='store_true',
                    help='连永久白名单文件一起列出（仅供排查，退出码仍只看非白名单）')
    ap.add_argument('--today', default=None, metavar='YYYY-MM-DD',
                    help='当日日期；outputs/ 下非当日的报告视为历史产物跳过（默认按系统日期）')
    a = ap.parse_args(argv)

    import datetime
    today = a.today or datetime.date.today().isoformat()
    hits, skipped = scan(show_all=False, today=today)

    print('=' * 66)
    print('对外显示名守卫 · 检查日期 %s' % today)
    print('=' * 66)
    if not hits:
        print('OK  对外产物与生成链路零泄漏（白名单跳过 %d 个文件）' % skipped)
        return 0
    for rel in sorted(hits):
        n, kinds = hits[rel]
        print('  %-58s %3d 处  %s' % (rel, n, '/'.join(kinds)))
    print('-' * 66)
    print('泄漏 %d 个文件 —— 请改生成器或补白名单' % len(hits))
    return 1


if __name__ == '__main__':
    sys.exit(main())
