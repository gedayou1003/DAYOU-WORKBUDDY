# -*- coding: utf-8 -*-
"""条件触发决策路径图 SVG：主路径(现价→决策位)+决策点(菱形)+分支(放量突破红/缩量假突破绿)，
每条分支标注触发条件+目标位+盘面应对。红涨绿跌。y 轴铁律：y = 底部 - (价格-最低)/价差*图高。

参数化：优先从 forecast_chain.json 最新 pending 预判的 `levels` 字段读关键位；
已走路径 OHLC 从最新 verified 记录的 review.actual 读；缺失时回退 DEFAULT。"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'forecast_chain.json')

# 回退默认值（8/28 盘中）
DEFAULT_LEVELS = {
    'date': '8/28',
    'now': 3964.92,
    'decision': {'price': 3968.48, 'label': '周线一卖'},
    'up_target': {'price': 4034.08, 'label': '周线中枢上沿'},
    'down_support': {'price': 3927.85, 'label': '三共振'},
    'down_lower': {'price': 3909.79, 'label': '15F三买'},
}
DEFAULT_ACTUAL = {'open': 3911.89, 'high': 3958.03, 'low': 3909.31, 'close': 3956.57}


def load_data():
    """返回 (levels, actual_ohlc, pred_id)。读不到就用 DEFAULT。"""
    lv, act, rid = dict(DEFAULT_LEVELS), dict(DEFAULT_ACTUAL), None
    try:
        chain = json.load(open(CHAIN, encoding='utf-8'))
    except Exception:
        return lv, act, rid
    # 最新 pending 的 levels
    pend = [r for r in chain if r.get('status') == 'pending']
    if pend:
        p = pend[-1]
        rid = p.get('id')
        if isinstance(p.get('levels'), dict):
            need = ['now', 'decision', 'up_target', 'down_support', 'down_lower']
            if all(k in p['levels'] for k in need):
                lv = p['levels']
    # 最新 verified 的 actual
    ver = [r for r in chain if r.get('status') == 'verified' and isinstance(r.get('review'), dict)]
    if ver:
        a = ver[-1]['review'].get('actual')
        if isinstance(a, dict) and all(k in a for k in ['open', 'high', 'low', 'close']):
            act = a
    return lv, act, rid


def build_svg(lv, act, out_path):
    P_NOW = float(lv['now'])
    P_DEC = float(lv['decision']['price']); L_DEC = lv['decision']['label']
    P_UP = float(lv['up_target']['price']); L_UP = lv['up_target']['label']
    P_DN = float(lv['down_support']['price']); L_DN = lv['down_support']['label']
    P_LOW = float(lv['down_lower']['price']); L_LOW = lv['down_lower']['label']
    D = lv.get('date', '')
    O, H, L, C = float(act['open']), float(act['high']), float(act['low']), float(act['close'])

    # 价格轴：下沿比最低支撑再低 40 点，上沿比最高目标再高 40 点
    PRICE_MIN = min(P_LOW, L, O) - 40
    PRICE_MAX = max(P_UP, H) + 40
    PRICE_RANGE = PRICE_MAX - PRICE_MIN
    Y_BOTTOM, Y_TOP, Y_RANGE = 480.0, 40.0, 440.0

    def y(p):
        return Y_BOTTOM - (p - PRICE_MIN) / PRICE_RANGE * Y_RANGE

    def path(points):
        return 'M ' + ' L '.join(f'{x:.1f},{yy:.1f}' for x, yy in points)

    # y 轴刻度：从 PRICE_MIN 向上每 20 点
    ticks = []
    t = int(PRICE_MIN // 20) * 20
    while t <= PRICE_MAX:
        if t >= PRICE_MIN:
            ticks.append(t)
        t += 20

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

    svg.append(f'<text x="450" y="18" text-anchor="middle" class="tt" fill="#1f3a3a" font-size="15">上证综指 {D} 预判 · 条件触发决策路径图（v5）</text>')

    for p in ticks:
        svg.append(f'<line class="grid" x1="20" y1="{y(p):.1f}" x2="600" y2="{y(p):.1f}"/>')
        svg.append(f'<text class="label" x="14" y="{y(p)+3:.1f}" text-anchor="end">{p}</text>')
    svg.append('<line class="axis" x1="20" y1="40" x2="20" y2="480"/>')

    svg.append('<line class="grid" x1="240" y1="40" x2="240" y2="480" stroke="#a89e87" stroke-dasharray="3 4"/>')
    svg.append('<text x="130" y="500" text-anchor="middle" class="label">前日已走</text>')
    svg.append('<text x="420" y="500" text-anchor="middle" class="label">当日决策路径</text>')

    # 前日已走路径（O→H→回撤→C）
    act_pts = [(20, y(O)), (86, y(H)), (130, y((H + C) / 2)), (175, y(C)), (240, y(C))]
    svg.append(f'<path class="actual" d="{path(act_pts)}"/>')
    svg.append(f'<circle cx="20" cy="{y(O):.1f}" r="3" fill="#1f3a3a"/>')
    svg.append(f'<text class="ts" x="18" y="{y(O)+14:.1f}" text-anchor="end" fill="#1a5a3a">O {O:.2f}</text>')
    svg.append(f'<circle cx="86" cy="{y(H):.1f}" r="3" fill="#b33a1f"/>')
    svg.append(f'<text class="ts" x="90" y="{y(H)-4:.1f}" fill="#b33a1f">H {H:.2f}</text>')

    # 现价点（决策起点）
    svg.append(f'<circle cx="240" cy="{y(P_NOW):.1f}" r="4.5" fill="#2b2b2b"/>')
    svg.append(f'<text class="tb" x="234" y="{y(P_NOW)-8:.1f}" text-anchor="end" fill="#2b2b2b">现价 {P_NOW:.2f}</text>')

    # 主路径：现价 → 决策点
    svg.append(f'<path class="main-path" d="{path([(240, y(P_NOW)), (400, y(P_DEC))])}"/>')
    mid = (P_NOW + P_DEC) / 2
    svg.append('<text class="ts" x="385" y="'+f'{y(mid)-6:.1f}" text-anchor="end" fill="#5a5a4f">主路径：上攻 {L_DEC}</text>')

    # 决策点（菱形）
    nx, ny = 400.0, y(P_DEC)
    svg.append(f'<polygon class="node" points="{nx},{ny-11} {nx+11},{ny} {nx},{ny+11} {nx-11},{ny}"/>')
    svg.append(f'<text class="tb" x="{nx+16}" y="{ny-4:.1f}" fill="#b33a1f">决策位 {L_DEC} {P_DEC:.2f}</text>')

    # 分支 A（放量突破，红）
    pa = [(nx, ny), (465, y(P_NOW + (P_UP - P_NOW) * 0.45)), (530, y(P_NOW + (P_UP - P_NOW) * 0.8)), (600, y(P_UP))]
    svg.append(f'<path class="branch-a" d="{path(pa)}"/>')
    svg.append(f'<polygon points="600,{y(P_UP)-8:.1f} 608,{y(P_UP):.1f} 600,{y(P_UP)+8:.1f} 592,{y(P_UP):.1f}" fill="#b33a1f"/>')
    ya = y(P_NOW + (P_UP - P_NOW) * 0.6)
    svg.append(f'<text class="tb" x="470" y="{ya-6:.1f}" fill="#b33a1f">A 放量突破</text>')
    svg.append(f'<text class="ts" x="470" y="{ya+6:.1f}" fill="#b33a1f">触发：放量站稳 {P_DEC:.0f}</text>')
    svg.append(f'<text class="ts" x="470" y="{ya+17:.1f}" fill="#b33a1f">应对：追多·持股</text>')
    svg.append(f'<text class="ts" x="598" y="{y(P_UP)-14:.1f}" text-anchor="end" fill="#b33a1f">目标 {P_UP:.2f} {L_UP}</text>')

    # 分支 B（缩量假突破·诱多，绿）
    pb = [(nx, ny), (455, y(P_DEC - (P_DEC - P_DN) * 0.5)), (510, y(P_DN)), (545, y((P_DN + P_LOW) / 2)), (600, y(P_LOW))]
    svg.append(f'<path class="branch-b" d="{path(pb)}"/>')
    svg.append(f'<polygon points="600,{y(P_LOW)-8:.1f} 608,{y(P_LOW):.1f} 600,{y(P_LOW)+8:.1f} 592,{y(P_LOW):.1f}" fill="#1a7a3a"/>')
    yb = y(P_DEC - (P_DEC - P_DN) * 0.35)
    svg.append(f'<text class="tb" x="448" y="{yb-4:.1f}" fill="#1a7a3a">B 缩量假突破·诱多</text>')
    svg.append(f'<text class="ts" x="448" y="{yb+8:.1f}" fill="#1a7a3a">触发：缩量遇阻回落</text>')
    svg.append(f'<text class="ts" x="448" y="{yb+19:.1f}" fill="#1a7a3a">应对：逢高减仓·不追涨</text>')
    svg.append(f'<text class="ts" x="448" y="{yb+30:.1f}" fill="#1a7a3a">跌破 {P_DN:.0f} 看 {P_LOW:.0f}</text>')
    svg.append(f'<text class="ts" x="598" y="{y(P_LOW)+22:.1f}" text-anchor="end" fill="#1a7a3a">目标 {P_LOW:.2f} {L_LOW}</text>')

    # 关键位水平线 + 右侧标签
    levels = [
        (P_UP, f'RESIST {P_UP:.2f} {L_UP}', '#b33a1f'),
        (P_DEC, f'RESIST {P_DEC:.2f} {L_DEC}（决策位）', '#b33a1f'),
        (P_DN, f'SUPP {P_DN:.2f} {L_DN}', '#1a7a3a'),
    ]
    # 下方支撑：若与主支撑价差 < 1%，只画线不标文字（避免标签重叠）
    if abs(P_LOW - P_DN) / P_DN >= 0.01:
        levels.append((P_LOW, f'SUPP {P_LOW:.2f} {L_LOW}', '#1a7a3a'))
    else:
        levels.append((P_LOW, None, '#1a7a3a'))
    for p, lbl, color in levels:
        svg.append(f'<line x1="20" y1="{y(p):.1f}" x2="600" y2="{y(p):.1f}" stroke="{color}" stroke-width="0.7" stroke-dasharray="2 3" opacity="0.75"/>')
        if lbl:
            svg.append(f'<text class="ts" x="610" y="{y(p)+3:.1f}" fill="{color}">{lbl}</text>')

    # 盘面应对框（右下）
    svg.append('<g>')
    svg.append('<rect x="615" y="385" width="270" height="150" rx="6" fill="#fffdf6" stroke="#a89e87" stroke-width="0.8"/>')
    svg.append('<text x="627" y="403" class="tb" fill="#1f3a3a">盘面应对（逆势反抽纪律）</text>')
    svg.append(f'<text x="627" y="423" class="ts" fill="#b33a1f">A 放量站稳 {P_DEC:.0f} → 60F 极强延续</text>')
    svg.append(f'<text x="627" y="437" class="ts" fill="#b33a1f">   追多/持股，目标 {P_UP:.0f} {L_UP}</text>')
    svg.append(f'<text x="627" y="455" class="ts" fill="#1a7a3a">B 缩量遇阻 {P_DEC:.0f} → 假突破回落</text>')
    svg.append(f'<text x="627" y="469" class="ts" fill="#1a7a3a">   逢高减仓不追涨，回踩 {P_DN:.0f} {L_DN}</text>')
    svg.append(f'<text x="627" y="483" class="ts" fill="#1a7a3a">   跌破看 {P_LOW:.0f} {L_LOW}</text>')
    svg.append(f'<text x="627" y="501" class="ts" fill="#5a5a4f">{L_DEC} {P_DEC:.0f} 附近不追高；</text>')
    svg.append(f'<text x="627" y="515" class="ts" fill="#5a5a4f">只有放量站稳 {P_DEC:.0f} + 周线 trend</text>')
    svg.append(f'<text x="627" y="529" class="ts" fill="#5a5a4f">持续向上才确认看 {P_UP:.0f}。</text>')
    svg.append('</g>')

    # 图例（底部）
    svg.append('<g>')
    svg.append('<rect x="20" y="545" width="580" height="26" rx="4" fill="#fffdf6" stroke="#a89e87" stroke-width="0.6"/>')
    svg.append('<line x1="30" y1="558" x2="52" y2="558" stroke="#1f3a3a" stroke-width="2"/>')
    svg.append('<text x="56" y="562" class="ts" fill="#1f3a3a">前日已走</text>')
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
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return len(content)


if __name__ == '__main__':
    lv, act, rid = load_data()
    d = lv.get('date', '') or '8/28'
    out = os.path.join(HERE, '..', 'outputs', f'000001_forecast_{d.replace("/", "-")}.svg')
    out = os.path.normpath(out)
    n = build_svg(lv, act, out)
    print(f'SVG written, size={n} chars, pred={rid}')
    print(f'now={lv["now"]}, decision={lv["decision"]["price"]}, up={lv["up_target"]["price"]}, down={lv["down_support"]["price"]}, lower={lv["down_lower"]["price"]}')
