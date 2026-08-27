"""生成 T&J 原始记录归档"""
import json
from datetime import datetime

with open(r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12\.workbuddy\zsxq_fetch_raw.json', encoding='utf-8') as f:
    d = json.load(f)

# 筛选 T&J 帖子
tj = [t for t in d if 'Truth and Justice' in t['group'] or 'T&J' in t['group']]
tj.sort(key=lambda x: x['create_time'])

today = datetime.now().strftime('%Y-%m-%d')

md = f'''# Truth and Justice 原始记录归档 · {today}

> 一字不差原文归档 · 摘自知识星球「Truth and Justice」频道 · 仅供本人查阅使用

## 抓取窗口

- 抓取时段：2026-08-26 16:00 ~ 2026-08-27 08:00
- 本期共 **{len(tj)}** 条
- 抓取通道：zsxq-cli Skill

---

'''

for i, t in enumerate(tj, 1):
    md += f'''## [{i}] {t['create_time']} · {t.get('text','')[:80]}...

- **topic_id**: {t['topic_id']}
- **发布时间**: {t['create_time']}
- **类型**: {t.get('type','text')}
- **正文（原文一字不差）**:

```
{t.get('text','')}
```

- **附件**（{len(t.get('files') or [])}）: {''.join([f"· {f.get('name','?')} ({f.get('size',0)//1024}KB)  " for f in (t.get('files') or [])]) or '无'}
- **图片**（{len(t.get('images') or [])}）: {len(t.get('images') or [])} 张

---

'''

with open(rf'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12\outputs\TRUTH_AND_JUSTICE_原始记录_{today}.md', 'w', encoding='utf-8') as f:
    f.write(md)

print(f"T&J 归档完成，{len(tj)} 条")