#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⑥ 信号失效机制对照回测：30天窗口(当前) vs 反向信号覆盖失效"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_v5 as bv
import pandas as pd


def evaluate_mode(start, end, use_15f, mode):
    """mode: 'window' = 30/20天窗口过滤；'override' = 最新信号永久有效（反向覆盖才失效）"""
    DAY = bv.load_df('day.json'); WEEK = bv.load_df('week.json')
    M60 = bv.load_df('m60.json', minute=True); M15 = bv.load_df('m15.json', minute=True)
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if start <= d <= end]
    rows = []
    for T in trade_days:
        after = DAY[DAY['date'] > pd.Timestamp(T)]
        if after.empty:
            continue
        next_day = after['date'].dt.strftime('%Y-%m-%d').iloc[0]
        cut = pd.Timestamp(T + ' 15:00:00')
        close_now = float(DAY[DAY['date'] <= pd.Timestamp(T)]['close'].iloc[-1])
        d55 = bv.ma55(DAY, pd.Timestamp(T)); m60_55 = bv.ma55(M60, cut)
        m15_55 = bv.ma55(M15, cut) if use_15f else None
        levels = [v for v in [d55, m60_55, m15_55] if v is not None]
        r_day = bv.run_engine_at(DAY[DAY['date'] <= pd.Timestamp(T)], 9)
        r_week = bv.run_engine_at(WEEK[WEEK['date'] <= pd.Timestamp(T)], 7)
        r_m60 = bv.run_engine_at(M60[M60['date'] <= cut], 6)
        r_m15 = bv.run_engine_at(M15[M15['date'] <= cut], 15) if use_15f else None
        cutoff_day = (pd.Timestamp(T) - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        cutoff_short = (pd.Timestamp(T) - pd.Timedelta(days=20)).strftime('%Y-%m-%d')
        trend_score = 0
        for r in (r_day, r_week):
            if r and r.get('structure'):
                t = r['structure'].get('current_trend')
                if t == '向上': trend_score += 2
                elif t == '向下': trend_score -= 2
        sig_score = 0
        for tag, r, w in [('日线', r_day, 2), ('周线', r_week, 2), ('60分钟', r_m60, 2), ('15分钟', r_m15, 1)]:
            if not r:
                continue
            if mode == 'window':
                _cut = cutoff_day if tag in ('日线', '周线') else cutoff_short
                sigs = [s for s in r.get('signals', []) if (s.get('date', '') or '') >= _cut]
            else:  # override：最新信号永久有效，反向覆盖才失效
                sigs = r.get('signals', [])
            if not sigs:
                continue
            if sigs[0]['type'] == 'buy':
                sig_score += w
            else:
                sig_score -= w
        total = trend_score + sig_score
        b15 = bv.boll(M15, cut) if use_15f else None
        bw = b15['bw'] if b15 else None
        if bw is not None and bw < 1.0:
            direction = '方向不明'
        elif total >= 3:
            direction = '偏多'
        elif total <= -3:
            direction = '偏空'
        elif abs(total) <= 1:
            direction = '方向不明'
        elif total > 0:
            direction = '震荡偏多'
        else:
            direction = '震荡偏空'
        below = [v for v in levels if v < close_now]; above = [v for v in levels if v > close_now]
        boll_low = b15['low'] if b15 else None
        boll_up = b15['up'] if b15 else None
        hist = DAY[DAY['date'] <= pd.Timestamp(T)].tail(10)
        prev_low = float(hist['low'].min()) if len(hist) else None
        sup = prev_low if (prev_low is not None and prev_low < close_now) else (boll_low if boll_low is not None else None)
        res = min(above) if above else (boll_up if boll_up is not None else None)
        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty:
            continue
        prev = DAY[DAY['date'] == pd.Timestamp(T)]
        pc = float(prev.iloc[0]['close']) if not prev.empty else None
        pct = round((float(act.iloc[0]['close']) - pc) / pc * 100, 2) if pc else None
        rows.append({'T': T, 'direction': direction, 'sup': sup, 'res': res,
                     'lo': float(act.iloc[0]['low']), 'hi': float(act.iloc[0]['high']), 'pct': pct})
    return rows


if __name__ == '__main__':
    print('===== ⑥ 信号失效机制对照回测 =====\n')
    # 60F 版（日线+60F，大样本）
    w = evaluate_mode('2025-11-14', '2026-08-21', use_15f=False, mode='window')
    o = evaluate_mode('2025-11-14', '2026-08-21', use_15f=False, mode='override')
    bv.report(w, 'A 30天窗口(当前) 60F版')
    print()
    bv.report(o, 'B 反向覆盖失效 60F版')
    print()
    # 15F 版（含15F，小样本）
    w15 = evaluate_mode('2026-07-28', '2026-08-21', use_15f=True, mode='window')
    o15 = evaluate_mode('2026-07-28', '2026-08-21', use_15f=True, mode='override')
    bv.report(w15, 'A 30天窗口(当前) 15F版')
    print()
    bv.report(o15, 'B 反向覆盖失效 15F版')
