# -*- coding: utf-8 -*-
"""consensus_chain.json 字段名统一：opposite -> opposing（一次性历史回填，幂等、默认只读）。

背景（2026-09-26 排查发现）
----------------------------
consensus_chain.json 里「对立观点」字段名历史漂移：
  - 20 条旧记录用 `opposite`（append_consensus.py 时代 + automation prompt 时代）
  - 5 条记录用 `opposing`（chain_apply.py 的 record 模板里写的是 `opposing`）
两者含义完全相同（都是 {topic, side_a, side_b, ...} 列表），只是键名不一致。

为什么必须统一：
  目前**没有任何在役脚本读取该字段**（chainlib / check_integrity 读的是另一个字段
  `opposite_review`，与 `opposite`/`opposing` 无关），所以今天不炸；但这是典型的
  「静默漂移」——将来只要有人写 `rec.get('opposing')`，20 条旧记录会被静默漏读。
  统一键名可永久消除这个隐患。内容（topic/side_a/side_b 文本）**逐字节不动**，
  只改键名，不触碰铁律「数据层保留原文」。

用法：
    $PY .workbuddy/normalize_opposing.py            # dry-run：只报告
    $PY .workbuddy/normalize_opposing.py --apply    # 落盘（先自动备份 .bak）

退出码：0 已落盘 / 1 ERROR / 2 0 处改动（幂等，正常）
"""
import argparse
import json
import os
import shutil
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'consensus_chain.json')


def plan(chain):
    """返回需要改键的记录索引列表（纯函数，不改入参）。"""
    hits = []
    for i, r in enumerate(chain):
        if 'opposite' in r and 'opposing' not in r:
            hits.append(i)
    return hits


def _atomic_write(path, obj):
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        with open(tmp, encoding='utf-8') as f:
            back = json.load(f)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    if type(back) is not list or len(back) != len(obj):
        os.remove(tmp)
        raise RuntimeError('回读断言失败：写入 %d 条，读回 %s'
                           % (len(obj), len(back) if isinstance(back, list)
                              else type(back).__name__))
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description='consensus_chain.json 字段名 opposite->opposing')
    ap.add_argument('--apply', action='store_true', help='真正落盘（不加则只报告）')
    a = ap.parse_args(argv)

    if not os.path.exists(CHAIN):
        print('[FAIL] 链文件不存在：%s' % CHAIN, file=sys.stderr)
        return 1
    try:
        with open(CHAIN, encoding='utf-8') as f:
            chain = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print('[FAIL] 链解析失败（%s）' % e, file=sys.stderr)
        return 1

    hits = plan(chain)
    both = [i for i, r in enumerate(chain) if 'opposite' in r and 'opposing' in r]

    print('consensus_chain.json 共 %d 条' % len(chain))
    print('需改名 opposite -> opposing：%d 条' % len(hits))
    for i in hits:
        print('  · %s（opposite 有 %d 组对立观点）'
              % (chain[i].get('id'), len(chain[i].get('opposite', []))))
    if both:
        print('[WARN] 同时含两个键的记录 %d 条（本脚本不处理，需人工核对）：%s'
              % (len(both), '、'.join(chain[i].get('id', '?') for i in both)))

    if not hits:
        print('\n[WARN] 0 处改动（链已统一），未写盘。幂等正常。')
        return 2

    if not a.apply:
        print('\n以上为 dry-run，未落盘。确认后加 --apply。')
        return 2

    # 备份到 gitignored 目录（archive/backup_*/，见 .gitignore「链回滚快照」）。
    # 不能放在 CHAIN 同目录裸 `.bak`：consensus_chain.json 本身因含真实星球名而 gitignore，
    # 同目录 `.bak` 若不被忽略，一次 `git add -A` 就会把含真实名的链快照推进仓库（泄敏）。
    bak_dir = os.path.join(HERE, 'archive', 'backup_20260926_opposing')
    os.makedirs(bak_dir, exist_ok=True)
    bak = os.path.join(bak_dir, 'consensus_chain.json')
    if not os.path.exists(bak):
        shutil.copy2(CHAIN, bak)
        print('\n已备份：%s' % bak)
    else:
        print('\n备份已存在（复用）：%s' % bak)

    for i in hits:
        chain[i]['opposing'] = chain[i].pop('opposite')

    # 落盘前自检：不得再有 opposite，且 opposing 全部为 list
    residual = [chain[i].get('id') for i, r in enumerate(chain) if 'opposite' in r]
    if residual:
        print('[FAIL] 改名后仍有 opposite 残留：%s —— 中止，未写盘' % '、'.join(residual),
              file=sys.stderr)
        return 1

    try:
        _atomic_write(CHAIN, chain)
    except Exception as e:
        print('[FAIL] 写盘失败：%s' % e, file=sys.stderr)
        return 1

    print('[OK] 已落盘：%s（改名 %d 条，opposite 残留 0）' % (CHAIN, len(hits)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
