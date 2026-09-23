# -*- coding: utf-8 -*-
"""forecast_chain.json 规范化（一次性历史回填；幂等、可重跑、默认只读）。

规范化三件事：
1) id 命名 —— 强制不变量「id 的日期 == created_at 的日期」，违反者按 created_at 改名。
2) actual 字段名统一：旧版 `pct` -> `pct_chg`（数值不变）。
3) 补 actual.date：从 target 字段提取交易日（历史盘中快照数值保留原貌，不篡改）。

用法：
    $PY .workbuddy/normalize_chain.py            # 默认 dry-run：只报告，不改文件
    $PY .workbuddy/normalize_chain.py --apply     # 真正落盘

退出码（2026-09-18 起，全项目统一口径）：
  0 = 有改动且已落盘（仅 --apply 可达）
  1 = ERROR（链文件缺失 / JSON 解析失败 / 目标 id 冲突 / 写盘失败）—— 必须处理
  2 = WARN（0 处改动；或 dry-run 下有改动但未落盘）—— 建议确认一下

────────────────────────────────────────────────────────────────────────
⚠️ 2026-09-18 修复记录（重要，勿重蹈）：
   本脚本原本用一张**固定改名表** ID_RENAME = {A: B, B: C, C: D}。该表**不幂等**：
   首次运行把 A→B、B→C 正确落位；**第二次运行**会把已经正确命名的 B 再改成 A、
   把 C 再改成 B，整体位移一步，直接**撞车产生重复 id**。
   （实测现场：2026-09-18 二次运行把 `2026-08-28-close`(created 08-28) 改成
     `2026-08-27-close`，与已存在的同名记录重复；md5 已回滚复原。）
   现改为**不变量驱动**：只对「id 日期 ≠ created_at 日期」的记录改名，天然幂等，
   且改名前后做**冲突检测**（目标 id 已存在则报 ERROR 并整体中止，不写盘）。
   另按项目惯例改为**默认 dry-run**，与 cleanup_workspace.py 同口径。
────────────────────────────────────────────────────────────────────────

注意：本脚本是**一次性历史回填**，正常情况下各项不变量早已成立。
之后每次跑都应返回 2（0 处改动）；若返回 0/待改动，说明链里又出现了需要规范化的旧格式记录。
"""
import argparse
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
CHAIN = os.path.join(HERE, 'forecast_chain.json')

DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})')


def _id_parts(rid):
    """`2026-08-28-close` -> ('2026-08-28', 'close')；无法解析返回 (None, None)。"""
    m = re.match(r'^(\d{4}-\d{2}-\d{2})-(.+)$', rid or '')
    return (m.group(1), m.group(2)) if m else (None, None)


def _created_date(rec):
    """取 created_at 的日期部分（'2026-08-28 15:46' -> '2026-08-28'）。"""
    m = DATE_RE.match(str(rec.get('created_at') or '').strip())
    return m.group(1) if m else None


def _atomic_write_json(path, obj):
    """临时文件 → 回读断言 → 原子替换（与 fetch_zsxq._atomic_write_json 同口径）。"""
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
    if type(back) is not type(obj) or len(back) != len(obj):
        os.remove(tmp)
        raise RuntimeError('链回读断言失败：写入 %d 条，读回 %s'
                           % (len(obj), len(back) if isinstance(back, (list, dict))
                              else type(back).__name__))
    os.replace(tmp, path)


def plan(chain):
    """算出全部待改动项（纯函数，不修改入参）。

    返回 (renames, pct_fixes, date_fixes, conflicts)
      renames    : [(index, old_id, new_id, created_at)]
      pct_fixes  : [(index, rid)]           actual.pct -> pct_chg
      date_fixes : [(index, rid, date)]     补 actual.date
      conflicts  : [(old_id, new_id, ...)]  目标 id 已被占用 —— ERROR
    """
    existing = {}
    for i, r in enumerate(chain):
        existing.setdefault(r.get('id'), []).append(i)

    renames, pct_fixes, date_fixes, conflicts = [], [], [], []

    for i, r in enumerate(chain):
        rid = r.get('id')
        id_date, suffix = _id_parts(rid)
        cdate = _created_date(r)

        # ---- 1) id 命名不变量：id 日期 == created_at 日期 ----
        if id_date and cdate and id_date != cdate and suffix:
            new_id = '%s-%s' % (cdate, suffix)
            owners = [j for j in existing.get(new_id, []) if j != i]
            if owners:
                conflicts.append((rid, new_id, r.get('created_at'),
                                  '目标 id 已被第 %s 条占用' % ', '.join(map(str, owners))))
            else:
                renames.append((i, rid, new_id, r.get('created_at')))

        # ---- 2)+3) actual 规范化（只对 dict 型 actual 生效）----
        rev = r.get('review')
        if rev and isinstance(rev.get('actual'), dict):
            a = rev['actual']
            if 'pct_chg' not in a and 'pct' in a:
                pct_fixes.append((i, rid))
            if a.get('date') is None:
                m = DATE_RE.search(str(r.get('target') or ''))
                if m:
                    date_fixes.append((i, rid, m.group(1)))

    return renames, pct_fixes, date_fixes, conflicts


