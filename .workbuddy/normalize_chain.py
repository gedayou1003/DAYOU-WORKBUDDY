# -*- coding: utf-8 -*-
"""forecast_chain.json 规范化（一次性，幂等可重跑）：

1) 修复 id 命名错位 —— 统一为「id 日期 = created 日期」：
   - 2026-08-28-close (created 08-27)  -> 2026-08-27-close
   - 2026-08-31-close (created 08-28)  -> 2026-08-28-close
   - 2026-09-01-close (created 08-31)  -> 2026-08-31-close
2) 统一 actual 字段名：旧版 `pct` -> `pct_chg`（数值不变）
3) 补 actual.date：从 target 字段提取交易日（历史盘中快照数值保留原貌，不篡改）
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

ID_RENAME = {
    '2026-08-28-close': '2026-08-27-close',
    '2026-08-31-close': '2026-08-28-close',
    '2026-09-01-close': '2026-08-31-close',
}

DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})')


def main():
    with open(CHAIN, encoding='utf-8') as f:
        chain = json.load(f)

    n_rename = 0
    n_pct = 0
    n_date = 0

    for r in chain:
        # 1) 改名
        if r['id'] in ID_RENAME:
            old = r['id']
            r['id'] = ID_RENAME[old]
            n_rename += 1
            print(f'[rename] {old} -> {r["id"]}')

        # 2) + 3) actual 规范化
        rev = r.get('review')
        if rev and isinstance(rev.get('actual'), dict):
            a = rev['actual']
            # 字段名 pct -> pct_chg
            if 'pct_chg' not in a and 'pct' in a:
                a['pct_chg'] = a.pop('pct')
                n_pct += 1
                print(f'[pct] {r["id"]} pct -> pct_chg = {a["pct_chg"]}')
            # 补 date（从 target 提取）
            if 'date' not in a or a.get('date') is None:
                m = DATE_RE.search(r.get('target', ''))
                if m:
                    a['date'] = m.group(1)
                    n_date += 1
                    print(f'[date] {r["id"]} date = {a["date"]}')

    with open(CHAIN, 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)

    print(f'\n完成：改名 {n_rename} 条，字段名统一 {n_pct} 条，补 date {n_date} 条')


if __name__ == '__main__':
    main()
