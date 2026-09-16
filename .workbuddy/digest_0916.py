# -*- coding: utf-8 -*-
"""提取 zsxq_fetch_raw.json 摘要（9/16 晨报用，按星球分组 + 时间排序 + 全文）"""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(os.path.join(BASE, 'zsxq_fetch_raw.json'), encoding='utf-8'))


def norm(raw):
    if isinstance(raw, list):
        return raw
    for k in ('topics', 'data', 'items', 'records', 'result'):
        if isinstance(raw.get(k), list):
            return raw[k]
    out = []
    for k, v in raw.items():
        if isinstance(v, list):
            for t in v:
                if isinstance(t, dict):
                    t.setdefault('_group', k)
                    out.append(t)
    return out


topics = norm(raw)


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


def atts(t):
    imgs = t.get('images') or []
    fls = t.get('files') or []
    s = []
    if imgs:
        s.append('IMG%d' % len(imgs))
    if fls:
        s.append('FILE%d' % len(fls))
    return (' ' + ' '.join(s)) if s else ''


L = []
L.append('总条数: %d' % len(topics))
if topics:
    L.append('样例键: ' + ', '.join(list(topics[0].keys())[:25]))
L.append('')

groups = {}
for t in topics:
    groups.setdefault(gname(t), []).append(t)

for g in sorted(groups, key=lambda k: -len(groups[k])):
    ts = sorted(groups[g], key=lambda t: ttime(t))
    L.append('=' * 70)
    L.append('### 星球: %s （%d 条）' % (g, len(ts)))
    L.append('=' * 70)
    for i, t in enumerate(ts, 1):
        body = txt(t)
        body = re.sub(r'[ \t]+', ' ', body).strip()
        L.append('')
        L.append('--- [%s#%d] %s%s ---' % (g, i, ttime(t), atts(t)))
        L.append(body if len(body) <= 3000 else body[:3000] + ' ……[截断]')

out = os.path.join(BASE, '_zsxq_digest_0916.txt')
with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('OK', len(topics), '->', out)
