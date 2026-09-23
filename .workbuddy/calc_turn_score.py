# -*- coding: utf-8 -*-
"""calc_turn_score.py —— 「变盘倾向分」独立计算器（OBS-2 专项审视结论的实装）。

## 为什么单独成一个脚本

OBS-2 审视（2026-09-19）的根因结论是：

    剧本概率分配是「方向打分」的机械映射，不是独立的概率评估。

5 期实证里方向全判偏空 → 剧本 A（偏空路径）概率就全部最高，且 A 的概率基本是方向总分的
单调函数；C（反向/突破路径）概率 = `100 − A − B` 的**被动余数**。
于是当实际走「放量突破」时，主导剧本必然落在名义非最高的 C 上。

修法是**把概率层与方向层解耦**：方向分一个都不动，另起一个「变盘倾向分」专门承接
方向层用不到的三个信号（短端背离 / 量能前兆 / 带宽收口），**只调剧本概率、不改方向标签**。

单独成脚本而不是写进 `forecast_analyze.py`，是为了让它：
  · 可**独立回归**（不进主链也能测）；
  · 阈值**集中在一处**，改映射参数不用碰主链；
  · 每次计算都**逐因子打印依据**，报告里能直接引用（避免"算了个分但说不出为什么"）。

## 三因子（规则 v5 · OBS-2 审视结论 §三）

| # | 因子 | 判据 | 分 |
|---|---|---|---|
| 1 | **短端背离** | 15F/30F/60F 中 **≥2 个**进多头区（DIF 向上）**且**长端（日线）偏空 | +1 |
| 2 | **量能前兆** | 缩量至近期极值（**5 日新低**）**或**放量站上关键位 | +1 |
| 3 | **带宽收口** | 15F BOLL 带宽 **< 1%**（极度收口） | +1 |

**刻意不做的事**：变盘倾向分**不进方向分**。这三分说明的是「变盘概率上升」，
而**不是「变盘方向」** —— 拿它去改方向标签就是把「即将变盘」误读成「看多/看空」，
正是 OBS-3 记录的那类误判（把 0.86% 收口按四级别全看空计 -1）。

## 映射（只调概率）

    0 分  → 维持方向强度映射（= 改前行为，保证可回滚）
    1 分  → A −5pct / B +2pct / C +3pct
    2 分  → A −8pct / B +3pct / C +5pct
    ≥3 分 → A −10pct / B +3pct / C +7pct

映射后**归一化到 100**（四舍五入到整数），并**保底**：每档 ≥ 5pct，
避免极端参数把某档压成 0 —— 概率为 0 的剧本等于宣称"不可能"，超出本模型的能力。

## 用法

    $PY .workbuddy/calc_turn_score.py --payload .workbuddy/payload_YYYY-MM-DD_TIER.json
    $PY .workbuddy/calc_turn_score.py --selftest          # 内置自检（不读外部文件）
    $PY .workbuddy/calc_turn_score.py --payload X --base-a 40 --base-b 35 --base-c 25

退出码：0 = 算出来了 · 1 = 输入不足/读不动（**不猜、不给默认分**）· 2 = 算出来了但有降级
（如量能数据缺失 → 该因子按 0 计并明确标注）
"""
import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

# --- 阈值（集中一处，改参数不用碰主链）-------------------------------------
BAND_COLLAPSE_PCT = 1.0      # 15F 带宽 < 1% → 极度收口
SHORT_TERM_LEVELS = ('15F', '30F', '60F')
SHORT_TERM_NEED = 2          # 短端需 ≥2 个 DIF 向上
MIN_SCENARIO_PCT = 5         # 每档概率保底
MAPPING = {                  # 变盘倾向分 → (A 调整, B 调整, C 调整) 单位 pct
    0: (0, 0, 0),
    1: (-5, +2, +3),
    2: (-8, +3, +5),
    3: (-10, +3, +7),
}


