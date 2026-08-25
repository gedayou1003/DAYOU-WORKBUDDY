# -*- coding: utf-8 -*-
"""多标的扫描 v3：申万一级行业（akshare历史 + Datayes实时补缺拼到8-24）+ 宽基/恒生（腾讯实时8-25）
按「方向明确度 × 波动幅度」选高确定性+高波动标的"""
import sys, os, json, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.workbuddy/skills/chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
sys.path.insert(0, HERE)
from chan_signal import run_engine, build_analysis, calc_macd
from market_codes import SW_INDEXES

# token 存不入 git 的 .workbuddy/datayes_token.txt（安全，避免泄露到 GitHub）
TOKEN = open(os.path.join(HERE, 'datayes_token.txt'), encoding='utf-8').read().strip()
H = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/json'}
def dy_get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30).read().decode('utf-8'))

UA = {'User-Agent': 'Mozilla/5.0'}
def tencent_get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode('utf-8'))

def fetch_sw_hist(code):
    """akshare 申万一级行业历史（到 8-21，完整）"""
    import akshare as ak
    raw = ak.index_hist_sw(symbol=code, period='day')
    df = pd.DataFrame({
        'date': pd.to_datetime(raw['日期']),
        'open': raw['开盘'].astype(float), 'close': raw['收盘'].astype(float),
        'high': raw['最高'].astype(float), 'low': raw['最低'].astype(float),
        'vol': raw['成交量'].astype(float), 'amount': raw['成交额'].astype(float),
    })
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def fetch_datayes_sw(code):
    """Datayes 申万指数日行情（getMktIdxdSw），补最近 20 天（覆盖 akshare 滞后缺口），口径与 akshare 一致（点位）"""
    from datetime import date, timedelta
    end = date.today().strftime('%Y%m%d')
    begin = (date.today() - timedelta(days=20)).strftime('%Y%m%d')
    u = f'https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktIdxdSw.json?ticker={code}&beginDate={begin}&endDate={end}&pagesize=20'
    d = dy_get(u)
    rows = []
    for x in d.get('data', []):
        rows.append({
            'date': pd.to_datetime(x.get('tradeDate')),
            'open': x.get('openIndex'), 'close': x.get('closeIndex'),
            'high': x.get('highestIndex'), 'low': x.get('lowestIndex'),
            'vol': 0, 'amount': 0,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()

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
    return {'name': name, 'code': code, 'close': close, 'last_date': last_date,
            'trend': trend, 'direction': total, 'volatility': round(vol, 2), 'sig': sig_name}

def main():
    results_sw, results_idx = [], []
    print('=== 申万一级行业扫描（akshare历史 + Datayes补到8-24）===')
    for i, (code, info) in enumerate(SW_INDEXES.items()):
        try:
            hist = fetch_sw_hist(code)
            dy = fetch_datayes_sw(code)
            # 拼接：akshare 历史 + datayes 补的 8-22~8-24
            if not dy.empty:
                hist = pd.concat([hist, dy]).drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
            r = score_one(code, info['name'], hist)
            if r and 'error' not in r:
                results_sw.append(r)
                print(f"  [{i+1}/31] {info['name']}: 方向{r['direction']:+.1f} 振幅{r['volatility']}% 趋势{r['trend']} 最新{r['last_date']}")
        except Exception as e:
            print(f"  [{i+1}/31] {info['name']}: 失败 {str(e)[:30]}")

    print('\n=== 宽基指数 + 恒生（腾讯，实时8-25）===')
    for tc, name in [('sh000300','沪深300'), ('sh000016','上证50'), ('sh000852','中证1000'), ('hkHSI','恒生指数')]:
        try:
            df = fetch_tencent(tc, 'day')
            r = score_one(tc, name, df)
            if r and 'error' not in r:
                results_idx.append(r)
                print(f"  {name}: 方向{r['direction']:+.1f} 振幅{r['volatility']}% 趋势{r['trend']} 信号[{r['sig']}]")
        except Exception as e:
            print(f"  {name}: 失败 {str(e)[:40]}")

    for lst in (results_sw, results_idx):
        for r in lst:
            r['score'] = round(abs(r['direction']) * r['volatility'], 2)
    results_sw.sort(key=lambda x: x['score'], reverse=True)
    results_idx.sort(key=lambda x: x['score'], reverse=True)

    print('\n\n===== 申万一级行业 TOP 10（|方向|×振幅 降序）=====')
    for r in results_sw[:10]:
        print(f"  {r['name']:10s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")
    print('\n===== 宽基/恒生 TOP =====')
    for r in results_idx:
        print(f"  {r['name']:8s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")

    out = {'sw': results_sw, 'index': results_idx}
    with open(os.path.join(HERE, 'backtest_data', 'scan_result_sw_v3.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存 backtest_data/scan_result_sw_v3.json")

if __name__ == '__main__':
    main()
