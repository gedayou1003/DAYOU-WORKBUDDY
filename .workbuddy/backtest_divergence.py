#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""级别间背离回测：日线死叉（回调压力）下，小级别逆势强势是否是看多信号。

验证 T&J「该跌不跌就是强」：
  日线 MACD 空头区（DIF<DEA，有回调压力）+ 60F 站上 MA55（逆势强势）
  vs 日线空头区 + 60F 在 MA55 下方（顺势弱势）
  后续 N 日涨跌差异。
"""
import sys, os, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_v5 as bv

def macd(df):
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    return dif, dea

def main():
    DAY = bv.load_df('day.json').reset_index(drop=True)
    M60 = bv.load_df('m60.json', minute=True).reset_index(drop=True)
    dif, dea = macd(DAY)
    DAY['dif'] = dif; DAY['dea'] = dea
    DAY['bear'] = DAY['dif'] < DAY['dea']  # 日线空头区（回调压力）

    # 每个交易日的 60F 收盘 vs 60F MA55（跨交易日的 55 根 60F 均线）
    M60['d'] = M60['date'].dt.strftime('%Y-%m-%d')
    M60['ma55'] = M60['close'].rolling(55).mean()  # 跨组滚动，勿在 groupby 内滚动
    m60_ma55 = M60.groupby('d')['ma55'].last()
    m60_last = M60.groupby('d')['close'].last()

    start = '2025-11-14'
    DAY = DAY[DAY['date'] >= pd.Timestamp(start)].reset_index(drop=True)
    dstr = DAY['date'].dt.strftime('%Y-%m-%d')

    rows = []
    for i in range(len(DAY) - 5):
        ds = dstr.iloc[i]
        if ds not in m60_ma55.index or ds not in m60_last.index: continue
        ma55 = m60_ma55[ds]; cl = m60_last[ds]
        if pd.isna(ma55) or pd.isna(cl): continue
        strong = cl > ma55  # 60F 站上 MA55 = 逆势强势
        bear = bool(DAY['bear'].iloc[i])
        # 未来 3 日涨跌
        fwd = DAY['close'].iloc[i+3]
        ret = (fwd - DAY['close'].iloc[i]) / DAY['close'].iloc[i] * 100
        rows.append({'bear': bear, 'strong': strong, 'ret': ret})

    df = pd.DataFrame(rows)
    print(f'样本 {len(df)} 个交易日\n')
    print('=== 日线空头区（回调压力）下，60F 强弱 对 3 日后涨跌 ===')
    for bear, strong, label in [(True, True, '空头区+60F强势(逆势)'), (True, False, '空头区+60F弱势(顺势)'),
                                 (False, True, '多头区+60F强势'), (False, False, '多头区+60F弱势')]:
        sub = df[(df['bear'] == bear) & (df['strong'] == strong)]
        if len(sub) == 0:
            print(f'  {label}: 无样本'); continue
        up = (sub['ret'] > 0).sum()
        print(f'  {label}: {len(sub):3d} 次 | 3日后平均 {sub["ret"].mean():+.2f}% | 上涨 {up}/{len(sub)} ({up/len(sub)*100:.0f}%)')

    print('\n=== 关键对比：空头区里 逆势强势 vs 顺势弱势 ===')
    a = df[(df['bear'] == True) & (df['strong'] == True)]
    b = df[(df['bear'] == True) & (df['strong'] == False)]
    if len(a) and len(b):
        print(f'  逆势强势: 平均 {a["ret"].mean():+.2f}% / 上涨率 {(a["ret"]>0).mean()*100:.0f}%')
        print(f'  顺势弱势: 平均 {b["ret"].mean():+.2f}% / 上涨率 {(b["ret"]>0).mean()*100:.0f}%')

if __name__ == '__main__':
    main()
