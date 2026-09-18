import json, os, re, urllib.parse, textwrap

ROOT = r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12'
d = json.load(open(os.path.join(ROOT, '.workbuddy', 'zsxq_fetch_raw.json'), encoding='utf-8'))

def clean(t):
    t = t or ''
    t = re.sub(r'<e type="hashtag"[^>]*title="([^"]*)"[^>]*/>', lambda m: '#' + m.group(1).replace('%23', ''), t)
    t = re.sub(r'<e type="hashtag"[^>]*title="([^"]*)"[^>]*>([^<]*)</e>', lambda m: '#' + m.group(1).replace('%23', ''), t)
    t = re.sub(r'<[^>]+>', '', t)
    try:
        t = urllib.parse.unquote(t)
    except Exception:
        pass
    t = t.replace('\u200b', '').replace('\xa0', ' ')
    return t.strip()

rows = []
for e in d:
    rows.append({
        'group': e.get('group') or '?',
        'time': e.get('create_time', ''),
        'type': e.get('type'),
        'text': clean(e.get('text')),
        'nimg': len(e.get('images') or []),
        'nfile': len(e.get('files') or []),
        'files': [(f.get('name') if isinstance(f, dict) else str(f)) for f in (e.get('files') or [])],
    })
rows.sort(key=lambda r: r['time'])

CAP = 150 * 1024  # per part bytes
parts = []
buf = []
size = 0

def flush():
    global buf, size
    if buf:
        parts.append('\n'.join(buf))
        buf = []
        size = 0

cur = None
for i, r in enumerate(rows):
    if r['group'] != cur:
        cur = r['group']
        buf.append('\n' + '=' * 60)
        buf.append('[星球] ' + cur)
        buf.append('=' * 60)
        size += 200
    head = '\n---- #%d %s | %s | IMG %d | FILE %d ----' % (i, r['time'], r['type'], r['nimg'], r['nfile'])
    body = ''
    if r['files']:
        body += '附件: ' + '; '.join(str(x) for x in r['files']) + '\n'
    body += r['text']
    wrapped = '\n'.join(textwrap.wrap(body, 150, break_long_words=True, replace_whitespace=False)) or '(空)'
    chunk = head + '\n' + wrapped + '\n'
    if size + len(chunk.encode('utf-8')) > CAP and buf:
        flush()
        buf.append('   >>> (接上页) ---- #%d %s %s ----' % (i, r['time'], r['group']))
    buf.append(chunk)
    size += len(chunk.encode('utf-8'))
flush()

for n, p in enumerate(parts, 1):
    fp = os.path.join(ROOT, '.workbuddy', '_dg_p%02d.txt' % n)
    open(fp, 'w', encoding='utf-8').write(p)
    print('PART%02d lines=%d bytes=%d' % (n, p.count('\n') + 1, len(p.encode('utf-8'))))
