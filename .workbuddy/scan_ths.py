# -*- coding: utf-8 -*-
"""多标的扫描 v2：同花顺行业(实时OHLC,8-24) + 宽基指数/恒生(腾讯,8-25)
按「方向明确度 × 波动幅度」选出高确定性+高波动标的"""
import sys, os, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.workbuddy/skills/chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
sys.path.insert(0, HERE)
from chan_signal import run_engine, build_analysis, calc_macd

UA = {'User-Agent': 'Mozilla/5.0'}
def tencent_get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode('utf-8'))

def fetch_tencent(code, period='day', count=250):
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

def fetch_ths(name):
    """同花顺行业指数 OHLC（akshare，完整开高低收，T+1 最新）"""
    import akshare as ak
    from datetime import date, timedelta
    end_date = date.today().strftime('%Y%m%d')
    start_date = (date.today() - timedelta(days=400)).strftime('%Y%m%d')
    raw = ak.stock_board_industry_index_ths(symbol=name, start_date=start_date, end_date=end_date)
    df = pd.DataFrame({
        'date': pd.to_datetime(raw['日期']),
        'open': raw['开盘价'].astype(float), 'close': raw['收盘价'].astype(float),
        'high': raw['最高价'].astype(float), 'low': raw['最低价'].astype(float),
        'vol': raw['成交量'].astype(float), 'amount': raw['成交额'].astype(float),
    })
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def score_one(code, name, df):
    if df is None or len(df) < 40:
        return None
    try:
        engine = run_engine(df)
        a = build_analysis(code, df, engine, 9, recent_bars=0)
    except Exception as e:
        return {'error': str(e)}
    trend = a['structure'].get('current_trend')
    trend_score = 2 if trend == '向上' else (-2 if trend == '向下' else 0)
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
    macd = calc_macd(df)
    dif = float(macd['macd'].iloc[-1]); dea = float(macd['macd_signal'].iloc[-1])
    macd_score = 1 if dif > dea else -1
    total = trend_score + sig_score + macd_score
    close = float(df['close'].iloc[-1])
    h20 = float(df['high'].tail(20).max()); l20 = float(df['low'].tail(20).min())
    vol = (h20 - l20) / close * 100
    last_date = str(df['date'].iloc[-1])[:10]
    return {
        'name': name, 'code': code, 'close': close, 'last_date': last_date,
        'trend': trend, 'direction': total, 'volatility': round(vol, 2), 'sig': sig_name,
    }

def main():
    import akshare as ak
    results_ths = []
    results_idx = []

    # 同花顺行业列表
    try:
        ind = ak.stock_board_industry_summary_ths()
        ths_names = ind['板块'].tolist()
    except Exception as e:
        print(f'同花顺行业列表失败: {e}')
        ths_names = []

    print(f'=== 同花顺行业扫描（{len(ths_names)} 个，akshare ths，最新 8-24）===')
    for i, name in enumerate(ths_names):
        try:
            df = fetch_ths(name)
            r = score_one('ths_'+name, name, df)
            if r and 'error' not in r:
                results_ths.append(r)
                print(f"  [{i+1}/{len(ths_names)}] {name}: 方向{r['direction']:+.1f} 振幅{r['volatility']}% 趋势{r['trend']}")
        except Exception as e:
            print(f"  [{i+1}/{len(ths_names)}] {name}: 失败 {str(e)[:30]}")

    print('\n=== 宽基指数 + 恒生（腾讯，实时 8-25）===')
    idx_list = [
        ('sh000300', '沪深300'), ('sh000016', '上证50'),
        ('sh000852', '中证1000'), ('hkHSI', '恒生指数'),
    ]
    for tc, name in idx_list:
        try:
            df = fetch_tencent(tc, 'day')
            r = score_one(tc, name, df)
            if r and 'error' not in r:
                results_idx.append(r)
                print(f"  {name}: 方向{r['direction']:+.1f} 振幅{r['volatility']}% 趋势{r['trend']} 信号[{r['sig']}]")
        except Exception as e:
            print(f"  {name}: 失败 {str(e)[:40]}")

    for lst in (results_ths, results_idx):
        for r in lst:
            r['score'] = round(abs(r['direction']) * r['volatility'], 2)
    results_ths.sort(key=lambda x: x['score'], reverse=True)
    results_idx.sort(key=lambda x: x['score'], reverse=True)

    print('\n\n===== 同花顺行业 TOP 15（|方向|×振幅 降序）=====')
    for r in results_ths[:15]:
        print(f"  {r['name']:10s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")
    print('\n===== 宽基/恒生 TOP =====')
    for r in results_idx:
        print(f"  {r['name']:8s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")

    out = {'ths': results_ths, 'index': results_idx}
    os.makedirs(os.path.join(HERE, 'backtest_data'), exist_ok=True)
    with open(os.path.join(HERE, 'backtest_data', 'scan_result_ths.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存 backtest_data/scan_result_ths.json")

if __name__ == '__main__':
    main()
