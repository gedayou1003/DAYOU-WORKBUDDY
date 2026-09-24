# -*- coding: utf-8 -*-
"""dragonball_signals.py —— DRAGONBALL 方法论融合 · P0 纯函数模块。

把 5 篇 T&J（现 DRAGONBALL）方法论文里的「可内化判据」收敛成**纯函数**：
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
