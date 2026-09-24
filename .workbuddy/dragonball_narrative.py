# -*- coding: utf-8 -*-
"""dragonball_narrative.py —— DRAGONBALL 融合 D 叙事层（篇1 反身性/脆弱性）。

把篇1 的「反身性四阶段 / 杠杆加速崩溃 / 盈亏同源」收敛成**报告风险提示文案**。
定位（蓝图 §二 D 级）：**定性叙事，不进方向/置信度打分**——只输出给报告阅读者看的
「当前市场处于反身性哪个阶段、风险点在哪」的提示，不参与任何机械判定。

判据来源：篇1 §1.6·B5「延迟反馈动力系统四阶段」+ §1.3「盈亏同源」+ 杠杆加速崩溃。
设计原则（沿用铁律）：
  - 纯函数、零网络零 IO；
  - 判据忠实原文，只做「阶段归类 + 文案拼装」这一层；
  - 无法判定的输入返回明确的「未定」文案，绝不静默给方向。

四阶段可观测代理（原文数学特征 → 可观测指标）：
  阶段1 初始稳健期（k<1）：价格温和、波动稳定        → 负反馈收敛，脆弱性低
  阶段2 正反馈放大期（k>1）：价格加速上涨 + 波动被压制 → 「看似稳健，实则脆弱」
  阶段3 脆弱性暴露期（分岔）：波动反转激增（突破拥挤阈值 ζ/η）→ 脆弱性达峰值
  阶段4 崩溃期（k<-1）：价格断崖下跌 + 波动飙升        → 负反馈主导、崩溃加速
"""

# 反身性四阶段定性文案（忠实原文，缩写成报告语气）
STAGES = {
    'stage1': {
        'name': '阶段1 · 初始稳健期',
        'k': 'k < 1（负反馈主导）',
        'feature': '资金流入规模小，预期与真实匹配，价格温和增长收敛于均衡，波动稳定',
        'risk': '低——系统处于负反馈收敛区间，无显著脆弱性积累',
        'advice': '正常持有，按关键位（55 线/中轨）纪律操作即可',
    },
    'stage2': {
        'name': '阶段2 · 正反馈放大期',
        'k': 'k > 1（正反馈主导）',
        'feature': '高夏普被广泛传播、资金涌入突破阈值；价格上涨加速、波动被压制下降',
        'risk': '中高——「看似稳健，实则脆弱」：涨速加快 + 波动下降是脆弱性积累的表象，非真实稳健',
        'advice': '不追高、警惕拥挤；关注波动率是否已到「压制→引爆」的转折',
    },
    'stage3': {
        'name': '阶段3 · 脆弱性暴露期（分岔）',
        'k': 'k 非线性反转',
        'feature': '资金突破拥挤阈值，波动从低位快速飙升；真实夏普急降、认知偏差巨大',
        'risk': '高——分岔点已现，脆弱性达峰值，一笔大额卖出即可能引发流动性枯竭',
        'advice': '收缩仓位、降低杠杆；把「波动反转」当作减仓信号而非抄底信号',
    },
    'stage4': {
        'name': '阶段4 · 崩溃期',
        'k': 'k < -1（负反馈主导）',
        'feature': '外部扰动打破认知幻觉，预期断崖下调、资金撤退叠加，波动飙升加速下跌',
        'risk': '极高——崩溃加速中，恢复时间大幅延长',
        'advice': '勿盲目抄底；等波动收敛、认知修正（T_rec 恢复）后再谈回补',
    },
}

# 盈亏同源 + 杠杆加速崩溃的固定提示（篇1 §1.3）
PROFIT_LOSS_SAME_SOURCE = (
    '盈亏同源：市场天然追逐高夏普资产，对持续上涨的追逐必然造成反身性、反身性又强化夏普，'
    '这一过程持续积累脆弱性——「找到风险最小、收益最确定的点然后加杠杆」的另一面，就是系统脆弱性。'
    '做空机制不完善的市场里，这种周期轮回是必然的。'
)


