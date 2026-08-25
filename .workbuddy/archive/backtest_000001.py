#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上证综指 000001 · chan-signal 打分回测

打分模型（信号主导，10 分制 → 仓位）：
  卖点信号：一卖/二卖=1分(清仓)、三卖=2分
  买点信号：一买=8分、二买=9分、三买=7分，再叠加趋势(±0.5)/中枢(±0.5)微调
  无信号 = 0 分空仓；仓位 = 分数 / 10

回测纪律：
  - 信号用「到当天收盘为止」的数据计算（无未来函数），次日生效
  - 单边成本 COST=0.0003（万3，覆盖佣金+滑点）
  - 初始资金 100000，只做 000001
"""
import sys, os, json, urllib.request
from datetime import datetime
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = r"C:\Users\gedayou\.workbuddy\skills\chan-signal__skillhub"
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine, build_analysis

UA = {'User-Agent': 'Mozilla/5.0'}
CODE = '000001'
NAME = '上证综指'

# ---------- 打分模型（信号主导，可调） ----------
# 卖点：一卖/二卖=1分(清仓)、三卖=2分；买点：一买=8、二买=9、三买=7；无信号=0空仓
SELL_BASE = {1: 1.0, 2: 1.0, 3: 2.0}
BUY_BASE = {1: 8.0, 2: 9.0, 3: 7.0}
ADJ = 0.5            # 趋势/中枢的微调幅度
MIN_BARS = 60        # 最少K线数才参与交易
WINDOW = 500         # 滚动窗口
COST = 0.0003        # 单边交易成本（万3）
INITIAL = 100000.0


def fetch_day(start, end, count):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,{start},{end},{count},qfq'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode('utf-8'))
    data = d.get('data', {}).get('sh000001', {})
    rows = data.get('qfqday') or data.get('day') or []
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


def score_at(df_sub, today_str):
    """用 df_sub（到当天收盘为止）跑引擎，返回 (score, trend, 最新信号描述)
    信号主导：卖点→清仓(1~2分)，买点→建仓(7~9分)，趋势/中枢仅做±0.5微调；无信号=空仓。"""
    engine = run_engine(df_sub)
    analysis = build_analysis(CODE, df_sub, engine, 9, recent_bars=0)
    s = analysis.get('structure', {})
    trend = s.get('current_trend', '')
    pzs = s.get('price_vs_zs', '')

    # 已确认信号（date < 今天，天然滞后 1 天，进一步兜底过滤）
    signals = [x for x in analysis.get('signals', []) if x.get('date', '') < today_str]
    if not signals:
        return 0.0, trend, '无信号'

    latest_date = signals[0]['date']
    batch = [x for x in signals if x['date'] == latest_date]
    buys = [x for x in batch if x['type'] == 'buy']
    sells = [x for x in batch if x['type'] == 'sell']

    t_adj = ADJ if trend == '向上' else (-ADJ if trend == '向下' else 0.0)
    z_adj = ADJ if '中枢上方' in pzs else (-ADJ if '中枢下方' in pzs else 0.0)

    if sells:
        # 卖点主导：清仓（取最强卖点，分数最低）
        score = min(SELL_BASE.get(x['level'], 1.0) for x in sells)
    elif buys:
        # 买点主导：建仓（取最强买点，分数最高），趋势/中枢微调
        base = max(BUY_BASE.get(x['level'], 7.0) for x in buys)
        score = base + t_adj + z_adj
    else:
        score = 0.0

    score = max(0.0, min(10.0, score))
    sig_desc = '、'.join(f"{x['name']}@{x['date']}" for x in batch) if batch else '无'
    return score, trend, sig_desc


def backtest(df, initial=INITIAL, window=WINDOW, cost=COST):
    n = len(df)
    dates = df['date'].dt.strftime('%Y-%m-%d').tolist()
    closes = df['close'].values.astype(float)

    equity = initial
    w_prev = 0.0          # 上一日收盘确定的仓位（次日生效）
    equity_curve = []     # 每日收盘净值
    bench_curve = []      # 基准（满仓持有）净值
    trades = []           # 关键调仓记录
    daily = []

    for i in range(n):
        today = dates[i]
        r = closes[i] / closes[i-1] - 1.0 if i > 0 else 0.0

        # 当日收益：用昨日仓位吃到今日涨跌
        equity = equity * (1.0 + w_prev * r)

        # 计算当日目标仓位（用当日收盘数据，次日生效）
        if len(df.iloc[max(0, i-window):i+1]) >= MIN_BARS:
            df_sub = df.iloc[max(0, i-window):i+1]
            score, trend, sig = score_at(df_sub, today)
            w_target = score / 10.0
        else:
            score, trend, sig, w_target = 0.0, '', '数据不足', 0.0

        # 调仓成本（次日按 w_target 调整，成本在次日发生时计，这里简化在当日按 Δw 计）
        dw = abs(w_target - w_prev)
        if dw > 1e-9:
            equity = equity * (1.0 - dw * cost)
            if dw >= 0.2:
                action = '加仓' if w_target > w_prev else '减仓'
                trades.append({
                    'date': today, 'score': round(score, 1), 'trend': trend,
                    'signal': sig, 'w_from': round(w_prev, 2), 'w_to': round(w_target, 2),
                    'action': action, 'close': round(closes[i], 2),
                })

        w_prev = w_target
        equity_curve.append(equity)
        bench = initial * (closes[i] / closes[0])
        bench_curve.append(bench)
        daily.append({'date': today, 'close': round(closes[i], 2), 'score': round(score, 1),
                      'weight': round(w_target, 2), 'equity': round(equity, 2)})

    return {'dates': dates, 'closes': closes.tolist(), 'equity_curve': equity_curve,
            'bench_curve': bench_curve, 'trades': trades, 'daily': daily,
            'final_equity': equity}


def stats(res, initial=INITIAL):
    eq = res['equity_curve']
    bench = res['bench_curve']
    n = len(eq)
    days = n
    total_ret = eq[-1] / initial - 1.0
    bench_ret = bench[-1] / initial - 1.0
    years = days / 365.0
    annual = (eq[-1] / initial) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    # 最大回撤
    peak = eq[0]
    max_dd = 0.0
    for v in eq:
        peak = max(peak, v)
        dd = v / peak - 1.0
        max_dd = min(max_dd, dd)

    # 交易统计
    trades = res['trades']
    buys = [t for t in trades if t['action'] == '加仓']
    sells = [t for t in trades if t['action'] == '减仓']

    return {
        'start': res['dates'][0], 'end': res['dates'][-1], 'days': days,
        'initial': initial, 'final': round(eq[-1], 2),
        'total_ret': round(total_ret * 100, 2), 'bench_ret': round(bench_ret * 100, 2),
        'excess': round((total_ret - bench_ret) * 100, 2),
        'annual': round(annual * 100, 2), 'max_dd': round(max_dd * 100, 2),
        'n_trades': len(trades), 'n_buys': len(buys), 'n_sells': len(sells),
    }


def render_html(res, st):
    """生成自包含暗色 HTML 报告（内联 SVG 净值曲线）"""
    dates = res['dates']
    eq = res['equity_curve']
    bench = res['bench_curve']
    n = len(eq)

    # 抽样画净值曲线（最多 400 点）
    step = max(1, n // 400)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)

    def to_svg_pts(series, ymax):
        pts = []
        for k, i in enumerate(idx):
            x = 60 + k * (620 / (len(idx) - 1))
            y = 40 + (1 - series[i] / ymax) * 320
            pts.append(f"{x:.1f},{y:.1f}")
        return ' '.join(pts)

    ymax = max(max(eq), max(bench)) * 1.05
    eq_pts = to_svg_pts(eq, ymax)
    bench_pts = to_svg_pts(bench, ymax)

    trade_rows = ''
    for t in res['trades'][-40:]:
        cls = 'buy' if t['action'] == '加仓' else 'sell'
        trade_rows += (f'<tr><td>{t["date"]}</td><td>{t["signal"]}</td>'
                       f'<td>{t["trend"]}</td><td class="num">{t["score"]}</td>'
                       f'<td class="num">{t["w_from"]:.2f}</td><td class="num">{t["w_to"]:.2f}</td>'
                       f'<td class="{cls}">{t["action"]}</td><td class="num">{t["close"]}</td></tr>')

    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>000001 chan-signal 打分回测</title>
<style>
:root{{--bg:#141518;--card:#1f2126;--text:#e8e8ea;--muted:#9a9ba3;--border:#2c2e33;--buy:#E24B4A;--sell:#1D9E75}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;padding:24px;line-height:1.6}}
h1{{font-size:18px;font-weight:600}}
.sub{{font-size:12px;color:var(--muted);margin:4px 0 16px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}}
.card .k{{font-size:12px;color:var(--muted)}}
.card .v{{font-size:22px;font-weight:600;margin-top:4px}}
.card .v.pos{{color:var(--buy)}}.card .v.neg{{color:var(--sell)}}
.chart{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:20px}}
.legend{{display:flex;gap:16px;font-size:12px;color:var(--muted);margin-bottom:8px}}
.legend span{{display:flex;align-items:center;gap:5px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{padding:6px 10px;text-align:left;border-bottom:1px solid var(--border)}}
th{{color:var(--muted);font-weight:500}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.buy{{color:var(--buy);font-weight:600}}.sell{{color:var(--sell);font-weight:600}}
.note{{margin-top:16px;font-size:12px;color:var(--muted)}}
</style></head><body>
<h1>上证综指 · chan-signal 打分回测</h1>
<div class="sub">回测区间 {st['start']} ~ {st['end']}（{st['days']} 个交易日）· 初始资金 ¥{st['initial']:,.0f} · 单边成本万3 · 信号次日生效</div>
<div class="cards">
<div class="card"><div class="k">期末资金</div><div class="v">¥{st['final']:,.0f}</div></div>
<div class="card"><div class="k">总收益率</div><div class="v {('pos' if st['total_ret']>=0 else 'neg')}">{st['total_ret']:+.2f}%</div></div>
<div class="card"><div class="k">年化收益率</div><div class="v {('pos' if st['annual']>=0 else 'neg')}">{st['annual']:+.2f}%</div></div>
<div class="card"><div class="k">最大回撤</div><div class="v neg">{st['max_dd']:.2f}%</div></div>
<div class="card"><div class="k">基准(持有)收益</div><div class="v {('pos' if st['bench_ret']>=0 else 'neg')}">{st['bench_ret']:+.2f}%</div></div>
<div class="card"><div class="k">超额收益</div><div class="v {('pos' if st['excess']>=0 else 'neg')}">{st['excess']:+.2f}%</div></div>
<div class="card"><div class="k">调仓次数</div><div class="v">{st['n_trades']}</div></div>
</div>
<div class="chart">
<div class="legend"><span><i class="dot" style="width:10px;height:10px;border-radius:3px;background:var(--buy);display:inline-block"></i>策略净值</span><span><i class="dot" style="width:10px;height:10px;border-radius:3px;background:#5a8dee;display:inline-block"></i>基准(满仓持有)</span></div>
<svg viewBox="0 0 680 400" style="width:100%;height:auto">
<line x1="60" y1="360" x2="680" y2="360" stroke="#2c2e33"/>
<line x1="60" y1="40" x2="60" y2="360" stroke="#2c2e33"/>
<polyline points="{bench_pts}" fill="none" stroke="#5a8dee" stroke-width="1.5" opacity="0.7"/>
<polyline points="{eq_pts}" fill="none" stroke="#E24B4A" stroke-width="2"/>
</svg>
</div>
<h1 style="font-size:15px;margin-bottom:8px">关键调仓记录（最近 40 次）</h1>
<table><thead><tr><th>日期</th><th>信号</th><th>趋势</th><th>分数</th><th>仓位前</th><th>仓位后</th><th>动作</th><th>收盘价</th></tr></thead>
<tbody>{trade_rows}</tbody></table>
<div class="note">打分模型（信号主导）：卖点→一卖/二卖=1分清仓、三卖=2分；买点→一买=8、二买=9、三买=7，叠加趋势/中枢±0.5微调；无信号=0空仓；仓位=分数÷10。以上为历史回测，仅供参考，不构成投资建议。</div>
</body></html>'''


def main():
    rows = fetch_day('2022-01-01', '2026-08-14', 1500)
    df = to_df(rows)
    if len(df) < MIN_BARS:
        print(f'数据不足: {len(df)} 根K线')
        return
    print(f'数据 {len(df)} 根K线, {df["date"].iloc[0].date()} ~ {df["date"].iloc[-1].date()}')

    res = backtest(df)
    st = stats(res)
    st['final'] = round(res['final_equity'], 2)
    st['initial'] = INITIAL

    print(f'''
========== 回测结果 ==========
区间: {st['start']} ~ {st['end']} ({st['days']} 交易日)
初始资金: ¥{st['initial']:,.0f}
期末资金: ¥{st['final']:,.2f}
总收益率: {st['total_ret']:+.2f}%
年化收益率: {st['annual']:+.2f}%
最大回撤: {st['max_dd']:.2f}%
基准(满仓持有)收益: {st['bench_ret']:+.2f}%
超额收益: {st['excess']:+.2f}%
调仓次数: {st['n_trades']} (加仓 {st['n_buys']} / 减仓 {st['n_sells']})
============================''')

    # 保存 JSON
    json_path = os.path.join(HERE, '..', 'outputs', '000001_chan-signal_回测数据_2026-08-14.json')
    json_path = os.path.normpath(json_path)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'stats': st, 'trades': res['trades']}, f, ensure_ascii=False, indent=1)
    print(f'JSON 已保存: {json_path}')

    # 生成 HTML 报告
    html = render_html(res, st)
    html_path = os.path.join(HERE, '..', 'outputs', '000001_chan-signal_回测报告_2026-08-14.html')
    html_path = os.path.normpath(html_path)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'HTML 报告已保存: {html_path}')


if __name__ == '__main__':
    main()
