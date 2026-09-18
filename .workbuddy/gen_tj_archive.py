# -*- coding: utf-8 -*-
"""生成「DRAGON BALL模型」原始记录归档，一字不差原文。

从 zsxq_fetch_raw.json 筛选目标星球帖子
→ 生成 outputs/DRAGON_BALL_原始记录_YYYY-MM-DD.md

用法：python gen_tj_archive.py

2026-09-18 改名（用户要求隐藏星球原名）：
  1) 输出文件名由旧前缀 `*_原始记录_*.md` 改为 `DRAGON_BALL_原始记录_*.md`
     （check_integrity.py 的归档缺口检测已同步；23 个历史归档已一并改名）
  2) 筛选口径由「按 group 显示名匹配」改为「按 gid 匹配」——
     gid 是稳定标识、与显示名解耦。改名前那种「拿星球名当匹配串」的写法
     会在改名后直接失效，且会把原名永久留在脚本里。
"""
import os
import json
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, 'zsxq_fetch_raw.json')

# 目标星球按 gid 识别（唯一、稳定，不受显示名变更影响）
TARGET_GID = '88512145458842'

with open(SRC, encoding='utf-8') as f:
    d = json.load(f)

tj = [t for t in d if str(t.get('gid')) == TARGET_GID]
tj.sort(key=lambda x: x['create_time'])

today = datetime.now().strftime('%Y-%m-%d')

# 动态抓取窗口：取 zsxq_fetch_raw.json 里实际内容的时间范围
ts = sorted(x.get('create_time', '') for x in d if x.get('create_time'))
win_start = ts[0][:19] if ts else '未知'
win_end = ts[-1][:19] if ts else '未知'

md = f'''# DRAGON BALL模型 原始记录归档 · {today}

> 一字不差原文归档 · 摘自知识星球「DRAGON BALL模型」频道 · 仅供本人查阅使用

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

out = os.path.join(ROOT, 'outputs', f'DRAGON_BALL_原始记录_{today}.md')
with open(out, 'w', encoding='utf-8') as f:
    f.write(md)

print(f"DRAGON BALL模型 归档完成，{len(tj)} 条 -> {out}")
