#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预判回测 v2（补救版）— 对比 v1，验证硬伤补救效果
补救 1：方向判断加入 趋势因子 + 15F BOLL 变盘抑制 + 「方向不明」状态
补救 2：支撑/压力从「单点」改为「区间带」±0.5%
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
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df

DAY = load_df('day.json')
WEEK = load_df('week.json')
M60 = load_df('m60.json', minute=True)
M15 = load_df('m15.json', minute=True)

TJ = json.load(open(os.path.join(BT_DIR, 'tj_topics.json'), encoding='utf-8'))
BULL_WORDS = ['金叉', '主涨', '反弹', 'b浪', 'B浪', '看多', '突破', '支撑有效', '低吸', '止跌', '上涨', '强势', '右侧', '二买', '三买', '底背离']
BEAR_WORDS = ['死叉', '主跌', 'c浪', 'C浪', '看空', '压制', '回落', '新低', '二次股灾', '下跌', '弱势', '顶背离', '一卖', '二卖', '三卖', '调整', '风险', '中枢构建']

def tj_direction(date_str):
    day_topics = [t for t in TJ if t['create_time'][:10] == date_str]
    if not day_topics:
        return None, ''
    tech = [t['text'] for t in day_topics if any(w in t['text'] for w in BULL_WORDS + BEAR_WORDS)]
    if not tech:
        return None, ''
    joined = '\n'.join(tech)
    bull = sum(1 for w in BULL_WORDS if w in joined)
    bear = sum(1 for w in BEAR_WORDS if w in joined)
    if bull > bear:
        return '偏多', joined[:150]
    elif bear > bull:
        return '偏空', joined[:150]
    return '震荡', joined[:150]

WEIGHT = {'日线': 2, '周线': 2, '60分钟': 2, '15分钟': 1}

def boll_bandwidth(df, n=20, k=2):
    """计算 BOLL 带宽（%），返回最后一根带宽值"""
    if df is None or len(df) < n + 1:
        return None
    mid = df['close'].rolling(n).mean()
    std = df['close'].rolling(n).std()
    up = mid + k * std
    low = mid - k * std
    bw = (up - low) / mid * 100
    return float(bw.iloc[-1])

def run_periods(df_day, df_week, df_m60, df_m15):
    results = {}
    for tag, cat, df in [('日线', 9, df_day), ('周线', 7, df_week), ('60分钟', 6, df_m60), ('15分钟', 15, df_m15)]:
        if df is None or len(df) < 30:
            results[tag] = None
            continue
        try:
            eng = run_engine(df)
            results[tag] = build_analysis(CODE, df, eng, cat, recent_bars=0)
        except Exception:
            results[tag] = None
    return results

def predict_v2(results, asof_date, m15_bw):
    """补救版预判：趋势因子 + 买卖点 + BOLL 变盘抑制 + 方向不明 + 区间带"""
    cutoff = (pd.Timestamp(asof_date) - pd.Timedelta(days=20)).strftime('%Y-%m-%d')

    # 1) 趋势因子
    trend_score = 0
    for tag in ('日线', '周线'):
        r = results.get(tag)
        if r and r.get('structure'):
            t = r['structure'].get('current_trend')
            if t == '向上':
                trend_score += 2
            elif t == '向下':
                trend_score -= 2

    # 2) 买卖点因子
    sig_score = 0
    buys, sells = [], []
    for tag, w in WEIGHT.items():
        r = results.get(tag)
        if not r:
            continue
        sigs = [s for s in r.get('signals', []) if (s.get('date', '') or '') >= cutoff]
        if not sigs:
            continue
        latest = sigs[0]
        if latest['type'] == 'buy':
            sig_score += w
            buys.append((latest['price'], latest['name'], tag))
        else:
            sig_score -= w
            sells.append((latest['price'], latest['name'], tag))

    total = trend_score + sig_score

    # 3) BOLL 变盘抑制：15F 带宽 < 1% 极度收口 → 方向不明
    if m15_bw is not None and m15_bw < 1.0:
        direction = '方向不明'
        reason = f'15F带宽{m15_bw:.2f}%极度收口变盘'
    elif total >= 3:
        direction = '偏多'
        reason = ''
    elif total <= -3:
        direction = '偏空'
        reason = ''
    elif abs(total) <= 1:
        direction = '方向不明'
        reason = '多空信号平衡'
    elif total > 0:
        direction = '震荡偏多'
        reason = ''
    else:
        direction = '震荡偏空'
        reason = ''

    # 4) 支撑/压力：区间带 ±0.5%
    prio = {'15分钟': 0, '60分钟': 1, '日线': 2, '周线': 3}
    sup = min(buys, key=lambda x: prio.get(x[2], 9)) if buys else None
    res = min(sells, key=lambda x: prio.get(x[2], 9)) if sells else None
    return {
        'direction': direction, 'total': total, 'reason': reason,
        'support': sup[0] if sup else None,
        'support_name': f"{sup[1]}@{sup[2]}" if sup else None,
        'resistance': res[0] if res else None,
        'resistance_name': f"{res[1]}@{res[2]}" if res else None,
    }

