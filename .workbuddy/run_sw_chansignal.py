# -*- coding: utf-8 -*-
"""
申万一级行业 · chan-signal 缠论买卖点分析（日线 + 周线）
========================================================
数据源：akshare index_hist_sw（完整 OHLC 日线/周线，31 个申万一级行业）
引擎层：复用 chan-signal 的 run_engine + build_analysis（纯缠论一二三类买卖点）
限制：申万行业无分钟线（免费源限制），仅日线/周线级别。

用法：
    python run_sw_chansignal.py                     # 默认 801080 申万电子
    python run_sw_chansignal.py --code 801150       # 申万医药生物
    python run_sw_chansignal.py --code 申万计算机     # 支持名称
"""
import sys, os, json, argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
from paths import SKILLS
CHAN_DIR = os.path.join(SKILLS, "chan-signal__skillhub")
sys.path.insert(0, CHAN_DIR)
sys.path.insert(0, os.path.join(CHAN_DIR, 'scripts'))
sys.path.insert(0, HERE)

import pandas as pd
from chan_signal import run_engine, build_analysis
from market_codes import resolve

_parser = argparse.ArgumentParser(description='申万行业 chan-signal 日线/周线缠论分析')
_parser.add_argument('--code', default='801080', help='申万行业代码或名称（默认 801080 申万电子）')
_args = _parser.parse_args()

resolved = resolve(_args.code)
if not resolved or resolved['type'] != '申万一级行业':
    print(f"错误：{_args.code} 不是有效的申万一级行业代码")
    sys.exit(1)

CODE = resolved['code']
NAME = resolved['name']
DATE_STR = datetime.now().strftime('%Y%m%d')


def fetch_sw(period='day'):
    """akshare 申万行业 OHLC，转 chan-signal 需要的 DataFrame"""
    import akshare as ak
    raw = ak.index_hist_sw(symbol=CODE, period=period)
    # akshare 列: 代码,日期,收盘,开盘,最高,最低,成交量,成交额
    df = pd.DataFrame({
        'date': pd.to_datetime(raw['日期']),
        'open': raw['开盘'],
        'close': raw['收盘'],
        'high': raw['最高'],
        'low': raw['最低'],
        'vol': raw['成交量'],
        'amount': raw['成交额'],
    })
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df


def run_one(tag, category, df):
    """运行单周期，返回精简结果（与 run_000001_chansignal 同结构）"""
    if df is None or len(df) < 30:
        return {'tag': tag, 'error': 'K线不足'}
    engine_result = run_engine(df)
    result = build_analysis(CODE, df, engine_result, category, recent_bars=0)
    if result.get('error'):
        return {'tag': tag, 'error': result['error']}
    structure = result.get('structure', {})
    return {
        'tag': tag,
        'latest_close': result.get('latest_close'),
        'change_pct': result.get('change_pct'),
        'trend': structure.get('current_trend'),
        'price_vs_zs': structure.get('price_vs_zs'),
        'bi_count': structure.get('bi_count'),
        'zhongshu_count': structure.get('zhongshu_count'),
        'buy_signals': [s for s in result.get('signals', []) if s.get('type') == 'buy'],
        'sell_signals': [s for s in result.get('signals', []) if s.get('type') == 'sell'],
        'latest_signal': result.get('latest_signal'),
    }


def main():
    results = []
    print(f"=== {CODE} {NAME} chan-signal 缠论买卖点（日线+周线，数据源 akshare）===")
    for tag, category, getter in [
        ('日线', 9, lambda: fetch_sw('day')),
        ('周线', 7, lambda: fetch_sw('week')),
    ]:
        try:
            df = getter()
            r = run_one(tag, category, df)
        except Exception as e:
            r = {'tag': tag, 'error': str(e)}
        results.append(r)
        print(f"\n[{tag}]")
        if r.get('error'):
            print(f"  {r['error']}")
            continue
        print(f"  最新价 {r['latest_close']} ({r['change_pct']}%) | 趋势 {r['trend']} | {r['price_vs_zs']}")
        print(f"  笔 {r['bi_count']} 中枢 {r['zhongshu_count']}")
        for b in r['buy_signals']:
            print(f"    买点 {b['name']} @{b.get('price')} 置信度{b.get('confidence')}")
        for s in r['sell_signals']:
            print(f"    卖点 {s['name']} @{s.get('price')} 置信度{s.get('confidence')}")
        if r['latest_signal']:
            ls = r['latest_signal']
            print(f"    最新信号: {ls.get('name')}@{ls.get('price')}")

    # 输出对比表 md
    out_dir = os.path.join(CHAN_DIR, 'output')
    os.makedirs(out_dir, exist_ok=True)
    md = render_markdown(results, NAME, CODE)
    md_path = os.path.join(out_dir, f'{CODE}_{DATE_STR}_申万买卖点对比表.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md + '\n')
    print(f"\n买卖点对比表已保存: {md_path}")

    # 输出 JSON
    json_path = os.path.join(out_dir, f'{CODE}_{DATE_STR}_sw_chansignal.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1, default=str)
    print(f"JSON 已保存: {json_path}")


def render_markdown(results, name, code):
    lines = [f'## {name}({code}) chan-signal 缠论买卖点交叉对比表（申万行业 · 日线+周线）', '']
    lines.append('| 周期 | 最新价 | 涨跌 | 趋势 | 中枢位置 | 买点信号 | 卖点信号 |')
    lines.append('|------|--------|------|------|---------|---------|---------|')
    for r in results:
        if r.get('error'):
            lines.append(f"| {r['tag']} | - | - | - | {r['error']} | - | - |")
            continue
        price = f"{r['latest_close']:.2f}"
        chg = f"{r['change_pct']:+.2f}%"
        buys = '、'.join(f"{b['name']}@{b.get('price')}" for b in r.get('buy_signals', [])) or '—'
        sells = '、'.join(f"{s['name']}@{s.get('price')}" for s in r.get('sell_signals', [])) or '—'
        lines.append(f"| {r['tag']} | {price} | {chg} | {r['trend']} | {r['price_vs_zs']} | {buys} | {sells} |")
    lines.append('')
    lines.append('> 说明：申万行业无分钟线（免费源限制），仅日线/周线级别。一买=下跌背驰反转、二买=回调不破前低、三买=突破中枢回踩；卖点对应减仓/止损。')
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
