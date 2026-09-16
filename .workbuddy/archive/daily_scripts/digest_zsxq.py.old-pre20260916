# -*- coding: utf-8 -*-
"""提取 zsxq_fetch_raw.json 摘要（供复盘阅读）"""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(os.path.join(BASE, 'zsxq_fetch_raw.json'), encoding='utf-8'))

# 探测结构
def norm(raw):
    if isinstance(raw, list):
        return raw
    for k in ('topics', 'data', 'items', 'records', 'result'):
        if isinstance(raw.get(k), list):
            return raw[k]
    # dict: group_name -> [topics]
    out = []
    for k, v in raw.items():
        if isinstance(v, list):
            for t in v:
                if isinstance(t, dict):
                    t.setdefault('_group', k)
                    out.append(t)
    return out

topics = norm(raw)
L = []
L.append(f'总条数: {len(topics)}')
if topics:
    L.append('样例键: ' + ', '.join(list(topics[0].keys())[:20]))
L.append('')

def txt(t):
    for k in ('text', 'content', 'body', 'talk_text'):
        v = t.get(k)
        if v:
            return str(v)
    return ''

def gname(t):
    for k in ('group_name', '_group', 'group', 'groupName'):
        v = t.get(k)
        if v:
            return str(v)
    return '?'

def ttime(t):
    for k in ('create_time', 'created_at', 'time', 'createTime'):
        v = t.get(k)
        if v:
            return str(v)
    return '?'

for i, t in enumerate(topics, 1):
    body = txt(t)
    body = re.sub(r'\s+', ' ', body).strip()
    L.append(f"[{i}] {gname(t)} | {ttime(t)} | len={len(body)}")
    L.append(body[:600])
    L.append('')

out = os.path.join(BASE, '_zsxq_digest.txt')
with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('OK', len(topics))
