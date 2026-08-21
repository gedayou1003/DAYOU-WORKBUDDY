# -*- coding: utf-8 -*-
"""
清理 zsxq_images 下的历史图片（中间产物，正文已提取进晨报 md）
默认预览模式（只列清单不删），加 --apply 才实际删除。

用法：
    python cleanup_images.py              # 预览：清理 3 天前的图片
    python cleanup_images.py 7            # 预览：清理 7 天前的图片
    python cleanup_images.py 3 --apply    # 实际删除 3 天前的图片
"""
import os, sys, datetime

IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zsxq_images")
EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')


def main():
    days = 3
    dry_run = True
    args = [a for a in sys.argv[1:]]
    if '--apply' in args:
        dry_run = False
        args.remove('--apply')
    if args and args[0].isdigit():
        days = int(args[0])

    # 按自然日判断：保留最近 N 个自然日（含今天），更早的删除
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today_start - datetime.timedelta(days=days - 1)
    cutoff_ts = cutoff.timestamp()

    targets = []
    total = 0
    for fname in os.listdir(IMG_DIR):
        fpath = os.path.join(IMG_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if not fname.lower().endswith(EXTS):
            continue
        if os.path.getmtime(fpath) < cutoff_ts:
            size = os.path.getsize(fpath)
            targets.append((fname, size))
            total += size

    targets.sort()
    mb = total / 1024 / 1024
    print(f"清理 {days} 天前的图片（截止 {cutoff.strftime('%Y-%m-%d %H:%M')} 之前）")
    print(f"命中 {len(targets)} 个文件，约 {mb:.1f} MB")
    print()

    if dry_run:
        print("【预览模式】以下文件将被删除（未实际删除）：")
        for fname, size in targets[:40]:
            print(f"  {fname}  ({size // 1024} KB)")
        if len(targets) > 40:
            print(f"  ... 其余 {len(targets) - 40} 个")
        print()
        print("确认无误后，加 --apply 参数实际删除。")
    else:
        for fname, _ in targets:
            os.remove(os.path.join(IMG_DIR, fname))
        print(f"已实际删除 {len(targets)} 个文件，释放 {mb:.1f} MB")


if __name__ == '__main__':
    main()
