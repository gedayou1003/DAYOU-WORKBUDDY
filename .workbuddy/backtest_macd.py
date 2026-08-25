#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MACD(12,26,9) 日线死叉/金叉/底背离 对方向的预测能力回测。

验证 T&J 的"日线死叉"因子是否值得纳入方向打分：
  1. 日线 MACD 死叉/金叉后，次日涨跌方向
  2. 底背离（价新低但 DIF 不新低）后，是否反弹（下跌衰竭）
"""
import sys, os, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_v5 as bv

def macd(df):
    """计算 MACD(12,26,9)：返回 DIF, DEA, HIST"""
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = (dif - dea) * 2  # 柱状图
    return dif, dea, hist

def main():
    DAY = bv.load_df('day.json')
    DAY = DAY.reset_index(drop=True)
    dif, dea, hist = macd(DAY)
    DAY['dif'] = dif; DAY['dea'] = dea; DAY['hist'] = hist
    # 死叉/金叉状态
    DAY['cross'] = 0  # 0=无, +1=金叉, -1=死叉
    prev_dif = dif.shift(1); prev_dea = dea.shift(1)
    DAY.loc[(prev_dif > prev_dea) & (dif < dea), 'cross'] = -1  # 死叉
    DAY.loc[(prev_dif < prev_dea) & (dif > dea), 'cross'] = 1   # 金叉

    start = '2025-11-14'
    d = DAY[DAY['date'] >= pd.Timestamp(start)].reset_index(drop=True)
    print(f'样本区间 {start} ~ 2026-08-21，共 {len(d)} 交易日\n')

    # 1. 死叉/金叉后次日方向
    print('=== 1. MACD 日线 死叉/金叉 后次日涨跌 ===')
    for label, mask in [('死叉次日', d['cross'].shift(1) == -1), ('金叉次日', d['cross'].shift(1) == 1)]:
        sub = d[mask]
        if len(sub) == 0:
            print(f'  {label}: 无样本'); continue
        up = (sub['close'] > sub['close'].shift(1)).sum()
        dn = (sub['close'] < sub['close'].shift(1)).sum()
        print(f'  {label}: {len(sub)} 次 | 涨 {up} / 跌 {dn} | 涨率 {up/len(sub)*100:.0f}%')

    # 2. 死叉状态持续期（死叉后 DIF<DEA 期间）的整体方向
    print('\n=== 2. DIF 在 DEA 下方（空头区）vs 上方（多头区）次日涨跌 ===')
    for label, mask in [('空头区(DIF<DEA)', d['dif'] < d['dea']), ('多头区(DIF>DEA)', d['dif'] > d['dea'])]:
        sub = d[mask]
        nxt = sub['close'].shift(-1)
        up = (nxt > sub['close']).sum(); dn = (nxt < sub['close']).sum()
        print(f'  {label}: {len(sub)} 日 | 次日涨 {up} / 跌 {dn} | 涨率 {up/len(sub)*100:.0f}%')

    # 3. 底背离（价创近20日新低但 DIF 不创新低）后 3 日反弹
    print('\n=== 3. 底背离（价创新低但 DIF 不新低）后 3 日反弹 ===')
    low20 = d['low'].rolling(20).min()
    dif_low20 = d['dif'].rolling(20).min()
    diverge = (d['low'] <= low20.shift(1)) & (d['dif'] > dif_low20.shift(1)) & (d['dif'] < d['dea'])
    sub = d[diverge]
    print(f'  底背离信号: {len(sub)} 次')
    if len(sub):
        # 信号后 3 日累计涨跌
        for horizon in [1, 3]:
            fwd = d['close'].shift(-horizon)
            ret = (fwd - d['close']) / d['close'] * 100
            sig_ret = ret[diverge]
            print(f'  信号后 {horizon} 日: 平均涨跌 {sig_ret.mean():+.2f}% | 上涨占比 {(sig_ret>0).sum()}/{len(sig_ret)}')

    # 4. 对照组：无背离的"破位新低"后 3 日
    print('\n=== 4. 对照：无底背离的破位新低（价新低且 DIF 也新低）后 3 日 ===')
    break_no_div = (d['low'] <= low20.shift(1)) & (d['dif'] <= dif_low20.shift(1)) & (d['dif'] < d['dea'])
    sub = d[break_no_div]
    print(f'  破位新低(无背离): {len(sub)} 次')
    if len(sub):
        fwd = d['close'].shift(-3)
        ret = (fwd - d['close']) / d['close'] * 100
        sig_ret = ret[break_no_div]
        print(f'  信号后 3 日: 平均涨跌 {sig_ret.mean():+.2f}% | 上涨占比 {(sig_ret>0).sum()}/{len(sig_ret)}')

if __name__ == '__main__':
    main()
