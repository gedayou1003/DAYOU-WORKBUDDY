# -*- coding: utf-8 -*-
"""recycle_smoke_tmp.py —— 回收冒烟测试的历史临时目录（常驻工具，2026-09-24 建）。

为什么需要它（复审 R3）
----------------------
`smoke_pipeline.py` 每次运行都新建 `_smoke_tmp/run_<时间戳>/`，且**从不删除别人的目录**
（这是刻意的设计：它自己的设计前提是「零副作用」，去删历史目录会让它有了删除副作用，
排查时无法区分是谁删的；另外 `_cleanup` 的阈值逻辑 2026-09-21 曾把冒烟自己在第一行就拦死）。
代价是：**这些目录不会自动回收**，跑几十次之后 `_smoke_tmp/` 会默默堆到几百 MB —— 
而目录本身不在 git 里、也不在任何校验器的视野内，没人会发现。

本工具就是那条缺失的回收通道。**独立脚本，不塞进冒烟主流程。**

设计要点
--------
1. **默认 dry-run**：不给 `--apply` 就只打印「会删什么、能省多少」，一个字都不删。
   删除是不可逆动作，默认必须是只读的。
2. **保留最近 N 次**（默认 5）：最新的几轮冒烟正在被排查中，先留着。
3. **只认自己的命名**：只处理 `run_<YYYYmmdd_HHMMSS>` 形态的目录，
   且必须位于 `_smoke_tmp/` 下。**不递归、不通配、不碰其他任何路径。**
   （这是防「手滑写成 rmtree(_smoke_tmp/*)」的护栏。）
4. **大目录不硬删**：目录内文件数超过 `MAX_FILES_PER_DIR` 时**跳过并说明**，
   因为环境的安全删除闸门会按文件数（含 zip 成员）计数拦截 ——
   硬来会像 2026-09-21 那样把调用方一起拖死。跳过时提示人工处理路径。
5. **删完必须回查**：`rmtree(ignore_errors=True)` 会把失败吞掉，
   所以删完要确认目录真的没了，没删掉就如实报出（留着垃圾可以，瞒着不行）。
6. 退出码：0 干净（无可回收 / 回收成功）· 2 有跳过项（需人工看一眼）· 1 参数错误。

用法
----
    $PY .workbuddy/recycle_smoke_tmp.py                 # 预演（默认，不删）
    $PY .workbuddy/recycle_smoke_tmp.py --apply         # 真删
    $PY .workbuddy/recycle_smoke_tmp.py --keep 3 --apply
    $PY .workbuddy/recycle_smoke_tmp.py --all --apply   # 连最近 N 次也删
"""
import argparse
import os
import re
import shutil
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(HERE, '_smoke_tmp')

# 只认这个命名形态（smoke_pipeline 里的 `run_%Y%m%d_%H%M%S`）
RUN_DIR_RE = re.compile(r'^run_\d{8}_\d{6}$')
# 单目录文件数上限：超过就跳过（环境删除闸门会按文件数拦截，硬删会把调用方一起拖死）
MAX_FILES_PER_DIR = 400
KEEP_DEFAULT = 5


def dir_stats(p):
    """返回 (松散文件数, zip 成员数, 字节数)。"""
    loose = members = size = 0
    for root, _, fs in os.walk(p):
        for f in fs:
            fp = os.path.join(root, f)
            loose += 1
            try:
                size += os.path.getsize(fp)
            except OSError:                 # silent-ok: 体积统计失败不影响"该不该删"的判定
                pass
            if f.endswith('.zip'):
                try:
                    import zipfile
                    with zipfile.ZipFile(fp) as z:
                        members += len(z.namelist())
                except Exception:           # silent-ok: zip 读不动按 0 计，只会让阈值判定偏保守
                    pass
    return loose, members, size


