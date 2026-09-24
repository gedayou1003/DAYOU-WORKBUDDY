#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上证综指 000001 · 四周期联动 + 区间套分析（15/60/120分钟 + 日线）
每周期：chan-signal（趋势/中枢/买卖点）+ MA55（位置/斜率）
区间套：相邻两周期（大周期中枢位置 + 小周期买卖点）共振判定

用法：
    $PY .workbuddy/analyze_000001_multi.py                 # 写 outputs/000001_四周期联动_<日期>.json
    $PY .workbuddy/analyze_000001_multi.py --out X.json    # 写到指定路径（冒烟/测试用）

退出码（2026-09-23 起有语义）：
    0 = 正常生成数据包
    1 = 行情不足/含 NaN（**不写数据包**）、或数据包写盘失败
    说明：原先无论如何都退 0，且数据不足时会打印一片 nan 并把裸 NaN 写进 JSON
    （不是合法 JSON），产出「看着成功」的废数据包 —— 与 D1（forecast_analyze）同族。
"""
import sys, os, json, urllib.request
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
from paths import SKILLS
SKILL = os.path.join(SKILLS, "chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chan_signal import run_engine, build_analysis
import qt_api      # 腾讯接口多域名 failover（2026-09-18：web.ifzq.gtimg.cn 被代理拦）
from dragonball_signals import (classify_macd_state, classify_pullback,
                                detect_zero_cross, detect_main_up)  # DRAGONBALL 融合（2026-09-24）

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
    d, _src = qt_api.get_json(
        f'/appstock/app/fqkline/get?param=sh000001,day,2024-01-01,{end},{count},qfq', timeout=30)
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

    # DRAGONBALL 融合 P0（2026-09-24）：MACD 六态（篇4 稳定性分类）。
    # 与 trend（缠论趋势）/ ma_slope（均线斜率）语义独立，不混用。
    close_s = df['close']
    e12 = close_s.ewm(span=12, adjust=False).mean()
    e26 = close_s.ewm(span=26, adjust=False).mean()
    dif = e12 - e26
    dea = dif.ewm(span=9, adjust=False).mean()
    mstate = classify_macd_state(float(dif.iloc[-1]), float(dea.iloc[-1]))
    zcross = detect_zero_cross(float(dif.iloc[-1]), float(dea.iloc[-1]),
                               float(dif.iloc[-2]), float(dea.iloc[-2]))
    # 笔类型序列（供主涨段/X段判定；篇3 已确认「带结构段=笔」）
    bi_types = [b.get('bi_type') for b in engine.get('bi_list', [])]

    return {
        'tag': tag, 'price': round(price, 2), 'trend': trend, 'pzs': pzs,
        'ma55': round(ma55, 2), 'ma_pos': ma_pos, 'ma_slope': ma_slope,
        'ma_dist_pct': round(ma_dist, 2),
        'macd_state': mstate['state'], 'macd_state_side': mstate['side'],
        'zero_cross': zcross,
        'bi_types': bi_types,
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
    # --out PATH：写到指定路径（冒烟/测试用）。默认仍是 outputs/000001_四周期联动_<日期>.json。
    # 2026-09-23 加：冒烟原先只能让它写**真实 outputs/**，每天跑一次冒烟就在交付目录里
    # 留一份冒烟数据包（冒烟自己的原则是「需落盘的产物一律写临时目录」，这处是漏网）。
    out_override = None
    if '--out' in sys.argv:
        i = sys.argv.index('--out')
        if i + 1 >= len(sys.argv):
            print('[FAIL] --out 后面要跟路径', file=sys.stderr)
            return 1
        out_override = sys.argv[i + 1]

    # 取数失败要**有意报错**，不能让它抛 traceback（2026-09-23 加固，与 D1 同口径）：
    # 崩栈与「有意报错」在退出码上同形（都是 1），但前者没有一句诊断。
    try:
        periods = [
            ('日线', fetch_day(), False),
            ('120分钟', fetch_mk('m120'), True),
            ('60分钟', fetch_mk('m60'), True),
            ('15分钟', fetch_mk('m15'), True),
        ]
    except Exception as e:                                  # noqa: BLE001
        print('[FAIL] 行情取不到（%s：%s）—— 未生成数据包'
              % (type(e).__name__, e), file=sys.stderr)
        return 1

    # 数据充足性守卫（2026-09-23 加），**必须在 analyze() 之前**：
    #   · 不足 55 根时 ma.iloc[-1] 是 NaN → 打印一片 nan、JSON 里写进裸 NaN
    #     （不是合法 JSON），而退出码仍是 0 —— 一份看着「生成成功」的废数据包；
    #   · 0 根时 ma.iloc[-1] 直接 IndexError **崩栈** —— 那是脚本坏了的样子，不是失败路径。
    # 两种情况都改为有意报错：退 1、不写数据包，让上游一眼看见。
    frames, thin = [], []
    for tag, rows, minute in periods:
        df = to_df(rows, minute)
        if len(df) < 60:
            thin.append('%s(%d 根)' % (tag, len(df)))
        frames.append((tag, df, minute))
    if thin:
        print('[FAIL] 行情数据不足（MA55 需 ≥60 根）：%s —— 未生成数据包'
              % '、'.join(thin), file=sys.stderr)
        return 1

    results = {}
    for tag, df, minute in frames:
        results[tag] = analyze(df, tag)
        r = results[tag]
        sig = r['latest_signal']
        sig_str = f"{sig['name']}@{sig['price']}({sig['date']})" if sig else '无'
        print(f"[{tag}] 价{r['price']} 趋势{r['trend']} {r['pzs']} | MA55={r['ma55']}({r['ma_pos']},{r['ma_slope']},{r['ma_dist_pct']:+.2f}%) | 最新信号:{sig_str}")

    # 兜底：根数够但算出来是 NaN（数据源给了空值）同样不产出数据包
    nan_dim = [t for t, v in results.items()
               if v['ma55'] != v['ma55'] or v['price'] != v['price']]
    if nan_dim:
        print('[FAIL] 行情含 NaN（%s），未生成数据包' % '、'.join(nan_dim), file=sys.stderr)
        return 1

    # DRAGONBALL 融合（2026-09-24）：主涨段判定（篇5 严格公式）+ X段（篇3）
    # 主涨段（detect_main_up）：N+2 极强/金叉 → N 上涨 + N 低位。
    #   ⚠️ 级别口径：本脚本四周期（日/120F/60F/15F）非篇4 标准 4 倍级差，
    #   故「N+2 触发」降级为「上一级触发」（跨一级近似跨两级）；
    #   最顶层「日线主涨段」缺周线触发，用日线自身极强/金叉 + 上涨 + 低位近似（标注待周线接入）。
    # X段（classify_pullback）：N+2 主涨段 → N+1 回踩中轨（有无结构）→ N 级别 X段。
    #   N+1 有无结构用 bi_count（笔数）代理（一笔必含顶分型+底分型+合并K线）。
    def _main_up(n2_state, n2_zc, bi_types, dist):
        return detect_main_up(n2_state, n2_zc, bi_types, dist)['is_main_up']

    main_up_day = _main_up(results['日线']['macd_state'], results['日线']['zero_cross'],
                           results['日线']['bi_types'], results['日线']['ma_dist_pct'])
    main_up_120 = _main_up(results['日线']['macd_state'], results['日线']['zero_cross'],
                           results['120分钟']['bi_types'], results['120分钟']['ma_dist_pct'])
    main_up_60 = _main_up(results['120分钟']['macd_state'], results['120分钟']['zero_cross'],
                          results['60分钟']['bi_types'], results['60分钟']['ma_dist_pct'])
    main_up_15 = _main_up(results['60分钟']['macd_state'], results['60分钟']['zero_cross'],
                          results['15分钟']['bi_types'], results['15分钟']['ma_dist_pct'])

    main_up = {
        '日线主涨段': main_up_day,
        '120分钟主涨段': main_up_120,
        '60分钟主涨段': main_up_60,
        '15分钟主涨段': main_up_15,
    }
    xduan = {
        '60F_X段(日线主涨→120F回踩)': classify_pullback(
            has_structure_n1=(results['120分钟']['bi_count'] > 0),
            is_main_up_n2=main_up_day),
        '15F_X段(120F主涨→60F回踩)': classify_pullback(
            has_structure_n1=(results['60分钟']['bi_count'] > 0),
            is_main_up_n2=main_up_120),
    }
    print('\n== DRAGONBALL 主涨段判定（篇5）==')
    for k, v in main_up.items():
        print(f"[{k}] → {'主涨段' if v else '非主涨段'}")
    print('== DRAGONBALL X段判定（篇3）==')
    for k, v in xduan.items():
        print(f"[{k}] → {v}")

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
    out = out_override or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       '..', 'outputs', f'000001_四周期联动_{date_str}.json')
    out = os.path.normpath(out)
    payload = {'periods': {k: v for k, v in results.items()}, 'taoquan': pairs,
               'xduan': xduan, 'main_up': main_up}
    try:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
    except OSError as e:
        print('[FAIL] 数据包写盘失败：%s' % e, file=sys.stderr)
        return 1
    print(f'\nJSON 已保存: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
