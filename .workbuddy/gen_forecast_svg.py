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
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
# 2026-09-18：显示层脱敏。链数据（forecast_chain.json）里的 levels.*.label / signals
# 属**刻意保留的历史原文**，但本脚本会把它们渲染进对外可见的 SVG —— 这是一条泄漏路径。
# 故在此统一过一道 scrub，只改渲染输出、不动数据。
from display_names import scrub, scrub_all

CHAIN = os.path.join(HERE, 'forecast_chain.json')


def _date_prefix(s):
    """从 '2026-09-24-morning' / '2026-09-24 全天（09:30-15:00）' 抽 YYYY-MM-DD。抽不到返回 None。"""
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', str(s or ''))
    return m.group(1) if m else None


def pick_actual(chain, target, rid=None):
    """按 `target` 选「该叠进走势图的那一天」的 actual。

    ⚠️ 2026-09-24 复审（R4）修正：原实现取「链中**最后一条**带完整 OHLC 的 verified」，
    这在两种情况下会**取错日子**：
      ① `--pred <历史记录>` 重绘旧图时 —— 取到的是**今天**的 actual，画成「历史预判 + 未来走势」；
      ② 记录 target 与 actual.date **不等**时（`*-close` 档 target=次日、actual=次日收盘后回填、
         周末档 target=下周一 而 actual=上周五）—— 原实现靠着「链顺序恰好如此」蒙对，
         一旦中间插一条 history 记录就会错。
    正确语义：**target 锁定的那个交易日**的 actual。
      取值规则：actual.date 的日期段 **≤ target 日期**，取其中**最接近 target 的那条**
      （取「最近且不晚于」而非「最近」，是为了避免用**未来**的行情去画**当下**的图）。
    """
    tg = _date_prefix(target) or _date_prefix(rid)
    cands = []
    for r in chain:
        if r.get('status') != 'verified':
            continue
        rv = r.get('review')
        if not isinstance(rv, dict):
            continue
        a = rv.get('actual')
        if not isinstance(a, dict):
            continue
        if not all(k in a for k in ('open', 'high', 'low', 'close')):
            continue
        ad = _date_prefix(a.get('date'))
        if not ad:
            continue
        cands.append((ad, r.get('id'), a))
    if not cands:
        raise SystemExit(
            '[FAIL] 链中找不到含 open/high/low/close 的 verified.review.actual，'
            '走势图无法叠加真实走势。\n'
            '       请先完成上一条的复盘（chain_apply 的 review 段）再生成图。')
    if tg is None:
        # 既无 target 也无 id 日期 → 退化为「最后一条」（与旧行为一致，但显式打印来源）
        cands.sort(key=lambda x: (x[0], str(x[1])))
        ad, sid, a = cands[-1]
        return a, {'matched': 'fallback-last', 'actual_date': ad, 'source_id': sid, 'target': None}
    not_later = [c for c in cands if c[0] <= tg]
    pool = not_later or cands
    # 距 target 最近（同一天优先），并列时取链上更靠后的
    pool.sort(key=lambda x: (abs(_days_between(x[0], tg)), x[0], str(x[1])))
    ad, sid, a = pool[0]
    return a, {'matched': 'by-target', 'actual_date': ad, 'source_id': sid, 'target': tg,
               'exact': ad == tg, 'used_future': (not not_later)}


def _days_between(d1, d2):
    """两个 YYYY-MM-DD 的日历日差（绝对值）。解析失败返回一个大数。"""
    import datetime
    try:
        a = datetime.date(*[int(x) for x in str(d1).split('-')[:3]])
        b = datetime.date(*[int(x) for x in str(d2).split('-')[:3]])
        return abs((a - b).days)
    except Exception:
        return 10 ** 6


