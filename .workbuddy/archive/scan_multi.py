# -*- coding: utf-8 -*-
"""多标的扫描：按「方向明确度 × 波动幅度」选出高确定性+高波动标的
申万一级行业(akshare) + 宽基指数/恒生(腾讯)，跑 chan-signal 日线引擎统一打分"""
import sys, os, json
import pandas as pd
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.workbuddy/skills/chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
sys.path.insert(0, HERE)
from chan_signal import run_engine, build_analysis, calc_macd
from market_codes import SW_INDEXES

UA = {'User-Agent': 'Mozilla/5.0'}
def tencent_get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode('utf-8'))

def fetch_tencent(code, period='day', count=250):
    """腾讯 fqkline 拉日线/周线"""
    u = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{period},,,{count},qfq'
    d = tencent_get(u)
    data = d.get('data', {}).get(code, {})
    rows = data.get('qfqday') or data.get('qfqweek') or data.get('day') or data.get('week') or []
    if not rows:
        return None
    df = pd.DataFrame([r[:6] for r in rows], columns=['date','open','close','high','low','vol'])
    for c in ['open','close','high','low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['amount'] = df['vol']
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def fetch_sw(code, period='day'):
    """akshare 申万行业 OHLC"""
    import akshare as ak
    raw = ak.index_hist_sw(symbol=code, period=period)
    df = pd.DataFrame({
        'date': pd.to_datetime(raw['日期']),
        'open': raw['开盘'].astype(float), 'close': raw['收盘'].astype(float),
        'high': raw['最高'].astype(float), 'low': raw['最低'].astype(float),
        'vol': raw['成交量'].astype(float), 'amount': raw['成交额'].astype(float),
    })
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def score_one(code, name, df):
    """日线单周期 v5 简化打分 + 20日振幅率。返回 (direction, volatility, detail)"""
    if df is None or len(df) < 40:
        return None
    try:
        engine = run_engine(df)
        a = build_analysis(code, df, engine, 9, recent_bars=0)
    except Exception as e:
        return {'error': str(e)}
    # 趋势因子
    trend = a['structure'].get('current_trend')
    trend_score = 2 if trend == '向上' else (-2 if trend == '向下' else 0)
    # 买卖点因子（30天窗口，confidence 降权）
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
    sigs = [s for s in a.get('signals', []) if (s.get('date','') or '') >= cutoff]
    sig_score = 0
    sig_name = '—'
    if sigs:
        s0 = sigs[0]
        w = 2
        if s0.get('confidence', 0.5) < 0.6:
            w *= 0.5
        sig_score = w if s0['type'] == 'buy' else -w
        sig_name = f"{s0.get('name')}@{s0.get('price')}(conf{s0.get('confidence')})"
    # MACD 因子
    macd = calc_macd(df)
    dif = float(macd['macd'].iloc[-1]); dea = float(macd['macd_signal'].iloc[-1])
    macd_score = 1 if dif > dea else -1
    total = trend_score + sig_score + macd_score
    # 波动幅度：20日振幅率（近20日 high-max - low-min）/ 收盘
    close = float(df['close'].iloc[-1])
    h20 = float(df['high'].tail(20).max()); l20 = float(df['low'].tail(20).min())
    vol = (h20 - l20) / close * 100
    return {
        'name': name, 'code': code, 'close': close,
        'trend': trend, 'trend_score': trend_score, 'sig_score': sig_score, 'macd_score': macd_score,
        'direction': total, 'volatility': round(vol, 2), 'sig': sig_name,
    }

def main():
    results_sw = []
    results_idx = []
    print('=== 申万一级行业扫描（akshare，日线）===')
    for code, info in SW_INDEXES.items():
        try:
            df = fetch_sw(code, 'day')
            r = score_one(code, info['name'], df)
            if r and 'error' not in r:
                results_sw.append(r)
                print(f"  {info['name']}: 方向分={r['direction']:+.1f} 振幅={r['volatility']}% 趋势={r['trend']}")
        except Exception as e:
            print(f"  {info['name']}: 失败 {str(e)[:40]}")

    print('\n=== 宽基指数 + 恒生（腾讯，日线）===')
    idx_list = [
        ('sh000300', '沪深300'), ('sh000016', '上证50'),
        ('sh000852', '中证1000'), ('hkHSI', '恒生指数'),
    ]
    for tc, name in idx_list:
        try:
            df = fetch_tencent(tc, 'day')
            code = tc.replace('sh','').replace('sz','').replace('hk','')
            r = score_one(tc, name, df)
            if r and 'error' not in r:
                results_idx.append(r)
                print(f"  {name}: 方向分={r['direction']:+.1f} 振幅={r['volatility']}% 趋势={r['trend']}")
        except Exception as e:
            print(f"  {name}: 失败 {str(e)[:40]}")

    # 综合评分 = |方向分| × 振幅
    for lst in (results_sw, results_idx):
        for r in lst:
            r['score'] = round(abs(r['direction']) * r['volatility'], 2)
    results_sw.sort(key=lambda x: x['score'], reverse=True)
    results_idx.sort(key=lambda x: x['score'], reverse=True)

    print('\n\n===== 申万行业 TOP 排名（|方向|×振幅 降序）=====')
    for r in results_sw:
        print(f"  {r['name']:12s} 方向分{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")
    print('\n===== 宽基/恒生 TOP 排名 =====')
    for r in results_idx:
        print(f"  {r['name']:8s} 方向分{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")

    # 保存结果
    out = {'sw': results_sw, 'index': results_idx}
    with open(os.path.join(HERE, 'backtest_data', 'scan_result.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存 backtest_data/scan_result.json")

if __name__ == '__main__':
    main()
