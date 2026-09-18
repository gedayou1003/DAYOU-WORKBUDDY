import json, os, re, urllib.parse, textwrap

ROOT = r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12'
d = json.load(open(os.path.join(ROOT, '.workbuddy', 'zsxq_fetch_raw.json'), encoding='utf-8'))

def clean(t):
    t = t or ''
    t = re.sub(r'<e type="hashtag"[^>]*title="([^"]*)"[^>]*/?>', lambda m: '#' + m.group(1).replace('%23', ''), t)
    t = re.sub(r'<[^>]+>', '', t)
    try:
        t = urllib.parse.unquote(t)
    except Exception:
        pass
    t = t.replace('\u200b', '').replace('\xa0', ' ')
    t = re.sub(r'!\[\]\(https?://[^\)]+\)', '[图]', t)
    return t.strip()

rows = []
for e in d:
    rows.append(dict(group=e.get('group') or '?', time=e.get('create_time', ''), type=e.get('type'),
                     text=clean(e.get('text')), nimg=len(e.get('images') or []),
                     nfile=len(e.get('files') or []),
                     files=[(f.get('name') if isinstance(f, dict) else str(f)) for f in (e.get('files') or [])]))
rows.sort(key=lambda r: r['time'])

out = []
for i, r in enumerate(rows):
    if i == 2:  # 跳过 181k 字的摩根大通研报长贴
        out.append('\n---- #2 2026-09-17T16:38 卫斯李 [已跳过：181k 字摩根大通跨资产波动率研报 PDF 转贴] ----\n')
        continue
    out.append('\n---- #%d %s | %s | IMG %d | FILE %d ----' % (i, r['time'], r['group'], r['nimg'], r['nfile']))
    if r['files']:
        out.append('附件: ' + '; '.join(str(x) for x in r['files']))
    out.append(r['text'] or '(无正文)')

txt = textwrap.wrap('\n'.join(out), 150, break_long_words=True, replace_whitespace=False)
fp = os.path.join(ROOT, '.workbuddy', '_dg_filtered.txt')
open(fp, 'w', encoding='utf-8').write('\n'.join(txt))
print('SAVED', fp, 'lines', len(txt), 'bytes', os.path.getsize(fp))
