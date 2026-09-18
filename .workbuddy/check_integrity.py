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
7) 链记录 → 报告产物：链上每条记录都应对应一份 outputs/作战报告_<档位>_<日期>.md

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

2026-09-18 分级（P1-1，本文件与 check_layout 口径统一）
-------------------------------------------------------
改前问题：只有「有问题 / 没问题」两档，且**无论如何只要 problems>0 就返回 2**——
把「ERROR（必须处理）」与「WARN（看一眼）」混成同一个码；而【5】把「开盘前静态初验
不写 O/H/L/C」这条**设计使然**的情况计成问题，导致每期固定刷同一条告警（就是上一段
说的「永久噪声」换了个位置复发）。

改后：
  - 三级：**ERROR / WARN / INFO**，退出码 `1 = 有 ERROR`、`2 = 仅 WARN`、`0 = 干净`
    —— 与 `check_layout.py`、`fetch_zsxq.py`、`gen_tj_archive.py` 完全同口径
  - 【5】按语义分流：静态初验（phase/reviewed_at/note 含「静态初验」）→ INFO；
    历史散文格式 actual → `KNOWN_ACTUAL_EXCEPTIONS` 白名单 → INFO；
    其余 actual 缺失 / 字段不全 / 类型异常 → WARN
  - 顺带补上一个**静默盲区**：旧实现对 `actual` 是字符串的记录**两个分支都不进**，
    等于从不校验（9/11、9/14 两条一直在裸奔），现明确纳入判定
  - 【1】【2】【4】【6】为 ERROR（数据缺口 / 链停更 / 漏复盘）

2026-09-18 补盲区【7】（全链路审计 5.5）
---------------------------------------
改前问题：所有校验器都只看「链里有没有记录 / 归档在不在」，**没有一处看报告文件本身在不在**。
链和报告是两条独立写入路径（链由脚本 append、报告由 LLM 落盘）——链写成功而报告落盘失败时，
全链路会静默「全绿」：记录说「本期预判已写入」，磁盘上却没有那份报告。
【7】补上这一环：链上每条 `<日期>-<档位>` 记录都要有对应的
`outputs/作战报告_<中文档位>_<日期>.md`，缺失即 ERROR。
只做单向断言（链有记录 → 报告先有）；反方向需要交易日历，刻意不做。
`ARTIFACT_SINCE` 之前的缺口归历史命名例外（旧报告名不同/已归档），聚合一条 INFO。

用法
----
    python check_integrity.py [--from YYYY-MM-DD] [--verbose]

