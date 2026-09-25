# -*- coding: utf-8 -*-
"""dragonball_signals.py —— DRAGONBALL 方法论融合 · P0 纯函数模块。

把 5 篇 DRAGONBALL 方法论文里的「可内化判据」收敛成**纯函数**：
每个函数只吃标量/序列，返回结构化结果，**零网络、零文件 IO、零副作用**，
可完全离线单元测试。判据严格忠实原文（篇4/篇3/篇5），边界处理见各函数 docstring。

设计原则（《DRAGONBALL_融合蓝图.md》§一）：
  - 只做「状态机/分类器」这一层，**不碰任何打分、不改引擎参数**；
  - 「稳定性」（MACD 六态）与「动能/背离」（现有 MACD 用法）**语义独立**，本模块字段不与现有字段混用；
  - 判据来源逐条标注（篇几 + 原文）。

已实现的 P0 融合点（对应蓝图 §三）：
  P0-1/2  classify_macd_state   极强/极弱六态分类 + 零轴金叉/死叉等价
  P0-3    build_ma55_grid       多级别 55 线网格
  P0-4    classify_break        刺破 / 有效跌破 语义分层
  P0-5    infer_transmission    极强传递性（有效突破本级 55 → 向上一级 55 运动）
  P0-6    classify_pullback     X 段 vs 带结构回踩

退出码/异常约定：本模块是**纯函数库**，不设进程退出码；判据无法满足时返回明确的
「未定/不适用」取值（如 'cross'、None），**绝不抛异常、绝不静默给默认方向**。
"""

# ============================================================================
# P0-1/2  极强/极弱六态分类器
# ============================================================================

# 六态判据（篇4 原文精确转写）：
#   极强：DIF ≥ 0  且 DEA ≤ 0  且 MACD > 0
#   强  ：DIF > DEA > 0       且 MACD > 0
#   中性偏强：0 > DIF > DEA    且 MACD > 0
#   中性偏弱：0 < DIF < DEA    且 MACD < 0
#   弱  ：DIF < DEA < 0       且 MACD < 0
#   极弱：DIF ≤ 0  且 DEA ≥ 0  且 MACD < 0
#
# 逻辑强化点（蓝图 §三 标注）：
#   1) MACD > 0 ⟺ DIF > DEA（标准 MACD 柱符号由 DIF-DEA 决定），
#      故实现只吃 dif/dea 两个值，不再引入「macd 柱」第三输入，
#      避免与 calc_tech.py 中 macd 柱可能用的 (DIF-DEA)*2 倍率定义冲突。
#   2) 六态完备：多头（DIF>DEA）按 {跨零轴 / 均在0上 / 均在0下} 三分，
#      空头（DIF<DEA）同理三分，无遗漏。
#   3) DIF == DEA（金叉/死叉点，柱=0）不属于任何六态 → 归 'cross'。
#   4) 极强/极弱用 ≥/≤（把「恰好在 0 轴」归给跨轴态），强/弱/中性用严格 >/<，忠实原文。


def classify_macd_state(dif, dea):
    """六态分类器。输入 DIF、DEA 两个浮点，返回 dict。

    返回：{
        'state': '极强'|'强'|'中性偏强'|'中性偏弱'|'弱'|'极弱'|'cross',
        'sign' : '+'|'-'|'0',      # 多头/空头/零柱
        'side' : '多头'|'空头'|'金叉死叉点',
    }
    「cross」= DIF==DEA 的金叉/死叉点，看次日确认，不强行归边。
    """
    if dif > dea:                       # MACD > 0，多头
        if dif >= 0 and dea <= 0:
            return {'state': '极强', 'sign': '+', 'side': '多头'}
        if dif > 0 and dea > 0:
            return {'state': '强', 'sign': '+', 'side': '多头'}
        return {'state': '中性偏强', 'sign': '+', 'side': '多头'}
    if dif < dea:                       # MACD < 0，空头
        if dif <= 0 and dea >= 0:
            return {'state': '极弱', 'sign': '-', 'side': '空头'}
        if dif > 0 and dea > 0:
            return {'state': '中性偏弱', 'sign': '-', 'side': '空头'}
        return {'state': '弱', 'sign': '-', 'side': '空头'}
    return {'state': 'cross', 'sign': '0', 'side': '金叉死叉点'}


