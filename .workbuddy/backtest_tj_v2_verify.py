#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TJ v2 补充验证：极强/极弱状态机信号稳健性 + 能否作为方向因子"""
import os, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.join(HERE, 'backtest_data')

def load_df(name):
    rows = json.load(open(os.path.join(BT, name), encoding='utf-8'))
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'].astype(str), errors='coerce')
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

DAY = load_df('day.json')
d55 = DAY['close'].rolling(55).mean()
dev = (DAY['close'] - d55) / d55 * 100

# 状态
states = []
for i in range(len(DAY)):
    if i < 56:
        states.append('nan'); continue
    c, m55 = DAY['close'].iloc[i], d55.iloc[i]
    if pd.isna(m55):
        states.append('nan'); continue
    d_now, d_prev = dev.iloc[i], dev.iloc[i-1]
    if c > m55 and d_now > d_prev: states.append('极强')
    elif c < m55 and d_now < d_prev: states.append('极弱')
    else: states.append('其他')

# 累计收益（未来 1/3 日）
pct1 = (DAY['close'].shift(-1) - DAY['close'])/DAY['close']*100
pct3 = (DAY['close'].shift(-3) - DAY['close'])/DAY['close']*100

def summarize(cond, label):
    idx = [i for i in range(len(DAY)) if cond(i)]
    p1 = [pct1.iloc[i] for i in idx if pd.notna(pct1.iloc[i])]
    p3 = [pct3.iloc[i] for i in idx if pd.notna(pct3.iloc[i])]
    up1 = sum(1 for x in p1 if x > 0.1)/len(p1)*100 if p1 else 0
    dn1 = sum(1 for x in p1 if x < -0.1)/len(p1)*100 if p1 else 0
    up3 = sum(1 for x in p3 if x > 0.1)/len(p3)*100 if p3 else 0
    avg3 = sum(p3)/len(p3) if p3 else 0
    print(f'  {label:24s} n={len(p1):3d}  次日涨{up1:5.1f}%/跌{dn1:5.1f}%  3日均值{avg3:+.3f}%  3日涨{up3:5.1f}%')

print('='*70)
print('极强/极弱状态机 —— 1日 vs 3日 稳健性交叉验证')
print('='*70)
summarize(lambda i: i>=57 and states[i-1]=='极强' and states[i]=='极强', '持续极强(连续加速)')
summarize(lambda i: i>=57 and states[i-1]=='极弱' and states[i]!='极弱', '解除极弱(减速反弹)')
summarize(lambda i: i>=57 and states[i-1]=='极强' and states[i]!='极强', '解除极强(减速见顶)')
summarize(lambda i: i>=57 and states[i]=='极强' and states[i-1]!='极强', '进入极强(加速启动)')
print()

# 作为方向因子：极强极弱状态机独立给方向 → 命中率 vs v5 基线
print('='*70)
print('方向因子命中率对比（次日 |pct|>0.1% 计有效，符号一致=命中）')
print('='*70)
def hitrate(cond, dir_sig):
    idx = [i for i in range(len(DAY)) if cond(i) and pd.notna(pct1.iloc[i])]
    if not idx: return
    hit = sum(1 for i in idx if (dir_sig=='空' and pct1.iloc[i] < -0.1) or (dir_sig=='多' and pct1.iloc[i] > 0.1))
    opp = sum(1 for i in idx if (dir_sig=='空' and pct1.iloc[i] > 0.1) or (dir_sig=='多' and pct1.iloc[i] < -0.1))
    print(f'  信号「{dir_sig}」n={len(idx):3d}  命中{hit/len(idx)*100:5.1f}%  相反{opp/len(idx)*100:5.1f}%')

# 因子1：持续极强 → 看空
hitrate(lambda i: i>=57 and states[i-1]=='极强' and states[i]=='极强', '空')
# 因子2：解除极弱 → 看多
hitrate(lambda i: i>=57 and states[i-1]=='极弱' and states[i]!='极弱', '多')
# 因子3：持续极弱 → 看多（越跌越买）
hitrate(lambda i: i>=57 and states[i-1]=='极弱' and states[i]=='极弱', '多')
# 组合：持续极强看空 + (解除极弱或持续极弱)看多
def combo(i):
    if i < 57: return False
    s, sp = states[i], states[i-1]
    return (sp=='极强' and s=='极强') or (sp=='极弱' and s!='极强')
print('  --- 组合因子（持续极强→空 / 解除极弱→多）---')
idx = [i for i in range(len(DAY)) if combo(i) and pd.notna(pct1.iloc[i])]
hit = sum(1 for i in idx if (states[i-1]=='极强' and pct1.iloc[i]<-0.1) or (states[i-1]=='极弱' and pct1.iloc[i]>0.1))
opp = sum(1 for i in idx if (states[i-1]=='极强' and pct1.iloc[i]>0.1) or (states[i-1]=='极弱' and pct1.iloc[i]<-0.1))
print(f'  组合 n={len(idx):3d}  命中{hit/len(idx)*100:5.1f}%  相反{opp/len(idx)*100:5.1f}%  规避(平){ (len(idx)-hit-opp)/len(idx)*100:5.1f}%')

print()
print('v5 基线参考：方向相反率约 28~30%（方向命中率 ~70%，含「方向不明」规避）')
