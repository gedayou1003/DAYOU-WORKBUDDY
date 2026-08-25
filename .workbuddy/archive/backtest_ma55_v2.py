#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MA55 作为「关键位」（支撑/压力）的有效性回测——验证 T&J 的 55 线真正用法"""
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

def ma55(df, asof):
    sub = df[df['date'] <= asof]
    return float(sub['close'].rolling(55).mean().iloc[-1]) if len(sub) >= 56 else None

def run_engine_at(df, cat):
    if df is None or len(df) < 30: return None
    try: return build_analysis(CODE, df, run_engine(df), cat, recent_bars=0)
    except Exception: return None

def evaluate(start, end, use_15f=True):
    DAY = load_df('day.json'); WEEK = load_df('week.json'); M60 = load_df('m60.json', minute=True); M15 = load_df('m15.json', minute=True)
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if start <= d <= end]
    rows = []
    for i, T in enumerate(trade_days):
        next_day = '2026-08-24' if i + 1 >= len(trade_days) else trade_days[i + 1]
        cut = pd.Timestamp(T + ' 15:00:00')
        close_now = float(DAY[DAY['date'] <= pd.Timestamp(T)]['close'].iloc[-1])
        levels = [v for v in [ma55(DAY, pd.Timestamp(T)), ma55(M60, cut), ma55(M15, cut) if use_15f else None] if v is not None]
        below = [v for v in levels if v < close_now]; above = [v for v in levels if v > close_now]
        sup55 = max(below) if below else None; res55 = min(above) if above else None
        df_day = DAY[DAY['date'] <= pd.Timestamp(T)]; df_week = WEEK[WEEK['date'] <= pd.Timestamp(T)]
        df_m60 = M60[M60['date'] <= cut]; df_m15 = M15[M15['date'] <= cut]
        cutoff = (pd.Timestamp(T) - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        buys, sells = [], []
        prio = {'15分钟':0, '60分钟':1, '日线':2, '周线':3}
        for tag, r in [('日线', run_engine_at(df_day,9)), ('周线', run_engine_at(df_week,7)), ('60分钟', run_engine_at(df_m60,6)), ('15分钟', run_engine_at(df_m15,15) if use_15f else None)]:
            if not r: continue
            sigs = [s for s in r.get('signals', []) if (s.get('date','') or '') >= cutoff]
            if not sigs: continue
            if sigs[0]['type'] == 'buy': buys.append((sigs[0]['price'], tag))
            else: sells.append((sigs[0]['price'], tag))
        sup_bs = min(buys, key=lambda x: prio.get(x[1],9))[0] if buys else None
        res_bs = min(sells, key=lambda x: prio.get(x[1],9))[0] if sells else None
        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty: continue
        lo, hi = float(act.iloc[0]['low']), float(act.iloc[0]['high'])
        rows.append({'sup55': sup55, 'res55': res55, 'sup_bs': sup_bs, 'res_bs': res_bs, 'lo': lo, 'hi': hi})
    return rows

def report(rows, label):
    n = len(rows)
    c55 = sum(1 for r in rows if r['sup55'] and r['res55'] and r['lo'] >= r['sup55']*0.995 and r['hi'] <= r['res55']*1.005)
    n55 = sum(1 for r in rows if r['sup55'] and r['res55'])
    cbs = sum(1 for r in rows if r['sup_bs'] and r['res_bs'] and r['lo'] >= r['sup_bs']*0.995 and r['hi'] <= r['res_bs']*1.005)
    nbs = sum(1 for r in rows if r['sup_bs'] and r['res_bs'])
    print(f'[{label}] 样本 {n}')
    if n55: print(f'  55线区间覆盖: {c55}/{n55} = {round(c55/n55*100,1)}%')
    if nbs: print(f'  买卖点区间覆盖: {cbs}/{nbs} = {round(cbs/nbs*100,1)}%')

if __name__ == '__main__':
    print('===== 55 线 vs 买卖点：谁更能框住次日走势 =====\n')
    report(evaluate('2025-11-14', '2026-08-21', use_15f=False), '60F 版区间（日线55+60F55，~10个月）')
    print()
    report(evaluate('2026-07-28', '2026-08-21', use_15f=True), '15F 版区间（含 15F55，1个月）')
