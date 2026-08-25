#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v5 预判规则回测：支撑/压力升级为「55线优先 + 买卖点 + BOLL 兜底」，方向判断保持 v4"""
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
    return float(sub['close'].rolling(55).mean().iloc[-1]) if len(sub) >= 55 else None

def boll(df, asof, n=20, k=2):
    sub = df[df['date'] <= asof]
    if len(sub) < n + 1: return None
    mid = sub['close'].rolling(n).mean(); std = sub['close'].rolling(n).std()
    return {'up': float((mid+k*std).iloc[-1]), 'low': float((mid-k*std).iloc[-1]),
            'bw': float(((mid+k*std-(mid-k*std))/mid*100).iloc[-1])}

ENGINE_CACHE = os.path.join(BT, 'engine_cache')

def run_engine_at(df, cat):
    if df is None or len(df) < 30: return None
    # 磁盘缓存：key = 周期 + 切片最后日期。回测同一 T 的引擎结果只算一次，
    # 改参数（方向阈值/窗口/支撑方案）重跑时直接读缓存，省 752 次引擎计算（约 2-3 分钟 → 秒级）
    try:
        # 时间戳里的冒号是 Windows 文件名非法字符，替换掉
        last_date = str(df['date'].iloc[-1])[:19].replace(':', '-').replace(' ', '_')
    except Exception:
        last_date = 'unknown'
    cache_file = os.path.join(ENGINE_CACHE, f'{cat}_{last_date}.json')
    try:
        if os.path.exists(cache_file):
            return json.load(open(cache_file, encoding='utf-8'))
    except Exception:
        pass
    try:
        r = build_analysis(CODE, df, run_engine(df), cat, recent_bars=0)
    except Exception:
        return None
    if r:
        try:
            os.makedirs(ENGINE_CACHE, exist_ok=True)
            json.dump(r, open(cache_file, 'w', encoding='utf-8'), ensure_ascii=False)
        except Exception:
            pass
    return r

