# -*- coding: utf-8 -*-
"""生成晨报匿名版：星球名+人名 -> 代号，文末附解密表
用法：python anonymize_report.py [YYYY-MM-DD]  （不传则默认今天）"""
import re, io, sys, os
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
from paths import OUTPUTS

DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
SRC = os.path.join(OUTPUTS, f"知识星球晨报_{DATE}.md")
DST = os.path.join(OUTPUTS, f"知识星球晨报_{DATE}_匿名版.md")

with io.open(SRC, encoding="utf-8") as f:
    text = f.read()

# 保护：文件路径中的真实文件名不被替换（否则路径失效）
import re as _re
path_holders = []
def _protect_paths(m):
    path_holders.append(m.group(0))
    return f"@@PATH{len(path_holders)-1}@@"
text = _re.sub(r"`[^`]*\.(md|html|json|PDF|pdf|docx|txt)`", _protect_paths, text)

# 替换映射：先长名后短名，避免交叉污染
replacements = [
    ("卫斯李的投研笔记", "星球②"),
    ("AI 产业链地图·Serenity 速报", "星球⑦"),
    ("Truth and Justice", "星球③"),
    ("180K Research", "星球⑥"),
    ("大鹏鸟笔记", "星球④"),
    ("基业长青+", "星球①"),
    ("短评&信息（可接ai）", "星球⑤"),
    ("短评&信息", "星球⑤"),
    ("基业长青", "知识库A"),
    ("浑水调研", "知识库B"),
    ("xxpq", "知识库C"),
    ("游资流沙河", "游资A"),
    ("流沙河", "游资A"),
    ("好运哥", "游资B"),
    ("卫斯李", "星球②"),
    ("大鹏鸟", "星球④"),
    ("T\\&J", "星球③"),  # 转义形式
    ("T&J", "星球③"),
    ("180K", "星球⑥"),
    ("AI 产业链", "星球⑦"),
]

for old, new in replacements:
    text = text.replace(old, new)

# 修正可能的双代号粘连（如 "星球② 星球②" 由相邻替换产生）
text = re.sub(r"(星球[①②③④⑤⑥⑦⑧⑨⑩])\s*\1", r"\1", text)
# 修正 "知识库B知识库" 这类重复
text = re.sub(r"(知识库[ABC])\s*知识库", r"\1", text)

# 还原文件路径
for i, p in enumerate(path_holders):
    text = text.replace(f"@@PATH{i}@@", p)

# 文末解密表
decode_table = """---

## 附：匿名代号解密表（仅供追溯，阅后可删除本节）

| 代号 | 对应星球/知识库 |
|------|----------------|
| 星球① | ⭕ 基业长青+ |
| 星球② | 卫斯李的投研笔记 |
| 星球③ | Truth and Justice |
| 星球④ | 大鹏鸟笔记 |
| 星球⑤ | 短评&信息 |
| 星球⑥ | 180K Research |
| 星球⑦ | AI 产业链地图·Serenity 速报 |
| 游资A | 流沙河（大鹏鸟转述的游资观点） |
| 游资B | 好运哥 |
| 知识库A | IMA【基业长青】浑水投研🥈 |
| 知识库B | IMA【浑水调研】叫我第一名🥇 |
| 知识库C | IMA xxpq |

> 匿名原则：所有星球名、人名、游资名一律以代号呈现，阅读时只看观点本身，避免主观锚定。
"""

with io.open(DST, "w", encoding="utf-8") as f:
    f.write(text + decode_table)

# 校验：确认无残留名字
remaining = []
for name in ["卫斯李", "大鹏鸟", "流沙河", "T&J", "T\\&J", "Truth and Justice", "基业长青+", "180K Research", "AI 产业链地图", "短评&信息", "好运哥", "浑水调研", "xxpq", "知识库B知识库"]:
    if name in text:
        remaining.append(name)

print("匿名版已生成:", DST)
print("残留名字检查:", remaining if remaining else "无残留 ✅")
print("字节数:", len(text.encode("utf-8")))
