# -*- coding: utf-8 -*-
"""normalize_levels_date.py —— 一次性把两条链里的 `levels.date` 按 `target` 归一化（2026-09-24 建）。

为什么需要它（复审报告「仍悬着」项）
------------------------------------
`levels.date` 在链上被**混用**了两种语义：
  ① **目标交易日**（本意）—— `2026-09-21-morning` 的 target 是「2026-09-21 全天」，
     于是 `levels.date = '2026-09-21'`，也与记录 id 的日期段一致；
  ② **数据基准日**（现价取自哪天的收盘）—— `2026-09-23-noon` 的现价取自 9/23 盘中，
     恰好也是 9/23；而 `2026-09-24-morning` 的现价取自 **9/23 收盘**，于是填了 `2026-09-23`。

历史记录之所以从没暴露问题，是因为 ①② **恰好同值**：
`2026-09-21-morning → '2026-09-21'`、`2026-09-23-noon → '2026-09-23'` ……
直到 9/24 晨报两条值首次分开，`gen_forecast_svg.py` 的默认文件名就推成了
`000001_forecast_2026-09-23.svg`，**静默覆盖了 9/23 午间档的走势图**（md5 相同、不可恢复）。

`gen_forecast_svg.py` 已在用端加固（id 日期段优先、并拒绝覆盖别人的图），
但**链里的错值仍在**：任何按 `levels.date` 理解目标日的下游都可能再踩一次。
本脚本把存量数据统一到语义 ①。

与 `backfill_actual_data.py` 同套路
-----------------------------------
  · 幂等：已是目标值的记录不动；重跑第二次应当 0 改动（返回 2 并说明）；
  · 原子写：tmp → 回读断言 → `os.replace`；
  · 缺 target / target 无日期段的记录**不猜**，归 WARN 明细报出来（不静默）；
  · 退出码 0 有改动 / 1 ERROR / 2 WARN（含幂等空跑）。

刻意**不做**的事
----------------
  · 不新增/删除记录，只改 `levels.date` 一个字段；
  · 不改 `review.actual.date`（那是**真实叠加数据的日子**，语义本来就该是"实际哪天"，与 target 可以不同）；
  · 不为缺 target 的历史记录编造目标日（宁可留 WARN，也不造假数据 —— 与 KNOWN_FC_GAPS 同一原则）。

用法
----
    $PY .workbuddy/normalize_levels_date.py                 # 预演（默认，不写盘）
    $PY .workbuddy/normalize_levels_date.py --apply         # 真写
    $PY .workbuddy/normalize_levels_date.py --only forecast  # 只处理一条链
"""
import argparse
import io
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 链名 → 文件名（与 chainlib.CHAINS 同口径；此处不 import chainlib 以保持本脚本可独立运行，
# 也避免 CHAIN_DIR 环境变量重定向把一次性脚本写到别处）。
CHAINS = {
    'forecast': os.path.join(HERE, 'forecast_chain.json'),
    'consensus': os.path.join(HERE, 'consensus_chain.json'),
}


def date_prefix(s):
    """抽 YYYY-MM-DD；抽不到返回 None。"""
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', str(s or ''))
    return m.group(1) if m else None


def _atomic_write_json(path, obj):
    """临时文件 → 回读断言 → 原子替换（与 backfill_actual_data / fetch_zsxq 同口径）。"""
    tmp = path + '.tmp'
    try:
        with io.open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        with io.open(tmp, encoding='utf-8') as f:
            back = json.load(f)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    if type(back) is not type(obj) or len(back) != len(obj):
        os.remove(tmp)
        raise RuntimeError('链回读断言失败：写入 %d 条，读回 %s'
                           % (len(obj), len(back) if isinstance(back, (list, dict))
                              else type(back).__name__))
    os.replace(tmp, path)


