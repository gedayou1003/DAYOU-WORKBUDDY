#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多周期预判回测：60分钟版（~10个月）+ 日线版（~1.5年）
用最大可取 K 线根数，v4/v5 预判规则
"""
import sys, os, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = r"C:\Users\gedayou\.workbuddy\skills\chan-signal__skillhub"
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine, build_analysis

CODE = '000001'
BT = os.path.join(HERE, 'backtest_data')

def load_df(name, minute=False):
    rows = json.load(open(os.path.join(BT, name), encoding='utf-8'))
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)
    df['amount'] = df['vol']
    if minute:
        df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d%H%M', errors='coerce')
    else:
        df['date'] = pd.to_datetime(df['date'].astype(str), errors='coerce')
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def boll(df, n=20, k=2):
    if df is None or len(df) < n + 1:
        return None
    mid = df['close'].rolling(n).mean(); std = df['close'].rolling(n).std()
    up = mid + k * std; low = mid - k * std
    return {'up': float(up.iloc[-1]), 'mid': float(mid.iloc[-1]), 'low': float(low.iloc[-1]),
            'bw': float(((up - low) / mid * 100).iloc[-1])}

def run_periods(periods, T):
    results = {}
    cut = pd.Timestamp(T + ' 15:00:00')
    for tag, cat, df, w in periods:
        sub = df[df['date'] <= cut] if tag == '60分钟' else df[df['date'] <= pd.Timestamp(T)]
        if sub is None or len(sub) < 30:
            results[tag] = None
            continue
        try:
            eng = run_engine(sub)
            results[tag] = build_analysis(CODE, sub, eng, cat, recent_bars=0)
        except Exception:
            results[tag] = None
    return results

def predict(results, periods, asof_date, boll_res):
    cutoff = (pd.Timestamp(asof_date) - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
    trend_score = 0
    for tag, cat, df, w in periods:
        if tag not in ('日线', '周线'):
            continue
        r = results.get(tag)
        if r and r.get('structure'):
            t = r['structure'].get('current_trend')
            if t == '向上': trend_score += 2
            elif t == '向下': trend_score -= 2
    sig_score = 0; buys, sells = [], []
    for tag, cat, df, w in periods:
        r = results.get(tag)
        if not r: continue
        sigs = [s for s in r.get('signals', []) if (s.get('date', '') or '') >= cutoff]
        if not sigs: continue
        if sigs[0]['type'] == 'buy':
            sig_score += w; buys.append((sigs[0]['price'], sigs[0]['name'], tag))
        else:
            sig_score -= w; sells.append((sigs[0]['price'], sigs[0]['name'], tag))
    total = trend_score + sig_score
    bw = boll_res['bw'] if boll_res else None
    if bw is not None and bw < 1.0: direction = '方向不明'
    elif total >= 3: direction = '偏多'
    elif total <= -3: direction = '偏空'
    elif abs(total) <= 1: direction = '方向不明'
    elif total > 0: direction = '震荡偏多'
    else: direction = '震荡偏空'
    prio = {'15分钟': 0, '60分钟': 1, '日线': 2, '周线': 3}
    sup = min(buys, key=lambda x: prio.get(x[2], 9))[0] if buys else None
    res = min(sells, key=lambda x: prio.get(x[2], 9))[0] if sells else None
    if sup is None and boll_res: sup = boll_res['low']
    if res is None and boll_res: res = boll_res['up']
    return {'direction': direction, 'support': sup, 'resistance': res}

def judge(pred, actual):
    pct = actual['pct']; d = pred['direction']
    lo, hi = actual['low'], actual['high']; sup, res = pred['support'], pred['resistance']
    if d == '方向不明': dir_v = '✅规避' if (pct is not None and abs(pct) <= 0.5) else '⚠️未给方向'
    elif d in ('偏多','震荡偏多') and pct > 0.15: dir_v = '✅命中'
    elif d in ('偏空','震荡偏空') and pct < -0.15: dir_v = '✅命中'
    elif d in ('偏多','震荡偏多') and pct < -0.15: dir_v = '❌相反'
    elif d in ('偏空','震荡偏空') and pct > 0.15: dir_v = '❌相反'
    else: dir_v = '⚠️部分'
    range_v = '✅' if (sup is not None and res is not None and lo >= sup*0.995 and hi <= res*1.005) else '—'
    sup_v = ('✅守' if lo >= sup*0.995 else '❌破') if sup is not None else '—'
    res_v = ('✅守' if hi <= res*1.005 else '❌破') if res is not None else '—'
    return {'direction': dir_v, 'range': range_v, 'support': sup_v, 'resistance': res_v}

def run(mode):
    DAY = load_df('day.json'); WEEK = load_df('week.json'); M60 = load_df('m60.json', minute=True)
    if mode == '60f':
        periods = [('日线', 9, DAY, 2), ('周线', 7, WEEK, 2), ('60分钟', 6, M60, 2)]
        boll_df = M60; start = '2025-11-14'
    else:
        periods = [('日线', 9, DAY, 2), ('周线', 7, WEEK, 2)]
        boll_df = DAY; start = '2024-04-01'
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if start <= d <= '2026-08-21']
    rows = []
    for i, T in enumerate(trade_days):
        next_day = '2026-08-24' if i + 1 >= len(trade_days) else trade_days[i + 1]
        results = run_periods(periods, T)
        cut = pd.Timestamp(T + ' 15:00:00')
        boll_res = boll(boll_df[boll_df['date'] <= cut])
        pred = predict(results, periods, T, boll_res)
        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty: continue
        a = act.iloc[0]
        prev = DAY[DAY['date'] == pd.Timestamp(T)]
        pc = float(prev.iloc[0]['close']) if not prev.empty else None
        actual = {'date': next_day, 'low': float(a['low']), 'high': float(a['high']),
                  'close': float(a['close']), 'pct': round((float(a['close'])-pc)/pc*100,2) if pc else None}
        rows.append({'T': T, 'next': next_day, 'pred': pred, 'actual': actual, 'verdict': judge(pred, actual)})
    return rows

def stats(rows):
    n = len(rows)
    hit = sum(1 for r in rows if '✅' in r['verdict']['direction'])
    opp = sum(1 for r in rows if '❌' in r['verdict']['direction'])
    avoid = sum(1 for r in rows if '规避' in r['verdict']['direction'])
    range_hit = sum(1 for r in rows if r['verdict']['range'] == '✅')
    sup_hold = sum(1 for r in rows if r['verdict']['support'] == '✅守')
    res_hold = sum(1 for r in rows if r['verdict']['resistance'] == '✅守')
    return {'n': n, 'dir_accuracy': round(hit/n*100,1), 'dir_opposite': round(opp/n*100,1),
            'dir_avoid': round(avoid/n*100,1), 'range_accuracy': round(range_hit/n*100,1),
            'sup_hold': round(sup_hold/n*100,1), 'res_hold': round(res_hold/n*100,1)}

if __name__ == '__main__':
    os.makedirs(BT, exist_ok=True)
    for mode, label in [('60f', '60分钟版'), ('day', '日线版')]:
        rows = run(mode)
        st = stats(rows)
        print(f'===== {label}（{mode}）=====')
        print(f'样本: {st["n"]} 个交易日（{rows[0]["T"] if rows else "-"} ~ {rows[-1]["T"] if rows else "-"}）')
        print(f'方向命中率: {st["dir_accuracy"]}%  相反率: {st["dir_opposite"]}%  规避率: {st["dir_avoid"]}%')
        print(f'区间覆盖率: {st["range_accuracy"]}%  支撑守住: {st["sup_hold"]}%  压力守住: {st["res_hold"]}%')
        json.dump({'stats': st, 'rows': rows}, open(os.path.join(BT, f'backtest_result_{mode}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
        print()