默认检查 2026-08-21（forecast_chain 首条）至今。
交易日判定：周一~周五，排除 HOLIDAYS 集合（需按实际节假日维护）。
"""
import datetime
import json
import os
import re
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

# 已知例外：review.actual 为「散文格式」而非结构化 O/H/L/C（早于结构化规范，历史已知）。
# 归 INFO 不报 WARN 是刻意的：这两条永远无法补齐，若报 WARN 就等于每期固定刷两条，
# 正好复现 2026-09-17 刚清掉的那类「永久噪声」。
KNOWN_ACTUAL_EXCEPTIONS = {
    '2026-09-11-morning': 'actual 为旧散文格式（早于结构化 actual 规范）',
    '2026-09-14-morning': 'actual 为旧散文格式（早于结构化 actual 规范）',
}

# actual 完整性要求的字段
ACTUAL_KEYS = ['date', 'open', 'high', 'low', 'close', 'pct_chg']

# ---------------------------------------------------------------------------
# 【7】链记录 → 报告产物：档位后缀 → 报告文件名里的中文档位段
#
# 背景（2026-09-18 全链路审计 5.5「校验器盲区」）
# ----------------------------------------------
# 原先所有校验器都只看「链里有没有记录」「归档在不在」，**没有一处看报告文件本身在不在**。
# 而链和报告是两条独立的写入路径（链由脚本 append、报告由 LLM 落盘）：
# 只要链写成功、报告落盘失败，全链路就会静默地"全绿" —— 记录说「本期预判已写入」，
# 磁盘上却根本没有那份报告。这正是 check 类工具最该覆盖、却恰好没覆盖的缝隙。
#
# 方向只有一个：**链已有记录 → 报告必须先有**。
# 反方向（"该生成却无记录"）需要交易日历 + 各档位排期，现有数据反查不出来，刻意不做，
# 免得做出一个靠猜的检查。
# ---------------------------------------------------------------------------
TIER_BY_SUFFIX = {
    'morning': '晨报', 'morning-v2': '晨报',   # -v2 是同日重生成的旧命名
    'noon': '午间', 'afternoon': '午间',
    'close': '收盘',
    'intraday': '盘中', '1100': '盘中', '1340': '盘中',   # 早期按时点命名，同属盘中档
}

# 报告命名统一为「作战报告_<档位>_<日期>.md」的生效日。此前的报告用了别的文件名
# （知识星球晨报_… 等）且多已归档，逐条报缺口就是纯噪声 —— 与 KNOWN_TJ_GAPS 同一处理。
ARTIFACT_SINCE = '2026-08-27'


def is_static_precheck(rev):
    """该 review 是否为「晨报档·开盘前静态初验」。

    晨报档职责含对前一日收盘档做两阶段静态初验：开盘前只判方向/区间，
    **按设计不写 O/H/L/C**（避免下游走势图误取零值），actual 只留 date/prev_close/note。
    故【5】不得把它当「数据缺失」报 —— 否则每期固定刷同一条告警，
    真正的缺口淹没其中，闸门等于没有（本文件 2026-09-17 已因同类原因加固过一次）。
    """
    blob = ' '.join(str(rev.get(k, '')) for k in ('phase', 'reviewed_at', 'note'))
    return '静态初验' in blob


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
    errors = 0     # ERROR：必须处理（数据缺口 / 链停更 / 漏复盘）
    warns = 0      # WARN：建议看一眼（actual 不完整等）
    infos = 0      # INFO：上下文与已知例外，不影响退出码

    # 1) DRAGON BALL模型 归档缺口
    print('\n【1】DRAGON BALL模型 原文归档缺口（有交易日但无归档文件）')
    tj_missing = [d for d in days if d not in tj_dates]
    tj_real = [d for d in tj_missing if d not in KNOWN_TJ_GAPS]
    tj_known = [d for d in tj_missing if d in KNOWN_TJ_GAPS]
    if tj_real:
        for d in tj_real:
            print(f'  ⚠️ {d} 缺 DRAGON BALL模型 归档（需确认当天是否真的无 DRAGON BALL模型 新帖）')
        errors += len(tj_real)
    else:
        print('  ✅ 无新增缺口')
    if tj_known:
        print(f'  ℹ️ 已知例外 {len(tj_known)} 条（不计入问题）：'
              + '、'.join('%s→%s' % (d, KNOWN_TJ_GAPS[d]) for d in tj_known))
        infos += 1

    # 2) forecast_chain 档位缺口
    print('\n【2】forecast_chain 档位缺口（有交易日但无任何预判记录）')
    fc_missing = [d for d in days if d not in fc_dates]
    if fc_missing:
        for d in fc_missing:
            print(f'  ⚠️ {d} 无预判记录')
        errors += len(fc_missing)
    else:
        print('  ✅ 无缺口')

    # 3) 档位覆盖偏薄（INFO —— 近期既定节奏只跑晨报档，不是缺口）
    thin = [d for d in days if d in fc_dates and len(fc_dates[d]) == 1]
    print('\n【3】档位覆盖偏薄（当日仅 1 条晨报）')
    print(f'  ℹ️ {len(thin)} 天（近期既定节奏为「只跑晨报档」，非缺口；--verbose 展开）')
    infos += 1
    if verbose:
        for d in thin:
            print(f'     · {d} 仅 {fc_dates[d][0]}')

    # 4) consensus 时效
    print('\n【4】consensus_chain 时效')
    print(f'  最后一条：{cc_last}（共 {len(cchain)} 条）')
    if days and cc_last < max(days):
        print(f'  ⚠️ 停更中（最近交易日 {max(days)} 未写入）')
        errors += 1

    # 5) forecast_chain 数据完整性（按语义分流，见 is_static_precheck 说明）
    print('\n【5】forecast_chain 数据完整性（review.actual 字段）')
    bad = 0            # WARN 级：actual 确实不完整
    static, legacy = [], []   # INFO 级：设计使然 / 历史已知
    for r in fchain:
        rev = r.get('review')
        if rev is None:
            continue
        a = rev.get('actual')
        # 先判「本条 actual 是否完整」，再决定这条不完整该归哪一级
        if a is None or a is False:
            reason = '无 actual'
        elif isinstance(a, str):
            # 旧实现的两个分支都不接字符串 → 这类记录**从不被校验**（静默盲区，本轮补上）
            reason = 'actual 为字符串（旧格式），OHLC 完整性无法机器校验'
        elif isinstance(a, dict):
            miss = [k for k in ACTUAL_KEYS if a.get(k) is None]
            reason = ('缺 %s' % miss) if miss else ''
        else:
            reason = 'actual 类型异常（%s）' % type(a).__name__
        if not reason:
            continue                                   # 完整：无话可说
        if is_static_precheck(rev):
            static.append(r['id'])                     # 设计使然：静态初验不写 O/H/L/C
        elif isinstance(a, str) and r['id'] in KNOWN_ACTUAL_EXCEPTIONS:
            legacy.append(r['id'])                     # 历史已知例外（附原因）
        else:
            print(f'  ⚠️ {r["id"]}: {reason}')
            bad += 1
    if bad:
        print(f'  ⚠️ {bad} 条 actual 不完整（WARN 级）')
        warns += bad
    else:
        print('  ✅ 无异常')
    if static:
        print(f'  ℹ️ 静态初验样本 {len(static)} 条（开盘前判定，O/H/L/C 按设计不写入，不计入问题）：'
              + '、'.join(static))
        infos += 1
    if legacy:
        print(f'  ℹ️ 历史已知例外 {len(legacy)} 条（不计入问题）：'
              + '、'.join('%s→%s' % (k, KNOWN_ACTUAL_EXCEPTIONS[k]) for k in legacy))
        infos += 1

    # 6) pending 守卫（自 chain_apply 下沉：链上超过 1 条 pending 说明可能漏复盘）
    print('\n【6】pending 守卫（> 1 条即可能漏复盘上一条）')
    for name, ch in (('forecast', fchain), ('consensus', cchain)):
        pends = [r.get('id') for r in ch if r.get('status') == 'pending']
        if len(pends) > 1:
            print(f'  ⚠️ {name}: pending={len(pends)} → {", ".join(pends)}')
            errors += 1
        else:
            print(f'  ✅ {name}: pending={len(pends)}'
                  + ('（%s）' % pends[0] if pends else ''))

    # 7) 链记录 → 报告产物存在性（2026-09-18 审计 5.5）
    print('\n【7】链记录 → 报告产物（链上有记录，但 outputs 里没有对应报告）')
    needs = {}          # 期望文件名 -> [记录 id]（同日多档位/重生成会指向同一个文件）
    art_unknown = []
    for r in fchain:
        rid = r.get('id', '')
        m = re.match(r'^(\d{4}-\d{2}-\d{2})-(.+)$', rid)
        zh = TIER_BY_SUFFIX.get(m.group(2)) if m else None
        if not zh:
            art_unknown.append(rid)
            continue
        needs.setdefault('作战报告_%s_%s.md' % (zh, m.group(1)), []).append(rid)

    art_gap, art_legacy = [], []
    for fn in sorted(needs):
        if os.path.exists(os.path.join(OUT, fn)):
            continue
        d = fn[-13:-3]                                  # 文件名尾部 YYYY-MM-DD
        rec = '%s（记录 %s）' % (fn, '、'.join(needs[fn]))
        (art_gap if d >= ARTIFACT_SINCE else art_legacy).append((d, fn, rec))

    if art_gap:
        for _d, _fn, x in art_gap:
            print(f'  ⚠️ 缺报告：{x}')
        errors += len(art_gap)
    else:
        print(f'  ✅ 无缺口（{ARTIFACT_SINCE} 起逐条对应）')
    if art_legacy:
        # 与【3】同口径：历史例外只在 --verbose 下逐条展开，默认一行汇总。
        # 18 份旧文件名逐条打印，会把上面真正的缺口挤出屏幕 —— 正是本文件反复加固的问题。
        print(f'  ℹ️ 命名规范生效前（< {ARTIFACT_SINCE}）的历史例外 {len(art_legacy)} 份'
              f'（{art_legacy[0][0]} ~ {art_legacy[-1][0]}；当时报告用了别的文件名/已归档，'
              f'不计入问题；--verbose 展开）')
        if verbose:
            for _d, fn, _x in art_legacy:
                print(f'     · {fn}')
        infos += 1
    if art_unknown:
        print(f'  ℹ️ 无法映射档位的记录 id {len(art_unknown)} 个'
              f'（新后缀？需补 TIER_BY_SUFFIX）：' + '、'.join(art_unknown))
        infos += 1

    # 汇总
    print('\n' + '=' * 70)
    print(f'汇总：DRAGON BALL模型 新增缺口 {len(tj_real)}（另有已知例外 {len(tj_known)}）· '
          f'档位缺口 {len(fc_missing)} · 产物缺口 {len(art_gap)} · '
          f'ERROR {errors} · WARN {warns} · INFO {infos}')
    if errors:
        print('❌ 存在 ERROR：必须处理（见上方 ⚠️ 行）。')
    elif warns:
        print('⚠️ 无 ERROR，但有 WARN：建议看一眼。')
    else:
        print('✅ 无实质问题。')
    print('=' * 70)
    # 退出码：与 check_layout.py / fetch_zsxq.py / gen_tj_archive.py 统一（1=ERROR，2=WARN）
    return 1 if errors else (2 if warns else 0)


if __name__ == '__main__':
    sys.exit(main())