def load_data(pred_id=None):
    """读取绘图数据。返回 (levels, actual_ohlc, pred_id, meta)。

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

    act, meta = pick_actual(chain, p.get('target'), rid)
    # ⚠️ 2026-09-24 复审（R4）：目标日以 **记录 id 的日期段** 为准（`levels.date` 曾有
    # 「填成数据基准日」的历史问题，见下方 --out 缺省命名段的注释）。SVG 的自述目标日
    # 与默认文件名都统一用这个值，避免两个来源打架。
    meta['target_date'] = _date_prefix(rid) or _date_prefix(p.get('target')) or meta.get('actual_date') or ''
    return lv, act, rid, meta


def _text_w(s, fs=9.0):
    """估算文本像素宽：CJK/全角按 1.0em，其余按 0.55em（够用于「是否溢出」判断）。"""
    return sum((1.0 if ord(c) > 0x2E80 else 0.55) * fs for c in str(s))


def _fit(s, max_px, fs=9.0):
    """按估算宽度截断并补省略号。

    2026-09-18：`signals` 是链数据原文，长度不受控；而 SVG 视口右边界在 x=900，
    超长文本会被**静默裁掉半截字**（看不出报错）。这里做宽度收口，
    保证「要么完整显示、要么以 … 明确收尾」。
    """
    s = str(s)
    if _text_w(s, fs) <= max_px:
        return s
    ell = _text_w('…', fs)
    out = ''
    for ch in s:
        if _text_w(out + ch, fs) + ell > max_px:
            break
        out += ch
    return out + '…'


def build_svg(lv, act, out_path, rid=None, meta=None):
    meta = meta or {}
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
    # ⚠️ 2026-09-24 复审（R2-1）：SVG **自述自己是哪张图**。
    # 起因：9/23 午间档的图被 9/24 内容**静默覆盖**（md5 完全相同，不可恢复）——
    # 而 SVG 本体不含任何身份信息，两条同名不同内容的图从字节上完全无法区分。
    # 现在把「记录 id / 目标日 / 实际叠加的 actual 日期」写进 <title>/<desc>：
    #   · 人肉排查：直接打开 SVG 源码即可看出它是哪一档；
    #   · 机器校验：check_integrity.py 会核对 **文件名日期 == 自述目标日**。
    # 注意 `<title>` 是 SVG 的首个可访问名元素，屏幕阅读器也会读它，故文本保持简短。
    _self_tgt = str(meta.get('target_date') or '')
    _self_rid = str(rid or '')
    _self_act = str(meta.get('actual_date') or '')
    svg.append('<title>%s</title>' % (
        '上证综指 %s 预判图' % _self_tgt if _self_tgt else '上证综指预判图'))
    svg.append('<desc>pred=%s / date=%s / actual=%s</desc>' % (
        _self_rid, _self_tgt, _self_act))
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
    # 信号行按框宽收口（框 x 615~885，文字起于 627 → 预算 250px），防止视口裁切
    _sig_lines = []
    for _i in range(3):
        if _i == 0 and not signals:
            _sig_lines.append('信号：待定')
        elif len(signals) > _i:
            _sig_lines.append(_fit('信号：' + signals[_i], 250.0))
        else:
            _sig_lines.append('信号：—')
    svg.append(f'<text x="627" y="477" class="ts" fill="#5a5a4f">{_sig_lines[0]}</text>')
    svg.append(f'<text x="627" y="491" class="ts" fill="#5a5a4f">{_sig_lines[1]}</text>')
    svg.append(f'<text x="627" y="505" class="ts" fill="#5a5a4f">{_sig_lines[2]}</text>')
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
    ap.add_argument('--force', action='store_true',
                    help='允许覆盖「已存在且不属于本记录」的走势图（默认拒绝，防毁掉别的档位的图）')
    a = ap.parse_args(argv)

    lv, act, rid, meta = load_data(a.pred)

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

        # ⚠️ 2026-09-24 加固（真实事故）：levels.date 有两种合理语义 ——
        #   ① 目标交易日（本意，与记录 id 的日期一致）
        #   ② 数据基准日（现价取自哪天的收盘）
        # 本档 `2026-09-24-morning` 填了基准日 '2026-09-23'，于是默认文件名推成
        # `000001_forecast_2026-09-23.svg`，**静默覆盖了 9/23 午间档的走势图**
        # （新旧同为 7738 字节、无备份、不可恢复）。
        # 历史记录之所以没暴露，是因为 ① ② **恰好同值**：
        #   `2026-09-21-morning → '2026-09-21'`、`2026-09-23-noon → '2026-09-23'`。
        # 故此处必须显式校验：**记录 id 的日期段与 date 不一致 → 报错退出**，
        # 不再静默按 date 命名（正则应从 `2026-09-24-morning` 抽出 `2026-09-24`）。
        m = re.match(r'^(\d{4}-\d{2}-\d{2})', str(rid))
        if m and m.group(1) != d:
            raise SystemExit(
                '[FAIL] %s 的 levels.date=%s 与记录 id 的日期 %s 不一致，拒绝按 date 推默认文件名。\n'
                '       两种可能：① levels.date 填成了「数据基准日」而应为「目标交易日」；\n'
                '                 ② 该记录的 target 本就跨日。\n'
                '       ⚠️ 按 date 命名可能**覆盖别的档位的图**（2026-09-24 真实事故：\n'
                '          9/24 晨报覆盖了 9/23 午间档的 000001_forecast_2026-09-23.svg，不可恢复）。\n'
                '       请用 --out <路径.svg> 显式指定输出（推荐 outputs/000001_forecast_<目标日>.svg）。'
                % (rid, d, m.group(1)))
        out = os.path.normpath(os.path.join(HERE, '..', 'outputs', '000001_forecast_%s.svg' % d))

    od = os.path.dirname(out)
    if od and not os.path.isdir(od):
        raise SystemExit('[FAIL] 输出目录不存在：%s' % od)

    # ⚠️ 2026-09-24 二次加固（复审发现：上一版的守卫**只堵了默认路径，没堵 --out**）。
    # 事实核对：`outputs/000001_forecast_2026-09-23.svg` 与
    # `000001_forecast_2026-09-24.svg` **字节完全相同（md5 445af259…）** ——
    # 说明 9/23 午间档的图**已被 9/24 的内容覆盖且无从恢复**。
    # 上一版加的「date 与 id 不一致即报错」只在 `else` 分支里，
    # 而这个覆盖正是**通过显式 --out 打进去的**（我自己的修复动作就是那条路径）→
    # 守卫形同虚设：真正的风险是「写一个已存在的别的档位的图」，与路径怎么来的无关。
    #
    # 故这里改成**按输出路径本身**判定（对 --out 与默认两条路径一视同仁）：
    #   · 目标文件已存在、且**不是本记录 id 对应**的文件 → 拒绝覆盖
    #     （本记录重跑要覆盖自己，属正常；覆盖别人的图才是事故）
    #   · 需要刻意重绘历史档 → `--force` 显式越过（并且要求同时给 --out，避免默认路径下手滑）
    # 判据用 **目标日**（meta['target_date']，优先取 id 日期段）：文件名里含该日期即视为「自己的图」。
    _tgt = str(meta.get('target_date') or '')
    _m2 = re.match(r'^(\d{4}-\d{2}-\d{2})', str(rid or ''))
    if os.path.exists(out) and not a.force:
        base = os.path.basename(out)
        mine = bool(_tgt) and (_tgt in base)
        if not mine:
            raise SystemExit(
                '[FAIL] 拒绝覆盖已存在的走势图：%s\n'
                '       该文件名与本记录 id=%s 的目标日 %s 不符 —— 覆盖它会**毁掉别的档位的图**\n'
                '       （2026-09-24 真实事故：9/23 午间档的图已被 9/24 内容覆盖，md5 相同、不可恢复）。\n'
                '       若确认要重绘，请显式加 --force（建议同时 --out 指定目标）。'
                % (out, rid, _tgt or '(未知)'))

    n = build_svg(lv, act, out, rid=rid, meta=meta)
    size = os.path.getsize(out)
    print('SVG written: %s' % out)
    print('  chars=%d bytes=%d pred=%s' % (n, size, rid))
    print('  now=%s band=(%s~%s) up=%s lower=%s'
          % (lv['now'], lv['down_support']['price'], lv['decision']['price'],
             lv['up_target']['price'], lv['down_lower']['price']))
    print('  signals=%s prob=%s' % (lv.get('signals', []), lv.get('prob', {})))
    # ⚠️ 2026-09-24 复审（R4/R2-1）：把「自述目标日」和「实际叠加的 actual 是哪天」都打出来。
    # 原实现只打 `pred=<id>` —— 而正是这条输出让 9/24 那次覆盖**看起来完全正常**
    # （图写出来了、路径也合理、幂等重跑一致），没人会想到叠进去的走势图是别的档位的。
    print('  target_date=%s actual_date=%s match=%s%s'
          % (meta.get('target_date'), meta.get('actual_date'), meta.get('matched'),
             '' if meta.get('exact') else '  ⚠️ actual 与目标日不同日（源 id=%s）' % meta.get('source_id')))
    if meta.get('used_future'):
        print('  ⚠️ 链上没有「不晚于目标日」的 actual，退化为使用**较晚**日期（%s）' % meta.get('actual_date'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
