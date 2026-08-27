# -*- coding: utf-8 -*-
"""生成「条件触发决策路径图」SVG：主路径(现价→决策位)+决策点(菱形)+分支(放量突破红/缩量假突破绿)，
每条分支标注触发条件+目标位+盘面应对。红涨绿跌。y 轴铁律：y = 底部 - (价格-最低)/价差*图高。"""

# 价格-坐标（viewBox 0 0 900 540）
PRICE_MIN = 3800.0
PRICE_MAX = 3968.48
PRICE_RANGE = PRICE_MAX - PRICE_MIN
Y_BOTTOM = 480.0
Y_TOP = 40.0
Y_RANGE = Y_BOTTOM - Y_TOP

def y(p):
    return Y_BOTTOM - (p - PRICE_MIN) / PRICE_RANGE * Y_RANGE

# x 轴：8/26 已走(20~240)，8/27 决策路径(240~600)，右侧标注(620~880)
X_LEFT = 20.0
X_DEC = 240.0      # 决策起点（现价）
X_NODE = 400.0     # 决策点
X_RIGHT = 600.0    # 分支末端

# 关键价位
P_OPEN = 3881.74
P_HIGH = 3926.44
P_LOW = 3881.74
P_CLOSE = 3912.52
P_NOW = 3912.52
P_RESIST_60F55 = 3925.67   # 决策位
P_RESIST_TRIPLE = 3927.85
P_RESIST_W1S = 3968.48
P_RESIST_60FS = 3911.08
P_SUPP_15F3B = 3909.79
P_SUPP_PRIMARY = 3881.74
P_SUPP_LOWEST = 3850.86
P_SUPP_BB = 3844.22

def path(points):
    return 'M ' + ' L '.join(f'{x:.1f},{yy:.1f}' for x, yy in points)

svg = []
svg.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 580" font-family="-apple-system,\'PingFang SC\',sans-serif">')
svg.append('<defs><style>')
svg.append('.grid{stroke:#d8d2c4;stroke-width:0.5;stroke-dasharray:2 3}')
svg.append('.axis{stroke:#3a4a4a;stroke-width:1;fill:none}')
svg.append('.label{fill:#3a4a4a;font-size:10px}')
svg.append('.actual{stroke:#1f3a3a;stroke-width:2.2;fill:none}')
svg.append('.main-path{stroke:#2b2b2b;stroke-width:2;fill:none;stroke-dasharray:1 0}')
svg.append('.branch-a{stroke:#b33a1f;stroke-width:2.2;fill:none}')
svg.append('.branch-b{stroke:#1a7a3a;stroke-width:2.2;fill:none}')
svg.append('.node{fill:#f6f2e9;stroke:#b33a1f;stroke-width:2}')
svg.append('.tt{font-size:11px;font-weight:700}')
svg.append('.tb{font-size:10px}')
svg.append('.ts{font-size:9px}')
svg.append('</style></defs>')

# 标题
svg.append('<text x="450" y="18" text-anchor="middle" class="tt" fill="#1f3a3a" font-size="15">上证综指 8/27 预判 · 条件触发决策路径图（v5）</text>')

# y 轴刻度（左）+ 网格
for p in [3844, 3860, 3880, 3900, 3920, 3940, 3960, 3968]:
    svg.append(f'<line class="grid" x1="20" y1="{y(p):.1f}" x2="600" y2="{y(p):.1f}"/>')
    svg.append(f'<text class="label" x="14" y="{y(p)+3:.1f}" text-anchor="end">{p}</text>')

# y 轴
svg.append(f'<line class="axis" x1="20" y1="40" x2="20" y2="480"/>')

# x 轴分隔线（8/26 已走 vs 8/27 决策）
svg.append(f'<line class="grid" x1="240" y1="40" x2="240" y2="480" stroke="#a89e87" stroke-dasharray="3 4"/>')
svg.append('<text x="130" y="500" text-anchor="middle" class="label">8/26 已走</text>')
svg.append('<text x="420" y="500" text-anchor="middle" class="label">8/27 决策路径</text>')

