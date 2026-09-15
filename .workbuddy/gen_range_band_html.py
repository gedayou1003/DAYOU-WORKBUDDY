# -*- coding: utf-8 -*-
"""生成：预判核心带上下轨 vs 上证综指实际走势（纯 SVG 内联，零 JS 依赖）"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
data = json.load(open(os.path.join(BASE, 'range_band_data.json'), encoding='utf-8'))
days = data['days']
summary = data['summary']

# 只保留有 bar 且 lo/hi 非空的日子
rows = []
for d in days:
    b = d.get('bar')
    if not b or d.get('lo') is None or d.get('hi') is None:
        continue
    rows.append(dict(date=d['date'], n=d['n'], lo=d['lo'], hi=d['hi'],
                     o=b['open'], h=b['high'], l=b['low'], c=b['close']))
n = len(rows)
for i, r in enumerate(rows):
    r['pct'] = (r['c'] - rows[i-1]['c']) / rows[i-1]['c'] * 100 if i > 0 else 0.0
    r['close_in'] = r['lo'] <= r['c'] <= r['hi']

# ---- 坐标 ----
W, H = 1240, 700
L, R, T, B = 78, 28, 56, 132
pw, ph = W - L - R, H - T - B

ymin = min(min(r['lo'], r['l']) for r in rows)
ymax = max(max(r['hi'], r['h']) for r in rows)
ymin = (ymin - 18) // 10 * 10
ymax = -((-ymax - 18) // 10) * 10

def X(i): return L + i * pw / (n - 1)
def Y(v): return T + (ymax - v) / (ymax - ymin) * ph

# ---- 配色 ----
C_GRID = '#eae3d4'; C_AXIS = '#9a9484'
C_BAND = 'rgba(196,112,58,0.13)'; C_RAIL = '#c4703a'
C_CLOSE = '#1e4d3a'
C_UP = '#c0392b'; C_DOWN = '#2e8b57'

# ---- SVG 组装 ----
svg = []
svg.append(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="display:block;width:100%;height:auto;background:#fbf8f0;border-radius:10px">')

# 网格 + y 轴
v = ymin
while v <= ymax:
    svg.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{W-R}" y2="{Y(v):.1f}" stroke="{C_GRID}" stroke-width="1"/>')
    svg.append(f'<text x="{L-10}" y="{Y(v):.1f}" text-anchor="end" dominant-baseline="middle" '
               f'font-size="11" fill="{C_AXIS}" font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">{int(v)}</text>')
    v += 20

# 核心带通道 polygon
top = [Y(r['hi']) for r in rows]
bot = [Y(r['lo']) for r in rows]
pts = [f"{X(i):.1f},{top[i]:.1f}" for i in range(n)] + [f"{X(i):.1f},{bot[i]:.1f}" for i in range(n-1, -1, -1)]
svg.append(f'<polygon points="{" ".join(pts)}" fill="{C_BAND}"/>')

# 上/下轨虚线
svg.append(f'<polyline points="{" ".join(f"{X(i):.1f},{top[i]:.1f}" for i in range(n))}" '
           f'fill="none" stroke="{C_RAIL}" stroke-width="2" stroke-dasharray="5,4"/>')
svg.append(f'<polyline points="{" ".join(f"{X(i):.1f},{bot[i]:.1f}" for i in range(n))}" '
           f'fill="none" stroke="{C_RAIL}" stroke-width="2" stroke-dasharray="5,4"/>')

# 阶梯锚点短横线
for i in range(n):
    for yy in (top[i], bot[i]):
        svg.append(f'<line x1="{X(i)-7:.1f}" y1="{yy:.1f}" x2="{X(i)+7:.1f}" y2="{yy:.1f}" '
                   f'stroke="{C_RAIL}" stroke-width="1.6"/>')

# 实际日内高低竖线（涨红跌绿）
for i, r in enumerate(rows):
    col = C_UP if r['pct'] >= 0 else C_DOWN
    svg.append(f'<line x1="{X(i):.1f}" y1="{Y(r["h"]):.1f}" x2="{X(i):.1f}" y2="{Y(r["l"]):.1f}" '
               f'stroke="{col}" stroke-width="1.4"/>')
    for vv in (r['h'], r['l']):
        svg.append(f'<line x1="{X(i)-5:.1f}" y1="{Y(vv):.1f}" x2="{X(i)+5:.1f}" y2="{Y(vv):.1f}" '
                   f'stroke="{col}" stroke-width="2"/>')

# 收盘折线
svg.append(f'<polyline points="{" ".join(f"{X(i):.1f},{Y(r["c"]):.1f}" for i, r in enumerate(rows))}" '
           f'fill="none" stroke="{C_CLOSE}" stroke-width="2.6"/>')

# 收盘点：带内实心 / 带外橙圈
for i, r in enumerate(rows):
    xx, yy = X(i), Y(r['c'])
    ttl = (f"{r['date']}（预判 {r['n']} 条）&#10;核心带 {r['lo']} ~ {r['hi']}&#10;"
           f"实际 O/H/L/C {r['o']}/{r['h']}/{r['l']}/{r['c']}（{r['pct']:+.2f}%）&#10;"
           f"{'收盘在带内' if r['close_in'] else '收盘出带外'}")
    if r['close_in']:
        svg.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="4.2" fill="{C_CLOSE}"><title>{ttl}</title></circle>')
    else:
        svg.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="5.5" fill="#fbf8f0" stroke="{C_RAIL}" '
                   f'stroke-width="2.4"><title>{ttl}</title></circle>')

# x 轴标签（隔一个）
for i in range(n):
    if i % 2 != 0:
        continue
    svg.append(f'<text x="{X(i):.1f}" y="{H-B+14}" text-anchor="middle" '
               f'font-size="10" fill="{C_AXIS}" font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">{rows[i]["date"][5:]}</text>')

# 逐日命中色块条
stripY = H - B + 34; stripH = 20; gap = 3
cellW = pw / n - gap
for i, r in enumerate(rows):
    x = L + i * (pw / n)
    col = '#cfc8b6'
    if r['close_in'] is True:
        col = C_DOWN
    elif r['close_in'] is False:
        col = C_UP
    svg.append(f'<rect x="{x:.1f}" y="{stripY}" width="{cellW:.1f}" height="{stripH}" rx="3" fill="{col}">'
               f'<title>{r["date"]}：{"收盘在带内" if r["close_in"] else "收盘出带外"}</title></rect>')
svg.append(f'<text x="{L}" y="{stripY+stripH+13}" font-size="11" fill="{C_AXIS}" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">收盘命中核心带（绿=带内 / 红=带外）</text>')

svg.append('</svg>')
SVG = '\n'.join(svg)

# ---- 统计卡片 ----
def card(k, v, d, cls='forest'):
    return (f'<div class="stat"><div class="k">{k}</div>'
            f'<div class="v {cls}">{v}</div><div class="d">{d}</div></div>')

n_days = summary['n_days']
cards = ''.join([
    card('收盘落在核心带内', f"{summary['in_close']}/{n_days}", f"{round(summary['in_close']/n_days*100)}%", 'forest'),
    card('高点未破上轨', f"{summary['in_high']}/{n_days}", f"{round(summary['in_high']/n_days*100)}%", 'forest'),
    card('低点守住下轨', f"{summary['in_low']}/{n_days}", f"{round(summary['in_low']/n_days*100)}%", 'clay'),
    card('高低全在带内', f"{summary['in_full']}/{n_days}", f"{round(summary['in_full']/n_days*100)}%", 'clay'),
    card('核心带平均宽度', f"{summary['avg_width']} 点", '≈0.98%', 'forest'),
])

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>上证综指 · 预判核心带上下轨 vs 实际走势</title>
<style>
:root{--paper:#f5f0e6;--panel:#fbf8f0;--card:#fffdf7;--forest:#1e4d3a;--clay:#c4703a;
  --ink:#3a3a36;--sub:#8a8577;--grid:#e5ddcc;--up:#c0392b;--down:#2e8b57}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);
  font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  padding:34px 40px 50px;line-height:1.6}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:22px;font-weight:700;letter-spacing:.5px;color:var(--forest)}
.sub{font-size:13px;color:var(--sub);margin-top:6px}
.legend{display:flex;flex-wrap:wrap;gap:22px;margin:18px 0 10px;font-size:13px;color:var(--ink)}
.legend .it{display:flex;align-items:center;gap:7px}
.sw{width:20px;height:3px;border-radius:2px;display:inline-block}
.sw.fill{width:16px;height:12px;border-radius:3px;background:rgba(196,112,58,.18);border:1px solid var(--clay)}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:20px 0}
.stat{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:14px 16px}
.stat .k{font-size:12px;color:var(--sub)}
.stat .v{font-size:26px;font-weight:700;color:var(--forest);margin-top:2px}
.stat .v.clay{color:var(--clay)}
.stat .d{font-size:11px;color:var(--sub);margin-top:4px}
.note{font-size:13px;color:var(--sub);margin-top:16px;border-left:3px solid var(--clay);
  padding-left:12px;max-width:860px}
.note b{color:var(--ink)}
</style>
</head>
<body>
<div class="wrap">
  <h1>上证综指 · 预判核心带上下轨 vs 实际走势</h1>
  <div class="sub">000001 日线 · 2026-08-21 至 2026-09-15（18 个交易日）· 预判链 47 条按目标日聚合取中位核心带</div>

  <div class="legend">
    <div class="it"><span class="sw fill"></span> 预判核心带（上轨 / 下轨通道）</div>
    <div class="it"><span class="sw" style="background:var(--clay)"></span> 核心带上轨 / 下轨</div>
    <div class="it"><span class="sw" style="background:var(--forest)"></span> 实际收盘走势</div>
    <div class="it"><span class="sw" style="background:var(--up)"></span> 当日收涨（红）</div>
    <div class="it"><span class="sw" style="background:var(--down)"></span> 当日收跌（绿）</div>
    <div class="it"><span class="dot" style="background:var(--forest);outline:2px solid var(--clay);outline-offset:1px"></span> 收盘落在核心带外</div>
  </div>

__SVG__

  <div class="stats">
__CARDS__
  </div>
  <div class="note"><b>读图要点</b> · 陶土橙通道是每交易日预判「核心震荡区间」聚合出的上/下轨，森林绿折线是实际收盘、红绿竖线是当日高低。鼠标悬停任意点位可看当日明细。<br>
  <b>收盘命中 55.6%</b> 说明核心带更像「收盘锚定带」；<b>盘中高低全包住仅 16.7%</b>、<b>低点守住下轨仅 38.9%</b>，说明日内波动常刺破带边、尤其下轨——9/11 破位下杀（预判下轨 3929 → 实际最低 3852，击穿 77 点）最典型。</div>
</div>
</body>
</html>
"""

HTML = HTML.replace('__SVG__', SVG).replace('__CARDS__', cards)

out = os.path.join(PROJ, 'outputs', '上证综指_预判区间带_2026-08-21至09-15.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('OK', len(HTML))
