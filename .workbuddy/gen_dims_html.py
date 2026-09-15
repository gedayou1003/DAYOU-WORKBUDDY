# -*- coding: utf-8 -*-
"""生成：四维命中率（方向/区间/支撑/压力）可视化 —— 纯 SVG 内联，零 JS"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
data = json.load(open(os.path.join(BASE, 'dims_hitrate_data.json'), encoding='utf-8'))
rows = data['rows']
final = data['final']

DIMS = [('direction', '方向'), ('range', '区间'), ('support', '支撑'), ('resistance', '压力')]
COLOR = {'direction': '#1e4d3a', 'range': '#c4703a', 'support': '#4a7d8c', 'resistance': '#a64b3c'}
C_OK, C_PART, C_FAIL = '#2e8b57', '#d9a441', '#c0392b'

n = len(rows)

# ---- 主图坐标 ----
W, H = 1240, 620
L, R, T, B = 66, 40, 40, 72
pw, ph = W - L - R, H - T - B
Y0, Y1 = 0.0, 100.0

def X(i): return L + i * pw / (n - 1)
def Y(v): return T + (Y1 - v) / (Y1 - Y0) * ph

svg = []
svg.append(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="display:block;width:100%;height:auto;background:#fbf8f0;border-radius:10px">')

# 网格 + y 轴（每 10%）
v = 0
while v <= 100:
    col = '#eae3d4'
    dash = ''
    if v == 50:
        col = '#c9bfa8'; dash = ' stroke-dasharray="4,4"'
    svg.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{W-R}" y2="{Y(v):.1f}" '
               f'stroke="{col}" stroke-width="1"{dash}/>')
    svg.append(f'<text x="{L-10}" y="{Y(v):.1f}" text-anchor="end" dominant-baseline="middle" '
               f'font-size="10.5" fill="#9a9484" font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">{v}%</text>')
    v += 10

# 50% 基准标注
svg.append(f'<text x="{L+8}" y="{Y(50)-6:.1f}" font-size="10" fill="#b0a78e" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">50% 基准</text>')

# 四维滚动命中率曲线（纯命中率）
for key, zh in DIMS:
    pts = []
    for i, r in enumerate(rows):
        val = r.get(key + '_pure')
        if val is None:
            continue
        pts.append(f"{X(i):.1f},{Y(val):.1f}")
    svg.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COLOR[key]}" '
               f'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    # 末端实心点
    last = rows[-1]
    if last.get(key + '_pure') is not None:
        svg.append(f'<circle cx="{X(n-1):.1f}" cy="{Y(last[key + "_pure"]):.1f}" r="4.4" fill="{COLOR[key]}" '
                   f'stroke="#fbf8f0" stroke-width="1.5"/>')

# x 轴：期序号（每 5 期标一个）
for i, r in enumerate(rows):
    if r['idx'] % 5 != 1:
        continue
    svg.append(f'<text x="{X(i):.1f}" y="{H-B+16}" text-anchor="middle" font-size="10" fill="#8a8577" '
               f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">{r["idx"]}期</text>')
svg.append(f'<text x="{L}" y="{H-B+34}" font-size="10.5" fill="#a09a8a" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">第 1 期（{rows[0]["date"]}）→ 第 {n} 期（{rows[-1]["date"]}）· 每期滚动累计</text>')

svg.append('</svg>')
SVG = '\n'.join(svg)

# ---- 图例（HTML）----
legend = ''.join(
    f'<div class="it"><span class="sw" style="background:{COLOR[k]}"></span>{zh} '
    f'<b style="color:{COLOR[k]}">{final[k]["ok"]/final[k]["tot"]*100:.1f}%</b></div>'
    for k, zh in DIMS)

# ---- 统计卡片 ----
def card(zh, k, col):
    f = final[k]
    tot = f['tot']; ok = f['ok']; part = f['part']; fail = tot - ok - part
    pure = ok / tot * 100
    return (f'<div class="stat"><div class="k">{zh} · 纯命中率</div>'
            f'<div class="v" style="color:{col}">{pure:.1f}%</div>'
            f'<div class="d"><span style="color:{C_OK}">✅{ok}</span> '
            f'<span style="color:{C_PART}">⚠️{part}</span> '
            f'<span style="color:{C_FAIL}">❌{fail}</span> · 共 {tot} 期</div></div>')

cards = ''.join(card(zh, k, COLOR[k]) for k, zh in DIMS)

# ---- 构成堆叠条 ----
def stack(zh, k):
    f = final[k]
    tot = f['tot']; ok = f['ok']; part = f['part']; fail = tot - ok - part
    w1 = ok / tot * 100; w2 = part / tot * 100; w3 = fail / tot * 100
    return (f'<div class="st-row"><div class="st-name">{zh}</div>'
            f'<div class="st-bar">'
            f'<div class="st-seg" style="width:{w1:.2f}%;background:{C_OK}" title="命中 {ok}"></div>'
            f'<div class="st-seg" style="width:{w2:.2f}%;background:{C_PART}" title="部分 {part}"></div>'
            f'<div class="st-seg" style="width:{w3:.2f}%;background:{C_FAIL}" title="失败 {fail}"></div>'
            f'</div><div class="st-val">{ok}/{tot}</div></div>')

stacks = ''.join(stack(zh, k) for k, zh in DIMS)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>四维命中率 · 预判系统复盘</title>
<style>
:root{--paper:#f5f0e6;--panel:#fbf8f0;--card:#fffdf7;--forest:#1e4d3a;--clay:#c4703a;
  --ink:#3a3a36;--sub:#8a8577;--grid:#e5ddcc}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);
  font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  padding:34px 40px 50px;line-height:1.6}
.wrap{max-width:1280px;margin:0 auto}
h1{font-size:22px;font-weight:700;letter-spacing:.5px;color:var(--forest)}
.sub{font-size:13px;color:var(--sub);margin-top:6px}
.legend{display:flex;flex-wrap:wrap;gap:26px;margin:18px 0 10px;font-size:13.5px;color:var(--ink)}
.legend .it{display:flex;align-items:center;gap:8px}
.sw{width:22px;height:3px;border-radius:2px;display:inline-block}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}
.stat{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:14px 16px}
.stat .k{font-size:12px;color:var(--sub)}
.stat .v{font-size:28px;font-weight:700;margin-top:2px}
.stat .d{font-size:11.5px;color:var(--sub);margin-top:5px}
.sec{font-size:14px;font-weight:700;color:var(--forest);margin:24px 0 10px;letter-spacing:.5px}
.st-row{display:flex;align-items:center;gap:12px;margin:8px 0}
.st-name{width:44px;font-size:13px;color:var(--ink);font-weight:600;text-align:right}
.st-bar{flex:1;height:22px;border-radius:5px;overflow:hidden;display:flex;background:#efe8d8}
.st-seg{height:100%}
.st-val{width:52px;font-size:13px;color:var(--forest);font-weight:700}
.note{font-size:13px;color:var(--sub);margin-top:22px;border-left:3px solid var(--clay);
  padding-left:12px;max-width:900px}
.note b{color:var(--ink)}
</style>
</head>
<body>
<div class="wrap">
  <h1>预判系统 · 四维命中率复盘</h1>
  <div class="sub">方向 / 区间 / 支撑 / 压力 · 46 期滚动累计 · 口径：纯命中率 = ✅ ÷（✅+⚠️+❌）</div>

  <div class="legend">
__LEGEND__
  </div>

__SVG__

  <div class="stats">
__CARDS__
  </div>

  <div class="sec">四维判定构成（命中 / 部分 / 失败）</div>
__STACKS__

  <div class="note"><b>读图要点</b> · 四条曲线是「纯命中率」随复盘期数的滚动累计，前 10 期样本少、波动大属正常，20 期后趋于稳定。<br>
  <b>结构稳定：支撑（66.7%）＞ 压力（60.0%）＞ 方向（56.5%）＞ 区间（39.1%）</b>。区间长期垫底，但看构成条可发现其「⚠️ 部分」占比最高（25/46）——区间判定常是「方向对、幅度差一点」，纯口径下被记为未命中，若按「含部分 0.5」口径可达 66.3%。支撑/压力是预判系统最可靠的维度，也是实际操盘中「关键位」最值得信赖的部分。</div>
</div>
</body>
</html>
"""

HTML = (HTML.replace('__LEGEND__', legend).replace('__SVG__', SVG)
        .replace('__CARDS__', cards).replace('__STACKS__', stacks))

out = os.path.join(PROJ, 'outputs', '四维命中率_预判系统_复盘.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('OK', len(HTML))
