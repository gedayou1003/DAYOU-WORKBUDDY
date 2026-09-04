# -*- coding: utf-8 -*-
"""报告版面规范（机器可读），与《报告逻辑排版完整性规范_v2.md》对应。

结构：
  TIER_ALIAS  文件名关键词 -> 档位 key
  BLOCKS      区块 key -> (中文名, [标题正则...])，正则用 re.search 匹配标题行文本
  SLOTS       档位 key -> {'required': [...], 'optional': [...]}
              required 缺块 = ERROR（硬伤，推导链不完整）
              optional 缺块 = WARN（排版不完整，prompt 要求但常漏）
              顺序以 required + optional 的先后为规范顺序，用于「顺序错位」检查。

被 check_layout.py 引用。修改版面规则只需改本文件。
"""

TIER_ALIAS = {
    '晨报': 'morning',
    '午间': 'noon',
    '盘中': 'intraday',
    '收盘': 'close',
    '复盘': 'review',
}

# key: (中文名, [标题正则...])  —— 正则允许措辞微变，覆盖「中文序数 / 第X块 / 无编号」三种标题写法
BLOCKS = {
    'core':       ('核心主线速览',   [r'核心主线速览']),
    'star':       ('星球信息',       [r'星球信息']),
    'judge':      ('信息判断',       [r'信息判断', r'跨星球观点对比', r'观点对比']),
    'tech':       ('技术分析',       [r'技术分析', r'盘面与技术面']),
    'forecast':   ('预判',           [r'预判']),
    'industry':   ('行业强弱榜',     [r'行业强弱榜', r'行业判断']),
    'bias':       ('偏差统计',       [r'偏差.*统计']),
    'appendix_a': ('附录A·抓取通道', [r'附录\s*A']),
    'appendix_b': ('附录B·星球代号', [r'附录\s*B']),
    'products':   ('产物清单',       [r'产物清单']),
    # —— 复盘档专属 ——
    'actual':     ('盘面实际',       [r'盘面实际']),
    'review':     ('预判复盘',       [r'预判.*复盘', r'复盘']),
    'cognition':  ('关键认知',       [r'关键认知']),
    'nextday':    ('次日衔接',       [r'次日衔接', r'次日.*衔接']),
}

SLOTS = {
    # 偏差统计(bias) 是第四块「预判」的子项，规范顺序在行业强弱榜(industry) 之前
    'morning': {
        'required': ['core', 'star', 'judge', 'tech', 'forecast', 'bias', 'industry'],
        'optional': ['appendix_a', 'appendix_b', 'products'],
    },
    'noon': {
        'required': ['core', 'star', 'judge', 'tech', 'forecast', 'bias', 'industry'],
        'optional': ['appendix_a', 'appendix_b'],
    },
    'intraday': {
        'required': ['core', 'star', 'judge', 'tech', 'forecast', 'bias', 'industry'],
        'optional': ['appendix_a', 'appendix_b', 'products'],
    },
    'close': {
        'required': ['core', 'star', 'judge', 'tech', 'forecast', 'bias', 'industry'],
        'optional': ['appendix_a', 'appendix_b'],
    },
    'review': {
        'required': ['actual', 'review', 'bias', 'cognition', 'nextday'],
        'optional': [],
    },
}


def slot_order(tier):
    """返回该档位的规范顺序（required + optional 拼接）。"""
    if tier not in SLOTS:
        return []
    s = SLOTS[tier]
    return s['required'] + s['optional']