def detect_zero_cross(dif, dea, prev_dif, prev_dea):
    """零轴金叉 / 零轴死叉（篇4：零轴金叉≡极强、零轴死叉≡极弱 的第二识别）。

    返回 'golden'（零轴金叉）/ 'dead'（零轴死叉）/ None（非零轴交叉）。
    判据：DIF 在本根与 DEA 交叉（金叉/死叉成立），且交叉发生点贴近 0 轴
    （即交叉后 DIF 与 DEA 分居 0 轴两侧，或 DIF 恰好穿越 0 轴）。
    简化口径（可复现）：金叉=prev_dif<=prev_dea 且 dif>dea；死叉反之。
    零轴判据：交叉后 (dif - 0) 与 (dea - 0) 异号，即「跨零轴」。
    """
    golden = prev_dif <= prev_dea and dif > dea
    dead = prev_dif >= prev_dea and dif < dea
    if golden and (dif * dea <= 0):      # 金叉且跨零轴（dif>=0>=dea 或 dif/dea 有一为0）
        return 'golden'
    if dead and (dif * dea <= 0):
        return 'dead'
    return None


# ============================================================================
# P0-3  多级别 55 线网格
# ============================================================================

def build_ma55_grid(closes_by_level):
    """多级别 55 线网格（篇4/篇5：每条 55 线 = 该级别多空分水岭）。

    输入：closes_by_level = {'15F': [..], '60F': [..], '日线': [..], ...}
          value 为该级别**按时间升序**的收盘价序列（list[float]）。
    返回：{'15F': ma55 或 None, ...}，不足 55 根 → None（不猜、不静默给数）。
    """
    grid = {}
    for level, closes in closes_by_level.items():
        closes = list(closes)
        if len(closes) >= 55:
            grid[level] = round(sum(closes[-55:]) / 55.0, 2)
        else:
            grid[level] = None
    return grid


# ============================================================================
# P0-4  刺破 / 有效跌破 语义分层
# ============================================================================

def classify_break(close, low, ma20, ma55):
    """中轨 vs 55 线的层次（篇4/5 综合）：刺破=预警，有效跌破=确认，破55=分水岭。

    输入：close 收盘价、low 当日最低（用于判「刺破」）、ma20（中轨近似）、ma55。
    返回四态之一（优先级从弱到强，取最先命中）：
      '有效破55线'   close < ma55                 —— 趋势分水岭失守
      '有效破中轨'   close < ma20（且 ≥ ma55）      —— 主涨特征解除候选
      '刺破中轨收回' low < ma20 <= close           —— 盘中跌破、收盘收回，仅预警
      '站上中轨'     其余（close >= ma20 且 low >= ma20）

    逻辑强化点（蓝图 §三）：原文「有效跌破」的判据是**收盘价**是否站回，
    不是盘中最低价；这是纠偏「跌破即转空」的关键 —— 单次收盘破中轨只是「解除候选」，
    不等于转空（转空还需 P1-9 的「二次跌破」确认）。
    """
    if close < ma55:
        return '有效破55线'
    if close < ma20:
        return '有效破中轨'
    if low < ma20 <= close:
        return '刺破中轨收回'
    return '站上中轨'


# ============================================================================
# P0-5  极强传递性
# ============================================================================

def infer_transmission(state, close, ma55_this, ma55_next):
    """极强传递性（篇4 特征3）：极强形态下有效突破本级 55 → 有向上一级 55 运动惯性。

    输入：state 本级别六态（classify_macd_state 的 'state'），close 现价，
          ma55_this 本级别 55 线，ma55_next 上一级别 55 线（None 表示无上一级）。
    返回：{'transmission': bool, 'target': 上一级 ma55 或 None}
    判据：state == '极强' 且 close > ma55_this（有效突破）→ 下一目标 = ma55_next。
    """
    if state == '极强' and ma55_this is not None and close > ma55_this:
        return {'transmission': True, 'target': ma55_next}
    return {'transmission': False, 'target': None}


# ============================================================================
# P0-6  X 段 vs 带结构回踩
# ============================================================================

def classify_pullback(has_structure_n1, is_main_up_n2):
    """X 段 vs 带结构回踩（篇3）。

    输入：
      has_structure_n1 : bool —— N+1 级别能否画出一段结构
        （「带结构」三要素：顶分型 + 底分型 + 合并后至少 1 根 K 线；
          该布尔由上游 chan_signal 分型结果给出）。
      is_main_up_n2    : bool —— N+2 级别是否处于主涨段。

    返回：
      'X段'          N+2 主涨段 且 N+1 **没结构**（回踩向下分解到 N 级别即 X 段）
      '带结构回踩'   N+2 主涨段 且 N+1 **有结构**
      '非主涨段'     N+2 非主涨段 —— X 段只在主涨/主跌段出现，不适用

    逻辑强化点（蓝图 §三）：X 段核心判据是「**上一级别没结构**」，
    不是「本级别有没有结构」—— 这是原文反复强调、最易实现搞反的一点。
    本函数刻意让 has_structure_n1 指向「上一级别」，把容易搞反的语义钉死在接口上。
    """
    if not is_main_up_n2:
        return '非主涨段'
    return 'X段' if not has_structure_n1 else '带结构回踩'


