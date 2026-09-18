# -*- coding: utf-8 -*-
"""check_integrity.py —— 数据完整性校验（防再漏的核心工具）。

每次抓取/生成报告后跑一次，比对「交易日 vs 实际归档/记录」，输出遗漏报告。

检查项
------
1) DRAGON BALL模型 原文归档：每个交易日应有 outputs/DRAGON_BALL_原始记录_YYYY-MM-DD.md
2) forecast_chain 档位：每个交易日应至少有一条预判记录（晨报）
3) 档位覆盖偏薄：当日仅 1 条晨报（**既定节奏，INFO 级**，见下）
4) consensus_chain 时效：最后一条记录日期 vs 最近交易日
5) forecast_chain 数据完整性：review.actual 缺 date/open/high/low/close/pct_chg
6) pending 守卫：任一链 pending > 1 → 可能漏复盘上一条（自 chain_apply 下沉）

2026-09-17 加固（消除永久噪声，恢复闸门可用性）
-----------------------------------------------
改前问题：本工具每期都会刷出 4 条历史 DRAGON BALL模型 缺口 + 7 条「档位覆盖偏薄」，共 11 行固定噪声，
而**真正的缺口淹没在里面**；且无论如何都返回 0，无法当 gate 用。这与 `DUP_RULES` /
`LENGTH_RULES`（规范写了但无机器检查）是同一类失效：**告警太多的闸门等于没有闸门**。

改后：
  - `KNOWN_TJ_GAPS` 白名单承载历史例外（附原因），归入「已知例外」不计入问题数
  - 「档位覆盖偏薄」降为 INFO，默认只给一行汇总（`--verbose` 才逐日展开）
  - 新增 pending 守卫
  - **退出码语义**：0 = 无实质问题（已知例外 / INFO 不影响）；2 = 存在需处理的问题

用法
----
    python check_integrity.py [--from YYYY-MM-DD] [--verbose]

默认检查 2026-08-21（forecast_chain 首条）至今。
交易日判定：周一~周五，排除 HOLIDAYS 集合（需按实际节假日维护）。
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'outputs')

FORECAST = os.path.join(HERE, 'forecast_chain.json')
CONSENSUS = os.path.join(HERE, 'consensus_chain.json')

# A股休市日（法定节假日，非周末）——需手动维护
HOLIDAYS = set()  # 例：{'2026-10-01', '2026-10-02', ...}

DEFAULT_FROM = '2026-08-21'

# 已知例外：DRAGON BALL模型 归档缺口（早于归档机制建立，不硬补，见脚本地图 §五）
KNOWN_TJ_GAPS = {
    '2026-08-24': '早于 DRAGON BALL模型 归档机制建立（历史已知）',
    '2026-08-28': '早于 DRAGON BALL模型 归档机制建立（历史已知）',
    '2026-08-31': '早于 DRAGON BALL模型 归档机制建立（历史已知）',
    '2026-09-01': '早于 DRAGON BALL模型 归档机制建立（历史已知）',
}


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
    argv = sys.argv
    start = DEFAULT_FROM
    if '--from' in argv:
        start = argv[argv.index('--from') + 1]
    verbose = '--verbose' in argv or '-v' in argv
    today = datetime.date.today().isoformat()

    # 已有 DRAGON BALL模型 归档的日期
    tj_dates = set()
    if os.path.isdir(OUT):
        for fn in os.listdir(OUT):
            if fn.startswith('DRAGON_BALL_原始记录_') and fn.endswith('.md'):
                tj_dates.add(fn.replace('DRAGON_BALL_原始记录_', '').replace('.md', ''))

    # forecast_chain 的日期分布
    with open(FORECAST, encoding='utf-8') as f:
        fchain = json.load(f)
    fc_dates = {}
    for r in fchain:
        d = '-'.join(r['id'].split('-')[0:3])
        fc_dates.setdefault(d, []).append(r['id'])

    # consensus
    with open(CONSENSUS, encoding='utf-8') as f:
        cchain = json.load(f)
    cc_dates = sorted(r['id'][:10] for r in cchain if r.get('id'))
    cc_last = cc_dates[-1] if cc_dates else '无'

    print('=' * 70)
    print('数据完整性校验报告')
    print(f'检查区间：{start} ~ {today}')
    print('=' * 70)

    days = trading_days(start, today)
    problems = 0   # 需处理的实质问题数（决定退出码）

    # 1) DRAGON BALL模型 归档缺口
    print('\n【1】DRAGON BALL模型 原文归档缺口（有交易日但无归档文件）')
    tj_missing = [d for d in days if d not in tj_dates]
    tj_real = [d for d in tj_missing if d not in KNOWN_TJ_GAPS]
    tj_known = [d for d in tj_missing if d in KNOWN_TJ_GAPS]
    if tj_real:
        for d in tj_real:
            print(f'  ⚠️ {d} 缺 DRAGON BALL模型 归档（需确认当天是否真的无 DRAGON BALL模型 新帖）')
        problems += len(tj_real)
    else:
        print('  ✅ 无新增缺口')
    if tj_known:
        print(f'  ℹ️ 已知例外 {len(tj_known)} 条（不计入问题）：'
              + '、'.join('%s→%s' % (d, KNOWN_TJ_GAPS[d]) for d in tj_known))

    # 2) forecast_chain 档位缺口
    print('\n【2】forecast_chain 档位缺口（有交易日但无任何预判记录）')
    fc_missing = [d for d in days if d not in fc_dates]
    if fc_missing:
        for d in fc_missing:
            print(f'  ⚠️ {d} 无预判记录')
        problems += len(fc_missing)
    else:
        print('  ✅ 无缺口')

    # 3) 档位覆盖偏薄（INFO —— 近期既定节奏只跑晨报档，不是缺口）
    thin = [d for d in days if d in fc_dates and len(fc_dates[d]) == 1]
    print('\n【3】档位覆盖偏薄（当日仅 1 条晨报）')
    print(f'  ℹ️ {len(thin)} 天（近期既定节奏为「只跑晨报档」，非缺口；--verbose 展开）')
    if verbose:
        for d in thin:
            print(f'     · {d} 仅 {fc_dates[d][0]}')

    # 4) consensus 时效
    print('\n【4】consensus_chain 时效')
    print(f'  最后一条：{cc_last}（共 {len(cchain)} 条）')
    if days and cc_last < max(days):
        print(f'  ⚠️ 停更中（最近交易日 {max(days)} 未写入）')
        problems += 1

    # 5) forecast_chain 数据完整性
    print('\n【5】forecast_chain 数据完整性（review.actual 字段）')
    bad = 0
    for r in fchain:
        rev = r.get('review')
        if rev is None:
            continue
        a = rev.get('actual')
        if a is None or a is False:
            print(f'  ⚠️ {r["id"]}: 无 actual')
            bad += 1
        elif isinstance(a, dict):
            miss = [k for k in ['date', 'open', 'high', 'low', 'close', 'pct_chg']
                    if a.get(k) is None]
            if miss:
                print(f'  ⚠️ {r["id"]}: 缺 {miss}')
                bad += 1
    if bad == 0:
        print('  ✅ 全部完整')
    else:
        print(f'  共 {bad} 条异常')
        problems += bad

    # 6) pending 守卫（自 chain_apply 下沉：链上超过 1 条 pending 说明可能漏复盘）
    print('\n【6】pending 守卫（> 1 条即可能漏复盘上一条）')
    for name, ch in (('forecast', fchain), ('consensus', cchain)):
        pends = [r.get('id') for r in ch if r.get('status') == 'pending']
        if len(pends) > 1:
            print(f'  ⚠️ {name}: pending={len(pends)} → {", ".join(pends)}')
            problems += 1
        else:
            print(f'  ✅ {name}: pending={len(pends)}'
                  + ('（%s）' % pends[0] if pends else ''))

    # 汇总
    print('\n' + '=' * 70)
    print(f'汇总：DRAGON BALL模型 新增缺口 {len(tj_real)}（另有已知例外 {len(tj_known)}）· '
          f'档位缺口 {len(fc_missing)} · 数据异常 {bad} · 实质问题合计 {problems}')
    if problems == 0:
        print('✅ 无实质问题。')
    else:
        print('⚠️ 存在需处理的问题（见上方 ⚠️ 行）。')
    print('=' * 70)
    return 2 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
