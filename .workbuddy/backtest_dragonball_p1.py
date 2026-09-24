# -*- coding: utf-8 -*-
"""backtest_dragonball_p1.py —— DRAGONBALL 融合 P1 回测（篇4 MACD 六态口径）。

验证三件事（《DRAGONBALL_融合蓝图.md》§四）：
  P1-7  「持续极强」看空优势：用**篇4 MACD 六态精确判据**（DIF≥0 且 DEA≤0 且多头）重新验证，
        对比旧「价格加速」口径（backtest_tj_v2 结论：持续极强 32.8%涨 vs 46.6%跌）。
  P1-8  「极强」形态的分布与方向：六态各自对「次日方向」的涨/跌率（预期与旧口径一致：无独立增量）。
  P1-9  「极强形态下顶背离失效」：篇4 特征1——N+2 极强加持的主涨段下，小级别顶背离阶段性无效。
        简化验证：state=极强 且 价格创近 N 日新高但 DIF 未同步新高（=顶背离）→ 次日是否仍偏涨。

口径与 v5 一致：T 日收盘出信号 → 预测 T+1。只用截至 T 的数据算 DIF/DEA（ewm 因果，无未来函数）。
数据源：.workbuddy/backtest_data/day.json（405 根，2025-01-02 ~ 2026-09-02）。

用法：
  $PY .workbuddy/backtest_dragonball_p1.py
"""
import importlib.util
import json
import os
import sys

import pandas as pd

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.join(HERE, 'backtest_data')

spec = importlib.util.spec_from_file_location(
    'dbsig', os.path.join(HERE, 'dragonball_signals.py'))
dbsig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbsig)


def load_day():
    rows = json.load(open(os.path.join(BT, 'day.json'), encoding='utf-8'))
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'].astype(str), errors='coerce')
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)


def stat(rows, label, thr=0.10):
    n = len(rows)
    if n == 0:
        print('  [%-28s] 样本 0' % label)
        return
    up = sum(1 for x in rows if x > thr)
    dn = sum(1 for x in rows if x < -thr)
    flat = n - up - dn
    avg = sum(rows) / n
    print('  [%-28s] n=%-4d 涨>%.1f%%: %5.1f%%  跌<-%.1f%%: %5.1f%%  平: %5.1f%%  均值 %+.3f%%'
          % (label, n, thr, up / n * 100, thr, dn / n * 100, flat / n * 100, avg))


def main():
    DAY = load_day()
    close = DAY['close']
    n = len(DAY)

    # 篇4 精确口径的 DIF/DEA（ewm adjust=False 与 calc_tech 手工 EMA 同参，因果无未来函数）
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    dif = e12 - e26
    dea = dif.ewm(span=9, adjust=False).mean()

    next_pct = (close.shift(-1) - close) / close * 100

    # 逐日算六态
    states = []
    for i in range(n):
        states.append(dbsig.classify_macd_state(float(dif.iloc[i]), float(dea.iloc[i]))['state'])

    print('=' * 74)
    print('DRAGONBALL 融合 P1 回测 · 篇4 MACD 六态精确口径（上证综指 000001 日线）')
    print('样本 %d 根  %s ~ %s' % (n, DAY['date'].iloc[0].date(), DAY['date'].iloc[-1].date()))
    print('=' * 74)

    # ── P1-8：六态分布 + 次日方向 ──
    print('\n【P1-8】六态分布 与 六态 → 次日方向')
    g = {k: [] for k in ('极强', '强', '中性偏强', '中性偏弱', '弱', '极弱', 'cross')}
    cnt = {k: 0 for k in g}
    for i in range(1, n - 1):
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        s = states[i]
        if s in g:
            g[s].append(pct)
            cnt[s] += 1
    total = sum(cnt.values())
    print('  六态出现次数（T 日，可预测 T+1 的样本）：')
    for k in ('极强', '强', '中性偏强', '中性偏弱', '弱', '极弱', 'cross'):
        print('    %-8s %4d 次（%5.1f%%）' % (k, cnt[k], cnt[k] / total * 100))
    for k in ('极强', '强', '中性偏强', '中性偏弱', '弱', '极弱'):
        stat(g[k], '次日方向·' + k)

    # ── P1-7：持续极强（MACD 六态口径）──
    print('\n【P1-7】持续极强（连续 ≥2 日 MACD 六态=极强）→ 次日方向')
    sw = {'进入极强': [], '持续极强': [], '解除极强': []}
    for i in range(2, n - 1):
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        s, sp = states[i], states[i - 1]
        if s == '极强' and sp != '极强':
            sw['进入极强'].append(pct)
        elif s == '极强' and sp == '极强':
            sw['持续极强'].append(pct)
        elif sp == '极强' and s != '极强':
            sw['解除极强'].append(pct)
    for k, v in sw.items():
        stat(v, k)
    print('  对照：旧「价格加速」口径 持续极强 = 32.8%涨 vs 46.6%跌（1 日级别动量衰竭）')

    # ── P1-9：极强形态下顶背离是否失效 ──
    print('\n【P1-9】极强形态下的「顶背离」（价格创 20 日新高但 DIF 未新高）→ 次日方向')
    hi20 = DAY['high'].rolling(20).max().shift(1)   # 截至前一日 20 日新高
    dif_hi20 = dif.rolling(20).max().shift(1)
    div = {'极强+顶背离': [], '极强+非背离': [], '非极强+顶背离': []}
    for i in range(30, n - 1):
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        s = states[i]
        price_new_high = DAY['high'].iloc[i] > hi20.iloc[i]
        dif_not_new_high = dif.iloc[i] < dif_hi20.iloc[i]
        if s == '极强' and price_new_high and dif_not_new_high:
            div['极强+顶背离'].append(pct)
        elif s == '极强':
            div['极强+非背离'].append(pct)
        elif price_new_high and dif_not_new_high:
            div['非极强+顶背离'].append(pct)
    for k, v in div.items():
        stat(v, k)

    print('\n' + '=' * 74)
    print('判读口径：v5 基线方向相反率约 28~30%。若「持续极强」跌率显著 > 涨率且样本≥30，')
    print('          则支持「MACD 六态口径的持续极强 = 短线看空辅助信号」；否则与旧口径结论一致、')
    print('          仍只作旁路标注，不进方向打分。')
    print('=' * 74)


if __name__ == '__main__':
    main()