# 8/26 已走路径（实线）
p826 = [(20, y(P_OPEN)), (86, y(P_HIGH)), (130, y(3905)), (175, y(3895)), (240, y(P_CLOSE))]
svg.append(f'<path class="actual" d="{path(p826)}"/>')
svg.append(f'<circle cx="20" cy="{y(P_OPEN):.1f}" r="3" fill="#1f3a3a"/>')
svg.append(f'<text class="ts" x="18" y="{y(P_OPEN)+14:.1f}" text-anchor="end" fill="#1a5a3a">O 3881.74</text>')
svg.append(f'<circle cx="86" cy="{y(P_HIGH):.1f}" r="3" fill="#b33a1f"/>')
svg.append(f'<text class="ts" x="90" y="{y(P_HIGH)-4:.1f}" fill="#b33a1f">H 3926.44</text>')

# 现价点（决策起点）
svg.append(f'<circle cx="240" cy="{y(P_NOW):.1f}" r="4.5" fill="#2b2b2b"/>')
svg.append(f'<text class="tb" x="234" y="{y(P_NOW)-8:.1f}" text-anchor="end" fill="#2b2b2b">现价 3912.52</text>')

# 主路径：现价 → 决策点
svg.append(f'<path class="main-path" d="{path([(240, y(P_NOW)), (400, y(P_RESIST_60F55))])}"/>')
svg.append('<text class="ts" x="385" y="'+f'{y(3920)-4:.1f}" text-anchor="end" fill="#5a5a4f">主路径：上攻 60F55</text>')

# 决策点（菱形）
nx, ny = X_NODE, y(P_RESIST_60F55)
svg.append(f'<polygon class="node" points="{nx},{ny-11} {nx+11},{ny} {nx},{ny+11} {nx-11},{ny}"/>')
svg.append(f'<text class="tb" x="{nx+16}" y="{ny-4:.1f}" fill="#b33a1f">决策位 60F55 3925.67</text>')
svg.append(f'<text class="ts" x="{nx+16}" y="{ny+8:.1f}" fill="#5a5a4f">8/26 突破 0.77 点未站稳</text>')

# 分支 A（放量突破，红）
pa = [(nx, ny), (465, y(3945)), (530, y(3968.48)), (600, y(3968.48))]
svg.append(f'<path class="branch-a" d="{path(pa)}"/>')
svg.append('<polygon points="600,36 608,44 600,52 592,44" fill="#b33a1f"/>')
svg.append(f'<text class="tb" x="470" y="{y(3952)-6:.1f}" fill="#b33a1f">A 放量突破</text>')
svg.append(f'<text class="ts" x="470" y="{y(3952)+6:.1f}" fill="#b33a1f">触发：放量站稳 3925</text>')
svg.append(f'<text class="ts" x="470" y="{y(3952)+17:.1f}" fill="#b33a1f">应对：追多·持股</text>')
svg.append(f'<text class="ts" x="598" y="{y(3968.48)-14:.1f}" text-anchor="end" fill="#b33a1f">目标 3968 周线一卖</text>')

# 分支 B（缩量假突破·诱多，绿）
pb = [(nx, ny), (455, y(3911.08)), (510, y(3909.79)), (545, y(3881.74)), (600, y(3844.22))]
svg.append(f'<path class="branch-b" d="{path(pb)}"/>')
svg.append('<polygon points="600,360.5 608,368.5 600,376.5 592,368.5" fill="#1a7a3a"/>')
svg.append(f'<text class="tb" x="448" y="{y(3905)-4:.1f}" fill="#1a7a3a">B 缩量假突破·诱多</text>')
svg.append(f'<text class="ts" x="448" y="{y(3905)+8:.1f}" fill="#1a7a3a">触发：缩量遇阻回落</text>')
svg.append(f'<text class="ts" x="448" y="{y(3905)+19:.1f}" fill="#1a7a3a">应对：逢高减仓·不追涨</text>')
svg.append(f'<text class="ts" x="448" y="{y(3905)+30:.1f}" fill="#1a7a3a">跌破 3911 看 3881</text>')
svg.append(f'<text class="ts" x="598" y="{y(3844.22)+22:.1f}" text-anchor="end" fill="#1a7a3a">目标 3844 60F下轨</text>')

