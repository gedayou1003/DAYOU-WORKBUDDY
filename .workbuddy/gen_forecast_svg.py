"""生成 8/27 预判 SVG 走势图（y 轴铁律：y = 底部 - (价格-最低价)/价差*图高）"""
import json

# 价格-坐标换算（viewBox 0 0 680 470，y 范围 20-470）
PRICE_MIN = 3844.0   # 60F BOLL 下轨/MA55 备援
PRICE_MAX = 3968.48  # 周线一卖（远端压力）
PRICE_RANGE = PRICE_MAX - PRICE_MIN  # 124.48
Y_BOTTOM = 470
Y_TOP = 20
Y_RANGE = Y_BOTTOM - Y_TOP  # 450

def y(p):
    return Y_BOTTOM - (p - PRICE_MIN) / PRICE_RANGE * Y_RANGE

# x 轴：左 8/26 已走（0-340），右 8/27 剧本（340-660）
def x_left(t):  # t 0~1
    return 20 + t * 320
def x_right(t):
    return 340 + t * 320

# 关键价位
P_OPEN_826 = 3881.74  # 8/26 开（=低）
P_HIGH_826 = 3926.44  # 8/26 高
P_LOW_826 = 3881.74   # 8/26 低（同开）
P_CLOSE_826 = 3912.52  # 8/26 收
P_NOW = 3912.52
P_SUPP_PRIMARY = 3881.74   # 前低 10 日
P_SUPP_15F3B = 3909.79    # 15F 三买
P_RESIST_60F55 = 3925.67   # 60F MA55
P_RESIST_TRIPLE = 3927.85  # 周线原一买 + 60F 中枢下沿
P_RESIST_W1S = 3968.48     # 周线一卖
P_RESIST_60FS = 3911.08    # 60F 一卖三卖（已被突破）
P_SUPP_BB = 3844.22        # 60F BOLL 下轨
P_SUPP_LOWEST = 3850.86    # 8/25 实际最低
P_SUPP_120F = 3800.0       # 120F 中枢下沿（备援）

# 8/26 已走路径：开 3881.74 → 高 3926.44 → 收 3912.52（开=低）
path_826 = [
    (x_left(0.00), y(P_OPEN_826)),    # 9:30 开盘
    (x_left(0.30), y(P_HIGH_826)),    # 9:50 上午冲高
    (x_left(0.55), y(3905)),          # 10:30 回落
    (x_left(0.75), y(3895)),          # 11:30 区间
    (x_left(1.00), y(P_CLOSE_826)),   # 15:00 收盘
]

# 剧本 A：反抽修复 50%（挑战 60F55 → 3927 → 周线一卖 3968）
path_a = [
    (x_right(0.00), y(P_NOW)),         # 9:30 开 3912
    (x_right(0.25), y(3920)),         # 10:30 突破 3920
    (x_right(0.45), y(P_RESIST_60F55)), # 11:30 突破 60F55
    (x_right(0.70), y(P_RESIST_TRIPLE)), # 13:30 挑战 3927
    (x_right(1.00), y(P_RESIST_TRIPLE)), # 15:00 3927 附近
]

