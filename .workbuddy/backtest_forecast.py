#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上证综指 000001 · 预判回测（最近 1 个月）
- 用当前 chan-signal 模型（日线/周线/60F/15F）对每个交易日收盘后生成"次日预判"
- 结合 T&J 技术分析观点做方向参考
- 对比次日实际 OHLC，统计方向/区间/支撑/压力偏差
- 无未来函数：预判只用「截止 T 收盘」的数据
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

# ---------- 数据加载 ----------
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

# ---------- T&J 观点加载 + 方向提取 ----------
TJ = json.load(open(os.path.join(BT_DIR, 'tj_topics.json'), encoding='utf-8'))
BULL_WORDS = ['金叉', '主涨', '反弹', 'b浪', 'B浪', '看多', '突破', '支撑有效', '低吸', '止跌', '上涨', '强势', '右侧', '二买', '三买', '底背离']
BEAR_WORDS = ['死叉', '主跌', 'c浪', 'C浪', '看空', '压制', '回落', '新低', '二次股灾', '下跌', '弱势', '顶背离', '一卖', '二卖', '三卖', '调整', '风险', '中枢构建']

def tj_direction(date_str):
    """提取 date_str 当日（或之前最近一个交易日）T&J 技术分析帖子的方向，返回 (direction, text)"""
    day_topics = [t for t in TJ if t['create_time'][:10] == date_str]
    if not day_topics:
        return None, ''
    # 只看技术分析相关的
    tech_topics = []
    for t in day_topics:
        txt = t['text']
        if any(w in txt for w in BULL_WORDS + BEAR_WORDS):
            tech_topics.append(txt)
    if not tech_topics:
        return None, ''
    joined = '\n'.join(tech_topics)
    bull = sum(1 for w in BULL_WORDS if w in joined)
    bear = sum(1 for w in BEAR_WORDS if w in joined)
    if bull > bear:
        return '偏多', joined[:200]
    elif bear > bull:
        return '偏空', joined[:200]
    return '震荡', joined[:200]

# ---------- 预判规则 ----------
# 周期权重（方向打分）
WEIGHT = {'日线': 2, '周线': 2, '60分钟': 2, '15分钟': 1}

def run_periods(df_day, df_week, df_m60, df_m15):
    """对给定截止时点的数据，跑 4 周期引擎，返回结果 dict"""
    results = {}
    periods = [('日线', 9, df_day), ('周线', 7, df_week), ('60分钟', 6, df_m60), ('15分钟', 15, df_m15)]
    for tag, cat, df in periods:
        if df is None or len(df) < 30:
            results[tag] = None
            continue
        try:
            eng = run_engine(df)
            res = build_analysis(CODE, df, eng, cat, recent_bars=0)
            results[tag] = res
        except Exception as e:
            results[tag] = None
    return results

def predict(results, asof_date):
    """把 4 周期引擎结果综合成预判。asof_date: 预判基准日，只取该日前 20 天内的近期信号（过滤过期信号）"""
    cutoff = (pd.Timestamp(asof_date) - pd.Timedelta(days=20)).strftime('%Y-%m-%d')
    score = 0
    buys, sells = [], []  # (price, date, name, tag)
    for tag, w in WEIGHT.items():
        r = results.get(tag)
        if not r:
            continue
        sigs = [s for s in r.get('signals', []) if (s.get('date', '') or '') >= cutoff]
        if not sigs:
            continue
        latest = sigs[0]  # signal_list 已按 date 倒序
        if latest['type'] == 'buy':
            score += w
            buys.append((latest['price'], latest['date'], latest['name'], tag))
        else:
            score -= w
            sells.append((latest['price'], latest['date'], latest['name'], tag))

    # 方向
    if score >= 2:
        direction = '偏多'
    elif score <= -2:
        direction = '偏空'
    else:
        # 震荡：看 15F 信号微调
        r15 = results.get('15分钟')
        if r15 and r15.get('signals'):
            sigs15 = [s for s in r15['signals'] if (s.get('date', '') or '') >= cutoff]
            if sigs15:
                if sigs15[0]['type'] == 'buy':
                    direction = '震荡偏多'
                else:
                    direction = '震荡偏空'
            else:
                direction = '震荡'
        else:
            direction = '震荡'

    # 支撑/压力：最近的买点/卖点价位（优先级：15F > 60F > 日线 > 周线，短线信号更贴价）
    prio = {'15分钟': 0, '60分钟': 1, '日线': 2, '周线': 3}
    support = min(buys, key=lambda x: prio.get(x[3], 9)) if buys else None
    resistance = min(sells, key=lambda x: prio.get(x[3], 9)) if sells else None
    return {
        'direction': direction,
        'score': score,
        'support': support[0] if support else None,
        'support_name': f"{support[2]}@{support[3]}" if support else None,
        'resistance': resistance[0] if resistance else None,
        'resistance_name': f"{resistance[2]}@{resistance[3]}" if resistance else None,
        'buys': [(b[0], b[2], b[3]) for b in buys],
        'sells': [(s[0], s[2], s[3]) for s in sells],
    }

