#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chan-signal 打分回测 · 通用版（任意标的 · 多配置 confidence 对比）

用法:
  python backtest_stock.py --code 002484 --name 江海股份
  python backtest_stock.py --code 000001 --name 上证综指 --market sh

阶段1：逐日跑引擎，缓存每日信号快照
阶段2：用不同 confidence 阈值重放仓位，对比收益/回撤/调仓
"""
import sys, os, json, urllib.request, argparse
from datetime import datetime
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = r"C:\Users\gedayou\.workbuddy\skills\chan-signal__skillhub"
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine, build_analysis

UA = {'User-Agent': 'Mozilla/5.0'}

SELL_BASE = {1: 1.0, 2: 1.0, 3: 2.0}
BUY_BASE = {1: 8.0, 2: 9.0, 3: 7.0}
ADJ = 0.5
MIN_BARS = 60
WINDOW = 500
COST = 0.0003
INITIAL = 100000.0
START = '2022-01-01'

CONFIGS = [
    {'name': '全部信号', 'min_conf': 0.0, 'color': '#E24B4A'},
    {'name': '过滤弱信号(≥0.7)', 'min_conf': 0.7, 'color': '#E8A33D'},
    {'name': '仅背驰确认(≥0.8)', 'min_conf': 0.8, 'color': '#1D9E75'},
]


def market_prefix(code):
    if code.startswith(('6', '9')):
        return 'sh'
    return 'sz'


def fetch_day(code, mk, start, end, count):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={mk}{code},day,{start},{end},{count},qfq'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8'))
    data = d.get('data', {}).get(f'{mk}{code}', {})
    rows = data.get('qfqday') or data.get('day') or []
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_xau(start, end):
    """新浪全球期货 · 伦敦金现货(XAU, 美元/盎司) 日K"""
    import re
    url = 'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol=XAU'
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8')
    m = re.search(r'\((\[.*\])\)', raw, re.S)
    if not m:
        return []
    arr = json.loads(m.group(1))
    rows = []
    for d in arr:
        dt = d.get('date', '')
        if start <= dt <= end:
            rows.append([dt, float(d['open']), float(d['close']), float(d['high']), float(d['low']), float(d.get('volume') or 0)])
    rows.sort(key=lambda r: r[0])
    return rows


def to_df(rows):
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)
    df['amount'] = df['vol']
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df


def snapshot(df_sub, today_str):
    engine = run_engine(df_sub)
    analysis = build_analysis('', df_sub, engine, 9, recent_bars=0)
    s = analysis.get('structure', {})
    trend = s.get('current_trend', '')
    pzs = s.get('price_vs_zs', '')
    signals = [x for x in analysis.get('signals', []) if x.get('date', '') < today_str]
    if signals:
        latest_date = signals[0]['date']
        batch = [{'name': x['name'], 'type': x['type'], 'level': x['level'],
                  'confidence': x.get('confidence', 0), 'date': x['date']} for x in signals if x['date'] == latest_date]
    else:
        batch = []
    return {'trend': trend, 'pzs': pzs, 'signals': batch}


def build_snapshots(df):
    n = len(df)
    dates = df['date'].dt.strftime('%Y-%m-%d').tolist()
    snaps = []
    for i in range(n):
        today = dates[i]
        if len(df.iloc[max(0, i - WINDOW):i + 1]) < MIN_BARS:
            snaps.append({'trend': '', 'pzs': '', 'signals': []})
            continue
        df_sub = df.iloc[max(0, i - WINDOW):i + 1]
        snaps.append(snapshot(df_sub, today))
        if (i + 1) % 100 == 0:
            print(f'  快照进度 {i+1}/{n}', flush=True)
    return dates, snaps


def replay(dates, snaps, closes, min_conf):
    n = len(snaps)
    equity = INITIAL
    w_prev = 0.0
    eq_curve = []
    trades = []
    for i in range(n):
        r = closes[i] / closes[i - 1] - 1.0 if i > 0 else 0.0
        equity *= (1.0 + w_prev * r)

        snap = snaps[i]
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
                trades.append({'date': dates[i], 'score': round(w_target * 10, 1), 'trend': snap['trend'],
                               'signal': sig_desc, 'w_from': round(w_prev, 2), 'w_to': round(w_target, 2),
                               'action': action, 'close': round(closes[i], 2)})
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


def render_compare(name, dates, closes, bench_curve, results, st_list):
    n = len(closes)
    step = max(1, n // 400)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)

    ymax = max(bench_curve[-1], max(r['equity_curve'][-1] for r in results)) * 1.05

    def pts(series):
        out = []
        for k, i in enumerate(idx):
            x = 60 + k * (620 / (len(idx) - 1))
            y = 40 + (1 - series[i] / ymax) * 320
            out.append(f"{x:.1f},{y:.1f}")
        return ' '.join(out)

    polylines = f'<polyline points="{pts(bench_curve)}" fill="none" stroke="#5a8dee" stroke-width="1.5" opacity="0.6"/>'
    for r, cfg in zip(results, CONFIGS):
        polylines += f'<polyline points="{pts(r["equity_curve"])}" fill="none" stroke="{cfg["color"]}" stroke-width="2"/>'

    legend = ''.join(f'<span><i class="dot" style="width:10px;height:10px;border-radius:3px;background:{cfg["color"]};display:inline-block"></i>{cfg["name"]}</span>' for cfg in CONFIGS)
    legend += '<span><i class="dot" style="width:10px;height:10px;border-radius:3px;background:#5a8dee;display:inline-block"></i>基准(满仓持有)</span>'

    rows = ''
    for cfg, st in zip(CONFIGS, st_list):
        ret_cls = 'pos' if st['total_ret'] >= 0 else 'neg'
        rows += (f'<tr><td>{cfg["name"]}</td><td class="num">¥{st["final"]:,.0f}</td>'
                 f'<td class="num {ret_cls}">{st["total_ret"]:+.2f}%</td>'
                 f'<td class="num {ret_cls}">{st["annual"]:+.2f}%</td>'
                 f'<td class="num neg">{st["max_dd"]:.2f}%</td>'
                 f'<td class="num">{st["n_trades"]}</td></tr>')

    bench_ret = (bench_curve[-1] / INITIAL - 1) * 100
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} chan-signal 回测对比</title>
<style>
:root{{--bg:#141518;--card:#1f2126;--text:#e8e8ea;--muted:#9a9ba3;--border:#2c2e33;--buy:#E24B4A;--sell:#1D9E75}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;padding:24px;line-height:1.6}}
h1{{font-size:18px;font-weight:600}}
.sub{{font-size:12px;color:var(--muted);margin:4px 0 16px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid var(--border)}}
th{{color:var(--muted);font-weight:500}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.pos{{color:var(--buy)}}.neg{{color:var(--sell)}}
.chart{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:20px}}
.legend{{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--muted);margin-bottom:8px}}
.legend span{{display:flex;align-items:center;gap:5px}}
.note{{font-size:12px;color:var(--muted)}}
</style></head><body>
<h1>{name} · chan-signal 回测对比（confidence 过滤提纯）</h1>
<div class="sub">回测区间 {dates[0]} ~ {dates[-1]}（{n} 个交易日）· 初始 ¥{INITIAL:,.0f} · 单边成本万3 · 信号次日生效</div>
<table><thead><tr><th>配置</th><th>期末资金</th><th>总收益</th><th>年化</th><th>最大回撤</th><th>调仓次数</th></tr></thead>
<tbody>{rows}
<tr style="border-top:1px solid var(--border)"><td>基准(满仓持有)</td><td class="num">¥{bench_curve[-1]:,.0f}</td><td class="num {('pos' if bench_ret>=0 else 'neg')}">{bench_ret:+.2f}%</td><td class="num">—</td><td class="num">—</td><td class="num">—</td></tr></tbody></table>
<div class="chart">
<div class="legend">{legend}</div>
<svg viewBox="0 0 680 400" style="width:100%;height:auto">
<line x1="60" y1="360" x2="680" y2="360" stroke="#2c2e33"/>
<line x1="60" y1="40" x2="60" y2="360" stroke="#2c2e33"/>
{polylines}
</svg>
</div>
<div class="note">打分（信号主导）：卖点(一卖/二卖=1分、三卖=2分)清仓；买点(一买=8、二买=9、三买=7)+趋势/中枢±0.5；无主导信号=保持仓位；仓位=分数÷10。confidence 档位：一买/一卖=0.8(背驰)或0.5(无背驰)、二买/二卖=0.7、三买/三卖=0.75。以上为历史回测，仅供参考，不构成投资建议。</div>
</body></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', default='000001')
    ap.add_argument('--name', default='上证综指')
    ap.add_argument('--market', default='')
    ap.add_argument('--source', default='tencent', help="数据源: tencent(A股/指数) / xau(黄金现货美元)")
    args = ap.parse_args()

    code = args.code
    name = args.name
    mk = args.market or market_prefix(code)
    date_str = datetime.now().strftime('%Y-%m-%d')

    CACHE = os.path.join(HERE, f'{code}_信号流缓存.json')
    OUT_HTML = os.path.normpath(os.path.join(HERE, '..', 'outputs', f'{code}_chan-signal_回测对比_{date_str}.html'))
    OUT_JSON = os.path.normpath(os.path.join(HERE, '..', 'outputs', f'{code}_chan-signal_回测对比数据_{date_str}.json'))

    print(f'== {code} {name} · 阶段1：取数 + 逐日跑引擎 ==')
    end_date = datetime.now().strftime('%Y-%m-%d')

    def fetch_rows():
        if args.source == 'xau':
            return fetch_xau(START, end_date)
        return fetch_day(code, mk, START, end_date, 2000)

    if os.path.exists(CACHE):
        print('检测到缓存，直接复用')
        data = json.load(open(CACHE, encoding='utf-8'))
        dates = data['dates']
        snaps = data['snaps']
    else:
        rows = fetch_rows()
        df = to_df(rows)
        if len(df) < MIN_BARS:
            print(f'数据不足: {len(df)} 根K线')
            return
        dates, snaps = build_snapshots(df)
        json.dump({'dates': dates, 'snaps': snaps}, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'快照已缓存: {CACHE}')

    rows = fetch_rows()
    df = to_df(rows)
    closes = df['close'].values.astype(float).tolist()
    dates = df['date'].dt.strftime('%Y-%m-%d').tolist()
    bench_curve = [INITIAL * (c / closes[0]) for c in closes]

    print(f'数据 {len(closes)} 根K线, {dates[0]} ~ {dates[-1]}（基准区间涨幅 {(closes[-1]/closes[0]-1)*100:+.2f}%）')
    print('== 阶段2：多配置重放 ==')
    results, st_list = [], []
    for cfg in CONFIGS:
        res = replay(dates, snaps, closes, cfg['min_conf'])
        st = stats(res['equity_curve'], res['trades'])
        results.append(res)
        st_list.append(st)
        print(f"[{cfg['name']}] 期末 ¥{st['final']:,.0f} | 总收益 {st['total_ret']:+.2f}% | 年化 {st['annual']:+.2f}% | 回撤 {st['max_dd']:.2f}% | 调仓 {st['n_trades']}")

    out_data = {'code': code, 'name': name, 'dates': dates, 'configs': CONFIGS, 'stats': st_list,
                'trades': {cfg['name']: res['trades'] for cfg, res in zip(CONFIGS, results)}}
    json.dump(out_data, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(OUT_HTML, 'w', encoding='utf-8').write(render_compare(name, dates, closes, bench_curve, results, st_list))
    print(f'对比 HTML: {OUT_HTML}')
    print(f'对比 JSON: {OUT_JSON}')


if __name__ == '__main__':
    main()
