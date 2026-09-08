# -*- coding: utf-8 -*-
"""复盘：两套缠论引擎的有效性（定量 + 定性支撑）。

指标1（引擎B·买卖点）: 提取 evidence.engineB 里所有 "N买/N卖@价格" 点位，
   判断是否落在当日 [low, high] 内（触及），以及距实际极值（高点/低点）的偏差（精准度）。
指标2（引擎A·多维融合）: 提取日线/60F 缠论结构(down/sideways/up)，对比实际方向命中。
"""
import json, re

recs = json.load(open('forecast_chain.json', encoding='utf-8'))
verified = [r for r in recs if r.get('status') == 'verified']

def get_actual(r):
    return (r.get('review') or {}).get('actual') or {}

def review_verdict(r, dim):
    rev = r.get('review') or {}
    return rev.get(dim + '_verdict') or rev.get(dim) or ''

# ---------- 指标1: 引擎B 买卖点触及/精准度 ----------
print('=' * 70)
print('【指标1】引擎B 买卖点作为支撑/压力的有效性')
print('=' * 70)
B_pts = []  # (id, 点位名, 价格, 是否触及, 距极值偏差%)
for r in verified:
    ev = r.get('evidence') or {}
    txt = ev.get('engineB') or ''
    a = get_actual(r)
    if not txt or not a.get('high'):
        continue
    hi, lo = float(a['high']), float(a['low'])
    # 提取 "N买@价格" / "N卖@价格"
    for m in re.finditer(r'(一买|二买|三买|一卖|二卖|三卖)@([\d.]+)', txt):
        name, price = m.group(1), float(m.group(2))
        touched = lo - 0.5 <= price <= hi + 0.5
        # 距极值偏差：卖点对应 high，买点对应 low
        if '卖' in name:
            dev = (price - hi) / hi * 100
        else:
            dev = (price - lo) / lo * 100
        B_pts.append((r['id'], name, price, touched, dev))

print(f'总买卖点样本: {len(B_pts)}')
if B_pts:
    touched = sum(1 for p in B_pts if p[3])
    print(f'触及率（点位落在当日[low,high]内）: {touched}/{len(B_pts)} = {touched/len(B_pts)*100:.1f}%')
    # 精准度：距极值 |dev| <= 0.5% 视为"精准"
    precise = sum(1 for p in B_pts if abs(p[4]) <= 0.5)
    print(f'精准度（距实际极值±0.5%内）: {precise}/{len(B_pts)} = {precise/len(B_pts)*100:.1f}%')
    print()
    print('明细（按偏差排序）:')
    for p in sorted(B_pts, key=lambda x: abs(x[4])):
        print(f"  {p[0]}  {p[1]:4s}@{p[2]:8.2f}  触及={p[3]}  距极值{p[4]:+6.2f}%")

# ---------- 指标2: 引擎A 方向命中 ----------
print()
print('=' * 70)
print('【指标2】引擎A 缠论结构 vs 实际方向（日线级别）')
print('=' * 70)
def parseA_dir(text, lvl):
    if not text:
        return None
    idx = text.find(lvl)
    if idx == -1:
        return None
    seg = text[idx: idx + 45]
    m = re.search(r'(down|sideways|up)', seg)
    return m.group(1) if m else None

hit = miss = side = 0
detail = []
for r in verified:
    ev = r.get('evidence') or {}
    d = parseA_dir(ev.get('engineA'), '日线')
    a = get_actual(r)
    pct = a.get('pct_chg')
    if d is None or pct is None:
        continue
    up = pct > 0.15
    dn = pct < -0.15
    if d == 'down':
        if dn: hit += 1; detail.append((r['id'], 'down', pct, 'HIT'))
        elif up: miss += 1; detail.append((r['id'], 'down', pct, 'MISS'))
        else: side += 1; detail.append((r['id'], 'down', pct, 'FLAT'))
    elif d == 'up':
        if up: hit += 1; detail.append((r['id'], 'up', pct, 'HIT'))
        elif dn: miss += 1; detail.append((r['id'], 'up', pct, 'MISS'))
        else: side += 1; detail.append((r['id'], 'up', pct, 'FLAT'))
    else:
        side += 1; detail.append((r['id'], 'sideways', pct, 'SIDE'))

n = hit + miss
print(f'日线明确方向(down/up)样本: 命中 {hit}, 反向 {miss}, 震荡/平 {side}')
print(f'方向命中率（排除震荡）: {hit}/{n} = {hit/n*100:.1f}%' if n else '无样本')
print('明细:')
for d in detail:
    print(f"  {d[0]}  {d[1]:8s}  实际{d[2]:+6.2f}%  {d[3]}")

# 引擎A"观望"占比统计
print()
obs = sum(1 for r in verified if parseA_dir((r.get('evidence') or {}).get('engineA'), '日线') is None)
print(f'engineA 无法提取日线方向的记录: {obs}（多为"观望"表述或无 engineA 字段）')