# ---------- 回测循环 ----------
def run_backtest():
    # 回测交易日：m15 有足够数据后（约 7-29）到 8-21（8-22/23 周末）
    trade_days = [d for d in DAY['date'].dt.strftime('%Y-%m-%d').tolist()
                  if '2026-07-28' <= d <= '2026-08-21']
    rows = []
    for i, T in enumerate(trade_days):
        # 找到 T 的下一个交易日作为 T+1
        if i + 1 >= len(trade_days):
            next_day = '2026-08-24'  # 8-21 之后是周末，下一个交易日是 8-24
        else:
            next_day = trade_days[i + 1]

        # 截止 T 收盘的数据
        df_day = DAY[DAY['date'] <= pd.Timestamp(T)]
        df_week = WEEK[WEEK['date'] <= pd.Timestamp(T)]
        cutoff = pd.Timestamp(T + ' 15:00:00')
        df_m60 = M60[M60['date'] <= cutoff]
        df_m15 = M15[M15['date'] <= cutoff]

        # 跑引擎 + 预判
        results = run_periods(df_day, df_week, df_m60, df_m15)
        pred = predict(results, T)

        # T&J 方向
        tj_dir, tj_text = tj_direction(T)

        # T+1 实际 OHLC
        act_day = DAY[DAY['date'] == pd.Timestamp(next_day)]
        if act_day.empty:
            continue
        act = act_day.iloc[0]
        prev_close = float(DAY[DAY['date'] == pd.Timestamp(T)].iloc[0]['close']) if not DAY[DAY['date'] == pd.Timestamp(T)].empty else None
        actual = {
            'date': next_day,
            'open': float(act['open']), 'high': float(act['high']),
            'low': float(act['low']), 'close': float(act['close']),
            'pct': round((float(act['close']) - prev_close) / prev_close * 100, 2) if prev_close else None,
        }

        # 偏差判定
        verdict = judge(pred, actual)

        rows.append({
            'T': T, 'next': next_day, 'pred': pred, 'tj_dir': tj_dir,
            'actual': actual, 'verdict': verdict,
        })

    return rows

def judge(pred, actual):
    """判定预判 vs 实际的偏差"""
    pct = actual['pct']
    d = pred['direction']
    # 方向
    if pct is None:
        dir_v = '无数据'
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

    # 区间（支撑~压力是否覆盖实际 low/high）
    lo, hi = actual['low'], actual['high']
    sup = pred['support']
    res = pred['resistance']
    if sup is not None and res is not None:
        inside = (lo >= sup - 0.002 * sup) and (hi <= res + 0.002 * res)
        if inside:
            range_v = '✅区间内'
        else:
            range_v = '⚠️越界'
    else:
        range_v = '—'

    # 支撑
    if sup is not None:
        if lo < sup:
            sup_v = f"❌跌破({round(lo-sup,1)}点)"
        elif lo <= sup + 0.002 * sup:
            sup_v = '✅精准'
        else:
            sup_v = '✅未触及'
    else:
        sup_v = '—'

    # 压力
    if res is not None:
        if hi > res:
            res_v = f"❌突破({round(hi-res,1)}点)"
        elif hi >= res - 0.002 * res:
            res_v = '✅精准'
        else:
            res_v = '✅未触及'
    else:
        res_v = '—'

    return {'direction': dir_v, 'range': range_v, 'support': sup_v, 'resistance': res_v}

