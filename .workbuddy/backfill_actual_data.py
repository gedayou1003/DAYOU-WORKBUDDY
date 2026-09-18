# -*- coding: utf-8 -*-
"""补全 forecast_chain.json 的复盘 actual 数据（一次性回填，幂等可重跑）。

1) 6 条「无 actual 字段」的记录，按 target 日期回填真实 OHLC + pct_chg。
2) 11 条「actual 缺 pct_chg」的记录，按 actual.date 回填 pct_chg。

数据源：腾讯 fqkline 日线（2026-08-14 ~ 2026-09-04），写死为只读快照。

退出码（2026-09-18 起，全项目统一口径）：
  0 = 有回填且已落盘
  1 = ERROR（链文件缺失 / JSON 解析失败 / 写盘失败）—— 必须处理
  2 = WARN（无回填，或有「该补却补不了」的记录，需人工确认）—— 建议看一眼

「该补却补不了」的两种情况（都会记 WARN 并打印明细）：
  a) 无 actual 且不在 NO_ACTUAL_TARGET 映射表 —— 说明是新记录，需扩充映射表或改用
     backfill 之外的正规路径（apply_review / 直改 JSON）。
  b) actual 缺 pct_chg，但该 date 不在 KLINE 只读快照范围内（快照只到 2026-09-04）——
     这类记录必须走正规回填路径，本脚本无能为力。

注意：本脚本是**一次性历史回填**。日期超出 2026-09-04 的记录一律补不了，返回 2 属预期。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

# 腾讯 fqkline 日线快照（date: (open, close, high, low)）
KLINE = {
    '2026-08-17': (3930.10, 3982.65, 3983.51, 3924.47),
    '2026-08-18': (3979.49, 3990.30, 3994.18, 3955.60),
    '2026-08-19': (3952.12, 3894.42, 3961.14, 3879.58),
    '2026-08-20': (3907.21, 3903.72, 3925.06, 3888.10),
    '2026-08-21': (3891.18, 3905.20, 3912.13, 3883.79),
    '2026-08-24': (3902.70, 3882.01, 3910.24, 3855.35),
    '2026-08-25': (3863.37, 3889.44, 3896.21, 3850.86),
    '2026-08-26': (3881.74, 3912.52, 3926.44, 3881.74),
    '2026-08-27': (3911.89, 3956.57, 3958.03, 3909.31),
    '2026-08-28': (3950.24, 3952.18, 3970.31, 3947.80),
    '2026-08-31': (3926.53, 3986.30, 3986.30, 3926.50),
    '2026-09-01': (3979.88, 3979.89, 3995.18, 3976.47),
    '2026-09-02': (3963.07, 3941.39, 3965.81, 3932.25),
    '2026-09-03': (3952.79, 3942.09, 3968.11, 3930.45),
    '2026-09-04': (3955.55, 3930.12, 3980.20, 3915.22),
}

# 交易日顺序（用于求 prev_close）
DATES = sorted(KLINE.keys())
SNAPSHOT_END = DATES[-1]


def pct_of(date):
    """求 date 的 pct_chg（相对前一交易日 close）"""
    i = DATES.index(date)
    if i == 0:
        return None
    prev_close = KLINE[DATES[i - 1]][1]
    close = KLINE[date][1]
    return round((close - prev_close) / prev_close * 100, 2)


def ohlc_of(date):
    o, c, h, l = KLINE[date]
    return {
        'date': date, 'open': o, 'high': h, 'low': l, 'close': c,
        'pct_chg': pct_of(date),
    }


# 6 条无 actual 的记录 → 回填的 target 日期
# ⚠️ 2026-09-18：本表键是**记录 id**，而 id 曾因「id 日期 = created 日期」规范化被改过
#    （原 `2026-09-01-close` 已改名为 `2026-08-31-close`，见 normalize_chain.py）。
#    键一旦失效就是**静默空操作** —— 因此 main() 里加了「映射表键未命中」自检，
#    键对不上任何记录时会报 WARN 并把失效键列出来，不再无声无息。
NO_ACTUAL_TARGET = {
    '2026-08-24-morning-v2': '2026-08-25',
    '2026-08-24-close': '2026-08-25',
    '2026-08-25-morning': '2026-08-25',
    '2026-08-25-intraday': '2026-08-25',
    '2026-08-31-close': '2026-09-01',   # 原键 2026-09-01-close（改名后失效，2026-09-18 修正）
    '2026-09-01-morning': '2026-09-01',
}


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


def main():
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

    fixed_actual = 0
    fixed_pct = 0
    skipped = []      # 该补却补不了（WARN 来源）

    for r in chain:
        rev = r.get('review')
        if rev is None:
            continue

        # 情况1：无 actual 字段 → 回填整份 OHLC
        if 'actual' not in rev or rev['actual'] is False or rev['actual'] is None:
            if r['id'] in NO_ACTUAL_TARGET:
                date = NO_ACTUAL_TARGET[r['id']]
                rev['actual'] = ohlc_of(date)
                fixed_actual += 1
                print(f"[+actual] {r['id']} -> {date} {ohlc_of(date)}")
            else:
                print(f"[跳过] {r['id']} 无 actual 且不在映射表")
                skipped.append('无 actual 且不在映射表：%s' % r['id'])
            continue

        # 情况2：actual 有但缺 pct_chg → 只补 pct_chg
        a = rev['actual']
        if isinstance(a, dict):
            date = a.get('date')
            if a.get('pct_chg') is None:
                if date in KLINE:
                    a['pct_chg'] = pct_of(date)
                    fixed_pct += 1
                    print(f"[+pct] {r['id']} ({date}) -> pct_chg={a['pct_chg']}")
                else:
                    print(f"[跳过] {r['id']} 缺 pct_chg，但 date={date} 超出只读快照范围"
                          f"（快照止于 {SNAPSHOT_END}）")
                    skipped.append('缺 pct_chg 且 %s 超出快照范围：%s' % (date, r['id']))

    changed = fixed_actual + fixed_pct

    # 映射表自检：键对不上任何记录 = 静默空操作（id 被改名过就会出现）
    chain_ids = {r.get('id') for r in chain}
    unused = [k for k in NO_ACTUAL_TARGET if k not in chain_ids]
    if unused:
        print('[WARN] NO_ACTUAL_TARGET 有 %d 个键未命中任何记录（映射表已过期）：' % len(unused))
        for k in unused:
            print('       · %s（想回填 target=%s，但链上已无此 id）' % (k, NO_ACTUAL_TARGET[k]))
        print('       多半是记录的 id 被规范化改过名；请按当前 id 更新映射表。')
        skipped.append('NO_ACTUAL_TARGET 过期键 %d 个：%s' % (len(unused), '、'.join(unused)))

    if changed:
        try:
            _atomic_write_json(CHAIN, chain)
        except Exception as e:
            print('[FAIL] 写盘失败：%s' % e, file=sys.stderr)
            return 1

    print(f'\n完成：回填 actual {fixed_actual} 条，补 pct_chg {fixed_pct} 条')

    if skipped:
        # 打印全部明细（不截断），让人能直接照着处理
        print(f'[WARN] 另有 {len(skipped)} 项「该补却补不了 / 映射表自身过期」：')
        for s in skipped:
            print('       · %s' % s)
        print('       这些记录本脚本补不了，请走正规回填路径（apply_review / 直改 JSON），'
              '或确认它们本就无需回填。')
        return 2
    if changed == 0:
        print('[WARN] 本次 0 处回填（链已回填完毕），未写盘。'
              '本脚本为一次性历史回填，属正常幂等结果。')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