# 关键位水平线 + 右侧标签
levels = [
    (3968.48, 'RESIST 3968.48 周线一卖', '#b33a1f'),
    (3927.85, 'RESIST 3927.85 三共振', '#b33a1f'),
    (3925.67, 'RESIST 3925.67 60F MA55（决策位）', '#b33a1f'),
    (3909.79, 'SUPP 3909.79 15F三买', '#1a7a3a'),
    (3881.74, 'SUPP 3881.74 前低10日', '#1a7a3a'),
    (3850.86, 'SUPP 3850.86 8/25低', '#2e8a4e'),
    (3844.22, 'SUPP 3844.22 60F BOLL下轨', '#2e8a4e'),
]
for p, lbl, color in levels:
    svg.append(f'<line x1="20" y1="{y(p):.1f}" x2="600" y2="{y(p):.1f}" stroke="{color}" stroke-width="0.7" stroke-dasharray="2 3" opacity="0.75"/>')
    svg.append(f'<text class="ts" x="610" y="{y(p)+3:.1f}" fill="{color}">{lbl}</text>')

# 盘面应对框（右下）
svg.append('<g>')
svg.append('<rect x="615" y="385" width="270" height="150" rx="6" fill="#fffdf6" stroke="#a89e87" stroke-width="0.8"/>')
svg.append('<text x="627" y="403" class="tb" fill="#1f3a3a">盘面应对（逆势反抽纪律）</text>')
svg.append('<text x="627" y="423" class="ts" fill="#b33a1f">A 放量站稳 3925 → 60F 趋势修复</text>')
svg.append('<text x="627" y="437" class="ts" fill="#b33a1f">   追多/持股，目标 3968 周线一卖</text>')
svg.append('<text x="627" y="455" class="ts" fill="#1a7a3a">B 缩量遇阻 3925 → 假突破回落</text>')
svg.append('<text x="627" y="469" class="ts" fill="#1a7a3a">   逢高减仓不追涨，跌破 3911</text>')
svg.append('<text x="627" y="483" class="ts" fill="#1a7a3a">   看 3881 前低 / 3844 下轨</text>')
svg.append('<text x="627" y="501" class="ts" fill="#5a5a4f">空头区反抽 60F55 = 减仓非追涨；</text>')
svg.append('<text x="627" y="515" class="ts" fill="#5a5a4f">只有放量站稳 3927 + 周线 trend</text>')
svg.append('<text x="627" y="529" class="ts" fill="#5a5a4f">持续 3 天向上才考虑翻多。</text>')
svg.append('</g>')

# 图例（底部）
svg.append('<g>')
svg.append('<rect x="20" y="545" width="580" height="26" rx="4" fill="#fffdf6" stroke="#a89e87" stroke-width="0.6"/>')
svg.append('<line x1="30" y1="558" x2="52" y2="558" stroke="#1f3a3a" stroke-width="2"/>')
svg.append('<text x="56" y="562" class="ts" fill="#1f3a3a">8/26 已走</text>')
svg.append('<polygon points="105,551 115,558 105,565 95,558" fill="#f6f2e9" stroke="#b33a1f" stroke-width="1.5"/>')
svg.append('<text x="120" y="562" class="ts" fill="#1f3a3a">决策点</text>')
svg.append('<line x1="175" y1="558" x2="197" y2="558" stroke="#b33a1f" stroke-width="2"/>')
svg.append('<text x="201" y="562" class="ts" fill="#b33a1f">A 放量突破（追多）</text>')
svg.append('<line x1="330" y1="558" x2="352" y2="558" stroke="#1a7a3a" stroke-width="2"/>')
svg.append('<text x="356" y="562" class="ts" fill="#1a7a3a">B 缩量假突破（减仓）</text>')
svg.append('<line x1="490" y1="558" x2="512" y2="558" stroke="#7a7a7a" stroke-width="1" stroke-dasharray="2 3"/>')
svg.append('<text x="516" y="562" class="ts" fill="#5a5a4f">关键位</text>')
svg.append('</g>')

svg.append('</svg>')

content = '\n'.join(svg)
with open(r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12\outputs\000001_forecast_2026-08-27.svg', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'SVG written, size={len(content)} chars')
print(f'3925.67@y={y(P_RESIST_60F55):.1f}, 3912.52@y={y(P_NOW):.1f}, 3881.74@y={y(P_SUPP_PRIMARY):.1f}, 3844.22@y={y(P_SUPP_BB):.1f}')