# ---------- 统计 ----------
def stats(rows):
    n = len(rows)
    dir_hit = sum(1 for r in rows if '✅' in r['verdict']['direction'])
    dir_opp = sum(1 for r in rows if '❌' in r['verdict']['direction'])
    range_hit = sum(1 for r in rows if '✅' in r['verdict']['range'])
    sup_break = sum(1 for r in rows if '跌破' in r['verdict']['support'])
    sup_hit = sum(1 for r in rows if r['verdict']['support'] in ('✅精准', '✅未触及'))
    res_break = sum(1 for r in rows if '突破' in r['verdict']['resistance'])
    res_hit = sum(1 for r in rows if r['verdict']['resistance'] in ('✅精准', '✅未触及'))

    # 累计误差：支撑位 vs 实际最低，压力位 vs 实际最高
    sup_errs = []
    res_errs = []
    for r in rows:
        if r['pred']['support'] is not None:
            sup_errs.append(r['actual']['low'] - r['pred']['support'])
        if r['pred']['resistance'] is not None:
            res_errs.append(r['actual']['high'] - r['pred']['resistance'])

    # T&J 方向准确率（作为引擎外的人工校准参考）
    tj_hit = 0
    tj_n = 0
    tj_opp = 0
    for r in rows:
        tj = r['tj_dir']
        pct = r['actual']['pct']
        if tj is None or pct is None:
            continue
        tj_n += 1
        if tj == '偏多' and pct > 0.15:
            tj_hit += 1
        elif tj == '偏空' and pct < -0.15:
            tj_hit += 1
        elif tj == '震荡' and abs(pct) <= 0.3:
            tj_hit += 1
        elif tj == '偏多' and pct < -0.15:
            tj_opp += 1
        elif tj == '偏空' and pct > 0.15:
            tj_opp += 1

    return {
        'n': n,
        'dir_accuracy': round(dir_hit / n * 100, 1) if n else 0,
        'dir_opposite': round(dir_opp / n * 100, 1) if n else 0,
        'range_accuracy': round(range_hit / n * 100, 1) if n else 0,
        'sup_break_rate': round(sup_break / n * 100, 1) if n else 0,
        'sup_hold_rate': round(sup_hit / n * 100, 1) if n else 0,
        'res_break_rate': round(res_break / n * 100, 1) if n else 0,
        'res_hold_rate': round(res_hit / n * 100, 1) if n else 0,
        'sup_mean_err': round(sum(sup_errs) / len(sup_errs), 2) if sup_errs else None,
        'res_mean_err': round(sum(res_errs) / len(res_errs), 2) if res_errs else None,
        'tj_n': tj_n,
        'tj_accuracy': round(tj_hit / tj_n * 100, 1) if tj_n else 0,
        'tj_opposite': round(tj_opp / tj_n * 100, 1) if tj_n else 0,
    }

if __name__ == '__main__':
    rows = run_backtest()
    st = stats(rows)
    print('===== 预判回测统计（最近 1 个月）=====')
    print(f'样本: {st["n"]} 个交易日预判')
    print(f'方向准确率: {st["dir_accuracy"]}%（相反 {st["dir_opposite"]}%）')
    print(f'区间覆盖率: {st["range_accuracy"]}%')
    print(f'支撑守住率: {st["sup_hold_rate"]}%（跌破 {st["sup_break_rate"]}%）')
    print(f'压力守住率: {st["res_hold_rate"]}%（突破 {st["res_break_rate"]}%）')
    print(f'支撑平均误差(实际低-支撑): {st["sup_mean_err"]} 点')
    print(f'压力平均误差(实际高-压力): {st["res_mean_err"]} 点')
    print(f'T&J 方向准确率: {st["tj_accuracy"]}%（相反 {st["tj_opposite"]}%，样本 {st["tj_n"]}）')

    # 保存结果
    out = {'stats': st, 'rows': rows}
    with open(os.path.join(BT_DIR, 'backtest_result.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print(f'\n结果已保存 -> backtest_data/backtest_result.json')

    print('\n===== 逐日明细 =====')
    for r in rows:
        p = r['pred']
        a = r['actual']
        v = r['verdict']
        sup = f"{p['support']:.1f}" if p['support'] else '—'
        res = f"{p['resistance']:.1f}" if p['resistance'] else '—'
        tj = r['tj_dir'] or '—'
        print(f"{r['T']}→{r['next']} | 预判{p['direction']}({sup}~{res}) | T&J:{tj} | 实际{a['pct']:+.2f}% 低{a['low']:.1f}高{a['high']:.1f} | 方向{v['direction']} 区间{v['range']} 支撑{v['support']} 压力{v['resistance']}")
