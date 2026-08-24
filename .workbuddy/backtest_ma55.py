#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MA55（55周期均线）方向信号回测——验证 T&J 的 55 线理论作方向信号是否有效"""
import sys, os, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
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

def ma55_state(df, minute=False, asof_ts=None):
    sub = df[df['date'] <= asof_ts] if asof_ts is not None else df
    if len(sub) < 56:
        return None
    ma55 = sub['close'].rolling(55).mean().iloc[-1]
    close = float(sub['close'].iloc[-1])
    diff = (close - ma55) / ma55 * 100
    return +1 if diff > 0.3 else (-1 if diff < -0.3 else 0)

def run(ma55_mode, start, end):
    DAY = load_df('day.json'); M60 = load_df('m60.json', minute=True); M15 = load_df('m15.json', minute=True)
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if start <= d <= end]
    rows = []
    for i, T in enumerate(trade_days):
        next_day = '2026-08-24' if i + 1 >= len(trade_days) else trade_days[i + 1]
        cut = pd.Timestamp(T + ' 15:00:00')
        if ma55_mode == 'day': s = ma55_state(DAY, asof_ts=pd.Timestamp(T))
        elif ma55_mode == '60f': s = ma55_state(M60, minute=True, asof_ts=cut)
        else: s = ma55_state(M15, minute=True, asof_ts=cut)
        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty: continue
        prev = DAY[DAY['date'] == pd.Timestamp(T)]
        pc = float(prev.iloc[0]['close']) if not prev.empty else None
        pct = round((float(act.iloc[0]['close'])-pc)/pc*100,2) if pc else None
        rows.append({'T': T, 'sig': s, 'pct': pct})
    return rows

def stats(rows, label):
    n = len(rows); hit = opp = avoid = partial = none = 0
    for r in rows:
        s, pct = r['sig'], r['pct']
        if s is None or pct is None: none += 1; continue
        if s == 0:
            if abs(pct) <= 0.5: avoid += 1
            else: partial += 1
        elif s == +1 and pct > 0.15: hit += 1
        elif s == -1 and pct < -0.15: hit += 1
        elif s == +1 and pct < -0.15: opp += 1
        elif s == -1 and pct > 0.15: opp += 1
        else: partial += 1
    total = n - none
    print(f'[{label}] 样本 {n}（有效 {total}）')
    print(f'  命中率: {round(hit/total*100,1)}%  相反率: {round(opp/total*100,1)}%  规避率: {round(avoid/total*100,1)}%  部分: {round(partial/total*100,1)}%')

if __name__ == '__main__':
    print('===== MA55 方向信号回测 =====\n')
    stats(run('day', '2024-04-01', '2026-08-21'), '日线 MA55')
    print()
    stats(run('60f', '2025-11-14', '2026-08-21'), '60F MA55')
    print()
    stats(run('15f', '2026-07-28', '2026-08-21'), '15F MA55')
    print('\n对比：买卖点方向（日线版）相反率 29.8% / 命中 44.1%')