def vol_trend(closes, win=20):
    """波动趋势：近 win 日收益标准差 vs 前 win 日收益标准差。

    返回 'squeeze'（波动下降，阶段2 特征）/ 'stable'（持平）/ 'explode'（波动激增，阶段3 特征）。
    不足 2*win 根 → 返回 None（不猜）。
    阈值：波动放大 1.4 倍以上记 explode，收缩至 0.8 倍以下记 squeeze。
    """
    if not closes or len(closes) < 2 * win + 1:
        return None
    import statistics
    closes = list(closes)
    def _std(seg):
        if len(seg) < 2:
            return None
        rets = [(seg[i] - seg[i - 1]) / seg[i - 1] for i in range(1, len(seg))]
        return statistics.pstdev(rets)
    recent = _std(closes[-win:])
    prior = _std(closes[-2 * win:-win])
    if recent is None or prior is None or prior == 0:
        return None
    ratio = recent / prior
    if ratio < 0.8:
        return 'squeeze'
    if ratio > 1.4:
        return 'explode'
    return 'stable'


def price_trend(closes, ma_win=20):
    """价格趋势：近端涨速 vs 远端涨速，识别加速/崩溃。

    返回 'accel_up'（加速上涨）/ 'up'（温和上涨）/ 'flat' / 'down' / 'crash'（加速下跌）。
    不足 ma_win+1 根 → None。
    """
    if not closes or len(closes) < ma_win + 2:
        return None
    closes = list(closes)
    recent = (closes[-1] - closes[-ma_win]) / closes[-ma_win] * 100
    prior = (closes[-ma_win] - closes[-2 * ma_win]) / closes[-2 * ma_win] * 100 if len(closes) >= 2 * ma_win else recent
    if recent < -5 and prior < -5 and recent < prior:
        return 'crash'
    if recent > 2 and prior > 0 and recent > prior * 1.5:
        return 'accel_up'
    if recent > 0.5:
        return 'up'
    if recent < -0.5:
        return 'down'
    return 'flat'


def reflexivity_stage(pt, vt):
    """反身性四阶段归类（可观测代理 → 阶段 key）。

    输入 pt = price_trend() 结果，vt = vol_trend() 结果。
    返回 stage key（'stage1'..'stage4'）或 None（信息不足）。
    判据（忠实原文数学特征）：
      crash          → 阶段4（价格断崖 + 负反馈）
      vt='explode'   → 阶段3（波动反转激增 = 分岔）
      accel_up 且 vt∈{'squeeze','stable'} → 阶段2（加速 + 波动压制 = 正反馈）
      其余（温和/平坦）→ 阶段1（负反馈收敛）
    """
    if pt is None or vt is None:
        return None
    if pt == 'crash':
        return 'stage4'
    if vt == 'explode':
        return 'stage3'
    if pt == 'accel_up' and vt in ('squeeze', 'stable'):
        return 'stage2'
    return 'stage1'


def build_risk_note(stage, tail_xi=None, main_up=False, conc_high=False):
    """生成报告「风险提示」文案（D 叙事层，定性、不进打分）。

    输入：
      stage    : reflexivity_stage() 的阶段 key（None 则返回未定提示）
      tail_xi  : 尾指数 ξ（None 不引用；ξ 越小尾越厚、脆弱性越强，篇1 §B2）
      main_up  : bool —— 是否处于主涨段（篇5，正反馈的加速载体）
      conc_high: bool —— 集中度是否偏高（篇2 抱团，脆弱性积累的土壤）

    返回：多行文案字符串（报告可直接引用）。
    """
    if stage is None or stage not in STAGES:
        return '风险提示：反身性阶段暂无法判定（数据不足），维持既有关键位纪律。'
    s = STAGES[stage]
    lines = [f"风险提示（DRAGONBALL 反身性视角）：{s['name']}（{s['k']}）"]
    lines.append(f"　特征：{s['feature']}")
    lines.append(f"　风险：{s['risk']}")
    lines.append(f"　应对：{s['advice']}")
    extras = []
    if stage in ('stage2', 'stage3') and tail_xi is not None:
        extras.append('尾指数 ξ=%.4f（V_tail=%.2f）——%s' % (
            tail_xi, 1.0 / tail_xi if tail_xi > 0 else float('inf'),
            '尾部偏厚，极端损失概率偏高' if tail_xi < 0.6 else '尾部适中'))
    if main_up:
        extras.append('当前处于主涨段，正反馈的加速载体仍在，脆弱性在「加速」中持续积累')
    if conc_high:
        extras.append('资金集中度偏高（抱团），属脆弱性积累的典型土壤，警惕「切换必跌」')
    if extras:
        lines.append('　量化佐证：' + '；'.join(extras))
    lines.append('　注：本条为定性叙事，不参与方向/置信度打分。' + PROFIT_LOSS_SAME_SOURCE)
    return '\n'.join(lines)
