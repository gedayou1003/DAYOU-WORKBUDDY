# -*- coding: utf-8 -*-
"""作战报告「隐掉」处理：把「星球①~⑦」代号与「星球」相关泛称一律隐去。

背景（2026-09-26 用户第三轮指令）：
    前两轮已把真实星球名 → 代号（星球①~⑦）并删除对照表（附录 B）。
    本轮用户：「别星球X了，就隐掉吧」——连代号也不要，来源直接隐去。
本脚本对**已代号化**的报告再处理：删除星球代号与「星球」相关泛称，
使对外报告不出现任何「星球」标识。

用法：
    $PY .workbuddy/hide_planets.py <报告.md> [--out B.md]
"""
import io
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 隐掉后不允许再出现的真实名/代号（漏配哨兵）
RESIDUAL = [
    "卫斯李", "大鹏鸟", "180K", "基业长青", "AI 产业链地图",
    "短评&信息", "DRAGON BALL", "DRAGONBALL", "Serenity",
    "Truth and Justice", "T&J", "T\\&J", "星球",
]

# 生硬残迹哨兵（删除星球代号后不应留下的残缺句式）
ARTIFACT = [
    "与 （", "与同源去重", "（的 ", "三篇 有摘要",
    "不做 原文", "本期 两条短讯", "| **合计** | | | ",
]


def hide(text):
    body = text

    # 0) v5 因子简写「星球③ -1」需保留因子名「定调」
    body = body.replace('星球③ -1', '定调 -1')

    # 1) 条数统计行 → 只留总数
    body = body.replace(
        '星球② 15 条 + 星球⑦ 4 条 + 星球① 3 条 + 星球③ 2 条 + 星球④ 1 条 + 星球⑥ 1 条；星球⑤本窗口内无更新',
        '本期窗口 26 条内容')

    # 2) 特殊：**星球⑦（4 条）** → **另有 4 条**
    body = body.replace('**星球⑦（4 条）**', '**另有 4 条**')

    # 3) 特殊：句首「星球③ 的「」不自然
    body = body.replace('星球③ 的「', '「')

    # 4) 附录 A 来源列（表格里「| 星球X |」整列删除）+ 表头列名
    body = re.sub(r'\|\s*星球[①②③④⑤⑥⑦]\s*\|', '|', body)
    body = body.replace('| 通道 | 工具 | 星球 | 本期条数 | 备注 |',
                        '| 通道 | 工具 | 本期条数 | 备注 |')
    body = body.replace('|---|---|---|---|---|', '|---|---|---|---|')

    # 5) 删除其余「星球X」（正文来源标注）
    body = re.sub(r'星球[①②③④⑤⑥⑦]\s*', '', body)

    # 6) 泛称「星球」相关词
    body = body.replace('跨星球观点对比', '多方观点对比')
    body = body.replace('跨星球重复挂载', '多处重复挂载')
    body = body.replace('跨星球一致的', '多方一致的')
    body = body.replace('星球窗口', '资讯窗口')
    body = body.replace('第一块 星球信息（知识星球收盘快报', '第一块 资讯信息（收盘快报')
    body = body.replace('窗口内星球内容', '窗口内资讯内容')
    body = body.replace('星球文字覆盖', '资讯文字覆盖')

    # 7) 删除附录 B（对照表）
    idx_b = body.find('## 附录 B')
    idx_prod = body.find('## 产物清单')
    if idx_b != -1 and idx_prod != -1 and idx_b < idx_prod:
        sep = body.rfind('\n---\n', 0, idx_b)
        if sep != -1:
            body = body[:sep] + '\n---\n' + body[idx_prod:]

    # 8) 附录 A 编号处理
    body = body.replace('## 附录 A', '## 附录')
    body = body.replace('说明见附录 A', '说明见文末附录')
    body = body.replace('附录 A/B', '附录')

    # 9) 清理括号边界（只处理括号内外多余空格，不做全局空格压缩——
    #    全局压缩会把 markdown 嵌套列表/代码块的缩进压平，破坏层级）
    body = body.replace('（ ', '（').replace(' ）', '）')

    # 10) 修复删除星球代号后留下的生硬残迹（已对照 65705ce 原文逐一验证）
    body = body.replace('与 （', '与（')                       # 行29：与 （17:10 → 与（17:10
    body = body.replace('与同源去重', '与主线 1 同源，已去重')   # 行311 补主语
    body = body.replace('仅读关键图（的 ', '仅读关键图（')        # 行317 去掉遗留「的」
    body = body.replace('三篇 有摘要', '三篇有摘要')             # 行317 去空格
    body = body.replace('收盘档不做 原文', '收盘档不做原文')      # 行319 去空格
    body = body.replace('本期 两条短讯', '本期两条短讯')          # 行319 去空格
    body = body.replace('| **合计** | | | **26** |',
                        '| **合计** | | **26** |')            # 附录A 合计行删星球空列

    return body


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    src = argv[0]
    dst = src
    if '--out' in argv:
        i = argv.index('--out')
        if i + 1 >= len(argv):
            sys.stderr.write('[FAIL] --out 后面要跟路径\n')
            return 1
        dst = argv[i + 1]
    if not os.path.isfile(src):
        sys.stderr.write('[FAIL] 找不到报告：%s\n' % src)
        return 1
    text = io.open(src, encoding='utf-8').read()
    body = hide(text)
    left = [n for n in RESIDUAL if n in body]
    if left:
        sys.stderr.write('[FAIL] 隐掉后仍有残留：%s —— 不写产物\n' % '、'.join(left))
        return 1
    left_a = [n for n in ARTIFACT if n in body]
    if left_a:
        sys.stderr.write('[FAIL] 仍有生硬残迹：%s —— 不写产物\n' % '、'.join(left_a))
        return 1
    io.open(dst, 'w', encoding='utf-8').write(body)
    print('隐掉完成：%s（%d 字）' % (dst, len(body)))
    print('真实名/星球残留：无')
    print('生硬残迹：无')
    return 0


if __name__ == '__main__':
    sys.exit(main())