# ============================================================================
# P1-8  主涨段判定（篇5 严格公式）
# ============================================================================

# 主涨段「低位」阈值：N 级别价格距 55 线 ≤ 该百分比视为「低位」（未大涨）。
# 篇5「低位出现结构后出现主涨段」的「低位」是可调参数，集中一处便于回测调优。
LOW_POSITION_THRESHOLD = 5.0


def detect_main_up(n2_state, n2_zero_cross, bis, n_price_ma55_dist=None):
    """篇5 主涨段判定（严格公式，落地版，线段计数）。

    原文：N+2 级别 MACD 进入极强（或金叉）→ N 级别在「低位出现结构」后出现主涨段；
          低位结构一般是「第三段或第五段上涨」，极度强势时第一段即可（概率偏小）。

    落地判据（三个可观测条件，缺一不可）：
      1. N+2 触发：macd_state == '极强' **或** 零轴金叉（篇5「极强状态，或金叉状态」的「或」=并集）。
      2. N 级别当前上涨：最近一个**线段**方向 up（「出现结构」= 已走出上涨线段）。
      3. N 级别低位：价格距 55 线 ≤ LOW_POSITION_THRESHOLD%（未大涨）。

    段计数：up_segment = 全序列「上涨**线段**数」（用 divide_segments 把笔合成线段；
    篇5 的「第三/五段上涨」的「段」是**线段**，非篇3 的「带结构段=笔」——两者粒度不同）。
    ⚠️ 口径边界：up_segment 是「全序列」上涨线段数（随数据起点漂移），精确的
    「从大级别底部起的第几段」需跨级别底部识别，暂未接；up_segment 作描述字段不参与布尔判定。

    输入：
      n2_state          : str —— N+2 级别 MACD 六态（classify_macd_state 的 'state'）
      n2_zero_cross     : str|None —— N+2 级别零轴交叉（detect_zero_cross，'golden'/'dead'/None）
      bis               : list[dict] —— N 级别笔列表（每笔含 bi_type/start_price/end_price，升序）
      n_price_ma55_dist : float|None —— N 级别价格距 55 线距离%（正=上方）；None=不判位置

    返回 dict：is_main_up / trigger / currently_up / low_position / up_segment / n_segments
    """
    trigger = (n2_state == '极强') or (n2_zero_cross == 'golden')
    segs = divide_segments(bis)
    up_segment = sum(1 for s in segs if s['direction'] == 'up')
    currently_up = bool(segs) and segs[-1]['direction'] == 'up'
    low_position = (n_price_ma55_dist is None) or (n_price_ma55_dist <= LOW_POSITION_THRESHOLD)

    return {
        'is_main_up': trigger and currently_up and low_position,
        'trigger': trigger,
        'currently_up': currently_up,
        'low_position': low_position,
        'up_segment': up_segment,
        'n_segments': len(segs),
    }


# ============================================================================
# 缠论线段划分（特征序列分型法）
# ============================================================================

