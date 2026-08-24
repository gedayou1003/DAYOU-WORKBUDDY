#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取 000001 上证综指 历史 K 线（日线/周线/60F/15F），保存到 .workbuddy/backtest_data/"""
import json, os, urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "backtest_data")
os.makedirs(OUT, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0'}
TC = 'sh000001'

def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read().decode('utf-8'))

def fetch_fqkline(period, start, end, count):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={TC},{period},{start},{end},{count},qfq'
    d = get(url)
    data = d.get('data', {}).get(TC, {})
    rows = data.get('qfq' + period) or data.get(period) or []
    rows.sort(key=lambda r: r[0])
    return rows

def fetch_mkline(mperiod, count):
    url = f'https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={TC},{mperiod},,{count}'
    d = get(url)
    data = d.get('data', {}).get(TC, {})
    rows = data.get(mperiod) or []
    rows.sort(key=lambda r: r[0])
    return rows

def save(name, rows):
    # 统一转成 [date, open, close, high, low, vol]
    clean = [r[:6] for r in rows if len(r) >= 6]
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False)
    print(f'{name}: {len(clean)} 根  {clean[0][0]} ~ {clean[-1][0]}  -> {p}')

if __name__ == '__main__':
    today = datetime.now().strftime('%Y-%m-%d')
    save('day.json', fetch_fqkline('day', '2025-01-01', today, 500))
    save('week.json', fetch_fqkline('week', '2024-01-01', today, 300))
    save('m60.json', fetch_mkline('m60', 800))
    save('m15.json', fetch_mkline('m15', 320))
    print('DONE')