def process(name, path, apply_changes):
    """返回 (changed, warned, failed)。"""
    if not os.path.exists(path):
        print('[FAIL] 链文件不存在：%s' % path, file=sys.stderr)
        return 0, 0, 1
    try:
        with io.open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print('[FAIL] 链文件解析失败：%s（%s）' % (path, e), file=sys.stderr)
        print('       本脚本不会重建链，请先修复或从备份恢复。', file=sys.stderr)
        return 0, 0, 1

    is_dict = isinstance(data, dict)
    recs = data.get('records', []) if is_dict else data
    print('\n== %s（%s）  %d 条' % (name, os.path.basename(path), len(recs)))

    changed, warned = [], []
    for r in recs:
        rid = r.get('id', '')
        lv = r.get('levels')
        if not isinstance(lv, dict):
            continue                      # 无 levels 字段（共识链大量如此）→ 不关本脚本的事
        cur = lv.get('date')
        tgt = date_prefix(r.get('target'))
        if tgt is None:
            # 不猜：target 缺失/无日期段 → 报出来让人判断，绝不用 id 日期顶替
            warned.append('id=%s：target=%r 抽不出日期段，`levels.date` 保持 %r 不动'
                          % (rid, r.get('target'), cur))
            continue
        cur_n = str(cur).replace('/', '-') if cur else None
        if cur_n == tgt:
            continue                      # 已正确 → 幂等，不动
        old = cur
        lv['date'] = tgt
        changed.append('id=%s：levels.date %r → %r（target=%r）'
                       % (rid, old, tgt, r.get('target')))
        print('   [改] id=%s  levels.date %r -> %r' % (rid, old, tgt))

    if changed:
        if apply_changes:
            try:
                _atomic_write_json(path, data)
            except Exception as e:        # noqa: BLE001
                print('[FAIL] 写盘失败：%s' % e, file=sys.stderr)
                return len(changed), len(warned), 1
            print('   ✅ 已写盘（%d 处改动，原子替换 + 回读断言通过）' % len(changed))
        else:
            print('   （预演：%d 处待改，未写盘。确认无误后加 --apply）' % len(changed))
    else:
        print('   ℹ️ 0 处待改（本链已归一化 —— 幂等，未写盘）')

    if warned:
        print('   ⚠️ 另有 %d 条无法判定（**不猜、不写**，请人工核对）：' % len(warned))
        for w in warned:
            print('      · %s' % w)

    return len(changed), len(warned), 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='一次性把两条链的 levels.date 按 target 归一化（默认预演，不写盘）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='例:\n'
               '  python normalize_levels_date.py            # 预演\n'
               '  python normalize_levels_date.py --apply    # 真写\n'
               '  python normalize_levels_date.py --only forecast --apply')
    ap.add_argument('--apply', action='store_true', help='真正写盘（默认只预演）')
    ap.add_argument('--only', default=None, choices=sorted(CHAINS),
                    help='只处理指定链（默认两条都处理）')
    a = ap.parse_args(argv)

    names = [a.only] if a.only else list(CHAINS)
    print('=' * 70)
    print('levels.date 按 target 归一化（一次性脚本）')
    print('模式：%s' % ('**真写**（--apply）' if a.apply else '预演（不加 --apply 不写盘）'))
    print('=' * 70)

    tot_c = tot_w = fail = 0
    for n in names:
        c, w, f = process(n, CHAINS[n], a.apply)
        tot_c += c
        tot_w += w
        fail += f

    print('\n' + '=' * 70)
    print('汇总：待改/已改 %d 处 · 无法判定 %d 条 · 失败 %d' % (tot_c, tot_w, fail))
    if fail:
        print('❌ 有链处理失败 —— 见上方 [FAIL]。')
        return 1
    if tot_w:
        print('⚠️ 有无法判定的记录（未改动）—— 需人工核对 target 是否缺失。')
        return 2
    if tot_c == 0:
        print('ℹ️ 无改动（两条链均已归一化）。本脚本为一次性历史归一化，属正常幂等结果。')
        return 2
    if not a.apply:
        print('（预演结束，未写任何东西。确认无误后加 --apply 执行）')
        return 0
    print('✅ 归一化完成。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