def divide_segments(bis):
    """缠论线段划分（特征序列分型法，简化版）。

    把「笔」（chan_signal 的 bi_list）合成「线段」——线段是比笔更大的结构，
    一个线段由至少 3 笔构成。篇5 的「第三段/第五段上涨」的「段」指的是**线段**，
    不是篇3 的「带结构段=笔」（两者粒度不同）。

    输入 bis：按时间升序的笔列表，每笔至少含：
      bi_type     : 'up'/'down'
      start_price : 笔起点价（up 笔=低点，down 笔=高点）
      end_price   : 笔终点价（up 笔=高点，down 笔=低点）
      start_date / end_date : 起止时间（可选）

    输出 segments：每段 {direction, start_price, end_price, start_date, end_date, bi_count}

    规则（缠中说禅原文简化，⚠️ 不含「特征序列缺口」的特殊处理）：
      1. 线段方向 = 第一笔方向；
      2. 特征序列 = 线段内与方向**相反**的笔（向上段的特征序列是其中的向下笔，反之亦然）；
      3. 向上段：特征序列出现「顶分型」（中间元素高点最高 **且** 低点最高）→ 线段结束于
         分型极点（顶分型的最高点）；向下段对称找「底分型」；
      4. 分型的中间元素作为下一线段的第一笔（其方向即新线段方向）。

    缺口边界：缠论标准里「特征序列第一、二元素之间存在缺口」时，线段结束条件更严
    （需等反向特征序列分型确认）。本简化版不区分缺口，遇到缺口场景可能比标准更早判结束
    —— 对「第几段上涨」的计数用途影响有限，已明确标注。
    """
    if not bis or len(bis) < 3:
        return []

    segments = []
    seg_bis = [bis[0]]
    direction = bis[0]['bi_type']

    def _end_price_of(seg, direction):
        # 段终点：向上段取段内最高（最后一笔终点或分型极点），向下段取最低
        if direction == 'up':
            return max(b['end_price'] for b in seg)
        return min(b['end_price'] for b in seg)

    for bi in bis[1:]:
        seg_bis.append(bi)
        feature = [b for b in seg_bis if b['bi_type'] != direction]
        if len(feature) < 3:
            continue
        f1, f2, f3 = feature[-3], feature[-2], feature[-1]
        if direction == 'up':
            # 特征序列是 down 笔：顶分型 = f2 高点(start)最高 且 低点(end)最高
            broken = (f2['start_price'] > f1['start_price'] and
                      f2['start_price'] > f3['start_price'] and
                      f2['end_price'] > f1['end_price'] and
                      f2['end_price'] > f3['end_price'])
            pole = f2['start_price']
        else:
            # 特征序列是 up 笔：底分型 = f2 低点(end)最低 且 高点(start)最低
            broken = (f2['end_price'] < f1['end_price'] and
                      f2['end_price'] < f3['end_price'] and
                      f2['start_price'] < f1['start_price'] and
                      f2['start_price'] < f3['start_price'])
            pole = f2['end_price']
        if not broken:
            continue
        # 线段结束于 f2（分型中间元素）；f2 之前的笔 + f2 的极点构成当前段
        idx_f2 = seg_bis.index(f2) if f2 in seg_bis else len(seg_bis) - 1
        cur = seg_bis[:idx_f2]          # f2 之前的笔
        head = seg_bis[0]
        segments.append({
            'direction': direction,
            'start_price': head['start_price'],
            'end_price': pole,
            'start_date': head.get('start_date'),
            'end_date': f2.get('start_date'),
            'bi_count': len(cur),
        })
        # 新线段从 f2 开始
        seg_bis = seg_bis[idx_f2:]
        direction = seg_bis[0]['bi_type']

    if seg_bis:
        head = seg_bis[0]
        segments.append({
            'direction': direction,
            'start_price': head['start_price'],
            'end_price': _end_price_of(seg_bis, direction),
            'start_date': head.get('start_date'),
            'end_date': seg_bis[-1].get('end_date'),
            'bi_count': len(seg_bis),
        })
    return segments


# ============================================================================
# P1-9  主涨特征解除的两路径状态机
# ============================================================================

def track_break(prev_state, close, ma20):
    """篇5 主涨特征解除后的两条演化路径（一步状态转移）。

    原文：有效跌破 N-1 中轨 → 主涨特征解除（**但不等于下跌**），一般两种演化：
      ① 反抽被中轨压制（弱势甚至被 N-2 中轨压制）；
      ② 反抽突破中轨（甚至金叉）→ 后续不管是否新高，**二次跌破**中轨（泛指最后一次
        有效跌破）→ 至少回踩 N-1 的 55 线，实现对 N 级别中轨的回踩。

    核心语义（蓝图原则）：**「解除 ≠ 下跌」，单次收盘跌破中轨只是解除候选，二次跌破才算数。**

    输入：
      prev_state : str —— 上一状态（'维持'/'解除'/'反抽突破'/'二次跌破'，首日传 '维持'）
      close      : float —— 当日收盘价
      ma20       : float —— 中轨（MA20 近似）

    返回 (new_state, verdict)：
      '维持'    ：主涨特征维持（收盘在中轨上方）
      '解除'    ：首次有效跌破中轨（主涨特征解除，不等于下跌）
      '反抽突破'：解除后反抽突破中轨（路径②）
      '二次跌破'：反抽突破后再次跌破中轨（回调升级确认，至少回踩 55 线）
    """
    if close < ma20:  # 收盘在中轨下方
        if prev_state in ('反抽突破', '二次跌破'):
            return '二次跌破', '二次跌破中轨确认，回调升级，至少回踩 55 线'
        if prev_state == '解除':
            return '解除', '中轨下方盘整（反抽未突破，路径①被压制）'
        return '解除', '首次有效跌破中轨，主涨特征解除（不等于下跌）'
    else:  # 收盘在中轨上方
        if prev_state == '解除':
            return '反抽突破', '反抽突破中轨（路径②，可能伴随金叉）'
        return '维持', '主涨特征维持'


