#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上证综指 000001 · 四周期联动 + 区间套分析（15/60/120分钟 + 日线）
每周期：chan-signal（趋势/中枢/买卖点）+ MA55（位置/斜率）
区间套：相邻两周期（大周期中枢位置 + 小周期买卖点）共振判定
"""
import sys, os, json, urllib.request
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
from paths import SKILLS
SKILL = os.path.join(SKILLS, "chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine, build_analysis

UA = {'User-Agent': 'Mozilla/5.0'}
CODE = '000001'


def fetch_mk(mperiod, count=500):
    url = f'https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh000001,{mperiod},,{count}'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8'))
    data = d.get('data', {}).get('sh000001', {})
    rows = data.get(mperiod) or []
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_day(count=500):
    end = datetime.now().strftime('%Y-%m-%d')
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2024-01-01,{end},{count},qfq'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8'))
    data = d.get('data', {}).get('sh000001', {})
    rows = data.get('qfqday') or data.get('day') or []
    rows.sort(key=lambda r: r[0])
    return rows


def to_df(rows, minute):
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)
    df['amount'] = df['vol']
    if minute:
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d%H%M', errors='coerce')
    else:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df


def analyze(df, tag):
    engine = run_engine(df)
    result = build_analysis(CODE, df, engine, 9, recent_bars=0)
    structure = result['structure']
    trend = structure['current_trend']
    pzs = structure['price_vs_zs']
    signals = result['signals']
    latest = signals[0] if signals else None

    ma = df['close'].rolling(55).mean()
    ma55 = float(ma.iloc[-1])
    ma55_prev = float(ma.iloc[-6])
    price = float(df['close'].iloc[-1])
    ma_pos = '上方' if price > ma55 else '下方'
    ma_slope = '向上' if ma55 > ma55_prev else '向下'
    ma_dist = (price / ma55 - 1) * 100

    zs = structure.get('recent_zhongshu', [])
    zs_last = zs[-1] if zs else None

    return {
        'tag': tag, 'price': round(price, 2), 'trend': trend, 'pzs': pzs,
        'ma55': round(ma55, 2), 'ma_pos': ma_pos, 'ma_slope': ma_slope,
        'ma_dist_pct': round(ma_dist, 2),
        'latest_signal': latest, 'recent_signals': signals[:6],
        'bi_count': structure['bi_count'], 'zhongshu_count': structure['zhongshu_count'],
        'last_zs': zs_last,
    }


def assess_pair(big, small):
    """相邻周期区间套：大周期中枢位置 + 小周期最新买卖点"""
    bzs = big.get('last_zs')
    ssig = small.get('latest_signal')
    pair = f"{big['tag']}→{small['tag']}"
    if not bzs:
        return {'pair': pair, 'conclusion': '无中枢参考', 'strength': '', 'pos': None}
    zs_low, zs_high = bzs['low'], bzs['high']
    price = big['price']
    pos = (price - zs_low) / (zs_high - zs_low) if zs_high > zs_low else None

    if not ssig:
        return {'pair': pair, 'conclusion': '小周期无信号', 'strength': '', 'pos': round(pos * 100, 1) if pos is not None else None}

    stype, sname = ssig['type'], ssig['name']
    if pos is None:
        return {'pair': pair, 'conclusion': '中枢异常', 'strength': '', 'pos': None}

    near_low = -0.05 <= pos <= 0.15
    near_high = 0.85 <= pos <= 1.05
    in_zs = 0 <= pos <= 1

    if stype == 'buy':
        if near_low:
            conclusion, strength = f"区间套买点（{sname}）", '强'
        elif in_zs:
            conclusion, strength = f"区间套买点（{sname}）", '中'
        elif pos < 0:
            conclusion, strength = f"买点但大周期已跌破中枢（{sname}）", '弱'
        else:
            conclusion, strength = f"买点但大周期在压力上方（{sname}）", '弱'
    elif stype == 'sell':
        if near_high:
            conclusion, strength = f"区间套卖点（{sname}）", '强'
        elif in_zs:
            conclusion, strength = f"区间套卖点（{sname}）", '中'
        elif pos > 1:
            conclusion, strength = f"卖点但大周期已突破中枢（{sname}）", '弱'
        else:
            conclusion, strength = f"卖点但大周期在支撑下方（{sname}）", '弱'
    else:
        conclusion, strength = '无共振', ''

    return {'pair': pair, 'conclusion': conclusion, 'strength': strength, 'pos': round(pos * 100, 1)}


def main():
    periods = [
        ('日线', fetch_day(), False),
        ('120分钟', fetch_mk('m120'), True),
        ('60分钟', fetch_mk('m60'), True),
        ('15分钟', fetch_mk('m15'), True),
    ]
    results = {}
    for tag, rows, minute in periods:
        df = to_df(rows, minute)
        results[tag] = analyze(df, tag)
        r = results[tag]
        sig = r['latest_signal']
        sig_str = f"{sig['name']}@{sig['price']}({sig['date']})" if sig else '无'
        print(f"[{tag}] 价{r['price']} 趋势{r['trend']} {r['pzs']} | MA55={r['ma55']}({r['ma_pos']},{r['ma_slope']},{r['ma_dist_pct']:+.2f}%) | 最新信号:{sig_str}")

    print('\n== 区间套判定（相邻周期）==')
    pairs = [
        assess_pair(results['日线'], results['120分钟']),
        assess_pair(results['120分钟'], results['60分钟']),
        assess_pair(results['60分钟'], results['15分钟']),
    ]
    for p in pairs:
        pos = f"{p['pos']}%" if p['pos'] is not None else '—'
        print(f"[{p['pair']}] 大周期价格在中枢{pos}位置 → {p['conclusion']}{'('+p['strength']+')' if p['strength'] else ''}")

    date_str = datetime.now().strftime('%Y-%m-%d')
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs', f'000001_四周期联动_{date_str}.json')
    out = os.path.normpath(out)
    payload = {'periods': {k: v for k, v in results.items()}, 'taoquan': pairs}
    json.dump(payload, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print(f'\nJSON 已保存: {out}')


if __name__ == '__main__':
    main()
