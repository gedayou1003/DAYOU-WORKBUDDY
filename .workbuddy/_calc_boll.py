# -*- coding: utf-8 -*-
"""临时：算 15F/60F/日线 BOLL 三轨（9/2 收盘）"""
import json, urllib.request
import pandas as pd
UA = {'User-Agent': 'Mozilla/5.0'}


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode())


def mk(p, count=200):
    d = get(f'https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh000001,{p},,{count}')
    rows = d['data']['sh000001'][p]
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.dropna()


def day(count=200):
    d = get(f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,{count},qfq')
    rows = d['data']['sh000001'].get('qfqday') or d['data']['sh000001'].get('day') or []
    rows = [r[:6] for r in rows if len(r) >= 6]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c in ['open', 'close', 'high', 'low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.dropna()


def boll(df, tag):
    c = df['close']
    m20 = c.rolling(20).mean()
    s = c.rolling(20).std()
    up = m20 + 2 * s
    dn = m20 - 2 * s
    mid = m20
    b = (up.iloc[-1] - dn.iloc[-1]) / mid.iloc[-1] * 100
    print(f'{tag}: 上轨{up.iloc[-1]:.2f} 中轨{mid.iloc[-1]:.2f} 下轨{dn.iloc[-1]:.2f} 带宽{b:.2f}%  现价{c.iloc[-1]:.2f}')


boll(mk('m15'), '15分钟')
boll(mk('m60'), '60分钟')
boll(day(), '日线')