# 剧本 B：偏空延续 50%（跌破 3911 → 3881 → 3850/120F 中枢）
path_b = [
    (x_right(0.00), y(P_NOW)),         # 9:30 开 3912
    (x_right(0.30), y(P_RESIST_60FS)), # 10:30 跌破 3911
    (x_right(0.55), y(P_SUPP_PRIMARY)), # 12:30 跌破前低 3881
    (x_right(0.80), y(3865)),         # 14:00 测 3865
    (x_right(1.00), y(P_SUPP_LOWEST)),  # 15:00 3850
]

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 470" font-family="-apple-system,'PingFang SC',sans-serif" font-size="11">
  <defs>
    <style>
      .axis{{stroke:#3a4a4a;stroke-width:1;fill:none}}
      .grid{{stroke:#d8d2c4;stroke-width:0.5;stroke-dasharray:2 3}}
      .label{{fill:#3a4a4a;font-size:10px}}
      .price-label{{fill:#1f3a3a;font-size:9px;font-weight:600}}
      .supp{{stroke:#1a7a3a;stroke-width:1.5;fill:none}}
      .resist{{stroke:#b33a1f;stroke-width:1.5;fill:none}}
      .now{{stroke:#2b2b2b;stroke-width:1.5;fill:none}}
      .actual{{stroke:#1f3a3a;stroke-width:2;fill:none}}
      .scenario-a{{stroke:#b33a1f;stroke-width:1.8;fill:none;stroke-dasharray:6 4}}
      .scenario-b{{stroke:#2e6e2e;stroke-width:1.8;fill:none;stroke-dasharray:6 4}}
      .legend-text{{font-size:10px;fill:#1f3a3a}}
      .title{{font-size:14px;font-weight:700;fill:#1f3a3a}}
    </style>
  </defs>

  <!-- 标题 -->
  <text x="340" y="14" text-anchor="middle" class="title">上证综指 8/27 预判走势图 · v5</text>

  <!-- y 轴价格刻度 -->
  {''.join([f'<line class="grid" x1="20" y1="{y(p)}" x2="660" y2="{y(p)}"/><text class="label" x="14" y="{y(p)+3}" text-anchor="end">{p}</text>' for p in [3844, 3860, 3880, 3900, 3920, 3940, 3960, 3968]])}
'''

# y 轴线
svg += f'  <line class="axis" x1="20" y1="20" x2="20" y2="470"/>\n'

# x 轴：分隔线 8/26 与 8/27
svg += f'  <line class="grid" x1="340" y1="20" x2="340" y2="470" stroke-dasharray="3 4"/>\n'
svg += f'  <text x="180" y="465" text-anchor="middle" class="label">8/26 已走</text>\n'
svg += f'  <text x="500" y="465" text-anchor="middle" class="label">8/27 剧本</text>\n'

# 8/26 已走路径（实线）
path_d_826 = 'M ' + ' L '.join([f'{x:.1f},{y_:.1f}' for x, y_ in path_826])
svg += f'  <path class="actual" d="{path_d_826}"/>\n'

# 8/26 关键点标注
svg += f'  <circle cx="{x_left(0):.1f}" cy="{y(P_OPEN_826):.1f}" r="3" fill="#1f3a3a"/>\n'
svg += f'  <text class="price-label" x="{x_left(0)-5:.1f}" y="{y(P_OPEN_826)+15:.1f}" text-anchor="end" fill="#1a5a3a">O 3881.74</text>\n'
svg += f'  <circle cx="{x_left(0.30):.1f}" cy="{y(P_HIGH_826):.1f}" r="3" fill="#b33a1f"/>\n'
svg += f'  <text class="price-label" x="{x_left(0.30)+5:.1f}" y="{y(P_HIGH_826)-5:.1f}" fill="#b33a1f">H 3926.44</text>\n'
svg += f'  <circle cx="{x_left(1.00):.1f}" cy="{y(P_CLOSE_826):.1f}" r="4" fill="#2b2b2b"/>\n'
svg += f'  <text class="price-label" x="{x_left(1.00)+5:.1f}" y="{y(P_CLOSE_826)+3:.1f}">C 3912.52</text>\n'

# 剧本 A 虚线
path_d_a = 'M ' + ' L '.join([f'{x:.1f},{y_:.1f}' for x, y_ in path_a])
svg += f'  <path class="scenario-a" d="{path_d_a}"/>\n'

# 剧本 B 虚线
path_d_b = 'M ' + ' L '.join([f'{x:.1f},{y_:.1f}' for x, y_ in path_b])
svg += f'  <path class="scenario-b" d="{path_d_b}"/>\n'

# 关键位水平线
key_levels = [
    (3881.74, 'SUPP 3881.74 前低10日', '#1a7a3a'),
    (3909.79, 'SUPP 3909.79 15F三买', '#2e8a4e'),
    (3911.08, '60F一卖三卖@3911.08（已突破）', '#7a7a7a'),
    (3925.67, 'RESIST 3925.67 60F MA55', '#b33a1f'),
    (3927.85, 'RESIST 3927.85 周线原一买三共振', '#a8301f'),
    (3968.48, 'RESIST 3968.48 周线一卖', '#8a2010'),
]
for p, lbl, color in key_levels:
    svg += f'  <line x1="20" y1="{y(p):.1f}" x2="660" y2="{y(p):.1f}" stroke="{color}" stroke-width="0.6" stroke-dasharray="2 3" opacity="0.7"/>\n'
    svg += f'  <text x="668" y="{y(p)+3:.1f}" font-size="9" fill="{color}">{lbl}</text>\n' if p != 3881.74 else f'  <text x="668" y="{y(p)-3:.1f}" font-size="9" fill="{color}">{lbl}</text>\n'

# 当前价 3912.52 水平线
svg += f'  <line x1="20" y1="{y(P_NOW):.1f}" x2="660" y2="{y(P_NOW):.1f}" stroke="#2b2b2b" stroke-width="1" opacity="0.85"/>\n'
svg += f'  <text x="680" y="{y(P_NOW)+3:.1f}" font-size="10" font-weight="700" fill="#2b2b2b">Day C 3912.52 现价</text>\n' if False else f'  <text x="660" y="{y(P_NOW)+3:.1f}" font-size="10" font-weight="700" fill="#2b2b2b">现价 3912.52</text>\n'

# 图例（左上角）
svg += '''  <g transform="translate(28,32)">
    <rect x="0" y="0" width="220" height="60" fill="#fdfaf3" stroke="#a89e87" stroke-width="0.6" opacity="0.95"/>
    <line x1="10" y1="14" x2="40" y2="14" stroke="#1f3a3a" stroke-width="2"/>
    <text x="46" y="18" class="legend-text">8/26 已走路径（实线）</text>
    <line x1="10" y1="32" x2="40" y2="32" stroke="#b33a1f" stroke-width="1.8" stroke-dasharray="6 4"/>
    <text x="46" y="36" class="legend-text">Scenario A 反抽修复 50%</text>
    <line x1="10" y1="50" x2="40" y2="50" stroke="#2e6e2e" stroke-width="1.8" stroke-dasharray="6 4"/>
    <text x="46" y="54" class="legend-text">Scenario B 偏空延续 50%</text>
  </g>
'''

# 关键事件标注
svg += '''  <g transform="translate(28,98)">
    <rect x="0" y="0" width="220" height="50" fill="#fdfaf3" stroke="#a89e87" stroke-width="0.6" opacity="0.95"/>
    <text x="10" y="16" font-size="9.5" fill="#1f3a3a">事件：NVDA F2Q27 财报已落地</text>
    <text x="10" y="30" font-size="9.5" fill="#1f3a3a">营收 962.21 亿 +106%（超预期）</text>
    <text x="10" y="44" font-size="9.5" fill="#b33a1f">F2028 指引 +70%（市场预期 45%）</text>
  </g>
'''

svg += '</svg>'

with open(r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12\outputs\000001_forecast_2026-08-27.svg', 'w', encoding='utf-8') as f:
    f.write(svg)

print(f"SVG written, size={len(svg)} chars")
print(f"y_min@y={y(3844):.1f}, y_max@y={y(3968):.1f}")
print(f"3912.52@y={y(3912.52):.1f}, 3881.74@y={y(3881.74):.1f}, 3926.44@y={y(3926.44):.1f}")