def judge_v2(pred, actual):
    pct = actual['pct']
    d = pred['direction']
    lo, hi = actual['low'], actual['high']
    sup, res = pred['support'], pred['resistance']

    # 方向（加入"方向不明"）
    if d == '方向不明':
        if pct is None:
            dir_v = '—'
        elif abs(pct) <= 0.5:
            dir_v = '✅规避(识别不确定)'
        else:
            dir_v = '⚠️未给方向'
    elif d in ('偏多', '震荡偏多') and pct > 0.15:
        dir_v = '✅命中'
    elif d in ('偏空', '震荡偏空') and pct < -0.15:
        dir_v = '✅命中'
    elif d == '震荡' and abs(pct) <= 0.3:
        dir_v = '✅命中'
    elif d in ('偏多', '震荡偏多') and pct < -0.15:
        dir_v = '❌相反'
    elif d in ('偏空', '震荡偏空') and pct > 0.15:
        dir_v = '❌相反'
    else:
        dir_v = '⚠️部分'

    # 区间（用带 ±0.5%）
    if sup is not None and res is not None:
        sup_lo = sup * 0.995
        res_hi = res * 1.005
        if lo >= sup_lo and hi <= res_hi:
            range_v = '✅区间内'
        else:
            range_v = '⚠️越界'
    else:
        range_v = '—'

    # 支撑（带下沿判定）
    if sup is not None:
        sup_lo = sup * 0.995
        if lo < sup_lo:
            sup_v = f"❌跌破({round(lo-sup,1)}点)"
        else:
            sup_v = '✅守住'
    else:
        sup_v = '—'

    # 压力（带上沿判定）
    if res is not None:
        res_hi = res * 1.005
        if hi > res_hi:
            res_v = f"❌突破({round(hi-res,1)}点)"
        else:
            res_v = '✅守住'
    else:
        res_v = '—'

    return {'direction': dir_v, 'range': range_v, 'support': sup_v, 'resistance': res_v}

def run_backtest():
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist() if '2026-07-28' <= d <= '2026-08-21']
    rows = []
    for i, T in enumerate(trade_days):
        next_day = '2026-08-24' if i + 1 >= len(trade_days) else trade_days[i + 1]
        df_day = DAY[DAY['date'] <= pd.Timestamp(T)]
        df_week = WEEK[WEEK['date'] <= pd.Timestamp(T)]
        cutoff = pd.Timestamp(T + ' 15:00:00')
        df_m60 = M60[M60['date'] <= cutoff]
        df_m15 = M15[M15['date'] <= cutoff]
        m15_bw = boll_bandwidth(df_m15)
        results = run_periods(df_day, df_week, df_m60, df_m15)
        pred = predict_v2(results, T, m15_bw)
        tj_dir, _ = tj_direction(T)
        act_day = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act_day.empty:
            continue
        act = act_day.iloc[0]
        prev = DAY[DAY['date'] == pd.Timestamp(T)]
        prev_close = float(prev.iloc[0]['close']) if not prev.empty else None
        actual = {
            'date': next_day, 'open': float(act['open']), 'high': float(act['high']),
            'low': float(act['low']), 'close': float(act['close']),
            'pct': round((float(act['close']) - prev_close) / prev_close * 100, 2) if prev_close else None,
        }
        verdict = judge_v2(pred, actual)
        rows.append({'T': T, 'next': next_day, 'pred': pred, 'tj_dir': tj_dir, 'actual': actual, 'verdict': verdict})
    return rows

def stats(rows):
    n = len(rows)
    hit = sum(1 for r in rows if '✅' in r['verdict']['direction'])
    opp = sum(1 for r in rows if '❌' in r['verdict']['direction'])
    avoid = sum(1 for r in rows if '规避' in r['verdict']['direction'])
    range_hit = sum(1 for r in rows if '✅' in r['verdict']['range'])
    sup_hold = sum(1 for r in rows if '守住' in r['verdict']['support'])
    sup_break = sum(1 for r in rows if '跌破' in r['verdict']['support'])
    res_hold = sum(1 for r in rows if '守住' in r['verdict']['resistance'])
    res_break = sum(1 for r in rows if '突破' in r['verdict']['resistance'])
    return {
        'n': n,
        'dir_accuracy': round(hit / n * 100, 1),
        'dir_opposite': round(opp / n * 100, 1),
        'dir_avoid': round(avoid / n * 100, 1),
        'range_accuracy': round(range_hit / n * 100, 1),
        'sup_hold_rate': round(sup_hold / n * 100, 1),
        'sup_break_rate': round(sup_break / n * 100, 1),
        'res_hold_rate': round(res_hold / n * 100, 1),
        'res_break_rate': round(res_break / n * 100, 1),
    }

if __name__ == '__main__':
    rows = run_backtest()
    st = stats(rows)
    print('===== 预判回测 v2（补救版）=====')
    print(f'样本: {st["n"]} 个交易日')
    print(f'方向命中率: {st["dir_accuracy"]}%')
    print(f'方向相反率: {st["dir_opposite"]}%  （v1 为 52.6%）')
    print(f'方向规避率(方向不明): {st["dir_avoid"]}%')
    print(f'区间覆盖率: {st["range_accuracy"]}%  （v1 为 10.5%）')
    print(f'支撑守住率: {st["sup_hold_rate"]}%（跌破 {st["sup_break_rate"]}%，v1 跌破 36.8%）')
    print(f'压力守住率: {st["res_hold_rate"]}%（突破 {st["res_break_rate"]}%，v1 突破 57.9%）')
    out = {'stats': st, 'rows': rows}
    with open(os.path.join(BT_DIR, 'backtest_result_v2.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print('\n结果已保存 -> backtest_data/backtest_result_v2.json')
    print('\n===== 逐日明细 =====')
    for r in rows:
        p = r['pred']; a = r['actual']; v = r['verdict']
        sup = f"{p['support']:.1f}" if p['support'] else '—'
        res = f"{p['resistance']:.1f}" if p['resistance'] else '—'
        print(f"{r['T'][5:]}→{r['next'][5:]} | {p['direction']}({sup}~{res}) | 实际{a['pct']:+.2f}% | 方向{v['direction']} 区间{v['range']} 支撑{v['support']} 压力{v['resistance']}")
