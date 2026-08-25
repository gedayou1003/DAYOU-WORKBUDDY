#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上证综指 000001 · 区间套过滤回测对比

纯日线版：日线信号主导（卖点清仓 / 买点建仓）
区间套版：日线信号 + 周线方向过滤（周线向下时日线买点大幅降仓）
"""
import sys, os, json, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = r"C:\Users\gedayou\.workbuddy\skills\chan-signal__skillhub"
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine, build_analysis

UA = {'User-Agent': 'Mozilla/5.0'}
CODE = '000001'

SELL_BASE = {1: 1.0, 2: 1.0, 3: 2.0}
BUY_BASE = {1: 8.0, 2: 9.0, 3: 7.0}
ADJ = 0.5
COST = 0.0003
INITIAL = 100000.0
MIN_BARS = 60
WINDOW = 500

# 周线方向系数（区间套版：周线定方向）
WEEK_COEF = {'向上': 1.0, '向下': 0.3, '': 0.6}

DAY_CACHE = os.path.join(HERE, '000001_信号流缓存.json')
WEEK_CACHE = os.path.join(HERE, '000001_周线快照缓存.json')


def fetch_fqkline(period, start, end, count):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,{period},{start},{end},{count},qfq'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8'))
    data = d.get('data', {}).get('sh000001', {})
    rows = data.get('qfq' + period) or data.get(period) or []
    rows.sort(key=lambda r: r[0])
    return rows


def week_to_df(rows):
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)
    df['amount'] = df['vol']
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df


def build_week_snaps(week_df, day_dates):
    """逐日截断跑周线引擎，返回与 day_dates 对齐的周线快照"""
    week_dates = week_df['date'].dt.strftime('%Y-%m-%d').tolist()
    snaps = []
    for i, day in enumerate(day_dates):
        sub = week_df[week_df['date'] <= day]
        if len(sub) < 30:
            snaps.append({'trend': '', 'pzs': ''})
            continue
        engine = run_engine(sub)
        analysis = build_analysis(CODE, sub, engine, 7, recent_bars=0)
        structure = analysis['structure']
        snaps.append({'trend': structure['current_trend'], 'pzs': structure['price_vs_zs']})
        if (i + 1) % 200 == 0:
            print(f'  周线快照进度 {i+1}/{len(day_dates)}', flush=True)
    return snaps


def replay(dates, day_snaps, week_snaps, closes, min_conf, use_week):
    n = len(day_snaps)
    equity = INITIAL
    w_prev = 0.0
    eq_curve = []
    trades = []
    for i in range(n):
        r = closes[i] / closes[i - 1] - 1.0 if i > 0 else 0.0
        equity *= (1.0 + w_prev * r)

        snap = day_snaps[i]
        sigs = [x for x in snap['signals'] if x['confidence'] >= min_conf]
        if sigs:
            sells = [x for x in sigs if x['type'] == 'sell']
            buys = [x for x in sigs if x['type'] == 'buy']
            if sells:
                score = min(SELL_BASE.get(x['level'], 1.0) for x in sells)
            elif buys:
                t_adj = ADJ if snap['trend'] == '向上' else (-ADJ if snap['trend'] == '向下' else 0.0)
                z_adj = ADJ if '中枢上方' in snap['pzs'] else (-ADJ if '中枢下方' in snap['pzs'] else 0.0)
                base = max(BUY_BASE.get(x['level'], 7.0) for x in buys)
                if use_week:
                    wt = week_snaps[i]['trend'] if week_snaps else ''
                    coef = WEEK_COEF.get(wt, 0.6)
                    base = base * coef
                score = max(0.0, min(10.0, base + t_adj + z_adj))
            else:
                score = 0.0
            w_target = score / 10.0
        else:
            w_target = w_prev

        dw = abs(w_target - w_prev)
        if dw > 1e-9:
            equity *= (1.0 - dw * COST)
            if dw >= 0.2:
                action = '加仓' if w_target > w_prev else '减仓'
                sig_desc = '、'.join(f"{x['name']}@{x['date']}" for x in sigs) if sigs else '无'
                wk = week_snaps[i]['trend'] if (use_week and week_snaps) else ''
                trades.append({'date': dates[i], 'score': round(w_target * 10, 1), 'trend': snap['trend'],
                               'week': wk, 'signal': sig_desc, 'w_from': round(w_prev, 2),
                               'w_to': round(w_target, 2), 'action': action, 'close': round(closes[i], 2)})
        w_prev = w_target
        eq_curve.append(equity)
    return {'equity_curve': eq_curve, 'trades': trades, 'final': equity}


def stats(eq_curve, trades, initial=INITIAL):
    n = len(eq_curve)
    total_ret = eq_curve[-1] / initial - 1.0
    years = n / 365.0
    annual = (eq_curve[-1] / initial) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    peak = eq_curve[0]
    max_dd = 0.0
    for v in eq_curve:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1.0)
    buys = [t for t in trades if t['action'] == '加仓']
    sells = [t for t in trades if t['action'] == '减仓']
    return {'final': round(eq_curve[-1], 2), 'total_ret': round(total_ret * 100, 2),
            'annual': round(annual * 100, 2), 'max_dd': round(max_dd * 100, 2),
            'n_trades': len(trades), 'n_buys': len(buys), 'n_sells': len(sells)}


def main():
    # 1) 日线快照
    if not os.path.exists(DAY_CACHE):
        print('日线快照缓存不存在，请先跑 backtest_compare_000001.py')
        return
    d = json.load(open(DAY_CACHE, encoding='utf-8'))
    dates = d['dates']
    day_snaps = d['snaps']
    print(f'日线快照 {len(day_snaps)} 天')

    # 2) 周线快照
    if os.path.exists(WEEK_CACHE):
        week_snaps = json.load(open(WEEK_CACHE, encoding='utf-8'))
        print('周线快照命中缓存')
    else:
        print('构建周线快照…')
        rows = fetch_fqkline('week', '2016-01-01', '2026-08-14', 600)
        week_df = week_to_df(rows)
        week_snaps = build_week_snaps(week_df, dates)
        json.dump(week_snaps, open(WEEK_CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'周线快照已缓存 {len(week_snaps)} 天')

    # 3) 收盘价
    rows = fetch_fqkline('day', '2022-01-01', '2026-08-14', 1500)
    df = week_to_df(rows)
    closes = df['close'].values.astype(float).tolist()
    bench_curve = [INITIAL * (c / closes[0]) for c in closes]

    print(f'\n数据 {len(closes)} 天, 基准涨幅 {(closes[-1]/closes[0]-1)*100:+.2f}%')
    print('== 对比：纯日线版 vs 区间套版(周线定方向) ==')

    confs = [('全部信号', 0.0), ('过滤弱信号', 0.7), ('仅背驰确认', 0.8)]
    results = {}
    for mode, use_week in [('纯日线', False), ('区间套', True)]:
        for cname, min_conf in confs:
            res = replay(dates, day_snaps, week_snaps, closes, min_conf, use_week)
            st = stats(res['equity_curve'], res['trades'])
            key = f'{mode}-{cname}'
            results[key] = {'res': res, 'st': st}
            print(f"[{mode} / {cname}] 期末 ¥{st['final']:,.0f} | 总收益 {st['total_ret']:+.2f}% | 年化 {st['annual']:+.2f}% | 回撤 {st['max_dd']:.2f}% | 调仓 {st['n_trades']}")

    # 保存
    out = os.path.normpath(os.path.join(HERE, '..', 'outputs', '000001_区间套回测对比_2026-08-14.json'))
    json.dump({k: {'stats': v['st'], 'trades': v['res']['trades']} for k, v in results.items()},
              open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\nJSON 已保存: {out}')


if __name__ == '__main__':
    main()
