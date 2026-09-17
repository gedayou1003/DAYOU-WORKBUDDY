# -*- coding: utf-8 -*-
"""缠论引擎产物轮转：按交易日保留最近 N 天，更早的归档。

背景：`run_000001_chansignal.py` 每次运行都往技能目录 `output/` 写
`<CODE>_<YYYYMMDD>_chansignal.json` / `_boll_chan.json` / `_买卖点对比表.md` /
`_买卖点面板.html` / `_BOLL缠论交叉验证.md` —— 每天 5 个文件、只增不减。
2026-09-17 盘点时已累积 132 个文件（8/14 起）。

保留规则（三重保险，任一命中即保留）：
  1. 日期落在最近 `--keep-days` 个**交易日**内（按 output 目录里实际出现过的日期取）
  2. 文件 mtime 在最近 `--mtime-days` 天内
  3. 显式前缀匹配 `--keep`（默认保留今日）

归档而非删除：移到 `<output>/archive/<YYYYMM>/`，要回滚直接移回上一层。

用法：
    python cleanup_engine_output.py                 # dry-run，看计划
    python cleanup_engine_output.py --apply         # 执行
    python cleanup_engine_output.py --keep-days 30  # 保留更长
    python cleanup_engine_output.py --dir <路径> --apply
"""
import argparse
import datetime
import os
import re
import shutil
import sys

DEFAULT_DIR = os.path.expanduser('~/.workbuddy/skills/chan-signal__skillhub/output')
DATE_RE = re.compile(r'_(\d{8})_')


def file_date(name):
    m = DATE_RE.search(name)
    return m.group(1) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser(description='缠论引擎产物轮转（归档更早的交易日产物）')
    ap.add_argument('--dir', default=DEFAULT_DIR, help='引擎 output 目录')
    ap.add_argument('--keep-days', type=int, default=15,
                    help='保留最近多少个交易日（按目录内实际出现的日期计，默认 15）')
    ap.add_argument('--mtime-days', type=int, default=3,
                    help='mtime 在此天数内的文件一律保留（默认 3）')
    ap.add_argument('--apply', action='store_true', help='真正执行；不加则只打印计划')
    a = ap.parse_args(argv)

    if not os.path.isdir(a.dir):
        raise SystemExit('[FAIL] 目录不存在：%s' % a.dir)

    files = [f for f in os.listdir(a.dir)
             if os.path.isfile(os.path.join(a.dir, f))]
    dated = {}
    undated = []
    for f in files:
        d = file_date(f)
        if d:
            dated.setdefault(d, []).append(f)
        else:
            undated.append(f)

    days = sorted(dated, reverse=True)
    keep = set(days[:a.keep_days])
    drop_days = [d for d in days if d not in keep]

    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=a.mtime_days)

    print('目录：%s' % a.dir)
    print('模式：%s' % ('APPLY' if a.apply else 'DRY-RUN'))
    print('共 %d 个文件，其中带日期的 %d 个、不带日期的 %d 个'
          % (len(files), sum(len(v) for v in dated.values()), len(undated)))
    print('覆盖交易日 %d 个：%s ~ %s' % (len(days), days[-1], days[0]) if days else '无')
    print('保留最近 %d 个交易日：%s' % (len(keep), ', '.join(sorted(keep, reverse=True)) if keep else '-'))
    print('拟归档 %d 个交易日：%s'
          % (len(drop_days), ', '.join(sorted(drop_days, reverse=True)) if drop_days else '无'))
    if undated:
        print('⚠️ 无日期文件（一律保留，请人工核对命名）：%s' % ', '.join(sorted(undated)))
    print('')

    moved, kept_recent = [], []
    for d in drop_days:
        ym = '%s-%s' % (d[:4], d[4:6])
        dest = os.path.join(a.dir, 'archive', ym)
        for f in dated[d]:
            src = os.path.join(a.dir, f)
            mt = datetime.date.fromtimestamp(os.path.getmtime(src))
            if mt >= cutoff:
                kept_recent.append((f, mt.isoformat()))
                continue
            moved.append((src, os.path.join(dest, f), os.path.getsize(src), d))
            if a.apply:
                os.makedirs(dest, exist_ok=True)
                shutil.move(src, os.path.join(dest, f))

    if kept_recent:
        print('— 因最近有写入（mtime ≥ %s）而改为保留 —' % cutoff.isoformat())
        for f, mt in kept_recent:
            print('  %-56s mtime=%s' % (f, mt))
        print('')

    if not moved:
        print('无需归档：所有文件都在保留窗口内。')
        return 0

    by_ym = {}
    for src, dst, size, d in moved:
        by_ym.setdefault(os.path.dirname(dst), [0, 0])
        by_ym[os.path.dirname(dst)][0] += 1
        by_ym[os.path.dirname(dst)][1] += size
    print('— %s —' % ('已归档' if a.apply else '拟归档'))
    for ym in sorted(by_ym):
        n, sz = by_ym[ym]
        print('  %-44s %3d 个 %8.1f KB' % (os.path.relpath(ym, a.dir), n, sz / 1024))
    print('  合计 %d 个，%.1f KB' % (len(moved), sum(x[2] for x in moved) / 1024))
    if not a.apply:
        print('')
        print('（dry-run 结束；加 --apply 才会真正移动）')
    else:
        print('')
        print('归档完成。回滚：把 archive/<YYYY-MM>/ 下的文件移回上一级即可。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