def apply_plan(chain, renames, pct_fixes, date_fixes):
    for i, _old, new_id, _ca in renames:
        chain[i]['id'] = new_id
    for i, _rid in pct_fixes:
        a = chain[i]['review']['actual']
        a['pct_chg'] = a.pop('pct')
    for i, _rid, date in date_fixes:
        chain[i]['review']['actual']['date'] = date


def main(argv=None):
    ap = argparse.ArgumentParser(description='forecast_chain.json 规范化（默认 dry-run）')
    ap.add_argument('--apply', action='store_true', help='真正落盘（不加则只报告）')
    a = ap.parse_args(argv)

    if not os.path.exists(CHAIN):
        print('[FAIL] 链文件不存在：%s' % CHAIN, file=sys.stderr)
        return 1
    try:
        with open(CHAIN, encoding='utf-8') as f:
            chain = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print('[FAIL] 链文件解析失败：%s（%s）' % (CHAIN, e), file=sys.stderr)
        print('       本脚本不会重建链，请先修复或从备份恢复。', file=sys.stderr)
        return 1

    renames, pct_fixes, date_fixes, conflicts = plan(chain)

    # 冲突是硬错误：整体中止，一条都不改（避免半改状态）
    if conflicts:
        print('[FAIL] 检测到 %d 处 id 改名冲突，已整体中止且未写盘：' % len(conflicts),
              file=sys.stderr)
        for old, new, ca, why in conflicts:
            print('       %s (created_at=%s) -> %s：%s' % (old, ca, new, why), file=sys.stderr)
        print('       多半是重复记录或 created_at 有误；请先人工核对，勿盲目改名。',
              file=sys.stderr)
        return 1

    changed = len(renames) + len(pct_fixes) + len(date_fixes)

    for i, old, new, ca in renames:
        print('[rename] %s -> %s   (created_at=%s)' % (old, new, ca))
    for i, rid in pct_fixes:
        print('[pct]    %s  actual.pct -> pct_chg = %s'
              % (rid, chain[i]['review']['actual']['pct']))
    for i, rid, date in date_fixes:
        print('[date]   %s  actual.date = %s' % (rid, date))

    if changed == 0:
        print('\n完成：改名 0 条，字段名统一 0 条，补 date 0 条')
        print('[WARN] 本次 0 处改动（链已满足全部不变量），未写盘。'
              '本脚本为一次性历史回填，属正常幂等结果。')
        return 2

    summary = '\n完成：改名 %d 条，字段名统一 %d 条，补 date %d 条' % (
        len(renames), len(pct_fixes), len(date_fixes))

    if not a.apply:
        print(summary)
        print('[WARN] 以上为 dry-run 结果，**未写盘**。确认无误后加 --apply 落盘。')
        return 2

    apply_plan(chain, renames, pct_fixes, date_fixes)

    # 落盘前自检：改名后不得出现重复 id
    seen, dup = set(), []
    for r in chain:
        if r['id'] in seen:
            dup.append(r['id'])
        seen.add(r['id'])
    if dup:
        print('[FAIL] 应用改动后出现重复 id：%s —— 已中止且未写盘' % dup, file=sys.stderr)
        return 1

    try:
        _atomic_write_json(CHAIN, chain)
    except Exception as e:
        print('[FAIL] 写盘失败：%s' % e, file=sys.stderr)
        return 1

    print(summary)
    print('[OK] 已落盘：%s' % CHAIN)
    return 0


if __name__ == '__main__':
    sys.exit(main())