def evaluate(start, end, use_15f=True):
    DAY = load_df('day.json'); WEEK = load_df('week.json'); M60 = load_df('m60.json', minute=True); M15 = load_df('m15.json', minute=True)
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if start <= d <= end]
    rows = []
    for i, T in enumerate(trade_days):
        # 动态找 T 之后的下一个交易日（避免硬编码，且最后一日无次日数据则跳过）
        after = DAY[DAY['date'] > pd.Timestamp(T)]
        if after.empty:
            continue
        next_day = after['date'].dt.strftime('%Y-%m-%d').iloc[0]
        cut = pd.Timestamp(T + ' 15:00:00')
        close_now = float(DAY[DAY['date'] <= pd.Timestamp(T)]['close'].iloc[-1])
        d55 = ma55(DAY, pd.Timestamp(T)); m60_55 = ma55(M60, cut); m15_55 = ma55(M15, cut) if use_15f else None
        levels = [v for v in [d55, m60_55, m15_55] if v is not None]
        r_day = run_engine_at(DAY[DAY['date'] <= pd.Timestamp(T)], 9)
        r_week = run_engine_at(WEEK[WEEK['date'] <= pd.Timestamp(T)], 7)
        r_m60 = run_engine_at(M60[M60['date'] <= cut], 6)
        r_m15 = run_engine_at(M15[M15['date'] <= cut], 15) if use_15f else None
        # 分级窗口（修复硬伤2）：日线/周线信号用 30 天，60F/15F 用 20 天
        cutoff_day = (pd.Timestamp(T) - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        cutoff_short = (pd.Timestamp(T) - pd.Timedelta(days=20)).strftime('%Y-%m-%d')
        trend_score = 0
        for r in (r_day, r_week):
            if r and r.get('structure'):
                t = r['structure'].get('current_trend')
                if t == '向上': trend_score += 2
                elif t == '向下': trend_score -= 2
        sig_score = 0; buys, sells = [], []
        prio = {'15分钟':0, '60分钟':1, '日线':2, '周线':3}
        for tag, r, w in [('日线', r_day, 2), ('周线', r_week, 2), ('60分钟', r_m60, 2), ('15分钟', r_m15, 1)]:
            if not r: continue
            _cut = cutoff_day if tag in ('日线', '周线') else cutoff_short
            sigs = [s for s in r.get('signals', []) if (s.get('date','') or '') >= _cut]
            if not sigs: continue
            s0 = sigs[0]
            # confidence 降权（2026-08-25 优化）：无背驰的一买/一卖 confidence<0.6 是弱信号，降半权
            w_eff = w * (0.5 if s0.get('confidence', 0.5) < 0.6 else 1.0)
            if s0['type'] == 'buy': sig_score += w_eff; buys.append((s0['price'], tag))
            else: sig_score -= w_eff; sells.append((s0['price'], tag))
        total = trend_score + sig_score
        b15 = boll(M15, cut) if use_15f else None
        bw = b15['bw'] if b15 else None
        if bw is not None and bw < 1.0: direction = '方向不明'
        elif total >= 3: direction = '偏多'
        elif total <= -3: direction = '偏空'
        elif abs(total) <= 1: direction = '方向不明'
        elif total > 0: direction = '震荡偏多'
        else: direction = '震荡偏空'
        below = [v for v in levels if v < close_now]; above = [v for v in levels if v > close_now]
        boll_low = b15['low'] if b15 else None
        boll_up = b15['up'] if b15 else None
        # 前低（最近10日最低）——回测验证支撑守住率 57%→91%，55线做支撑太贴价会跌破（支撑跌破6次根因）
        hist = DAY[DAY['date'] <= pd.Timestamp(T)].tail(10)
        prev_low = float(hist['low'].min()) if len(hist) else None
        # 支撑：前低优先（<现价），前低被破则 BOLL 下轨兜底，再无则买卖点
        sup = prev_low if (prev_low is not None and prev_low < close_now) else (boll_low if boll_low is not None else (min(buys, key=lambda x: prio.get(x[1],9))[0] if buys else None))
        # 压力：上方最近 55 线（保持不变）
        res = min(above) if above else (boll_up if boll_up is not None else (min(sells, key=lambda x: prio.get(x[1],9))[0] if sells else None))
        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty: continue
        prev = DAY[DAY['date'] == pd.Timestamp(T)]
        pc = float(prev.iloc[0]['close']) if not prev.empty else None
        pct = round((float(act.iloc[0]['close'])-pc)/pc*100,2) if pc else None
        rows.append({'T': T, 'direction': direction, 'sup': sup, 'res': res,
                     'lo': float(act.iloc[0]['low']), 'hi': float(act.iloc[0]['high']), 'pct': pct})
    return rows

def report(rows, label):
    n = len(rows)
    hit = sum(1 for r in rows if (r['direction'] in ('偏多','震荡偏多') and r['pct'] > 0.15) or (r['direction'] in ('偏空','震荡偏空') and r['pct'] < -0.15))
    opp = sum(1 for r in rows if (r['direction'] in ('偏多','震荡偏多') and r['pct'] < -0.15) or (r['direction'] in ('偏空','震荡偏空') and r['pct'] > 0.15))
    avoid = sum(1 for r in rows if r['direction'] == '方向不明' and abs(r['pct']) <= 0.5)
    c = sum(1 for r in rows if r['sup'] and r['res'] and r['lo'] >= r['sup']*0.995 and r['hi'] <= r['res']*1.005)
    nn = sum(1 for r in rows if r['sup'] and r['res'])
    sup_hold = sum(1 for r in rows if r['sup'] and r['lo'] >= r['sup']*0.995)
    res_hold = sum(1 for r in rows if r['res'] and r['hi'] <= r['res']*1.005)
    print(f'[{label}] 样本 {n}')
    print(f'  方向: 命中 {round(hit/n*100,1)}% / 相反 {round(opp/n*100,1)}% / 规避 {round(avoid/n*100,1)}%')
    if nn: print(f'  区间覆盖: {c}/{nn} = {round(c/nn*100,1)}%')
    print(f'  支撑守住: {round(sup_hold/n*100,1)}%  压力守住: {round(res_hold/n*100,1)}%')

if __name__ == '__main__':
    print('===== v5（55线优先支撑/压力）回测 =====\n')
    report(evaluate('2025-11-14', '2026-08-21', use_15f=False), '60F 版区间（日线55+60F55，188样本）')
    print()
    report(evaluate('2026-07-28', '2026-08-21', use_15f=True), '15F 版区间（含15F55，19样本）')
