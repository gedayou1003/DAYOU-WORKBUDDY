# -*- coding: utf-8 -*-
"""check_integrity.py —— 数据完整性校验（防再漏的核心工具）。

每次抓取/生成报告后跑一次，比对「交易日 vs 实际归档/记录」，输出遗漏报告。

检查项：
1) T&J 原文归档：每个交易日应有 outputs/TRUTH_AND_JUSTICE_原始记录_YYYY-MM-DD.md
   （提示而非报错——T&J 可能当天无新帖，需人工确认）
2) forecast_chain 档位：每个交易日应至少有一条预判记录（晨报）
3) consensus_chain 时效：最后一条记录日期 vs 最近交易日，提示停更天数
4) forecast_chain 数据完整性：无 actual 缺 date/open/high/low/close/pct_chg

用法：
    python check_integrity.py [--from YYYY-MM-DD]
默认检查 2026-08-21（forecast_chain 首条）至今。

交易日判定：周一~周五，排除 HOLIDAYS 集合（需按实际节假日维护）。
"""
import json, os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'outputs')

FORECAST = os.path.join(HERE, 'forecast_chain.json')
CONSENSUS = os.path.join(HERE, 'consensus_chain.json')

# A股休市日（法定节假日，非周末）——需手动维护
HOLIDAYS = set()  # 例：{'2026-10-01', '2026-10-02', ...}

DEFAULT_FROM = '2026-08-21'


def trading_days(start, end):
    """返回 [start, end] 区间内的交易日（周一~周五，排除节假日）"""
    days = []
    d = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    while d <= e:
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            days.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return days


def main():
    start = DEFAULT_FROM
    if '--from' in sys.argv:
        start = sys.argv[sys.argv.index('--from') + 1]
    today = datetime.date.today().isoformat()

    # 已有 T&J 归档的日期
    tj_dates = set()
    for fn in os.listdir(OUT):
        if fn.startswith('TRUTH_AND_JUSTICE_原始记录_') and fn.endswith('.md'):
            tj_dates.add(fn.replace('TRUTH_AND_JUSTICE_原始记录_', '').replace('.md', ''))

    # forecast_chain 的日期分布
    with open(FORECAST, encoding='utf-8') as f:
        chain = json.load(f)
    fc_dates = {}
    for r in chain:
        d = r['id'].split('-')[0:3]
        d = '-'.join(d)
        fc_dates.setdefault(d, []).append(r['id'])

    # consensus 最后日期
    with open(CONSENSUS, encoding='utf-8') as f:
        cc = json.load(f)
    cc_dates = sorted(r['id'][:10] for r in cc if r.get('id'))
    cc_last = cc_dates[-1] if cc_dates else '无'

    print('=' * 70)
    print('数据完整性校验报告')
    print(f'检查区间：{start} ~ {today}')
    print('=' * 70)

    days = trading_days(start, today)

    # 1) T&J 归档缺口
    print('\n【1】T&J 原文归档缺口（有交易日但无归档文件，需确认当天是否真的无 T&J 新帖）')
    tj_missing = [d for d in days if d not in tj_dates]
    if tj_missing:
        for d in tj_missing:
            print(f'  ⚠️ {d} 缺 T&J 归档')
    else:
        print('  ✅ 无缺口')

    # 2) forecast_chain 档位缺口
    print('\n【2】forecast_chain 档位缺口（有交易日但无任何预判记录）')
    fc_missing = [d for d in days if d not in fc_dates]
    if fc_missing:
        for d in fc_missing:
            print(f'  ⚠️ {d} 无预判记录')
    else:
        print('  ✅ 无缺口')

    # 每个交易日只有晨报（无盘中/午间/收盘）的提示
    print('\n【3】档位覆盖偏薄（当日仅 1 条晨报，收盘/午间未跟进）')
    for d in days:
        if d in fc_dates and len(fc_dates[d]) == 1:
            print(f'  · {d} 仅 {fc_dates[d][0]}')

    # 3) consensus 时效
    print('\n【4】consensus_chain 时效')
    print(f'  最后一条：{cc_last}（共 {len(cc)} 条）')
    if cc_last < max(days):
        print(f'  ⚠️ 停更中（最近交易日 {max(days)} 未写入）')

    # 4) forecast_chain 数据完整性
    print('\n【5】forecast_chain 数据完整性（review.actual 字段）')
    bad = 0
    for r in chain:
        rev = r.get('review')
        if rev is None:
            continue
        a = rev.get('actual')
        if a is None or a is False:
            print(f'  ⚠️ {r["id"]}: 无 actual')
            bad += 1
        elif isinstance(a, dict):
            miss = [k for k in ['date', 'open', 'high', 'low', 'close', 'pct_chg'] if a.get(k) is None]
            if miss:
                print(f'  ⚠️ {r["id"]}: 缺 {miss}')
                bad += 1
    if bad == 0:
        print('  ✅ 全部完整')
    else:
        print(f'  共 {bad} 条异常')

    # 汇总
    print('\n' + '=' * 70)
    total_issue = len(tj_missing) + len(fc_missing) + bad
    print(f'汇总：T&J 缺口 {len(tj_missing)} · 档位缺口 {len(fc_missing)} · 数据异常 {bad}')
    print('（T&J 缺口需人工确认是否真的无新帖；其余缺口应补录）')
    print('=' * 70)


if __name__ == '__main__':
    main()
