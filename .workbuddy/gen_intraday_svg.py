# -*- coding: utf-8 -*-
"""生成 9/3 盘中预判 SVG（当日实况用 9/3 盘中 OHLC，不走 verified 记录）"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_forecast_svg as g

CHAIN = os.path.join(HERE, 'forecast_chain.json')
fc = json.load(open(CHAIN, encoding='utf-8'))

lv = None
for r in fc:
    if r.get('id') == '2026-09-03-intraday' and isinstance(r.get('levels'), dict):
        lv = r['levels']
if not lv:
    print('未找到 intraday levels'); sys.exit(1)

# 9/3 盘中实况（09:45 快照）
act = {'open': 3952.79, 'high': 3966.96, 'low': 3952.79, 'close': 3962.48}

out = os.path.normpath(os.path.join(HERE, '..', 'outputs', '000001_forecast_2026-09-03.svg'))
n = g.build_svg(lv, act, out)
print(f'SVG written, size={n} chars, path={out}')
print(f'now={lv["now"]}, band=({lv["down_support"]["price"]}~{lv["decision"]["price"]}), up={lv["up_target"]["price"]}, lower={lv["down_lower"]["price"]}')
