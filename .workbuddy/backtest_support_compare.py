#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""支撑位方案对照回测：验证「支撑跌破 6 次」该用哪种支撑位最抗跌破。

4 种方案：
  A 下方55线（当前 v5）
  B 前低（最近 10 日最低 low）
  C BOLL 下轨(20,2)
  D 三者取最低（最保守）

输出每种方案的支撑守住率 + 区间覆盖，供固化决策。
"""
import sys, os, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_v5 as bv

def evaluate_support(start, end, scheme, use_15f=True):
    DAY = bv.load_df('day.json'); WEEK = bv.load_df('week.json')
    M60 = bv.load_df('m60.json', minute=True); M15 = bv.load_df('m15.json', minute=True)
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if start <= d <= end]
    rows = []
    for i, T in enumerate(trade_days):
        next_day = '2026-08-24' if i + 1 >= len(trade_days) else trade_days[i + 1]
        cut = pd.Timestamp(T + ' 15:00:00')
        close_now = float(DAY[DAY['date'] <= pd.Timestamp(T)]['close'].iloc[-1])
        d55 = bv.ma55(DAY, pd.Timestamp(T)); m60_55 = bv.ma55(M60, cut); m15_55 = bv.ma55(M15, cut) if use_15f else None
        levels = [v for v in [d55, m60_55, m15_55] if v is not None]
        b15 = bv.boll(M15, cut) if use_15f else None
        below = [v for v in levels if v < close_now]
        above = [v for v in levels if v > close_now]
        # 前低：最近 10 日最低 low（含当日）
        hist = DAY[(DAY['date'] <= pd.Timestamp(T))].tail(10)
        prev_low = float(hist['low'].min()) if len(hist) else None
        boll_low = b15['low'] if b15 else None
        boll_up = b15['up'] if b15 else None

        # 支撑位按方案选择
        if scheme == 'A':
            sup = max(below) if below else (boll_low if boll_low else None)
        elif scheme == 'B':
            sup = prev_low if prev_low and prev_low < close_now else (max(below) if below else (boll_low if boll_low else None))
        elif scheme == 'C':
            sup = boll_low if boll_low and boll_low < close_now else (max(below) if below else (prev_low if prev_low else None))
        elif scheme == 'D':
            cands = [v for v in below + [prev_low, boll_low] if v is not None and v < close_now]
            sup = min(cands) if cands else None
        else:
            sup = None
        # 压力统一：上方最近 55 线
        res = min(above) if above else (boll_up if boll_up else None)

        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty: continue
        lo = float(act.iloc[0]['low']); hi = float(act.iloc[0]['high'])
        rows.append({'T': T, 'sup': sup, 'res': res, 'lo': lo, 'hi': hi})

    n = len(rows)
    nn = sum(1 for r in rows if r['sup'] and r['res'])
    sup_hold = sum(1 for r in rows if r['sup'] and r['lo'] >= r['sup'] * 0.995)
    res_hold = sum(1 for r in rows if r['res'] and r['hi'] <= r['res'] * 1.005)
    cov = sum(1 for r in rows if r['sup'] and r['res'] and r['lo'] >= r['sup']*0.995 and r['hi'] <= r['res']*1.005)
    # 支撑平均距离（支撑离现价多远，越小越贴价）
    dists = []
    for r in rows:
        if r['sup']:
            pc = DAY[DAY['date'] == pd.Timestamp(r['T'])]
            if not pc.empty:
                dists.append((float(pc.iloc[0]['close']) - r['sup']) / float(pc.iloc[0]['close']) * 100)
    avg_dist = round(sum(dists)/len(dists), 2) if dists else None
    return {
        'n': n, 'sup_hold': round(sup_hold/n*100, 1),
        'res_hold': round(res_hold/n*100, 1),
        'coverage': round(cov/nn*100, 1) if nn else None,
        'avg_dist_pct': avg_dist,
    }

if __name__ == '__main__':
    print('===== 支撑位方案对照（60F版 188样本）=====\n')
    for scheme, name in [('A','下方55线(当前)'), ('B','前低(10日最低)'), ('C','BOLL下轨'), ('D','三者取最低')]:
        r = evaluate_support('2025-11-14', '2026-08-21', scheme, use_15f=False)
        print(f"[{scheme}] {name}: 支撑守住 {r['sup_hold']}% / 压力守住 {r['res_hold']}% / 区间覆盖 {r['coverage']}% / 支撑离现价均 {r['avg_dist_pct']}%")
