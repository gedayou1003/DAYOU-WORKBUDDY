# -*- coding: utf-8 -*-
"""显示层脱敏：把内部沿用的旧称呼统一改写成对外的「定调」（v5 因子语义名）。

对外名演进（三次用户指令）：
    2026-09-18  「DRAGON BALL模型」（旧对外名）
    2026-09-26①  「星球③」（代号，6a36aff）
    2026-09-26②  「定调」（隐掉代号，本版）
背景（2026-09-18 用户指令）：
    报告/图表等**对外可见**的产物中，不再出现该知识星球的真实名称。

为什么需要这个模块：
    改名分两层 ——
      · **生成链路**（脚本、文档、报告 md）已直接改写成「DRAGON BALL模型」；
      · **数据层**（forecast_chain.json / consensus_chain.json 里的
        `levels.*.label`、`signals`、`engine_reason` 等**历史原文**）按约定
        **保持不变**（改动会波及历史回测与链比对，且属刻意保留的数据映射）。
    于是出现一条泄漏路径：
        链数据原文 → gen_forecast_svg.py 渲染 → SVG → 内嵌进报告 HTML
    该路径会把旧称呼带到对外产物上。本模块即为**渲染边界的统一脱敏**，
    与数据层解耦：数据怎么存是一回事，渲染出去什么样是另一回事。

用法：
    from display_names import scrub
    text = scrub(text)          # 对任何即将写入 SVG/HTML 的字符串调用

设计约束：
    纯字符串替换、无外部依赖；`scrub` 对非字符串入参先转 str，None 安全。
"""
import re

# 中间态名称（真实名先统一收编到这里，再在 _RULES 末段映射为最终对外名「定调」）
DISPLAY_ALIAS = 'DRAGON BALL模型'
# 用于文件名 / 常量位置（不带中文，避免编码与路径问题）
DISPLAY_ALIAS_ASCII = 'DRAGON_BALL'

# 顺序敏感：长模式优先，避免 "Truth and Justice" 被 "TJ" 规则切碎。
# `(?<![A-Za-z_])TJ(?![A-Za-z_])` 的词边界保护用于：
#   - 不误伤内部标识符 `tj_bypass` / `compute_tj_bypass` / `backtest_tj_v2`（小写，本就不匹配）
#   - 不误伤 `TJ_RE` 之类的大写缩写变量名（前后有字母/下划线，不匹配）
_RULES = (
    (re.compile(r'TRUTH_AND_JUSTICE'), DISPLAY_ALIAS_ASCII),
    (re.compile(r'Truth and Justice'), DISPLAY_ALIAS),
    (re.compile(r'T\\&J'), DISPLAY_ALIAS),   # anonymize_report.py 里的转义写法
    (re.compile(r'T&J'), DISPLAY_ALIAS),
    (re.compile(r'(?<![A-Za-z_])TJ(?![A-Za-z_])'), DISPLAY_ALIAS),
    # 2026-09-26 第二轮用户指令：对外名从「星球③」代号进一步隐掉，统一为
    # v5 因子语义名「定调」（与报告/走势图一致）。数据层落链时可能已手写成
    # DRAGON BALL（非原名），一并收编为「定调」。
    # 顺序敏感：DRAGON BALL模型 先于 DRAGON BALL，避免「模型」残留。
    (re.compile(r'DRAGON BALL模型'), '定调'),
    (re.compile(r'DRAGON BALL'), '定调'),
    (re.compile(r'DRAGON_BALL'), '定调'),
)


def scrub(text):
    """把对外文本里的旧称呼改写为「DRAGON BALL模型」。None 原样返回 None。"""
    if text is None:
        return None
    s = str(text)
    for pat, rep in _RULES:
        s = pat.sub(rep, s)
    return s


def scrub_all(items):
    """对列表逐项脱敏（signals 之类的字符串数组）。"""
    return [scrub(x) for x in (items or [])]
