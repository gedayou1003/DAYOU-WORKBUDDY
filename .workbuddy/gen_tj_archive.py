# -*- coding: utf-8 -*-
"""生成 T&J（Truth and Justice）原始记录归档，一字不差原文。
从 zsxq_fetch_raw.json 筛选 T&J 帖子 → 生成 outputs/TRUTH_AND_JUSTICE_原始记录_YYYY-MM-DD.md
用法：python gen_tj_archive.py
"""
import os, json
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, 'zsxq_fetch_raw.json')

with open(SRC, encoding='utf-8') as f:
    d = json.load(f)

# 筛选 T&J 帖子
tj = [t for t in d if 'Truth and Justice' in t.get('group', '') or 'T&J' in t.get('group', '')]
tj.sort(key=lambda x: x['create_time'])

today = datetime.now().strftime('%Y-%m-%d')

# 动态抓取窗口：取 zsxq_fetch_raw.json 里实际内容的时间范围
ts = sorted(x.get('create_time', '') for x in d if x.get('create_time'))
win_start = ts[0][:19] if ts else '未知'
win_end = ts[-1][:19] if ts else '未知'

md = f'''# Truth and Justice 原始记录归档 · {today}

> 一字不差原文归档 · 摘自知识星球「Truth and Justice」频道 · 仅供本人查阅使用

## 抓取窗口

- 抓取时段：{win_start} ~ {win_end}
- 本期共 **{len(tj)}** 条
- 抓取通道：zsxq-cli Skill

---

'''

for i, t in enumerate(tj, 1):
    title = t.get('text', '').replace('\n', ' ')[:80]
    files = t.get('files') or []
    file_txt = '、'.join(f"{f.get('name', '?')} ({f.get('size', 0)//1024}KB)" for f in files) or '无'
    md += f'''## [{i}] {t['create_time']} · {title}...

- **topic_id**: {t.get('topic_id')}
- **发布时间**: {t.get('create_time')}
- **类型**: {t.get('type', 'text')}
- **正文（原文一字不差）**:

```
{t.get('text', '')}
```

- **附件**（{len(files)}）: {file_txt}
- **图片**（{len(t.get('images') or [])}）: {len(t.get('images') or [])} 张

---

'''

out = os.path.join(ROOT, 'outputs', f'TRUTH_AND_JUSTICE_原始记录_{today}.md')
with open(out, 'w', encoding='utf-8') as f:
    f.write(md)

print(f"T&J 归档完成，{len(tj)} 条 -> {out}")
