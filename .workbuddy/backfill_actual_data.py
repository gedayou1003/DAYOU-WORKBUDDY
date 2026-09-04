# -*- coding: utf-8 -*-
"""补全 forecast_chain.json 的复盘 actual 数据（一次性回填，幂等可重跑）。

1) 6 条「无 actual 字段」的记录，按 target 日期回填真实 OHLC + pct_chg。
2) 11 条「actual 缺 pct_chg」的记录，按 actual.date 回填 pct_chg。

数据源：腾讯 fqkline 日线（2026-08-14 ~ 2026-09-04），写死为只读快照。
"""
import json, os

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
    '2026-09-04': (3955.55, 3970.64, 3980.20, 3955.55),
}

# 交易日顺序（用于求 prev_close）
DATES = sorted(KLINE.keys())


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
NO_ACTUAL_TARGET = {
    '2026-08-24-morning-v2': '2026-08-25',
    '2026-08-24-close': '2026-08-25',
    '2026-08-25-morning': '2026-08-25',
    '2026-08-25-intraday': '2026-08-25',
    '2026-09-01-close': '2026-09-01',
    '2026-09-01-morning': '2026-09-01',
}


def main():
    with open(CHAIN, encoding='utf-8') as f:
        chain = json.load(f)

    fixed_actual = 0
    fixed_pct = 0

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
            continue

        # 情况2：actual 有但缺 pct_chg → 只补 pct_chg
        a = rev['actual']
        if isinstance(a, dict):
            date = a.get('date')
            if date in KLINE and a.get('pct_chg') is None:
                a['pct_chg'] = pct_of(date)
                fixed_pct += 1
                print(f"[+pct] {r['id']} ({date}) -> pct_chg={a['pct_chg']}")

    with open(CHAIN, 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)

    print(f'\n完成：回填 actual {fixed_actual} 条，补 pct_chg {fixed_pct} 条')


if __name__ == '__main__':
    main()