def human(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return '%.1f %s' % (n, u)
        n /= 1024.0
    return '%.1f TB' % n


def find_runs(root):
    """列出 root 下所有符合命名规范的 run 目录，按名字（即时间）升序。"""
    if not os.path.isdir(root):
        return []
    out = []
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if os.path.isdir(p) and RUN_DIR_RE.match(name):
            out.append((name, p))
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='回收冒烟测试的历史临时目录（默认预演，不删）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='例:\n'
               '  python recycle_smoke_tmp.py              # 预演\n'
               '  python recycle_smoke_tmp.py --apply      # 真删（保留最近 5 次）\n'
               '  python recycle_smoke_tmp.py --keep 3 --apply\n'
               '  python recycle_smoke_tmp.py --all --apply')
    ap.add_argument('--root', default=DEFAULT_ROOT, help='临时目录根（默认 .workbuddy/_smoke_tmp）')
    ap.add_argument('--keep', type=int, default=KEEP_DEFAULT,
                    help='保留最近 N 次运行（默认 %d）' % KEEP_DEFAULT)
    ap.add_argument('--all', action='store_true', help='不保留，全部回收（含最近 N 次）')
    ap.add_argument('--apply', action='store_true', help='真正执行删除（默认只预演）')
    a = ap.parse_args(argv)

    if a.keep < 0:
        print('[FAIL] --keep 不能为负（收到 %s）' % a.keep)
        return 1
    root = os.path.abspath(a.root)
    print('=' * 70)
    print('冒烟临时目录回收')
    print('根目录：%s' % root)
    print('模式  ：%s' % ('**真删**（--apply）' if a.apply else '预演（不加 --apply 不删任何东西）'))
    print('保留  ：%s' % ('全部回收（--all）' if a.all else '最近 %d 次' % a.keep))
    print('=' * 70)

    if not os.path.isdir(root):
        print('ℹ️ 目录不存在 → 无可回收：%s' % root)
        return 0

    runs = find_runs(root)
    others = sorted(n for n in os.listdir(root)
                    if os.path.isdir(os.path.join(root, n)) and not RUN_DIR_RE.match(n))
    if not runs:
        print('ℹ️ 没有符合 `run_<YYYYmmdd_HHMMSS>` 命名的历史目录 → 无可回收')
        if others:
            print('   （另有 %d 个不合命名的目录，**刻意不动**：%s）' % (len(others), '、'.join(others)))
        return 0

    keep = 0 if a.all else min(a.keep, len(runs))
    kept = runs[len(runs) - keep:] if keep else []
    doomed = runs[:len(runs) - keep] if keep else list(runs)

    # ⚠️ 「保留最近 N 次」只决定**删不删**，不决定**查不查**。
    # 初版把 kept 直接从候选集里剔掉，于是被保留目录里的超大目录**从不被检查** ——
    # 它既不在待删清单里、也不会被跳过逻辑看到，就等于**静默豁免**。
    # （实测：造 410 文件的 run 目录 + --keep 1，它恰好落在保留区间，
    #   输出里连一句提示都没有，退出码还是 0。）
    # 现在改成：**全部扫描一遍**，只是把保留项标出来、不删。
    print('\n共 %d 个历史目录；计划回收 %d 个、保留 %d 个'
          % (len(runs), len(doomed), len(kept)))
    if kept:
        print('保留：' + '、'.join(n for n, _ in kept))

    # 预先统计「被保留但仍需提醒」的目录（冻结的垃圾也是垃圾，必须能看见）
    frozen_big = []
    for name, p in kept:
        loose, members, size = dir_stats(p)
        if loose + members > MAX_FILES_PER_DIR:
            frozen_big.append((name, p, loose + members, size))

    if not doomed:
        print('ℹ️ 本次无目录需要回收（最近 %d 次全部保留）' % (len(kept) or 0))
        if frozen_big:
            print('⚠️ 但保留区间内有 %d 个目录**体积超标**（冻结的垃圾也是垃圾，'
                  '下次 --keep 调小或 --all 时会处理；也可人工清理）：' % len(frozen_big))
            for name, p, cnt, size in frozen_big:
                print('   · %s（%d 个文件 / %s）%s' % (name, cnt, human(size), p))
            return 2
        return 0

    print('\n待回收明细：')
    total_files = total_size = 0
    skipped = []
    ready = []
    for name, p in doomed:
        loose, members, size = dir_stats(p)
        cnt = loose + members          # 闸门按「松散文件 + zip 成员」计数
        flag = ''
        if cnt > MAX_FILES_PER_DIR:
            flag = '  ⚠️ 跳过（%d > 阈值 %d，硬删会撞环境删除闸门）' % (cnt, MAX_FILES_PER_DIR)
            skipped.append((name, p, cnt))
        else:
            ready.append((name, p, cnt, size))
        total_files += cnt
        total_size += size
        print('  %-22s 文件 %-5d 体积 %-10s%s' % (name, cnt, human(size), flag))

    print('\n小计：%d 个目录 / %d 个文件 / %s' % (len(doomed), total_files, human(total_size)))
    if skipped:
        print('⚠️ 其中 %d 个**已跳过**（体积/文件数过大），需人工处理：' % len(skipped))
        for name, p, cnt in skipped:
            print('   · %s（%d 个文件）%s' % (name, cnt, p))
    if frozen_big:
        print('⚠️ 另在保留区间内有 %d 个目录体积超标（本次不动，但须知道）：' % len(frozen_big))
        for name, p, cnt, size in frozen_big:
            print('   · %s（%d 个文件 / %s）' % (name, cnt, human(size)))

    if not a.apply:
        print('\n（预演结束，未删除任何东西。确认无误后加 --apply 执行）')
        return 2 if (skipped or frozen_big) else 0

    print('\n执行删除：')
    ok = fail = 0
    for name, p, cnt, _size in ready:
        shutil.rmtree(p, ignore_errors=True)
        if os.path.isdir(p):           # 删完必须回查：ignore_errors=True 会把失败吞掉
            print('  [FAIL] %s 删除失败（环境删除保护拦截），请人工处理：%s' % (name, p))
            fail += 1
        else:
            print('  [OK] %s 已回收' % name)
            ok += 1

    kept_note = ('' if a.all else '（保留最近 %d 次的目录）' % len(kept))
    print('\n' + '=' * 70)
    print('汇总：回收 %d · 失败 %d · 跳过 %d · 保留区间超标 %d%s'
          % (ok, fail, len(skipped), len(frozen_big), kept_note))
    if fail or skipped or frozen_big:
        # ⚠️ 刻意**不用 `rc = 2 if fail else ...` 的近似写法**：有跳过项时也该报 2，
        # 否则「文件里写了退出码 2 = 有跳过项」这句话与实际行为不符 ——
        # 而调用方（人或 CI）只信退出码，不信文档。
        # （本文件初版正是这样：文档写 2、实现只在 fail 时给 2，被
        #   test_recycle_smoke_tmp.py 的 ③ 组抓出来；同轮还抓出「保留区间的目录
        #   从不被检查」这个更实质的漏洞 —— 见上面 frozen_big 的注释。）
        print('⚠️ 有未回收项 —— 留下的垃圾能看见，不会瞒着。')
        return 2
    print('✅ 回收完成。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
