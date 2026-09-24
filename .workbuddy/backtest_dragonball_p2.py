# -*- coding: utf-8 -*-
"""backtest_dragonball_p2.py —— DRAGONBALL 融合 P2 回测（验证预测增量）。

《DRAGONBALL_融合蓝图.md》§五：P2 定义 =「先打通数据，再回测」。数据链路已在
dragonball_p2_data.py 打通，本脚本做**回测验证增量**——三个融合点各自有没有对
后续走势的预测能力，再决定是否进打分（沿用铁律「先回测再进打分」）。

  P2-12 尾指数（篇1 尾部脆弱性）：滚动 60 日窗口估 Hill ξ（V_tail=1/ξ），
        验证「ξ 越小尾越厚 → 未来 5 日极端下跌概率越高、最差单日越深」。
  P2-10 双日体系 B（篇4 2 倍级差）：aggregate_double 聚合双日，双日级别算 MACD 六态，
        验证双日「极强/极弱」对未来 2 日（下一双日）方向的预测，对比单日级别结论。
  P2-11 集中度 Σwi²（篇2 詹森不等式）：akshare 31 个申万一级行业历史成交额，
        按日算集中度，验证「抱团（集中度高）→ 偏涨 / 切换（集中度骤降）→ 偏跌」。

数据源：本地 .workbuddy/backtest_data/day.json（405 根，2025-01-02 ~ 2026-09-02），
        P2-11 额外用 akshare 抓历史行业成交额（可 --skip-industry 跳过）。

用法：
  $PY .workbuddy/backtest_dragonball_p2.py                 # 全部（P2-11 抓 akshare，较慢）
  $PY .workbuddy/backtest_dragonball_p2.py --skip-industry # 只 P2-12 + P2-10（本地，快）
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
    rows = [x for x in rows if x == x]  # 去 NaN
    n = len(rows)
    if n == 0:
        print('  [%-30s] 样本 0' % label)
        return
    up = sum(1 for x in rows if x > thr)
    dn = sum(1 for x in rows if x < -thr)
    flat = n - up - dn
    avg = sum(rows) / n
    print('  [%-30s] n=%-4d 涨>%.1f%%: %5.1f%%  跌<-%.1f%%: %5.1f%%  平: %5.1f%%  均值 %+.3f%%'
          % (label, n, thr, up / n * 100, thr, dn / n * 100, flat / n * 100, avg))


# ============================================================================
# P2-12  尾指数：滚动 Hill ξ → 未来 5 日极端下跌
# ============================================================================

def backtest_tail(DAY):
    close = DAY['close']
    n = len(DAY)
    pct = close.pct_change() * 100          # 逐日收益率 %

    WIN = 60                                  # 滚动窗口（约 3 个月）
    FWD = 5                                   # 前瞻窗口
    EXTREME = -2.0                            # 极端单日阈值 %

    rows = []
    for i in range(WIN, n - FWD):
        win_rets = pct.iloc[i - WIN:i].tolist()
        win_rets = [x for x in win_rets if x == x]  # 去 NaN，保留原始收益率（含正负）
        if len(win_rets) < 30:
            continue
        xi = dbsig.hill_tail_index(win_rets)['xi']  # hill 内部自己取「下跌尾」
        if xi is None:
            continue
        fwd = pct.iloc[i + 1:i + 1 + FWD].tolist()
        fwd = [x for x in fwd if x == x]
        if len(fwd) < FWD:
            continue
        cum = 1.0
        for r in fwd:
            cum *= (1 + r / 100.0)
        rows.append({
            'xi': xi,
            'v_tail': 1.0 / xi,
            'worst_day': min(fwd),            # 未来 5 日最差单日 %
            'cum5': (cum - 1) * 100,          # 未来 5 日累计 %
            'extreme': 1 if min(fwd) < EXTREME else 0,  # 是否出现极端日
        })

    if not rows:
        print('  无有效滚动窗口')
        return
    rdf = pd.DataFrame(rows)
    med = rdf['xi'].median()
    thick = rdf[rdf['xi'] <= med]             # 厚尾组（ξ 低）
    thin = rdf[rdf['xi'] > med]               # 薄尾组（ξ 高）

    print('  滚动窗口 %d 日 · 前瞻 %d 日 · 极端阈值 %.1f%% · 有效窗口 %d 个' % (WIN, FWD, EXTREME, len(rdf)))
    print('  ξ 中位数 = %.4f（V_tail = %.3f）' % (med, 1.0 / med))
    print('')
    print('  ── 厚尾组（ξ ≤ %.4f，尾厚/脆弱） n=%d ──' % (med, len(thick)))
    print('    未来 5 日最差单日均值 : %+.3f%%' % thick['worst_day'].mean())
    print('    未来 5 日累计收益均值 : %+.3f%%' % thick['cum5'].mean())
    print('    出现极端日(<%.1f%%)概率 : %.1f%%' % (EXTREME, thick['extreme'].mean() * 100))
    print('  ── 薄尾组（ξ > %.4f，尾薄/稳健） n=%d ──' % (med, len(thin)))
    print('    未来 5 日最差单日均值 : %+.3f%%' % thin['worst_day'].mean())
    print('    未来 5 日累计收益均值 : %+.3f%%' % thin['cum5'].mean())
    print('    出现极端日(<%.1f%%)概率 : %.1f%%' % (EXTREME, thin['extreme'].mean() * 100))

    # 顶/底 20% 对比（更极端的尾厚 vs 尾薄）
    q20 = rdf['xi'].quantile(0.2)
    q80 = rdf['xi'].quantile(0.8)
    top_thick = rdf[rdf['xi'] <= q20]         # 最厚尾 20%
    top_thin = rdf[rdf['xi'] >= q80]          # 最薄尾 20%
    print(f'  ── 最厚尾 20%（xi ≤ {q20:.4f}） n={len(top_thick)} vs 最薄尾 20%（xi ≥ {q80:.4f}） n={len(top_thin)} ──')
    print(f'    极端日概率 : {top_thick["extreme"].mean() * 100:5.1f}%  vs  {top_thin["extreme"].mean() * 100:5.1f}%')
    print(f'    最差单日均 : {top_thick["worst_day"].mean():+.3f}%  vs  {top_thin["worst_day"].mean():+.3f}%')
    print(f'    累计 5 日均: {top_thick["cum5"].mean():+.3f}%  vs  {top_thin["cum5"].mean():+.3f}%')


# ============================================================================
# P2-10  双日体系 B：双日 MACD 六态 → 未来 2 日
# ============================================================================

def backtest_double(DAY):
    rows = [{'date': str(r['date']), 'open': float(r['open']), 'close': float(r['close']),
             'high': float(r['high']), 'low': float(r['low']), 'vol': float(r['vol'])}
            for _, r in DAY.iterrows()]
    dbl = dbsig.aggregate_double(rows)
    if not dbl:
        print('  双日聚合为空')
        return

    ddf = pd.DataFrame(dbl)
    close = ddf['close'].astype(float)
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    dif = e12 - e26
    dea = dif.ewm(span=9, adjust=False).mean()

    states = [dbsig.classify_macd_state(float(dif.iloc[i]), float(dea.iloc[i]))['state']
              for i in range(len(ddf))]

    next_pct = (close.shift(-1) - close) / close * 100  # 双日 i → 双日 i+1（≈未来 2 日）

    g = {k: [] for k in ('极强', '强', '中性偏强', '中性偏弱', '弱', '极弱', 'cross')}
    cnt = {k: 0 for k in g}
    for i in range(1, len(ddf) - 1):
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        s = states[i]
        if s in g:
            g[s].append(pct)
            cnt[s] += 1

    print('  双日级别根数 %d（日线 %d 根聚合）· 六态对未来 2 日方向' % (len(ddf), len(DAY)))
    for k in ('极强', '强', '中性偏强', '中性偏弱', '弱', '极弱'):
        stat(g[k], '双日' + k + '→未来2日', thr=0.2)
    print('  对照：单日级别 MACD 六态「极强」→ 次日 = 52.4%%涨 vs 28.6%%跌（P1-7 结论，趋势延续）')
    print('  （双日阈值取 0.2%%：2 日累计，幅度门槛略高于单日 0.1%%）')


def main():
    DAY = load_day()
    print('=' * 74)
    print('DRAGONBALL 融合 P2 回测 · 预测增量验证（上证综指 000001 日线 %d 根）' % len(DAY))
    print('样本 %s ~ %s' % (DAY['date'].iloc[0].date(), DAY['date'].iloc[-1].date()))
    print('=' * 74)

    print('\n【P2-12】尾指数 V_tail=1/ξ：滚动 Hill ξ → 未来 5 日极端下跌')
    backtest_tail(DAY)

    print('\n【P2-10】双级差体系 B：双日 MACD 六态 → 未来 2 日')
    backtest_double(DAY)

    print('\n' + '=' * 74)
    print('判读：')
    print('  P2-12 若「厚尾组极端日概率/最差单日显著 > 薄尾组」，则尾指数有风险预警增量，')
    print('        可作为「风险提示」定量字段；否则仅作叙事层参考。')
    print('  P2-10 若双日极强/极弱方向与单日级别一致（趋势延续）且样本≥20，则体系 B 交叉确认')
    print('        有价值；否则体系 B 不增加信息、降级为旁路。')
    print('=' * 74)


if __name__ == '__main__':
    main()
