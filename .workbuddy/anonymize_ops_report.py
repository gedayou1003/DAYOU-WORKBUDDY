# -*- coding: utf-8 -*-
"""作战报告脱敏：真实星球名 → 代号（星球①~⑦），并删除文末「星球代号对照表」。

背景（2026-09-26 用户指令）
----------------------------
旧匿名化 `anonymize_report.py` 只套在旧版「知识星球晨报」上、且会**附文末解密表**；
新的「作战报告」生成链路直接输出真实星球名（卫斯李 / 大鹏鸟 / 180K / 基业长青+ /
AI 产业链地图 / 短评&信息），附录 B 还附了一张「星球代号对照表」。
用户要求：
    ① 信息来源（真实星球名）一律换成代号；
    ② 对照表（附录 B）也一并隐藏（删除）。

与 anonymize_report.py 的区别：
    - 目标文件是「作战报告」（作战报告_*.md），不是「知识星球晨报」；
    - 不再附文末解密表（用户要求删对照表）；
    - 额外处理「DRAGON BALL / DRAGONBALL → 星球③」（原匿名化只做到 Truth and Justice → DRAGON BALL，
      未进一步编号化）。

用法：
    $PY .workbuddy/anonymize_ops_report.py <报告.md>            # 原地脱敏（覆盖）
    $PY .workbuddy/anonymize_ops_report.py <报告.md> --out B.md # 输出到别处（不覆盖源）

退出码：0 成功且零残留 · 1 失败（参数 / 读不到 / 残留未清 / 写不了）
"""
import io
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为
        pass

# 顺序敏感：全称在前、简称在后，避免简称先替换残留全称尾巴（如「180K Research」先于「180K」）。
REPLACEMENTS = [
    ("卫斯李的投研笔记", "星球②"),
    ("AI 产业链地图·Serenity 速报", "星球⑦"),   # 附录 B 写法（有空格）
    ("AI 产业链地图·Serenity速报", "星球⑦"),    # 附录 A 写法（无空格）
    ("AI 产业链地图", "星球⑦"),
    ("180K Research", "星球⑥"),
    ("大鹏鸟笔记", "星球④"),
    ("⭕ 基业长青+", "星球①"),
    ("基业长青+", "星球①"),
    ("⭕ 短评&信息", "星球⑤"),
    ("短评&信息", "星球⑤"),
    ("DRAGON BALL", "星球③"),
    ("DRAGONBALL", "星球③"),
    ("卫斯李", "星球②"),
    ("大鹏鸟", "星球④"),
    ("180K", "星球⑥"),
]

# 脱敏后不允许再出现的真实名（漏配哨兵）。
# 注意不含「AI 产业链」（泛化词，可能指产业概念），只含精确星球全称「AI 产业链地图」。
RESIDUAL = [
    "卫斯李", "大鹏鸟", "180K", "基业长青", "AI 产业链地图",
    "短评&信息", "DRAGON BALL", "DRAGONBALL", "Serenity",
    "Truth and Justice", "T&J", "T\\&J",
]


def anonymize(text):
    """返回脱敏后的正文。调用方负责残留检查（本函数只管替换 + 删段）。"""
    body = text
    for old, new in REPLACEMENTS:
        body = body.replace(old, new)

    # 删除附录 B（星球代号对照表）整段：从「## 附录 B」往前吞掉前面的 --- 分隔，
    # 一直到「## 产物清单」为止，产物清单保留。
    idx_b = body.find('## 附录 B')
    idx_prod = body.find('## 产物清单')
    if idx_b != -1 and idx_prod != -1 and idx_b < idx_prod:
        sep = body.rfind('\n---\n', 0, idx_b)
        if sep != -1:
            body = body[:sep] + '\n---\n' + body[idx_prod:]

    # 删了附录 B 后，「附录 A」编号孤立 → 去掉编号；正文里的引用改为「文末附录」
    body = body.replace('## 附录 A', '## 附录')
    body = body.replace('说明见附录 A', '说明见文末附录')
    body = body.replace('附录 A/B', '附录')   # 产物清单里的残留引用（附录 B 已删）

    # 双代号粘连修正（如「星球② 星球②」）
    body = re.sub(r'(星球[①②③④⑤⑥⑦])\s*\1', r'\1', body)
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
    try:
        text = io.open(src, encoding='utf-8').read()
    except Exception as e:
        sys.stderr.write('[FAIL] 报告读不动（%s：%s）\n' % (type(e).__name__, e))
        return 1

    body = anonymize(text)

    left = [n for n in RESIDUAL if n in body]
    if left:
        sys.stderr.write('[FAIL] 脱敏后仍有真实名残留：%s —— 不写产物\n' % '、'.join(left))
        return 1

    try:
        io.open(dst, 'w', encoding='utf-8').write(body)
    except Exception as e:
        sys.stderr.write('[FAIL] 写不了（%s：%s）\n' % (type(e).__name__, e))
        return 1

    print('脱敏完成：%s（%d 字）' % (dst, len(body)))
    print('真实名残留：无')
    return 0


if __name__ == '__main__':
    sys.exit(main())
