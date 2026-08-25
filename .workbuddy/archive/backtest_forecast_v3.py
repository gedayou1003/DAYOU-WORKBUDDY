#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预判回测 v3（深度补救版）— 在 v2 基础上：
补救 4：支撑/压力缺失时用 15F BOLL 上下轨兜底
补救 5：引擎"方向不明"时用 T&J 方向校准
"""
import sys, os, json
import pandas as pd
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = r"C:\Users\gedayou\.workbuddy\skills\chan-signal__skillhub"
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine, build_analysis

CODE = '000001'
BT_DIR = os.path.join(HERE, 'backtest_data')

def load_df(name, minute=False):
    rows = json.load(open(os.path.join(BT_DIR, name), encoding='utf-8'))
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

DAY = load_df('day.json'); WEEK = load_df('week.json')
M60 = load_df('m60.json', minute=True); M15 = load_df('m15.json', minute=True)
TJ = json.load(open(os.path.join(BT_DIR, 'tj_topics.json'), encoding='utf-8'))

BULL = ['金叉', '主涨', '反弹', 'b浪', 'B浪', '看多', '突破', '支撑有效', '低吸', '止跌', '上涨', '强势', '右侧', '二买', '三买', '底背离']
BEAR = ['死叉', '主跌', 'c浪', 'C浪', '看空', '压制', '回落', '新低', '二次股灾', '下跌', '弱势', '顶背离', '一卖', '二卖', '三卖', '调整', '风险', '中枢构建']

def tj_direction(date_str):
    day_topics = [t for t in TJ if t['create_time'][:10] == date_str]
    if not day_topics:
        return None
    tech = [t['text'] for t in day_topics if any(w in t['text'] for w in BULL + BEAR)]
    if not tech:
        return None
    joined = '\n'.join(tech)
    bull = sum(1 for w in BULL if w in joined); bear = sum(1 for w in BEAR if w in joined)
    return '偏多' if bull > bear else ('偏空' if bear > bull else '震荡')

WEIGHT = {'日线': 2, '周线': 2, '60分钟': 2, '15分钟': 1}

def boll(df, n=20, k=2):
    if df is None or len(df) < n + 1:
        return None
    mid = df['close'].rolling(n).mean(); std = df['close'].rolling(n).std()
    up = mid + k * std; low = mid - k * std
    bw = float(((up - low) / mid * 100).iloc[-1])
    return {'up': float(up.iloc[-1]), 'mid': float(mid.iloc[-1]), 'low': float(low.iloc[-1]), 'bw': bw}

def run_periods(df_day, df_week, df_m60, df_m15):
    r = {}
    for tag, cat, df in [('日线', 9, df_day), ('周线', 7, df_week), ('60分钟', 6, df_m60), ('15分钟', 15, df_m15)]:
        if df is None or len(df) < 30:
            r[tag] = None; continue
        try:
            eng = run_engine(df); r[tag] = build_analysis(CODE, df, eng, cat, recent_bars=0)
        except Exception:
            r[tag] = None
    return r

def predict_v3(results, asof_date, boll15, tj_dir):
    cutoff = (pd.Timestamp(asof_date) - pd.Timedelta(days=20)).strftime('%Y-%m-%d')
    trend_score = 0
    for tag in ('日线', '周线'):
        r = results.get(tag)
        if r and r.get('structure'):
            t = r['structure'].get('current_trend')
            if t == '向上': trend_score += 2
            elif t == '向下': trend_score -= 2
    sig_score = 0; buys, sells = [], []
    for tag, w in WEIGHT.items():
        r = results.get(tag)
        if not r: continue
        sigs = [s for s in r.get('signals', []) if (s.get('date', '') or '') >= cutoff]
        if not sigs: continue
        if sigs[0]['type'] == 'buy':
            sig_score += w; buys.append((sigs[0]['price'], sigs[0]['name'], tag))
        else:
            sig_score -= w; sells.append((sigs[0]['price'], sigs[0]['name'], tag))
    total = trend_score + sig_score

    bw = boll15['bw'] if boll15 else None
    # 方向
    if bw is not None and bw < 1.0:
        engine_dir = '方向不明'
    elif total >= 3: engine_dir = '偏多'
    elif total <= -3: engine_dir = '偏空'
    elif abs(total) <= 1: engine_dir = '方向不明'
    elif total > 0: engine_dir = '震荡偏多'
    else: engine_dir = '震荡偏空'

    # 方向：保留"方向不明"（不做 T&J 校准，v4 结论）
    direction = engine_dir
    calibrated = False

    # 支撑/压力：买卖点优先，缺失用 BOLL 上下轨兜底
    prio = {'15分钟': 0, '60分钟': 1, '日线': 2, '周线': 3}
    sup = min(buys, key=lambda x: prio.get(x[2], 9))[0] if buys else None
    res = min(sells, key=lambda x: prio.get(x[2], 9))[0] if sells else None
    if sup is None and boll15:
        sup = boll15['low']
    if res is None and boll15:
        res = boll15['up']
    return {
        'direction': direction, 'engine_dir': engine_dir, 'calibrated': calibrated,
        'total': total, 'bw': bw,
        'support': sup, 'resistance': res,
    }

def judge_v3(pred, actual):
    pct = actual['pct']; d = pred['direction']
    lo, hi = actual['low'], actual['high']; sup, res = pred['support'], pred['resistance']
    if d == '方向不明':
        dir_v = '✅规避' if (pct is not None and abs(pct) <= 0.5) else '⚠️未给方向'
    elif d in ('偏多', '震荡偏多') and pct > 0.15: dir_v = '✅命中'
    elif d in ('偏空', '震荡偏空') and pct < -0.15: dir_v = '✅命中'
    elif d in ('偏多', '震荡偏多') and pct < -0.15: dir_v = '❌相反'
    elif d in ('偏空', '震荡偏空') and pct > 0.15: dir_v = '❌相反'
    else: dir_v = '⚠️部分'

    if sup is not None and res is not None:
        range_v = '✅区间内' if (lo >= sup * 0.995 and hi <= res * 1.005) else '⚠️越界'
    else: range_v = '—'
    sup_v = ('❌跌破' if lo < sup * 0.995 else '✅守住') if sup is not None else '—'
    res_v = ('❌突破' if hi > res * 1.005 else '✅守住') if res is not None else '—'
    return {'direction': dir_v, 'range': range_v, 'support': sup_v, 'resistance': res_v}

def run():
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if '2026-07-28' <= d <= '2026-08-21']
    rows = []
    for i, T in enumerate(trade_days):
        next_day = '2026-08-24' if i + 1 >= len(trade_days) else trade_days[i + 1]
        df_day = DAY[DAY['date'] <= pd.Timestamp(T)]
        df_week = WEEK[WEEK['date'] <= pd.Timestamp(T)]
        cut = pd.Timestamp(T + ' 15:00:00')
        df_m60 = M60[M60['date'] <= cut]; df_m15 = M15[M15['date'] <= cut]
        b15 = boll(df_m15)
        res = run_periods(df_day, df_week, df_m60, df_m15)
        tj = tj_direction(T)
        pred = predict_v3(res, T, b15, tj)
        act = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act.empty: continue
        a = act.iloc[0]
        prev = DAY[DAY['date'] == pd.Timestamp(T)]
        pc = float(prev.iloc[0]['close']) if not prev.empty else None
        actual = {'date': next_day, 'low': float(a['low']), 'high': float(a['high']),
                  'close': float(a['close']),
                  'pct': round((float(a['close']) - pc) / pc * 100, 2) if pc else None}
        v = judge_v3(pred, actual)
        rows.append({'T': T, 'next': next_day, 'pred': pred, 'tj': tj, 'actual': actual, 'verdict': v})
    return rows

def stats(rows):
    n = len(rows)
    hit = sum(1 for r in rows if '✅' in r['verdict']['direction'])
    opp = sum(1 for r in rows if '❌' in r['verdict']['direction'])
    avoid = sum(1 for r in rows if '规避' in r['verdict']['direction'])
    range_hit = sum(1 for r in rows if '✅' in r['verdict']['range'])
    sup_hold = sum(1 for r in rows if '守住' in r['verdict']['support'])
    res_hold = sum(1 for r in rows if '守住' in r['verdict']['resistance'])
    n_cal = sum(1 for r in rows if r['pred']['calibrated'])
    return {'n': n, 'dir_accuracy': round(hit/n*100,1), 'dir_opposite': round(opp/n*100,1),
            'dir_avoid': round(avoid/n*100,1), 'range_accuracy': round(range_hit/n*100,1),
            'sup_hold': round(sup_hold/n*100,1), 'res_hold': round(res_hold/n*100,1), 'n_cal': n_cal}

if __name__ == '__main__':
    rows = run(); st = stats(rows)
    print('===== 预判回测 v3（深度补救版）=====')
    print(f'样本: {st["n"]}')
    print(f'方向命中率: {st["dir_accuracy"]}%  (v1 31.6% → v2 36.8%)')
    print(f'方向相反率: {st["dir_opposite"]}%  (v1 52.6% → v2 36.8%)')
    print(f'方向规避率: {st["dir_avoid"]}%')
    print(f'区间覆盖率: {st["range_accuracy"]}%  (v1/v2 10.5%)')
    print(f'支撑守住率: {st["sup_hold"]}%')
    print(f'压力守住率: {st["res_hold"]}%')
    print(f'T&J 校准次数: {st["n_cal"]}')
    json.dump({'stats': st, 'rows': rows}, open(os.path.join(BT_DIR, 'backtest_result_v3.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print('\n===== 逐日明细 =====')
    for r in rows:
        p = r['pred']; a = r['actual']; v = r['verdict']
        sup = f"{p['support']:.1f}" if p['support'] else '—'; res = f"{p['resistance']:.1f}" if p['resistance'] else '—'
        cal = '⭐T&J校准' if p['calibrated'] else ''
        print(f"{r['T'][5:]}→{r['next'][5:]} | {p['direction']}({sup}~{res}){cal} | 实际{a['pct']:+.2f}% | 方向{v['direction']} 区间{v['range']} 支撑{v['support']} 压力{v['resistance']}")