# ============================================================================
# P2-12  尾指数（Hill 估计量，无需 scipy）
# ============================================================================

def hill_tail_index(returns, k=None):
    """Hill 估计量估厚尾指数 ξ（篇1 尾部脆弱性 V_tail = 1/ξ）。

    篇1：尾部脆弱性用广义帕累托分布（GPD）尾指数 ξ 刻画 —— ξ>0 厚尾，ξ 越小尾越厚、
    极端损失概率越高、脆弱性越强，V_tail = 1/ξ。Hill 估计量是 ξ 的无参估计，
    只依赖 numpy（项目 venv 无 scipy，故不用 scipy.stats.genpareto）。

    输入：
      returns : list[float] —— 收益率序列（负值=下跌）
      k       : int|None —— 用于估计的极端观测数；None 默认 max(10, 10% 样本)

    返回 dict：xi / v_tail / n（损失样本数）/ k（用到的尾观测数）/ note（异常说明）

    口径：对「损失尾」（下跌）估 ξ —— 损失 = -return（只取下跌日，正数）。
    """
    import math
    losses = sorted([-r for r in returns if r < 0], reverse=True)  # 降序：最大损失在前
    n = len(losses)
    if n < 10:
        return {'xi': None, 'v_tail': None, 'n': n, 'k': 0, 'note': '下跌样本不足 10'}
    k = k or max(10, int(n * 0.1))
    k = min(k, n - 1)
    if k < 2:
        return {'xi': None, 'v_tail': None, 'n': n, 'k': k, 'note': '尾观测数不足'}
    threshold = losses[k]  # 第 k+1 大损失 = 阈值
    xi = sum(math.log(losses[i]) - math.log(threshold) for i in range(k)) / k
    xi = max(xi, 1e-6)  # 防 0/负 → 除零
    return {'xi': round(xi, 4), 'v_tail': round(1.0 / xi, 4), 'n': n, 'k': k}


# ============================================================================
# P2-10  双级差体系 B：双日/双周聚合
# ============================================================================

def aggregate_double(rows):
    """把日线/周线每 2 根聚合为「双日/双周」（篇4 体系 B 的 2 倍级差）。

    篇4 体系 B：1F-5F-30F-120F-双日-双周。「双日」= 2 根日线合并、「双周」= 2 根周线合并，
    标准接口不直接给这两个周期，故从日线/周线聚合。

    输入 rows：升序 OHLC 序列，每根 {date, open, close, high, low, vol}（vol 可缺省）
    输出：每 2 根合并为 1 根（最后若剩单根则丢弃）——
      date  = 第 2 根 date；open = 第 1 根 open；close = 第 2 根 close；
      high  = max(两根 high)；low = min(两根 low)；vol = 两根 vol 之和。
    """
    out = []
    for i in range(0, len(rows) - 1, 2):
        a, b = rows[i], rows[i + 1]
        def _f(v):
            return v if v is not None else 0
        out.append({
            'date': b.get('date'),
            'open': _f(a.get('open')),
            'close': _f(b.get('close')),
            'high': max(_f(a.get('high')), _f(b.get('high'))),
            'low': min(_f(a.get('low')), _f(b.get('low'))),
            'vol': _f(a.get('vol')) + _f(b.get('vol')),
        })
    return out


# ============================================================================
# P2-11  集中度 Σwi²（抱团度量）
# ============================================================================

def concentration(weights):
    """集中度 Σwi²（篇2 詹森不等式里的 E[X]=Σwi²）。

    篇2：把资金权重视为概率分布，E[X]=Σwi² 是「资金集中度」的数学表达——
    分散行情 E[X]=1/n→0，主线集中 E[X]=1/k（k≪n）越大。Σwi² 越大 = 抱团越明显。

    输入 weights：权重列表（如各行业成交额占比，不必归一化，内部会归一）
    输出 dict：concentration（Σwi²，∈[1/n,1]）/ n / max_weight / hhi（赫芬达尔指数，=Σwi²）
    """
    if not weights:
        return {'concentration': None, 'n': 0, 'max_weight': None, 'hhi': None}
    total = sum(weights)
    if total <= 0:
        return {'concentration': None, 'n': len(weights), 'max_weight': None, 'hhi': None}
    w = [x / total for x in weights]
    conc = sum(x * x for x in w)
    return {
        'concentration': round(conc, 6),
        'hhi': round(conc, 6),
        'n': len(w),
        'max_weight': round(max(w), 6),
    }
