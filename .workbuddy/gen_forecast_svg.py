# -*- coding: utf-8 -*-
"""条件触发决策路径图 SVG：当日实况形态 + 震荡区间带 + 上下两个变盘点（三态：震荡/突破/跌破）。
红涨绿跌。y 轴铁律：y = 底部 - (价格-最低)/价差*图高。

数据来源（**缺数据即报错，不回退**，2026-09-17 加固）：
  - 关键位/信号/概率：forecast_chain.json 最新 pending 预判的 `levels` 字段
  - 已走路径 OHLC：最新 verified 记录的 `review.actual`
  ⚠️ 旧版在两者任一缺失时**静默回退到写死的 2026-08-31 数据** —— 会把 8/31 的
     走势图塞进 9 月的报告，且只打印一行 `SVG written` 看不出异常。已彻底移除。

三态结构（弃用旧的"二分支要么涨要么跌"）：
1) 核心震荡带（down_support ~ decision）浅色填充，现价在带内
2) 震荡主路径（灰虚线）——区间内震荡是常态，线宽随 prob.range
3) 上沿决策位（decision）→ 突破路径（红，向上到 up_target），线宽随 prob.up
4) 下沿决策位（down_support）→ 跌破路径（绿，向下到 down_lower），线宽随 prob.down
另：当日实况形态（上影线/下影线判断）+ 假突破标注 + 当日关键信号。

用法：
    python gen_forecast_svg.py                    # 用最新 pending 记录
    python gen_forecast_svg.py --pred 2026-09-17-morning   # 指定记录重绘历史图
    python gen_forecast_svg.py --out <路径.svg>   # 指定输出（默认 outputs/000001_forecast_<date>.svg）
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
# 2026-09-18：显示层脱敏。链数据（forecast_chain.json）里的 levels.*.label / signals
# 属**刻意保留的历史原文**，但本脚本会把它们渲染进对外可见的 SVG —— 这是一条泄漏路径。
# 故在此统一过一道 scrub，只改渲染输出、不动数据。
from display_names import scrub, scrub_all

CHAIN = os.path.join(HERE, 'forecast_chain.json')


def load_data(pred_id=None):
    """读取绘图数据。返回 (levels, actual_ohlc, pred_id)。

    ⚠️ 2026-09-17 加固：原实现在读不到数据时**静默回退到写死的 2026-08-31 数据**
    （DEFAULT_LEVELS / DEFAULT_ACTUAL）。后果比崩溃严重得多 —— 链上没有可用 pending 时，
    9 月的报告会被塞进一张 **8/31 的走势图**：图看着正常、四个价位全错、
    而调用方只看到一行 `SVG written` 便以为成功。
    现改为缺数据即明确报错退出（非零），不再渲染任何陈旧数据；
    需要重绘历史图时用 `--pred <id>` 显式指定记录。
    """
    try:
        with open(CHAIN, encoding='utf-8') as f:
            chain = json.load(f)
    except Exception as e:
        raise SystemExit('[FAIL] 无法读取预判链 %s：%r' % (CHAIN, e))

    if pred_id:
        cand = [r for r in chain if r.get('id') == pred_id]
        if not cand:
            raise SystemExit('[FAIL] 链中找不到记录 id=%s' % pred_id)
        p = cand[0]
    else:
        pend = [r for r in chain if r.get('status') == 'pending']
        if not pend:
            raise SystemExit(
                '[FAIL] 预判链中没有任何 pending 记录，无法确定本期预判。\n'
                '       请先跑 chain_apply 落链（追本期预判），或用 --pred <id> 指定历史记录重绘。')
        p = pend[-1]

    rid = p.get('id')
    lv = p.get('levels')
    need = ['now', 'decision', 'up_target', 'down_support', 'down_lower']
    if not isinstance(lv, dict) or not all(k in lv for k in need):
        raise SystemExit('[FAIL] %s 的 levels 不完整（需含 %s），无法绘图。'
                         % (rid, ' / '.join(need)))

    act = None
    for r in reversed([x for x in chain
                       if x.get('status') == 'verified' and isinstance(x.get('review'), dict)]):
        a = r['review'].get('actual')
        if isinstance(a, dict) and all(k in a for k in ['open', 'high', 'low', 'close']):
            act = a
            break
    if act is None:
        raise SystemExit('[FAIL] 链中找不到含 open/high/low/close 的 verified.review.actual，'
                         '走势图无法叠加真实走势。\n'
                         '       请先完成上一条的复盘（chain_apply 的 review 段）再生成图。')
    return lv, act, rid


def build_svg(lv, act, out_path):
    P_NOW = float(lv['now'])
    # 所有写入 SVG 的文本都过 scrub（标签与信号来自链数据原文）
    P_DEC = float(lv['decision']['price']); L_DEC = scrub(lv['decision']['label'])
    P_UP = float(lv['up_target']['price']); L_UP = scrub(lv['up_target']['label'])
    P_DN = float(lv['down_support']['price']); L_DN = scrub(lv['down_support']['label'])
    P_LOW = float(lv['down_lower']['price']); L_LOW = scrub(lv['down_lower']['label'])
    D = lv.get('date', '')
    signals = scrub_all(lv.get('signals', []))
    O, H, L, C = float(act['open']), float(act['high']), float(act['low']), float(act['close'])

    # 三态概率（兼容旧 {"A":..,"B":..} 格式）
    prob = lv.get('prob', {}) or {}
    if 'up' in prob:
        p_up = float(prob.get('up', 0.3)); p_range = float(prob.get('range', 0.4)); p_down = float(prob.get('down', 0.3))
    else:
        p_up = float(prob.get('A', 0.25)); p_down = float(prob.get('B', 0.30))
        p_range = max(0.1, 1 - p_up - p_down)
    w_up = 1.5 + p_up * 2.0
    w_range = 1.5 + p_range * 2.0
    w_down = 1.5 + p_down * 2.0

    # 价格轴
    PRICE_MIN = min(P_LOW, L, O) - 40
    PRICE_MAX = max(P_UP, H) + 40
    PRICE_RANGE = PRICE_MAX - PRICE_MIN
    Y_BOTTOM, Y_TOP, Y_RANGE = 480.0, 40.0, 440.0

    def y(p):
        return Y_BOTTOM - (p - PRICE_MIN) / PRICE_RANGE * Y_RANGE

    def path(points):
        return 'M ' + ' L '.join(f'{x:.1f},{yy:.1f}' for x, yy in points)

    ticks = []
    t = int(PRICE_MIN // 20) * 20
    while t <= PRICE_MAX:
        if t >= PRICE_MIN:
            ticks.append(t)
        t += 20

    svg = []
    svg.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-40 0 940 580" font-family="-apple-system,\'PingFang SC\',sans-serif">')
    svg.append('<defs><style>')
    svg.append('.grid{stroke:#d8d2c4;stroke-width:0.5;stroke-dasharray:2 3}')
    svg.append('.axis{stroke:#3a4a4a;stroke-width:1;fill:none}')
    svg.append('.label{fill:#3a4a4a;font-size:10px}')
    svg.append('.actual{stroke:#1f3a3a;stroke-width:2.2;fill:none}')
    svg.append('.node-up{fill:#fdf0ec;stroke:#b33a1f;stroke-width:2}')
    svg.append('.node-dn{fill:#edf5ee;stroke:#1a7a3a;stroke-width:2}')
    svg.append('.tt{font-size:11px;font-weight:700}')
    svg.append('.tb{font-size:10px}')
    svg.append('.ts{font-size:9px}')
    svg.append('</style></defs>')

    svg.append(f'<text x="430" y="18" text-anchor="middle" class="tt" fill="#1f3a3a" font-size="15">上证综指 {D} 预判 · 震荡区间 + 变盘路径图（v5）</text>')

    for p in ticks:
        svg.append(f'<line class="grid" x1="20" y1="{y(p):.1f}" x2="600" y2="{y(p):.1f}"/>')
        svg.append(f'<text class="label" x="14" y="{y(p)+3:.1f}" text-anchor="end">{p}</text>')
    svg.append('<line class="axis" x1="20" y1="40" x2="20" y2="480"/>')

    svg.append('<line class="grid" x1="240" y1="40" x2="240" y2="480" stroke="#a89e87" stroke-dasharray="3 4"/>')
    svg.append('<text x="130" y="500" text-anchor="middle" class="label">当日实况</text>')
    svg.append('<text x="420" y="500" text-anchor="middle" class="label">震荡区间 · 变盘路径</text>')

    # ---- 已走路径（当日实况形态） ----
    upper_shadow = H - max(O, C)
    lower_shadow = min(O, C) - L
    if upper_shadow >= lower_shadow:
        act_pts = [(20, y(O)), (100, y(H)), (170, y(L)), (240, y(C))]
        hx, lx = 100, 170
    else:
        act_pts = [(20, y(O)), (100, y(L)), (170, y(H)), (240, y(C))]
        hx, lx = 170, 100
    svg.append(f'<path class="actual" d="{path(act_pts)}"/>')
    svg.append(f'<circle cx="20" cy="{y(O):.1f}" r="3" fill="#1f3a3a"/>')
    svg.append(f'<text class="ts" x="18" y="{y(O)+14:.1f}" text-anchor="end" fill="#1a5a3a">O {O:.2f}</text>')
    svg.append(f'<circle cx="{hx}" cy="{y(H):.1f}" r="3" fill="#b33a1f"/>')
    svg.append(f'<text class="ts" x="{hx+4}" y="{y(H)-4:.1f}" fill="#b33a1f">H {H:.2f}</text>')
    svg.append(f'<circle cx="{lx}" cy="{y(L):.1f}" r="3" fill="#1a7a3a"/>')
    svg.append(f'<text class="ts" x="{lx+4}" y="{y(L)+14:.1f}" fill="#1a7a3a">L {L:.2f}</text>')
    svg.append(f'<circle cx="240" cy="{y(C):.1f}" r="3" fill="#1f3a3a"/>')
    svg.append(f'<text class="ts" x="228" y="{y(C)-8:.1f}" text-anchor="end" fill="#1f3a3a">C {C:.2f}</text>')

    if H > P_DEC + 0.5:
        svg.append(f'<text class="tb" x="{hx}" y="{y(H)-16:.1f}" fill="#b33a1f">⚠ 假突破 {P_DEC:.0f} 失败</text>')

    # ---- 当日关键信号（左侧顶部） ----
    if signals:
        sig_y = 48.0
        svg.append(f'<text x="22" y="{sig_y:.1f}" class="tb" fill="#b33a1f">▸ 当日关键信号</text>')
        for s in signals[:3]:
            sig_y += 15
            svg.append(f'<text x="24" y="{sig_y:.1f}" class="ts" fill="#5a5a4f">· {s}</text>')

    # ---- 震荡区间带（下沿 P_DN ~ 上沿 P_DEC） ----
    y_up_band = y(P_DEC)
    y_dn_band = y(P_DN)
    svg.append(f'<rect x="240" y="{y_up_band:.1f}" width="360" height="{y_dn_band - y_up_band:.1f}" fill="#f3eddd" opacity="0.55"/>')
    svg.append(f'<text class="ts" x="592" y="{((y_up_band + y_dn_band) / 2):.1f}" text-anchor="end" fill="#8a7a55">震荡带 {P_DN:.0f}–{P_DEC:.0f}</text>')

    # 现价点
    svg.append(f'<circle cx="240" cy="{y(P_NOW):.1f}" r="4.5" fill="#2b2b2b"/>')
    svg.append(f'<text class="tb" x="234" y="{y(P_NOW)-8:.1f}" text-anchor="end" fill="#2b2b2b">现价 {P_NOW:.2f}</text>')

    # ---- 震荡主路径（灰虚线，区间内锯齿，常态） ----
    amp = min(8.0, (P_DEC - P_DN) * 0.15)
    zz = [(240, y(P_NOW)), (320, y(P_NOW + amp)), (400, y(P_NOW - amp)), (480, y(P_NOW + amp * 0.6)), (600, y(P_NOW))]
    svg.append(f'<path d="{path(zz)}" stroke="#8a8a80" stroke-width="{w_range:.1f}" fill="none" stroke-dasharray="4 3"/>')
    svg.append(f'<text class="tb" x="330" y="{y(P_NOW + amp) + 14:.1f}" fill="#6a6a5f">区间震荡（{p_range*100:.0f}%）</text>')

    # ---- 上沿决策位 + 突破路径（红） ----
    ux = 420.0
    svg.append(f'<polygon class="node-up" points="{ux},{y(P_DEC)-11} {ux+11},{y(P_DEC)} {ux},{y(P_DEC)+11} {ux-11},{y(P_DEC)}"/>')
    up_pts = [(ux, y(P_DEC)), (510, y(P_DEC + (P_UP - P_DEC) * 0.5)), (600, y(P_UP))]
    svg.append(f'<path d="{path(up_pts)}" stroke="#b33a1f" stroke-width="{w_up:.1f}" fill="none"/>')
    svg.append(f'<polygon points="600,{y(P_UP)-8:.1f} 608,{y(P_UP):.1f} 600,{y(P_UP)+8:.1f} 592,{y(P_UP):.1f}" fill="#b33a1f"/>')
    svg.append(f'<text class="tb" x="{ux+16}" y="{y(P_DEC)-6:.1f}" fill="#b33a1f">突破 {P_DEC:.0f}（{p_up*100:.0f}%）</text>')
    svg.append(f'<text class="ts" x="490" y="{y(P_DEC + (P_UP - P_DEC) * 0.55):.1f}" fill="#b33a1f">放量站稳 → 看 {P_UP:.0f} {L_UP}</text>')

    # ---- 下沿决策位 + 跌破路径（绿） ----
    dx = 420.0
    svg.append(f'<polygon class="node-dn" points="{dx},{y(P_DN)-11} {dx+11},{y(P_DN)} {dx},{y(P_DN)+11} {dx-11},{y(P_DN)}"/>')
    dn_pts = [(dx, y(P_DN)), (510, y(P_DN - (P_DN - P_LOW) * 0.5)), (600, y(P_LOW))]
    svg.append(f'<path d="{path(dn_pts)}" stroke="#1a7a3a" stroke-width="{w_down:.1f}" fill="none"/>')
    svg.append(f'<polygon points="600,{y(P_LOW)-8:.1f} 608,{y(P_LOW):.1f} 600,{y(P_LOW)+8:.1f} 592,{y(P_LOW):.1f}" fill="#1a7a3a"/>')
    svg.append(f'<text class="tb" x="{dx+16}" y="{y(P_DN)+14:.1f}" fill="#1a7a3a">跌破 {P_DN:.0f}（{p_down*100:.0f}%）</text>')
    svg.append(f'<text class="ts" x="490" y="{y(P_DN - (P_DN - P_LOW) * 0.55) + 4:.1f}" fill="#1a7a3a">缩量跌破 → 看 {P_LOW:.0f} {L_LOW}</text>')

    # ---- 关键位水平线 + 右侧标签 ----
    levels = [
        (P_UP, f'RESIST {P_UP:.2f} {L_UP}', '#b33a1f'),
        (P_DEC, f'RESIST {P_DEC:.2f} {L_DEC}', '#b33a1f'),
        (P_DN, f'SUPP {P_DN:.2f} {L_DN}', '#1a7a3a'),
    ]
    if abs(P_LOW - P_DN) / P_DN >= 0.01:
        levels.append((P_LOW, f'SUPP {P_LOW:.2f} {L_LOW}', '#1a7a3a'))
    else:
        levels.append((P_LOW, None, '#1a7a3a'))
    for p, lbl, color in levels:
        svg.append(f'<line x1="20" y1="{y(p):.1f}" x2="600" y2="{y(p):.1f}" stroke="{color}" stroke-width="0.7" stroke-dasharray="2 3" opacity="0.75"/>')
        if lbl:
            svg.append(f'<text class="ts" x="610" y="{y(p)+3:.1f}" fill="{color}">{lbl}</text>')

    # ---- 盘面应对框（右下） ----
    svg.append('<g>')
    svg.append('<rect x="615" y="385" width="270" height="150" rx="6" fill="#fffdf6" stroke="#a89e87" stroke-width="0.8"/>')
    svg.append('<text x="627" y="403" class="tb" fill="#1f3a3a">盘面应对（v5 纪律）</text>')
    svg.append(f'<text x="627" y="423" class="ts" fill="#6a6a5f">震荡：{P_DN:.0f}–{P_DEC:.0f} 内不追涨杀跌，等变盘</text>')
    svg.append(f'<text x="627" y="441" class="ts" fill="#b33a1f">突破：放量站稳 {P_DEC:.0f} → 追多，看 {P_UP:.0f}</text>')
    svg.append(f'<text x="627" y="459" class="ts" fill="#1a7a3a">跌破：跌破 {P_DN:.0f} → 减仓，看 {P_LOW:.0f}</text>')
    svg.append(f'<text x="627" y="477" class="ts" fill="#5a5a4f">信号：{signals[0] if signals else '待定'}</text>')
    svg.append(f'<text x="627" y="491" class="ts" fill="#5a5a4f">信号：{signals[1] if len(signals) > 1 else '—'}</text>')
    svg.append(f'<text x="627" y="505" class="ts" fill="#5a5a4f">信号：{signals[2] if len(signals) > 2 else '—'}</text>')
    svg.append(f'<text x="627" y="523" class="ts" fill="#5a5a4f">概率：突破{p_up*100:.0f}% / 震荡{p_range*100:.0f}% / 跌破{p_down*100:.0f}%</text>')
    svg.append('</g>')

    # ---- 图例（底部） ----
    svg.append('<g>')
    svg.append('<rect x="20" y="545" width="580" height="26" rx="4" fill="#fffdf6" stroke="#a89e87" stroke-width="0.6"/>')
    svg.append('<line x1="30" y1="558" x2="52" y2="558" stroke="#1f3a3a" stroke-width="2"/>')
    svg.append('<text x="56" y="562" class="ts" fill="#1f3a3a">当日实况</text>')
    svg.append('<line x1="130" y1="558" x2="152" y2="558" stroke="#8a8a80" stroke-width="2.5" stroke-dasharray="4 3"/>')
    svg.append('<text x="156" y="562" class="ts" fill="#5a5a4f">震荡（常态）</text>')
    svg.append('<line x1="250" y1="558" x2="272" y2="558" stroke="#b33a1f" stroke-width="3"/>')
    svg.append('<text x="276" y="562" class="ts" fill="#b33a1f">突破（线宽=概率）</text>')
    svg.append('<line x1="380" y1="558" x2="402" y2="558" stroke="#1a7a3a" stroke-width="3"/>')
    svg.append('<text x="406" y="562" class="ts" fill="#1a7a3a">跌破（线宽=概率）</text>')
    svg.append('<line x1="495" y1="558" x2="517" y2="558" stroke="#7a7a7a" stroke-width="1" stroke-dasharray="2 3"/>')
    svg.append('<text x="521" y="562" class="ts" fill="#5a5a4f">关键位</text>')
    svg.append('</g>')

    svg.append('</svg>')
    content = '\n'.join(svg)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return len(content)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='生成条件触发决策路径图 SVG（当日实况形态 + 震荡区间带 + 上下两个变盘点）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='例:\n'
               '  python gen_forecast_svg.py\n'
               '  python gen_forecast_svg.py --pred 2026-09-17-morning\n'
               '  python gen_forecast_svg.py --pred 2026-09-17-morning --out /tmp/x.svg')
    ap.add_argument('--pred', default=None, metavar='ID',
                    help='指定预判链记录 id 重绘历史图；不给则用最新 pending 记录')
    ap.add_argument('--out', default=None, metavar='PATH',
                    help='输出 SVG 路径；不给则默认 outputs/000001_forecast_<date>.svg')
    a = ap.parse_args(argv)

    lv, act, rid = load_data(a.pred)

    # ⚠️ 2026-09-17 加固：原为 `d = lv.get('date','') or '2026-08-31'`，
    # 缺日期时文件名会退化成写死的 8/31。现在：给了 --out 就与 date 无关；
    # 没给 --out 才需要 date 来推默认文件名，缺了即报错。
    if a.out:
        out = os.path.abspath(a.out)
    else:
        d = lv.get('date', '')
        if not d:
            raise SystemExit(
                '[FAIL] %s 的 levels 缺少 date 字段，推不出默认输出文件名。\n'
                '       请用 --out <路径.svg> 显式指定输出。' % rid)
        d = str(d).replace('/', '-')
        out = os.path.normpath(os.path.join(HERE, '..', 'outputs', '000001_forecast_%s.svg' % d))

    od = os.path.dirname(out)
    if od and not os.path.isdir(od):
        raise SystemExit('[FAIL] 输出目录不存在：%s' % od)

    n = build_svg(lv, act, out)
    size = os.path.getsize(out)
    print('SVG written: %s' % out)
    print('  chars=%d bytes=%d pred=%s' % (n, size, rid))
    print('  now=%s band=(%s~%s) up=%s lower=%s'
          % (lv['now'], lv['down_support']['price'], lv['decision']['price'],
             lv['up_target']['price'], lv['down_lower']['price']))
    print('  signals=%s prob=%s' % (lv.get('signals', []), lv.get('prob', {})))
    return 0


if __name__ == '__main__':
    sys.exit(main())
