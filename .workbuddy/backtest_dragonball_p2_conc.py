# -*- coding: utf-8 -*-
"""backtest_dragonball_p2_conc.py —— DRAGONBALL 融合 P2-11 集中度回测（篇2 詹森不等式）。

验证篇2 两条结论（《DRAGONBALL_方法论.md》§1.6·A）：
  结论 A：抱团（资金集中）→ 推高 A 股总市值（f 严格凸增 → 偏涨）
  结论 B：切换（资金分散）→ 必然引发下跌（「必然不存在丝滑无伤的高低切换」）

落地口径：31 个申万一级行业的**当日成交额占比**作为「资金权重 wi」的近似，
  集中度 = Σwi²（concentration 函数，篇2 E[X]=Σwi²）。用上证综指作「总市值」代理。

两个回测切面：
  (1) 集中度**水平**：当日 Σwi² 高（抱团）vs 低（分散）→ 次日 / 未来 5 日涨跌；
  (2) 集中度**变化**：Σwi² 较前一日上升（抱团加强）vs 下降（切换/分散）→ 次日涨跌。

数据源：akshare index_hist_sw 抓 31 行业历史成交额（缓存 .workbuddy/backtest_data/
        industry_amount_history.json）；上证行情用本地 day.json。

用法：
  $PY .workbuddy/backtest_dragonball_p2_conc.py                # 抓取（无缓存时）+ 回测
  $PY .workbuddy/backtest_dragonball_p2_conc.py --no-fetch     # 只用缓存回测
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
CACHE = os.path.join(BT, 'industry_amount_history.json')

spec = importlib.util.spec_from_file_location(
    'dbsig', os.path.join(HERE, 'dragonball_signals.py'))
dbsig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbsig)

INDUSTRY_CODES = ["801010", "801030", "801040", "801050", "801080", "801110", "801120",
                  "801130", "801140", "801150", "801160", "801170", "801180", "801200",
                  "801210", "801230", "801710", "801720", "801730", "801740", "801750",
                  "801760", "801770", "801780", "801790", "801880", "801890", "801950",
                  "801960", "801970", "801980"]


def fetch_history():
    """抓 31 行业历史成交额 → {date_str: [amount, ...]}（对齐的日期才能有 31 个）。"""
    import akshare as ak
    per_date = {}
    ok = 0
    for code in INDUSTRY_CODES:
        try:
            df = ak.index_hist_sw(symbol=code, period='day')
            df.columns = ['code', 'date', 'close', 'open', 'high', 'low', 'volume', 'amount']
            for _, r in df.iterrows():
                d = str(r['date'])
                amt = float(r['amount']) if r['amount'] is not None else None
                if amt is None:
                    continue
                per_date.setdefault(d, {})[code] = amt
            ok += 1
        except Exception as e:
            print('[WARN] 行业 %s 抓取失败：%s' % (code, e), file=sys.stderr)
    print('抓取完成：%d/%d 行业成功' % (ok, len(INDUSTRY_CODES)))
    return per_date


def load_history(force_fetch):
    if not force_fetch and os.path.exists(CACHE):
        return json.load(open(CACHE, encoding='utf-8'))
    per_date = fetch_history()
    json.dump(per_date, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    return per_date


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
        print('  [%-32s] 样本 0' % label)
        return
    up = sum(1 for x in rows if x > thr)
    dn = sum(1 for x in rows if x < -thr)
    flat = n - up - dn
    avg = sum(rows) / n
    print('  [%-32s] n=%-4d 涨>%.1f%%: %5.1f%%  跌<-%.1f%%: %5.1f%%  平: %5.1f%%  均值 %+.3f%%'
          % (label, n, thr, up / n * 100, thr, dn / n * 100, flat / n * 100, avg))


def main():
    force_fetch = '--no-fetch' not in sys.argv
    print('=' * 74)
    print('DRAGONBALL 融合 P2-11 集中度回测 · 篇2 詹森不等式（Σwi²）')
    print('=' * 74)

    per_date = load_history(force_fetch)
    # 每日集中度（只用当日有 >=10 个行业成交额的日期，避免行业缺失干扰）
    daily_conc = {}
    for d, amts in per_date.items():
        vals = list(amts.values())
        if len(vals) >= 10:
            daily_conc[d] = dbsig.concentration(vals)['concentration']
    print('有效日期（>=10 行业）：%d 个' % len(daily_conc))
    if not daily_conc:
        print('[FAIL] 无有效行业数据')
        return 1

    DAY = load_day()
    # 把集中度按上证交易日对齐
    DAY['dstr'] = DAY['date'].dt.strftime('%Y-%m-%d')
    DAY['conc'] = DAY['dstr'].map(daily_conc)
    DAY['conc_chg'] = DAY['conc'].diff()
    close = DAY['close']
    DAY['next_pct'] = (close.shift(-1) - close) / close * 100
    DAY['fwd5'] = (close.shift(-5) - close) / close * 100

    sub = DAY.dropna(subset=['conc', 'next_pct']).copy()
    print('对齐后有效样本：%d 个交易日\n' % len(sub))

    # ── 切面 1：集中度水平 ──
    med = sub['conc'].median()
    hi = sub[sub['conc'] >= med]
    lo = sub[sub['conc'] < med]
    print('【切面1】集中度水平 → 次日 / 未来5日（中位数 %.4f）' % med)
    print('  ── 高集中度组（抱团，Σwi² ≥ %.4f） n=%d ──' % (med, len(hi)))
    stat(hi['next_pct'].tolist(), '高集中→次日', thr=0.10)
    stat(hi['fwd5'].tolist(), '高集中→未来5日', thr=0.3)
    print('  ── 低集中度组（分散，Σwi² < %.4f） n=%d ──' % (med, len(lo)))
    stat(lo['next_pct'].tolist(), '低集中→次日', thr=0.10)
    stat(lo['fwd5'].tolist(), '低集中→未来5日', thr=0.3)

    # ── 切面 2：集中度变化（切换 vs 抱团加强）──
    sub2 = sub.dropna(subset=['conc_chg'])
    upc = sub2[sub2['conc_chg'] >= 0]
    dnc = sub2[sub2['conc_chg'] < 0]
    print('\n【切面2】集中度变化 → 次日（+ = 抱团加强，- = 切换/分散）')
    stat(upc['next_pct'].tolist(), '集中度上升→次日', thr=0.10)
    stat(dnc['next_pct'].tolist(), '集中度下降(切换)→次日', thr=0.10)
    stat(upc['fwd5'].tolist(), '集中度上升→未来5日', thr=0.3)
    stat(dnc['fwd5'].tolist(), '集中度下降(切换)→未来5日', thr=0.3)

    # ── 极端切换：集中度降幅 top 20% ──
    q20 = sub2['conc_chg'].quantile(0.2)
    big_drop = sub2[sub2['conc_chg'] <= q20]
    print('\n【切面3】集中度骤降（降幅最低 20%%，阈值 %+.4f）→ 次日/未来5日' % q20)
    stat(big_drop['next_pct'].tolist(), '集中度骤降→次日', thr=0.10)
    stat(big_drop['fwd5'].tolist(), '集中度骤降→未来5日', thr=0.3)

    print('\n' + '=' * 74)
    print('判读（篇2）：')
    print('  结论 A「抱团推高」成立 ⟺ 高集中度组次日/未来5日 显著偏涨；')
    print('  结论 B「切换必跌」成立 ⟺ 集中度下降（尤其骤降）组 显著偏跌。')
    print('  若两者均无显著增量，则集中度（行业成交额口径）只作叙事层参考，不进打分。')
    print('=' * 74)
    return 0


if __name__ == '__main__':
    sys.exit(main())