def pick(d, *keys, default=None):
    """按多个候选键取第一个非 None 值（payload 的键名跨版本会有出入）"""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def parse_pct(text):
    """从 '82%' / 82 / '82.5' 里取出数字；取不到返回 None（**不猜**）"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = re.search(r'(-?\d+(?:\.\d+)?)', str(text))
    return float(m.group(1)) if m else None


def parse_macd_from_text(text):
    """从自然语言 MACD 描述里解析各周期 DIF 的「值 + 方向」。

    为什么要解析文本（2026-09-23 实装时发现）：
      payload 的 `forecast.record.evidence` **不是结构化字段**，而是四段自然语言
      （`engineB` / `boll` / `macd` / `overnight`）。所以「取不到就计 0 + 降级」
      虽然**没瞎猜**（这是对的），但**一个因子都算不出来 = 实装等于没装**。

    真实数据长这样（今日 `macd_factor` 字段）：

        日线 DIF **0.20**（前值 -1.53，**向上**，且已**上穿零轴**）…… 9 月以来首次转正
        60F DIF **向下**（13.35 → 12.54，仍处多头区 gap +1.91）
        30F DIF 向下（空头区 gap -3.77）
        15F DIF **向下**（-0.54 → -0.82，空头区 gap -2.53）
        5F DIF 向上（多头区 gap +0.16）

    解析**只认三类明确写法**，认不出就返回 None（宁可降级，不许猜）：
      1. `XXF/日线 DIF 向上/向下`         → 只有方向
      2. `… DIF（a → b …）` 或 `（前值 a，**b**）` → 取 b 为当前值、a 为前值
      3. `日线 DIF **x**（前值 y`/`（y → x` → 同上

    返回 {级别: {'dif': cur|None, 'dif_prev': prev|None, 'dir': 'up'/'down'|None}}
    """
    out = {}
    if not isinstance(text, str) or not text:
        return out
    # 级别标记：日线 / 周线 / 120F / 60F / 30F / 15F / 5F
    levels = ('日线', '周线', '120F', '60F', '30F', '15F', '5F')
    # 只在「级别 … DIF …」的短窗口内取值，避免跨周期串味（文本里周期是连续罗列的）
    #
    # ⚠️ **必须遍历同一级别的所有出现位置并合并**（2026-09-23 踩坑）：
    # 单一 `re.search` 只取**第一处**。真实 payload 里同一级别常出现两次——
    # 一次在「指针句」里（`见 macd_factor 字段（日线 DIF 拐头向上…）`，只有方向没有数值），
    # 一次在正文数值段里（`日线 DIF …（1.80 → +0.20）`）。
    # 取第一处 → node 拿到 dir 但拿不到 dif/dif_prev → 下游「长端 MACD 不可得」→
    # **因子恒 0 却不是因为我们判对了，而是因为解析器半瞎**。
    # 合并规则：窗口按出现顺序累加，后出现的**数值**优先（数值段通常在后面、信息更全），
    # 但已解析到的值不被无值窗口覆盖。
    for i, lv in enumerate(levels):
        node = {}
        for m in re.finditer(re.escape(lv) + r'[^。；;]{0,120}?DIF[^。；;]{0,120}', text):
            seg = m.group(0)
            # 抹掉 markdown 粗体/斜体记号再匹配 —— 真实文本里数字常被 `**` 包住
            # （如「DIF 拐头向上 +1**（**-1.53 → +0.20**」），不抹掉就会把值连星号一起漏掉。
            seg_c = seg.replace('*', '')
            # 方向：后出现的窗口可**覆盖**前一个（离该级别主句更近）
            if re.search(r'向上|拐头向上|上行', seg_c):
                node['dir'] = 'up'
            elif re.search(r'向下|拐头向下|下行', seg_c):
                node['dir'] = 'down'
            # 值：优先「a → b」（先抹记号再匹配）
            mm = re.search(r'(-?\d+(?:\.\d+)?)\s*(?:→|->|—>|-->)\s*\+?(-?\d+(?:\.\d+)?)', seg_c)
            if mm:
                node['dif_prev'], node['dif'] = float(mm.group(1)), float(mm.group(2))
            else:
                # 「DIF **x**（前值 y」形式 —— 只在还没拿到值时补，避免覆盖上面更好的值
                if 'dif' not in node:
                    mm2 = re.search(r'DIF\s*(-?\d+(?:\.\d+)?)', seg_c)
                    if mm2:
                        node['dif'] = float(mm2.group(1))
                if 'dif_prev' not in node:
                    mm3 = re.search(r'前值\s*(-?\d+(?:\.\d+)?)', seg_c)
                    if mm3:
                        node['dif_prev'] = float(mm3.group(1))
        if node:
            out[lv] = node
    return out


def parse_band_from_text(text):
    """从 BOLL 描述里取 **15F 带宽**（%）。认不出返回 None。"""
    if not isinstance(text, str):
        return None
    m = re.search(r'15F[^。；;]{0,80}?带宽\s*\*{0,2}\s*(\d+(?:\.\d+)?)\s*%', text)
    if m:
        return float(m.group(1))
    m = re.search(r'带宽\s*\*{0,2}\s*(\d+(?:\.\d+)?)\s*%', text)
    return float(m.group(1)) if m else None


def _macd_text_richness(text):
    """估算一段 MACD 文本里「真正有多少可解析的 DIF 级别」。

    用来决定该不该去取 `macd_factor`：`evidence['macd']` 常常**不是**数据本身，
    而是一句**指针**（如 `'见 macd_factor 字段（日线 DIF 拐头向上且上穿零轴，取 +1）。'`，
    40 字），真正的 DIF 值在 `forecast.record.macd_factor`（369 字）。

    **踩坑记录（2026-09-23 实装时）**：最初写成
    `if not isinstance(evidence.get('macd'), (dict, str)): 取 macd_factor`，
    但指针句本身就是 `str` → 判断为 False → **fallback 永不触发**，
    于是「短端背离」永远算不出（因子恒 0），而脚本却报"数据不可得"——
    实装等于没装。教训：**判「有没有数据」要看可解析内容量，不能看类型**。
    """
    parsed = parse_macd_from_text(text)
    n_lv = len(parsed)
    n_val = sum(1 for v in parsed.values()
                if isinstance(v.get('dif'), (int, float)))
    return n_lv, n_val


def _merge_macd_sources(evidence, frec):
    """合并 `evidence['macd']` 与 `forecast.record.macd_factor` 两处 MACD 文本。

    返回给 `factor_short_end` 用的值（dict 直通 / str / ''）：
      · 任一处已是结构化 dict → 原样直通（最可信，无需解析）
      · 两处都是文本 → **拼接**（各自可能只有一半信息：指针句给方向、
        macd_factor 给数值），拼接后解析命中率最高
      · 都比较贫瘠 → 仍返回拼接结果，让下游按「解析为空」如实降级
    """
    cands = []
    ev_macd = evidence.get('macd')
    if isinstance(ev_macd, dict):
        return ev_macd
    if isinstance(ev_macd, str) and ev_macd.strip():
        cands.append(ev_macd)
    mf = pick(frec, 'macd_factor', 'macdFactor', default='')
    if isinstance(mf, dict):
        return mf
    if isinstance(mf, str) and mf.strip():
        cands.append(mf)
    if not cands:
        return ''
    if len(cands) == 1:
        return cands[0]
    # 两段文本都留：指针句在前（含主观方向定性），数值段在后（含 a → b）
    # —— 同一级别若两段都提到，parse_macd_from_text 以**后出现的窗口**为准，
    #    而数值段信息更全，所以把它放后面。
    ev_rich = _macd_text_richness(cands[0])
    mf_rich = _macd_text_richness(cands[1])
    if mf_rich[0] >= ev_rich[0] and mf_rich[1] >= ev_rich[1]:
        return '\n'.join(cands)
    return '\n'.join(reversed(cands))


def factor_short_end(evidence):
    """因子 1：短端背离 —— 15F/30F/60F 中 ≥2 个 DIF 向上，且长端（日线）**偏空**。

    为什么要求「长端偏空」：这个因子的价值在于捕捉**短端抢先转向、长端尚未跟上**的
    分歧状态（变盘前兆）。若长端也多，那就不是背离而是共振，方向分明，不需要"变盘倾向"。

    ⚠️ **「长端偏空」的判据（2026-09-23 钉死，此前规则原文未明确）**
    ---------------------------------------------------------------
    规则 v5 只写了「长端偏空」，但「偏空」有两种读法，取错会导致本因子含义漂移：

      · 读法 A：**DIF 下行**（`cur < prev`）—— 动能边际转弱
      · 读法 B：**DIF 在零轴下方**（`cur < 0`）—— 处空头区

    **采用 A ∨ B（任一成立即算偏空）**，理由是两者都意味着"长端不站在多头一侧"：
      · 只看 A：日线 DIF 在零轴上方但正在回落（如 1.00→0.20）→ 长端动能转弱、短端抢跑，
        这正是最典型的变盘前兆，**漏掉它等于漏掉本因子的主要场景**；
      · 只看 B：日线 DIF 已转正（如 -1.53→+0.20）但绝对位置仍在零轴上方 —— 此时长端
        明确偏多，本因子不该再算"背离"，否则会把"长短端共振向上"误判成变盘。
    故 A ∨ B：**只要长端没有"正在向上"或"已在零轴上方且向上"，就认为是偏空**。
    """
    macd = pick(evidence, 'macd', 'MACD', default={}) or {}
    if isinstance(macd, str):
        macd = parse_macd_from_text(macd)
    if not isinstance(macd, dict):
        return 0, 'MACD 数据非字典且无法解析，无法判定', False
    if not macd:
        return 0, 'MACD 数据解析后为空（文本里认不出「XX DIF 向上/向下」或「a → b」写法）→ 本因子计 0（不猜）', False


    up, seen, detail = 0, [], []
    for lv in SHORT_TERM_LEVELS:
        node = macd.get(lv) or macd.get(lv.replace('F', ''))
        if not isinstance(node, dict):
            continue
        # payload 里常见两种写法：显式 dir 字段，或 prev/cur 两个值
        d = node.get('dif_dir') or node.get('dir')
        if d in ('up', '向上', 'rising', True):
            up += 1
            seen.append(lv)
            detail.append('%s DIF 向上' % lv)
        elif d in ('down', '向下', 'falling', False):
            seen.append(lv)
            detail.append('%s DIF 向下' % lv)
        else:
            cur, prev = pick(node, 'dif', 'cur'), pick(node, 'dif_prev', 'prev')
            if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
                seen.append(lv)
                if cur > prev:
                    up += 1
                    detail.append('%s DIF 向上(%.2f→%.2f)' % (lv, prev, cur))
                else:
                    detail.append('%s DIF 向下(%.2f→%.2f)' % (lv, prev, cur))

    long_node = macd.get('日线') or macd.get('D') or macd.get('daily')
    long_bear = None
    if isinstance(long_node, dict):
        cur, prev = pick(long_node, 'dif', 'cur'), pick(long_node, 'dif_prev', 'prev')
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            bear_by_trend = cur < prev          # 读法 A：DIF 下行
            bear_by_zone = cur < 0              # 读法 B：DIF 在零轴下方
            long_bear = bear_by_trend or bear_by_zone
            long_reason = '日线 DIF %.2f→%.2f（%s；零轴%s）' % (
                prev, cur,
                '下行' if bear_by_trend else '上行',
                '下方' if bear_by_zone else '上方')
    if long_bear is None:
        return 0, '长端（日线）MACD 不可得 → 无法确认「短端背离」，本因子计 0（不猜）', False

    hit = (up >= SHORT_TERM_NEED) and long_bear
    why = '%s；%s → 长端偏空=%s；短端向上 %d/%d 个（需 ≥%d）' % (
        '、'.join(detail) if detail else '短端 MACD 不可得', long_reason,
        long_bear, up, len(seen), SHORT_TERM_NEED)
    return (1 if hit else 0), why, hit


def factor_volume(evidence, vol_hist):
    """因子 2：量能前兆 —— 缩量至 5 日新低，或放量站上关键位。

    vol_hist：近若干日成交量序列（含当日，按时间升序）。给不出就计 0 并标注。
    """
    if not vol_hist or len(vol_hist) < 2:
        return 0, '量能序列缺失或不足（需 ≥2 个；建议给近 5 日含当日）→ 本因子计 0（不猜）', False
    cur = vol_hist[-1]
    window = vol_hist[-5:] if len(vol_hist) >= 5 else vol_hist
    if not isinstance(cur, (int, float)):
        return 0, '当日量能非数值（%r）→ 本因子计 0' % (cur,), False
    is_new_low = cur <= min(window)
    if is_new_low:
        return 1, '缩量至近 %d 日新低（当日 %.4g ≤ 窗口最小 %.4g）' % (
            len(window), cur, min(window)), True
    return 0, '量能未创近 %d 日新低（当日 %.4g vs 窗口最小 %.4g）' % (
        len(window), cur, min(window)), False


def factor_band(band_pct):
    """因子 3：带宽收口 —— 15F BOLL 带宽 < 1%"""
    if band_pct is None:
        return 0, '15F 带宽不可得 → 本因子计 0（不猜）', False
    hit = band_pct < BAND_COLLAPSE_PCT
    return (1 if hit else 0), '15F 带宽 %.2f%%（阈值 <%.1f%%）' % (
        band_pct, BAND_COLLAPSE_PCT), hit


def score(evidence, vol_hist=None, band_pct=None):
    """返回 (总分, 逐因子明细 list[(名称, 得分, 依据)], 是否降级)"""
    rows, degraded = [], False
    for name, fn in (('短端背离', lambda: factor_short_end(evidence)),
                     ('量能前兆', lambda: factor_volume(evidence, vol_hist)),
                     ('带宽收口', lambda: factor_band(band_pct))):
        try:
            s, why, _hit = fn()
        except Exception as e:                       # noqa: BLE001
            s, why, _ = 0, '计算异常（%s: %s）→ 计 0' % (type(e).__name__, e)
            degraded = True
        if '计 0（不猜）' in why:
            degraded = True                          # 数据缺失 → 降级（要如实报）
        rows.append((name, s, why))
    return sum(r[1] for r in rows), rows, degraded


def apply_mapping(a, b, c, turn):
    """按变盘倾向分调整三档概率，归一化到 100 且每档保底 ≥ MIN_SCENARIO_PCT"""
    da, db, dc = MAPPING[min(turn, max(MAPPING))]
    na, nb, nc = a + da, b + db, c + dc
    # 保底：先抬到下限，再从最大的一档里扣回来（不引入负概率）
    vals = [na, nb, nc]
    for i in range(3):
        if vals[i] < MIN_SCENARIO_PCT:
            short = MIN_SCENARIO_PCT - vals[i]
            j = max(range(3), key=lambda k: vals[k])
            vals[j] -= short
            vals[i] = MIN_SCENARIO_PCT
    total = sum(vals)
    if total <= 0:
        return a, b, c, '归一化失败（总额 ≤0）→ 维持原值'
    out = [int(round(v * 100.0 / total)) for v in vals]
    # 四舍五入会有 ±1~2 的零头，补给最大的一档
    diff = 100 - sum(out)
    if diff:
        j = max(range(3), key=lambda k: out[k])
        out[j] += diff
    note = 'A%+d / B%+d / C%+d → 归一化' % (da, db, dc) if turn else '0 分：维持方向强度映射（改前行为）'
    return out[0], out[1], out[2], note


def _selftest():
    """内置自检：三因子各自的命中/未命中 + 映射 + 保底 + 映射 0 分必须等于原值

    照 assertion-gate-hardening：**不只测「会算」，要测「该命中时命中、不该命中时不命中」**。
    """
    fails = []

    def ck(cond, msg):
        print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
        if not cond:
            fails.append(msg)

    print('A) 三因子 —— 命中')
    ev = {'macd': {'15F': {'dif_prev': -0.54, 'dif': -0.82},   # 向下
                   '30F': {'dif_dir': 'up'},
                   '60F': {'dif_dir': 'down'},
                   '日线': {'dif_prev': -1.53, 'dif': 0.20}}}  # 长端「向上」→ 不算偏空
    s, rows, _ = score(ev, vol_hist=[10, 9, 8, 7, 6], band_pct=0.83)
    ck(s == 2, '短端 1 个向上 + 长端向上 → 因子1 不命中；量能新低 +1、带宽 +1 → 总分 2（实测 %d）' % s)

    print('B) 三因子 —— 全部未命中')
    ev2 = {'macd': {'15F': {'dif_dir': 'down'}, '30F': {'dif_dir': 'down'},
                    '60F': {'dif_dir': 'down'}, '日线': {'dif_prev': 0.5, 'dif': 0.1}}}
    s2, rows2, d2 = score(ev2, vol_hist=[1, 2, 3, 4, 5], band_pct=3.2)
    ck(s2 == 0, '全不命中 → 0（实测 %d）' % s2)
    ck(d2 is False, '数据齐全时不得报降级')

    print('C) 短端背离命中（≥2 个向上 + 长端偏空）')
    ev3 = {'macd': {'15F': {'dif_dir': 'up'}, '30F': {'dif_dir': 'up'},
                    '60F': {'dif_dir': 'down'}, '日线': {'dif_prev': 0.5, 'dif': 0.1}}}
    s3, rows3, _ = score(ev3, vol_hist=[5, 4, 3, 2, 1], band_pct=5.0)
    f1 = dict((n, v) for n, v, _w in rows3)
    ck(f1['短端背离'] == 1, '短端 2/3 向上且长端向下 → 因子1 命中（实测 %s）' % f1['短端背离'])

    print('D) 数据缺失必须降级（不猜）')
    s4, rows4, d4 = score({}, vol_hist=None, band_pct=None)
    ck(s4 == 0, '全缺 → 0 分（实测 %d）' % s4)
    ck(d4 is True, '全缺 → 标记降级（不许静默按 0 当"无倾向"）')
    ck(all('计 0' in w for _n, _v, w in rows4), '三条依据都写明"计 0"及原因')

    print('E) 映射四档 + 归一化 + 保底')
    a, b, c, note = apply_mapping(40, 35, 25, 0)
    ck((a, b, c) == (40, 35, 25), '0 分必须**原值返回**（改前行为，保证可回滚）：实测 %s' % ((a, b, c),))
    ck('改前行为' in note, '0 分时注明"维持方向强度映射"')
    for t in (1, 2, 3):
        a, b, c, _ = apply_mapping(40, 35, 25, t)
        ck(a + b + c == 100, '%d 分 → 三档和 =100（实测 %d）' % (t, a + b + c))
        ck(c > 25, '%d 分 → C 档（反向/突破）概率必须**上升**（实测 %d > 25）' % (t, c))
        ck(a < 40, '%d 分 → A 档（延续方向）概率必须**下降**（实测 %d < 40）' % (t, a))
        ck(min(a, b, c) >= 5, '%d 分 → 无档位低于保底 5pct（实测 min=%d）' % (t, min(a, b, c)))

    print('F) 保底不能被突破（极端输入）')
    a, b, c, _ = apply_mapping(8, 5, 87, 3)
    ck(min(a, b, c) >= 5, '极端输入下仍无档位 <5pct（实测 %s）' % ((a, b, c),))
    ck(a + b + c == 100, '极端输入下仍归一化到 100（实测 %d）' % (a + b + c))

    print('G) 因子值域：任何情况下三因子合计 ≤3')
    s5, rows5, _ = score({'macd': {'15F': {'dif_dir': 'up'}, '30F': {'dif_dir': 'up'},
                                   '60F': {'dif_dir': 'up'}, '日线': {'dif_prev': 1, 'dif': 0}}},
                         vol_hist=[9, 9, 9, 9, 1], band_pct=0.2)
    ck(s5 <= 3, '总分上限 3（实测 %d）' % s5)
    ck(s5 == 3, '短端 3/3 向上 + 日线 DIF 下行(1→0, 仍在零轴上) → 按 A∨B 判长端偏空 → 因子1 命中，'
                '合计 3（实测 %d）' % s5)

    print('H) 「长端偏空」两种读法必须双向覆盖（2026-09-23 钉死的判据）')
    # 断言「因子 1 自身」而不是总分 —— 总分会被量能因子（vol 递减 → 5 日新低 +1）带偏，
    # 断言总分等于把两个因子的效果混在一起量，失败时分不清是哪个因子错了。
    def _f1(ev):
        return dict((n, v) for n, v, _w in score(ev, vol_hist=[9, 9, 9, 9, 9], band_pct=9.9)[1])['短端背离']

    short_up = {'15F': {'dif_dir': 'up'}, '30F': {'dif_dir': 'up'}, '60F': {'dif_dir': 'down'}}
    # H1 读法 A：DIF 下行、但在零轴上方 → 算偏空（动能转弱，典型变盘前兆）
    ck(_f1({'macd': dict(short_up, **{'日线': {'dif_prev': 1.00, 'dif': 0.20}})}) == 1,
       '长端 DIF 下行但在零轴上方 → 因子1 **命中**（读法 A）')
    # H2 读法 B：DIF 上行、但仍在零轴下方 → 也算偏空（处空头区）
    ck(_f1({'macd': dict(short_up, **{'日线': {'dif_prev': -2.00, 'dif': -1.00}})}) == 1,
       '长端 DIF 上行但仍在零轴下方 → 因子1 **命中**（读法 B）')
    # H3 双向都不成立：DIF 上行 + 已在零轴上方 → 长端明确偏多 → **不命中**
    ck(_f1({'macd': dict(short_up, **{'日线': {'dif_prev': -1.53, 'dif': 0.20}})}) == 0,
       '长端 DIF 上行且已上零轴 → 明确偏多 → 因子1 **不命中**')
    # H4 短端不足 2 个（即便长端偏空也不命中）—— 防「只看长端就加分」
    ck(_f1({'macd': dict({'15F': {'dif_dir': 'up'}, '30F': {'dif_dir': 'down'},
                          '60F': {'dif_dir': 'down'}},
                         **{'日线': {'dif_prev': 1.0, 'dif': 0.1}})}) == 0,
       '短端仅 1 个向上（<2）→ 即便长端偏空，因子1 也**不命中**')


    print('I) 文本解析器（真实 payload 是自然语言，必须能抽出来）')
    # 夹具取自 2026-09-23 午间 payload 的 macd_factor / boll 原文片段
    txt = ('**日线 DIF 拐头向上 +1**（**-1.53 → +0.20**，单日 +1.73，**且上穿零轴**）；'
           '60F DIF **向下**（13.35 → 12.54，仍处多头区 gap +1.91）；'
           '30F DIF 向下（空头区 gap -3.77）；'
           '15F DIF **向下**（-0.54 → -0.82，空头区 gap -2.53）；'
           '5F DIF 向上（多头区 gap +0.16）。')
    pm = parse_macd_from_text(txt)
    ck(set(SHORT_TERM_LEVELS) <= set(pm), '15F/30F/60F 三级都解析出来了（实测 %s）' % sorted(pm))
    ck(pm.get('60F', {}).get('dir') == 'down', '60F 方向 = down')
    ck(abs(pm.get('15F', {}).get('dif_prev', 0) - (-0.54)) < 1e-9, '15F 前值 = -0.54')
    ck(abs(pm.get('15F', {}).get('dif', 0) - (-0.82)) < 1e-9, '15F 当前值 = -0.82')
    ck(pm.get('日线', {}).get('dir') == 'up', '日线方向 = up')
    ck(abs(pm.get('日线', {}).get('dif', 0) - 0.20) < 1e-9, '日线当前值 = +0.20')
    ck(parse_band_from_text('15F 中轨 3950.25 **下方**（**看空 81%**，带宽 **0.83% 极度收口**）') == 0.83,
       'boll 文本里抽出 15F 带宽 0.83')
    ck(parse_band_from_text('60F 中轨 3919.87 上方（看多 82%，带宽 3.03% 开口）') == 3.03,
       '无 15F 前缀时也能取到带宽（3.03）')
    ck(parse_band_from_text('今天没有带宽字样') is None, '认不出 → 返回 None（不许猜 0 或 50）')
    ck(parse_macd_from_text('') == {}, '空文本 → 空字典，不报异常')

    # I2) 同一级别出现多次必须**合并**（2026-09-23 踩坑：单次 re.search 只取第一处）
    #     真实场景：指针句先提到「日线 DIF 拐头向上」（无值），正文数值段后提到
    #     「日线 DIF（1.80 → +0.20）」。取第一处 → 只有 dir 没有值 → 下游判「长端不可得」，
    #     因子恒 0 却**看起来像"判对了"**，是比直接报错更危险的静默错误。
    twice = ('见 macd_factor 字段（日线 DIF 拐头向上且上穿零轴，取 +1）。\n'
             '**日线 DIF 拐头向上 +1**（**1.80 → +0.20**，且上穿零轴）；'
             '60F DIF **向下**（13.35 → 12.54）；30F DIF 向上（空头区 gap -3.77）；'
             '15F DIF **向上**（-0.54 → -0.82）。')
    pmt = parse_macd_from_text(twice)
    ck(isinstance(pmt.get('日线', {}).get('dif'), (int, float)),
       '同一级别出现两次 → **数值必须被合并进来**（改前单次 search 只取指针句 → dif 缺失，'
       '实测 %r）' % pmt.get('日线', {}).get('dif'))
    ck(abs(pmt.get('日线', {}).get('dif_prev', 0) - 1.80) < 1e-9,
       '前值取数值段的 1.80（实测 %r）' % pmt.get('日线', {}).get('dif_prev'))
    ck(abs(pmt.get('日线', {}).get('dif', 0) - 0.20) < 1e-9,
       '当前值取数值段的 +0.20（实测 %r）' % pmt.get('日线', {}).get('dif'))
    ck(pmt.get('日线', {}).get('dir') == 'up', '方向仍为 up')
    ck(pmt.get('30F', {}).get('dir') == 'up', '30F 方向 up（未被日线窗口串味）')
    ck(pmt.get('60F', {}).get('dir') == 'down', '60F 方向 down（未被串味）')

    print('K) 两处 MACD 文本合并（2026-09-23 实装踩坑的回归钉子）')
    # 真实情形：evidence['macd'] 是**指针句**（长度 40），真数据在 record.macd_factor（长度 369）。
    # 改前的 fallback 判类型 → 指针句也是 str → 永不触发 → 因子 1 恒 0。
    pointer = '见 macd_factor 字段（日线 DIF 拐头向上且上穿零轴，取 +1）。'
    real = ('**日线 DIF 拐头向上 +1**（**-1.53 → +0.20**，且上穿零轴）；'
            '60F DIF **向下**（13.35 → 12.54）；30F DIF 向下（空头区 gap -3.77）；'
            '15F DIF **向下**（-0.54 → -0.82）；5F DIF 向上。')
    ck(_macd_text_richness(pointer)[0] < _macd_text_richness(real)[0],
       '指针句的可解析级别数 (%d) 必须**少于**真数据 (%d) —— 这是"要不要 fallback"的判据'
       % (_macd_text_richness(pointer)[0], _macd_text_richness(real)[0]))
    merged = _merge_macd_sources({'macd': pointer}, {'macd_factor': real})
    ck(isinstance(merged, str) and real in merged,
       '合并结果必须**包含** macd_factor 全文（改前用「判类型」→ 指针句也是 str → 直接漏掉）')
    pm_k = parse_macd_from_text(merged)
    ck(set(SHORT_TERM_LEVELS) <= set(pm_k),
       '合并后短端三级都解析得出（实测 %s）—— 改前这里只有指针句 → 解析为空 → 因子恒 0' % sorted(pm_k))
    # 结构化 dict 必须直通，不许被文本合并逻辑吃掉
    struct = {'15F': {'dif_dir': 'up'}, '30F': {'dif_dir': 'up'},
              '60F': {'dif_dir': 'down'}, '日线': {'dif_prev': 1.0, 'dif': 0.1}}
    ck(_merge_macd_sources({'macd': struct}, {'macd_factor': '无关文本'}) is struct,
       'evidence["macd"] 已是 dict 时**原样直通**（结构化最可信，不参与合并）')
    ck(_merge_macd_sources({}, {'macd_factor': struct}) is struct,
       'evidence 无 macd 时，macd_factor 是 dict 也直通')
    ck(_merge_macd_sources({}, {}) == '', '两处都没有 → 返回空串（下游据此降级，不猜）')

    print('L) 合并后因子 1 必须真的能算出（端到端钉子）')
    ev_k = {'macd': _merge_macd_sources({'macd': pointer}, {'macd_factor': real})}
    f1k = dict((n, v) for n, v, _w in
               score(ev_k, vol_hist=[9, 9, 9, 9, 9], band_pct=9.9)[1])['短端背离']
    ck(f1k == 0, '今日短端 15F↓/30F↓/60F↓ 只有 0 个向上 → 因子1 不命中（实测 %s）' % f1k)
    # 反向：把短端真值改成 2 个向上，同一套合并逻辑必须能判命中
    # （只换 15F/30F 两行的方向，证明「不命中」不是因为解析不出来而恒 0）
    real_up2 = real.replace('30F DIF 向下', '30F DIF 向上').replace(
        '15F DIF **向下**', '15F DIF **向上**')
    ev_k2 = {'macd': _merge_macd_sources({'macd': pointer}, {'macd_factor': real_up2})}
    f1k2 = dict((n, v) for n, v, _w in
                score(ev_k2, vol_hist=[9, 9, 9, 9, 9], band_pct=9.9)[1])['短端背离']
    ck(f1k2 == 0,
       '长端已上零轴且向上（-1.53→+0.20）→ 明确偏多 → 即便短端 2/3 向上，因子1 仍**不命中**'
       '（实测 %s）' % f1k2)
    # 再来一组：短端 2 个向上 + 长端**下行**在零轴上方 → 必须命中
    real_bear = real.replace('30F DIF 向下', '30F DIF 向上').replace(
        '15F DIF **向下**', '15F DIF **向上**').replace(
        '-1.53 → +0.20', '1.80 → +0.20')
    ev_k3 = {'macd': _merge_macd_sources({'macd': pointer}, {'macd_factor': real_bear})}
    f1k3 = dict((n, v) for n, v, _w in
                score(ev_k3, vol_hist=[9, 9, 9, 9, 9], band_pct=9.9)[1])['短端背离']
    ck(f1k3 == 1,
       '短端 2/3 向上 + 长端 DIF 下行（1.80→+0.20，仍在零轴上）→ 因子1 **命中**'
       '（证明合并后解析完全可用，实测 %s）' % f1k3)

    print('J) 端到端：真实 payload 文本 → 因子（今日 9/23 实况）')
    ev_today = {'macd': txt,
                'boll': '现价 3938.08：15F 中轨 3950.25 **下方**（**看空 81%**，带宽 **0.83% 极度收口**）'}
    band_today = parse_band_from_text(ev_today['boll'])
    st, rowst, _ = score(ev_today, vol_hist=[5.2, 4.8, 4.6, 5.5, 4.41], band_pct=band_today)
    ft = dict((n, v) for n, v, _w in rowst)
    ck(ft['带宽收口'] == 1, '带宽 0.83%% <1%% → 因子3 命中（实测 %s）' % ft['带宽收口'])
    ck(ft['量能前兆'] == 1, '量能 4.41 为 5 日新低 → 因子2 命中（实测 %s）' % ft['量能前兆'])
    ck(ft['短端背离'] == 0, '今日短端 15F↓/30F↓/60F↓ 仅 0 个向上（<2）→ 因子1 **不命中**'
                           '（实测 %s）' % ft['短端背离'])
    ck(st == 2, '今日实况 = 2 分（实测 %d）' % st)

    print()
    print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='变盘倾向分（OBS-2 实装，只调剧本概率不改方向）')
    ap.add_argument('--payload', help='payload JSON（读 forecast.record.evidence 等）')
    ap.add_argument('--band-pct', type=float, help='15F BOLL 带宽（%%）')
    ap.add_argument('--vol', help='近几日成交量，逗号分隔（含当日，时间升序）')
    ap.add_argument('--base-a', type=int, default=None, help='改前 A 档概率')
    ap.add_argument('--base-b', type=int, default=None, help='改前 B 档概率')
    ap.add_argument('--base-c', type=int, default=None, help='改前 C 档概率')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出（供主链消费）')
    ap.add_argument('--selftest', action='store_true', help='跑内置自检后退出')
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()

    evidence, vol_hist = {}, None
    if a.vol:
        try:
            vol_hist = [float(x) for x in a.vol.split(',') if x.strip()]
        except ValueError as e:
            sys.stderr.write('[FAIL] --vol 解析失败：%s\n' % e)
            return 1
    if a.payload:
        if not os.path.isfile(a.payload):
            sys.stderr.write('[FAIL] payload 不存在：%s\n' % a.payload)
            return 1
        try:
            d = json.load(open(a.payload, encoding='utf-8'))
        except Exception as e:                       # noqa: BLE001
            sys.stderr.write('[FAIL] payload 读不动（%s: %s）—— 不猜，直接失败\n'
                             % (type(e).__name__, e))
            return 1
        frec = pick(pick(d, 'forecast', default={}), 'record', default={}) or {}
        # evidence 是四段自然语言（engineB / boll / macd / overnight），不是结构化字段。
        # 这里把可解析的部分抽出来喂给因子；抽不出的部分保持缺失（→ 降级，不猜）。
        raw = pick(frec, 'evidence', default={}) or {}
        evidence = dict(raw) if isinstance(raw, dict) else {'macd': raw}
        evidence['macd'] = _merge_macd_sources(evidence, frec)
        if a.band_pct is None:
            a.band_pct = parse_band_from_text(str(pick(evidence, 'boll', default='')))
        if vol_hist is None:
            m = pick(d, 'market', default={}) or {}
            v = pick(m, 'vol_hist', 'volume_hist')
            if isinstance(v, list) and all(isinstance(x, (int, float)) for x in v):
                vol_hist = v

    total, rows, degraded = score(evidence, vol_hist, a.band_pct)

    base = None
    if a.base_a is not None and a.base_b is not None and a.base_c is not None:
        a2, b2, c2, note = apply_mapping(a.base_a, a.base_b, a.base_c, total)
        base = (a.base_a, a.base_b, a.base_c)
        adj = (a2, b2, c2)
    else:
        note, adj = '未给 --base-a/b/c → 只报分，不做映射', None

    if a.json:
        print(json.dumps({
            'turn_score': total,
            'factors': [{'name': n, 'score': s, 'reason': w} for n, s, w in rows],
            'degraded': degraded,
            'base': base, 'adjusted': adj, 'note': note,
            'thresholds': {'band_collapse_pct': BAND_COLLAPSE_PCT,
                           'short_term_need': SHORT_TERM_NEED,
                           'min_scenario_pct': MIN_SCENARIO_PCT},
        }, ensure_ascii=False, indent=1))
    else:
        print('=' * 70)
        print('变盘倾向分（只调剧本概率，不改方向标签 —— OBS-2 实装）')
        print('=' * 70)
        for n, s, w in rows:
            print('  [%s] %-8s %s' % ('+' if s else ' ', n, w))
        print('  ' + '-' * 66)
        print('  变盘倾向分 = %d / 3' % total)
        if adj:
            print('  剧本概率：A/B/C = %d/%d/%d → **%d/%d/%d**（%s）'
                  % (base[0], base[1], base[2], adj[0], adj[1], adj[2], note))
        else:
            print('  %s' % note)
        if degraded:
            print('  ⚠️ 数据不全：缺失因子按 0 计（不是"无倾向"，是"不知道"）—— 报告须写明')
        print('=' * 70)

    return 2 if degraded else 0


if __name__ == '__main__':
    sys.exit(main())
