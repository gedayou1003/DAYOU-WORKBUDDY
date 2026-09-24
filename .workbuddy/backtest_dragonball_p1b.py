# -*- coding: utf-8 -*-
"""backtest_dragonball_p1b.py —— DRAGONBALL 融合 P1-8 / P1-9 回测（补漏）。

补上蓝图 §四里两个「已落地但增量未回测」的融合点：
  P1-8 主涨段判定（detect_main_up）：精确复现笔（chan_signal run_engine）+ 六态/零轴/低位，
       验证「判定为主涨段后 5 日新高概率」是否显著 >50% 且 > 基线。
  P1-9 解除两路径（track_break）：逐日推进状态机，验证「二次跌破后 5 日仍跌概率」是否显著。

因果性保证（无未来函数）：
  - 六态/零轴用 ewm DIF/DEA（因果）；MA55/MA20 用 rolling（因果）；
  - 笔只用 end_index <= T 的「已完成笔」；
  - 未来 5 日 = T+1..T+5 的 high/close（纯前瞻，不参与判定）。

数据源：本地 .workbuddy/backtest_data/day.json（405 根，2025-01-02 ~ 2026-09-02）。

用法：$PY .workbuddy/backtest_dragonball_p1b.py
"""
import importlib.util
import json
import os
import sys

import pandas as pd

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.join(HERE, 'backtest_data')

sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
from paths import SKILLS
SKILL = os.path.join(SKILLS, "chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
from chan_signal import run_engine

spec = importlib.util.spec_from_file_location(
    'dbsig', os.path.join(HERE, 'dragonball_signals.py'))
dbsig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dbsig)


def load_day():
    rows = json.load(open(os.path.join(BT, 'day.json'), encoding='utf-8'))
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def pct(group, total_label):
    n = len(group)
    if n == 0:
        print('  [%-28s] 样本 0' % total_label)
        return
    hit = sum(group)
    print('  [%-28s] n=%-4d 命中 %5.1f%%' % (total_label, n, hit / n * 100))


def main():
    DAY = load_day()
    n = len(DAY)
    close = DAY['close']
    high = DAY['high']

    # 六态 / 零轴（ewm 因果）
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    dif = e12 - e26
    dea = dif.ewm(span=9, adjust=False).mean()
    ma55 = close.rolling(55).mean()
    ma20 = close.rolling(20).mean()

    # 全量笔（chan_signal），只用于「已完成笔」过滤
    try:
        eng = run_engine(DAY)
        bi_list = eng.get('bi_list', [])
    except Exception as e:
        print('[FAIL] chan_signal 引擎跑不出笔：%s' % e, file=sys.stderr)
        return 1
    print('=' * 74)
    print('DRAGONBALL P1-8 / P1-9 回测 · 日线 %d 根 · 笔 %d 条' % (n, len(bi_list)))
    print('=' * 74)

    # 逐日判定（因果）：六态/零轴/低位 + 已完成笔
    states = []
    zcross = []
    for i in range(n):
        states.append(dbsig.classify_macd_state(float(dif.iloc[i]), float(dea.iloc[i]))['state'])
        zcross.append(dbsig.detect_zero_cross(
            float(dif.iloc[i]), float(dea.iloc[i]),
            float(dif.iloc[i - 1]), float(dea.iloc[i - 1])) if i >= 1 else None)

    def bis_upto(i):
        return [b for b in bi_list if b.get('end_index', 0) <= i]

    # ── P1-8 主涨段 ──
    print('\n【P1-8】主涨段判定（detect_main_up）→ 未来 5 日新高')
    main_hit5, non_hit5 = [], []   # 突破前 5 日高点
    main_hit20, non_hit20 = [], []  # 突破前 20 日高点（更严格）
    main_n, non_n = 0, 0
    for T in range(60, n - 5):
        dist = (close.iloc[T] / ma55.iloc[T] - 1) * 100 if pd.notna(ma55.iloc[T]) else None
        r = dbsig.detect_main_up(states[T], zcross[T], bis_upto(T), dist)
        prior5 = high.iloc[T - 4:T + 1].max()
        prior20 = high.iloc[T - 19:T + 1].max()
        fwd5 = high.iloc[T + 1:T + 6].max()
        hit5 = fwd5 > prior5
        hit20 = fwd5 > prior20
        if r['is_main_up']:
            main_n += 1
            main_hit5.append(hit5)
            main_hit20.append(hit20)
        else:
            non_n += 1
            non_hit5.append(hit5)
            non_hit20.append(hit20)
    base_hit5 = (sum(main_hit5) + sum(non_hit5)) / (main_n + non_n)
    base_hit20 = (sum(main_hit20) + sum(non_hit20)) / (main_n + non_n)
    print('  主涨段样本 n=%d（非主涨段 n=%d）' % (main_n, non_n))
    pct(main_hit5, '主涨段→5日新高(破前5日)')
    pct(non_hit5, '非主涨段→5日新高(破前5日)')
    print('  基线（全样本）破前5日高点概率 = %.1f%%' % (base_hit5 * 100))
    print('  ── 更严格：破前 20 日高点 ──')
    pct(main_hit20, '主涨段→5日新高(破前20日)')
    pct(non_hit20, '非主涨段→5日新高(破前20日)')
    print('  基线（全样本）破前20日高点概率 = %.1f%%' % (base_hit20 * 100))

    # ── P1-9 解除两路径 ──
    print('\n【P1-9】解除两路径状态机（track_break）→ 未来 5 日')
    buckets = {'维持': [], '解除': [], '反抽突破': [], '二次跌破': []}
    prev_state = '维持'
    for T in range(20, n - 5):
        m20 = ma20.iloc[T]
        if pd.isna(m20):
            continue
        state, _ = dbsig.track_break(prev_state, float(close.iloc[T]), float(m20))
        fwd_close = close.iloc[T + 5]
        still_down = fwd_close < close.iloc[T]          # 未来 5 日收盘仍低于当日
        fwd_ret = (fwd_close - close.iloc[T]) / close.iloc[T] * 100
        buckets.setdefault(state, []).append((still_down, fwd_ret))
        prev_state = state
    for k in ('解除', '反抽突破', '二次跌破'):
        v = buckets.get(k, [])
        if not v:
            print('  [%-12s] 样本 0' % k)
            continue
        down = sum(1 for s, _ in v if s)
        avg = sum(r for _, r in v) / len(v)
        print('  [%-12s] n=%-3d 5日后仍跌 %5.1f%%  5日收益均值 %+.3f%%'
              % (k, len(v), down / len(v) * 100, avg))

    print('\n' + '=' * 74)
    print('判读：P1-8 若「主涨段→5日新高」显著 > 基线且 >50%，则判定有增量；')
    print('      P1-9 若「二次跌破→5日后仍跌」显著 >「解除/反抽突破」，则二次跌破是有效回调升级确认。')
    print('=' * 74)
    return 0


if __name__ == '__main__':
    sys.exit(main())
