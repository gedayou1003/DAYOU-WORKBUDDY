# -*- coding: utf-8 -*-
"""生成晨报 8/21 匿名版（独立脚本版本）"""
import re, io

SRC = r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12\outputs\知识星球晨报_2026-08-21.md'
DST = r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12\outputs\知识星球晨报_2026-08-21_匿名版.md'

with io.open(SRC, encoding='utf-8') as f:
    text = f.read()

# 保护路径
path_holders = []
def _protect_paths(m):
    path_holders.append(m.group(0))
    return '@@PATH{0}@@'.format(len(path_holders)-1)
text = re.sub(r'`[^`]*\.(md|html|json|PDF|pdf|docx|txt)`', _protect_paths, text)

# 替换映射
replacements = [
    ('卫斯李的投研笔记', '星球②'),
    ('AI 产业链地图·Serenity 速报', '星球⑦'),
    ('AI 产业链地图·Serenity速报', '星球⑦'),
    ('Truth and Justice', '星球③'),
    ('180K Research', '星球⑥'),
    ('投行圈子~私密交流圈', '星球⑩'),
    ('口罩哥的星球', '星球⑧'),
    ('大鹏鸟笔记', '星球④'),
    ('⭕ 基业长青+', '星球①'),
    ('短评&信息（可接ai）', '星球⑤'),
    ('短评&信息', '星球⑤'),
    ('信息平权', '星球⑨'),
    ('基业长青', '知识库A'),
    ('浑水调研', '知识库B'),
    ('xxpq', '知识库C'),
    ('流沙河', '游资A'),
    ('好运哥', '游资B'),
    ('卫斯李', '星球②'),
    ('大鹏鸟', '星球④'),
    ('T&J', '星球③'),
    ('口罩哥', '星球⑧'),
    ('180K', '星球⑥'),
    ('AI 产业链', '星球⑦'),
    ('投行圈子', '星球⑩'),
]

for old, new in replacements:
    text = text.replace(old, new)

# 修正重复
text = re.sub(r'(星球[①②③④⑤⑥⑦⑧⑨⑩])\s*\1', r'\1', text)
text = re.sub(r'(知识库[ABC])\s*知识库', r'\1', text)

# 还原路径
for i, p in enumerate(path_holders):
    text = text.replace('@@PATH{0}@@'.format(i), p)

# 解码表
decode_table = '''---

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
| 星球⑧ | 口罩哥的星球 |
| 星球⑨ | 信息平权 |
| 星球⑩ | 投行圈子~私密交流圈 |
| 游资A | 流沙河（大鹏鸟转述的游资观点） |
| 游资B | 好运哥 |
| 知识库A | IMA【基业长青】浑水投研🥈 |
| 知识库B | IMA【浑水调研】叫我第一名🥇 |
| 知识库C | IMA xxpq |
'''

text += decode_table

with io.open(DST, 'w', encoding='utf-8') as f:
    f.write(text)

print('匿名版已生成:', DST)
print('字节数:', len(text.encode('utf-8')))

# 检查残留
print('--- 残留检查 ---')
for name in ['卫斯李', '大鹏鸟', 'T&J', '180K', 'AI 产业链', '基业长青', '浑水调研', 'xxpq', '信息平权', '口罩哥', '投行圈子', '短评&信息', 'Truth and Justice', 'Serenity']:
    cnt2 = 0
    for line in text.split('\n'):
        if name in line:
            # 排除路径/解密表/小节标题中必要的引用
            if '```' in line or '|' in line and ('代号' in line or '对应' in line or '---' in line):
                continue
            cnt2 += line.count(name)
    if cnt2 > 0:
        print('残留 {0}: {1} 次'.format(name, cnt2))
