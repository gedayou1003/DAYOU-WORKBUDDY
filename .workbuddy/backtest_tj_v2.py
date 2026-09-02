#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TJ 方法论 v2 新领悟量化回测
============================
把「中轨层次 / 极强极弱状态机 / 右侧标准(60F55) / 55线共振(压力唯一解) / 刺破中轨」
这几个 TJ 可内化模块，量化成纯价格+均线信号，用历史日线+60F 数据回测，
检验它们对「次日方向/涨跌」的预测力，并与 v5 现有基线对比。

口径与 v5 回测一致：T 日收盘后出信号 → 预测 T+1 日走势。
数据源：.workbuddy/backtest_data/{day,week,m60}.json（2026-09-02 已更新）
只依赖 pandas，用 venv python 跑：
  C:/Users/gedayou/.workbuddy/binaries/python/envs/default/Scripts/python.exe backtest_tj_v2.py
"""
import os, json
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
    if minute:
        df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d%H%M', errors='coerce')
    else:
        df['date'] = pd.to_datetime(df['date'].astype(str), errors='coerce')
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)


def ma(df, col, n, asof):
    sub = df[df['date'] <= asof][col]
    return float(sub.rolling(n).mean().iloc[-1]) if len(sub) >= n else None


def stat(rows, label, key='pct', thr=0.10):
    """rows: 该信号的次日涨跌幅序列；输出上涨率/平均/中位/样本数"""
    n = len(rows)
    if n == 0:
        print(f'  [{label}] 样本 0（不足）')
        return
    up = sum(1 for x in rows if x > thr)
    dn = sum(1 for x in rows if x < -thr)
    flat = n - up - dn
    avg = sum(rows) / n
    rows_s = sorted(rows)
    med = rows_s[n // 2]
    print(f'  [{label}] n={n:4d}  涨>{thr:.1f}%: {up/n*100:5.1f}%  跌<-{thr:.1f}%: {dn/n*100:5.1f}%  平: {flat/n*100:5.1f}%  均值 {avg:+.3f}%  中位 {med:+.3f}%')


def main():
    DAY = load_df('day.json')
    M60 = load_df('m60.json', minute=True)

    # 逐交易日构建信号表
    days = DAY['date'].tolist()
    # 预处理：日线 ma20 / ma55 / 偏离度（向量化，用 shift 保证只用截至 T 的数据）
    d20 = DAY['close'].rolling(20).mean()
    d55 = DAY['close'].rolling(55).mean()
    dev = (DAY['close'] - d55) / d55 * 100  # 偏离度 %

    # 次日涨跌幅（T+1 close vs T close）
    next_pct = (DAY['close'].shift(-1) - DAY['close']) / DAY['close'] * 100
    next_low = DAY['low'].shift(-1)
    next_high = DAY['high'].shift(-1)

    # 60F MA55（截至每个日收盘），先算 60F 收盘序列的 rolling
    m60_close = M60['close']
    m60_ma55 = m60_close.rolling(55).mean()
    # 60F 收盘价 → 映射到日（取每日最后一根 60F）
    m60_day = M60['date'].dt.strftime('%Y-%m-%d')
    m60_last = M60.groupby(m60_day).tail(1)
    m60_last_ma55 = pd.Series(m60_ma55.values, index=M60.index).groupby(m60_day.values).last()
    m60_map = dict(zip(m60_last['date'].dt.strftime('%Y-%m-%d'), m60_last_ma55.values))

    print('=' * 70)
    print('TJ 方法论 v2 量化回测（上证综指 000001，日线 + 60F）')
    print(f'日线样本 {len(DAY)} 根  {DAY["date"].iloc[0].date()} ~ {DAY["date"].iloc[-1].date()}')
    print('=' * 70)

    # ── 信号 1：中轨（MA20）层次 vs MA55 分水岭 ──
    print('\n【信号1】中轨层次（MA20 预警线 vs MA55 分水岭）→ 次日方向')
    g = {'强势(close>20>55)': [], '回调守55(20>close>55)': [], '破55(close<55,20仍>55)': [], '空头排列(20<55)': []}
    for i in range(len(DAY)):
        if i < 55 or i + 1 >= len(DAY):
            continue
        c = DAY['close'].iloc[i]
        m20, m55 = d20.iloc[i], d55.iloc[i]
        if pd.isna(m20) or pd.isna(m55):
            continue
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        if c > m20 and m20 > m55:
            g['强势(close>20>55)'].append(pct)
        elif m20 > c > m55:
            g['回调守55(20>close>55)'].append(pct)
        elif c < m55 and m20 > m55:
            g['破55(close<55,20仍>55)'].append(pct)
        else:
            g['空头排列(20<55)'].append(pct)
    for k, v in g.items():
        stat(v, k)

    # ── 信号 2：极强/极弱状态机（偏离度加速/减速）──
    print('\n【信号2】极强/极弱状态机（偏离度加速=极强/极弱，减速=解除）→ 次日方向')
    # 极强：close>55 且 dev 较前日扩大；极弱：close<55 且 dev 较前日缩小（负向扩大）
    states = []  # 每行：('极强'/'极弱'/其他)
    for i in range(len(DAY)):
        if i < 56:
            states.append('nan')
            continue
        c = DAY['close'].iloc[i]
        m55 = d55.iloc[i]
        if pd.isna(m55):
            states.append('nan')
            continue
        d_now = dev.iloc[i]
        d_prev = dev.iloc[i - 1]
        if c > m55 and d_now > d_prev:
            states.append('极强')
        elif c < m55 and d_now < d_prev:
            states.append('极弱')
        else:
            states.append('其他')
    sw = {'进入极强': [], '持续极强': [], '解除极强': [], '进入极弱': [], '持续极弱': [], '解除极弱': []}
    for i in range(len(DAY)):
        if i < 57 or i + 1 >= len(DAY):
            continue
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        s, s_prev = states[i], states[i - 1]
        if s == '极强' and s_prev != '极强':
            sw['进入极强'].append(pct)
        elif s == '极强' and s_prev == '极强':
            sw['持续极强'].append(pct)
        elif s_prev == '极强' and s != '极强':
            sw['解除极强'].append(pct)
        elif s == '极弱' and s_prev != '极弱':
            sw['进入极弱'].append(pct)
        elif s == '极弱' and s_prev == '极弱':
            sw['持续极弱'].append(pct)
        elif s_prev == '极弱' and s != '极弱':
            sw['解除极弱'].append(pct)
    for k, v in sw.items():
        stat(v, k)

    # ── 信号 3：右侧标准（60F MA55 得失）──
    print('\n【信号3】右侧标准（收盘 vs 60F MA55）→ 次日方向')
    r = {'站上60F55': [], '跌破60F55': []}
    for i in range(len(DAY)):
        if i < 55 or i + 1 >= len(DAY):
            continue
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        d = DAY['date'].iloc[i].strftime('%Y-%m-%d')
        v = m60_map.get(d)
        if v is None or pd.isna(v):
            continue
        c = DAY['close'].iloc[i]
        r['站上60F55' if c > v else '跌破60F55'].append(pct)
    for k, v in r.items():
        stat(v, k)

    # ── 信号 4：55线共振（日线55 vs 60F55 聚集）──
    print('\n【信号4】55线共振（日线55 与 60F55 距离<1%=重叠区）→ 次日方向')
    res = {'上方共振(双55重叠压)': [], '上方分离': [], '下方共振(双55重叠支)': [], '下方分离': []}
    for i in range(len(DAY)):
        if i < 55 or i + 1 >= len(DAY):
            continue
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        c = DAY['close'].iloc[i]
        m55 = d55.iloc[i]
        d = DAY['date'].iloc[i].strftime('%Y-%m-%d')
        v = m60_map.get(d)
        if pd.isna(m55) or v is None or pd.isna(v):
            continue
        dist = abs(m55 - v) / c * 100
        if v > c and m55 > c:  # 双线在上方
            res['上方共振(双55重叠压)' if dist < 1.0 else '上方分离'].append(pct)
        elif v < c and m55 < c:  # 双线在下方
            res['下方共振(双55重叠支)' if dist < 1.0 else '下方分离'].append(pct)
    for k, v in res.items():
        stat(v, k)

    # ── 信号 5：刺破中轨 vs 有效跌破中轨（T 日盘中 vs 收盘）──
    print('\n【信号5】刺破中轨 vs 有效跌破中轨（当日盘中 vs 收盘）→ 次日方向')
    br = {'刺破中轨收回(low<20<close)': [], '有效跌破(close<20)': [], '守住中轨(close>20)': []}
    for i in range(len(DAY)):
        if i < 20 or i + 1 >= len(DAY):
            continue
        pct = next_pct.iloc[i]
        if pd.isna(pct):
            continue
        m20 = d20.iloc[i]
        if pd.isna(m20):
            continue
        lo, c = DAY['low'].iloc[i], DAY['close'].iloc[i]
        if lo < m20 <= c:
            br['刺破中轨收回(low<20<close)'].append(pct)
        elif c < m20:
            br['有效跌破(close<20)'].append(pct)
        else:
            br['守住中轨(close>20)'].append(pct)
    for k, v in br.items():
        stat(v, k)

    print('\n' + '=' * 70)
    print('结论提示：对比 v5 基线 —— 方向相反率约 28~30%（即方向命中率 ~70%）；')
    print('          若某 TJ 信号分档的「涨/跌」概率显著偏离 50% 且样本≥30，即具预测力。')
    print('=' * 70)


if __name__ == '__main__':
    main()
